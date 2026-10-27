from pydantic import BaseModel
from typing import Optional

class EmergencyProfile(BaseModel):
    cidadao_nome: str
    tipo_sanguineo: str
    alergias_conhecidas: Optional[str] = "Nenhuma registada"
    contato_emergencia_nome: str
    contato_emergencia_telefone: str
    observacoes_clinicas: Optional[str] = None
