
"""
SUAS SAMU 192
Central de Regulação Médica de Urgências

Recursos:
- Solicitação digital SOS do App do Cidadão
- Localização GPS e atualizações de posição
- Alertas em tempo real via WebSocket
- Recuperação de alertas pendentes
- Reconhecimento pelo operador
- Regulação médica
- Gestão de ambulâncias
- Despacho e aceite de missão
- Acompanhamento da ocorrência
- Auditoria

Integração com FastAPI:
    import suas_samu
    app.include_router(suas_samu.router)

As credenciais são configuradas por variáveis de ambiente.
Não colocar tokens no JavaScript público do App do Cidadão.
"""

import os
import uuid
import json
import secrets
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional, Literal

from fastapi import (
    APIRouter, Depends, Header, HTTPException,
    WebSocket, WebSocketDisconnect
)
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column, String, Integer, Float,
    DateTime, Text, ForeignKey, select
)
from sqlalchemy.orm import Session

import database


Base = database.Base


def agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def identificador():
    return str(uuid.uuid4())


# =====================================================
# BANCO DE DADOS
# =====================================================

class SamuAmbulancia(Base):
    __tablename__ = "samu_ambulancias"

    id = Column(String(36), primary_key=True)
    prefixo = Column(String(40), unique=True, nullable=False)
    tipo = Column(String(30), nullable=False)
    base_operacional = Column(String(150))
    status = Column(String(40), default="disponivel", nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    atualizada_em = Column(DateTime, default=agora)


class SamuOcorrencia(Base):
    __tablename__ = "samu_ocorrencias"

    id = Column(String(36), primary_key=True)
    protocolo = Column(String(60), unique=True, nullable=False, index=True)

    origem = Column(String(40), nullable=False)
    cidadao_id = Column(Integer)
    descricao = Column(Text, nullable=False)

    latitude = Column(Float)
    longitude = Column(Float)
    referencia = Column(String(300))
    gps_atualizado_em = Column(DateTime)

    status = Column(String(50), default="recebida", nullable=False)
    prioridade = Column(String(30))

    medico_regulador = Column(String(120))
    decisao_medica = Column(String(50))
    justificativa_medica = Column(Text)

    ambulancia_id = Column(
        String(36), ForeignKey("samu_ambulancias.id")
    )

    hospital_destino = Column(String(200))

    recebida_em = Column(DateTime, default=agora)
    reconhecida_em = Column(DateTime)
    despachada_em = Column(DateTime)
    aceita_em = Column(DateTime)
    encerrada_em = Column(DateTime)
    atualizada_em = Column(DateTime, default=agora)


class SamuEvento(Base):
    __tablename__ = "samu_eventos"

    id = Column(String(36), primary_key=True)
    ocorrencia_id = Column(
        String(36), ForeignKey("samu_ocorrencias.id"),
        nullable=False, index=True
    )
    tipo = Column(String(80), nullable=False)
    profissional = Column(String(120), nullable=False)
    detalhes = Column(Text)
    criado_em = Column(DateTime, default=agora)


@asynccontextmanager
async def ciclo_vida(app):
    Base.metadata.create_all(
        bind=database.engine,
        tables=[
            SamuAmbulancia.__table__,
            SamuOcorrencia.__table__,
            SamuEvento.__table__,
        ]
    )
    yield


router = APIRouter(
    prefix="/samu",
    tags=["SUAS SAMU 192"],
    lifespan=ciclo_vida
)


# =====================================================
# AUTENTICAÇÃO
# =====================================================

CREDENCIAIS = {
    "operador": "SUAS_SAMU_OPERADOR_TOKEN",
    "medico": "SUAS_SAMU_MEDICO_TOKEN",
    "despachante": "SUAS_SAMU_DESPACHANTE_TOKEN",
    "equipe": "SUAS_SAMU_EQUIPE_TOKEN",
    "integracao": "SUAS_SAMU_INTEGRACAO_TOKEN",
}


def verificar_token(token):
    if not token:
        return None

    for perfil, variavel in CREDENCIAIS.items():
        esperado = os.getenv(variavel, "")
        if esperado and secrets.compare_digest(token, esperado):
            return perfil

    return None


def autenticar(
    x_samu_token: Optional[str] = Header(default=None),
    x_samu_profissional: Optional[str] = Header(default=None),
):
    perfil = verificar_token(x_samu_token)

    if not perfil:
        raise HTTPException(401, "Credenciais inválidas")

    if not x_samu_profissional:
        raise HTTPException(401, "Identificação obrigatória")

    return {
        "perfil": perfil,
        "profissional": x_samu_profissional
    }


def permitir(*perfis):
    def validar(usuario=Depends(autenticar)):
        if usuario["perfil"] not in perfis:
            raise HTTPException(403, "Acesso não autorizado")
        return usuario

    return validar


# =====================================================
# COMUNICAÇÃO EM TEMPO REAL
# =====================================================

class CentralTempoReal:

    def __init__(self):
        self.conexoes = set()

    async def conectar(self, websocket):
        await websocket.accept()
        self.conexoes.add(websocket)

    def desconectar(self, websocket):
        self.conexoes.discard(websocket)

    async def publicar(self, evento):
        desconectados = []

        for ws in list(self.conexoes):
            try:
                await ws.send_json(evento)
            except Exception:
                desconectados.append(ws)

        for ws in desconectados:
            self.desconectar(ws)


central = CentralTempoReal()


@router.websocket("/ws/central")
async def websocket_central(websocket: WebSocket):
    await websocket.accept()

    try:
        # Autenticação enviada como primeira mensagem,
        # evitando token na URL.
        credenciais = await asyncio.wait_for(
            websocket.receive_json(), timeout=10
        )

        perfil = verificar_token(
            credenciais.get("token", "")
        )

        if perfil not in ("operador", "medico", "despachante"):
            await websocket.close(code=1008)
            return

        await websocket.send_json({
            "tipo": "CONEXAO_AUTORIZADA",
            "mensagem": "Central SAMU conectada"
        })

        central.conexoes.add(websocket)

        while True:
            await websocket.receive_text()

    except (
        WebSocketDisconnect,
        asyncio.TimeoutError,
        ValueError,
        TypeError,
    ):
        pass

    finally:
        central.desconectar(websocket)


# =====================================================
# FUNÇÕES AUXILIARES
# =====================================================

def registrar(db, ocorrencia_id, tipo, usuario, detalhes=None):
    db.add(SamuEvento(
        id=identificador(),
        ocorrencia_id=ocorrencia_id,
        tipo=tipo,
        profissional=usuario["profissional"],
        detalhes=json.dumps(
            detalhes or {}, ensure_ascii=False
        )
    ))


def buscar_ocorrencia(db, id):
    ocorrencia = db.get(SamuOcorrencia, id)

    if not ocorrencia:
        raise HTTPException(404, "Ocorrência não encontrada")

    return ocorrencia


def buscar_ambulancia(db, id):
    ambulancia = db.get(SamuAmbulancia, id)

    if not ambulancia:
        raise HTTPException(404, "Ambulância não encontrada")

    return ambulancia


def resposta(o):
    return {
        "id": o.id,
        "protocolo": o.protocolo,
        "origem": o.origem,
        "cidadao_id": o.cidadao_id,
        "descricao": o.descricao,
        "latitude": o.latitude,
        "longitude": o.longitude,
        "referencia": o.referencia,
        "gps_atualizado_em": o.gps_atualizado_em,
        "status": o.status,
        "prioridade": o.prioridade,
        "medico_regulador": o.medico_regulador,
        "decisao_medica": o.decisao_medica,
        "ambulancia_id": o.ambulancia_id,
        "hospital_destino": o.hospital_destino,
        "recebida_em": o.recebida_em,
        "reconhecida_em": o.reconhecida_em,
        "despachada_em": o.despachada_em,
        "aceita_em": o.aceita_em,
        "encerrada_em": o.encerrada_em
    }


# =====================================================
# ESQUEMAS
# =====================================================

class SolicitacaoSOS(BaseModel):
    cidadao_id: Optional[int] = None
    descricao: str = Field(min_length=5, max_length=2000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    referencia: Optional[str] = Field(
        default=None, max_length=300
    )


class AtualizacaoGPS(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Regulacao(BaseModel):
    prioridade: Literal[
        "vermelha", "laranja", "amarela", "verde", "azul"
    ]
    decisao: Literal[
        "despacho_autorizado",
        "orientacao_medica",
        "encaminhamento",
        "encerramento"
    ]
    justificativa: str = Field(min_length=10)


class AmbulanciaEntrada(BaseModel):
    prefixo: str = Field(min_length=2)
    tipo: Literal["USB", "USA", "MOTOLANCIA", "OUTRA"]
    base_operacional: Optional[str] = None


class DespachoEntrada(BaseModel):
    ambulancia_id: str


class AndamentoEntrada(BaseModel):
    status: Literal[
        "no_local",
        "paciente_embarcado",
        "em_transporte",
        "chegada_hospital"
    ]


class HospitalEntrada(BaseModel):
    hospital: str = Field(min_length=3)


# =====================================================
# 1. RECEBIMENTO DE SOS
# =====================================================

@router.post("/sos", status_code=201)
async def receber_sos(
    dados: SolicitacaoSOS,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("integracao", "operador"))
):
    ocorrencia = SamuOcorrencia(
        id=identificador(),
        protocolo="SAMU-" + uuid.uuid4().hex[:16].upper(),
        origem=(
            "app_cidadao"
            if usuario["perfil"] == "integracao"
            else "central"
        ),
        cidadao_id=dados.cidadao_id,
        descricao=dados.descricao,
        latitude=dados.latitude,
        longitude=dados.longitude,
        referencia=dados.referencia,
        gps_atualizado_em=agora(),
        status="recebida"
    )

    db.add(ocorrencia)

    registrar(
        db, ocorrencia.id, "SOS_RECEBIDO",
        usuario, {"origem": ocorrencia.origem}
    )

    db.commit()
    db.refresh(ocorrencia)

    alerta = {
        "tipo": "NOVO_SOS",
        "protocolo": ocorrencia.protocolo,
        "ocorrencia_id": ocorrencia.id,
        "latitude": ocorrencia.latitude,
        "longitude": ocorrencia.longitude,
        "horario": ocorrencia.recebida_em.isoformat(),
        "alerta_visual": True,
        "alerta_sonoro": True,
        "status": "recebida"
    }

    await central.publicar(alerta)

    return {
        **resposta(ocorrencia),
        "alerta_emitido": True,
        "aviso": (
            "Ocorrência registrada na API. "
            "A entrega ao operador deve ser confirmada "
            "pela interface da central."
        )
    }


# =====================================================
# 2. FILA DE ALERTAS PENDENTES
# =====================================================

@router.get("/alertas")
def listar_alertas(
    db: Session = Depends(database.get_db),
    usuario=Depends(
        permitir("operador", "medico", "despachante")
    )
):
    registros = db.scalars(
        select(SamuOcorrencia)
        .where(SamuOcorrencia.status == "recebida")
        .order_by(SamuOcorrencia.recebida_em.asc())
        .limit(100)
    ).all()

    return {
        "total": len(registros),
        "alertas": [resposta(o) for o in registros]
    }


@router.post("/alertas/{ocorrencia_id}/reconhecer")
async def reconhecer_alerta(
    ocorrencia_id: str,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("operador"))
):
    ocorrencia = buscar_ocorrencia(db, ocorrencia_id)

    if ocorrencia.status != "recebida":
        raise HTTPException(
            409, "Alerta já processado"
        )

    ocorrencia.status = "em_regulacao"
    ocorrencia.reconhecida_em = agora()
    ocorrencia.atualizada_em = agora()

    registrar(
        db, ocorrencia_id, "ALERTA_RECONHECIDO", usuario
    )

    db.commit()

    await central.publicar({
        "tipo": "ALERTA_RECONHECIDO",
        "ocorrencia_id": ocorrencia_id,
        "status": ocorrencia.status
    })

    return resposta(ocorrencia)


# =====================================================
# 3. LOCALIZAÇÃO GPS
# =====================================================

@router.post("/ocorrencias/{ocorrencia_id}/gps")
async def atualizar_gps(
    ocorrencia_id: str,
    dados: AtualizacaoGPS,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("integracao", "operador"))
):
    ocorrencia = buscar_ocorrencia(db, ocorrencia_id)

    if ocorrencia.status == "encerrada":
        raise HTTPException(409, "Ocorrência encerrada")

    ocorrencia.latitude = dados.latitude
    ocorrencia.longitude = dados.longitude
    ocorrencia.gps_atualizado_em = agora()
    ocorrencia.atualizada_em = agora()

    registrar(
        db, ocorrencia_id, "GPS_ATUALIZADO", usuario
    )

    db.commit()

    await central.publicar({
        "tipo": "GPS_ATUALIZADO",
        "ocorrencia_id": ocorrencia_id,
        "latitude": dados.latitude,
        "longitude": dados.longitude,
        "horario": ocorrencia.gps_atualizado_em.isoformat()
    })

    return {
        "status": "localizacao_atualizada",
        "ocorrencia_id": ocorrencia_id
    }


