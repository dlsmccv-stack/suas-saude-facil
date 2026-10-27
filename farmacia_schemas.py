from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class MedicamentoCreate(BaseModel):
    cidadao_nome: str
    medicamento_nome: str
    dosagem: str
    posologia: str
    quantidade_disponibilizada: int

class MedicamentoDispensacaoQRCode(BaseModel):
    qr_code_token: str

class MedicamentoResponse(BaseModel):
    id: int
    cidadao_nome: str
    medicamento_nome: str
    dosagem: str
    posologia: str
    quantidade_disponibilizada: int
    qr_code_token: str
    dispensado: bool
    data_dispensacao: Optional[datetime] = None

    class Config:
        from_attributes = True
