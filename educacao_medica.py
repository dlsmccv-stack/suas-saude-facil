from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models, educacao_medica_schemas
from typing import List
from datetime import datetime

router = APIRouter()

@router.post(
    "/",
    response_model=educacao_medica_schemas.EducacaoMedicaResponse,
    summary="Cadastrar Curso de Educação Médica",
    description="Regista um novo módulo de capacitação ou curso voltado para profissionais de saúde em parceria com a indústria."
)
def criar_curso(
    curso: educacao_medica_schemas.EducacaoMedicaCreate,
    db: Session = Depends(database.get_db)
):
    db_curso = models.EducacaoMedicaItem(
        **curso.model_dump(),
        data_publicacao=datetime.utcnow()
    )
    db.add(db_curso)
    db.commit()
    db.refresh(db_curso)
    return db_curso

@router.get(
    "/",
    response_model=List[educacao_medica_schemas.EducacaoMedicaResponse],
    summary="Listar Cursos de Educação Médica",
    description="Retorna a lista de todos os cursos, materiais de estudo e créditos CME disponíveis no ecossistema."
)
def listar_cursos(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    return db.query(models.EducacaoMedicaItem).offset(skip).limit(limit).all()
