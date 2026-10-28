from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models, regulacao_schemas
from typing import List
from datetime import datetime

router = APIRouter()

@router.post(
    "/",
    response_model=regulacao_schemas.RegulacaoResponse,
    summary="Solicitar Regulação de Vaga/Leito",
    description="Cria um novo pedido de encaminhamento e regulação médica entre unidades de saúde."
)
def criar_solicitacao_regulacao(
    solicitacao: regulacao_schemas.RegulacaoCreate,
    db: Session = Depends(database.get_db)
):
    db_regulacao = models.RegulacaoItem(
        **solicitacao.model_dump(),
        status_solicitacao="Pendente",
        data_solicitacao=datetime.utcnow()
    )
    db.add(db_regulacao)
    db.commit()
    db.refresh(db_regulacao)
    return db_regulacao

@router.get(
    "/",
    response_model=List[regulacao_schemas.RegulacaoResponse],
    summary="Listar Solicitações de Regulação",
    description="Retorna a lista de todas as solicitações de regulação e transferência de leitos cadastradas."
)
def listar_solicitacoes_regulacao(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    return db.query(models.RegulacaoItem).offset(skip).limit(limit).all()
