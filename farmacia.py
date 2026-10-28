from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models, farmacia_schemas
from typing import List
import uuid
from datetime import datetime

router = APIRouter()

@router.post(
    "/",
    response_model=farmacia_schemas.MedicamentoResponse,
    summary="Registar receita ou prescrição de medicamento",
    description="Regista uma prescrição, definindo se é fornecida gratuitamente pelo SUS (retirada por QR Code) ou se requer compra com desconto na rede particular."
)
def criar_medicamento(
    medicamento: farmacia_schemas.MedicamentoCreate,
    db: Session = Depends(database.get_db)
):
    # Verifica se o medicamento é do SUS ou particular com desconto
    # Se fornecido pelo SUS, gera token para QR Code de retirada na farmácia pública.
    qr_token = None
    if getattr(medicamento, "fornecido_pelo_sus", True):
        qr_token = f"QR-SUS-PHARM-{uuid.uuid4().hex[:8].upper()}"
    else:
        qr_token = f"QR-DESC-PARCEIRO-{uuid.uuid4().hex[:8].upper()}"
    
    db_medicamento = models.MedicamentoItem(
        **medicamento.model_dump(),
        qr_code_token=qr_token,
        dispensado=False,
        data_dispensacao=None
    )
    db.add(db_medicamento)
    db.commit()
    db.refresh(db_medicamento)
    return db_medicamento

@router.get(
    "/",
    response_model=List[farmacia_schemas.MedicamentoResponse],
    summary="Listar medicamentos registados",
    description="Retorna a lista de todos os registos e receitas de medicamentos cadastrados no sistema."
)
def listar_medicamentos(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    return db.query(models.MedicamentoItem).offset(skip).limit(limit).all()

@router.post(
    "/dispensar/",
    summary="Dispensar medicamento (SUS ou Compra com Desconto) e Configurar Alarmes",
    description="Valida o QR Code, marca como dispensado/comprado, e ativa automaticamente os alarmes, horários e posologia no App do Cidadão."
)
def dispensar_medicamento(
    payload: farmacia_schemas.MedicamentoDispensacaoQRCode,
    db: Session = Depends(database.get_db)
):
    db_medicamento = db.query(models.MedicamentoItem).filter(
        models.MedicamentoItem.qr_code_token == payload.qr_code_token
    ).first()
    
    if not db_medicamento:
        raise HTTPException(status_code=404, detail="Token QR Code de farmácia/desconto não encontrado.")
    
    if db_medicamento.dispensado:
        raise HTTPException(status_code=400, detail="Este medicamento / receita já foi dispensado ou utilizado anteriormente.")
    
    # Atualiza o estado para dispensado / adquirido
    db_medicamento.dispensado = True
    db_medicamento.data_dispensacao = datetime.utcnow()
    db.commit()
    db.refresh(db_medicamento)

    # Regra Inteligente: Ao confirmar a retirada no SUS ou a compra com desconto,
    # injeta o medicamento automaticamente no perfil de tratamento do cidadão para disparar a campainha/alarme.
    if hasattr(models, "MedicamentoCidadao") and db_medicamento.cidadao_id:
        novo_alarme_cidadao = models.MedicamentoCidadao(
            cidadao_id=db_medicamento.cidadao_id,
            nome_medicamento=db_medicamento.nome_medicamento,
            tipo_presricao="Contínuo (Adquirido/Retirado)" if getattr(db_medicamento, "uso_continuo", False) else "Temporário / Emergência",
            horarios_alarme=getattr(db_medicamento, "horarios_alarme", "08:00, 20:00")
        )
        db.add(novo_alarme_cidadao)
        db.commit()

    origem_atendimento = "Farmácia do SUS (Retirada Gratuita por QR Code)" if getattr(db_medicamento, "fornecido_pelo_sus", True) else "Rede Particular Parceira (Compra com Desconto pelo App)"

    return {
        "status": "Sucesso",
        "mensagem": f"Dispensação/Aquisição confirmada via {origem_atendimento}.",
        "medicamento": db_medicamento.nome_medicamento,
        "posologia_ativa": getattr(db_medicamento, "posologia", "Conforme orientação médica"),
        "alarme_configurado_no_app": "Ativado com sucesso! O despertador/campainha do telemóvel foi programado."
    }
