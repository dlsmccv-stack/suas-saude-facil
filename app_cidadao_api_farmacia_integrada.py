"""API Integrada e 100% Ativa do App do Cidadão — SUAS Saúde +Fácil.
Compatível com main.py, models.py e database.py existentes sem alterá-los.
Inclui: Cadastro/Login flexível (CPF ou CNS), gatilho estratégico de CNS no
acompanhamento de medicação, Cartão Vital com QR Code, Alerta de Emergência
com GPS e contato familiar, Pré-Triagem Inteligente com direcionamento por
Unidade e Convênio livre com sugestão dinâmica, Farmácia Digital e
Despertador de Posologia.
"""
import os
import re
import uuid
import json
import secrets
import hashlib
import hmac
import time
from urllib.parse import quote as url_quote
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, inspect, text
from sqlalchemy.orm import Session
import database
import models

router = APIRouter(prefix="/app-cidadao", tags=["App do Cidadão"])


# --- Modelos Complementares ---
class CitizenAuth(models.Base):
    __tablename__ = "app_cidadao_auth"
    id = Column(Integer, primary_key=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), unique=True, nullable=False)
    cns = Column(String(20), unique=True, index=True, nullable=False)
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
    protocolo = Column(String(64), unique=True, index=True, nullable=True)
    queixa_principal = Column(Text, nullable=False)
    gravidade_autorreferida = Column(String(40), nullable=False)
    unidade_indicada = Column(String(255), default="UBS de Referência")
    tempo_estimado_min = Column(Integer, default=35)
    qr_checkin = Column(String(255), nullable=True)
    status = Column(String(255), default="Pré-triagem validada · Aguardando check-in QR")
    created_at = Column(DateTime, default=datetime.utcnow)


class CitizenMedicationSchedule(models.Base):
    __tablename__ = "app_cidadao_alarmes_posologia"
    id = Column(Integer, primary_key=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), nullable=False, index=True)
    nome_medicamento = Column(String(180), nullable=False)
    dosagem = Column(String(80), nullable=True)
    tipo_tratamento = Column(String(20), default="TEMPORARIO")
    intervalo_horas = Column(Integer, default=8)
    duracao_dias = Column(Integer, nullable=True)
    horarios_alarme = Column(String(200), nullable=False)
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
    status = Column(String(80), default="Alerta registrado no sistema · Geolocalização capturada")
    created_at = Column(DateTime, default=datetime.utcnow)


try:
    if hasattr(database, "engine") and database.engine is not None:
        models.Base.metadata.create_all(bind=database.engine)
except Exception:
    pass


def get_db():
    yield from database.get_db()


def only_digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _normalizar_operadora(valor: str | None) -> str | None:
    if not valor:
        return None
    limpo = re.sub(r"\s+", " ", str(valor).strip())
    return limpo if limpo else None


