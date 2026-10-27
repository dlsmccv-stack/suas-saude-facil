from sqlalchemy import Column, Integer, String, DateTime, Boolean
from database import Base
import datetime

class MedicamentoItem(Base):
    __tablename__ = "farmacia_medicamentos"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_nome = Column(String, index=True)
    medicamento_nome = Column(String)
    dosagem = Column(String)
    posologia = Column(String)  # Ex: "1 comprimido de 8 em 8 horas"
    quantidade_disponibilizada = Column(Integer)
    dispensado = Column(Boolean, default=True)
    data_dispensacao = Column(DateTime, default=datetime.datetime.utcnow)
