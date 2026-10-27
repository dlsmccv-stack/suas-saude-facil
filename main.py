from fastapi import FastAPI

app = FastAPI(
    title="SUAS Saúde / Saúde +Fácil",
    description="Ecossistema integrado de saúde e assistência social",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {
        "sistema": "SUAS Saúde / Saúde +Fácil",
        "status": "Operacional",
        "modulo": "Core API & Interoperabilidade FHIR"
    }

@app.get("/saude")
def status_saude():
    return {
        "conexao": "Ativa",
        "regulacao": "Integrada (Óculos, Próteses e Aparelhos Auditivos)",
        "triagem": "Protocolo de Manchester Ativo"
    }
