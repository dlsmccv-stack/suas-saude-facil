from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class MedicamentoCreate(BaseModel):
    cidadao_nome: str = Field(..., description="Nome completo do cidadão beneficiário", example="Maria da Silva")
    medicamento_nome: str = Field(..., description="Nome comercial ou genérico do medicamento", example="Paracetamol 500mg")
    dosagem: str = Field(..., description="Concentração ou dosagem do fármaco", example="500mg")
    posologia: str = Field(..., description="Instruções de toma ou administração", example="1 comprimido de 8 em 8 horas se dor")
    quantidade_disponibilizada: int = Field(..., description="Quantidade total de unidades disponibilizadas", example=30)

    class Config:
        json_schema_extra = {
            "example": {
                "cidadao_nome": "Maria da Silva",
                "medicamento_nome": "Paracetamol 500mg",
                "dosagem": "500mg",
                "posologia": "1 comprimido de 8 em 8 horas se dor",
                "quantidade_disponibilizada": 30
            }
        }

class MedicamentoDispensacaoQRCode(BaseModel):
    qr_code_token: str = Field(..., description="Token único codificado no QR Code para validação e retirada", example="QR-PHARM-987654XYZ")

    class Config:
        json_schema_extra = {
            "example": {
                "qr_code_token": "QR-PHARM-987654XYZ"
            }
        }

class MedicamentoResponse(BaseModel):
    id: int = Field(..., description="Identificador único do registo na base de dados", example=1)
    cidadao_nome: str = Field(..., description="Nome completo do cidadão", example="Maria da Silva")
    medicamento_nome: str = Field(..., description="Nome do medicamento", example="Paracetamol 500mg")
    dosagem: str = Field(..., description="Dosagem", example="500mg")
    posologia: str = Field(..., description="Posologia", example="1 comprimido de 8 em 8 horas se dor")
    quantidade_disponibilizada: int = Field(..., description="Quantidade", example=30)
    qr_code_token: str = Field(..., description="Token do QR Code gerado", example="QR-PHARM-987654XYZ")
    dispensado: bool = Field(..., description="Indica se o medicamento já foi retirado/dispensado", example=False)
    data_dispensacao: Optional[datetime] = Field(None, description="Data e hora em que ocorreu a dispensação", example="2026-10-28T14:30:00")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "cidadao_nome": "Maria da Silva",
                "medicamento_nome": "Paracetamol 500mg",
                "dosagem": "500mg",
                "posologia": "1 comprimido de 8 em 8 horas se dor",
                "quantidade_disponibilizada": 30,
                "qr_code_token": "QR-PHARM-987654XYZ",
                "dispensado": False,
                "data_dispensacao": None
            }
        }
