from pydantic import BaseModel
from datetime import datetime

class MedicamentoCreate(BaseModel):
    cidadao_nome: str
    medicamento_nome: str
    dosagem: str
    posologia: str
    quantidade_disponibilizada: int

class MedicamentoResponse(BaseModel):
    id: int
    cidadao_nome: str
    medicamento_nome: str
    dosagem: str
    posologia: str
    quantidade_disponibilizada: int
    dispensado: bool
    data_dispensacao: datetime

    class Config:
        from_attributes = True
