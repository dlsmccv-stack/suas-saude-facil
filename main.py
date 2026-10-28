from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models, schemas, triagem, triagem_schemas, suas_social, suas_social_schemas, fhir_integration, emergency_qrcode, farmacia, farmacia_schemas, educacao_medica, educacao_medica_schemas

# Inicializa as tabelas no banco de dados de forma centralizada
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="SUAS Saúde / Saúde +Fácil",
    description="""
    ## Ecossistema Integrado de Saúde, Assistência Social e Inovação Tecnológica
    
    Esta API disponibiliza serviços operacionais para:
    * **Regulação**: Gestão centralizada de solicitações e itens regulados.
    * **Triagem de Manchester**: Classificação de risco e priorização de atendimento.
    * **Assistência Social (SUAS)**: Registo e acompanhamento de cidadãos em situação de vulnerabilidade.
    * **Interoperabilidade FHIR**: Troca padronizada de dados de saúde.
    * **QR Code de Emergência**: Acionamento rápido e suporte com geolocalização.
    * **Farmácia Digital**: Gestão e retirada de medicamentos por QR Code.
    * **Educação Médica**: Módulos de capacitação e formação continuada.
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
            "QR Code de Emergência & Acionamento SAMU com GPS",
            "Farmácia Digital & Retirada por QR Code",
            "Educação Continuada & Indústria Farmacêutica"
        ]
    }

# Endpoints de Regulação
@app.post(
    "/regulacao/", 
    response_model=schemas.RegulacaoResponse,
    summary="Criar registo de regulação",
    description="Regista um novo pedido de regulação no sistema."
)
def criar_regulacao(regulacao: schemas.RegulacaoCreate, db: Session = Depends(database.get_db)):
    db_regulacao = models.RegulacaoItem(**regulacao.model_dump())
    db.add(db_regulacao)
    db.commit()
    db.refresh(db_regulacao)
    return db_regulacao

@app.get(
    "/regulacao/", 
    response_model=list[schemas.RegulacaoResponse],
    summary="Listar registos de regulação",
    description="Retorna a lista de todos os pedidos de regulação cadastrados."
)
def listar_regulacoes(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.RegulacaoItem).offset(skip).limit(limit).all()

# Rotas dos demais módulos com tags organizadas
app.include_router(triagem.router, prefix="/triagem", tags=["Triagem de Manchester"])
app.include_router(suas_social.router, prefix="/suas", tags=["Assistência Social (SUAS)"])
app.include_router(fhir_integration.router, prefix="/fhir", tags=["Interoperabilidade FHIR"])
app.include_router(emergency_qrcode.router, prefix="/emergencia", tags=["QR Code de Emergência"])
app.include_router(farmacia.router, prefix="/farmacia", tags=["Farmácia Digital"])
app.include_router(educacao_medica.router, prefix="/educacao", tags=["Educação Médica"])