# =====================================================
# 4. CONSULTA DE OCORRÊNCIAS
# =====================================================

@router.get("/ocorrencias")
def listar_ocorrencias(
    db: Session = Depends(database.get_db),
    usuario=Depends(
        permitir("operador", "medico", "despachante")
    )
):
    registros = db.scalars(
        select(SamuOcorrencia)
        .order_by(SamuOcorrencia.recebida_em.desc())
        .limit(100)
    ).all()

    return [resposta(o) for o in registros]


@router.get("/ocorrencias/{ocorrencia_id}")
def consultar_ocorrencia(
    ocorrencia_id: str,
    db: Session = Depends(database.get_db),
    usuario=Depends(
        permitir("operador", "medico", "despachante", "equipe")
    )
):
    return resposta(buscar_ocorrencia(db, ocorrencia_id))


# =====================================================
# 5. REGULAÇÃO MÉDICA
# =====================================================

@router.post("/ocorrencias/{ocorrencia_id}/regulacao")
async def regular(
    ocorrencia_id: str,
    dados: Regulacao,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("medico"))
):
    ocorrencia = buscar_ocorrencia(db, ocorrencia_id)

    if ocorrencia.status != "em_regulacao":
        raise HTTPException(
            409, "Ocorrência não está em regulação"
        )

    estados = {
        "despacho_autorizado": "despacho_autorizado",
        "orientacao_medica": "orientacao_registrada",
        "encaminhamento": "encaminhamento_registrado",
        "encerramento": "encerrada"
    }

    ocorrencia.prioridade = dados.prioridade
    ocorrencia.decisao_medica = dados.decisao
    ocorrencia.justificativa_medica = dados.justificativa
    ocorrencia.medico_regulador = usuario["profissional"]
    ocorrencia.status = estados[dados.decisao]
    ocorrencia.atualizada_em = agora()

    if ocorrencia.status == "encerrada":
        ocorrencia.encerrada_em = agora()

    registrar(
        db, ocorrencia_id, "REGULACAO_MEDICA",
        usuario, {
            "decisao": dados.decisao,
            "prioridade": dados.prioridade,
            "justificativa": dados.justificativa
        }
    )

    db.commit()

    await central.publicar({
        "tipo": "REGULACAO_ATUALIZADA",
        "ocorrencia_id": ocorrencia_id,
        "status": ocorrencia.status
    })

    return resposta(ocorrencia)


