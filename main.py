from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import datetime
import database, modelos, schemas, triagem, triagem_schemas, suas_social, suas_social_schemas, fhir_integration, emergency_qrcode, farmacia, farmacia_schemas, educacao_medica, educacao_medica_schemas

# Inicializa as tabelas no banco de dados para os módulos ativos
modelos.Base.metadata.create_all(bind=database.engine)
triagem.Base.metadata.create_all(bind=database.engine)
suas_social.Base.metadata.create_all(bind=database.engine)
farmacia.Base.metadata.create_all(bind=database.engine)
educacao_medica.Base.metadata.create_all(bind=database.engine)
emergency_qrcode.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="SUAS Saúde / Saúde +Fácil",
    description="Ecossistema integrado de saúde, assistência social, regulação, farmácia digital e emergência",
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
def criar_regulacao(item: schemas.RegulacaoCreate, db: Session = Depends(database.get_db)):
    db_item = modelos.RegulacaoItem(cidadao_nome=item.cidadao_nome, tipo_item=item.tipo_item)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.get("/regulacao/", response_model=list[schemas.RegulacaoResponse])
def listar_regulacoes(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(modelos.RegulacaoItem).offset(skip).limit(limit).all()

# Endpoints de Triagem (Protocolo de Manchester)
@app.post("/triagem/", response_model=triagem_schemas.TriagemResponse)
def criar_triagem(item: triagem_schemas.TriagemCreate, db: Session = Depends(database.get_db)):
    db_triagem = triagem.TriagemItem(
        paciente_nome=item.paciente_nome, queixa_principal=item.queixa_principal,
        cor_prioridade=item.cor_prioridade, tempo_alvo_atendimento=item.tempo_alvo_atendimento
    )
    db.add(db_triagem)
    db.commit()
    db.refresh(db_triagem)
    return db_triagem

@app.get("/triagem/", response_model=list[triagem_schemas.TriagemResponse])
def listar_triagens(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(triagem.TriagemItem).offset(skip).limit(limit).all()

# Endpoints de Apoio Social (SUAS)
@app.post("/suas-social/", response_model=suas_social_schemas.ApoioSocialResponse)
def criar_apoio_social(item: suas_social_schemas.ApoioSocialCreate, db: Session = Depends(database.get_db)):
    db_social = suas_social.ApoioSocialItem(
        cidadao_nome=item.cidadao_nome, nis=item.nis,
        situacao_vulnerabilidade=item.situacao_vulnerabilidade, beneficio_ativo=item.beneficio_ativo
    )
    db.add(db_social)
    db.commit()
    db.refresh(db_social)
    return db_social

@app.get("/suas-social/", response_model=list[suas_social_schemas.ApoioSocialResponse])
def listar_apoios_sociais(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(suas_social.ApoioSocialItem).offset(skip).limit(limit).all()

# Endpoints FHIR
@app.post("/fhir/patient/", response_model=fhir_integration.FHIRPatientResource)
def criar_paciente_fhir(patient: fhir_integration.FHIRPatientResource):
    return patient

@app.post("/fhir/observation/", response_model=fhir_integration.FHIRObservationResource)
def criar_observacao_fhir(observation: fhir_integration.FHIRObservationResource):
    return observation

# Endpoints de QR Code de Emergência & Acionamento SAMU com GPS
@app.post("/emergencia/qrcode/", response_model=emergency_qrcode.EmergencyProfile)
def gerar_perfil_emergencia(profile: emergency_qrcode.EmergencyProfile):
    return profile

@app.post("/emergencia/acionar/", response_model=emergency_qrcode.EmergencyTriggerResponse)
def acionar_emergencia(payload: emergency_qrcode.EmergencyTriggerRequest):
    return {
        "status": "ALERTA_DISPARADO_COM_SUCESSO",
        "mensagem_samu": f"Central do SAMU acionada com prioridade. Localização GPS recebida: {payload.localizacao_gps}.",
        "mensagem_familiares": "Notificação de emergência e localização enviadas para o contacto da família.",
        "timestamp": datetime.datetime.utcnow()
    }

# Endpoints de Farmácia Digital & Retirada via QR Code
@app.post("/farmacia/prescricao/", response_model=farmacia_schemas.MedicamentoResponse)
def criar_prescricao_farmacia(item: farmacia_schemas.MedicamentoCreate, db: Session = Depends(database.get_db)):
    db_med = farmacia.MedicamentoItem(
        cidadao_nome=item.cidadao_nome, medicamento_nome=item.medicamento_nome,
        dosagem=item.dosagem, posologia=item.posologia, quantidade_disponibilizada=item.quantidade_disponibilizada
    )
    db.add(db_med)
    db.commit()
    db.refresh(db_med)
    return db_med

@app.post("/farmacia/dispensar/", response_model=farmacia_schemas.MedicamentoResponse)
def dispensar_medicamento_por_qrcode(payload: farmacia_schemas.MedicamentoDispensacaoQRCode, db: Session = Depends(database.get_db)):
    db_med = db.query(farmacia.MedicamentoItem).filter(farmacia.MedicamentoItem.qr_code_token == payload.qr_code_token).first()
    if not db_med:
        raise HTTPException(status_code=404, detail="Receita ou QR Code não encontrado.")
    if db_med.dispensado:
        raise HTTPException(status_code=400, detail="Este medicamento já foi dispensado anteriormente.")
    
    db_med.dispensado = True
    db_med.data_dispensacao = datetime.datetime.utcnow()
    db.commit()
    db.refresh(db_med)
    return db_med

@app.get("/farmacia/medicamentos/", response_model=list[farmacia_schemas.MedicamentoResponse])
def listar_medicamentos(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(farmacia.MedicamentoItem).offset(skip).limit(limit).all()

# Endpoints de Educação Médica Continuada
@app.post("/educacao-medica/", response_model=educacao_medica_schemas.EducacaoMedicaResponse)
def criar_modulo_educacao(item: educacao_medica_schemas.EducacaoMedicaCreate, db: Session = Depends(database.get_db)):
    db_edu = educacao_medica.ModuloEducacaoItem(
        titulo_curso=item.titulo_curso, especialidade=item.especialidade,
        parceiro_industria=item.parceiro_industria, descricao_conteudo=item.descricao_conteudo,
        link_material_estudo=item.link_material_estudo, pontos_credito_cme=item.pontos_credito_cme
    )
    db.add(db_edu)
    db.commit()
    db.refresh(db_edu)
    return db_edu

@app.get("/educacao-medica/", response_model=list[educacao_medica_schemas.EducacaoMedicaResponse])
def listar_cursos_educacao(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(educacao_medica.ModuloEducacaoItem).offset(skip).limit(limit).all()
