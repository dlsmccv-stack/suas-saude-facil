from pydantic import BaseModel
from typing import Optional
import datetime

class EmergencyProfile(BaseModel):
    cidadao_nome: str
    tipo_sanguineo: str
    alergias_conhecidas: Optional[str] = "Nenhuma registada"
    contato_emergencia_nome: str
    contato_emergencia_telefone: str
    observacoes_clinicas: Optional[str] = None

class EmergencyTriggerRequest(BaseModel):
    qr_code_token: str
    localizacao_gps: Optional[str] = "Localização não informada"

class EmergencyTriggerResponse(BaseModel):
    status: str
    mensagem_samu: str
    mensagem_familiares: str
    timestamp: datetime.datetime
