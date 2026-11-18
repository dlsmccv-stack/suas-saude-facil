
"""
SUAS SAMU 192
Integração com QR Code de emergência e ficha clínica.

Quem lê o QR Code:
- Solicita socorro.
- Não recebe dados pessoais ou clínicos.

Central SAMU:
- Recebe a ocorrência.
- Consulta a ficha clínica mediante autenticação.

Depende dos módulos existentes:
database.py, models.py e suas_samu.py
"""

import uuid
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
    tags=["SUAS SAMU - Integrações"]
)


# =====================================================
# DADOS DE ENTRADA
# =====================================================

class ChamadoQR(BaseModel):
    qr_code_token: str = Field(
        min_length=12,
        max_length=150
    )
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    referencia: Optional[str] = Field(
        default=None,
        max_length=300
    )
    chave_requisicao: str = Field(
        min_length=16,
        max_length=100
    )


class ChamadoApp(BaseModel):
    descricao: str = Field(
        min_length=5,
        max_length=2000
    )
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    referencia: Optional[str] = Field(
        default=None,
        max_length=300
    )
    chave_requisicao: str = Field(
        min_length=16,
        max_length=100
    )


# =====================================================
# AUTENTICAÇÃO DO CIDADÃO
# =====================================================

def token_cidadao(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(database.get_db)
):
    """
    A autenticação individual do cidadão precisa ser
    conectada ao sistema de login existente.

    Não aceita um ID informado pelo navegador como
    prova de identidade.
    """
    raise HTTPException(
        status_code=503,
        detail="Autenticação do cidadão ainda não integrada"
    )


# =====================================================
# CONSULTA INTERNA DO QR CODE
# =====================================================

def obter_perfil_qr(db, token):
    perfil = db.scalar(
        select(models.EmergencyItem).where(
            models.EmergencyItem.qr_code_token == token
        )
    )

    if not perfil:
        raise HTTPException(
            status_code=404,
            detail="QR Code inválido ou não cadastrado"
        )

    return perfil


# =====================================================
# REGISTRO DA OCORRÊNCIA
# =====================================================

def salvar_chamado(
    db,
    origem,
    descricao,
    lat,
    lon,
    referencia,
    cidadao_id,
    chave,
    ator
):
    # Verificação de repetição da solicitação.
    # Para concorrência entre servidores, também é
    # necessária uma restrição UNIQUE no banco.

    evento = db.scalar(
        select(suas_samu.SamuEvento).where(
            suas_samu.SamuEvento.tipo == "CHAVE_REQUISICAO",
            suas_samu.SamuEvento.detalhes == chave
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
        protocolo=(
            "SAMU-" + uuid.uuid4().hex[:16].upper()
        ),
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
            detalhes=chave
        )
    )

    db.add(
        suas_samu.SamuEvento(
            id=str(uuid.uuid4()),
            ocorrencia_id=ocorrencia.id,
            tipo="SOS_RECEBIDO",
            profissional=ator,
            detalhes=origem
        )
    )

    db.commit()
    db.refresh(ocorrencia)

    return ocorrencia, True


# =====================================================
# ACIONAMENTO PELO QR CODE
# =====================================================

@router.post("/qr/acionar", status_code=201)
async def acionar_por_qr(
    dados: ChamadoQR,
    db: Session = Depends(database.get_db)
):
    """
    A pessoa que lê o QR Code apenas solicita socorro.

    A resposta não contém:
    - Nome do cidadão
    - CPF
    - Tipo sanguíneo
    - Alergias
    - Medicamentos
    - Histórico médico
    """

    perfil = obter_perfil_qr(
        db,
        dados.qr_code_token
    )

    ocorrencia, novo = salvar_chamado(
        db=db,
        origem="qr_code",
        descricao=(
            "Solicitação de socorro por leitura "
            "de QR Code"
        ),
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
            "Solicitação registrada no SUAS. "
            "Em emergência, ligue 192. "
            "Não há confirmação de recebimento "
            "pela central oficial."
        )
    }


# =====================================================
# FICHA CLÍNICA — SOMENTE CENTRAL AUTORIZADA
# =====================================================

@router.get(
    "/ocorrencias/{ocorrencia_id}/ficha-clinica"
)
def ficha_clinica_samu(
    ocorrencia_id: str,
    db: Session = Depends(database.get_db),
    usuario=Depends(
        suas_samu.permitir("medico", "operador")
    )
):
    """
    Consulta restrita à Central SAMU autenticada.

    Os dados clínicos não são retornados
    ao leitor público do QR Code.
    """

    ocorrencia = suas_samu.buscar_ocorrencia(
        db,
        ocorrencia_id
    )

    if not ocorrencia.cidadao_id:
        raise HTTPException(
            status_code=404,
            detail="Ocorrência sem cidadão vinculado"
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
            status_code=404,
            detail="Ficha clínica não cadastrada"
        )

    medicamentos = db.scalars(
        select(models.MedicamentoCidadao).where(
            models.MedicamentoCidadao.cidadao_id
            == ocorrencia.cidadao_id
        )
    ).all()

    suas_samu.registrar(
        db,
        ocorrencia.id,
        "FICHA_CLINICA_CONSULTADA",
        usuario
    )

    db.commit()

    return {
        "ocorrencia_id": ocorrencia.id,
        "nome": (
            getattr(cidadao, "nome_completo", None)
            or getattr(perfil, "cidadao_nome", None)
        ),
        "tipo_sanguineo": (
            getattr(perfil, "tipo_sanguineo", None)
            or getattr(cidadao, "tipo_sanguineo", None)
        ),
        "alergias": (
            getattr(perfil, "alergias", None)
            or getattr(cidadao, "alergias", None)
        ),
        "condicoes_medicas": (
            getattr(perfil, "condicoes_medicas", None)
            or getattr(cidadao, "condicoes_cronicas", None)
        ),
        "contato_emergencia": getattr(
            perfil,
            "contacto_emergencia_nome",
            None
        ),
        "telefone_emergencia": getattr(
            perfil,
            "contacto_emergencia_telefone",
            None
        ),
        "medicamentos": [
            getattr(m, "nome_medicamento", None)
            for m in medicamentos
        ]
    }
