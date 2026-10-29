from ai_engine import PatientDataSchema, ai_predictor  # Importa o motor preditivo e o esquema de IA
import cco_cpo_external  # Importa o módulo isolado do CCO / CPO (Setor Externo)
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session
import cidadao, database, educacao_medica, emergency_qrcode, farmacia, fhir_integration, laboratorio, medico, models, regulacao, suas_social, triagem

# Inicializa as tabelas no banco de dados de forma centralizada
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="SUAS Saúde / Saúde +Fácil",
    description="""
    ## Ecossistema Integrado de Saúde, Assistência Social e Inovação Tecnológica
    
    Esta API disponibiliza serviços operacionais para:
    * **App do Cidadão**: Onboarding, gestão de planos de saúde, alarmes de medicamentos (contínuos e temporários), scanner preventivo e QR Code de emergência/tela de bloqueio.
    * **Regulação**: Gestão centralizada de solicitações, leitos e encaminhamentos médicos.
    * **Painel do Médico**: Prescrições clínicas, geração de QR Code de farmácia e pedidos de regulação.
    * **Laboratório e Retornos**: Gestão de resultados de exames, notificações e agendamento automático de retorno.
    * **Triagem de Manchester**: Classificação de risco e priorização de atendimento.
    * **Assistência Social (SUAS)**: Registo e acompanhamento de cidadãos em situação de vulnerabilidade.
    * **Interoperabilidade FHIR**: Troca padronizada de dados de saúde (R4).
    * **QR Code de Emergência**: Acionamento rápido e suporte com dados clínicos críticos.
    * **Farmácia Digital**: Gestão e retirada de medicamentos por QR Code.
    * **Educação Médica**: Módulos de capacitação, formação continuada e créditos CME.
    * **CCO / CPO (Setor Externo Isolado)**: Canal seguro e segregado para reporte de ocorrências e gestão operacional descentralizada.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

@app.get("/", tags=["Início"])
def read_root():
    return {
        "sistema": "SUAS Saúde / Saúde +Fácil",
        "status": "Operacional",
        "modulos": [
            "Core API",
            "App do Cidadão (Plano de Saúde, Medicamentos & Preventivo)",
            "Painel do Médico (Prescrições & Regulação)",
            "Laboratório e Retornos Automáticos",
            "Regulação",
            "Triagem (Protocolo de Manchester)",
            "Apoio Social (SUAS)",
            "Interoperabilidade FHIR",
            "QR Code de Emergência & Acionamento SAMU",
            "Farmácia Digital & Retirada por QR Code",
            "Educação Continuada & Indústria Farmacêutica",
            "Motor de IA Preditiva de Eventos Adversos",
            "CCO / CPO - Setor Externo Isolado"
        ]
    }

# Registo de todos os routers modulares do ecossistema
app.include_router(regulacao.router, prefix="/regulacao", tags=["Regulação"])
app.include_router(medico.router)  # Inclui o Painel do Médico com prefixo /medico definido no router
app.include_router(laboratorio.router)  # Inclui as rotas de laboratório e agendamento automático de retorno
app.include_router(triagem.router, prefix="/triagem", tags=["Triagem de Manchester"])
app.include_router(suas_social.router, prefix="/suas", tags=["Assistência Social (SUAS)"])
app.include_router(fhir_integration.router, prefix="/fhir", tags=["Interoperabilidade FHIR"])
app.include_router(emergency_qrcode.router, prefix="/emergencia", tags=["QR Code de Emergência"])
app.include_router(farmacia.router, prefix="/farmacia", tags=["Farmácia Digital"])
app.include_router(educacao_medica.router, prefix="/educacao", tags=["Educação Médica"])
app.include_router(cidadao.router)  # Inclui as rotas do App do Cidadão com prefixo /cidadao

# Registo do Router Isolado para o CCO / CPO (Setor Externo)
app.include_router(cco_cpo_external.router)


# --- MÓDULO DE IA: Preditiva de Eventos Adversos ---
@app.post(
    "/api/v1/predict-adverse-event",
    tags=["Inteligência Preditiva (IA)"],
    summary="Avalia o risco de evento adverso no prontuário"
)
def predict_adverse_event(patient_data: PatientDataSchema):
    try:
        data_dict = patient_data.dict()
        resultado = ai_predictor.predict_risk(data_dict)
        return {
            "status": "sucesso",
            "dados_analisados": data_dict,
            "predicao": resultado
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar predição de IA: {str(e)}"
        )