# =====================================================
# 6. AMBULÂNCIAS
# =====================================================

@router.post("/ambulancias", status_code=201)
def cadastrar_ambulancia(
    dados: AmbulanciaEntrada,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("despachante"))
):
    existente = db.scalar(
        select(SamuAmbulancia).where(
            SamuAmbulancia.prefixo == dados.prefixo
        )
    )

    if existente:
        raise HTTPException(409, "Ambulância já cadastrada")

    ambulancia = SamuAmbulancia(
        id=identificador(),
        prefixo=dados.prefixo,
        tipo=dados.tipo,
        base_operacional=dados.base_operacional,
        status="disponivel"
    )

    db.add(ambulancia)
    db.commit()
    db.refresh(ambulancia)

    return {
        "id": ambulancia.id,
        "prefixo": ambulancia.prefixo,
        "status": ambulancia.status
    }


@router.get("/ambulancias")
def listar_ambulancias(
    db: Session = Depends(database.get_db),
    usuario=Depends(
        permitir("medico", "despachante", "equipe")
    )
):
    registros = db.scalars(
        select(SamuAmbulancia)
        .order_by(SamuAmbulancia.prefixo)
    ).all()

    return [
        {
            "id": a.id,
            "prefixo": a.prefixo,
            "tipo": a.tipo,
            "status": a.status,
            "latitude": a.latitude,
            "longitude": a.longitude
        }
        for a in registros
    ]


