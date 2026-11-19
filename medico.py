import os
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import database
import farmacia_schemas
import models
import regulacao

router = APIRouter(prefix="/medico", tags=["Painel do Médico"])


class RequisicaoExameCreate(BaseModel):
    cidadao_id: Optional[int] = Field(None, description="ID do cidadão no sistema")
    cidadao_nome: Optional[str] = Field(None, description="Nome completo do paciente")
    categoria_exame: str = Field(
        "Laboratorial",
        description="Ex.: Laboratorial, Imagem / Radiologia, Cardiológico / Diagnóstico, Outros Exames Médicos",
    )
    exame_nome: str = Field(..., description="Nome do exame solicitado", example="Hemograma Completo")
    laboratorio_ou_unidade: Optional[str] = Field(
        "Laboratório / Rede Credenciada",
        description="Unidade, laboratório parceiro ou setor executante",
    )
    prioridade: str = Field("Rotina", description="Rotina, Urgente ou Emergência")
    indicacao_clinica: Optional[str] = Field(None, description="Hipótese diagnóstica ou justificativa clínica")
    preparo_observacoes: Optional[str] = Field(None, description="Preparo necessário ou observações ao laboratório")


def verificar_token_medico(
    x_medico_token: Optional[str] = Header(None, alias="X-Medico-Token"),
    x_crm_medico: Optional[str] = Header(None, alias="X-CRM-Medico"),
):
    token_med = os.getenv("SUAS_SAMU_MED_TOKEN", "samu-med-2026")
    token_ext = os.getenv("SUAS_EXTERNAL_TOKEN", "suas-ext-2026")
    tokens_validos = {t for t in (token_med, token_ext) if t}

    if not x_medico_token or x_medico_token not in tokens_validos:
        raise HTTPException(
            status_code=401,
            detail="Acesso médico não autorizado. Token inválido ou ausente.",
        )

    if not x_crm_medico or not x_crm_medico.strip():
        raise HTTPException(
            status_code=400,
            detail="Identificação profissional (CRM/UF) obrigatória para operação clínica.",
        )

    return {"crm": x_crm_medico.strip()}


def extrair_horarios_posologia(posologia: str, fallback: Optional[str] = "08:00, 20:00") -> str:
    """Extrai horários explícitos (ex.: 08:00, 20:00) da posologia ou define padrão pela frequência."""
    encontrados = re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", posologia or "")
    if encontrados:
        return ", ".join(dict.fromkeys(encontrados))
    texto = (posologia or "").lower()
    if "6/6" in texto or "6 em 6" in texto:
        return "06:00, 12:00, 18:00, 00:00"
    if "8/8" in texto or "8 em 8" in texto:
        return "08:00, 16:00, 00:00"
    if "12/12" in texto or "12 em 12" in texto:
        return "08:00, 20:00"
    if "24/24" in texto or "1x" in texto or "uma vez" in texto:
        return "08:00"
    return fallback or "08:00, 20:00"


@router.get(
    "/validar-acesso",
    summary="Valida credenciais de acesso do médico na área de trabalho",
)
def validar_acesso_medico(auth: dict = Depends(verificar_token_medico)):
    return {
        "status": "autenticado",
        "crm": auth["crm"],
        "mensagem": "Acesso médico validado com sucesso.",
    }


