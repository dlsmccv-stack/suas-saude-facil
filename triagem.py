from sqlalchemy import Column, Integer, String, DateTime
from database import Base
import datetime

class TriagemItem(Base):
    __tablename__ = "triagem_itens"

    id = Column(Integer, primary_key=True, index=True)
    paciente_nome = Column(String, index=True)
    queixa_principal = Column(String)
    cor_prioridade = Column(String, index=True)  # "Vermelho", "Laranja", "Amarelo", "Verde", "Azul"
    tempo_alvo_atendimento = Column(String)  # Ex: "Imediato", "10 minutos", etc.
    data_triagem = Column(DateTime, default=datetime.datetime.utcnow)
