from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import database
import models

router = APIRouter(prefix="/laboratorio", tags=["Laboratório e Retornos"])


class ResultadoExameDTO(BaseModel):
    paciente_id: str
    medico_solicitante: str
    exame_nome: str
    status: str  # Ex: "REALIZADO"
    resultado_detalhes: str
    codigo_requisicao: Optional[str] = None


@router.post("/resultado")
def receber_resultado_laboratorio(
    dados: ResultadoExameDTO,
    db: Session = Depends(database.get_db),
):
    """
    Recebe a notificação do laboratório, valida o resultado, atualiza a requisição
    quando existir, agenda retorno para 14 dias e grava notificação/lembrete real
    para o cidadão na base de dados.
    """
    if dados.status != "REALIZADO":
        raise HTTPException(status_code=400, detail="Status de exame inválido.")

    cidadao = None
    paciente_id_limpo = (dados.paciente_id or "").strip()
    if paciente_id_limpo.isdigit():
        cidadao = (
            db.query(models.CidadaoPerfil)
            .filter(models.CidadaoPerfil.id == int(paciente_id_limpo))
            .first()
        )
    if not cidadao and paciente_id_limpo:
        cidadao = (
            db.query(models.CidadaoPerfil)
            .filter(models.CidadaoPerfil.nome_completo.ilike(paciente_id_limpo))
            .first()
        )

    exame_requisitado = None
    if dados.codigo_requisicao:
        exame_requisitado = (
            db.query(models.ExameRequisicaoItem)
            .filter(models.ExameRequisicaoItem.codigo_requisicao == dados.codigo_requisicao.strip())
            .first()
        )
    if not exame_requisitado and cidadao:
        exame_requisitado = (
            db.query(models.ExameRequisicaoItem)
            .filter(
                models.ExameRequisicaoItem.cidadao_id == cidadao.id,
                models.ExameRequisicaoItem.exame_nome.ilike(dados.exame_nome),
                models.ExameRequisicaoItem.status_exame == "SOLICITADO",
            )
            .order_by(models.ExameRequisicaoItem.id.desc())
            .first()
        )
    if exame_requisitado:
        exame_requisitado.status_exame = "REALIZADO"

    data_retorno = datetime.now() + timedelta(days=14)
    retorno_formatado = data_retorno.strftime("%d/%m/%Y às 10:00")

    notif_id = None
    if cidadao:
        notif = models.NotificacaoCidadaoItem(
            cidadao_id=cidadao.id,
            cidadao_nome=cidadao.nome_completo,
            tipo_evento="RETORNO_MEDICO",
            titulo=f"Retorno Agendado: {dados.exame_nome}",
            mensagem=(
                f"Resultado de '{dados.exame_nome}' disponível. "
                f"Retorno médico agendado para {retorno_formatado} com {dados.medico_solicitante}."
            ),
            data_agendada=retorno_formatado,
            alarme_sugerido="08:30",
            lida=False,
            data_criacao=datetime.utcnow(),
        )
        db.add(notif)
        db.flush()
        notif_id = notif.id

    db.commit()

    return {
        "status": "sucesso",
        "mensagem": f"Resultado do exame '{dados.exame_nome}' integrado com sucesso.",
        "medico_notificado": dados.medico_solicitante,
        "retorno_agendado_automaticamente": retorno_formatado,
        "notificacao_enviada_ao_cidadao": bool(cidadao),
        "notificacao_id": notif_id,
        "endpoint_lembretes_cidadao": f"/cidadao/{cidadao.id}/notificacoes-lembretes" if cidadao else None,
        "lembrete_ativado": "Persistido na base de dados para o App / PWA",
    }
