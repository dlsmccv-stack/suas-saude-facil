from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class RegulacaoCreate(BaseModel):
    paciente_nome: str = Field(..., description="Nome completo do paciente", example="Maria Aparecida da Silva")
    unidade_origem: str = Field(..., description="Unidade de saúde solicitante", example="UBS Centro")
    unidade_destino: str = Field(..., description="Unidade/Hospital de destino desejado", example="Hospital Regional")
    especialidade_solicitada: str = Field(..., description="Especialidade, leito ou insumo necessário", example="Cardiologia / Consulta Especializada")
    prioridade_clinica: str = Field(..., description="Nível de urgência clínica (Alta, Média, Baixa)", example="Média")
    observacoes_medicas: Optional[str] = Field(None, description="Resumo clínico e justificativa do encaminhamento", example="Hipertensão descompensada; paciente sem rede de apoio familiar.")

class AcionarSuasPayload(BaseModel):
    tipo_apoio_social: str = Field(..., description="Tipo de suporte acionado junto ao CRAS/CREAS", example="Transporte Sanitário Social + Cesta Nutricional")
    equipamento_destino: str = Field(default="CRAS Referência Territorial", description="Unidade do SUAS acionada", example="CRAS Centro")
    observacao_social: Optional[str] = Field(None, description="Detalhes para a equipe de assistência social", example="Paciente idosa hipertensa sem recursos para deslocamento até o hospital.")

class RegulacaoResponse(BaseModel):
    id: int
    paciente_nome: Optional[str] = None
    unidade_origem: Optional[str] = None
    unidade_destino: Optional[str] = None
    especialidade_solicitada: Optional[str] = None
    prioridade_clinica: Optional[str] = None
    status_solicitacao: Optional[str] = "Pendente"
    observacoes_medicas: Optional[str] = None
    nis_vinculado: Optional[str] = None
    vulnerabilidade_suas: Optional[str] = None
    beneficio_social_ativo: Optional[str] = None
    score_prioridade_intersetorial: int = 0
    justificativa_priorizacao: Optional[str] = None
    acao_suas_vinculada: Optional[str] = None
    data_solicitacao: datetime

    class Config:
        from_attributes = True
