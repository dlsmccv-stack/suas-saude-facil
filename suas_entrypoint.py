"""Ponto de entrada unificado — SUAS Saúde +Fácil (100% Ativo).
Preserva integralmente o main.py original e registra:
- App do Cidadão + Farmácia Digital
- Central SAMU 192 / CCO e Integração QR Code SOS
"""
from fastapi.middleware.cors import CORSMiddleware
from main import app
from app_cidadao_api_farmacia_integrada import router as cidadao_router
import database
import models
import suas_samu
import samu_integracoes

# Garante comunicação fluida entre Vercel, Base44 e a API no Render
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cidadao_router)
app.include_router(suas_samu.router)
app.include_router(samu_integracoes.router)

# Cria todas as tabelas (App do Cidadão + SAMU 192) no banco
models.Base.metadata.create_all(bind=database.engine)


@app.get("/app-cidadao/status-integracao", tags=["App do Cidadão"])
def status_integracao():
    return {
        "status": "100% ATIVO",
        "api_complementar": "carregada",
        "samu_192_cco": "ativo",
        "main_original": "preservado",
        "cadastro_publico_habilitado": True,
        "qrcode_vital_ativo": True,
        "triagem_checkin_qr_ativo": True,
        "farmacia_digital_qr_ativo": True,
        "despertador_posologia_ativo": True,
        "acessibilidade_voz_ptt_ativa": True,
    }
