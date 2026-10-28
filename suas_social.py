from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, suas_social_schemas, models

router = APIRouter()

@router.post(
    "/", 
    response_model=suas_social_schemas.ApoioSocialResponse,
    summary="Registar atendimento do SUAS",
    description="Regista um novo atendimento ou acompanhamento de apoio social para um cidadão."
)
def criar_atendimento_suas(atendimento: suas_social_schemas.ApoioSocialCreate, db: Session = Depends(database.get_db)):
    db_atendimento = models.SuasSocial(**atendimento.model_dump())
    db.add(db_atendimento)
    db.commit()
    db.refresh(db_atendimento)
    return db_atendimento

@router.get(
    "/", 
    response_model=list[suas_social_schemas.ApoioSocialResponse],
    summary="Listar atendimentos do SUAS",
    description="Retorna a lista de todos os registos e atendimentos de assistência social cadastrados."
)
def listar_atendimentos_suas(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.SuasSocial).offset(skip).limit(limit).all()
