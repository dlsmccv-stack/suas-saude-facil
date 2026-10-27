from sqlalchemy import Column, Integer, String, DateTime, Boolean
from database import Base
import datetime
import uuid

class MedicamentoItem(Base):
    __tablename__ = "farmacia_medicamentos"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_nome = Column(String, index=True)
    medicamento_nome = Column(String)
    dosagem = Column(String)
    posologia = Column(String)
    quantidade_disponibilizada = Column(Integer)
    qr_code_token = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    dispensado = Column(Boolean, default=False)
    data_dispensacao = Column(DateTime, nullable=True)
    data_prescricao = Column(DateTime, default=datetime.datetime.utcnow)