@router.post(
    "/prescrever/",
    summary="Médico emite Prescrição (Farmácia/App do Cidadão ou Administração Hospitalar)",
    description="Regista prescrição médica, sincroniza despertador no App do Cidadão quando ambulatorial ou gera guia de administração imediata na unidade hospitalar.",
)
def emitir_prescricao(
    payload: farmacia_schemas.MedicamentoCreate,
    db: Session = Depends(database.get_db),
    auth: dict = Depends(verificar_token_medico),
):
    cidadao = None
    if payload.cidadao_id:
        cidadao = (
            db.query(models.CidadaoPerfil)
            .filter(models.CidadaoPerfil.id == payload.cidadao_id)
            .first()
        )

    nome_beneficiario = (
        payload.cidadao_nome
        or (cidadao.nome_completo if cidadao else None)
        or (f"Cidadão ID #{payload.cidadao_id}" if payload.cidadao_id else "Paciente Não Identificado")
    )

    is_hospitalar = (payload.modalidade_atendimento or "").strip().lower() == "hospitalar_imediato"
    horarios_calculados = extrair_horarios_posologia(payload.posologia, payload.horarios_alarme)

    if is_hospitalar:
        qr_token = f"QR-HOSP-INT-{uuid.uuid4().hex[:8].upper()}"
        detalhes_hosp = []
        if payload.via_administracao:
            detalhes_hosp.append(f"Via: {payload.via_administracao}")
        if payload.local_administracao:
            detalhes_hosp.append(f"Local: {payload.local_administracao}")
        posologia_registrada = (
            f"[USO HOSPITALAR IMEDIATO{' | ' + ' | '.join(detalhes_hosp) if detalhes_hosp else ''}] "
            f"{payload.posologia}"
        )
        tipo_retirada = "Administração Interna na Unidade Hospitalar / Posto de Enfermagem"
    else:
        posologia_registrada = payload.posologia
        if payload.fornecido_pelo_sus:
            qr_token = f"QR-SUS-PHARM-{uuid.uuid4().hex[:8].upper()}"
            tipo_retirada = "Farmácia do SUS (Gratuita)"
        else:
            qr_token = f"QR-DESC-PARCEIRO-{uuid.uuid4().hex[:8].upper()}"
            tipo_retirada = "Rede Particular Parceira (Com Desconto)"

    db_medicamento = models.MedicamentoItem(
        cidadao_id=cidadao.id if cidadao else payload.cidadao_id,
        cidadao_nome=nome_beneficiario,
        medicamento_nome=payload.medicamento_nome,
        dosagem=payload.dosagem or "Conforme prescrição",
        posologia=posologia_registrada,
        quantidade_disponibilizada=payload.quantidade_disponibilizada or 1,
        fornecido_pelo_sus=payload.fornecido_pelo_sus,
        uso_continuo=payload.uso_continuo,
        horarios_alarme=None if is_hospitalar else horarios_calculados,
        qr_code_token=qr_token,
        dispensado=is_hospitalar,
        data_dispensacao=datetime.utcnow() if is_hospitalar else None,
    )
    db.add(db_medicamento)

    alarme_app_ativado = False
    if cidadao and not is_hospitalar:
        db_med_cidadao = models.MedicamentoCidadao(
            cidadao_id=cidadao.id,
            nome_medicamento=payload.medicamento_nome,
            tipo_presricao="Contínuo" if payload.uso_continuo else "Temporário",
            data_inicio=datetime.utcnow(),
            data_fim=None,
            horarios_alarme=horarios_calculados,
        )
        db.add(db_med_cidadao)
        alarme_app_ativado = True

    db.commit()
    db.refresh(db_medicamento)

    return {
        "status": "Sucesso",
        "mensagem": (
            "Prescrição hospitalar interna registada para administração imediata na unidade."
            if is_hospitalar
            else "Prescrição médica registada com sucesso e sincronizada com o App do Cidadão."
        ),
        "modalidade_atendimento": "hospitalar_imediato" if is_hospitalar else "farmacia_externa",
        "medico_responsavel_crm": auth["crm"],
        "cidadao_nome": nome_beneficiario,
        "medicamento_nome": db_medicamento.medicamento_nome,
        "posologia": db_medicamento.posologia,
        "token_gerado": qr_token,
        "tipo_retirada": tipo_retirada,
        "alarme_app_cidadao": {
            "ativado": alarme_app_ativado,
            "horarios_alarme": None if is_hospitalar else horarios_calculados,
            "observacao": (
                "Administração direta pela equipe de enfermagem (sem despertador domiciliar)."
                if is_hospitalar
                else (
                    f"Despertador ativado no App do Cidadão nos horários: {horarios_calculados}"
                    if alarme_app_ativado
                    else "Cidadão sem perfil prévio no App; token QR gerado para retirada."
                )
            ),
        },
    }


