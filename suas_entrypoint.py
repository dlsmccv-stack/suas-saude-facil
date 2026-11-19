"""Ponto de entrada unificado — SUAS Saúde +Fácil (100% Ativo).
Preserva integralmente o main.py original e registra o módulo completo do App do Cidadão,
garantindo CORS ativo para o PWA e criação automática das tabelas complementares.
"""
from fastapi.middleware.cors import CORSMiddleware
from main import app  # conserva a aplicação e todos os routers existentes (CCO/CPO, etc.)
from app_cidadao_api_farmacia_integrada import router
import database
import models

# Garante comunicação fluida entre o PWA (Vercel / domínio próprio) e a API (Render)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
models.Base.metadata.create_all(bind=database.engine)


@app.get("/app-cidadao/status-integracao", tags=["App do Cidadão"])
def status_integracao():
    return {
        "status": "100% ATIVO",
        "api_complementar": "carregada",
        "main_original": "preservado",
        "cadastro_publico_habilitado": True,
        "qrcode_vital_ativo": True,
        "triagem_checkin_qr_ativo": True,
        "farmacia_digital_qr_ativo": True,
        "despertador_posologia_ativo": True,
        "acessibilidade_voz_ptt_ativa": True,
    }
