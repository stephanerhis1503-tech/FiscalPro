"""Autorização OAuth local e segura para a Gmail API."""

from __future__ import annotations

from pathlib import Path
from typing import Any


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class DependenciasGmailAusentes(RuntimeError):
    """Bibliotecas oficiais do Google ainda não foram instaladas."""


class CredenciaisGmailInvalidas(RuntimeError):
    """Arquivo OAuth inexistente, inválido ou não autorizado."""


def _importar_google() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as erro:
        raise DependenciasGmailAusentes(
            "Instale as bibliotecas com: pip install -r requirements_robo_email.txt"
        ) from erro
    return Request, Credentials, InstalledAppFlow, build, HttpError


def criar_servico_gmail(caminho_credenciais: Path, caminho_token: Path):
    """Cria o cliente Gmail usando apenas permissão de leitura."""

    Request, Credentials, InstalledAppFlow, build, _ = _importar_google()

    if not caminho_credenciais.is_file():
        raise CredenciaisGmailInvalidas(
            "Selecione o arquivo JSON do tipo Aplicativo para computador baixado no Google Cloud."
        )

    credenciais = None
    if caminho_token.is_file():
        try:
            credenciais = Credentials.from_authorized_user_file(str(caminho_token), SCOPES)
        except (OSError, ValueError):
            caminho_token.unlink(missing_ok=True)

    if credenciais and credenciais.expired and credenciais.refresh_token:
        try:
            credenciais.refresh(Request())
        except Exception:
            caminho_token.unlink(missing_ok=True)
            credenciais = None

    if not credenciais or not credenciais.valid:
        try:
            fluxo = InstalledAppFlow.from_client_secrets_file(
                str(caminho_credenciais),
                SCOPES,
            )
            credenciais = fluxo.run_local_server(
                port=0,
                open_browser=True,
                authorization_prompt_message=(
                    "O navegador será aberto para autorizar o Robô FiscalPro no Gmail."
                ),
                success_message=(
                    "Autorização concluída. Você já pode fechar esta janela e voltar ao FiscalPro."
                ),
            )
        except Exception as erro:
            raise CredenciaisGmailInvalidas(
                f"Não foi possível autorizar o Gmail: {erro}"
            ) from erro

        caminho_token.parent.mkdir(parents=True, exist_ok=True)
        caminho_token.write_text(credenciais.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=credenciais, cache_discovery=False)
