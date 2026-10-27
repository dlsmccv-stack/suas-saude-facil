from sqlalchemy import Column, Integer, String, DateTime, Text
from database import Base
import datetime

class ModuloEducacaoItem(Base):
    __tablename__ = "educacao_medica_modulos"

    id = Column(Integer, primary_key=True, index=True)
    titulo_curso = Column(String, index=True)
    especialidade = Column(String, index=True)  # Ex: Cardiologia, Pediatria, Medicina da Família
    parceiro_industria = Column(String)         # Nome do laboratório/indústria farmacêutica parceira
    descricao_conteudo = Column(Text)
    link_material_estudo = Column(String)
    pontos_credito_cme = Column(Integer, default=10) # Créditos de Educação Médica Continuada
    data_publicacao = Column(DateTime, default=datetime.datetime.utcnow)