def _is_cns_oficial(val: str | None) -> bool:
    d = only_digits(val)
    return len(d) == 15 and not (val or "").startswith("PROV-")


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
    cidadao_id: int | None,
    nome_cidadao: str | None,
    latitude: str | None,
    longitude: str | None,
    observacao: str,
) -> tuple[bool, str | None, dict | None]:
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
    if "cidadao_id" in colunas and cidadao_id is not None:
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
        valores["status"] = "registrada_local"
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
            ev_vals["tipo"] = "ALERTA_REGISTRADO"
        if "profissional" in ev_cols:
            ev_vals["profissional"] = "APP_CIDADAO"
        if "detalhes" in ev_cols:
            ev_vals["detalhes"] = json.dumps(
                {
                    "origem": "app_cidadao",
                    "cidadao_id": cidadao_id,
                    "protocolo": protocolo,
                    "integracao_externa_ativa": False,
                },
                ensure_ascii=False,
            )
        if "criado_em" in ev_cols:
            ev_vals["criado_em"] = agora_utc

        if ev_vals:
            ev_cols_sql = ", ".join(ev_vals.keys())
            ev_params_sql = ", ".join(f":{k}" for k in ev_vals.keys())
            db.execute(text(f"INSERT INTO samu_eventos ({ev_cols_sql}) VALUES ({ev_params_sql})"), ev_vals)

    alerta_ws = {
        "tipo": "NOVO_ALERTA_EMERGENCIA",
        "protocolo": protocolo,
        "ocorrencia_id": ocorrencia_id,
        "latitude": lat_f,
        "longitude": lon_f,
        "horario": agora_utc.isoformat(),
        "alerta_visual": True,
        "alerta_sonoro": True,
        "status": "registrada_local",
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


def _extrair_codigo_qr(codigo_bruto: str) -> str:
    val = (codigo_bruto or "").strip()
    if "|" in val:
        partes = [p.strip() for p in val.split("|") if p.strip()]
        for p in partes:
            if p.upper().startswith(("SUAS-VITAL-", "QR-EMERG-")):
                return p
        if len(partes) > 1:
            return partes[1]
    return val


def _resolver_familiar_por_qr(db: Session, codigo_bruto: str) -> tuple[int | None, str | None, str | None]:
    codigo = _extrair_codigo_qr(codigo_bruto)
    if not codigo:
        return None, None, None

    if hasattr(models, "EmergencyItem"):
        emerg = db.query(models.EmergencyItem).filter(models.EmergencyItem.qr_code_token == codigo).first()
        if emerg:
            telefone = only_digits(emerg.contacto_emergencia_telefone)
            cidadao = None
            if emerg.cidadao_id:
                cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == emerg.cidadao_id).first()
            if not telefone and cidadao:
                telefone = only_digits(getattr(cidadao, "contacto_responsavel", None))
            return emerg.cidadao_id, emerg.cidadao_nome, telefone or None

    auth = db.query(CitizenAuth).filter(CitizenAuth.vital_code == codigo).first()
    if auth:
        cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == auth.cidadao_id).first()
        if cidadao:
            telefone = only_digits(getattr(cidadao, "contacto_responsavel", None))
            return cidadao.id, getattr(cidadao, "nome_completo", None), telefone or None

    return None, None, None


# --- Schemas Pydantic ---
class CadastroIn(BaseModel):
    cns: str | None = Field(default=None, description="Opcional no primeiro acesso; pode ser vinculado depois")
    cpf: str
    nome_completo: str = Field(min_length=3, max_length=150)
    data_nascimento: str
    telefone: str = Field(min_length=8, max_length=30)
    senha: str = Field(min_length=8, max_length=128)
    tipo_sanguineo: str | None = Field(default=None, max_length=10)
    alergias: str | None = Field(default=None, max_length=300)
    condicoes_cronicas: str | None = Field(default=None, max_length=300)
    contacto_responsavel: str | None = Field(default=None, max_length=120)
    possui_plano_saude: bool = False
    operadora_plano: str | None = Field(default=None, max_length=100)
    numero_carteira: str | None = Field(default=None, max_length=60)


class LoginIn(BaseModel):
    identificador: str | None = Field(default=None, description="CPF (11 dígitos) ou Cartão SUS CNS (15 dígitos)")
    cns: str | None = Field(default=None, description="Compatibilidade retroativa com clientes que enviam 'cns'")
    senha: str


class RecuperarSenhaIn(BaseModel):
    cns: str | None = None
    cpf: str
    nova_senha: str = Field(min_length=8, max_length=128)


class VincularCnsIn(BaseModel):
    cns: str = Field(..., description="Cartão Nacional de Saúde com 15 dígitos numéricos")


class PerfilUpdateIn(BaseModel):
    telefone: str | None = Field(default=None, max_length=30)
    cns: str | None = Field(default=None, max_length=20)
    tipo_sanguineo: str | None = Field(default=None, max_length=10)
    alergias: str | None = Field(default=None, max_length=300)
    condicoes_cronicas: str | None = Field(default=None, max_length=300)
    contacto_responsavel: str | None = Field(default=None, max_length=120)
    possui_plano_saude: bool | None = None
    operadora_plano: str | None = Field(default=None, max_length=100)
    numero_carteira: str | None = Field(default=None, max_length=60)


