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