@router.post(
    "/requisitar-exame/",
    summary="Médico emite Requisição de Exame (Laboratorial, Imagem ou Demais Exames)",
    description="Regista permanentemente a solicitação de exame no banco e cria notificação/lembrete para o App do Cidadão quando vinculado.",
)
def requisitar_exame_medico(
    payload: RequisicaoExameCreate,
    db: Session = Depends(database.get_db),
    auth: dict = Depends(verificar_token_medico),
):
    cidadao = None
    if payload.cidadao_id:
        cidadao = (
            db.query(models.CidadaoPerfil)
            .filter(models.CidadaoPerfil.id == payload.cidadao_id)
            .first()
        )
        if not cidadao:
            raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    nome_paciente = (
        (payload.cidadao_nome or "").strip()
        or (cidadao.nome_completo if cidadao else None)
    )
    if not nome_paciente:
        raise HTTPException(
            status_code=400,
            detail="Informe cidadao_id válido ou cidadao_nome para emitir a requisição de exame.",
        )

    cat_lower = (payload.categoria_exame or "").lower()
    prefixo = "REQ-LAB" if "lab" in cat_lower else "REQ-EXM"
    codigo_requisicao = f"{prefixo}-{uuid.uuid4().hex[:8].upper()}"
    emitido_em = datetime.utcnow()
    unidade_destino = payload.laboratorio_ou_unidade or "Laboratório / Rede Credenciada"

    db_exame = models.ExameRequisicaoItem(
        codigo_requisicao=codigo_requisicao,
        cidadao_id=cidadao.id if cidadao else payload.cidadao_id,
        cidadao_nome=nome_paciente,
        medico_crm=auth["crm"],
        categoria_exame=payload.categoria_exame,
        exame_nome=payload.exame_nome,
        laboratorio_ou_unidade=unidade_destino,
        prioridade=payload.prioridade,
        indicacao_clinica=payload.indicacao_clinica,
        preparo_observacoes=payload.preparo_observacoes,
        status_exame="SOLICITADO",
        data_solicitacao=emitido_em,
    )
    db.add(db_exame)

    notificacao_criada = False
    if cidadao:
        msg_exame = (
            f"Exame solicitado ({payload.exame_nome}) em {unidade_destino}. "
            f"Código: {codigo_requisicao} | Prioridade: {payload.prioridade}."
        )
        if payload.preparo_observacoes:
            msg_exame += f" Preparo/Obs.: {payload.preparo_observacoes}"

        db_notif = models.NotificacaoCidadaoItem(
            cidadao_id=cidadao.id,
            cidadao_nome=cidadao.nome_completo,
            tipo_evento="EXAME_SOLICITADO",
            titulo=f"Exame Solicitado: {payload.exame_nome}",
            mensagem=msg_exame,
            data_agendada=None,
            alarme_sugerido="07:00",
            lida=False,
            data_criacao=emitido_em,
        )
        db.add(db_notif)
        notificacao_criada = True

    db.commit()
    db.refresh(db_exame)

    return {
        "status": "Sucesso",
        "mensagem": f"Requisição de exame '{payload.exame_nome}' registada para {unidade_destino}.",
        "requisicao_id": db_exame.id,
        "codigo_requisicao": codigo_requisicao,
        "status_exame": "SOLICITADO",
        "medico_responsavel_crm": auth["crm"],
        "data_emissao": emitido_em.isoformat(),
        "paciente": {
            "cidadao_id": cidadao.id if cidadao else payload.cidadao_id,
            "nome": nome_paciente,
        },
        "exame": {
            "categoria_exame": payload.categoria_exame,
            "exame_nome": payload.exame_nome,
            "laboratorio_ou_unidade": unidade_destino,
            "prioridade": payload.prioridade,
            "indicacao_clinica": payload.indicacao_clinica,
            "preparo_observacoes": payload.preparo_observacoes,
        },
        "notificacao_app_cidadao": {
            "registada_no_banco": notificacao_criada,
            "alarme_sugerido": "07:00" if notificacao_criada else None,
            "endpoint_consulta": f"/cidadao/{cidadao.id}/notificacoes-lembretes" if cidadao else None,
        },
    }