class TriageIn(BaseModel):
    queixa_principal: str = Field(min_length=3, max_length=1500)
    gravidade: str
    unidade_id: str | None = Field(default=None, max_length=80)
    unidade_nome: str | None = Field(default=None, max_length=180)
    modalidade_atendimento: str = Field(default="PLANO_SAUDE", description="PLANO_SAUDE | SUS | PARTICULAR")
    operadora_plano: str | None = Field(default=None, max_length=100)
    numero_carteira: str | None = Field(default=None, max_length=60)


class AlarmePosologiaIn(BaseModel):
    nome_medicamento: str = Field(min_length=2, max_length=180)
    dosagem: str | None = Field(default=None, max_length=80)
    tipo_tratamento: str = Field(default="TEMPORARIO")
    intervalo_horas: int = Field(default=8)
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
    modalidade: str = Field(default="SUS")


class SosIn(BaseModel):
    latitude: str | None = None
    longitude: str | None = None
    observacao: str | None = Field(default=None, max_length=300)


class QrSamuAcionarIn(BaseModel):
    qr_code: str = Field(min_length=1, max_length=160)
    latitude: float | None = None
    longitude: float | None = None
    observacao: str | None = Field(default="Alerta de emergência registrado via leitura de QR Code", max_length=300)


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


# --- Endpoints Públicos de Emergência via QR ---
@router.get("/qr-emergencia/resolver")
def resolver_qr_emergencia(qr_code: str, db: Session = Depends(get_db)):
    cidadao_id, _, telefone_familiar = _resolver_familiar_por_qr(db, qr_code)
    return {
        "valido": bool(cidadao_id or telefone_familiar),
        "tem_familiar_cadastrado": bool(telefone_familiar),
        "telefone_familiar": telefone_familiar,
        "despacho_externo_ativo": False,
    }


@router.post("/qr-emergencia/acionar", status_code=201)
async def acionar_samu_por_qr(payload: QrSamuAcionarIn, db: Session = Depends(get_db)):
    cidadao_id, nome_cidadao, telefone_familiar = _resolver_familiar_por_qr(db, payload.qr_code)
    protocolo = f"EMG-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
    lat_str = str(payload.latitude) if payload.latitude is not None else None
    lon_str = str(payload.longitude) if payload.longitude is not None else None
    obs = payload.observacao or f"Alerta de emergência via QR ({_extrair_codigo_qr(payload.qr_code)})"

    alerta_ws = None
    registrado_no_sistema = False
    ocorrencia_id = None

    if cidadao_id:
        log = CitizenEmergencyLog(
            cidadao_id=cidadao_id,
            protocolo=protocolo,
            latitude=lat_str,
            longitude=lon_str,
            observacao=obs,
        )
        db.add(log)
        registrado_no_sistema, ocorrencia_id, alerta_ws = _registrar_ocorrencia_samu(
            db=db,
            protocolo=protocolo,
            cidadao_id=cidadao_id,
            nome_cidadao=nome_cidadao,
            latitude=lat_str,
            longitude=lon_str,
            observacao=obs,
        )
        db.commit()
        await _notificar_central_ws(alerta_ws)

    maps_url = (
        f"https://www.google.com/maps?q={payload.latitude},{payload.longitude}"
        if payload.latitude is not None and payload.longitude is not None
        else None
    )
    ddd_phone = (
        telefone_familiar
        if (not telefone_familiar or telefone_familiar.startswith("55"))
        else f"55{telefone_familiar}"
    )
    mensagem = (
        f"🚨 ALERTA DE EMERGÊNCIA — Protocolo {protocolo}. "
        f"Ficha de primeiros socorros acessada via QR."
        + (f" Localização: {maps_url}" if maps_url else "")
        + " Se necessário, acione o serviço público 192 ou a cobertura do plano."
    )
    wa_url = (
        f"https://wa.me/{ddd_phone}?text={url_quote(mensagem)}"
        if ddd_phone
        else f"https://wa.me/?text={url_quote(mensagem)}"
    )

    return {
        "protocolo": protocolo,
        "registrado_samu": registrado_no_sistema,
        "despacho_externo_ativo": False,
        "ocorrencia_samu_id": ocorrencia_id,
        "maps_url": maps_url,
        "telefone_familiar": telefone_familiar,
        "whatsapp_url": wa_url,
        "mensagem_familiar": mensagem,
    }


