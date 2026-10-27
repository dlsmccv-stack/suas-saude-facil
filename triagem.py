from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, triagem_schemas, models

router = APIRouter()

@router.post("/", response_model=triagem_schemas.TriagemResponse)
def criar_triagem(triagem: triagem_schemas.TriagemCreate, db: Session = Depends(database.get_db)):
    db_triagem = models.Triagem(**triagem.dict())
    db.add(db_triagem)
    db.commit()
    db.refresh(db_triagem)
    return db_triagem

@router.get("/", response_model=list[triagem_schemas.TriagemResponse])
def listar_triagens(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Triagem).offset(skip).limit(limit).all()
