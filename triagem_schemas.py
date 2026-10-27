from pydantic import BaseModel
from datetime import datetime

class TriagemCreate(BaseModel):
    paciente_nome: str
    queixa_principal: str
    cor_prioridade: str
    tempo_alvo_atendimento: str

class TriagemResponse(BaseModel):
    id: int
    paciente_nome: str
    queixa_principal: str
    cor_prioridade: str
    tempo_alvo_atendimento: str
    data_triagem: datetime

    class Config:
        from_attributes = True
