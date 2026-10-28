from pydantic import BaseModel, Field
from datetime import datetime

class ApoioSocialCreate(BaseModel):
    cidadao_nome: str = Field(..., description="Nome completo do cidadão assistido", example="Marcos Pereira")
    nis: str = Field(..., description="Número de Identificação Social (NIS)", example="12345678900")
    situacao_vulnerabilidade: str = Field(..., description="Resumo da situação sócio-económica", example="Baixa renda")
    beneficio_ativo: str = Field(..., description="Status do benefício social", example="Sim")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "cidadao_nome": "Marcos Pereira",
                    "nis": "12345678900",
                    "situacao_vulnerabilidade": "Baixa renda",
                    "beneficio_ativo": "Sim"
                }
            ]
        }
    }

class ApoioSocialResponse(BaseModel):
    id: int
    cidadao_nome: str
    nis: str
    situacao_vulnerabilidade: str
    beneficio_ativo: str
    data_cadastro: datetime

    class Config:
        from_attributes = True
