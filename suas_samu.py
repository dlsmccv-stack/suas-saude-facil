
"""SUAS SAMU 192 — API piloto de regulação (SEM despacho real).

Instalação: pip install fastapi pydantic
Integração futura (somente após revisão e testes):
    from suas_samu import router as samu_router
    app.include_router(samu_router)

Variáveis de ambiente obrigatórias para usar as rotas:
    SUAS_SAMU_OPERATOR_TOKEN, SUAS_SAMU_MEDICO_TOKEN, SUAS_SAMU_DESPACHANTE_TOKEN
    SUAS_SAMU_DB_PATH (opcional; padrão: ./suas_samu_piloto.db)

ATENÇÃO: não é integração com o SAMU 192 oficial. Não utilizar com pacientes reais.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/samu", tags=["SUAS SAMU 192 — Piloto"])

DB_PATH = os.environ.get("SUAS_SAMU_DB_PATH", "./suas_samu_piloto.db")
ROLES = {
    "operador": "SUAS_SAMU_OPERATOR_TOKEN",
    "medico": "SUAS_SAMU_MEDICO_TOKEN",
    "despachante": "SUAS_SAMU_DESPACHANTE_TOKEN",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def authorize(*roles: str):
    def dependency(x_samu_token: Optional[str] = Header(default=None)) -> str:
        if not x_samu_token:
            raise HTTPException(status_code=401, detail="Token obrigatório")
        for role in roles:
            configured = os.environ.get(ROLES[role], "")
            if configured and secrets.compare_digest(x_samu_token, configured):
                return role
        raise HTTPException(status_code=403, detail="Acesso não autorizado")
    return dependency


@contextmanager
def connection():
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("""CREATE TABLE IF NOT EXISTS samu_ocorrencias (
            id TEXT PRIMARY KEY, protocolo TEXT UNIQUE NOT NULL,
            origem TEXT NOT NULL, descricao TEXT NOT NULL,
            latitude REAL, longitude REAL, referencia TEXT,
            estado TEXT NOT NULL, decisao TEXT, justificativa TEXT,
            ambulancia_id TEXT, criada_em TEXT NOT NULL, atualizada_em TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS samu_ambulancias (
            id TEXT PRIMARY KEY, identificador TEXT UNIQUE NOT NULL,
            tipo TEXT NOT NULL, estado TEXT NOT NULL, atualizada_em TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS samu_auditoria (
            id TEXT PRIMARY KEY, ocorrencia_id TEXT, acao TEXT NOT NULL,
            perfil TEXT NOT NULL, detalhes TEXT NOT NULL, criado_em TEXT NOT NULL
        )""")
        db.commit()
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def audit(db, ocorrencia_id: Optional[str], acao: str, perfil: str, detalhes: dict):
    db.execute("INSERT INTO samu_auditoria VALUES (?,?,?,?,?,?)", (
        str(uuid.uuid4()), ocorrencia_id, acao, perfil,
        json.dumps(detalhes, ensure_ascii=False), now()
    ))


def get_occurrence(db, occurrence_id: str):
    row = db.execute("SELECT * FROM samu_ocorrencias WHERE id=?", (occurrence_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada")
    return row


class OcorrenciaEntrada(BaseModel):
    origem: Literal["telefone_192", "app_cidadao_teste", "central_teste"]
    descricao: str = Field(min_length=5, max_length=1500)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    referencia: Optional[str] = Field(default=None, max_length=300)


class DecisaoMedica(BaseModel):
    decisao: Literal["orientacao", "avaliacao_presencial", "despacho_autorizado", "encerramento"]
    justificativa: str = Field(min_length=10, max_length=2000)


class AmbulanciaEntrada(BaseModel):
    identificador: str = Field(min_length=2, max_length=40)
    tipo: Literal["USB", "USA", "outro"]


class Atribuicao(BaseModel):
    ambulancia_id: str


@router.get("/status")
def status_piloto():
    return {
        "sistema": "SUAS SAMU 192 — piloto isolado",
        "modo": "SIMULACAO",
        "integrado_samu_oficial": False,
        "despacho_real_habilitado": False,
        "aviso": "Em emergências reais, ligue 192."
    }


@router.post("/ocorrencias", status_code=status.HTTP_201_CREATED)
def criar_ocorrencia(data: OcorrenciaEntrada, perfil: str = Depends(authorize("operador"))):
    occurrence_id = str(uuid.uuid4())
    protocolo = "SIM-SAMU-" + uuid.uuid4().hex[:12].upper()
    timestamp = now()
    with connection() as db:
        db.execute("""INSERT INTO samu_ocorrencias
            (id, protocolo, origem, descricao, latitude, longitude, referencia, estado, criada_em, atualizada_em)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                occurrence_id, protocolo, data.origem, data.descricao,
                data.latitude, data.longitude, data.referencia,
                "aguardando_regulacao", timestamp, timestamp
            ))
        audit(db, occurrence_id, "ocorrencia_criada", perfil, {"origem": data.origem})
    return {"id": occurrence_id, "protocolo": protocolo,
            "estado": "aguardando_regulacao", "despacho_real": False}


