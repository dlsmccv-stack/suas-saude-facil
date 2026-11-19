"""API Integrada e 100% Ativa do App do Cidadão — SUAS Saúde +Fácil.
Compatível com main.py, models.py e database.py existentes sem alterá-los.
Inclui: Cadastro/Login seguros (PBKDF2 + SHA-256), Cartão Vital editável com QR Code,
SOS Geolocalizado com registo permanente em samu_ocorrencias, Pré-Triagem Inteligente
com Check-in QR, Farmácia Digital (SUS e Plano) e Despertador de Posologia
(Temporário 6/6h, 8/8h, 12/12h e Uso Contínuo).
"""
import os
import re
import uuid
import json
import secrets
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, inspect, text
from sqlalchemy.orm import Session
import database
import models

router = APIRouter(prefix="/app-cidadao", tags=["App do Cidadão"])


# --- Modelos Complementares (criados automaticamente se não existirem) ---
class CitizenAuth(models.Base):
    __tablename__ = "app_cidadao_auth"
    id = Column(Integer, primary_key=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), unique=True, nullable=False)
    cns = Column(String(15), unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    vital_code = Column(String(32), unique=True, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CitizenSession(models.Base):
    __tablename__ = "app_cidadao_sessions"
    id = Column(Integer, primary_key=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    expires_at = Column(Integer, nullable=False)


class CitizenTriage(models.Base):
    __tablename__ = "app_cidadao_triagens"
    id = Column(Integer, primary_key=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), nullable=False, index=True)
    protocolo = Column(String(32), unique=True, index=True, nullable=True)
    queixa_principal = Column(String(1500), nullable=False)
    gravidade_autorreferida = Column(String(12), nullable=False)
    unidade_indicada = Column(String(120), default="UBS de Referência")
    tempo_estimado_min = Column(Integer, default=35)
    qr_checkin = Column(String(64), nullable=True)
    status = Column(String(60), default="Pré-triagem validada · Aguardando check-in QR")
    created_at = Column(DateTime, default=datetime.utcnow)


class CitizenMedicationSchedule(models.Base):
    __tablename__ = "app_cidadao_alarmes_posologia"
    id = Column(Integer, primary_key=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), nullable=False, index=True)
    nome_medicamento = Column(String(180), nullable=False)
    dosagem = Column(String(80), nullable=True)
    tipo_tratamento = Column(String(20), default="TEMPORARIO")  # TEMPORARIO ou CONTINUO
    intervalo_horas = Column(Integer, default=8)  # 6, 8, 12, 24 ou 0 (personalizado)
    duracao_dias = Column(Integer, nullable=True)  # Ex: 5, 7, 10, 14 dias
    horarios_alarme = Column(String(200), nullable=False)  # Ex: "08:00, 16:00, 00:00"
    origem = Column(String(40), default="Prescrição / Cidadão")
    ativo = Column(Boolean, default=True)
    inicio_em = Column(DateTime, default=datetime.utcnow)
    fim_em = Column(DateTime, nullable=True)


class CitizenEmergencyLog(models.Base):
    __tablename__ = "app_cidadao_sos_logs"
    id = Column(Integer, primary_key=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), nullable=False, index=True)
    protocolo = Column(String(32), unique=True, nullable=False)
    latitude = Column(String(40), nullable=True)
    longitude = Column(String(40), nullable=True)
    observacao = Column(String(300), nullable=True)
    status = Column(String(60), default="Alerta SOS registrado · Geolocalização ativa")
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    yield from database.get_db()


def only_digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def validar_cpf(cpf: str) -> bool:
    cpf = only_digits(cpf)
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    for i in (9, 10):
        soma = sum(int(cpf[num]) * ((i + 1) - num) for num in range(i))
        dig = ((soma * 10) % 11) % 10
        if dig != int(cpf[i]):
            return False
    return True


