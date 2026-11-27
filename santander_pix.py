import os
import time
import tempfile
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

router = APIRouter(prefix="/api/v1/santander", tags=["Santander Pix Sandbox"])


class CriarCobrancaPixRequest(BaseModel):
    unidade_id: str = Field(..., min_length=2, max_length=80)
    valor: float = Field(..., gt=0)
    descricao: str = Field(default="Adesao SUAS Saude +Facil", max_length=140)
    txid: str | None = Field(default=None, min_length=26, max_length=35)


class SantanderSandboxClient:
    def __init__(self) -> None:
        self.env = os.getenv("SANTANDER_ENV", "sandbox").strip().lower()
        self.client_id = os.getenv("SANTANDER_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("SANTANDER_CLIENT_SECRET", "").strip()
        self.chave_pix = os.getenv("SANTANDER_CHAVE_PIX", "").strip()
        # URLs confirmadas na documentação / tela da aplicação no portal do Santander
        self.token_url = os.getenv("SANTANDER_TOKEN_URL", "").strip()
        self.api_base_url = os.getenv("SANTANDER_API_BASE_URL", "").strip()
        self.scope = os.getenv("SANTANDER_SCOPE", "").strip()

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._cert_paths: tuple[str, str] | None = None

    def _carregar_mtls_cert(self) -> tuple[str, str] | None:
        """Cria arquivos temporários PEM para certificado e chave privada usados no mTLS."""
        if self._cert_paths:
            return self._cert_paths

        cert_pem = os.getenv("SANTANDER_CERT_PEM", "").strip()
        key_pem = os.getenv("SANTANDER_KEY_PEM", "").strip()
        if not cert_pem or not key_pem:
            return None

        cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        cert_file.write(cert_pem.replace("\\n", "\n").encode("utf-8"))
        cert_file.close()

        key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".key")
        key_file.write(key_pem.replace("\\n", "\n").encode("utf-8"))
        key_file.close()

        self._cert_paths = (cert_file.name, key_file.name)
        return self._cert_paths

    def validar_configuracao_basica(self) -> list[str]:
        faltando = []
        if not self.client_id:
            faltando.append("SANTANDER_CLIENT_ID")
        if not self.client_secret:
            faltando.append("SANTANDER_CLIENT_SECRET")
        if not self.token_url:
            faltando.append("SANTANDER_TOKEN_URL")
        if not self.api_base_url:
            faltando.append("SANTANDER_API_BASE_URL")
        return faltando

    async def obter_access_token(self) -> str:
        faltando = self.validar_configuracao_basica()
        if faltando:
            raise HTTPException(
                status_code=503,
                detail={
                    "erro": "Configuração incompleta no ambiente para conectar ao Santander.",
                    "variaveis_ausentes": faltando,
                },
            )

        agora = time.time()
        if self._access_token and agora < self._token_expires_at - 20:
            return self._access_token

        cert = self._carregar_mtls_cert()
        form_data: dict[str, str] = {"grant_type": "client_credentials"}
        if self.scope:
            form_data["scope"] = self.scope

        try:
            async with httpx.AsyncClient(cert=cert, timeout=20.0) as client:
                resp = await client.post(
                    self.token_url,
                    data=form_data,
                    auth=(self.client_id, self.client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "erro": "Falha na autenticação OAuth 2.0 com o Santander.",
                    "status_santander": exc.response.status_code,
                    "detalhe": exc.response.text[:400],
                },
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Erro de rede/mTLS ao solicitar token ao Santander: {exc}",
            ) from exc

        token = payload.get("access_token")
        if not token:
            raise HTTPException(
                status_code=502,
                detail="Resposta de token do Santander não conteve 'access_token'.",
            )

        expires_in = int(payload.get("expires_in", 300))
        self._access_token = token
        self._token_expires_at = agora + expires_in
        return token

    async def chamar_api(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self.obter_access_token()
        cert = self._carregar_mtls_cert()
        url = f"{self.api_base_url.rstrip('/')}/{path.lstrip('/')}"

        try:
            async with httpx.AsyncClient(cert=cert, timeout=20.0) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    json=json_body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                return resp.json() if resp.content else {"status": "ok"}
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "erro": "Erro retornado pela API do Santander.",
                    "status_santander": exc.response.status_code,
                    "detalhe": exc.response.text[:500],
                },
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Erro de conexão/mTLS na chamada à API do Santander: {exc}",
            ) from exc


santander_client = SantanderSandboxClient()


@router.get("/status-config")
async def status_config_santander():
    faltando = santander_client.validar_configuracao_basica()
    return {
        "ambiente": santander_client.env,
        "configurado": len(faltando) == 0,
        "mtls_cert_configurado": santander_client._carregar_mtls_cert() is not None,
        "chave_pix_configurada": bool(santander_client.chave_pix),
        "variaveis_ausentes": faltando,
    }


@router.post("/testar-token")
async def testar_token_santander():
    token = await santander_client.obter_access_token()
    return {
        "autenticado": True,
        "ambiente": santander_client.env,
        "token_preview": f"{token[:10]}...{token[-6:]}" if len(token) > 16 else "***",
    }


@router.post("/cob-pix")
async def criar_cobranca_pix_sandbox(dados: CriarCobrancaPixRequest):
    if not santander_client.chave_pix:
        raise HTTPException(
            status_code=503,
            detail="Variável SANTANDER_CHAVE_PIX não configurada no ambiente.",
        )

    txid = dados.txid or uuid.uuid4().hex
    body_cob = {
        "calendario": {"expiracao": 3600},
        "valor": {"original": f"{dados.valor:.2f}"},
        "chave": santander_client.chave_pix,
        "solicitacaoPagador": f"{dados.descricao} ({dados.unidade_id})"[:140],
    }

    # Caminho padrão de cobrança imediata Pix (/cob/{txid}); ajuste se a documentação da rota diferir
    resposta_santander = await santander_client.chamar_api("PUT", f"/cob/{txid}", json_body=body_cob)
    return {
        "unidade_id": dados.unidade_id,
        "txid": txid,
        "cobranca": resposta_santander,
    }


@router.post("/webhook/pix")
async def webhook_pix_santander(payload: dict[str, Any]):
    # Aqui você valida o evento recebido e atualiza a assinatura da unidade no seu banco
    return {
        "recebido": True,
        "eventos_count": len(payload.get("pix", [])) if isinstance(payload, dict) else 0,
    }