@router.post(
    "/regulacao/",
    summary="Médico solicita Regulação Assistencial ou Transferência Hospitalar",
    description="Encaminha pedido de item de regulação ou transferência hospitalar (com origem, destino, especialidade, prioridade e observações) para a fila unificada.",
)
def solicitar_regulacao_medica(
    cidadao_nome: str,
    tipo_item: str,
    unidade_origem: Optional[str] = None,
    unidade_destino: Optional[str] = None,
    especialidade_solicitada: Optional[str] = None,
    prioridade_clinica: Optional[str] = "Média",
    observacoes_medicas: Optional[str] = None,
    db: Session = Depends(database.get_db),
    auth: dict = Depends(verificar_token_medico),
):
    prioridade_final = prioridade_clinica or "Média"
    analise = regulacao.calcular_prioridade_intersetorial(
        nome_paciente=cidadao_nome,
        prioridade_clinica=prioridade_final,
        db=db,
    )

    db_reg = models.RegulacaoItem(
        cidadao_nome=cidadao_nome,
        paciente_nome=cidadao_nome,
        tipo_item=tipo_item,
        unidade_origem=unidade_origem,
        unidade_destino=unidade_destino,
        especialidade_solicitada=especialidade_solicitada or tipo_item,
        prioridade_clinica=prioridade_final,
        observacoes_medicas=observacoes_medicas,
        nis_vinculado=analise["nis_vinculado"],
        vulnerabilidade_suas=analise["vulnerabilidade_suas"],
        beneficio_social_ativo=analise["beneficio_social_ativo"],
        score_prioridade_intersetorial=analise["score"],
        justificativa_priorizacao=analise["justificativa"],
        status="Pendente",
        status_solicitacao="Pendente",
        data_solicitacao=datetime.utcnow(),
    )
    db.add(db_reg)
    db.commit()
    db.refresh(db_reg)

    eh_transferencia = "transfer" in (tipo_item or "").lower()

    return {
        "status": "Sucesso",
        "mensagem": (
            f"Solicitação de transferência hospitalar enviada para a regulação ({unidade_origem or 'Origem não informada'} -> {unidade_destino or 'Destino a definir'})."
            if eh_transferencia
            else f"Solicitação de {tipo_item} enviada para a fila de regulação."
        ),
        "tipo_solicitacao": "transferencia_hospitalar" if eh_transferencia else "regulacao_assistencial",
        "medico_responsavel_crm": auth["crm"],
        "registo_id": db_reg.id,
        "status_regulacao": db_reg.status,
        "score_prioridade_intersetorial": db_reg.score_prioridade_intersetorial,
        "detalhes_transferencia": {
            "paciente_nome": db_reg.paciente_nome,
            "unidade_origem": db_reg.unidade_origem,
            "unidade_destino": db_reg.unidade_destino,
            "especialidade_solicitada": db_reg.especialidade_solicitada,
            "prioridade_clinica": db_reg.prioridade_clinica,
            "observacoes_medicas": db_reg.observacoes_medicas,
        },
    }


@router.get(
    "/prontuario-historico/{cidadao_id}",
    summary="Consultar Histórico Médico e Prescrições do Cidadão",
    description="Permite ao médico consultar os dados vitais e histórico do cidadão antes de prescrever.",
)
def consultar_historico_cidadao(
    cidadao_id: int,
    db: Session = Depends(database.get_db),
    auth: dict = Depends(verificar_token_medico),
):
    cidadao = (
        db.query(models.CidadaoPerfil)
        .filter(models.CidadaoPerfil.id == cidadao_id)
        .first()
    )
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    medicamentos_ativos = [
        {
            "id": m.id,
            "nome_medicamento": m.nome_medicamento,
            "tipo_presricao": m.tipo_presricao,
            "horarios_alarme": m.horarios_alarme,
        }
        for m in cidadao.medicamentos
    ]

    return {
        "id": cidadao.id,
        "paciente": cidadao.nome_completo,
        "cpf": cidadao.cpf,
        "tipo_sanguineo": cidadao.tipo_sanguineo,
        "alergias": cidadao.alergias or "Nenhuma registada",
        "condicoes_cronicas": cidadao.condicoes_cronicas or "Nenhuma",
        "cartao_sus": cidadao.numero_carteira or cidadao.cpf or "SUS / Não informado",
        "possui_plano_saude": cidadao.possui_plano_saude,
        "operadora_plano": cidadao.operadora_plano,
        "medicamentos_app_ativos": medicamentos_ativos,
    }