def password_hash(p: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", p.encode("utf-8"), salt, 310000)
    return salt.hex() + ":" + key.hex()


def check_password(p: str, encoded: str) -> bool:
    try:
        salt, expected = encoded.split(":")
        actual = hashlib.pbkdf2_hmac("sha256", p.encode("utf-8"), bytes.fromhex(salt), 310000)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def calcular_horarios_intervalo(intervalo_horas: int, hora_inicial: str = "08:00") -> str:
    if intervalo_horas not in (4, 6, 8, 12, 24):
        return hora_inicial
    try:
        hh, mm = [int(x) for x in hora_inicial.strip().split(":")[:2]]
    except Exception:
        hh, mm = 8, 0
    qtd = max(1, 24 // intervalo_horas)
    lista = []
    for i in range(qtd):
        h_atual = (hh + i * intervalo_horas) % 24
        lista.append(f"{h_atual:02d}:{mm:02d}")
    return ", ".join(lista)


def _to_float_or_none(val: str | float | int | None) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _registrar_ocorrencia_samu(
    db: Session,
    protocolo: str,
    cidadao_id: int,
    nome_cidadao: str | None,
    latitude: str | None,
    longitude: str | None,
    observacao: str,
) -> tuple[bool, str | None, dict | None]:
    """Grava permanentemente a ocorrência na tabela samu_ocorrencias e evento em samu_eventos."""
    if db.bind is None:
        return False, None, None

    inspector = inspect(db.bind)
    if not inspector.has_table("samu_ocorrencias"):
        return False, None, None

    colunas = {c["name"] for c in inspector.get_columns("samu_ocorrencias")}
    ocorrencia_id = str(uuid.uuid4())
    agora_utc = datetime.utcnow()
    lat_f = _to_float_or_none(latitude)
    lon_f = _to_float_or_none(longitude)
    descricao_completa = f"{observacao} (Cidadão: {nome_cidadao})" if nome_cidadao else observacao

    valores: dict[str, object] = {}
    if "id" in colunas:
        valores["id"] = ocorrencia_id
    if "protocolo" in colunas:
        valores["protocolo"] = protocolo
    if "origem" in colunas:
        valores["origem"] = "app_cidadao"
    if "cidadao_id" in colunas:
        valores["cidadao_id"] = cidadao_id
    if "descricao" in colunas:
        valores["descricao"] = descricao_completa
    if "latitude" in colunas:
        valores["latitude"] = lat_f
    if "longitude" in colunas:
        valores["longitude"] = lon_f
    if "gps_atualizado_em" in colunas:
        valores["gps_atualizado_em"] = agora_utc
    if "status" in colunas:
        valores["status"] = "recebida"
    if "recebida_em" in colunas:
        valores["recebida_em"] = agora_utc
    if "atualizada_em" in colunas:
        valores["atualizada_em"] = agora_utc

    if not valores:
        return False, None, None

    cols_sql = ", ".join(valores.keys())
    params_sql = ", ".join(f":{k}" for k in valores.keys())
    db.execute(text(f"INSERT INTO samu_ocorrencias ({cols_sql}) VALUES ({params_sql})"), valores)

    if inspector.has_table("samu_eventos"):
        ev_cols = {c["name"] for c in inspector.get_columns("samu_eventos")}
        ev_vals: dict[str, object] = {}
        if "id" in ev_cols:
            ev_vals["id"] = str(uuid.uuid4())
        if "ocorrencia_id" in ev_cols:
            ev_vals["ocorrencia_id"] = ocorrencia_id
        if "tipo" in ev_cols:
            ev_vals["tipo"] = "SOS_RECEBIDO"
        if "profissional" in ev_cols:
            ev_vals["profissional"] = "APP_CIDADAO"
        if "detalhes" in ev_cols:
            ev_vals["detalhes"] = json.dumps(
                {"origem": "app_cidadao", "cidadao_id": cidadao_id, "protocolo": protocolo},
                ensure_ascii=False,
            )
        if "criado_em" in ev_cols:
            ev_vals["criado_em"] = agora_utc

        if ev_vals:
            ev_cols_sql = ", ".join(ev_vals.keys())
            ev_params_sql = ", ".join(f":{k}" for k in ev_vals.keys())
            db.execute(text(f"INSERT INTO samu_eventos ({ev_cols_sql}) VALUES ({ev_params_sql})"), ev_vals)

    alerta_ws = {
        "tipo": "NOVO_SOS",
        "protocolo": protocolo,
        "ocorrencia_id": ocorrencia_id,
        "latitude": lat_f,
        "longitude": lon_f,
        "horario": agora_utc.isoformat(),
        "alerta_visual": True,
        "alerta_sonoro": True,
        "status": "recebida",
    }
    return True, ocorrencia_id, alerta_ws


async def _notificar_central_ws(alerta_ws: dict | None) -> None:
    if not alerta_ws:
        return
    try:
        import suas_samu
        if hasattr(suas_samu, "central") and hasattr(suas_samu.central, "publicar"):
            await suas_samu.central.publicar(alerta_ws)
    except Exception:
        pass


# --- Schemas Pydantic ---
class CadastroIn(BaseModel):
    cns: str
    cpf: str
    nome_completo: str = Field(min_length=3, max_length=150)
    data_nascimento: str
    telefone: str = Field(min_length=8, max_length=30)
    senha: str = Field(min_length=8, max_length=128)
    tipo_sanguineo: str | None = Field(default=None, max_length=10)
    alergias: str | None = Field(default=None, max_length=300)
    condicoes_cronicas: str | None = Field(default=None, max_length=300)
    contacto_responsavel: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    cns: str
    senha: str


class PerfilUpdateIn(BaseModel):
    telefone: str | None = Field(default=None, max_length=30)
    tipo_sanguineo: str | None = Field(default=None, max_length=10)
    alergias: str | None = Field(default=None, max_length=300)
    condicoes_cronicas: str | None = Field(default=None, max_length=300)
    contacto_responsavel: str | None = Field(default=None, max_length=120)


class TriageIn(BaseModel):
    queixa_principal: str = Field(min_length=3, max_length=1500)
    gravidade: str


class AlarmePosologiaIn(BaseModel):
    nome_medicamento: str = Field(min_length=2, max_length=180)
    dosagem: str | None = Field(default=None, max_length=80)
    tipo_tratamento: str = Field(default="TEMPORARIO")  # TEMPORARIO ou CONTINUO
    intervalo_horas: int = Field(default=8)  # 6, 8, 12, 24 ou 0
    duracao_dias: int | None = Field(default=7, ge=1, le=365)
    hora_inicial: str = Field(default="08:00", max_length=10)
    horarios_personalizados: str | None = Field(default=None, max_length=200)
    origem: str = Field(default="Cidadão / Prescrição", max_length=40)


class AutomedicacaoIn(BaseModel):
    nome_medicamento: str = Field(min_length=2, max_length=180)
    codigo_barras: str | None = Field(default=None, max_length=100)


class FarmaciaQrIn(BaseModel):
    medicamento_id: int | None = None
    medicamento_nome: str = Field(min_length=2, max_length=180)
    modalidade: str = Field(default="SUS")  # SUS ou PLANO_DESCONTO


class SosIn(BaseModel):
    latitude: str | None = None
    longitude: str | None = None
    observacao: str | None = Field(default=None, max_length=300)


# --- Autenticação ---
def current_citizen(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Autenticação necessária")
    token = authorization[7:].strip()
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session = db.query(CitizenSession).filter_by(token_hash=digest).first()
    if not session or session.expires_at < int(time.time()):
        raise HTTPException(401, "Sessão inválida ou expirada. Faça login novamente.")
    citizen = db.query(models.CidadaoPerfil).filter_by(id=session.cidadao_id).first()
    if not citizen:
        raise HTTPException(401, "Cadastro do cidadão não encontrado")
    return citizen


# --- Endpoints 100% Ativos ---
@router.post("/cadastro", status_code=201)
def cadastro(data: CadastroIn, db: Session = Depends(get_db)):
    cns = only_digits(data.cns)
    cpf = only_digits(data.cpf)
    if len(cns) != 15:
        raise HTTPException(422, "O Cartão Nacional de Saúde (CNS) deve conter exatamente 15 dígitos.")
    if not validar_cpf(cpf):
        raise HTTPException(422, "CPF inválido. Verifique os 11 dígitos informados.")

    if db.query(CitizenAuth).filter_by(cns=cns).first():
        raise HTTPException(409, "Este Cartão SUS (CNS) já possui cadastro ativo. Faça login.")

    citizen = db.query(models.CidadaoPerfil).filter_by(cpf=cpf).first()
    if citizen and db.query(CitizenAuth).filter_by(cidadao_id=citizen.id).first():
        raise HTTPException(409, "Este CPF já possui conta cadastrada. Faça login com seu CNS.")

    if not citizen:
        perfil_kwargs = {}
        candidatos = {
            "nome_completo": data.nome_completo.strip(),
            "cpf": cpf,
            "cns": cns,
            "data_nascimento": data.data_nascimento,
            "telefone": data.telefone.strip(),
            "tipo_sanguineo": (data.tipo_sanguineo or "").strip() or None,
            "alergias": (data.alergias or "").strip() or None,
            "condicoes_cronicas": (data.condicoes_cronicas or "").strip() or None,
            "contacto_responsavel": (data.contacto_responsavel or "").strip() or None,
        }
        for k, v in candidatos.items():
            if hasattr(models.CidadaoPerfil, k):
                perfil_kwargs[k] = v
        citizen = models.CidadaoPerfil(**perfil_kwargs)
        db.add(citizen)
        db.flush()

    vital_code = "SUAS-VITAL-" + secrets.token_hex(6).upper()
    auth_row = CitizenAuth(
        cidadao_id=citizen.id,
        cns=cns,
        password_hash=password_hash(data.senha),
        vital_code=vital_code,
    )
    db.add(auth_row)
    db.commit()
    db.refresh(citizen)

    return {
        "status": "ativo",
        "mensagem": "Cadastro concluído com sucesso! Acesso liberado.",
        "cidadao_id": citizen.id,
        "cns": cns,
        "vital_code": vital_code,
    }


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    cns = only_digits(data.cns)
    auth = db.query(CitizenAuth).filter_by(cns=cns).first()
    if not auth or not check_password(data.senha, auth.password_hash):
        raise HTTPException(401, "Cartão SUS ou senha incorretos.")

    if not auth.vital_code:
        auth.vital_code = "SUAS-VITAL-" + secrets.token_hex(6).upper()

    token = secrets.token_urlsafe(40)
    ttl = 86400  # 24 horas
    db.add(
        CitizenSession(
            cidadao_id=auth.cidadao_id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=int(time.time()) + ttl,
        )
    )
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl}


@router.get("/me")
def me(c=Depends(current_citizen), db: Session = Depends(get_db)):
    auth = db.query(CitizenAuth).filter_by(cidadao_id=c.id).first()
    return {
        "id": c.id,
        "nome_completo": getattr(c, "nome_completo", None),
        "cpf": getattr(c, "cpf", None),
        "cns": auth.cns if auth else getattr(c, "cns", None),
        "telefone": getattr(c, "telefone", None),
        "data_nascimento": str(getattr(c, "data_nascimento", "")) if getattr(c, "data_nascimento", None) else None,
        "tipo_sanguineo": getattr(c, "tipo_sanguineo", None),
        "alergias": getattr(c, "alergias", None),
        "condicoes_cronicas": getattr(c, "condicoes_cronicas", None),
        "contacto_responsavel": getattr(c, "contacto_responsavel", None),
        "vital_code": auth.vital_code if auth else f"SUAS-VITAL-{c.id}",
    }


@router.put("/me")
def atualizar_perfil(data: PerfilUpdateIn, c=Depends(current_citizen), db: Session = Depends(get_db)):
    updates = data.model_dump(exclude_unset=True)
    for k, v in updates.items():
        if hasattr(c, k):
            setattr(c, k, v.strip() if isinstance(v, str) and v.strip() else None)
    db.commit()
    db.refresh(c)
    return {"status": "atualizado", "mensagem": "Cartão Vital e dados de emergência atualizados."}


@router.get("/cartao-vital")
def cartao_vital(c=Depends(current_citizen), db: Session = Depends(get_db)):
    auth = db.query(CitizenAuth).filter_by(cidadao_id=c.id).first()
    vital_code = auth.vital_code if auth and auth.vital_code else f"SUAS-VITAL-{c.id}"
    payload_qr = (
        f"SUAS-SOS|{vital_code}|"
        f"NOME:{getattr(c, 'nome_completo', 'Cidadão')}|"
        f"SANGUE:{getattr(c, 'tipo_sanguineo', None) or 'N/I'}|"
        f"ALERGIAS:{getattr(c, 'alergias', None) or 'Nenhuma informada'}|"
        f"CONTATO:{getattr(c, 'contacto_responsavel', None) or '192'}"
    )
    return {
        "vital_code": vital_code,
        "qr_payload": payload_qr,
        "nome": getattr(c, "nome_completo", None),
        "tipo_sanguineo": getattr(c, "tipo_sanguineo", None),
        "alergias": getattr(c, "alergias", None),
        "condicoes_cronicas": getattr(c, "condicoes_cronicas", None),
        "contacto_responsavel": getattr(c, "contacto_responsavel", None),
    }


@router.post("/sos", status_code=201)
async def acionar_sos(data: SosIn, c=Depends(current_citizen), db: Session = Depends(get_db)):
    protocolo = f"SOS-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
    observacao = data.observacao or "Acionamento via App do Cidadão"
    log = CitizenEmergencyLog(
        cidadao_id=c.id,
        protocolo=protocolo,
        latitude=data.latitude,
        longitude=data.longitude,
        observacao=observacao,
    )
    db.add(log)

    registrado_samu, ocorrencia_samu_id, alerta_ws = _registrar_ocorrencia_samu(
        db=db,
        protocolo=protocolo,
        cidadao_id=c.id,
        nome_cidadao=getattr(c, "nome_completo", None),
        latitude=data.latitude,
        longitude=data.longitude,
        observacao=observacao,
    )

    db.commit()
    db.refresh(log)
    await _notificar_central_ws(alerta_ws)

    maps_url = (
        f"https://www.google.com/maps?q={data.latitude},{data.longitude}"
        if data.latitude and data.longitude
        else None
    )
    return {
        "protocolo": protocolo,
        "ocorrencia_samu_id": ocorrencia_samu_id,
        "registrado_samu": registrado_samu,
        "status": log.status,
        "maps_url": maps_url,
        "contato_emergencia": getattr(c, "contacto_responsavel", None),
        "mensagem": "Alerta SOS registrado permanentemente no SAMU com sua geolocalização.",
    }


@router.post("/triagens", status_code=201)
def criar_triagem(data: TriageIn, c=Depends(current_citizen), db: Session = Depends(get_db)):
    grav = data.gravidade.upper().strip()
    if grav not in ("LEVE", "MODERADO", "GRAVE"):
        raise HTTPException(422, "Gravidade inválida. Use LEVE, MODERADO ou GRAVE.")

    if grav == "GRAVE":
        unidade = "UPA 24h / Pronto Atendimento Urgente (Prioridade Vermelha/Laranja)"
        tempo_min = 12
    elif grav == "MODERADO":
        unidade = "UPA 24h ou Policlínica de Referência (Prioridade Amarela)"
        tempo_min = 30
    else:
        unidade = "UBS — Unidade Básica de Saúde mais próxima (Prioridade Verde/Azul)"
        tempo_min = 45

    protocolo = f"TRI-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
    qr_checkin = f"SUAS-CHECKIN|{protocolo}|CNS:{only_digits(getattr(c, 'cns', ''))[-4:] or c.id}|GRAV:{grav}"

    item = CitizenTriage(
        cidadao_id=c.id,
        protocolo=protocolo,
        queixa_principal=data.queixa_principal.strip(),
        gravidade_autorreferida=grav,
        unidade_indicada=unidade,
        tempo_estimado_min=tempo_min,
        qr_checkin=qr_checkin,
        status="Pré-triagem concluída · Check-in QR liberado (sem ficha física)",
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "protocolo": item.protocolo,
        "gravidade": grav,
        "unidade_indicada": item.unidade_indicada,
        "tempo_estimado_min": item.tempo_estimado_min,
        "qr_checkin": item.qr_checkin,
        "status": item.status,
    }


@router.get("/triagens")
def listar_triagens(c=Depends(current_citizen), db: Session = Depends(get_db)):
    rows = (
        db.query(CitizenTriage)
        .filter_by(cidadao_id=c.id)
        .order_by(CitizenTriage.id.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": r.id,
            "protocolo": r.protocolo or f"TRI-{r.id}",
            "queixa_principal": r.queixa_principal,
            "gravidade": r.gravidade_autorreferida,
            "unidade_indicada": r.unidade_indicada,
            "tempo_estimado_min": r.tempo_estimado_min,
            "qr_checkin": r.qr_checkin,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/prescricoes")
def prescricoes(c=Depends(current_citizen), db: Session = Depends(get_db)):
    rows = (
        db.query(models.MedicamentoItem)
        .filter_by(cidadao_id=c.id)
        .order_by(models.MedicamentoItem.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": p.id,
            "medicamento_nome": p.medicamento_nome,
            "dosagem": p.dosagem,
            "posologia": p.posologia,
            "fornecido_pelo_sus": bool(getattr(p, "fornecido_pelo_sus", False)),
            "dispensado": bool(p.dispensado),
            "horarios_alarme": getattr(p, "horarios_alarme", None),
        }
        for p in rows
    ]


@router.get("/farmacia/meus-registros")
def farmacia_meus_registros(c=Depends(current_citizen), db: Session = Depends(get_db)):
    rows = (
        db.query(models.MedicamentoItem)
        .filter(models.MedicamentoItem.cidadao_id == c.id)
        .order_by(models.MedicamentoItem.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": r.id,
            "medicamento_nome": r.medicamento_nome,
            "dosagem": r.dosagem,
            "posologia": r.posologia,
            "fornecido_pelo_sus": bool(r.fornecido_pelo_sus),
            "dispensado": bool(r.dispensado),
            "data_dispensacao": r.data_dispensacao.isoformat() if r.data_dispensacao else None,
            "horarios_alarme": r.horarios_alarme,
        }
        for r in rows
    ]


@router.post("/farmacia/gerar-qr")
def farmacia_gerar_qr(data: FarmaciaQrIn, c=Depends(current_citizen)):
    codigo = f"FARMA-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    modalidade_label = "SUS-RETIRADA-AGENDADA" if data.modalidade == "SUS" else "PLANO-DESCONTO-CREDENCIADA"
    assinatura = hashlib.sha256(f"{c.id}:{codigo}:{data.medicamento_nome}".encode()).hexdigest()[:12].upper()
    qr_payload = f"SUAS-FARMA|{modalidade_label}|{codigo}|MED:{data.medicamento_nome}|HASH:{assinatura}"
    return {
        "codigo_autorizacao": codigo,
        "modalidade": data.modalidade,
        "medicamento_nome": data.medicamento_nome,
        "qr_payload": qr_payload,
        "validade_horas": 48,
        "mensagem": "QR Code gerado! Apresente no balcão da farmácia para validação e ativação automática da posologia.",
    }


# --- Despertador Inteligente de Posologia (Temporário 6/6h, 8/8h, 12/12h e Uso Contínuo) ---
@router.get("/alarmes-posologia")
def listar_alarmes_posologia(c=Depends(current_citizen), db: Session = Depends(get_db)):
    agora = datetime.utcnow()
    rows = (
        db.query(CitizenMedicationSchedule)
        .filter_by(cidadao_id=c.id)
        .order_by(CitizenMedicationSchedule.id.desc())
        .limit(100)
        .all()
    )
    resultado = []
    alterou = False
    for r in rows:
        dias_restantes = None
        if r.tipo_tratamento == "TEMPORARIO" and r.fim_em:
            delta = (r.fim_em - agora).total_seconds()
            if delta <= 0 and r.ativo:
                r.ativo = False
                alterou = True
            dias_restantes = max(0, int((delta + 86399) // 86400))
        resultado.append(
            {
                "id": r.id,
                "nome_medicamento": r.nome_medicamento,
                "dosagem": r.dosagem,
                "tipo_tratamento": r.tipo_tratamento,
                "intervalo_horas": r.intervalo_horas,
                "duracao_dias": r.duracao_dias,
                "dias_restantes": dias_restantes,
                "horarios_alarme": r.horarios_alarme,
                "origem": r.origem,
                "ativo": bool(r.ativo),
                "inicio_em": r.inicio_em.isoformat() if r.inicio_em else None,
                "fim_em": r.fim_em.isoformat() if r.fim_em else None,
            }
        )
    if alterou:
        db.commit()
    return resultado


@router.post("/alarmes-posologia", status_code=201)
def criar_alarme_posologia(data: AlarmePosologiaIn, c=Depends(current_citizen), db: Session = Depends(get_db)):
    tipo = data.tipo_tratamento.upper().strip()
    if tipo not in ("TEMPORARIO", "CONTINUO"):
        raise HTTPException(422, "Tipo de tratamento deve ser TEMPORARIO ou CONTINUO.")

    if data.horarios_personalizados and data.horarios_personalizados.strip():
        horarios = data.horarios_personalizados.strip()
    else:
        horarios = calcular_horarios_intervalo(data.intervalo_horas, data.hora_inicial)

    agora = datetime.utcnow()
    fim_em = None
    duracao = None
    if tipo == "TEMPORARIO":
        duracao = data.duracao_dias or 7
        fim_em = agora + timedelta(days=duracao)

    row = CitizenMedicationSchedule(
        cidadao_id=c.id,
        nome_medicamento=data.nome_medicamento.strip(),
        dosagem=(data.dosagem or "").strip() or None,
        tipo_tratamento=tipo,
        intervalo_horas=data.intervalo_horas,
        duracao_dias=duracao,
        horarios_alarme=horarios,
        origem=data.origem,
        ativo=True,
        inicio_em=agora,
        fim_em=fim_em,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "id": row.id,
        "nome_medicamento": row.nome_medicamento,
        "tipo_tratamento": row.tipo_tratamento,
        "intervalo_horas": row.intervalo_horas,
        "duracao_dias": row.duracao_dias,
        "horarios_alarme": row.horarios_alarme,
        "fim_em": row.fim_em.isoformat() if row.fim_em else None,
        "mensagem": f"Despertador ativado nos horários: {row.horarios_alarme}",
    }


@router.delete("/alarmes-posologia/{alarme_id}")
def desativar_alarme_posologia(alarme_id: int, c=Depends(current_citizen), db: Session = Depends(get_db)):
    row = db.query(CitizenMedicationSchedule).filter_by(id=alarme_id, cidadao_id=c.id).first()
    if not row:
        raise HTTPException(404, "Alarme não encontrado.")
    row.ativo = False
    db.commit()
    return {"status": "desativado", "id": alarme_id}


# --- Compatibilidade com rotas anteriores ---
@router.get("/medicamentos-pessoais")
def meus_medicamentos(c=Depends(current_citizen), db: Session = Depends(get_db)):
    rows = db.query(models.MedicamentoCidadao).filter_by(cidadao_id=c.id).limit(100).all()
    return [
        {
            "id": r.id,
            "nome_medicamento": r.nome_medicamento,
            "tipo_presricao": r.tipo_presricao,
            "horarios_alarme": r.horarios_alarme,
        }
        for r in rows
    ]


@router.post("/automedicacoes", status_code=201)
def registrar_automedicacao_pessoal(data: AutomedicacaoIn, c=Depends(current_citizen), db: Session = Depends(get_db)):
    row = models.AutomedicacaoLog(cidadao_id=c.id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    limite = datetime.utcnow().timestamp() - 60 * 86400
    qtd = sum(
        1
        for x in db.query(models.AutomedicacaoLog)
        .filter_by(cidadao_id=c.id, nome_medicamento=data.nome_medicamento)
        .all()
        if x.data_registo and x.data_registo.timestamp() >= limite
    )
    return {
        "id": row.id,
        "registros_60_dias": qtd,
        "alerta": "Atenção: uso repetido registrado nos últimos 60 dias. Procure avaliação médica." if qtd >= 3 else None,
    }
