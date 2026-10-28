from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

router = APIRouter()

class EmergencyProfileCreate(BaseModel):
    cidadao_nome: str = Field(..., description="Nome completo do cidadão", example="Maria da Silva")
    tipo_sanguineo: str = Field(..., description="Tipo sanguíneo e fator RH", example="O+")
    alergias: str = Field(..., description="Alergias conhecidas a medicamentos ou substâncias", example="Penicilina, Dipirona")
    condicoes_medicas: str = Field(..., description="Condições crónicas ou patologias importantes", example="Hipertensão, Diabetes Tipo 1")
    contacto_emergencia_nome: str = Field(..., description="Nome do contacto de emergência/familiar", example="João Silva")
    contacto_emergencia_telefone: str = Field(..., description="Telefone do contacto de emergência", example="(86) 99999-9999")

    class Config:
        json_schema_extra = {
            "example": {
                "cidadao_nome": "Maria da Silva",
                "tipo_sanguineo": "O+",
                "alergias": "Penicilina, Dipirona",
                "condicoes_medicas": "Hipertensão, Diabetes Tipo 1",
                "contacto_emergencia_nome": "João Silva",
                "contacto_emergencia_telefone": "(86) 99999-9999"
            }
        }

class EmergencyValidateToken(BaseModel):
    qr_code_token: str = Field(..., description="Token de emergência codificado no QR Code", example="QR-EMERG-ABC123XYZ")

    class Config:
        json_schema_extra = {
            "example": {
                "qr_code_token": "QR-EMERG-ABC123XYZ"
            }
        }

class EmergencyProfileResponse(BaseModel):
    id: int = Field(..., description="Identificador único do registo", example=1)
    cidadao_nome: str = Field(..., description="Nome completo", example="Maria da Silva")
    tipo_sanguineo: str = Field(..., description="Tipo sanguíneo", example="O+")
    alergias: str = Field(..., description="Alergias", example="Penicilina, Dipirona")
    condicoes_medicas: str = Field(..., description="Condições médicas", example="Hipertensão, Diabetes Tipo 1")
    contacto_emergencia_nome: str = Field(..., description="Contacto de emergência", example="João Silva")
    contacto_emergencia_telefone: str = Field(..., description="Telefone de emergência", example="(86) 99999-9999")
    qr_code_token: str = Field(..., description="Token único do QR Code de emergência", example="QR-EMERG-ABC123XYZ")
    data_registo: datetime = Field(..., description="Data de criação do perfil", example="2026-10-28T14:30:00")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "cidadao_nome": "Maria da Silva",
                "tipo_sanguineo": "O+",
                "alergias": "Penicilina, Dipirona",
                "condicoes_medicas": "Hipertensão, Diabetes Tipo 1",
                "contacto_emergencia_nome": "João Silva",
                "contacto_emergencia_telefone": "(86) 99999-9999",
                "qr_code_token": "QR-EMERG-ABC123XYZ",
                "data_registo": "2026-10-28T14:30:00"
            }
        }

@router.post(
    "/",
    response_model=EmergencyProfileResponse,
    summary="Criar Perfil de QR Code de Emergência",
    description="Regista um novo perfil médico de emergência e gera um token QR Code único para acesso rápido por equipas de socorro."
)
def criar_perfil_emergencia(
    payload: EmergencyProfileCreate,
    db: Session = Depends(database.get_db)
):
    qr_token = f"QR-EMERG-{uuid.uuid4().hex[:8].upper()}"
    
    db_emergencia = models.EmergencyItem(
        **payload.model_dump(),
        qr_code_token=qr_token,
        data_registo=datetime.utcnow()
    )
    db.add(db_emergencia)
    db.commit()
    db.refresh(db_emergencia)
    return db_emergencia

@router.get(
    "/",
    response_model=List[EmergencyProfileResponse],
    summary="Listar Perfis de Emergência",
    description="Retorna a lista de todos os perfis médicos de emergência cadastrados no sistema."
)
def listar_emergencias(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    return db.query(models.EmergencyItem).offset(skip).limit(limit).all()

@router.post(
    "/consultar/",
    response_model=EmergencyProfileResponse,
    summary="Consultar Emergência por Token QR Code",
    description="Permite que serviços de socorro consultem rapidamente os dados críticos de saúde através do token do QR Code."
)
def consultar_por_qrcode(
    payload: EmergencyValidateToken,
    db: Session = Depends(database.get_db)
):
    db_emergencia = db.query(models.EmergencyItem).filter(
        models.EmergencyItem.qr_code_token == payload.qr_code_token
    ).first()
    
    if not db_emergencia:
        raise HTTPException(status_code=404, detail="Perfil de emergência não encontrado para o token fornecido.")
    
    return db_emergencia
