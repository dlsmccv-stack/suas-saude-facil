from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
import datetime

class RegulacaoItem(Base):
    __tablename__ = "regulacao_itens"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_nome = Column(String, index=True)
    tipo_item = Column(String, index=True)  # "Oculos", "Protese", "Aparelho Auditivo"
    status = Column(String, default="Pendente")
    data_solicitacao = Column(DateTime, default=datetime.datetime.utcnow)

class Triagem(Base):
    __tablename__ = "triagens"

    id = Column(Integer, primary_key=True, index=True)
    paciente_nome = Column(String, index=True)
    queixa_principal = Column(String)
    cor_prioridade = Column(String)
    tempo_alvo_atendimento = Column(String)
    data_triagem = Column(DateTime, default=datetime.datetime.utcnow)

class SuasSocial(Base):
    __tablename__ = "suas_sociais"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_nome = Column(String, index=True)
    nis = Column(String, index=True)
    situacao_vulnerabilidade = Column(String)
    beneficio_ativo = Column(String)
    data_cadastro = Column(DateTime, default=datetime.datetime.utcnow)

# ==========================================
# NOVAS TABELAS: APP DO CIDADÃO & PREVENÇÃO
# ==========================================

class CidadaoPerfil(Base):
    __tablename__ = "cidadaos_perfil"

    id = Column(Integer, primary_key=True, index=True)
    nome_completo = Column(String, index=True)
    cpf = Column(String, unique=True, index=True)
    tipo_sanguineo = Column(String)
    alergias = Column(String, nullable=True)
    condicoes_cronicas = Column(String, nullable=True)
    contacto_responsavel = Column(String) # Nome e telefone do responsável/familiar de emergência
    
    # Dados do Plano de Saúde (para direcionamento e desafogo da rede pública)
    possui_plano_saude = Column(Boolean, default=False)
    operadora_plano = Column(String, nullable=True)
    numero_carteira = Column(String, nullable=True)
    tipo_cobertura = Column(String, nullable=True) # "Apenas Urgência/Emergência" ou "Hospitalar com Internação"
    rede_credenciada = Column(String, nullable=True)

    medicamentos = relationship("MedicamentoCidadao", back_populates="cidadao")
    automedicacoes = relationship("AutomedicacaoLog", back_populates="cidadao")

class MedicamentoCidadao(Base):
    __tablename__ = "medicamentos_cidadao"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"))
    nome_medicamento = Column(String)
    tipo_presricao = Column(String) # "continuo" (para doenças crónicas) ou "temporario_emergencia" (para viroses, infecções, etc.)
    data_inicio = Column(DateTime, nullable=True)
    data_fim = Column(DateTime, nullable=True)
    horarios_alarme = Column(String, nullable=True) # Ex: "08:00, 20:00"

    cidadao = relationship("CidadaoPerfil", back_populates="medicamentos")

class AutomedicacaoLog(Base):
    __tablename__ = "automedicacao_logs"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"))
    nome_medicamento = Column(String)
    codigo_barras = Column(String, nullable=True)
    data_registo = Column(DateTime, default=datetime.datetime.utcnow)

    cidadao = relationship("CidadaoPerfil", back_populates="automedicacoes")
