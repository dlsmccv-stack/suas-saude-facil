from pydantic import BaseModel
from datetime import datetime

class RegulacaoCreate(BaseModel):
    cidadao_nome: str
    tipo_item: str

class RegulacaoResponse(BaseModel):
    id: int
    cidadao_nome: str
    tipo_item: str
    status: str
    data_solicitacao: datetime

    class Config:
        from_attributes = True
