
"""
SUAS — Sistema Unificado Aprimorado à Saúde
Integração QR Code e Central SAMU 192.
"""

import uuid
import json
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import database
import models
import suas_samu


router = APIRouter(
    prefix="/samu",
    tags=["SUAS SAMU — Integrações"]
)


class ChamadoQR(BaseModel):
    qr_code_token: str = Field(min_length=12, max_length=150)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    referencia: Optional[str] = Field(default=None, max_length=300)
    chave_requisicao: str = Field(min_length=16, max_length=100)


class ChamadoApp(BaseModel):
    descricao: str = Field(min_length=5, max_length=2000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    referencia: Optional[str] = Field(default=None, max_length=300)
    chave_requisicao: str = Field(min_length=16, max_length=100)


def token_cidadao(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(database.get_db)
):
    raise HTTPException(
        status_code=503,
        detail="Autenticação individual do cidadão ainda não integrada."
    )


def obter_perfil_qr(db, token):
    perfil = db.scalar(
        select(models.EmergencyItem).where(
            models.EmergencyItem.qr_code_token == token
        )
    )
    if not perfil:
        raise HTTPException(404, "QR Code não cadastrado.")
    if not perfil.cidadao_id:
        raise HTTPException(
            409,
            "QR Code sem vínculo com cadastro clínico."
        )
    return perfil


def salvar_chamado(
    db, origem, descricao, lat, lon,
    referencia, cidadao_id, chave, ator
):
    # A chave é armazenada em hash, não em texto aberto.
    chave_hash = hashlib.sha256(
        chave.encode("utf-8")
    ).hexdigest()

    evento = db.scalar(
        select(suas_samu.SamuEvento).where(
            suas_samu.SamuEvento.tipo == "CHAVE_REQUISICAO",
            suas_samu.SamuEvento.detalhes == chave_hash
        )
    )

    if evento:
        existente = db.get(
            suas_samu.SamuOcorrencia,
            evento.ocorrencia_id
        )
        if existente:
            return existente, False

    ocorrencia = suas_samu.SamuOcorrencia(
        id=str(uuid.uuid4()),
        protocolo="SAMU-" + uuid.uuid4().hex[:16].upper(),
        origem=origem,
        cidadao_id=cidadao_id,
        descricao=descricao,
        latitude=lat,
        longitude=lon,
        referencia=referencia,
        gps_atualizado_em=suas_samu.agora(),
        status="recebida"
    )

    db.add(ocorrencia)
    db.flush()

    db.add(
        suas_samu.SamuEvento(
            id=str(uuid.uuid4()),
            ocorrencia_id=ocorrencia.id,
            tipo="CHAVE_REQUISICAO",
            profissional=ator,
            detalhes=chave_hash
        )
    )

    suas_samu.registrar(
        db,
        ocorrencia.id,
        "SOS_RECEBIDO",
        {"profissional": ator},
        {"origem": origem}
    )

    db.commit()
    db.refresh(ocorrencia)
    return ocorrencia, True


@router.post("/qr/acionar", status_code=201)
async def acionar_por_qr(
    dados: ChamadoQR,
    db: Session = Depends(database.get_db)
):
    """
    O cidadão solicita socorro sem receber
    informações pessoais ou clínicas.
    """

    perfil = obter_perfil_qr(db, dados.qr_code_token)

    ocorrencia, novo = salvar_chamado(
        db=db,
        origem="qr_code",
        descricao="Solicitação de socorro por QR Code",
        lat=dados.latitude,
        lon=dados.longitude,
        referencia=dados.referencia,
        cidadao_id=perfil.cidadao_id,
        chave=dados.chave_requisicao,
        ator="LEITOR_QR"
    )

    if novo:
        await suas_samu.central.publicar({
            "tipo": "NOVO_SOS",
            "ocorrencia_id": ocorrencia.id,
            "protocolo": ocorrencia.protocolo,
            "origem": "qr_code",
            "latitude": ocorrencia.latitude,
            "longitude": ocorrencia.longitude,
            "alerta_visual": True,
            "alerta_sonoro": True
        })

    return {
        "protocolo": ocorrencia.protocolo,
        "status": "solicitacao_registrada_na_plataforma",
        "mensagem": (
            "Pedido registrado no SUAS. "
            "Não há confirmação de despacho ou de "
            "recebimento pelo SAMU oficial. "
            "Em emergência, ligue 192."
        )
    }


@router.get("/ocorrencias/{ocorrencia_id}/ficha-clinica")
def ficha_clinica_samu(
    ocorrencia_id: str,
    db: Session = Depends(database.get_db),
    usuario=Depends(
        suas_samu.permitir(
            "medico", "operador", "equipe"
        )
    )
):
    """
    Ficha restrita a profissionais autenticados.
    Para produção, também será necessário verificar
    vínculo do profissional com a ocorrência.
    """

    ocorrencia = suas_samu.buscar_ocorrencia(
        db, ocorrencia_id
    )

    if not ocorrencia.cidadao_id:
        raise HTTPException(
            404, "Ocorrência sem paciente vinculado."
        )

    cidadao = db.get(
        models.CidadaoPerfil,
        ocorrencia.cidadao_id
    )

    perfil = db.scalar(
        select(models.EmergencyItem)
        .where(
            models.EmergencyItem.cidadao_id
            == ocorrencia.cidadao_id
        )
        .order_by(
            models.EmergencyItem.data_registo.desc()
        )
    )

    if not cidadao and not perfil:
        raise HTTPException(
            404, "Ficha clínica não cadastrada."
        )

    medicamentos = db.scalars(
        select(models.MedicamentoCidadao).where(
            models.MedicamentoCidadao.cidadao_id
            == ocorrencia.cidadao_id
        )
    ).all()

    automedicacoes = db.scalars(
        select(models.AutomedicacaoLog).where(
            models.AutomedicacaoLog.cidadao_id
            == ocorrencia.cidadao_id
        )
    ).all()

    def primeiro(*valores):
        for valor in valores:
            if valor is not None and valor != "":
                return valor
        return None

    resultado = {
        "ocorrencia_id": ocorrencia.id,
        "protocolo": ocorrencia.protocolo,
        "nome": primeiro(
            getattr(cidadao, "nome_completo", None),
            getattr(perfil, "cidadao_nome", None)
        ),
        "idade": None,
        "idade_observacao": (
            "Data de nascimento não cadastrada "
            "no modelo atual."
        ),
        "tipo_sanguineo": primeiro(
            getattr(perfil, "tipo_sanguineo", None),
            getattr(cidadao, "tipo_sanguineo", None)
        ),
        "alergias": primeiro(
            getattr(perfil, "alergias", None),
            getattr(cidadao, "alergias", None)
        ),
        "condicoes_medicas": primeiro(
            getattr(perfil, "condicoes_medicas", None),
            getattr(cidadao, "condicoes_cronicas", None)
        ),
        "medicamentos": [
            m.nome_medicamento
            for m in medicamentos
            if m.nome_medicamento
        ],
        "automedicacoes_registradas": [
            m.nome_medicamento
            for m in automedicacoes
            if m.nome_medicamento
        ],
        "contato_emergencia": getattr(
            perfil, "contacto_emergencia_nome", None
        ),
        "telefone_emergencia": getattr(
            perfil, "contacto_emergencia_telefone", None
        ),
        "localizacao": {
            "latitude": ocorrencia.latitude,
            "longitude": ocorrencia.longitude,
            "referencia": ocorrencia.referencia
        },
        "aviso": (
            "Informações provenientes do cadastro. "
            "Medicamentos registrados não confirmam "
            "o uso atual pelo paciente."
        )
    }

    suas_samu.registrar(
        db,
        ocorrencia.id,
        "FICHA_CLINICA_CONSULTADA",
        usuario,
        {"perfil": usuario["perfil"]}
    )
    db.commit()

    return resultado


@router.get("/ocorrencias/{ocorrencia_id}/notificacao-familiar")
def consultar_notificacao_familiar(
    ocorrencia_id: str,
    db: Session = Depends(database.get_db),
    usuario=Depends(
        suas_samu.permitir("operador", "medico")
    )
):
    """
    Não informa envio ou entrega sem registro real
    de um provedor de notificações.
    """

    ocorrencia = suas_samu.buscar_ocorrencia(
        db, ocorrencia_id
    )

    eventos = db.scalars(
        select(suas_samu.SamuEvento)
        .where(
            suas_samu.SamuEvento.ocorrencia_id
            == ocorrencia.id,
            suas_samu.SamuEvento.tipo.in_([
                "FAMILIAR_ENVIO_SOLICITADO",
                "FAMILIAR_ENVIADO",
                "FAMILIAR_ENTREGUE",
                "FAMILIAR_CONFIRMADO",
                "FAMILIAR_FALHA"
            ])
        )
        .order_by(suas_samu.SamuEvento.criado_em.desc())
    ).all()

    if not eventos:
        return {
            "ocorrencia_id": ocorrencia.id,
            "status": "nao_integrado",
            "mensagem": (
                "Nenhuma notificação familiar "
                "foi registrada por um serviço de envio."
            )
        }

    ultimo = eventos[0]

    return {
        "ocorrencia_id": ocorrencia.id,
        "status": ultimo.tipo,
        "registrado_em": ultimo.criado_em,
        "mensagem": (
            "Estado registrado no histórico da ocorrência. "
            "A confirmação deve vir de um provedor confiável."
        )
    }
