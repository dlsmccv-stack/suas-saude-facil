from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import database, modelos, schemas

# Inicializa as tabelas no banco de dados
modelos.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="SUAS Saúde / Saúde +Fácil",
    description="Ecossistema integrado de saúde e regulação",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {
        "sistema": "SUAS Saúde / Saúde +Fácil",
        "status": "Operacional",
        "modulo": "Core API & Regulação"
    }

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
