from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class RegulacaoCreate(BaseModel):
    paciente_nome: str = Field(..., description="Nome completo do paciente", example="Carlos Eduardo")
    unidade_origem: str = Field(..., description="Unidade de saúde solicitante", example="UBDS Centro")
    unidade_destino: str = Field(..., description="Unidade/Hospital de destino desejado", example="Hospital Geral")
    especialidade_solicitada: str = Field(..., description="Especialidade ou leito necessário", example="UTI Adulto")
    prioridade_clinica: str = Field(..., description="Nível de urgência/prioridade", example="Alta")
    observacoes_medicas: Optional[str] = Field(None, description="Resumo clínico e justificativa do encaminhamento", example="Paciente necessita de suporte ventilatório contínuo.")

    class Config:
        json_schema_extra = {
            "example": {
                "paciente_nome": "Carlos Eduardo",
                "unidade_origem": "UBDS Centro",
                "unidade_destino": "Hospital Geral",
                "especialidade_solicitada": "UTI Adulto",
                "prioridade_clinica": "Alta",
                "observacoes_medicas": "Paciente necessita de suporte ventilatório contínuo."
            }
        }

class RegulacaoResponse(BaseModel):
    id: int = Field(..., description="Identificador único da solicitação de regulação", example=1)
    paciente_nome: str
    unidade_origem: str
    unidade_destino: str
    especialidade_solicitada: str
    prioridade_clinica: str
    status_solicitacao: str = Field(..., description="Status atual (ex: Pendente, Aprovado, Negado, Transferido)", example="Pendente")
    observacoes_medicas: Optional[str]
    data_solicitacao: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "paciente_nome": "Carlos Eduardo",
                "unidade_origem": "UBDS Centro",
                "unidade_destino": "Hospital Geral",
                "especialidade_solicitada": "UTI Adulto",
                "prioridade_clinica": "Alta",
                "status_solicitacao": "Pendente",
                "observacoes_medicas": "Paciente necessita de suporte ventilatório contínuo.",
                "data_solicitacao": "2026-10-28T14:30:00"
            }
        }
