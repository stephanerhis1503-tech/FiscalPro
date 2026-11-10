"""Autenticacao OAuth2 Client Credentials - Receita Integra (RTC/CBS).

Endpoint e formato conforme manual oficial da Receita/CGIBS:
POST https://api.receitafederal.gov.br/token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded
grant_type=client_credentials

NUNCA grava client_id, client_secret, Authorization ou access_token.
"""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)

TOKEN_URL = "https://api.receitafederal.gov.br/token"
LIMITE_RESPOSTA = 64 * 1024


class ErroAutenticacaoReceita(RuntimeError):
    """Falha de autenticacao com mensagem publica livre de credenciais."""


@dataclass(frozen=True)
class TokenTemporario:
    valor: str
    expira_em_segundos: int


class _ProibirRedirecionamentos(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ErroAutenticacaoReceita(
            "A Receita redirecionou a autenticacao; requisicao interrompida por seguranca."
        )


class AutenticadorReceitaIntegra:
    """Troca credenciais por token no HTTPS oficial; nao faz consultas tributarias."""

    def __init__(self, opener=None):
        self._opener = opener or build_opener(
            HTTPSHandler(context=ssl.create_default_context()),
            _ProibirRedirecionamentos(),
        )

    @staticmethod
    def _validar_credencial(valor: str, rotulo: str) -> str:
        valor = str(valor or "").strip()
        if not valor or len(valor) > 4096 or any(c in valor for c in "\r\n"):
            raise ValueError(f"{rotulo}: valor ausente ou invalido.")
        return valor

    def obter_token(self, client_id: str, client_secret: str) -> TokenTemporario:
        identificador = self._validar_credencial(client_id, "Client ID")
        segredo = self._validar_credencial(client_secret, "Client Secret")
        autenticacao = b64encode(f"{identificador}:{segredo}".encode("utf-8")).decode("ascii")
        requisicao = Request(
            TOKEN_URL,
            data=b"grant_type=client_credentials",
            headers={
                "Authorization": f"Basic {autenticacao}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener.open(requisicao, timeout=30) as resposta:
                if resposta.status != 200:
                    raise ErroAutenticacaoReceita(
                        f"Receita retornou HTTP {resposta.status} ao autenticar."
                    )
                dados = resposta.read(LIMITE_RESPOSTA + 1)
                if len(dados) > LIMITE_RESPOSTA:
                    raise ErroAutenticacaoReceita("Resposta de autenticacao acima do limite.")
                obj = json.loads(dados)
        except HTTPError as exc:
            # Nao incluir o corpo, headers, URL completa nem a credencial.
            if exc.code == 400:
                raise ErroAutenticacaoReceita(
                    "HTTP 400 (requisicao recusada). Confira se o Client ID e o "
                    "Client Secret foram copiados completos da mesma credencial; "
                    "uma troca de caracteres por leitura de imagem pode causar falha."
                ) from None
            if exc.code == 401:
                raise ErroAutenticacaoReceita(
                    "HTTP 401 (autenticacao recusada). Confira a validade e os "
                    "dados da credencial no portal da Receita. Nao envie as chaves "
                    "em mensagens ou capturas de tela."
                ) from None
            if exc.code == 403:
                raise ErroAutenticacaoReceita(
                    "HTTP 403 (acesso negado). Verifique no portal se a credencial "
                    "esta ativa e autorizada a acessar o servico de Apuracao CBS."
                ) from None
            raise ErroAutenticacaoReceita(
                f"Receita nao concluiu autenticacao: HTTP {exc.code}."
            ) from None
        except (URLError, OSError):
            raise ErroAutenticacaoReceita(
                "Nao foi possivel acessar o endpoint oficial de autenticacao da Receita."
            ) from None
        except (UnicodeError, json.JSONDecodeError):
            raise ErroAutenticacaoReceita(
                "Resposta de autenticacao nao e JSON valido."
            ) from None

        if not isinstance(obj, dict):
            raise ErroAutenticacaoReceita("Resposta de autenticacao invalida.")
        valor = obj.get("access_token")
        tipo = str(obj.get("token_type") or "").lower()
        validade = obj.get("expires_in")
        if (
            not isinstance(valor, str)
            or not valor.strip()
            or len(valor) > 16000
            or any(c.isspace() for c in valor)
            or tipo != "bearer"
            or isinstance(validade, bool)
        ):
            raise ErroAutenticacaoReceita("Resposta da Receita sem token Bearer valido.")
        try:
            segundos = int(validade)
        except (TypeError, ValueError):
            raise ErroAutenticacaoReceita("Duracao do token ausente ou invalida.") from None
        if not 30 <= segundos <= 86400:
            raise ErroAutenticacaoReceita("Duracao do token fora do intervalo esperado.")
        return TokenTemporario(valor=valor, expira_em_segundos=segundos)
