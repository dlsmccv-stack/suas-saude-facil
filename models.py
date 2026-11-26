from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
import datetime

class RegulacaoItem(Base):
    __tablename__ = "regulacao_itens"

    id = Column(Integer, primary_key=True, index=True)
    # Campos originais mantidos para retrocompatibilidade com Painel do Médico
    cidadao_nome = Column(String, index=True, nullable=True)
    tipo_item = Column(String, index=True, nullable=True)
    status = Column(String, default="Pendente", nullable=True)

    # Campos completos de Regulação + Integração Intersetorial SUAS
    paciente_nome = Column(String, index=True, nullable=True)
    unidade_origem = Column(String, nullable=True)
    unidade_destino = Column(String, nullable=True)
    especialidade_solicitada = Column(String, nullable=True)
    prioridade_clinica = Column(String, default="Média", nullable=True)
    status_solicitacao = Column(String, default="Pendente", nullable=True)
    observacoes_medicas = Column(Text, nullable=True)

    # Dados cruzados automaticamente do SUAS & Triagem
    nis_vinculado = Column(String, nullable=True)
    vulnerabilidade_suas = Column(String, nullable=True)
    beneficio_social_ativo = Column(String, nullable=True)
    score_prioridade_intersetorial = Column(Integer, default=0)
    justificativa_priorizacao = Column(Text, nullable=True)
    acao_suas_vinculada = Column(String, nullable=True)

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
# APP DO CIDADÃO & PREVENÇÃO
# ==========================================

class CidadaoPerfil(Base):
    __tablename__ = "cidadaos_perfil"

    id = Column(Integer, primary_key=True, index=True)
    nome_completo = Column(String, index=True)
    cpf = Column(String, unique=True, index=True)
    tipo_sanguineo = Column(String)
    alergias = Column(String, nullable=True)
    condicoes_cronicas = Column(String, nullable=True)
    contacto_responsavel = Column(String)

    possui_plano_saude = Column(Boolean, default=False)
    operadora_plano = Column(String, nullable=True)
    numero_carteira = Column(String, nullable=True)
    tipo_cobertura = Column(String, nullable=True)
    rede_credenciada = Column(String, nullable=True)

    medicamentos = relationship("MedicamentoCidadao", back_populates="cidadao")
    automedicacoes = relationship("AutomedicacaoLog", back_populates="cidadao")
    emergencias = relationship("EmergencyItem", back_populates="cidadao")
    exames_requisitados = relationship("ExameRequisicaoItem", back_populates="cidadao")
    notificacoes = relationship("NotificacaoCidadaoItem", back_populates="cidadao")

class MedicamentoCidadao(Base):
    __tablename__ = "medicamentos_cidadao"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"))
    nome_medicamento = Column(String)
    tipo_presricao = Column(String)
    data_inicio = Column(DateTime, nullable=True)
    data_fim = Column(DateTime, nullable=True)
    horarios_alarme = Column(String, nullable=True)

    cidadao = relationship("CidadaoPerfil", back_populates="medicamentos")

class AutomedicacaoLog(Base):
    __tablename__ = "automedicacao_logs"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"))
    nome_medicamento = Column(String)
    codigo_barras = Column(String, nullable=True)
    data_registo = Column(DateTime, default=datetime.datetime.utcnow)

    cidadao = relationship("CidadaoPerfil", back_populates="automedicacoes")

# ==========================================
# REQUISIÇÕES DE EXAMES & NOTIFICAÇÕES DO CIDADÃO
# ==========================================

class ExameRequisicaoItem(Base):
    __tablename__ = "exames_requisicoes"

    id = Column(Integer, primary_key=True, index=True)
    codigo_requisicao = Column(String, unique=True, index=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), nullable=True)
    cidadao_nome = Column(String, index=True)
    medico_crm = Column(String, nullable=True)
    categoria_exame = Column(String, default="Laboratorial")
    exame_nome = Column(String, index=True)
    laboratorio_ou_unidade = Column(String, nullable=True)
    prioridade = Column(String, default="Rotina")
    indicacao_clinica = Column(Text, nullable=True)
    preparo_observacoes = Column(Text, nullable=True)
    status_exame = Column(String, default="SOLICITADO")
    data_solicitacao = Column(DateTime, default=datetime.datetime.utcnow)

    cidadao = relationship("CidadaoPerfil", back_populates="exames_requisitados")

class NotificacaoCidadaoItem(Base):
    __tablename__ = "notificacoes_cidadao"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), nullable=True)
    cidadao_nome = Column(String, index=True, nullable=True)
    tipo_evento = Column(String, index=True)  # "EXAME_SOLICITADO" | "RETORNO_MEDICO"
    titulo = Column(String)
    mensagem = Column(Text)
    data_agendada = Column(String, nullable=True)
    alarme_sugerido = Column(String, nullable=True)
    lida = Column(Boolean, default=False)
    data_criacao = Column(DateTime, default=datetime.datetime.utcnow)

    cidadao = relationship("CidadaoPerfil", back_populates="notificacoes")

# ==========================================
# FARMÁCIA DIGITAL & DISPENSAÇÃO
# ==========================================

class MedicamentoItem(Base):
    __tablename__ = "medicamentos_farmacia"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), nullable=True)
    cidadao_nome = Column(String, index=True)
    medicamento_nome = Column(String, index=True)
    dosagem = Column(String)
    posologia = Column(String)
    quantidade_disponibilizada = Column(Integer)

    fornecido_pelo_sus = Column(Boolean, default=True)
    uso_continuo = Column(Boolean, default=False)
    horarios_alarme = Column(String, nullable=True)

    qr_code_token = Column(String, unique=True, index=True)
    dispensado = Column(Boolean, default=False)
    data_dispensacao = Column(DateTime, nullable=True)

