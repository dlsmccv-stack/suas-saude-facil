from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models
import triagem, suas_social, fhir_integration, emergency_qrcode, farmacia, educacao_medica, regulacao

# Inicializa as tabelas no banco de dados de forma centralizada
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="SUAS Saúde / Saúde +Fácil",
    description="""
    ## Ecossistema Integrado de Saúde, Assistência Social e Inovação Tecnológica
    
    Esta API disponibiliza serviços operacionais para:
    * **Regulação**: Gestão centralizada de solicitações, leitos e encaminhamentos médicos.
    * **Triagem de Manchester**: Classificação de risco e priorização de atendimento.
    * **Assistência Social (SUAS)**: Registo e acompanhamento de cidadãos em situação de vulnerabilidade.
    * **Interoperabilidade FHIR**: Troca padronizada de dados de saúde (R4).
    * **QR Code de Emergência**: Acionamento rápido e suporte com dados clínicos críticos.
    * **Farmácia Digital**: Gestão e retirada de medicamentos por QR Code.
    * **Educação Médica**: Módulos de capacitação, formação continuada e créditos CME.
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
            "Regulação",
            "Triagem (Protocolo de Manchester)",
            "Apoio Social (SUAS)",
            "Interoperabilidade FHIR",
            "QR Code de Emergência & Acionamento SAMU",
            "Farmácia Digital & Retirada por QR Code",
            "Educação Continuada & Indústria Farmacêutica"
        ]
    }

# Registo de todos os routers modulares do ecossistema
app.include_router(regulacao.router, prefix="/regulacao", tags=["Regulação"])
app.include_router(triagem.router, prefix="/triagem", tags=["Triagem de Manchester"])
app.include_router(suas_social.router, prefix="/suas", tags=["Assistência Social (SUAS)"])
app.include_router(fhir_integration.router, prefix="/fhir", tags=["Interoperabilidade FHIR"])
app.include_router(emergency_qrcode.router, prefix="/emergencia", tags=["QR Code de Emergência"])
app.include_router.router(farmacia.router, prefix="/farmacia", tags=["Farmácia Digital"]) if hasattr(app.include_router, 'router') else app.include_router(farmacia.router, prefix="/farmacia", tags=["Farmácia Digital"])
app.include_router(educacao_medica.router, prefix="/educacao", tags=["Educação Médica"])
