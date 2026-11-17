from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
import database, models, regulacao_schemas
from typing import List
from datetime import datetime

router = APIRouter()


def calcular_prioridade_intersetorial(
    nome_paciente: str,
    prioridade_clinica: str,
    db: Session
) -> dict:
    """
    Cruza dados clínicos (prioridade médica, triagem de Manchester e prontuário)
    com registros de vulnerabilidade do SUAS (CRAS/CREAS, NIS e benefícios)
    para calcular o Score de Prioridade Intersetorial (0 a 100).
    """
    score = 0
    motivos = []
    nome_busca = (nome_paciente or "").strip()

    # 1. Peso da Prioridade Clínica Solicitada (até 35 pts)
    prio_lower = (prioridade_clinica or "").lower()
    if "alta" in prio_lower or "urgente" in prio_lower:
        score += 35
        motivos.append("Prioridade clínica Alta (+35 pts)")
    elif "média" in prio_lower or "media" in prio_lower:
        score += 20
        motivos.append("Prioridade clínica Média (+20 pts)")
    else:
        score += 10
        motivos.append("Prioridade clínica Eletiva/Baixa (+10 pts)")

    # 2. Peso da Triagem de Manchester (até 15 pts)
    ultima_triagem = (
        db.query(models.Triagem)
        .filter(func.lower(models.Triagem.paciente_nome) == nome_busca.lower())
        .order_by(models.Triagem.id.desc())
        .first()
    )
    if ultima_triagem:
        cor = (ultima_triagem.cor_prioridade or "").lower()
        if "vermelho" in cor or "laranja" in cor:
            score += 15
            motivos.append(f"Triagem Manchester {ultima_triagem.cor_prioridade} (+15 pts)")
        elif "amarelo" in cor:
            score += 10
            motivos.append("Triagem Manchester Amarelo (+10 pts)")

    # 3. Peso da Vulnerabilidade Social - SUAS (até 40 pts)
    registro_suas = (
        db.query(models.SuasSocial)
        .filter(func.lower(models.SuasSocial.cidadao_nome) == nome_busca.lower())
        .order_by(models.SuasSocial.id.desc())
        .first()
    )
    nis_vinculado = None
    vulnerabilidade_suas = None
    beneficio_ativo = None

    if registro_suas:
        nis_vinculado = registro_suas.nis
        vulnerabilidade_suas = registro_suas.situacao_vulnerabilidade
        beneficio_ativo = registro_suas.beneficio_ativo
        vuln_lower = (registro_suas.situacao_vulnerabilidade or "").lower()

        if any(k in vuln_lower for k in ["extrema", "rua", "grave", "risco social", "abandono"]):
            score += 30
            motivos.append(f"SUAS: {registro_suas.situacao_vulnerabilidade} (+30 pts)")
        else:
            score += 20
            motivos.append(f"SUAS: {registro_suas.situacao_vulnerabilidade} (+20 pts)")

        if (registro_suas.beneficio_ativo or "").lower() in ["sim", "ativo", "bpc", "bolsa familia", "bolsa família"]:
            score += 10
            motivos.append(f"Benefício social ativo / NIS {registro_suas.nis} (+10 pts)")

    # 4. Peso de Comorbidades / Alergias no App do Cidadão (até 10 pts)
    perfil_cidadao = (
        db.query(models.CidadaoPerfil)
        .filter(func.lower(models.CidadaoPerfil.nome_completo) == nome_busca.lower())
        .first()
    )
    if perfil_cidadao and (perfil_cidadao.condicoes_cronicas or perfil_cidadao.alergias):
        score += 10
        motivos.append("Condição crônica/alergia registada no prontuário (+10 pts)")

    return {
        "score": min(100, score),
        "nis_vinculado": nis_vinculado,
        "vulnerabilidade_suas": vulnerabilidade_suas or "Sem vínculo SUAS registado",
        "beneficio_social_ativo": beneficio_ativo or "Não informado",
        "justificativa": " | ".join(motivos)
    }


def normalizar_item_legado(item: models.RegulacaoItem) -> models.RegulacaoItem:
    """Garante compatibilidade com registros antigos criados pelo painel médico."""
    if not item.paciente_nome and item.cidadao_nome:
        item.paciente_nome = item.cidadao_nome
    if not item.especialidade_solicitada and item.tipo_item:
        item.especialidade_solicitada = item.tipo_item
    if not item.unidade_origem:
        item.unidade_origem = "Rede Básica / Consultório"
    if not item.unidade_destino:
        item.unidade_destino = "Central de Regulação Municipal"
    if not item.prioridade_clinica:
        item.prioridade_clinica = "Média"
    if not item.status_solicitacao:
        item.status_solicitacao = item.status or "Pendente"
    if item.score_prioridade_intersetorial is None:
        item.score_prioridade_intersetorial = 0
    return item