# ==========================================
# QR CODE DE EMERGÊNCIA (INTEGRADO)
# ==========================================

class EmergencyItem(Base):
    __tablename__ = "emergency_items"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_id = Column(Integer, ForeignKey("cidadaos_perfil.id"), nullable=True)
    cidadao_nome = Column(String, index=True)
    tipo_sanguineo = Column(String)
    alergias = Column(String, nullable=True)
    condicoes_medicas = Column(String, nullable=True)
    contacto_emergencia_nome = Column(String)
    contacto_emergencia_telefone = Column(String)
    qr_code_token = Column(String, unique=True, index=True)
    data_registo = Column(DateTime, default=datetime.datetime.utcnow)

    cidadao = relationship("CidadaoPerfil", back_populates="emergencias")

# ==========================================
# SUPORTE A RECURSOS FHIR GENÉRICOS
# ==========================================

class FHIRItem(Base):
    __tablename__ = "fhir_items"

    id = Column(Integer, primary_key=True, index=True)
    resource_type = Column(String, index=True)
    resource_data = Column(Text)
    data_criacao = Column(DateTime, default=datetime.datetime.utcnow)

# ==========================================
# EDUCAÇÃO MÉDICA CONTINUADA
# ==========================================

class EducacaoMedicaItem(Base):
    __tablename__ = "educacao_medica_itens"

    id = Column(Integer, primary_key=True, index=True)

    titulo_curso = Column(String, nullable=False)
    especialidade = Column(String, nullable=False)
    parceiro_industria = Column(String, nullable=False)

    descricao_conteudo = Column(Text, nullable=False)
    link_material_estudo = Column(String, nullable=False)

    pontos_credito_cme = Column(
        Integer,
        nullable=False,
        default=0
    )

    data_publicacao = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        nullable=False
    )

# ==========================================
# ASSINATURAS, ATIVAÇÃO E EVENTOS B2B
# ==========================================

class B2BAssinaturaUnidade(Base):
    __tablename__ = "b2b_assinaturas_unidades"

    id = Column(Integer, primary_key=True, index=True)
    unidade_id = Column(String, unique=True, index=True, nullable=False)
    cnpj_cliente = Column(String, index=True, nullable=False)
    nome_unidade = Column(String, nullable=False)
    email_responsavel = Column(String, nullable=True)

    plano = Column(String, nullable=False)
    plano_nome = Column(String, nullable=False)
    valor_adesao = Column(String, nullable=False)
    custo_setup_estimado = Column(String, nullable=False)
    mensalidade = Column(String, nullable=False)
    repasse_ti_mensal = Column(String, nullable=False)
    liquido_operacao_mensal = Column(String, nullable=False)

    status = Column(String, default="AGUARDANDO_ADESAO", index=True)
    instalacao_ativa = Column(Boolean, default=False)
    api_key_unidade = Column(String, unique=True, index=True, nullable=False)
    proximo_vencimento = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

    pagamentos = relationship("B2BPagamentoLog", back_populates="assinatura")

class B2BPagamentoLog(Base):
    __tablename__ = "b2b_pagamentos_log"

    id = Column(Integer, primary_key=True, index=True)
    assinatura_id = Column(Integer, ForeignKey("b2b_assinaturas_unidades.id"), nullable=False)
    unidade_id = Column(String, index=True, nullable=False)
    tipo_pagamento = Column(String, nullable=False)  # ADESAO ou MENSALIDADE
    valor_pago = Column(String, nullable=False)
    comprovante_ref = Column(String, nullable=False)
    confirmado_em = Column(DateTime, default=datetime.datetime.utcnow)

    assinatura = relationship("B2BAssinaturaUnidade", back_populates="pagamentos")

class B2BEventoClinico(Base):
    __tablename__ = "b2b_eventos_clinicos"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True, nullable=False)
    unidade_id = Column(String, index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)
    patient_hash = Column(String, index=True, nullable=False)
    patient_name = Column(String, nullable=True)
    gravidade = Column(String, default="LEVE")
    queixa_ou_descricao = Column(Text, nullable=True)
    medicamentos_json = Column(Text, nullable=True)
    alergias_json = Column(Text, nullable=True)
    condicoes_json = Column(Text, nullable=True)
    status_fluxo = Column(String, default="AGUARDANDO_ACOLHIMENTO")
    alerta_imediato = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class B2BGatilhoTreinamento(Base):
    __tablename__ = "b2b_gatilhos_treinamento"

    id = Column(Integer, primary_key=True, index=True)
    trigger_id = Column(String, unique=True, index=True, nullable=False)
    unidade_id = Column(String, index=True, nullable=False)
    setor = Column(String, nullable=False)
    motivo_gatilho = Column(String, nullable=False)
    gravidade = Column(String, default="MODERADA")
    protocolo_recomendado = Column(Text, nullable=False)
    equipe_alvo = Column(String, nullable=True)
    status = Column(String, default="DISPARADO")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class B2BIdempotencia(Base):
    __tablename__ = "b2b_idempotencia"

    id = Column(Integer, primary_key=True, index=True)
    request_key = Column(String, unique=True, index=True, nullable=False)
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
