from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# ==========================================
# 1. REGULAÇÃO (Mantido do seu original)
# ==========================================

class RegulacaoCreate(BaseModel):
    cidadao_nome: str
    tipo_item: str

class RegulacaoResponse(BaseModel):
    id: int
    cidadao_nome: str
    tipo_item: str
    status: str
    data_solicitacao: datetime

    class Config:
        from_attributes = True


# ==========================================
# 2. TRIAGEM DE MANCHESTER
# ==========================================

class TriagemCreate(BaseModel):
    paciente_nome: str
    queixa_principal: str
    cor_prioridade: str
    tempo_alvo_atendimento: str

class TriagemResponse(BaseModel):
    id: int
    paciente_nome: str
    queixa_principal: str
    cor_prioridade: str
    tempo_alvo_atendimento: str
    data_triagem: datetime

    class Config:
        from_attributes = True


# ==========================================
# 3. ASSISTÊNCIA SOCIAL (SUAS)
# ==========================================

class SuasSocialCreate(BaseModel):
    cidadao_nome: str
    nis: str
    situacao_vulnerabilidade: str
    beneficio_ativo: str

class SuasSocialResponse(BaseModel):
    id: int
    cidadao_nome: str
    nis: str
    situacao_vulnerabilidade: str
    beneficio_ativo: str
    data_cadastro: datetime

    class Config:
        from_attributes = True


# ==========================================
# 4. APP DO CIDADÃO & SAÚDE PREVENTIVA
# ==========================================

class MedicamentoCidadaoCreate(BaseModel):
    nome_medicamento: str
    tipo_presricao: str  # "continuo" ou "temporario_emergencia"
    data_inicio: Optional[datetime] = None
    data_fim: Optional[datetime] = None
    horarios_alarme: Optional[str] = None

class MedicamentoCidadaoResponse(BaseModel):
    id: int
    cidadao_id: int
    nome_medicamento: str
    tipo_presricao: str
    data_inicio: Optional[datetime] = None
    data_fim: Optional[datetime] = None
    horarios_alarme: Optional[str] = None

    class Config:
        from_attributes = True


class AutomedicacaoCreate(BaseModel):
    nome_medicamento: str
    codigo_barras: Optional[str] = None

class AutomedicacaoResponse(AutomedicacaoCreate):
    id: int
    cidadao_id: int
    data_registo: datetime

    class Config:
        from_attributes = True


class CidadaoCreate(BaseModel):
    nome_completo: str
    cpf: str
    tipo_sanguineo: str
    alergias: Optional[str] = None
    condicoes_cronicas: Optional[str] = None
    contacto_responsavel: str
    
    # Plano de Saúde (para direcionamento e desafogo da rede pública)
    possui_plano_saude: bool
    operadora_plano: Optional[str] = None
    numero_carteira: Optional[str] = None

class CidadaoResponse(BaseModel):
    id: int
    nome_completo: str
    cpf: str
    tipo_sanguineo: str
    alergias: Optional[str] = None
    condicoes_cronicas: Optional[str] = None
    contacto_responsavel: str
    
    possui_plano_saude: bool
    operadora_plano: Optional[str] = None
    numero_carteira: Optional[str] = None
    tipo_cobertura: Optional[str] = None
    rede_credenciada: Optional[str] = None

    medicamentos: List[MedicamentoCidadaoResponse] = []
    automedicacoes: List[AutomedicacaoResponse] = []

    class Config:
        from_attributes = True
