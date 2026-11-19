import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

import database
import farmacia_schemas
import models

router = APIRouter(prefix="/medico", tags=["Painel do Médico"])


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
    summary="Médico emite Prescrição e Gera QR Code de Farmácia",
    description="Regista uma prescrição médica e gera automaticamente o token QR Code (SUS Gratuito ou Desconto Particular) com posologia e alarmes.",
)
def emitir_prescricao(
    payload: farmacia_schemas.MedicamentoCreate,
    db: Session = Depends(database.get_db),
    auth: dict = Depends(verificar_token_medico),
):
    if payload.fornecido_pelo_sus:
        qr_token = f"QR-SUS-PHARM-{uuid.uuid4().hex[:8].upper()}"
    else:
        qr_token = f"QR-DESC-PARCEIRO-{uuid.uuid4().hex[:8].upper()}"

    db_medicamento = models.MedicamentoItem(
        **payload.model_dump(),
        qr_code_token=qr_token,
        dispensado=False,
        data_dispensacao=None,
    )
    db.add(db_medicamento)
    db.commit()
    db.refresh(db_medicamento)

    return {
        "status": "Sucesso",
        "mensagem": "Prescrição médica registada com sucesso e associada ao perfil do cidadão.",
        "medico_responsavel_crm": auth["crm"],
        "medicamento_nome": db_medicamento.medicamento_nome,
        "posologia": db_medicamento.posologia,
        "token_gerado": qr_token,
        "tipo_retirada": (
            "Farmácia do SUS (Gratuita)"
            if payload.fornecido_pelo_sus
            else "Rede Particular Parceira (Com Desconto)"
        ),
    }


@router.post(
    "/regulacao/",
    summary="Médico solicita Item de Regulação (Óculos, Prótese, Aparelho Auditivo)",
    description="Encaminha o pedido de regulação do paciente para a fila unificada.",
)
def solicitar_regulacao_medica(
    cidadao_nome: str,
    tipo_item: str,
    db: Session = Depends(database.get_db),
    auth: dict = Depends(verificar_token_medico),
):
    db_reg = models.RegulacaoItem(
        cidadao_nome=cidadao_nome,
        tipo_item=tipo_item,
        status="Pendente",
        data_solicitacao=datetime.utcnow(),
    )
    db.add(db_reg)
    db.commit()
    db.refresh(db_reg)

    return {
        "status": "Sucesso",
        "mensagem": f"Solicitação de {tipo_item} enviada para a fila de regulação.",
        "medico_responsavel_crm": auth["crm"],
        "registo_id": db_reg.id,
        "status_regulacao": db_reg.status,
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

    return {
        "paciente": cidadao.nome_completo,
        "tipo_sanguineo": cidadao.tipo_sanguineo,
        "alergias": cidadao.alergias or "Nenhuma registada",
        "condicoes_cronicas": cidadao.condicoes_cronicas or "Nenhuma",
        "cartao_sus": cidadao.cartao_sus,
    }
