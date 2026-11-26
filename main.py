from pathlib import Path

from ai_engine import PatientDataSchema, ai_predictor
import app_cidadao_api_farmacia_integrada
from b2b_api import b2b_router
import cco_cpo_external
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

import cidadao
import database
import educacao_medica
import emergency_qrcode
import farmacia
import fhir_integration
import laboratorio
import medico
import models
import regulacao
import suas_social
import triagem

# =====================================================
# MÓDULOS SUAS SAMU 192
# =====================================================

import suas_samu
import samu_integracoes


# =====================================================
# DIRETÓRIO PRINCIPAL DA APLICAÇÃO
# =====================================================

BASE_DIR = Path(__file__).resolve().parent


# =====================================================
# INICIALIZAÇÃO DAS TABELAS
# =====================================================

models.Base.metadata.create_all(bind=database.engine)


# =====================================================
# ATUALIZAÇÃO CONTROLADA DAS COLUNAS DE REGULAÇÃO
# =====================================================

with database.engine.begin() as conn:
    colunas_novas = [
        ("paciente_nome", "VARCHAR"),
        ("unidade_origem", "VARCHAR"),
        ("unidade_destino", "VARCHAR"),
        ("especialidade_solicitada", "VARCHAR"),
        ("prioridade_clinica", "VARCHAR DEFAULT 'Média'"),
        ("status_solicitacao", "VARCHAR DEFAULT 'Pendente'"),
        ("observacoes_medicas", "TEXT"),
        ("nis_vinculado", "VARCHAR"),
        ("vulnerabilidade_suas", "VARCHAR"),
        ("beneficio_social_ativo", "VARCHAR"),
        ("score_prioridade_intersetorial", "INTEGER DEFAULT 0"),
        ("justificativa_priorizacao", "TEXT"),
        ("acao_suas_vinculada", "VARCHAR"),
    ]

    inspector = inspect(conn)

    if inspector.has_table("regulacao_itens"):
        colunas_existentes = {
            coluna["name"]
            for coluna in inspector.get_columns("regulacao_itens")
        }

        for col_nome, col_tipo in colunas_novas:
            if col_nome not in colunas_existentes:
                conn.execute(
                    text(
                        f"ALTER TABLE regulacao_itens "
                        f"ADD COLUMN {col_nome} {col_tipo}"
                    )
                )


# =====================================================
# APLICAÇÃO PRINCIPAL FASTAPI
# =====================================================

