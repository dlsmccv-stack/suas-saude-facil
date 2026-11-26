import json
import os
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
import httpx
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
import models

b2b_router = APIRouter(prefix="/api/v1", tags=["SUAS B2B & Interoperabilidade"])

# Chave master de sandbox/produção (configure SUAS_B2B_API_KEY no Render)
DEFAULT_B2B_KEY = os.getenv("SUAS_B2B_API_KEY", "suas_b2b_sandbox_2026")

# Chave administrativa exclusiva para confirmar pagamento e ativar unidades (configure SUAS_ADMIN_API_KEY no Render)
ADMIN_API_KEY = os.getenv("SUAS_ADMIN_API_KEY", "")

# Chave exclusiva de monitoramento para o parceiro de TI (configure SUAS_TI_MONITOR_KEY no Render)
TI_MONITOR_KEY = os.getenv("SUAS_TI_MONITOR_KEY", "")

# Configuração opcional de alerta automático via Webhook para WhatsApp (Evolution API, Z-API, n8n, etc.)
TI_WHATSAPP_PHONE = os.getenv("SUAS_TI_WHATSAPP_PHONE", "")
TI_WHATSAPP_WEBHOOK_URL = os.getenv("SUAS_TI_WHATSAPP_WEBHOOK_URL", "")
TI_WHATSAPP_WEBHOOK_TOKEN = os.getenv("SUAS_TI_WHATSAPP_WEBHOOK_TOKEN", "")

# Dados bancários e chave Pix CNPJ para recebimento (Santander PJ - Ag. 4326 / CC 130085637)
PIX_CHAVE_CNPJ = os.getenv("SUAS_PIX_CNPJ", "")
CONTA_BANCARIA_REF = "Santander PJ | Ag. 4326 | CC 130085637"

# Catálogo base: adesão maior que mensalidade (cobre setup/deslocamento) + 20% na recorrência
PLANOS_B2B: Dict[str, Dict[str, Any]] = {
    "farma_digital": {
        "nome": "Farma Digital",
        "adesao": 890.00,
        "mensalidade": 590.00,
        "repasse_ti_perc": 0.20,
    },
    "clinica_agil": {
        "nome": "Clínica Ágil",
        "adesao": 1690.00,
        "mensalidade": 1190.00,
        "repasse_ti_perc": 0.20,
    },
    "hospital_pro": {
        "nome": "Hospital Pro",
        "adesao": 2490.00,
        "mensalidade": 1690.00,
        "repasse_ti_perc": 0.20,
    },
    "enterprise_redes": {
        "nome": "Enterprise & Redes",
        "adesao": 3990.00,
        "mensalidade": 2990.00,
        "repasse_ti_perc": 0.20,
    },
}


def _fmt_moeda(valor: float) -> str:
    return f"{valor:.2f}"


def _unidade_esta_ativa(db: Session, unidade_id: str) -> bool:
    reg = (
        db.query(models.B2BAssinaturaUnidade)
        .filter(models.B2BAssinaturaUnidade.unidade_id == unidade_id)
        .first()
    )
    if not reg or reg.status != "ATIVA":
        return False

    if reg.proximo_vencimento:
        agora_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        if agora_naive > reg.proximo_vencimento:
            reg.status = "SUSPENSA_INADIMPLENCIA"
            reg.instalacao_ativa = False
            db.commit()
            return False

    return True


def verificar_credenciais_b2b(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    x_unidade_id: str = Header(..., description="Identificador da clínica, hospital ou farmácia (tenant)"),
    db: Session = Depends(get_db),
):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
    elif x_api_key:
        token = x_api_key.strip()

    if not token or token != DEFAULT_B2B_KEY:
        raise HTTPException(status_code=401, detail="Chave de API B2B inválida ou ausente.")

    uid = x_unidade_id.strip()

    assinatura = (
        db.query(models.B2BAssinaturaUnidade)
        .filter(models.B2BAssinaturaUnidade.unidade_id == uid)
        .first()
    )

    if assinatura and not _unidade_esta_ativa(db, uid):
        raise HTTPException(
            status_code=402,
            detail="Assinatura pendente ou vencida para esta unidade. Confirme o pagamento para ativar/renovar.",
        )

    return {"unidade_id": uid}


