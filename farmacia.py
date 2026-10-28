from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models, farmacia_schemas
from typing import List
import uuid
from datetime import datetime

router = APIRouter()

@router.post(
    "/",
    response_model=farmacia_schemas.MedicamentoResponse,
    summary="Registar dispensação ou receita de medicamento",
    description="Cria um novo registo de medicamento associado a um cidadão, gerando automaticamente um token QR Code único para retirada."
)
def criar_medicamento(
    medicamento: farmacia_schemas.MedicamentoCreate,
    db: Session = Depends(database.get_db)
):
    # Gera um token único de QR Code para a retirada do medicamento
    qr_token = f"QR-PHARM-{uuid.uuid4().hex[:8].upper()}"
    
    db_medicamento = models.MedicamentoItem(
        **medicamento.model_dump(),
        qr_code_token=qr_token,
        dispensado=False,
        data_dispensacao=None
    )
    db.add(db_medicamento)
    db.commit()
    db.refresh(db_medicamento)
    return db_medicamento

@router.get(
    "/",
    response_model=List[farmacia_schemas.MedicamentoResponse],
    summary="Listar medicamentos registados",
    description="Retorna a lista de todos os registos e receitas de medicamentos cadastrados no sistema."
)
def listar_medicamentos(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    return db.query(models.MedicamentoItem).offset(skip).limit(limit).all()

@router.post(
    "/dispensar/",
    response_model=farmacia_schemas.MedicamentoResponse,
    summary="Dispensar medicamento por QR Code",
    description="Valida o token do QR Code apresentado pelo cidadão e marca o medicamento como dispensado/retirado."
)
def dispensar_medicamento(
    payload: farmacia_schemas.MedicamentoDispensacaoQRCode,
    db: Session = Depends(database.get_db)
):
    db_medicamento = db.query(models.MedicamentoItem).filter(
        models.MedicamentoItem.qr_code_token == payload.qr_code_token
    ).first()
    
    if not db_medicamento:
        raise HTTPException(status_code=404, detail="Token QR Code de farmácia não encontrado.")
    
    if db_medicamento.dispensado:
        raise HTTPException(status_code=400, detail="Este medicamento já foi dispensado anteriormente.")
    
    db_medicamento.dispensado = True
    db_medicamento.data_dispensacao = datetime.utcnow()
    db.commit()
    db.refresh(db_medicamento)
    return db_medicamento
