"""Extração, validação e download seguro de links de documentos fiscais."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from email.message import Message
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .classificador import nome_seguro, normalizar_texto
from .config import DOMINIOS_RASTREADORES


PALAVRAS_DOCUMENTO = {
    "guia", "guias", "darf", "dae", "das", "gnre", "gps", "boleto",
    "tributo", "tributos", "imposto", "impostos", "icms", "inss", "fgts",
    "irpj", "csll", "pis", "cofins", "documento", "documentos", "download",
    "arquivo", "arquivos", "pdf", "competencia", "vencimento", "declaracao",
}

PALAVRAS_DESCARTAR = {
    "unsubscribe", "descadastrar", "cancelar-inscricao", "optout", "tracking",
    "tracker", "pixel", "beacon", "facebook", "instagram", "linkedin",
    "twitter", "x.com", "youtube", "whatsapp", "privacy", "privacidade",
    "terms", "termos", "view-in-browser", "ver-no-navegador",
}

EXTENSOES_DOCUMENTO = {".pdf", ".zip", ".xml"}
MIMES_DOCUMENTO = {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/xml",
    "text/xml",
}


@dataclass(slots=True, frozen=True)
class LinkEncontrado:
    url: str
    texto: str = ""
    origem: str = "texto"

    @property
    def dominio(self) -> str:
        return dominio_da_url(self.url) or ""


@dataclass(slots=True)
class ResultadoDownloadLink:
    status: str
    detalhe: str
    url_final: str = ""
    nome_arquivo: str = ""
    mime_type: str = ""
    dados: bytes = b""


class _ParserLinksHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[LinkEncontrado] = []
        self._href: str | None = None
        self._texto: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        atributos = {nome.casefold(): valor for nome, valor in attrs}
        href = atributos.get("href")
        if href:
            self._href = unescape(href.strip())
            self._texto = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._texto.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href is not None:
            texto = " ".join(" ".join(self._texto).split())
            self.links.append(LinkEncontrado(self._href, texto, "html"))
            self._href = None
            self._texto = []


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class BaixadorLinksSeguro:
    """Baixa somente HTTPS, domínio autorizado e conteúdo documental."""

    def __init__(
        self,
        dominios_confiaveis: Iterable[str],
        tamanho_maximo_mb: int = 25,
        timeout_segundos: int = 25,
    ) -> None:
        self.dominios_confiaveis = normalizar_lista_dominios(dominios_confiaveis)
        self.tamanho_maximo_bytes = int(tamanho_maximo_mb) * 1024 * 1024
        self.timeout_segundos = timeout_segundos
        self._opener = build_opener(_SemRedirecionamento())

    def dominio_confiavel(self, url: str) -> bool:
        host = dominio_da_url(url)
        return bool(host and dominio_esta_autorizado(host, self.dominios_confiaveis))

    def baixar(self, url: str) -> ResultadoDownloadLink:
        atual = normalizar_url(url)
        visitadas: set[str] = set()

        for _ in range(6):
            validacao = validar_url_segura(atual, self.dominios_confiaveis)
            if validacao:
                return ResultadoDownloadLink("BLOQUEADO", validacao, url_final=atual)
            if atual in visitadas:
                return ResultadoDownloadLink("ERRO", "Redirecionamento em ciclo.", url_final=atual)
            visitadas.add(atual)

            try:
                resposta = self._abrir(atual)
            except HTTPError as erro:
                if erro.code in {301, 302, 303, 307, 308}:
                    destino = erro.headers.get("Location", "")
                    if not destino:
                        return ResultadoDownloadLink(
                            "ERRO", f"Redirecionamento HTTP {erro.code} sem destino.", url_final=atual
                        )
                    atual = normalizar_url(urljoin(atual, destino))
                    continue
                if erro.code in {401, 403}:
                    return ResultadoDownloadLink(
                        "PENDENTE_ACESSO",
                        f"O portal exige autenticação ou autorização (HTTP {erro.code}).",
                        url_final=atual,
                    )
                return ResultadoDownloadLink(
                    "ERRO", f"O servidor respondeu HTTP {erro.code}.", url_final=atual
                )
            except (URLError, TimeoutError, OSError) as erro:
                return ResultadoDownloadLink("ERRO", f"Falha de conexão: {erro}", url_final=atual)

            with resposta:
                url_final = normalizar_url(resposta.geturl() or atual)
                validacao_final = validar_url_segura(url_final, self.dominios_confiaveis)
                if validacao_final:
                    return ResultadoDownloadLink("BLOQUEADO", validacao_final, url_final=url_final)

                content_length = resposta.headers.get("Content-Length")
                if content_length:
                    try:
                        tamanho = int(content_length)
                    except ValueError:
                        tamanho = 0
                    if tamanho > self.tamanho_maximo_bytes:
                        return ResultadoDownloadLink(
                            "BLOQUEADO",
                            f"Arquivo maior que o limite de {self.tamanho_maximo_bytes // (1024 * 1024)} MB.",
                            url_final=url_final,
                        )

                dados = resposta.read(self.tamanho_maximo_bytes + 1)
                if len(dados) > self.tamanho_maximo_bytes:
                    return ResultadoDownloadLink(
                        "BLOQUEADO",
                        f"Arquivo maior que o limite de {self.tamanho_maximo_bytes // (1024 * 1024)} MB.",
                        url_final=url_final,
                    )

                mime = (resposta.headers.get_content_type() or "").lower()
                if _parece_html(dados, mime):
                    return ResultadoDownloadLink(
                        "PENDENTE_ACESSO",
                        _mensagem_portal(url_final),
                        url_final=url_final,
                        mime_type=mime,
                    )

                tipo = identificar_tipo_documento(dados, mime, url_final)
                if not tipo:
                    return ResultadoDownloadLink(
                        "BLOQUEADO",
                        "O conteúdo recebido não foi reconhecido como PDF, ZIP ou XML.",
                        url_final=url_final,
                        mime_type=mime,
                    )

                nome = nome_arquivo_resposta(resposta.headers, url_final, tipo)
                return ResultadoDownloadLink(
                    "BAIXADO",
                    "Documento baixado com segurança.",
                    url_final=url_final,
                    nome_arquivo=nome,
                    mime_type=mime or tipo,
                    dados=dados,
                )

        return ResultadoDownloadLink("ERRO", "Quantidade máxima de redirecionamentos excedida.", url_final=atual)

    def _abrir(self, url: str):
        # A resolução é repetida imediatamente antes da requisição para reduzir
        # risco de acesso a endereços internos por DNS malicioso.
        host = dominio_da_url(url)
        if not host:
            raise OSError("Domínio ausente.")
        validar_ips_publicos(host)
        requisicao = Request(
            url,
            headers={
                "User-Agent": "FiscalPro-RoboFiscal/2.0",
                "Accept": "application/pdf, application/zip, application/xml, text/xml, application/octet-stream;q=0.8",
            },
            method="GET",
        )
        return self._opener.open(requisicao, timeout=self.timeout_segundos)


def extrair_links(
    corpo_texto: str = "",
    corpo_html: str = "",
    contexto_mensagem: str = "",
    limite: int = 50,
) -> list[LinkEncontrado]:
    encontrados: list[LinkEncontrado] = []

    if corpo_html:
        parser = _ParserLinksHTML()
        try:
            parser.feed(corpo_html)
            encontrados.extend(parser.links)
        except Exception:
            # Um HTML malformado não deve interromper o processamento do e-mail.
            pass

    padrao = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
    for url in padrao.findall(corpo_texto or ""):
        encontrados.append(LinkEncontrado(url, "", "texto"))

    resultado: list[LinkEncontrado] = []
    vistos: set[str] = set()
    for link in encontrados:
        url = normalizar_url(link.url)
        if not url or url in vistos:
            continue
        if not link_relevante(url, link.texto, contexto_mensagem):
            continue
        vistos.add(url)
        resultado.append(LinkEncontrado(url, link.texto, link.origem))
        if len(resultado) >= limite:
            break
    return resultado


def link_relevante(url: str, texto: str = "", contexto_mensagem: str = "") -> bool:
    dominio = dominio_da_url(url) or ""
    if any(dominio == item or dominio.endswith(f".{item}") for item in DOMINIOS_RASTREADORES):
        return False
    contexto_link = normalizar_texto(f"{url} {texto}")
    contexto_geral = normalizar_texto(contexto_mensagem)
    if any(palavra in contexto_link for palavra in PALAVRAS_DESCARTAR):
        return False

    caminho = Path(urlsplit(url).path)
    if caminho.suffix.lower() in EXTENSOES_DOCUMENTO:
        return True

    palavras_link = set(re.findall(r"[a-z0-9]+", contexto_link))
    if palavras_link.intersection(PALAVRAS_DOCUMENTO):
        return True
    palavras_gerais = set(re.findall(r"[a-z0-9]+", contexto_geral))
    return bool(palavras_gerais.intersection(PALAVRAS_DOCUMENTO))


def normalizar_url(url: str) -> str:
    url = unescape((url or "").strip())
    # Remove pontuação comum que costuma grudar no fim de links em texto puro.
    url = url.rstrip(".,;:!?)]}>\'\"")
    try:
        partes = urlsplit(url)
    except ValueError:
        return ""
    if partes.scheme.casefold() not in {"http", "https"}:
        return ""
    host = (partes.hostname or "").rstrip(".").lower()
    if not host:
        return ""
    try:
        host_ascii = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    try:
        porta = partes.port
    except ValueError:
        return ""
    netloc = host_ascii if porta is None else f"{host_ascii}:{porta}"
    caminho = partes.path or "/"
    return urlunsplit((partes.scheme.casefold(), netloc, caminho, partes.query, ""))


def dominio_da_url(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    if not host:
        return None
    try:
        return host.rstrip(".").lower().encode("idna").decode("ascii")
    except UnicodeError:
        return None


def normalizar_lista_dominios(dominios: Iterable[str]) -> tuple[str, ...]:
    resultado: list[str] = []
    for item in dominios:
        dominio = (item or "").strip().lower().rstrip(".")
        dominio = re.sub(r"^https?://", "", dominio).split("/", 1)[0]
        if dominio.startswith("www."):
            dominio = dominio[4:]
        try:
            dominio = dominio.encode("idna").decode("ascii")
        except UnicodeError:
            continue
        if dominio and dominio not in resultado:
            resultado.append(dominio)
    return tuple(resultado)


def dominio_esta_autorizado(host: str, dominios: Iterable[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == dominio or host.endswith(f".{dominio}") for dominio in dominios)


def validar_url_segura(url: str, dominios_confiaveis: Iterable[str]) -> str | None:
    try:
        partes = urlsplit(url)
    except ValueError:
        return "Endereço inválido."

    if partes.scheme.casefold() != "https":
        return "Somente links HTTPS podem ser baixados automaticamente."
    if partes.username or partes.password:
        return "Links com usuário ou senha embutidos são bloqueados."
    try:
        porta = partes.port
    except ValueError:
        return "Porta de rede inválida."
    if porta not in {None, 443}:
        return "Porta de rede não permitida para download automático."

    host = dominio_da_url(url)
    if not host:
        return "O link não possui um domínio válido."
    if host == "localhost" or host.endswith(".local"):
        return "Endereço local bloqueado."
    try:
        ipaddress.ip_address(host)
        return "Links apontando diretamente para endereço IP são bloqueados."
    except ValueError:
        pass

    if not dominio_esta_autorizado(host, dominios_confiaveis):
        return f"Domínio não autorizado: {host}"
    return None


def validar_ips_publicos(host: str) -> None:
    enderecos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not enderecos:
        raise OSError("O domínio não pôde ser resolvido.")
    for item in enderecos:
        ip_texto = item[4][0]
        ip = ipaddress.ip_address(ip_texto)
        if not ip.is_global:
            raise OSError("O domínio resolveu para um endereço de rede não público.")


def identificar_tipo_documento(dados: bytes, mime: str, url: str) -> str | None:
    inicio = dados[:1024].lstrip()
    if dados.startswith(b"%PDF-"):
        return "application/pdf"
    if dados.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "application/zip"
    if inicio.startswith(b"<?xml") or (
        inicio.startswith(b"<") and not inicio[:100].lower().startswith((b"<!doctype html", b"<html"))
    ):
        return "application/xml"

    extensao = Path(urlsplit(url).path).suffix.lower()
    if mime in MIMES_DOCUMENTO and extensao in EXTENSOES_DOCUMENTO:
        return mime
    return None


def nome_arquivo_resposta(headers, url: str, tipo: str) -> str:  # noqa: ANN001
    nome = ""
    content_disposition = headers.get("Content-Disposition", "")
    if content_disposition:
        mensagem = Message()
        mensagem["content-disposition"] = content_disposition
        nome = mensagem.get_filename() or ""

    if not nome:
        nome = unquote(Path(urlsplit(url).path).name)

    extensoes = {
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "application/xml": ".xml",
        "text/xml": ".xml",
    }
    extensao = extensoes.get(tipo, "")
    nome = nome_seguro(nome, f"guia{extensao}")
    if extensao and Path(nome).suffix.lower() not in EXTENSOES_DOCUMENTO:
        nome += extensao
    return nome



def _mensagem_portal(url: str) -> str:
    dominio = dominio_da_url(url) or ""
    if dominio == "nibo.com.br" or dominio.endswith(".nibo.com.br"):
        return (
            "O Nibo abriu o Portal do Cliente e exige acesso no navegador. "
            "Use o botão ‘Abrir e capturar download’ para entrar no Nibo, baixar a guia e arquivá-la no FiscalPro."
        )
    return "O link abriu uma página/portal, não um arquivo direto. Requer acesso manual."

def _parece_html(dados: bytes, mime: str) -> bool:
    inicio = dados[:1024].lstrip().lower()
    return "text/html" in mime or inicio.startswith((b"<!doctype html", b"<html"))
