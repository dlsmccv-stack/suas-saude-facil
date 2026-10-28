from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models, farmacia_schemas
from typing import List
import uuid
from datetime import datetime

router = APIRouter(prefix="/medico", tags=["Painel do Médico"])

@router.post(
    "/prescrever/",
    summary="Médico emite Prescrição e Gera QR Code de Farmácia",
    description="Regista uma prescrição médica e gera automaticamente o token QR Code (SUS Gratuito ou Desconto Particular) com posologia e alarmes."
)
def emitir_prescricao(
    payload: farmacia_schemas.MedicamentoCreate,
    db: Session = Depends(database.get_db)
):
    qr_token = None
    if payload.fornecido_pelo_sus:
        qr_token = f"QR-SUS-PHARM-{uuid.uuid4().hex[:8].upper()}"
    else:
        qr_token = f"QR-DESC-PARCEIRO-{uuid.uuid4().hex[:8].upper()}"

    db_medicamento = models.MedicamentoItem(
        **payload.model_dump(),
        qr_code_token=qr_token,
        dispensado=False,
        data_dispensacao=None
    )
    db.add(db_medicamento)
    db.commit()
    db.refresh(db_medicamento)

    return {
        "status": "Sucesso",
        "mensagem": "Prescrição médica registada com sucesso e associada ao perfil do cidadão.",
        "medicamento_nome": db_medicamento.medicamento_nome,
        "posologia": db_medicamento.posologia,
        "token_gerado": qr_token,
        "tipo_retirada": "Farmácia do SUS (Gratuita)" if payload.fornecido_pelo_sus else "Rede Particular Parceira (Com Desconto)"
    }

@router.post(
    "/regulacao/",
    summary="Médico solicita Item de Regulação (Óculos, Prótese, Aparelho Auditivo)",
    description="Encaminha o pedido de regulação do paciente para a fila unificada."
)
def solicitar_regulacao_medica(
    cidadao_nome: str,
    tipo_item: str,
    db: Session = Depends(database.get_db)
):
    db_reg = models.RegulacaoItem(
        cidadao_nome=cidadao_nome,
        tipo_item=tipo_item,
        status="Pendente",
        data_solicitacao=datetime.utcnow()
    )
    db.add(db_reg)
    db.commit()
    db.refresh(db_reg)

    return {
        "status": "Sucesso",
        "mensagem": f"Solicitação de {tipo_item} enviada para a fila de regulação.",
        "registo_id": db_reg.id,
        "status_regulacao": db_reg.status
    }

@router.get(
    "/prontuario-historico/{cidadao_id}",
    summary="Consultar Histórico Médico e Prescrições do Cidadão",
    description="Permite ao médico consultar os dados vitais e histórico do cidadão antes de prescrever."
)
def consultar_historico_cidadao(
    cidadao_id: int,
    db: Session = Depends(database.get_db)
):
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    return {
        "paciente": cidadao.nome_completo,
        "tipo_sanguineo": cidadao.tipo_sanguineo,
        "alergias": cidadao.alergias or "Nenhuma registada",
        "condicoes_cronicas": cidadao.condicoes_cronicas or "Nenhuma",
        "cartao_sus": cidadao.cartao_sus
    }
