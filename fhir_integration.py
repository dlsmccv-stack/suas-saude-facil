from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import database, models
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

router = APIRouter()

class FHIRResourceCreate(BaseModel):
    resource_type: str = Field(..., description="Tipo do recurso FHIR R4 (ex: Patient, Observation, Encounter)", example="Patient")
    resource_data: Dict[str, Any] = Field(..., description="Payload completo do recurso em formato FHIR R4 JSON", example={
        "resourceType": "Patient",
        "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}]
    })

    class Config:
        json_schema_extra = {
            "example": {
                "resource_type": "Patient",
                "resource_data": {
                    "resourceType": "Patient",
                    "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}]
                }
            }
        }

class FHIRResourceResponse(BaseModel):
    id: int = Field(..., description="Identificador interno do registo FHIR na base de dados", example=1)
    resource_type: str = Field(..., description="Tipo do recurso FHIR", example="Patient")
    resource_data: Dict[str, Any] = Field(..., description="Dados do recurso FHIR R4", example={
        "resourceType": "Patient",
        "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}]
    })

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "resource_type": "Patient",
                "resource_data": {
                    "resourceType": "Patient",
                    "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}]
                }
            }
        }

@router.post(
    "/",
    response_model=FHIRResourceResponse,
    summary="Submeter Recurso FHIR R4",
    description="Recebe e armazena um recurso clínico estruturado de acordo com o padrão internacional FHIR R4 para interoperabilidade em saúde."
)
def criar_recurso_fhir(
    payload: FHIRResourceCreate,
    db: Session = Depends(database.get_db)
):
    db_fhir = models.FHIRItem(
        resource_type=payload.resource_type,
        resource_data=payload.resource_data
    )
    db.add(db_fhir)
    db.commit()
    db.refresh(db_fhir)
    return db_fhir

@router.get(
    "/",
    response_model=List[FHIRResourceResponse],
    summary="Listar Recursos FHIR",
    description="Retorna a lista de todos os recursos clínicos interoperáveis armazenados no formato FHIR R4."
)
def listar_recursos_fhir(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    return db.query(models.FHIRItem).offset(skip).limit(limit).all()
