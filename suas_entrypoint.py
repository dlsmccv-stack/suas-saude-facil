"""Ponto de entrada unificado — SUAS Saúde +Fácil (100% Ativo).
Preserva integralmente o main.py original e registra:
- App do Cidadão + Farmácia Digital
- Central SAMU 192 / CCO e Integração QR Code SOS
- Landing Page Institucional na rota raiz (/)
- Integração Pix / Sandbox Santander
"""
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from main import app
from app_cidadao_api_farmacia_integrada import router as cidadao_router
from santander_pix import router as santander_pix_router
import database
import models
import suas_samu
import samu_integracoes

BASE_DIR = Path(__file__).resolve().parent
LEARNING_HTML = BASE_DIR / "learning.html"

# Remove a rota "/" antiga importada do main.py para que a landing page assuma a raiz
app.router.routes = [
    route for route in app.router.routes
    if not (getattr(route, "path", None) == "/" and "GET" in getattr(route, "methods", set()))
]


@app.get("/", include_in_schema=False)
async def landing_page():
    if LEARNING_HTML.exists():
        return FileResponse(LEARNING_HTML, media_type="text/html; charset=utf-8")
    return JSONResponse(
        status_code=404,
        content={"detail": "Arquivo learning.html não encontrado na raiz do projeto."},
    )


@app.get("/api/status", tags=["Sistema"])
def sistema_status():
    return {
        "sistema": "SUAS Saúde / Saúde +Fácil",
        "status": "Operacional",
    }


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
app.include_router(santander_pix_router)

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