# --- Cadastro, Login, Vinculação CNS e Recuperação de Senha ---
@router.post("/cadastro", status_code=201)
def cadastro(data: CadastroIn, db: Session = Depends(get_db)):
    cns_digitos = only_digits(data.cns)
    cpf = only_digits(data.cpf)

    if cns_digitos and len(cns_digitos) != 15:
        raise HTTPException(422, "Se informado, o Cartão Nacional de Saúde (CNS) deve conter 15 dígitos.")
    if not validar_cpf(cpf):
        raise HTTPException(422, "CPF inválido. Verifique os 11 dígitos informados.")

    if cns_digitos and db.query(CitizenAuth).filter_by(cns=cns_digitos).first():
        raise HTTPException(409, "Este Cartão SUS (CNS) já possui cadastro ativo. Faça login ou recupere sua senha.")

    citizen = db.query(models.CidadaoPerfil).filter_by(cpf=cpf).first()
    if citizen and db.query(CitizenAuth).filter_by(cidadao_id=citizen.id).first():
        raise HTTPException(409, "Este CPF já possui conta cadastrada. Faça login com seu CPF/CNS ou recupere sua senha.")

    contacto_limpo = (data.contacto_responsavel or "").strip() or (data.telefone or "").strip() or "Não informado"
    cns_armazenado = cns_digitos if len(cns_digitos) == 15 else f"PROV-{cpf}"
    operadora_limpa = _normalizar_operadora(data.operadora_plano)

    if not citizen:
        perfil_kwargs = {}
        candidatos = {
            "nome_completo": data.nome_completo.strip(),
            "cpf": cpf,
            "cns": cns_digitos if len(cns_digitos) == 15 else None,
            "cartao_sus": cns_digitos if len(cns_digitos) == 15 else None,
            "data_nascimento": data.data_nascimento,
            "telefone": data.telefone.strip(),
            "tipo_sanguineo": (data.tipo_sanguineo or "").strip() or "N/I",
            "alergias": (data.alergias or "").strip() or None,
            "condicoes_cronicas": (data.condicoes_cronicas or "").strip() or None,
            "contacto_responsavel": contacto_limpo,
            "possui_plano_saude": bool(data.possui_plano_saude or operadora_limpa),
            "operadora_plano": operadora_limpa,
            "numero_carteira": (data.numero_carteira or "").strip() or None,
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
        cns=cns_armazenado,
        password_hash=password_hash(data.senha),
        vital_code=vital_code,
    )
    db.add(auth_row)
    db.commit()
    db.refresh(citizen)

    return {
        "status": "ativo",
        "mensagem": "Cadastro salvo permanentemente! Você já pode entrar com seu CPF" + (" ou Cartão SUS." if len(cns_digitos) == 15 else "."),
        "cidadao_id": citizen.id,
        "cpf": cpf,
        "cns": cns_digitos if len(cns_digitos) == 15 else None,
        "cns_pendente": len(cns_digitos) != 15,
        "vital_code": vital_code,
    }


