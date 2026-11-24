import os
import uuid
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel, Field

b2b_router = APIRouter(prefix="/api/v1", tags=["SUAS B2B & Interoperabilidade"])

# Chave master de sandbox/produção (configure SUAS_B2B_API_KEY no Render)
DEFAULT_B2B_KEY = os.getenv("SUAS_B2B_API_KEY", "suas_b2b_sandbox_2026")

# Armazenamento em memória para resposta imediata (substitua ou espelhe nas tabelas PostgreSQL)
CLINICAL_EVENTS_DB: List[Dict[str, Any]] = []
TRAINING_TRIGGERS_DB: List[Dict[str, Any]] = []
IDEMPOTENCY_CACHE: Dict[str, Dict[str, Any]] = {}


def verificar_credenciais_b2b(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    x_unidade_id: str = Header(..., description="Identificador da clínica, hospital ou farmácia (tenant)")
):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
    elif x_api_key:
        token = x_api_key.strip()

    if not token or token != DEFAULT_B2B_KEY:
        raise HTTPException(status_code=401, detail="Chave de API B2B inválida ou ausente.")

    return {"unidade_id": x_unidade_id.strip()}


# --- MODELOS DE ENTRADA (CONTRATOS JSON / FHIR-LIKE) ---

class ClinicalEventIn(BaseModel):
    event_type: str = Field(..., example="CHECKIN_TRIAGEM", description="CHECKIN_TRIAGEM | PRESCRICAO | DISPENSA_FARMA | ALTA_CLINICA | REACAO_ADVERSA")
    patient_hash: str = Field(..., example="cns_hash_98a7f2")
    patient_name: Optional[str] = Field(None, example="Paciente Demonstração")
    gravidade: Optional[str] = Field("LEVE", example="MODERADO")
    queixa_ou_descricao: Optional[str] = Field(None, example="Febre persistente há 2 dias e dor no corpo")
    medicamentos: Optional[List[str]] = Field(default_factory=list, example=["Dipirona 500mg", "Amoxicilina 500mg"])
    alergias_conhecidas: Optional[List[str]] = Field(default_factory=list, example=["Dipirona"])
    condicoes_cronicas: Optional[List[str]] = Field(default_factory=list, example=["Hipertensão"])
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class PredictAdverseIn(BaseModel):
    patient_hash: str = Field(..., example="cns_hash_98a7f2")
    medicamentos_prescritos: List[str] = Field(..., example=["Dipirona 500mg", "Losartana 50mg"])
    alergias_cadastradas: Optional[List[str]] = Field(default_factory=list, example=["Dipirona"])
    condicoes_cronicas: Optional[List[str]] = Field(default_factory=list, example=["Hipertensão"])
    historico_automedicacao: Optional[List[str]] = Field(default_factory=list, example=["Ibuprofeno"])


class TrainingTriggerIn(BaseModel):
    setor: str = Field(..., example="PRONTO_SOCORRO")
    motivo_gatilho: str = Field(..., example="ALTA_RECORRENCIA_INTERACAO_AINE")
    gravidade: str = Field("MODERADA", example="ALTA")
    protocolo_recomendado: str = Field(..., example="Revisão de protocolo de analgesia em pacientes hipertensos/alérgicos")
    equipe_alvo: Optional[str] = Field("Enfermagem e Corpo Clínico")


# --- 1. ENDPOINT: INGESTÃO DE EVENTOS CLÍNICOS (PACOTES 1, 2 E 3) ---

