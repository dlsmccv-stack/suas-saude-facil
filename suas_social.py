from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, suas_social_schemas, models

router = APIRouter()

@router.post("/", response_model=suas_social_schemas.SuasSocialResponse)
def criar_atendimento_suas(atendimento: suas_social_schemas.SuasSocialCreate, db: Session = Depends(database.get_db)):
    db_atendimento = models.SuasSocial(**atendimento.dict())
    db.add(db_atendimento)
    db.commit()
    db.refresh(db_atendimento)
    return db_atendimento

@router.get("/", response_model=list[suas_social_schemas.SuasSocialResponse])
def listar_atendimentos_suas(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.SuasSocial).offset(skip).limit(limit).all()