@router.post("/recuperar-senha")
def recuperar_senha(data: RecuperarSenhaIn, db: Session = Depends(get_db)):
    cpf = only_digits(data.cpf)
    cns = only_digits(data.cns)
    if not validar_cpf(cpf):
        raise HTTPException(422, "Informe um CPF válido (11 dígitos).")

    citizen = db.query(models.CidadaoPerfil).filter_by(cpf=cpf).first()
    if not citizen:
        raise HTTPException(404, "Nenhum cadastro encontrado para este CPF.")

    auth = db.query(CitizenAuth).filter_by(cidadao_id=citizen.id).first()
    if not auth:
        raise HTTPException(404, "Conta de acesso não encontrada para este cadastro.")

    if cns and _is_cns_oficial(auth.cns) and auth.cns != cns:
        raise HTTPException(403, "O Cartão SUS informado não confere com o CPF cadastrado.")

    auth.password_hash = password_hash(data.nova_senha)
    db.query(CitizenSession).filter_by(cidadao_id=auth.cidadao_id).delete()
    db.commit()

    return {
        "status": "redefinida",
        "mensagem": "Nova senha salva com sucesso! Já pode entrar com seu CPF ou Cartão SUS.",
    }


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    bruto = only_digits(data.identificador or data.cns)
    if len(bruto) not in (11, 15):
        raise HTTPException(422, "Informe seu CPF (11 dígitos) ou Cartão SUS (15 dígitos).")

    auth = None
    if len(bruto) == 15:
        auth = db.query(CitizenAuth).filter_by(cns=bruto).first()
    else:
        citizen = db.query(models.CidadaoPerfil).filter_by(cpf=bruto).first()
        if citizen:
            auth = db.query(CitizenAuth).filter_by(cidadao_id=citizen.id).first()
        if not auth:
            auth = db.query(CitizenAuth).filter_by(cns=f"PROV-{bruto}").first()

    if not auth or not check_password(data.senha, auth.password_hash):
        raise HTTPException(401, "CPF/Cartão SUS ou senha incorretos.")

    if not auth.vital_code:
        auth.vital_code = "SUAS-VITAL-" + secrets.token_hex(6).upper()

    token = secrets.token_urlsafe(40)
    ttl = 86400
    db.add(
        CitizenSession(
            cidadao_id=auth.cidadao_id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=int(time.time()) + ttl,
        )
    )
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl}


@router.put("/vincular-cns")
def vincular_cns_cidadao(data: VincularCnsIn, c=Depends(current_citizen), db: Session = Depends(get_db)):
    cns = only_digits(data.cns)
    if len(cns) != 15:
        raise HTTPException(422, "O Cartão Nacional de Saúde (CNS) deve conter exatamente 15 dígitos numéricos.")

    existente = db.query(CitizenAuth).filter(CitizenAuth.cns == cns, CitizenAuth.cidadao_id != c.id).first()
    if existente:
        raise HTTPException(409, "Este número de Cartão SUS já está vinculado a outro cadastro.")

    auth = db.query(CitizenAuth).filter_by(cidadao_id=c.id).first()
    if auth:
        auth.cns = cns

    if hasattr(c, "cns"):
        c.cns = cns
    if hasattr(c, "cartao_sus"):
        c.cartao_sus = cns

    db.commit()
    return {
        "status": "vinculado",
        "cns": cns,
        "mensagem": "Cartão SUS (CNS) vinculado ao seu prontuário digital com sucesso!",
    }


@router.get("/me")
def me(c=Depends(current_citizen), db: Session = Depends(get_db)):
    auth = db.query(CitizenAuth).filter_by(cidadao_id=c.id).first()
    raw_cns = auth.cns if auth else (getattr(c, "cns", None) or getattr(c, "cartao_sus", None))
    cns_oficial = raw_cns if _is_cns_oficial(raw_cns) else None

    return {
        "id": c.id,
        "nome_completo": getattr(c, "nome_completo", None),
        "cpf": getattr(c, "cpf", None),
        "cns": cns_oficial,
        "cns_pendente": not bool(cns_oficial),
        "telefone": getattr(c, "telefone", None),
        "data_nascimento": str(getattr(c, "data_nascimento", "")) if getattr(c, "data_nascimento", None) else None,
        "tipo_sanguineo": getattr(c, "tipo_sanguineo", None),
        "alergias": getattr(c, "alergias", None),
        "condicoes_cronicas": getattr(c, "condicoes_cronicas", None),
        "contacto_responsavel": getattr(c, "contacto_responsavel", None),
        "possui_plano_saude": bool(getattr(c, "possui_plano_saude", False)),
        "operadora_plano": getattr(c, "operadora_plano", None),
        "numero_carteira": getattr(c, "numero_carteira", None),
        "vital_code": auth.vital_code if auth else f"SUAS-VITAL-{c.id}",
    }


