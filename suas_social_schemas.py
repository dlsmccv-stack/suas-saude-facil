from pydantic import BaseModel
from datetime import datetime

class ApoioSocialCreate(BaseModel):
    cidadao_nome: str
    nis: str
    situacao_vulnerabilidade: str
    beneficio_ativo: str

class ApoioSocialResponse(BaseModel):
    id: int
    cidadao_nome: str
    nis: str
    situacao_vulnerabilidade: str
    beneficio_ativo: str
    data_cadastro: datetime

    class Config:
        from_attributes = True