@router.get("/ocorrencias")
def listar_ocorrencias(perfil: str = Depends(authorize("operador", "medico", "despachante"))):
    with connection() as db:
        rows = db.execute("SELECT * FROM samu_ocorrencias ORDER BY criada_em DESC LIMIT 100").fetchall()
        return [dict(row) for row in rows]


@router.get("/ocorrencias/{ocorrencia_id}")
def consultar_ocorrencia(ocorrencia_id: str, perfil: str = Depends(authorize("operador", "medico", "despachante"))):
    with connection() as db:
        return dict(get_occurrence(db, ocorrencia_id))


@router.post("/ocorrencias/{ocorrencia_id}/decisao")
def registrar_decisao(ocorrencia_id: str, data: DecisaoMedica,
                      perfil: str = Depends(authorize("medico"))):
    with connection() as db:
        occurrence = get_occurrence(db, ocorrencia_id)
        if occurrence["estado"] in ("encerrada", "missao_atribuida"):
            raise HTTPException(status_code=409, detail="Ocorrência não admite nova decisão")
        estado = "encerrada" if data.decisao == "encerramento" else (
            "despacho_autorizado_simulado" if data.decisao == "despacho_autorizado"
            else "em_regulacao"
        )
        db.execute("""UPDATE samu_ocorrencias SET decisao=?, justificativa=?,
                      estado=?, atualizada_em=? WHERE id=?""",
                   (data.decisao, data.justificativa, estado, now(), ocorrencia_id))
        audit(db, ocorrencia_id, "decisao_medica_simulada", perfil,
              {"decisao": data.decisao, "justificativa": data.justificativa})
    return {"id": ocorrencia_id, "estado": estado, "despacho_real": False}


@router.post("/ambulancias", status_code=status.HTTP_201_CREATED)
def cadastrar_ambulancia(data: AmbulanciaEntrada,
                         perfil: str = Depends(authorize("despachante"))):
    ambulance_id = str(uuid.uuid4())
    with connection() as db:
        try:
            db.execute("INSERT INTO samu_ambulancias VALUES (?,?,?,?,?)",
                       (ambulance_id, data.identificador, data.tipo, "disponivel", now()))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Identificador já cadastrado")
        audit(db, None, "ambulancia_cadastrada_simulacao", perfil,
              {"id": ambulance_id, "identificador": data.identificador})
    return {"id": ambulance_id, "estado": "disponivel", "modo": "SIMULACAO"}


@router.get("/ambulancias")
def listar_ambulancias(perfil: str = Depends(authorize("medico", "despachante"))):
    with connection() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM samu_ambulancias ORDER BY identificador").fetchall()]


@router.post("/ocorrencias/{ocorrencia_id}/atribuir-ambulancia")
def atribuir_ambulancia_simulada(ocorrencia_id: str, data: Atribuicao,
                                perfil: str = Depends(authorize("despachante"))):
    with connection() as db:
        occurrence = get_occurrence(db, ocorrencia_id)
        if occurrence["estado"] != "despacho_autorizado_simulado":
            raise HTTPException(status_code=409, detail="Requer autorização simulada do médico")
        ambulance = db.execute("SELECT * FROM samu_ambulancias WHERE id=?",
                               (data.ambulancia_id,)).fetchone()
        if not ambulance:
            raise HTTPException(status_code=404, detail="Ambulância não encontrada")
        if ambulance["estado"] != "disponivel":
            raise HTTPException(status_code=409, detail="Ambulância indisponível")
        db.execute("UPDATE samu_ambulancias SET estado='em_missao_simulada', atualizada_em=? WHERE id=?",
                   (now(), data.ambulancia_id))
        db.execute("UPDATE samu_ocorrencias SET estado='missao_atribuida', ambulancia_id=?, atualizada_em=? WHERE id=?",
                   (data.ambulancia_id, now(), ocorrencia_id))
        audit(db, ocorrencia_id, "atribuicao_simulada", perfil,
              {"ambulancia_id": data.ambulancia_id})
    return {"estado": "missao_atribuida", "despacho_real": False,
            "mensagem": "Atribuição registrada somente no ambiente de simulação."}


@router.get("/ocorrencias/{ocorrencia_id}/auditoria")
def consultar_auditoria(ocorrencia_id: str,
                       perfil: str = Depends(authorize("medico", "despachante"))):
    with connection() as db:
        get_occurrence(db, ocorrencia_id)
        rows = db.execute("""SELECT id, ocorrencia_id, acao, perfil, detalhes, criado_em
                             FROM samu_auditoria WHERE ocorrencia_id=? ORDER BY criado_em""",
                          (ocorrencia_id,)).fetchall()
        return [dict(row) for row in rows]
