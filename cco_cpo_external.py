from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/cco-cpo/externo",
    tags=["CCO / CPO - Setor Externo Isolado"],
)

API_KEY_NAME = "X-External-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


class OcorrenciaExternaSchema(BaseModel):
  setor_origem: str = Field(
      ..., example="Unidade Operacional Alfa", description="Nome do setor externo"
  )
  tipo_ocorrencia: str = Field(
      ...,
      example="Alerta de Risco Operacional",
      description="Categoria do evento",
  )
  descricao: str = Field(
      ...,
      example="Necessário reforço de triagem na zona norte.",
      description="Detalhes do chamado",
  )
  nivel_urgencia: str = Field(
      ..., example="Alto", description="Baixo, Moderado ou Alto"
  )


@router.post(
    "/reportar", summary="Registo de ocorrência por setor externo isolado"
)
def reportar_ocorrencia_externa(
    payload: OcorrenciaExternaSchema, token: str = Security(api_key_header)
):
  try:
    return {
        "status": "sucesso",
        "mensagem": (
            "Ocorrência registada com sucesso na zona isolada CCO/CPO."
        ),
        "dados_recebidos": payload.dict(),
        "protocolo_gerado": "CCO-CPO-2026-EXT-091",
    }
  except Exception as e:
    raise HTTPException(
        status_code=500,
        detail=f"Erro ao processar o canal externo do CCO/CPO: {str(e)}",
    )


@router.get(
    "/status", summary="Consulta de status operacional do setor externo"
)
def status_cco_cpo_externo():
  return {
      "canal": "CCO / CPO Setor Externo Isolado",
      "estado": "Operacional",
      "isolamento_rede": "Ativo",
  }
