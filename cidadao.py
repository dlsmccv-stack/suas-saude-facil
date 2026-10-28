from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import models
import schemas
from database import get_db
import json

router = APIRouter(prefix="/cidadao", tags=["App do Cidadão"])

@router.post("/onboarding", response_model=schemas.CidadaoResponse, summary="Registar Cidadão e Plano de Saúde")
def criar_cidadao(dados: schemas.CidadaoCreate, db: Session = Depends(get_db)):
    # Identificação automática da cobertura para direcionamento inteligente
    tipo_cobertura = None
    rede_credenciada = None
    
    if dados.possui_plano_saude:
        tipo_cobertura = "Hospitalar com Internação e Urgência"
        rede_credenciada = "Rede Particular Credenciada (Hospitais Privados Parceiros)"

    db_cidadao = models.CidadaoPerfil(
        **dados.model_dump(),
        tipo_cobertura=tipo_cobertura,
        rede_credenciada=rede_credenciada
    )
    db.add(db_cidadao)
    db.commit()
    db.refresh(db_cidadao)
    return db_cidadao

@router.post("/{cidadao_id}/medicamentos", response_model=schemas.MedicamentoCidadaoResponse, summary="Adicionar Medicamento (Contínuo ou Temporário com Campainha/Despertador)")
def adicionar_medicamento(cidadao_id: int, item: schemas.MedicamentoCidadaoCreate, db: Session = Depends(get_db)):
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    db_med = models.MedicamentoCidadao(
        cidadao_id=cidadao_id,
        **item.model_dump()
    )
    db.add(db_med)
    db.commit()
    db.refresh(db_med)
    return db_med

@router.post("/{cidadao_id}/automedicacao", summary="Registar Automedicação via Scanner e Acionar Alerta Preventivo")
def registar_automedicacao(cidadao_id: int, item: schemas.AutomedicacaoCreate, db: Session = Depends(get_db)):
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    log = models.AutomedicacaoLog(
        cidadao_id=cidadao_id,
        nome_medicamento=item.nome_medicamento,
        codigo_barras=item.codigo_barras,
        data_registo=datetime.utcnow()
    )
    db.add(log)
    db.commit()

    # Algoritmo de Inteligência Preventiva: Verificar frequência nos últimos 60 dias
    dois_meses_atras = datetime.utcnow() - timedelta(days=60)
    recorrencia = db.query(models.AutomedicacaoLog).filter(
        models.AutomedicacaoLog.cidadao_id == cidadao_id,
        models.AutomedicacaoLog.nome_medicamento == item.nome_medicamento,
        models.AutomedicacaoLog.data_registo >= dois_meses_atras
    ).count()

    alerta_preventivo = None
    if recorrencia >= 3:
        alerta_preventivo = f"Alerta Preventivo: Notamos um uso frequente de {item.nome_medicamento} nos últimos dois meses. Deseja agendar uma teleconsulta?"

    return {
        "status": "Registo efetuado com sucesso no Prontuário",
        "medicamento": item.nome_medicamento,
        "frequencia_recorrente": recorrencia,
        "alerta_preventivo": alerta_preventivo
    }

@router.get("/{cidadao_id}/qrcode-emergencia", summary="Gerar Dados para o QR Code de Emergência (Tela de Bloqueio e SAMU)")
def gerar_qrcode_emergencia(cidadao_id: int, db: Session = Depends(get_db)):
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    payload_emergencia = {
        "id": cidadao.id,
        "nome": cidadao.nome_completo,
        "cpf": cidadao.cpf,
        "tipo_sanguineo": cidadao.tipo_sanguineo,
        "alergias": cidadao.alergias or "Nenhuma registada",
        "condicoes_cronicas": cidadao.condicoes_cronicas or "Nenhuma",
        "contacto_responsavel": cidadao.contacto_responsavel,
        "plano_saude": {
            "possui": cidadao.possui_plano_saude,
            "operadora": cidadao.operadora_plano if cidadao.possui_plano_saude else "Não possui",
            "carteira": cidadao.numero_carteira if cidadao.possui_plano_saude else None,
            "cobertura": cidadao.tipo_cobertura if cidadao.possui_plano_saude else "SUS (Rede Pública)",
            "direcionamento": cidadao.rede_credenciada if cidadao.possui_plano_saude else "Encaminhar para Urgência SUS mais próxima"
        }
    }

    json_str = json.dumps(payload_emergencia, ensure_ascii=False)
    
    return {
        "status": "Sucesso",
        "instrucao_app": "Converta a string 'payload_qr' num gráfico de QR Code no front-end do aplicativo para exibição no perfil e na tela de bloqueio.",
        "payload_qr": json_str
    }
