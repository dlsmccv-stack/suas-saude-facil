from sqlalchemy import Column, Integer, String, DateTime
from database import Base
import datetime

class ApoioSocialItem(Base):
    __tablename__ = "apoio_social_itens"

    id = Column(Integer, primary_key=True, index=True)
    cidadao_nome = Column(String, index=True)
    nis = Column(String, index=True)  # Número de Identificação Social
    situacao_vulnerabilidade = Column(String)
    beneficio_ativo = Column(String)  # Ex: "Bolsa Família", "BPC", etc.
    data_cadastro = Column(DateTime, default=datetime.datetime.utcnow)
