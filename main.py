from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import database, modelos, schemas, triagem, triagem_schemas

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
@app.post("/triagem/", response_model=triagem_schemas.TriagemResponse)
def criar_triagem(item: triagem_schemas.TriagemCreate, db: Session = Depends(database.get_db)):
    db_triagem = triagem.TriagemItem(
        paciente_nome=item.paciente_nome,
        queixa_principal=item.queixa_principal,
        cor_prioridade=item.cor_prioridade,
        tempo_alvo_atendimento=item.tempo_alvo_atendimento
    )
    db.add(db_triagem)
    db.commit()
    db.refresh(db_triagem)
    return db_triagem

@app.get("/triagem/", response_model=list[triagem_schemas.TriagemResponse])
def listar_triagens(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    itens = db.query(triagem.TriagemItem).offset(skip).limit(limit).all()
    return itens