# =====================================================
# 7. DESPACHO
# =====================================================

@router.post("/ocorrencias/{ocorrencia_id}/despacho")
async def despachar(
    ocorrencia_id: str,
    dados: DespachoEntrada,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("despachante"))
):
    ocorrencia = buscar_ocorrencia(db, ocorrencia_id)
    ambulancia = buscar_ambulancia(db, dados.ambulancia_id)

    if ocorrencia.status != "despacho_autorizado":
        raise HTTPException(
            409, "Despacho exige autorização médica"
        )

    if ambulancia.status != "disponivel":
        raise HTTPException(
            409, "Ambulância indisponível"
        )

    ocorrencia.ambulancia_id = ambulancia.id
    ocorrencia.status = "aguardando_aceite"
    ocorrencia.despachada_em = agora()
    ocorrencia.atualizada_em = agora()

    ambulancia.status = "missao_pendente"

    registrar(
        db, ocorrencia_id, "DESPACHO_REGISTRADO",
        usuario, {"ambulancia": ambulancia.prefixo}
    )

    db.commit()

    await central.publicar({
        "tipo": "DESPACHO_REGISTRADO",
        "ocorrencia_id": ocorrencia_id,
        "ambulancia_id": ambulancia.id
    })

    return resposta(ocorrencia)


