from pydantic import BaseModel
from datetime import datetime

class EducacaoMedicaCreate(BaseModel):
    titulo_curso: str
    especialidade: str
    parceiro_industria: str
    descricao_conteudo: str
    link_material_estudo: str
    pontos_credito_cme: int

class EducacaoMedicaResponse(BaseModel):
    id: int
    titulo_curso: str
    especialidade: str
    parceiro_industria: str
    descricao_conteudo: str
    link_material_estudo: str
    pontos_credito_cme: int
    data_publicacao: datetime

    class Config:
        from_attributes = True