def verificar_credencial_admin(
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None),
):
    if not ADMIN_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="SUAS_ADMIN_API_KEY não configurada no servidor."
        )

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
    elif x_admin_key:
        token = x_admin_key.strip()

    if not token or token != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Chave administrativa inválida ou ausente.")

    return {"perfil": "admin_financeiro"}


def verificar_credencial_monitoramento_ti(
    authorization: Optional[str] = Header(None),
    x_monitor_key: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    if not TI_MONITOR_KEY:
        raise HTTPException(
            status_code=503,
            detail="SUAS_TI_MONITOR_KEY não configurada no servidor."
        )

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
    elif x_monitor_key:
        token = x_monitor_key.strip()
    elif x_api_key:
        token = x_api_key.strip()

    if not token or token != TI_MONITOR_KEY:
        raise HTTPException(status_code=401, detail="Chave de monitoramento de TI inválida ou ausente.")

    return {"perfil": "suporte_ti"}


# --- MODELOS DE ASSINATURA, ADESÃO E ATIVAÇÃO ---

class AdesaoPacoteIn(BaseModel):
    unidade_id: str = Field(..., example="farma_centro_01")
    cnpj_cliente: str = Field(..., example="12345678000199")
    nome_unidade: str = Field(..., example="Farmácia Central")
    email_responsavel: Optional[str] = Field(None, example="gestor@farmaciacentral.com.br")
    responsavel: Optional[str] = Field(None, example="Dra. Mariana")
    whatsapp: Optional[str] = Field(None, example="(86) 99999-0000")
    plano: str = Field(..., example="farma_digital")
    valor_adesao_custom: Optional[float] = Field(None, example=None)


class ConfirmarPagamentoIn(BaseModel):
    unidade_id: str = Field(..., example="farma_centro_01")
    tipo_pagamento: str = Field(..., example="ADESAO", description="ADESAO ou MENSALIDADE")
    comprovante_ref: str = Field(..., example="PIX-CNPJ-SANTANDER-001")
    valor_pago: float = Field(..., example=890.00)


class AlertaWhatsAppIn(BaseModel):
    unidade_id: str = Field(..., example="farma_centro_01")
    titulo: str = Field(..., example="Alerta Clínico / Suporte Técnico")
    mensagem: str = Field(..., example="Unidade requer atenção técnica imediata.")
    telefone_destino: Optional[str] = Field(None, example="5586999999999")


# --- MODELOS DE ENTRADA (CONTRATOS JSON / FHIR-LIKE) ---

class ClinicalEventIn(BaseModel):
    event_type: str = Field(..., example="CHECKIN_TRIAGEM")
    patient_hash: str = Field(..., example="cns_hash_98a7f2")
    patient_name: Optional[str] = Field(None, example="Paciente Demonstração")
    gravidade: Optional[str] = Field("LEVE", example="MODERADO")
    queixa_ou_descricao: Optional[str] = Field(None, example="Febre persistente há 2 dias e dor no corpo")
    medicamentos: Optional[List[str]] = Field(default_factory=list)
    alergias_conhecidas: Optional[List[str]] = Field(default_factory=list)
    condicoes_cronicas: Optional[List[str]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class PredictAdverseIn(BaseModel):
    patient_hash: str = Field(..., example="cns_hash_98a7f2")
    medicamentos_prescritos: List[str] = Field(..., example=["Dipirona 500mg", "Losartana 50mg"])
    alergias_cadastradas: Optional[List[str]] = Field(default_factory=list)
    condicoes_cronicas: Optional[List[str]] = Field(default_factory=list)
    historico_automedicacao: Optional[List[str]] = Field(default_factory=list)


class TrainingTriggerIn(BaseModel):
    setor: str = Field(..., example="PRONTO_SOCORRO")
    motivo_gatilho: str = Field(..., example="ALTA_RECORRENCIA_INTERACAO_AINE")
    gravidade: str = Field("MODERADA", example="ALTA")
    protocolo_recomendado: str = Field(..., example="Revisão de protocolo de analgesia em pacientes hipertensos/alérgicos")
    equipe_alvo: Optional[str] = Field("Enfermagem e Corpo Clínico")


# --- 0. ENDPOINTS: ADESÃO, INSTALAÇÃO AUTOMÁTICA E ASSINATURA RECORRENTE ---

@b2b_router.post("/assinaturas/adesao")
def criar_adesao_unidade(payload: AdesaoPacoteIn, db: Session = Depends(get_db)):
    plano_cfg = PLANOS_B2B.get(payload.plano)
    if not plano_cfg:
        raise HTTPException(status_code=400, detail="Plano inválido.")

    uid = payload.unidade_id.strip()
    valor_adesao = payload.valor_adesao_custom if payload.valor_adesao_custom is not None else plano_cfg["adesao"]
    mensalidade = plano_cfg["mensalidade"]
    repasse_ti = round(mensalidade * plano_cfg["repasse_ti_perc"], 2)
    liquido_operacao = round(mensalidade - repasse_ti, 2)
    custo_setup_estimado = round(max(0.0, valor_adesao - mensalidade), 2)

    existente = (
        db.query(models.B2BAssinaturaUnidade)
        .filter(models.B2BAssinaturaUnidade.unidade_id == uid)
        .first()
    )

    if existente:
        existente.cnpj_cliente = payload.cnpj_cliente
        existente.nome_unidade = payload.nome_unidade
        existente.email_responsavel = payload.email_responsavel
        existente.plano = payload.plano
        existente.plano_nome = plano_cfg["nome"]
        existente.valor_adesao = _fmt_moeda(valor_adesao)
        existente.custo_setup_estimado = _fmt_moeda(custo_setup_estimado)
        existente.mensalidade = _fmt_moeda(mensalidade)
        existente.repasse_ti_mensal = _fmt_moeda(repasse_ti)
        existente.liquido_operacao_mensal = _fmt_moeda(liquido_operacao)
        if not existente.instalacao_ativa:
            existente.status = "AGUARDANDO_ADESAO"
        reg = existente
    else:
        reg = models.B2BAssinaturaUnidade(
            unidade_id=uid,
            cnpj_cliente=payload.cnpj_cliente,
            nome_unidade=payload.nome_unidade,
            email_responsavel=payload.email_responsavel,
            plano=payload.plano,
            plano_nome=plano_cfg["nome"],
            valor_adesao=_fmt_moeda(valor_adesao),
            custo_setup_estimado=_fmt_moeda(custo_setup_estimado),
            mensalidade=_fmt_moeda(mensalidade),
            repasse_ti_mensal=_fmt_moeda(repasse_ti),
            liquido_operacao_mensal=_fmt_moeda(liquido_operacao),
            status="AGUARDANDO_ADESAO",
            instalacao_ativa=False,
            api_key_unidade=f"suas_unit_{uuid.uuid4().hex[:16]}",
            proximo_vencimento=None,
        )
        db.add(reg)

    db.commit()
    db.refresh(reg)

    return {
        "status": reg.status,
        "unidade_id": reg.unidade_id,
        "plano": reg.plano_nome,
        "responsavel": payload.responsavel,
        "whatsapp": payload.whatsapp,
        "cobranca": {
            "valor_adesao": float(reg.valor_adesao),
            "custo_setup_estimado": float(reg.custo_setup_estimado),
            "assinatura_recorrente_mensal": float(reg.mensalidade),
            "repasse_ti_20_porcento_mensal": float(reg.repasse_ti_mensal),
            "chave_pix_cnpj": PIX_CHAVE_CNPJ or "CONFIGURAR_ENV_SUAS_PIX_CNPJ",
            "conta_recebimento": CONTA_BANCARIA_REF,
        },
        "proximo_passo": "Após o pagamento da adesão, confirme via POST /api/v1/assinaturas/confirmar-pagamento para liberar a instalação e o funcionamento."
    }


@b2b_router.post("/assinaturas/confirmar-pagamento")
def confirmar_pagamento_e_ativar(
    payload: ConfirmarPagamentoIn,
    _auth: dict = Depends(verificar_credencial_admin),
    db: Session = Depends(get_db),
):
    uid = payload.unidade_id.strip()
    reg = (
        db.query(models.B2BAssinaturaUnidade)
        .filter(models.B2BAssinaturaUnidade.unidade_id == uid)
        .first()
    )
    if not reg:
        raise HTTPException(status_code=404, detail="Unidade não encontrada na base de assinaturas.")

    agora_utc = datetime.now(timezone.utc)
    agora_naive = agora_utc.replace(tzinfo=None)
    proximo_venc_naive = (agora_utc + timedelta(days=30)).replace(tzinfo=None)

    pagamento = models.B2BPagamentoLog(
        assinatura_id=reg.id,
        unidade_id=uid,
        tipo_pagamento=payload.tipo_pagamento.upper(),
        valor_pago=_fmt_moeda(payload.valor_pago),
        comprovante_ref=payload.comprovante_ref,
        confirmado_em=agora_naive,
    )
    db.add(pagamento)

    reg.status = "ATIVA"
    reg.instalacao_ativa = True
    reg.proximo_vencimento = proximo_venc_naive

    db.commit()
    db.refresh(reg)

    return {
        "status": reg.status,
        "unidade_id": reg.unidade_id,
        "nome_unidade": reg.nome_unidade,
        "instalacao_ativa": reg.instalacao_ativa,
        "api_key_unidade": reg.api_key_unidade,
        "proximo_vencimento": reg.proximo_vencimento.isoformat(),
        "resumo_financeiro": {
            "mensalidade": float(reg.mensalidade),
            "repasse_ti_20_porcento": float(reg.repasse_ti_mensal),
            "sobra_operacao_infra": float(reg.liquido_operacao_mensal),
        },
        "timestamp": agora_utc.isoformat()
    }


@b2b_router.get("/assinaturas/{unidade_id}")
def consultar_status_assinatura(unidade_id: str, db: Session = Depends(get_db)):
    uid = unidade_id.strip()
    reg = (
        db.query(models.B2BAssinaturaUnidade)
        .filter(models.B2BAssinaturaUnidade.unidade_id == uid)
        .first()
    )
    if not reg:
        raise HTTPException(status_code=404, detail="Unidade não encontrada.")

    _unidade_esta_ativa(db, uid)
    db.refresh(reg)

    pagamentos = (
        db.query(models.B2BPagamentoLog)
        .filter(models.B2BPagamentoLog.unidade_id == uid)
        .order_by(models.B2BPagamentoLog.id.desc())
        .all()
    )

    return {
        "unidade_id": reg.unidade_id,
        "cnpj_cliente": reg.cnpj_cliente,
        "nome_unidade": reg.nome_unidade,
        "email_responsavel": reg.email_responsavel,
        "plano": reg.plano,
        "plano_nome": reg.plano_nome,
        "valor_adesao": float(reg.valor_adesao),
        "custo_setup_estimado": float(reg.custo_setup_estimado),
        "mensalidade": float(reg.mensalidade),
        "repasse_ti_mensal": float(reg.repasse_ti_mensal),
        "liquido_operacao_mensal": float(reg.liquido_operacao_mensal),
        "status": reg.status,
        "instalacao_ativa": reg.instalacao_ativa,
        "api_key_unidade": reg.api_key_unidade,
        "proximo_vencimento": reg.proximo_vencimento.isoformat() if reg.proximo_vencimento else None,
        "criado_em": reg.criado_em.isoformat() if reg.criado_em else None,
        "pagamentos": [
            {
                "tipo_pagamento": p.tipo_pagamento,
                "valor_pago": float(p.valor_pago),
                "comprovante_ref": p.comprovante_ref,
                "confirmado_em": p.confirmado_em.isoformat() if p.confirmado_em else None,
            }
            for p in pagamentos
        ],
    }


# --- 1. ENDPOINT: INGESTÃO DE EVENTOS CLÍNICOS (PACOTES 1, 2 E 3) ---

@b2b_router.post("/clinical-events")
def registrar_evento_clinico(
    payload: ClinicalEventIn,
    x_request_id: Optional[str] = Header(None),
    tenant: dict = Depends(verificar_credenciais_b2b),
    db: Session = Depends(get_db),
):
    t0 = time.perf_counter()

    if x_request_id:
        cache_item = (
            db.query(models.B2BIdempotencia)
            .filter(models.B2BIdempotencia.request_key == x_request_id)
            .first()
        )
        if cache_item:
            cached = json.loads(cache_item.response_json)
            cached["idempotent_replay"] = True
            return cached

    event_id = f"EVT-{uuid.uuid4().hex[:10].upper()}"
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    alerta_imediato = None
    if payload.medicamentos and payload.alergias_conhecidas:
        alergias_lower = [a.lower() for a in payload.alergias_conhecidas]
        conflitos = [m for m in payload.medicamentos if any(a in m.lower() for a in alergias_lower)]
        if conflitos:
            alerta_imediato = f"ALERTA CRÍTICO: Possível conflito com alergia cadastrada ({', '.join(conflitos)})."

    evento_db = models.B2BEventoClinico(
        event_id=event_id,
        unidade_id=tenant["unidade_id"],
        event_type=payload.event_type,
        patient_hash=payload.patient_hash,
        patient_name=payload.patient_name or "Cidadão SUAS",
        gravidade=payload.gravidade,
        queixa_ou_descricao=payload.queixa_ou_descricao,
        medicamentos_json=json.dumps(payload.medicamentos or [], ensure_ascii=False),
        alergias_json=json.dumps(payload.alergias_conhecidas or [], ensure_ascii=False),
        condicoes_json=json.dumps(payload.condicoes_cronicas or [], ensure_ascii=False),
        status_fluxo="AGUARDANDO_ACOLHIMENTO",
        alerta_imediato=alerta_imediato,
        metadata_json=json.dumps(payload.metadata or {}, ensure_ascii=False),
        created_at=now_utc.replace(tzinfo=None),
    )
    db.add(evento_db)

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    response = {
        "status": "INGESTED",
        "event_id": event_id,
        "unidade_id": tenant["unidade_id"],
        "alerta_imediato": alerta_imediato,
        "latency_ms": latency_ms,
        "timestamp": now_iso,
    }

    if x_request_id:
        db.add(
            models.B2BIdempotencia(
                request_key=x_request_id,
                response_json=json.dumps(response, ensure_ascii=False),
            )
        )

    db.commit()
    return response


@b2b_router.get("/clinical-events")
def listar_eventos_unidade(
    tenant: dict = Depends(verificar_credenciais_b2b),
    db: Session = Depends(get_db),
):
    itens = (
        db.query(models.B2BEventoClinico)
        .filter(models.B2BEventoClinico.unidade_id == tenant["unidade_id"])
        .order_by(models.B2BEventoClinico.id.desc())
        .limit(50)
        .all()
    )

    eventos_formatados = [
        {
            "event_id": e.event_id,
            "unidade_id": e.unidade_id,
            "event_type": e.event_type,
            "patient_hash": e.patient_hash,
            "patient_name": e.patient_name,
            "gravidade": e.gravidade,
            "queixa_ou_descricao": e.queixa_ou_descricao,
            "medicamentos": json.loads(e.medicamentos_json) if e.medicamentos_json else [],
            "alergias_conhecidas": json.loads(e.alergias_json) if e.alergias_json else [],
            "condicoes_cronicas": json.loads(e.condicoes_json) if e.condicoes_json else [],
            "status_fluxo": e.status_fluxo,
            "alerta_imediato": e.alerta_imediato,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "metadata": json.loads(e.metadata_json) if e.metadata_json else {},
        }
        for e in itens
    ]

    return {
        "unidade_id": tenant["unidade_id"],
        "total": len(eventos_formatados),
        "eventos": eventos_formatados,
    }


# --- 2. ENDPOINT: PREDIÇÃO DE EVENTOS ADVERSOS (PACOTES 2 E 3) ---

@b2b_router.post("/predict-adverse-events")
def predizer_eventos_adversos(
    payload: PredictAdverseIn,
    tenant: dict = Depends(verificar_credenciais_b2b)
):
    t0 = time.perf_counter()
    alertas = []
    risk_score = 0.08

    alergias_l = [a.lower().strip() for a in (payload.alergias_cadastradas or []) if a.strip()]
    cronicas_l = [c.lower().strip() for c in (payload.condicoes_cronicas or []) if c.strip()]
    auto_l = [m.lower().strip() for m in (payload.historico_automedicacao or []) if m.strip()]

    for med in payload.medicamentos_prescritos:
        med_l = med.lower()

        for alg in alergias_l:
            if alg and alg in med_l:
                risk_score = max(risk_score, 0.95)
                alertas.append({
                    "nivel": "CRITICO",
                    "tipo": "ALERGIA_CRUZADA_OU_DIRETA",
                    "medicamento": med,
                    "detalhe": f"Paciente possui alergia registrada a '{alg}' no Cartão Vital.",
                    "conduta_sugerida": "Suspender administração e revisar prescrição imediatamente."
                })

        aines = ["ibuprofeno", "diclofenaco", "nimesulida", "cetoprofeno", "naproxeno"]
        if any(a in med_l for a in aines) and any("hipertens" in c or "renal" in c for c in cronicas_l):
            risk_score = max(risk_score, 0.72)
            alertas.append({
                "nivel": "MODERADO",
                "tipo": "INTERACAO_CONDICAO_CRONICA",
                "medicamento": med,
                "detalhe": "Uso de anti-inflamatório não esteroidal em paciente com condição crônica sensível.",
                "conduta_sugerida": "Avaliar alternativa analgésica e monitorar pressão arterial/função renal."
            })

        if any(med_l in a or a in med_l for a in auto_l):
            risk_score = max(risk_score, 0.65)
            alertas.append({
                "nivel": "MODERADO",
                "tipo": "SOBREPOSICAO_AUTOMEDICACAO",
                "medicamento": med,
                "detalhe": "Medicamento já consta em relato recente de automedicação pelo cidadão.",
                "conduta_sugerida": "Orientar sobre risco de sobredosagem e ajustar posologia."
            })

    nivel_geral = "ALTO" if risk_score >= 0.8 else ("MODERADO" if risk_score >= 0.5 else "BAIXO")
    disparar_treinamento = risk_score >= 0.8

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "prediction_id": f"PRED-{uuid.uuid4().hex[:8].upper()}",
        "unidade_id": tenant["unidade_id"],
        "patient_hash": payload.patient_hash,
        "risk_score": round(risk_score, 2),
        "risk_level": nivel_geral,
        "alertas": alertas,
        "recommend_training_trigger": disparar_treinamento,
        "latency_ms": latency_ms
    }


# --- 3. ENDPOINT: GATILHOS DE TREINAMENTO E PROTOCOLO (PACOTE 3) ---

@b2b_router.post("/training-triggers")
def acionar_gatilho_treinamento(
    payload: TrainingTriggerIn,
    tenant: dict = Depends(verificar_credenciais_b2b),
    db: Session = Depends(get_db),
):
    trigger_id = f"TRG-{uuid.uuid4().hex[:8].upper()}"
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    item_db = models.B2BGatilhoTreinamento(
        trigger_id=trigger_id,
        unidade_id=tenant["unidade_id"],
        setor=payload.setor,
        motivo_gatilho=payload.motivo_gatilho,
        gravidade=payload.gravidade,
        protocolo_recomendado=payload.protocolo_recomendado,
        equipe_alvo=payload.equipe_alvo,
        status="DISPARADO",
        created_at=now_utc.replace(tzinfo=None),
    )
    db.add(item_db)
    db.commit()

    return {
        "status": "TRIGGERED",
        "trigger_id": trigger_id,
        "unidade_id": tenant["unidade_id"],
        "mensagem": f"Microtreinamento/alerta operacional enviado para {payload.equipe_alvo} ({payload.setor}).",
        "timestamp": now_iso
    }


@b2b_router.get("/training-triggers")
def listar_gatilhos_unidade(
    tenant: dict = Depends(verificar_credenciais_b2b),
    db: Session = Depends(get_db),
):
    itens = (
        db.query(models.B2BGatilhoTreinamento)
        .filter(models.B2BGatilhoTreinamento.unidade_id == tenant["unidade_id"])
        .order_by(models.B2BGatilhoTreinamento.id.desc())
        .limit(30)
        .all()
    )

    gatilhos_formatados = [
        {
            "trigger_id": t.trigger_id,
            "unidade_id": t.unidade_id,
            "setor": t.setor,
            "motivo_gatilho": t.motivo_gatilho,
            "gravidade": t.gravidade,
            "protocolo_recomendado": t.protocolo_recomendado,
            "equipe_alvo": t.equipe_alvo,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in itens
    ]

    return {
        "unidade_id": tenant["unidade_id"],
        "total": len(gatilhos_formatados),
        "gatilhos": gatilhos_formatados,
    }


# --- 4. ENDPOINTS: MONITORAMENTO E ALERTAS WHATSAPP PARA PARCEIRO DE TI ---

@b2b_router.get("/suporte/monitoramento")
def obter_monitoramento_ti(
    _auth: dict = Depends(verificar_credencial_monitoramento_ti),
    db: Session = Depends(get_db),
):
    unidades = (
        db.query(models.B2BAssinaturaUnidade)
        .order_by(models.B2BAssinaturaUnidade.id.desc())
        .all()
    )

    unidades_resumo = []
    total_repasse_ti_ativo = 0.0
    ativas_count = 0

    for u in unidades:
        _unidade_esta_ativa(db, u.unidade_id)
        db.refresh(u)

        repasse = float(u.repasse_ti_mensal or 0.0)
        if u.status == "ATIVA":
            ativas_count += 1
            total_repasse_ti_ativo += repasse

        ult_evento = (
            db.query(models.B2BEventoClinico)
            .filter(models.B2BEventoClinico.unidade_id == u.unidade_id)
            .order_by(models.B2BEventoClinico.id.desc())
            .first()
        )

        unidades_resumo.append({
            "unidade_id": u.unidade_id,
            "nome_unidade": u.nome_unidade,
            "cnpj_cliente": u.cnpj_cliente,
            "plano_nome": u.plano_nome,
            "status": u.status,
            "instalacao_ativa": u.instalacao_ativa,
            "proximo_vencimento": u.proximo_vencimento.isoformat() if u.proximo_vencimento else None,
            "repasse_ti_mensal": repasse,
            "ultimo_evento_em": ult_evento.created_at.isoformat() if ult_evento and ult_evento.created_at else None,
            "ultimo_evento_tipo": ult_evento.event_type if ult_evento else None,
        })

    eventos_recentes = (
        db.query(models.B2BEventoClinico)
        .order_by(models.B2BEventoClinico.id.desc())
        .limit(40)
        .all()
    )

    alertas_criticos = []
    for e in eventos_recentes:
        grav = (e.gravidade or "").upper()
        if e.alerta_imediato or grav in {"ALTO", "CRITICO", "CRÍTICO", "GRAVE"}:
            alertas_criticos.append({
                "event_id": e.event_id,
                "unidade_id": e.unidade_id,
                "event_type": e.event_type,
                "gravidade": e.gravidade,
                "alerta_imediato": e.alerta_imediato or e.queixa_ou_descricao,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            })

    gatilhos_recentes = (
        db.query(models.B2BGatilhoTreinamento)
        .order_by(models.B2BGatilhoTreinamento.id.desc())
        .limit(20)
        .all()
    )

    return {
        "resumo": {
            "total_unidades": len(unidades_resumo),
            "unidades_ativas": ativas_count,
            "alertas_criticos_recentes": len(alertas_criticos),
            "repasse_ti_mensal_previsto": round(total_repasse_ti_ativo, 2),
            "webhook_whatsapp_configurado": bool(TI_WHATSAPP_WEBHOOK_URL),
            "whatsapp_suporte_configurado": bool(TI_WHATSAPP_PHONE),
        },
        "unidades": unidades_resumo,
        "alertas_criticos": alertas_criticos,
        "gatilhos_treinamento": [
            {
                "trigger_id": g.trigger_id,
                "unidade_id": g.unidade_id,
                "setor": g.setor,
                "motivo_gatilho": g.motivo_gatilho,
                "gravidade": g.gravidade,
                "status": g.status,
                "created_at": g.created_at.isoformat() if g.created_at else None,
            }
            for g in gatilhos_recentes
        ],
    }


@b2b_router.post("/suporte/alerta-whatsapp")
def disparar_alerta_whatsapp_ti(
    payload: AlertaWhatsAppIn,
    _auth: dict = Depends(verificar_credencial_monitoramento_ti),
):
    telefone = "".join(ch for ch in (payload.telefone_destino or TI_WHATSAPP_PHONE) if ch.isdigit())
    texto_formatado = (
        f"[SUAS Saúde +Fácil • Suporte TI]\n"
        f"Unidade: {payload.unidade_id}\n"
        f"Assunto: {payload.titulo}\n"
        f"Detalhe: {payload.mensagem}"
    )

    wa_link = (
        f"https://wa.me/{telefone}?text={urllib.parse.quote(texto_formatado)}"
        if telefone
        else f"https://wa.me/?text={urllib.parse.quote(texto_formatado)}"
    )

    enviado_webhook = False
    detalhe_webhook = "Webhook não configurado (use o link wa.me ou configure SUAS_TI_WHATSAPP_WEBHOOK_URL)."

    if TI_WHATSAPP_WEBHOOK_URL:
        headers = {"Content-Type": "application/json"}
        if TI_WHATSAPP_WEBHOOK_TOKEN:
            headers["Authorization"] = f"Bearer {TI_WHATSAPP_WEBHOOK_TOKEN}"

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(
                    TI_WHATSAPP_WEBHOOK_URL,
                    headers=headers,
                    json={
                        "phone": telefone,
                        "unidade_id": payload.unidade_id,
                        "title": payload.titulo,
                        "message": texto_formatado,
                    },
                )
            enviado_webhook = 200 <= resp.status_code < 300
            detalhe_webhook = f"Webhook respondeu HTTP {resp.status_code}."
        except Exception as exc:
            detalhe_webhook = f"Falha ao chamar webhook: {exc}"

    return {
        "status": "OK",
        "unidade_id": payload.unidade_id,
        "enviado_webhook": enviado_webhook,
        "detalhe_webhook": detalhe_webhook,
        "whatsapp_link": wa_link,
        "mensagem_formatada": texto_formatado,
    }
