from sqlalchemy import Column, Integer, String, DateTime
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
