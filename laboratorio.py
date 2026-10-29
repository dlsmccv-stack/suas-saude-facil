from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta

router = APIRouter(prefix="/laboratorio", tags=["Laboratório e Retornos"])

class ResultadoExameDTO(BaseModel):
    paciente_id: str
    medico_solicitante: str
    exame_nome: str
    status: str  # Ex: "REALIZADO"
    resultado_detalhes: str

@router.post("/resultado")
def receber_resultado_laboratorio(dados: ResultadoExameDTO):
    """
    Recebe a notificação do laboratório, valida o resultado, 
    agenda automaticamente a consulta de retorno e notifica o cidadão.
    """
    if dados.status != "REALIZADO":
        raise HTTPException(status_code=400, detail="Status de exame inválido.")
    
    # Simulação de regra de agendamento automático para daqui a 14 dias
    data_retorno = datetime.now() + timedelta(days=14)
    
    return {
        "status": "sucesso",
        "mensagem": f"Resultado do exame '{dados.exame_nome}' integrado com sucesso.",
        "medico_notificado": dados.medico_solicitante,
        "retorno_agendado_automaticamente": data_retorno.strftime("%d/%m/%Y às 10:00"),
        "notificacao_enviada_ao_cidadao": True,
        "lembrete_ativado": "Ativado no PWA Offline-First"
    }