@b2b_router.post("/clinical-events")
def registrar_evento_clinico(
    payload: ClinicalEventIn,
    x_request_id: Optional[str] = Header(None),
    tenant: dict = Depends(verificar_credenciais_b2b)
):
    t0 = time.perf_counter()
    if x_request_id and x_request_id in IDEMPOTENCY_CACHE:
        cached = IDEMPOTENCY_CACHE[x_request_id]
        cached["idempotent_replay"] = True
        return cached

    event_id = f"EVT-{uuid.uuid4().hex[:10].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Avaliação rápida automática se houver medicamentos + alergias no evento
    alerta_imediato = None
    if payload.medicamentos and payload.alergias_conhecidas:
        alergias_lower = [a.lower() for a in payload.alergias_conhecidas]
        conflitos = [m for m in payload.medicamentos if any(a in m.lower() for a in alergias_lower)]
        if conflitos:
            alerta_imediato = f"ALERTA CRÍTICO: Possível conflito com alergia cadastrada ({', '.join(conflitos)})."

    registro = {
        "event_id": event_id,
        "unidade_id": tenant["unidade_id"],
        "event_type": payload.event_type,
        "patient_hash": payload.patient_hash,
        "patient_name": payload.patient_name or "Cidadão SUAS",
        "gravidade": payload.gravidade,
        "queixa_ou_descricao": payload.queixa_ou_descricao,
        "medicamentos": payload.medicamentos,
        "alergias_conhecidas": payload.alergias_conhecidas,
        "condicoes_cronicas": payload.condicoes_cronicas,
        "status_fluxo": "AGUARDANDO_ACOLHIMENTO",
        "alerta_imediato": alerta_imediato,
        "created_at": now_iso,
        "metadata": payload.metadata
    }
    CLINICAL_EVENTS_DB.insert(0, registro)

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    response = {
        "status": "INGESTED",
        "event_id": event_id,
        "unidade_id": tenant["unidade_id"],
        "alerta_imediato": alerta_imediato,
        "latency_ms": latency_ms,
        "timestamp": now_iso
    }
    if x_request_id:
        IDEMPOTENCY_CACHE[x_request_id] = response
    return response


@b2b_router.get("/clinical-events")
def listar_eventos_unidade(
    tenant: dict = Depends(verificar_credenciais_b2b)
):
    itens = [e for e in CLINICAL_EVENTS_DB if e["unidade_id"] == tenant["unidade_id"]]
    return {"unidade_id": tenant["unidade_id"], "total": len(itens), "eventos": itens[:50]}


# --- 2. ENDPOINT: PREDIÇÃO DE EVENTOS ADVERSOS (PACOTES 2 E 3) ---

@b2b_router.post("/predict-adverse-events")
def predizer_eventos_adversos(
    payload: PredictAdverseIn,
    tenant: dict = Depends(verificar_credenciais_b2b)
):
    t0 = time.perf_counter()
    alertas = []
    risk_score = 0.08  # baseline baixo

    alergias_l = [a.lower().strip() for a in (payload.alergias_cadastradas or []) if a.strip()]
    cronicas_l = [c.lower().strip() for c in (payload.condicoes_cronicas or []) if c.strip()]
    auto_l = [m.lower().strip() for m in (payload.historico_automedicacao or []) if m.strip()]

    for med in payload.medicamentos_prescritos:
        med_l = med.lower()

        # 1. Cruzamento direto com alergias do Cartão Vital
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

        # 2. Cruzamento com condições crônicas (ex.: AINEs em hipertensos/renais)
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

        # 3. Duplicidade com histórico recente de automedicação
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
    tenant: dict = Depends(verificar_credenciais_b2b)
):
    trigger_id = f"TRG-{uuid.uuid4().hex[:8].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    item = {
        "trigger_id": trigger_id,
        "unidade_id": tenant["unidade_id"],
        "setor": payload.setor,
        "motivo_gatilho": payload.motivo_gatilho,
        "gravidade": payload.gravidade,
        "protocolo_recomendado": payload.protocolo_recomendado,
        "equipe_alvo": payload.equipe_alvo,
        "status": "DISPARADO",
        "created_at": now_iso
    }
    TRAINING_TRIGGERS_DB.insert(0, item)

    return {
        "status": "TRIGGERED",
        "trigger_id": trigger_id,
        "unidade_id": tenant["unidade_id"],
        "mensagem": f"Microtreinamento/alerta operacional enviado para {payload.equipe_alvo} ({payload.setor}).",
        "timestamp": now_iso
    }


@b2b_router.get("/training-triggers")
def listar_gatilhos_unidade(
    tenant: dict = Depends(verificar_credenciais_b2b)
):
    itens = [t for t in TRAINING_TRIGGERS_DB if t["unidade_id"] == tenant["unidade_id"]]
    return {"unidade_id": tenant["unidade_id"], "total": len(itens), "gatilhos": itens[:30]}
