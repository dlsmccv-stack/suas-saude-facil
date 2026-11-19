from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class MedicamentoCreate(BaseModel):
    cidadao_id: Optional[int] = Field(None, description="ID do cidadão associado para integração com o App", example=1)
    cidadao_nome: Optional[str] = Field(None, description="Nome completo do cidadão beneficiário", example="Maria da Silva")
    medicamento_nome: str = Field(..., description="Nome comercial ou genérico do medicamento", example="Paracetamol 500mg")
    dosagem: Optional[str] = Field("Conforme prescrição", description="Concentração ou dosagem do fármaco", example="500mg")
    posologia: str = Field(..., description="Instruções de toma ou administração prescritas pelo médico", example="1 comprimido de 8 em 8 horas")
    quantidade_disponibilizada: int = Field(1, description="Quantidade total de unidades disponibilizadas", example=30)
    fornecido_pelo_sus: bool = Field(True, description="Indica se é fornecido gratuitamente pelo SUS (True) ou rede particular (False)", example=True)
    uso_continuo: bool = Field(False, description="Indica se é de uso contínuo (crónico) ou temporário/emergência", example=False)
    horarios_alarme: Optional[str] = Field("08:00, 20:00", description="Horários configurados para o alarme/campainha no telemóvel", example="08:00, 20:00")
    
    # Novos campos opcionais para fluxo hospitalar interno
    modalidade_atendimento: Optional[str] = Field("farmacia_externa", description="'farmacia_externa' (retirada/casa) ou 'hospitalar_imediato' (aplicação na unidade)")
    local_administracao: Optional[str] = Field(None, description="Ex.: Enfermaria, Emergência, Leito 04, Posto de Enfermagem")
    via_administracao: Optional[str] = Field(None, description="Ex.: VO, EV, IM, SC")

    class Config:
        json_schema_extra = {
            "example": {
                "cidadao_id": 1,
                "cidadao_nome": "Maria da Silva",
                "medicamento_nome": "Paracetamol 500mg",
                "dosagem": "500mg",
                "posologia": "1 comprimido de 8 em 8 horas",
                "quantidade_disponibilizada": 30,
                "fornecido_pelo_sus": True,
                "uso_continuo": False,
                "horarios_alarme": "08:00, 20:00",
                "modalidade_atendimento": "farmacia_externa",
                "local_administracao": None,
                "via_administracao": "VO"
            }
        }


class MedicamentoDispensacaoQRCode(BaseModel):
    qr_code_token: str = Field(..., description="Token único codificado no QR Code para validação na farmácia", example="QR-SUS-PHARM-987654XYZ")


class MedicamentoResponse(BaseModel):
    id: int
    cidadao_id: Optional[int] = None
    cidadao_nome: str
    medicamento_nome: str
    dosagem: str
    posologia: str
    quantidade_disponibilizada: int
    fornecido_pelo_sus: bool
    uso_continuo: bool
    horarios_alarme: Optional[str] = None
    qr_code_token: str
    dispensado: bool
    data_dispensacao: Optional[datetime] = None

    class Config:
        from_attributes = True
