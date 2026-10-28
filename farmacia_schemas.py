from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class MedicamentoCreate(BaseModel):
    cidadao_id: Optional[int] = Field(None, description="ID do cidadão associado para integração com o App", example=1)
    cidadao_nome: str = Field(..., description="Nome completo do cidadão beneficiário", example="Maria da Silva")
    medicamento_nome: str = Field(..., description="Nome comercial ou genérico do medicamento", example="Paracetamol 500mg")
    dosagem: str = Field(..., description="Concentração ou dosagem do fármaco", example="500mg")
    posologia: str = Field(..., description="Instruções de toma ou administração prescritas pelo médico", example="1 comprimido de 8 em 8 horas")
    quantidade_disponibilizada: int = Field(..., description="Quantidade total de unidades disponibilizadas", example=30)
    fornecido_pelo_sus: bool = Field(True, description="Indica se é fornecido gratuitamente pelo SUS (True) ou se requer compra com desconto na rede particular (False)", example=True)
    uso_continuo: bool = Field(False, description="Indica se é de uso contínuo (crónico) ou temporário/emergência", example=False)
    horarios_alarme: Optional[str] = Field("08:00, 20:00", description="Horários configurados para o alarme/campainha no telemóvel", example="08:00, 20:00")

    class Config:
        json_schema_extra = {
            "example": {
                "cidadao_id": 1,
                "cidadao_nome": "Maria da Silva",
                "medicamento_nome": "Paracetamol 500mg",
                "dosagem": "500mg",
                "posologia": "1 comprimido de 8 em 8 horas",
                "quantidade_disponibilizada": 30,
                "fornecido_pelo_sus": True,
                "uso_continuo": False,
                "horarios_alarme": "08:00, 20:00"
            }
        }

class MedicamentoDispensacaoQRCode(BaseModel):
    qr_code_token: str = Field(..., description="Token único codificado no QR Code para validação na farmácia do SUS ou parceiro com desconto", example="QR-SUS-PHARM-987654XYZ")

    class Config:
        json_schema_extra = {
            "example": {
                "qr_code_token": "QR-SUS-PHARM-987654XYZ"
            }
        }

class MedicamentoResponse(BaseModel):
    id: int = Field(..., description="Identificador único do registo na base de dados", example=1)
    cidadao_id: Optional[int] = Field(None, description="ID do cidadão associado", example=1)
    cidadao_nome: str = Field(..., description="Nome completo do cidadão", example="Maria da Silva")
    medicamento_nome: str = Field(..., description="Nome do medicamento", example="Paracetamol 500mg")
    dosagem: str = Field(..., description="Dosagem", example="500mg")
    posologia: str = Field(..., description="Posologia", example="1 comprimido de 8 em 8 horas")
    quantidade_disponibilizada: int = Field(..., description="Quantidade", example=30)
    fornecido_pelo_sus: bool = Field(..., description="Indica se é do SUS ou particular com desconto", example=True)
    uso_continuo: bool = Field(..., description="Uso contínuo ou temporário", example=False)
    horarios_alarme: Optional[str] = Field(None, description="Horários do alarme no telemóvel", example="08:00, 20:00")
    qr_code_token: str = Field(..., description="Token do QR Code gerado", example="QR-SUS-PHARM-987654XYZ")
    dispensado: bool = Field(..., description="Indica se o medicamento já foi retirado/comprado", example=False)
    data_dispensacao: Optional[datetime] = Field(None, description="Data e hora em que ocorreu a dispensação ou aquisição", example="2026-10-28T14:30:00")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "cidadao_id": 1,
                "cidadao_nome": "Maria da Silva",
                "medicamento_nome": "Paracetamol 500mg",
                "dosagem": "500mg",
                "posologia": "1 comprimido de 8 em 8 horas",
                "quantidade_disponibilizada": 30,
                "fornecido_pelo_sus": True,
                "uso_continuo": False,
                "horarios_alarme": "08:00, 20:00",
                "qr_code_token": "QR-SUS-PHARM-987654XYZ",
                "dispensado": False,
                "data_dispensacao": None
            }
        }
