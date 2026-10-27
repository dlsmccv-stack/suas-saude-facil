from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import database, modelos, schemas, triagem, triagem_schemas, suas_social, suas_social_schemas

# Inicializa as tabelas no banco de dados para todos os módulos
modelos.Base.metadata.create_all(bind=database.engine)
triagem.Base.metadata.create_all(bind=database.engine)
suas_social.Base.metadata.create_all(bind=database.engine)

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
        "modulos": ["Core API", "Regulação", "Triagem (Protocolo de Manchester)", "Apoio Social (SUAS)"]
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

# Endpoints de Apoio Social (SUAS)
@app.post("/suas-social/", response_model=suas_social_schemas.ApoioSocialResponse)
def criar_apoio_social(item: suas_social_schemas.ApoioSocialCreate, db: Session = Depends(database.get_db)):
    db_social = suas_social.ApoioSocialItem(
        cidadao_nome=item.cidadao_nome,
        nis=item.nis,
        situacao_vulnerabilidade=item.situacao_vulnerabilidade,
        beneficio_ativo=item.beneficio_ativo
    )
    db.add(db_social)
    db.commit()
    db.refresh(db_social)
    return db_social

@app.get("/suas-social/", response_model=list[suas_social_schemas.ApoioSocialResponse])
def listar_apoios_sociais(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    itens = db.query(suas_social.ApoioSocialItem).offset(skip).limit(limit).all()
    return itens
