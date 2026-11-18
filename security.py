
import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

external_token_header = APIKeyHeader(
    name="X-External-Token",
    auto_error=False
)


def validar_token_externo(
    token: str = Security(external_token_header)
):
    token_configurado = os.getenv(
        "SUAS_EXTERNAL_API_TOKEN"
    )

    if not token_configurado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticação externa não configurada."
        )

    if not token or not secrets.compare_digest(
        token,
        token_configurado
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso inválido ou ausente.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    return True