@router.post(
    "/",
    response_model=regulacao_schemas.RegulacaoResponse,
    summary="Solicitar Regulação de Vaga/Leito (com Priorização Automática SUAS)",
    description="Cria um novo pedido de regulação e calcula automaticamente o Score de Prioridade Intersetorial cruzando dados clínicos e do SUAS."
)
def criar_solicitacao_regulacao(
    solicitacao: regulacao_schemas.RegulacaoCreate,
    db: Session = Depends(database.get_db)
):
    analise = calcular_prioridade_intersetorial(
        nome_paciente=solicitacao.paciente_nome,
        prioridade_clinica=solicitacao.prioridade_clinica,
        db=db
    )

    db_regulacao = models.RegulacaoItem(
        cidadao_nome=solicitacao.paciente_nome,
        tipo_item=solicitacao.especialidade_solicitada,
        status="Pendente",
        paciente_nome=solicitacao.paciente_nome,
        unidade_origem=solicitacao.unidade_origem,
        unidade_destino=solicitacao.unidade_destino,
        especialidade_solicitada=solicitacao.especialidade_solicitada,
        prioridade_clinica=solicitacao.prioridade_clinica,
        status_solicitacao="Pendente",
        observacoes_medicas=solicitacao.observacoes_medicas,
        nis_vinculado=analise["nis_vinculado"],
        vulnerabilidade_suas=analise["vulnerabilidade_suas"],
        beneficio_social_ativo=analise["beneficio_social_ativo"],
        score_prioridade_intersetorial=analise["score"],
        justificativa_priorizacao=analise["justificativa"],
        data_solicitacao=datetime.utcnow()
    )
    db.add(db_regulacao)
    db.commit()
    db.refresh(db_regulacao)
    return normalizar_item_legado(db_regulacao)


@router.get(
    "/",
    response_model=List[regulacao_schemas.RegulacaoResponse],
    summary="Listar Solicitações de Regulação",
    description="Retorna a lista de todas as solicitações de regulação e insumos cadastradas."
)
def listar_solicitacoes_regulacao(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    itens = db.query(models.RegulacaoItem).offset(skip).limit(limit).all()
    return [normalizar_item_legado(i) for i in itens]


@router.get(
    "/fila-priorizada-suas",
    response_model=List[regulacao_schemas.RegulacaoResponse],
    summary="Fila de Regulação Ordenada por Vulnerabilidade Social (SUAS) + Risco Clínico",
    description="Recalcula e ordena dinamicamente todas as solicitações pendentes pelo Score Intersetorial (Saúde + Assistência Social)."
)
def listar_fila_priorizada_suas(db: Session = Depends(database.get_db)):
    itens = db.query(models.RegulacaoItem).all()
    resultado = []

    for item in itens:
        item = normalizar_item_legado(item)
        analise = calcular_prioridade_intersetorial(
            nome_paciente=item.paciente_nome,
            prioridade_clinica=item.prioridade_clinica,
            db=db
        )
        item.nis_vinculado = analise["nis_vinculado"]
        item.vulnerabilidade_suas = analise["vulnerabilidade_suas"]
        item.beneficio_social_ativo = analise["beneficio_social_ativo"]
        item.score_prioridade_intersetorial = analise["score"]
        item.justificativa_priorizacao = analise["justificativa"]
        resultado.append(item)

    db.commit()
    resultado.sort(key=lambda x: x.score_prioridade_intersetorial, reverse=True)
    return resultado


@router.post(
    "/{solicitacao_id}/acionar-suas",
    summary="Acionar Contrarreferência Social (CRAS/CREAS) para Vaga Regulada",
    description="Vincula um pedido de apoio socioassistencial (ex: transporte sanitário, cesta básica ou visita domiciliar) diretamente à solicitação de regulação."
)
def acionar_suas_para_regulacao(
    solicitacao_id: int,
    payload: regulacao_schemas.AcionarSuasPayload,
    db: Session = Depends(database.get_db)
):
    item = db.query(models.RegulacaoItem).filter(models.RegulacaoItem.id == solicitacao_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Solicitação de regulação não encontrada.")

    item = normalizar_item_legado(item)
    acao_texto = f"{payload.tipo_apoio_social} ({payload.equipamento_destino})"
    item.acao_suas_vinculada = acao_texto

    # Se o cidadão ainda não tinha cadastro no SUAS, cria um encaminhamento automático
    registro_existente = (
        db.query(models.SuasSocial)
        .filter(func.lower(models.SuasSocial.cidadao_nome) == (item.paciente_nome or "").lower())
        .first()
    )
    if not registro_existente:
        novo_suas = models.SuasSocial(
            cidadao_nome=item.paciente_nome,
            nis=item.nis_vinculado or "Aguardando Cadastro Único",
            situacao_vulnerabilidade=f"Encaminhado pela Regulação Saúde: {payload.tipo_apoio_social}",
            beneficio_ativo="Em avaliação CRAS"
        )
        db.add(novo_suas)

    db.commit()
    db.refresh(item)

    return {
        "status": "Contrarreferência Saúde -> SUAS registada com sucesso",
        "regulacao_id": item.id,
        "paciente_nome": item.paciente_nome,
        "acao_suas_vinculada": item.acao_suas_vinculada,
        "observacao_social": payload.observacao_social,
        "score_prioridade_atualizado": item.score_prioridade_intersetorial
    }