# =====================================================
# 8. EQUIPE MÓVEL
# =====================================================

@router.get("/equipes/missoes")
def consultar_missoes(
    ambulancia_id: str,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("equipe", "despachante"))
):
    registros = db.scalars(
        select(SamuOcorrencia).where(
            SamuOcorrencia.ambulancia_id == ambulancia_id,
            SamuOcorrencia.status.in_([
                "aguardando_aceite",
                "em_deslocamento",
                "no_local",
                "paciente_embarcado",
                "em_transporte",
                "chegada_hospital"
            ])
        )
    ).all()

    return [resposta(o) for o in registros]


@router.post("/ocorrencias/{ocorrencia_id}/aceite")
async def aceitar_missao(
    ocorrencia_id: str,
    ambulancia_id: str,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("equipe"))
):
    ocorrencia = buscar_ocorrencia(db, ocorrencia_id)

    if ocorrencia.ambulancia_id != ambulancia_id:
        raise HTTPException(403, "Missão não atribuída")

    if ocorrencia.status != "aguardando_aceite":
        raise HTTPException(409, "Missão não aguarda aceite")

    ambulancia = buscar_ambulancia(db, ambulancia_id)

    ocorrencia.status = "em_deslocamento"
    ocorrencia.aceita_em = agora()
    ocorrencia.atualizada_em = agora()

    ambulancia.status = "em_atendimento"

    registrar(
        db, ocorrencia_id, "MISSAO_ACEITA", usuario
    )

    db.commit()

    await central.publicar({
        "tipo": "MISSAO_ACEITA",
        "ocorrencia_id": ocorrencia_id,
        "ambulancia_id": ambulancia_id
    })

    return resposta(ocorrencia)


@router.post("/ocorrencias/{ocorrencia_id}/andamento")
async def atualizar_andamento(
    ocorrencia_id: str,
    dados: AndamentoEntrada,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("equipe"))
):
    ocorrencia = buscar_ocorrencia(db, ocorrencia_id)

    transicoes = {
        "em_deslocamento": "no_local",
        "no_local": "paciente_embarcado",
        "paciente_embarcado": "em_transporte",
        "em_transporte": "chegada_hospital"
    }

    esperado = transicoes.get(ocorrencia.status)

    if dados.status != esperado:
        raise HTTPException(
            409, "Atualização incompatível com o andamento"
        )

    ocorrencia.status = dados.status
    ocorrencia.atualizada_em = agora()

    registrar(
        db, ocorrencia_id, "ANDAMENTO_ATUALIZADO",
        usuario, {"status": dados.status}
    )

    db.commit()

    await central.publicar({
        "tipo": "ANDAMENTO_ATUALIZADO",
        "ocorrencia_id": ocorrencia_id,
        "status": dados.status
    })

    return resposta(ocorrencia)