@router.put("/me")
def atualizar_perfil(data: PerfilUpdateIn, c=Depends(current_citizen), db: Session = Depends(get_db)):
    updates = data.model_dump(exclude_unset=True)
    if "cns" in updates and updates["cns"]:
        cns_limpo = only_digits(updates["cns"])
        if len(cns_limpo) != 15:
            raise HTTPException(422, "O Cartão SUS (CNS) deve conter 15 dígitos numéricos.")
        auth = db.query(CitizenAuth).filter_by(cidadao_id=c.id).first()
        if auth:
            auth.cns = cns_limpo
        updates["cns"] = cns_limpo
        if hasattr(c, "cartao_sus"):
            c.cartao_sus = cns_limpo

    if "operadora_plano" in updates:
        updates["operadora_plano"] = _normalizar_operadora(updates["operadora_plano"])

    for k, v in updates.items():
        if hasattr(c, k):
            if isinstance(v, bool):
                setattr(c, k, v)
            else:
                val = v.strip() if isinstance(v, str) and v.strip() else None
                if k == "contacto_responsavel" and not val:
                    val = "Não informado"
                setattr(c, k, val)
    db.commit()
    db.refresh(c)
    return {"status": "atualizado", "mensagem": "Cartão Vital, plano de saúde e dados de emergência atualizados."}


@router.get("/cartao-vital")
def cartao_vital(c=Depends(current_citizen), db: Session = Depends(get_db)):
    auth = db.query(CitizenAuth).filter_by(cidadao_id=c.id).first()
    vital_code = auth.vital_code if auth and auth.vital_code else f"SUAS-VITAL-{c.id}"
    payload_qr = f"https://suas-saude-facil.onrender.com/app-cidadao?qr={vital_code}"
    return {
        "vital_code": vital_code,
        "qr_payload": payload_qr,
        "nome": getattr(c, "nome_completo", None),
        "tipo_sanguineo": getattr(c, "tipo_sanguineo", None),
        "alergias": getattr(c, "alergias", None),
        "condicoes_cronicas": getattr(c, "condicoes_cronicas", None),
        "contacto_responsavel": getattr(c, "contacto_responsavel", None),
        "possui_plano_saude": bool(getattr(c, "possui_plano_saude", False)),
        "operadora_plano": getattr(c, "operadora_plano", None),
        "numero_carteira": getattr(c, "numero_carteira", None),
    }


@router.get("/operadoras-sugeridas")
def listar_operadoras_sugeridas(db: Session = Depends(get_db)):
    """Retorna operadoras de saúde já captadas na base para sugestão espontânea."""
    sugestoes: set[str] = set()

    if hasattr(models.CidadaoPerfil, "operadora_plano"):
        perfis = (
            db.query(models.CidadaoPerfil.operadora_plano)
            .filter(models.CidadaoPerfil.operadora_plano.isnot(None))
            .distinct()
            .all()
        )
        for (op,) in perfis:
            norm = _normalizar_operadora(op)
            if norm:
                sugestoes.add(norm)

    triagens_recentes = (
        db.query(CitizenTriage.qr_checkin, CitizenTriage.status)
        .order_by(CitizenTriage.id.desc())
        .limit(200)
        .all()
    )
    for qr_val, status_val in triagens_recentes:
        for texto in (qr_val or "", status_val or ""):
            match = re.search(r"CONV:([^|]+)", texto)
            if match:
                norm = _normalizar_operadora(match.group(1))
                if norm:
                    sugestoes.add(norm)

    return {"operadoras": sorted(sugestoes, key=str.lower)}


