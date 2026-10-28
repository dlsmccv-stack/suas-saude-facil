from pydantic import BaseModel, Field
from datetime import datetime

class TriagemCreate(BaseModel):
    paciente_nome: str = Field(..., description="Nome completo do paciente", example="Ana Clara Silva")
    queixa_principal: str = Field(..., description="Descrição dos sintomas apresentados", example="Dor de cabeça intensa, tontura e visão embaçada")
    cor_prioridade: str = Field(..., description="Cor atribuída pelo Protocolo de Manchester", example="Vermelho")
    tempo_alvo_atendimento: str = Field(..., description="Tempo máximo para atendimento inicial", example="0 minutos")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "paciente_nome": "Ana Clara Silva",
                    "queixa_principal": "Dor de cabeça intensa, tontura e visão embaçada",
                    "cor_prioridade": "Vermelho",
                    "tempo_alvo_atendimento": "0 minutos"
                }
            ]
        }
    }

class TriagemResponse(BaseModel):
    id: int
    paciente_nome: str
    queixa_principal: str
    cor_prioridade: str
    tempo_alvo_atendimento: str
    data_triagem: datetime

    class Config:
        from_attributes = True