@router.post("/ambulancias/{ambulancia_id}/gps")
async def atualizar_gps_ambulancia(
    ambulancia_id: str,
    dados: AtualizacaoGPS,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("equipe"))
):
    ambulancia = buscar_ambulancia(db, ambulancia_id)

    ambulancia.latitude = dados.latitude
    ambulancia.longitude = dados.longitude
    ambulancia.atualizada_em = agora()

    db.commit()

    await central.publicar({
        "tipo": "GPS_AMBULANCIA",
        "ambulancia_id": ambulancia_id,
        "latitude": dados.latitude,
        "longitude": dados.longitude
    })

    return {"status": "localizacao_atualizada"}


# =====================================================
# 9. DESTINO HOSPITALAR
# =====================================================

@router.post("/ocorrencias/{ocorrencia_id}/hospital")
async def definir_hospital(
    ocorrencia_id: str,
    dados: HospitalEntrada,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("medico", "despachante"))
):
    ocorrencia = buscar_ocorrencia(db, ocorrencia_id)

    if ocorrencia.status in ("recebida", "encerrada"):
        raise HTTPException(409, "Estado incompatível")

    ocorrencia.hospital_destino = dados.hospital
    ocorrencia.atualizada_em = agora()

    registrar(
        db, ocorrencia_id, "HOSPITAL_DEFINIDO",
        usuario, {"hospital": dados.hospital}
    )

    db.commit()

    await central.publicar({
        "tipo": "HOSPITAL_DEFINIDO",
        "ocorrencia_id": ocorrencia_id,
        "hospital": dados.hospital
    })

    return resposta(ocorrencia)


# =====================================================
# 10. ENCERRAMENTO
# =====================================================

@router.post("/ocorrencias/{ocorrencia_id}/encerrar")
async def encerrar(
    ocorrencia_id: str,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("medico", "despachante"))
):
    ocorrencia = buscar_ocorrencia(db, ocorrencia_id)

    if ocorrencia.status not in (
        "chegada_hospital",
        "orientacao_registrada",
        "encaminhamento_registrado"
    ):
        raise HTTPException(
            409, "Ocorrência não pode ser encerrada"
        )

    if ocorrencia.ambulancia_id:
        ambulancia = buscar_ambulancia(
            db, ocorrencia.ambulancia_id
        )
        ambulancia.status = "disponivel"
        ambulancia.atualizada_em = agora()

    ocorrencia.status = "encerrada"
    ocorrencia.encerrada_em = agora()
    ocorrencia.atualizada_em = agora()

    registrar(
        db, ocorrencia_id, "OCORRENCIA_ENCERRADA",
        usuario
    )

    db.commit()

    await central.publicar({
        "tipo": "OCORRENCIA_ENCERRADA",
        "ocorrencia_id": ocorrencia_id
    })

    return resposta(ocorrencia)


# =====================================================
# 11. AUDITORIA
# =====================================================

@router.get("/ocorrencias/{ocorrencia_id}/auditoria")
def auditoria(
    ocorrencia_id: str,
    db: Session = Depends(database.get_db),
    usuario=Depends(permitir("medico", "despachante"))
):
    buscar_ocorrencia(db, ocorrencia_id)

    eventos = db.scalars(
        select(SamuEvento)
        .where(SamuEvento.ocorrencia_id == ocorrencia_id)
        .order_by(SamuEvento.criado_em)
    ).all()

    return [
        {
            "evento": e.tipo,
            "profissional": e.profissional,
            "detalhes": e.detalhes,
            "horario": e.criado_em
        }
        for e in eventos
    ]


@router.get("/status")
def status_samu():
    return {
        "sistema": "SUAS SAMU 192",
        "api": "disponivel",
        "recursos": [
            "sos",
            "alertas",
            "gps",
            "regulacao",
            "ambulancias",
            "despacho",
            "equipes",
            "hospital",
            "auditoria",
            "websocket"
        ]
    }
