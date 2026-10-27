from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import database, modelos, schemas, triagem

# Inicializa as tabelas no banco de dados para todos os módulos
modelos.Base.metadata.create_all(bind=database.engine)
triagem.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="SUAS Saúde / Saúde +Fácil",
    description="Ecossistema integrado de saúde, assistência social e regulação",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {
        "sistema": "SUAS Saúde / Saúde +Fácil",
        "status": "Operacional",
        "modulos": ["Core API", "Regulação", "Triagem (Protocolo de Manchester)"]
    }

# Endpoints de Regulação
@app.post("/regulacao/", response_model=schemas.RegulacaoResponse)
def criar_regulacao(item: schemas.RegulacaoCreate, db: Session = Depends(database.get_db)):
    db_item = modelos.RegulacaoItem(
        cidadao_nome=item.cidadao_nome,
        tipo_item=item.tipo_item
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.get("/regulacao/", response_model=list[schemas.RegulacaoResponse])
def listar_regulacoes(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    itens = db.query(modelos.RegulacaoItem).offset(skip).limit(limit).all()
    return itens

# Endpoints de Triagem (Protocolo de Manchester)
@app.post("/triagem/")
def criar_triagem(
    paciente_nome: str, 
    queixa_principal: str, 
    cor_prioridade: str, 
    tempo_alvo_atendimento: str, 
    db: Session = Depends(database.get_db)
):
    db_triagem = triagem.TriagemItem(
        paciente_nome=paciente_nome,
        queixa_principal=queixa_principal,
        cor_prioridade=cor_prioridade,
        tempo_alvo_atendimento=tempo_alvo_atendimento
    )
    db.add(db_triagem)
    db.commit()
    db.refresh(db_triagem)
    return db_triagem

@app.get("/triagem/")
def listar_triagens(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    itens = db.query(triagem.TriagemItem).offset(skip).limit(limit).all()
    return itens