app = FastAPI(
    title="SUAS Saúde / Saúde +Fácil",
    description="""
    ## Ecossistema Integrado de Saúde, Assistência Social e Inovação Tecnológica

    Esta API disponibiliza serviços operacionais para:

    * **App do Cidadão**: Onboarding, gestão de planos de saúde,
      alarmes de medicamentos (contínuos e temporários),
      scanner preventivo e QR Code de emergência/tela de bloqueio.

    * **Regulação**: Gestão centralizada de solicitações,
      leitos e encaminhamentos médicos com priorização
      intersetorial via SUAS.

    * **Painel do Médico**: Prescrições clínicas,
      geração de QR Code de farmácia e pedidos de regulação.

    * **Laboratório e Retornos**: Gestão de resultados de exames,
      notificações e agendamento automático de retorno.

    * **Triagem de Manchester**: Classificação de risco
      e priorização de atendimento.

    * **Assistência Social (SUAS)**: Registo e acompanhamento
      de cidadãos em situação de vulnerabilidade.

    * **Interoperabilidade FHIR**: Troca padronizada
      de dados de saúde (R4).

    * **QR Code de Emergência**: Acionamento rápido
      e suporte com dados clínicos críticos.

    * **Farmácia Digital**: Gestão e retirada
      de medicamentos por QR Code.

    * **Educação Médica**: Módulos de capacitação,
      formação continuada e créditos CME.

    * **CCO / CPO (Setor Externo Isolado)**:
      Canal seguro e segregado para reporte
      de ocorrências e gestão operacional descentralizada.

    * **SUAS SAMU 192**: API de registro de solicitações SOS,
      regulação médica, acompanhamento de ocorrências,
      gestão de ambulâncias e comunicação em tempo real.

    * **Integração SAMU e QR Code**:
      Registro de solicitação de socorro por QR Code
      e consulta de ficha clínica restrita aos
      profissionais autenticados.

    * **Interface Central SAMU 192**:
      Painel web de acompanhamento operacional,
      regulação e gestão de ocorrências.

    * **SUAS B2B & Interoperabilidade**:
      Endpoints comerciais, adesão/ativação de unidades e integração
      para hospitais, clínicas, farmácias e parceiros
      (/api/v1/assinaturas/adesao, /api/v1/assinaturas/confirmar-pagamento,
      /api/v1/clinical-events, /api/v1/predict-adverse-events,
      /api/v1/training-triggers, /api/v1/suporte/monitoramento e
      /api/v1/suporte/alerta-whatsapp).
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


# =====================================================
# CONFIGURAÇÃO CORS
# =====================================================

# Configuração provisória herdada do projeto.
# Antes da produção, restringir às origens autorizadas.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# ROTA PRINCIPAL
# =====================================================

@app.get("/", tags=["Início"])
def read_root():
    return {
        "sistema": "SUAS Saúde / Saúde +Fácil",
        "status": "Operacional",
        "modulos": [
            "Core API",
            "App do Cidadão (Plano de Saúde, Medicamentos & Preventivo)",
            "Painel do Médico (Prescrições & Regulação)",
            "Laboratório e Retornos Automáticos",
            "Regulação & Priorização Intersetorial SUAS",
            "Triagem (Protocolo de Manchester)",
            "Apoio Social (SUAS)",
            "Interoperabilidade FHIR",
            "QR Code de Emergência & Acionamento SAMU",
            "Farmácia Digital & Retirada por QR Code",
            "Educação Continuada & Indústria Farmacêutica",
            "Motor de IA Preditiva de Eventos Adversos",
            "CCO / CPO - Setor Externo Isolado",
            "SUAS SAMU 192 - API de Regulação de Urgências",
            "SUAS SAMU - Integração com QR Code e Ficha Clínica",
            "SUAS SAMU 192 - Interface Web da Central",
            "SUAS B2B & Interoperabilidade"
        ]
    }


# =====================================================
# REGISTRO DOS MÓDULOS EXISTENTES
# =====================================================

app.include_router(
    regulacao.router,
    prefix="/regulacao",
    tags=["Regulação"]
)

app.include_router(medico.router)

app.include_router(laboratorio.router)

app.include_router(
    triagem.router,
    prefix="/triagem",
    tags=["Triagem de Manchester"]
)

app.include_router(
    suas_social.router,
    prefix="/suas",
    tags=["Assistência Social (SUAS)"]
)

app.include_router(
    fhir_integration.router,
    prefix="/fhir",
    tags=["Interoperabilidade FHIR"]
)

app.include_router(
    emergency_qrcode.router,
    prefix="/emergencia",
    tags=["QR Code de Emergência"]
)

app.include_router(
    farmacia.router,
    prefix="/farmacia",
    tags=["Farmácia Digital"]
)

app.include_router(
    educacao_medica.router,
    prefix="/educacao",
    tags=["Educação Médica"]
)

app.include_router(cidadao.router)

app.include_router(app_cidadao_api_farmacia_integrada.router)

app.include_router(cco_cpo_external.router)

app.include_router(b2b_router)


# =====================================================
# CENTRAL SUAS SAMU 192 - API
# =====================================================

app.include_router(suas_samu.router)


# =====================================================
# INTEGRAÇÃO SAMU E QR CODE
# =====================================================

app.include_router(samu_integracoes.router)


# =====================================================
# INTERFACE WEB - APP DO CIDADÃO
# =====================================================

@app.get(
    "/app-cidadao",
    include_in_schema=False
)
@app.get(
    "/app-cidadao/",
    include_in_schema=False
)
def abrir_app_cidadao():
    arquivo = BASE_DIR / "app-cidadao" / "index.html"

    if not arquivo.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "Interface do App do Cidadão não encontrada. "
                "Verifique app-cidadao/index.html."
            )
        )

    return FileResponse(
        path=str(arquivo),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff"
        }
    )


# =====================================================
# INTERFACE WEB - CENTRAL SUAS SAMU 192
# =====================================================

@app.get(
    "/central-samu",
    include_in_schema=False
)
@app.get(
    "/central-samu/",
    include_in_schema=False
)
def abrir_central_samu():
    """
    Disponibiliza a interface HTML da Central SAMU.

    A autenticação das operações é realizada
    pelos endpoints protegidos da API.
    """

    arquivo = BASE_DIR / "central-samu" / "index.html"

    if not arquivo.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "Interface da Central SAMU não encontrada. "
                "Verifique central-samu/index.html."
            )
        )

    return FileResponse(
        path=str(arquivo),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff"
        }
    )


# =====================================================
# INTERFACE WEB - PAINEL B2B (HOSPITAIS / CLÍNICAS)
# =====================================================

@app.get(
    "/painel-b2b",
    include_in_schema=False
)
@app.get(
    "/painel-b2b/",
    include_in_schema=False
)
def abrir_painel_b2b():
    arquivo = BASE_DIR / "painel-b2b" / "index.html"

    if not arquivo.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "Interface do Painel B2B não encontrada. "
                "Verifique painel-b2b/index.html."
            )
        )

    return FileResponse(
        path=str(arquivo),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff"
        }
    )


# =====================================================
# INTERFACE WEB - LEARNING / ADESÃO B2B
# =====================================================

@app.get(
    "/learning",
    include_in_schema=False
)
@app.get(
    "/learning/",
    include_in_schema=False
)
def abrir_learning():
    arquivo = BASE_DIR / "learning.html"

    if not arquivo.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "Interface learning.html não encontrada."
            )
        )

    return FileResponse(
        path=str(arquivo),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff"
        }
    )


# =====================================================
# INTERFACE WEB - MONITORAMENTO & SUPORTE TI
# =====================================================

@app.get(
    "/monitoramento-ti",
    include_in_schema=False
)
@app.get(
    "/monitoramento-ti/",
    include_in_schema=False
)
def abrir_monitoramento_ti():
    arquivo = BASE_DIR / "monitoramento-ti" / "index.html"

    if not arquivo.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "Interface do Monitoramento TI não encontrada. "
                "Verifique monitoramento-ti/index.html."
            )
        )

    return FileResponse(
        path=str(arquivo),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff"
        }
    )


# =====================================================
# INTELIGÊNCIA ARTIFICIAL E FARMACOVIGILÂNCIA
# =====================================================

@app.post(
    "/api/v1/predict-adverse-event",
    tags=["Inteligência Preditiva (IA)"],
    summary=(
        "Avalia o risco de evento adverso no prontuário "
        "(parâmetros manuais)"
    )
)
def predict_adverse_event(
    patient_data: PatientDataSchema
):
    try:
        data_dict = patient_data.dict()

        resultado = ai_predictor.predict_risk(
            data_dict
        )

        return {
            "status": "sucesso",
            "dados_analisados": data_dict,
            "predicao": resultado
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                "Erro ao processar predição de IA: "
                f"{str(e)}"
            )
        )


# =====================================================
# ANÁLISE PREDITIVA INTEGRADA DO CIDADÃO
# =====================================================

@app.get(
    "/api/v1/predict-adverse-event/cidadao/{cidadao_id}",
    tags=["Inteligência Preditiva (IA)"],
    summary=(
        "Análise Preditiva Integrada do Cidadão "
        "(Medicamentos, Automedicação & Alergias)"
    )
)
def predict_adverse_event_cidadao(
    cidadao_id: int,
    idade: int = 55,
    db: Session = Depends(database.get_db)
):
    cidadao_obj = db.query(
        models.CidadaoPerfil
    ).filter(
        models.CidadaoPerfil.id == cidadao_id
    ).first()

    if not cidadao_obj:
        raise HTTPException(
            status_code=404,
            detail="Cidadão não encontrado."
        )

    medicamentos_app = db.query(
        models.MedicamentoCidadao
    ).filter(
        models.MedicamentoCidadao.cidadao_id == cidadao_id
    ).all()

    prescricoes_farmacia = db.query(
        models.MedicamentoItem
    ).filter(
        models.MedicamentoItem.cidadao_id == cidadao_id
    ).all()

    automedicacoes = db.query(
        models.AutomedicacaoLog
    ).filter(
        models.AutomedicacaoLog.cidadao_id == cidadao_id
    ).all()

    triagens = db.query(
        models.Triagem
    ).filter(
        models.Triagem.paciente_nome == cidadao_obj.nome_completo
    ).all()

    return ai_predictor.analisar_farmacovigilancia_cidadao(
        cidadao=cidadao_obj,
        medicamentos_app=medicamentos_app,
        prescricoes_farmacia=prescricoes_farmacia,
        automedicacoes=automedicacoes,
        triagens=triagens,
        idade_estimada=idade
    )
