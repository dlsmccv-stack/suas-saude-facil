from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models, schemas, triagem, triagem_schemas, suas_social, suas_social_schemas, fhir_integration, emergency_qrcode, farmacia, farmacia_schemas, educacao_medica, educacao_medica_schemas

# Inicializa as tabelas no banco de dados de forma centralizada
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="SUAS Saúde / Saúde +Fácil",
    description="Ecossistema integrado de saúde, assistência social e inovação tecnológica",
    version="1.0.0"
)

@app.get("/")
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
@app.post("/regulacao/", response_model=schemas.RegulacaoResponse)
def criar_regulacao(regulacao: schemas.RegulacaoCreate, db: Session = Depends(database.get_db)):
    db_regulacao = models.Regulacao(**regulacao.dict())
    db.add(db_regulacao)
    db.commit()
    db.refresh(db_regulacao)
    return db_regulacao

@app.get("/regulacao/", response_model=list[schemas.RegulacaoResponse])
def listar_regulacoes(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Regulacao).offset(skip).limit(limit).all()

# Rotas dos demais módulos
app.include_router(triagem.router, prefix="/triagem", tags=["Triagem de Manchester"])
app.include_router(suas_social.router, prefix="/suas", tags=["Assistência Social (SUAS)"])
app.include_router(fhir_integration.router, prefix="/fhir", tags=["Interoperabilidade FHIR"])
app.include_router(emergency_qrcode.router, prefix="/emergencia", tags=["QR Code de Emergência"])
app.include_router(farmacia.router, prefix="/farmacia", tags=["Farmácia Digital"])
app.include_router(educacao_medica.router, prefix="/educacao", tags=["Educação Médica"])
