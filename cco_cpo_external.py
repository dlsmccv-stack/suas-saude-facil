from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/cco-cpo/externo",
    tags=["CCO / CPO - Setor Externo Isolado"],
)

API_KEY_NAME = "X-External-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Armazenamento em memória para simular o feed em tempo real do Dashboard
db_ocorrencias = [
    {
        "protocolo": "CCO-CPO-2026-EXT-090",
        "data_hora": "2026-10-29T12:00:00",
        "setor_origem": "Posto Beira Rio",
        "tipo_ocorrencia": "Infraestrutura",
        "descricao": "Nobreak do terminal de triagem apresentou oscilação.",
        "nivel_urgencia": "Moderado",
        "status": "Em Atendimento",
    }
]


class OcorrenciaExternaSchema(BaseModel):
  setor_origem: str = Field(
      ...,
      example="Unidade Operacional Alfa",
      description="Nome do setor externo",
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
    # Gera protocolo dinâmico e regista na base do dashboard
    protocolo = f"CCO-CPO-2026-EXT-{len(db_ocorrencias) + 91:03d}"
    nova_ocorrencia = {
        "protocolo": protocolo,
        "data_hora": datetime.now().isoformat(),
        **payload.dict(),
        "status": "Pendente",
    }
    db_ocorrencias.append(nova_ocorrencia)

    return {
        "status": "sucesso",
        "mensagem": (
            "Ocorrência registada com sucesso na zona isolada CCO/CPO."
        ),
        "dados_recebidos": payload.dict(),
        "protocolo_gerado": protocolo,
    }
  except Exception as e:
    raise HTTPException(
        status_code=500,
        detail=f"Erro ao processar o canal externo do CCO/CPO: {str(e)}",
    )


@router.get(
    "/ocorrencias",
    summary="Listagem de ocorrências registadas para o Dashboard CCO/CPO",
)
def listar_ocorrencias_externas(
    status_filtro: Optional[str] = None, token: str = Security(api_key_header)
):
  try:
    if status_filtro:
      filtradas = [
          o
          for o in db_ocorrencias
          if o["status"].lower() == status_filtro.lower()
      ]
      return {
          "total": len(filtradas),
          "filtro_aplicado": status_filtro,
          "ocorrencias": filtradas,
      }
    return {
        "total": len(db_ocorrencias),
        "ocorrencias": db_ocorrencias,
    }
  except Exception as e:
    raise HTTPException(
        status_code=500,
        detail=(
            "Erro ao listar ocorrências do setor externo do CCO/CPO:"
            f" {str(e)}"
        ),
    )


@router.get(
    "/status", summary="Consulta de status operacional do setor externo"
)
def status_cco_cpo_externo():
  return {
      "canal": "CCO / CPO Setor Externo Isolado",
      "estado": "Operacional",
      "isolamento_rede": "Ativo",
      "total_ocorrencias_registadas": len(db_ocorrencias),
  }
