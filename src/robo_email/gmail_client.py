"""Leitura de mensagens, corpo e anexos pela Gmail API."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(slots=True)
class AnexoGmail:
    identificador: str
    nome: str
    mime_type: str
    dados_inline: str | None = None
    attachment_id: str | None = None


@dataclass(slots=True)
class MensagemGmail:
    id: str
    thread_id: str
    remetente: str
    destinatarios: str
    assunto: str
    data: datetime
    snippet: str
    corpo_texto: str
    corpo_html: str
    anexos: list[AnexoGmail]


class GmailClient:
    def __init__(self, servico):
        self.servico = servico

    def perfil(self) -> dict[str, Any]:
        return self.servico.users().getProfile(userId="me").execute()

    def listar_ids(self, consulta: str, limite: int) -> list[dict[str, str]]:
        mensagens: list[dict[str, str]] = []
        token: str | None = None

        while len(mensagens) < limite:
            quantidade = min(500, limite - len(mensagens))
            resposta = (
                self.servico.users()
                .messages()
                .list(
                    userId="me",
                    q=consulta,
                    maxResults=quantidade,
                    pageToken=token,
                )
                .execute()
            )
            mensagens.extend(resposta.get("messages", []))
            token = resposta.get("nextPageToken")
            if not token:
                break
        return mensagens[:limite]

    def obter_mensagem(self, mensagem_id: str) -> MensagemGmail:
        bruto = (
            self.servico.users()
            .messages()
            .get(userId="me", id=mensagem_id, format="full")
            .execute()
        )
        payload = bruto.get("payload", {})
        headers = self._headers(payload.get("headers", []))
        destinatarios = " | ".join(
            valor
            for valor in (
                headers.get("to", ""),
                headers.get("cc", ""),
                headers.get("delivered-to", ""),
                headers.get("x-original-to", ""),
            )
            if valor
        )

        interno = int(bruto.get("internalDate", "0") or 0)
        data = datetime.fromtimestamp(interno / 1000) if interno else datetime.now()
        textos, htmls = self._extrair_corpos(payload)

        return MensagemGmail(
            id=bruto["id"],
            thread_id=bruto.get("threadId", ""),
            remetente=headers.get("from", ""),
            destinatarios=destinatarios,
            assunto=headers.get("subject", "(sem assunto)"),
            data=data,
            snippet=bruto.get("snippet", ""),
            corpo_texto="\n".join(textos),
            corpo_html="\n".join(htmls),
            anexos=list(self._extrair_anexos(payload)),
        )

    def baixar_anexo(self, mensagem_id: str, anexo: AnexoGmail) -> bytes:
        dados = anexo.dados_inline
        if not dados and anexo.attachment_id:
            resposta = (
                self.servico.users()
                .messages()
                .attachments()
                .get(
                    userId="me",
                    messageId=mensagem_id,
                    id=anexo.attachment_id,
                )
                .execute()
            )
            dados = resposta.get("data")

        if not dados:
            return b""
        return self._decodificar_base64(dados)

    @staticmethod
    def _headers(headers: Iterable[dict[str, str]]) -> dict[str, str]:
        return {
            item.get("name", "").lower(): item.get("value", "")
            for item in headers
            if item.get("name")
        }

    def _extrair_anexos(self, parte: dict[str, Any]) -> Iterable[AnexoGmail]:
        nome = parte.get("filename", "")
        corpo = parte.get("body", {})
        if nome:
            identificador = corpo.get("attachmentId") or f"inline:{nome}:{corpo.get('size', 0)}"
            yield AnexoGmail(
                identificador=identificador,
                nome=nome,
                mime_type=parte.get("mimeType", "application/octet-stream"),
                dados_inline=corpo.get("data"),
                attachment_id=corpo.get("attachmentId"),
            )

        for filha in parte.get("parts", []) or []:
            yield from self._extrair_anexos(filha)

    def _extrair_corpos(self, parte: dict[str, Any]) -> tuple[list[str], list[str]]:
        textos: list[str] = []
        htmls: list[str] = []

        def percorrer(item: dict[str, Any]) -> None:
            mime_type = (item.get("mimeType") or "").lower()
            nome = item.get("filename") or ""
            corpo = item.get("body", {}) or {}
            dados = corpo.get("data")

            # Não lê anexos nomeados como corpo da mensagem.
            if not nome and dados and mime_type in {"text/plain", "text/html"}:
                bruto = self._decodificar_base64(dados)
                texto = self._decodificar_texto(bruto)
                if mime_type == "text/html":
                    htmls.append(texto)
                else:
                    textos.append(texto)

            for filha in item.get("parts", []) or []:
                percorrer(filha)

        percorrer(parte)
        return textos, htmls

    @staticmethod
    def _decodificar_base64(dados: str) -> bytes:
        if not dados:
            return b""
        # A API usa base64url e pode omitir o preenchimento final.
        faltante = len(dados) % 4
        if faltante:
            dados += "=" * (4 - faltante)
        return base64.urlsafe_b64decode(dados.encode("ascii"))

    @staticmethod
    def _decodificar_texto(dados: bytes) -> str:
        for codificacao in ("utf-8", "latin-1"):
            try:
                return dados.decode(codificacao)
            except UnicodeDecodeError:
                continue
        return dados.decode("utf-8", errors="replace")