@router.post("/sos", status_code=201)
async def acionar_sos(data: SosIn, c=Depends(current_citizen), db: Session = Depends(get_db)):
    protocolo = f"SOS-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
    observacao = data.observacao or "Alerta de emergência registrado via App do Cidadão"
    log = CitizenEmergencyLog(
        cidadao_id=c.id,
        protocolo=protocolo,
        latitude=data.latitude,
        longitude=data.longitude,
        observacao=observacao,
    )
    db.add(log)

    registrado_no_sistema, ocorrencia_id, alerta_ws = _registrar_ocorrencia_samu(
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
        "ocorrencia_samu_id": ocorrencia_id,
        "registrado_samu": registrado_no_sistema,
        "despacho_externo_ativo": False,
        "status": log.status,
        "maps_url": maps_url,
        "contato_emergencia": getattr(c, "contacto_responsavel", None),
        "mensagem": "Alerta e geolocalização salvos no sistema. Se precisar de despacho público, ligue 192 ou use a cobertura do seu plano.",
    }


@router.post("/triagens", status_code=201)
def criar_triagem(data: TriageIn, c=Depends(current_citizen), db: Session = Depends(get_db)):
    grav = data.gravidade.upper().strip()
    if grav not in ("LEVE", "MODERADO", "GRAVE"):
        raise HTTPException(422, "Gravidade inválida. Use LEVE, MODERADO ou GRAVE.")

    modalidade = (data.modalidade_atendimento or "PLANO_SAUDE").upper().strip()
    if modalidade not in ("SUS", "PLANO_SAUDE", "PARTICULAR"):
        modalidade = "PLANO_SAUDE"

    operadora = _normalizar_operadora(data.operadora_plano)
    carteira = (data.numero_carteira or "").strip() or None

    if modalidade == "PLANO_SAUDE":
        if not operadora or not carteira:
            raise HTTPException(422, "Para atendimento por Plano de Saúde, informe a operadora e o número da carteirinha.")
        if hasattr(c, "possui_plano_saude"):
            c.possui_plano_saude = True
        if hasattr(c, "operadora_plano"):
            c.operadora_plano = operadora
        if hasattr(c, "numero_carteira"):
            c.numero_carteira = carteira

    if data.unidade_nome and data.unidade_nome.strip():
        unidade = data.unidade_nome.strip()
        tempo_min = 12 if grav == "GRAVE" else (25 if grav == "MODERADO" else 35)
    elif grav == "GRAVE":
        unidade = "Pronto Atendimento / Unidade de Urgência Referenciada"
        tempo_min = 12
    elif grav == "MODERADO":
        unidade = "Hospital / Centro Médico Referenciado"
        tempo_min = 30
    else:
        unidade = "Unidade / Clínica de Referência"
        tempo_min = 45

    protocolo = f"TRI-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
    id_ref = only_digits(getattr(c, "cns", ""))[-4:] or only_digits(getattr(c, "cpf", ""))[-4:] or str(c.id)

    if modalidade == "PLANO_SAUDE":
        tag_mod = f"CONV:{operadora}|CART:{carteira}"
        status_fluxo = "PRE_TRIAGEM_AGUARDANDO_CONVENIO"
        status_legivel = f"Pré-triagem enviada · Aguardando autorização do convênio ({operadora})"
    elif modalidade == "PARTICULAR":
        tag_mod = "MOD:PARTICULAR"
        status_fluxo = "PRE_TRIAGEM_PARTICULAR"
        status_legivel = "Pré-triagem concluída · Check-in Particular liberado"
    else:
        tag_mod = "MOD:SUS"
        status_fluxo = "PRE_TRIAGEM_SUS"
        status_legivel = "Pré-triagem concluída · Check-in QR SUS liberado"

    qr_checkin = f"SUAS-CHECKIN|{protocolo}|UNID:{data.unidade_id or 'geral'}|ID:{id_ref}|GRAV:{grav}|{tag_mod}"

    item = CitizenTriage(
        cidadao_id=c.id,
        protocolo=protocolo,
        queixa_principal=data.queixa_principal.strip(),
        gravidade_autorreferida=grav,
        unidade_indicada=unidade,
        tempo_estimado_min=tempo_min,
        qr_checkin=qr_checkin,
        status=status_legivel,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "protocolo": item.protocolo,
        "gravidade": grav,
        "modalidade_atendimento": modalidade,
        "operadora_plano": operadora,
        "numero_carteira": carteira,
        "status_fluxo": status_fluxo,
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
