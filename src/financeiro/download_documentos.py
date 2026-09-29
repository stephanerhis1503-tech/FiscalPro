"""Download em lote de documentos compartilhados pelo Adobe Acrobat.

Versões 17.8.103/17.8.107:
- extrai links do Adobe Acrobat colados de mensagens do WhatsApp;
- tenta resolver links de compartilhamento para PDF/imagem usando apenas a biblioteca padrão;
- salva os arquivos na pasta escolhida pela usuária; se nenhuma for informada, usa ``dados/financeiro/recebidos/AAAA-MM``;
- gera relatório de sucesso/falha sem interromper o lote quando um link exige abertura manual.

O resolvedor é deliberadamente conservador: ele só aceita links iniciais de domínios Adobe
suportados e só grava respostas que sejam de fato PDF ou imagem. Links que dependem de uma
sessão/login ou de JavaScript específico do navegador ficam marcados como MANUAL.
"""

from __future__ import annotations

import html
import json
import mimetypes
import re
import time
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


DOMINIOS_ADOBE_INICIAIS = {
    "acrobat.adobe.com",
    "documentcloud.adobe.com",
}

# CDNs/serviços que podem aparecer dentro da própria página de compartilhamento.
# A URL candidata só é usada depois de ter sido extraída da página Adobe recebida.
DOMINIOS_CANDIDATOS_ADOBE = (
    "adobe.com",
    "adobe.io",
    "adobelogin.com",
    "acrobat.com",
)

TIPOS_ACEITOS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

MAX_PAGINA_HTML = 8 * 1024 * 1024
MAX_DOCUMENTO = 80 * 1024 * 1024


@dataclass(frozen=True)
class ResultadoLinkDownload:
    indice: int
    url: str
    status: str  # OK, MANUAL ou ERRO
    caminho: Path | None
    mensagem: str


@dataclass(frozen=True)
class ResultadoLoteDownload:
    pasta: Path
    total_links: int
    baixados: int
    manuais: int
    erros: int
    resultados: tuple[ResultadoLinkDownload, ...]
    relatorio: Path


class BaixadorDocumentosAdobe:
    """Extrai e baixa documentos de links compartilhados pelo Acrobat."""

    _regex_url = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

    def __init__(self, pasta_financeiro: str | Path):
        self.pasta_financeiro = Path(pasta_financeiro).expanduser().resolve()
        self.pasta_recebidos = self.pasta_financeiro / "recebidos"

    @classmethod
    def extrair_links(cls, texto: str) -> tuple[str, ...]:
        """Extrai links Adobe de um texto, preservando a ordem e removendo duplicados."""

        encontrados: list[str] = []
        vistos: set[str] = set()
        for bruto in cls._regex_url.findall(html.unescape(texto or "")):
            url = bruto.strip().rstrip(".,;:!?)]}>'\"")
            try:
                partes = urlsplit(url)
            except ValueError:
                continue
            host = (partes.hostname or "").casefold()
            if host not in DOMINIOS_ADOBE_INICIAIS:
                continue
            chave = url.casefold()
            if chave in vistos:
                continue
            vistos.add(chave)
            encontrados.append(url)
        return tuple(encontrados)

    def pasta_competencia(self, competencia: str) -> Path:
        if not re.fullmatch(r"\d{4}-\d{2}", competencia or ""):
            raise ValueError("Competência inválida para receber os documentos.")
        pasta = self.pasta_recebidos / competencia
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    @staticmethod
    def _opener():
        cookies = CookieJar()
        return build_opener(HTTPCookieProcessor(cookies))

    @staticmethod
    def _headers(referer: str = "") -> dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
            ),
            "Accept": "application/pdf,image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    @staticmethod
    def _ler_limitado(resposta, limite: int) -> bytes:
        partes: list[bytes] = []
        total = 0
        while True:
            bloco = resposta.read(min(1024 * 1024, limite - total + 1))
            if not bloco:
                break
            partes.append(bloco)
            total += len(bloco)
            if total > limite:
                raise ValueError("O arquivo retornado é maior que o limite de segurança do FiscalPro.")
        return b"".join(partes)

    @staticmethod
    def _tipo_documento(content_type: str, dados: bytes) -> tuple[str, str] | None:
        tipo = (content_type or "").split(";", 1)[0].strip().casefold()
        if dados.startswith(b"%PDF-"):
            return "application/pdf", ".pdf"
        if dados.startswith(b"\xff\xd8\xff"):
            return "image/jpeg", ".jpg"
        if dados.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png", ".png"
        if len(dados) >= 12 and dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
            return "image/webp", ".webp"
        if tipo in TIPOS_ACEITOS:
            return tipo, TIPOS_ACEITOS[tipo]
        return None

    @staticmethod
    def _nome_disposition(disposition: str) -> str:
        texto = disposition or ""
        m = re.search(r"filename\*=UTF-8''([^;]+)", texto, re.IGNORECASE)
        if m:
            return unquote(m.group(1)).strip().strip('"')
        m = re.search(r'filename\s*=\s*"([^"]+)"', texto, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r"filename\s*=\s*([^;]+)", texto, re.IGNORECASE)
        return m.group(1).strip().strip('"') if m else ""

    @staticmethod
    def _nome_seguro(nome: str) -> str:
        base = Path(nome or "").name
        base = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", base).strip(" ._")
        base = re.sub(r"\s+", " ", base)
        return base[:120] if base else ""

    def _destino_unico(
        self,
        pasta: Path,
        *,
        indice: int,
        extensao: str,
        nome_sugerido: str = "",
    ) -> Path:
        nome = self._nome_seguro(nome_sugerido)
        if nome:
            atual = Path(nome)
            if atual.suffix.casefold() not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
                nome = atual.stem + extensao
        else:
            nome = f"ADOBE_{indice:03d}{extensao}"

        destino = pasta / nome
        contador = 2
        while destino.exists():
            destino = pasta / f"{Path(nome).stem}_{contador}{Path(nome).suffix}"
            contador += 1
        return destino

    @staticmethod
    def _desescapar_url(valor: str) -> str:
        texto = html.unescape(valor or "")
        texto = texto.replace("\\/", "/")

        def repl(match: re.Match[str]) -> str:
            try:
                return chr(int(match.group(1), 16))
            except ValueError:
                return match.group(0)

        texto = re.sub(r"\\u([0-9a-fA-F]{4})", repl, texto)
        return texto.strip().strip('"\'')

    @classmethod
    def _candidatos_html(cls, html_texto: str, pagina_url: str) -> tuple[str, ...]:
        """Encontra URLs com chance razoável de apontarem para o documento."""

        texto = html.unescape(html_texto or "")
        coletados: list[tuple[int, str]] = []

        padroes_prioritarios = [
            r'(?i)"(?:downloadUrl|downloadURL|downloadUri|downloadURI|assetUrl|assetURL|fileUrl|fileURL|contentUrl|contentURL)"\s*:\s*"([^"]+)"',
            r"(?i)(?:href|src|data-url|data-download-url)\s*=\s*['\"]([^'\"]+)['\"]",
        ]
        for prioridade, padrao in enumerate(padroes_prioritarios):
            for m in re.finditer(padrao, texto):
                coletados.append((prioridade, m.group(1)))

        # Fallback: URLs presentes nos scripts. Recebem prioridade menor.
        for m in re.finditer(r"https?:\\?/\\?/[^\s\"'<>]+", texto, re.IGNORECASE):
            coletados.append((5, m.group(0)))

        candidatos: list[tuple[int, int, str]] = []
        vistos: set[str] = set()
        for prioridade, bruto in coletados:
            valor = cls._desescapar_url(bruto)
            if not valor:
                continue
            absoluto = urljoin(pagina_url, valor)
            try:
                p = urlsplit(absoluto)
            except ValueError:
                continue
            if p.scheme not in {"http", "https"} or not p.hostname:
                continue
            host = p.hostname.casefold()
            if not any(host == d or host.endswith("." + d) for d in DOMINIOS_CANDIDATOS_ADOBE):
                continue
            chave = absoluto.casefold()
            if chave in vistos or absoluto == pagina_url:
                continue
            vistos.add(chave)

            baixo = absoluto.casefold()
            bonus = 0
            if ".pdf" in baixo:
                bonus -= 5
            if any(palavra in baixo for palavra in ("download", "asset", "content", "document", "file")):
                bonus -= 3
            if any(palavra in baixo for palavra in ("analytics", "track", "pixel", "telemetry", "favicon", ".js", ".css")):
                bonus += 10
            candidatos.append((prioridade, bonus, absoluto))

        candidatos.sort(key=lambda item: (item[0] + item[1], item[0]))
        return tuple(url for _, _, url in candidatos[:20])

    def _baixar_resposta_documento(
        self,
        opener,
        url: str,
        *,
        referer: str = "",
        timeout: int = 25,
    ) -> tuple[bytes, str, str, str] | None:
        req = Request(url, headers=self._headers(referer))
        with opener.open(req, timeout=timeout) as resposta:
            content_type = resposta.headers.get("Content-Type", "")
            content_length = resposta.headers.get("Content-Length", "")
            try:
                if content_length and int(content_length) > MAX_DOCUMENTO:
                    raise ValueError("O documento ultrapassa 80 MB.")
            except ValueError:
                if content_length and content_length.isdigit():
                    raise
            dados = self._ler_limitado(resposta, MAX_DOCUMENTO)
            tipo = self._tipo_documento(content_type, dados)
            if not tipo:
                return None
            _, extensao = tipo
            nome = self._nome_disposition(resposta.headers.get("Content-Disposition", ""))
            return dados, extensao, nome, resposta.geturl()

    def _baixar_um(self, url: str, pasta: Path, indice: int, timeout: int) -> ResultadoLinkDownload:
        opener = self._opener()
        try:
            # Primeiro acesso: pode ser o PDF em si ou a página de compartilhamento.
            req = Request(url, headers=self._headers())
            with opener.open(req, timeout=timeout) as resposta:
                final_url = resposta.geturl()
                content_type = resposta.headers.get("Content-Type", "")
                content_length = resposta.headers.get("Content-Length", "")
                tipo_base = (content_type or "").split(";", 1)[0].strip().casefold()
                limite = MAX_DOCUMENTO if tipo_base in TIPOS_ACEITOS else MAX_PAGINA_HTML
                try:
                    if content_length and int(content_length) > limite:
                        raise ValueError("A página/arquivo retornado é grande demais para o download automático.")
                except ValueError:
                    if content_length and content_length.isdigit():
                        raise
                dados = self._ler_limitado(resposta, limite)
                tipo = self._tipo_documento(content_type, dados)
                if tipo:
                    _, extensao = tipo
                    nome = self._nome_disposition(resposta.headers.get("Content-Disposition", ""))
                    destino = self._destino_unico(
                        pasta, indice=indice, extensao=extensao, nome_sugerido=nome
                    )
                    destino.write_bytes(dados)
                    return ResultadoLinkDownload(indice, url, "OK", destino, "Baixado diretamente.")

            # Página HTML: procura dentro dela URLs de download/asset.
            texto = dados.decode("utf-8", errors="replace")
            candidatos = self._candidatos_html(texto, final_url)
            for candidato in candidatos:
                try:
                    obtido = self._baixar_resposta_documento(
                        opener, candidato, referer=final_url, timeout=timeout
                    )
                except (HTTPError, URLError, TimeoutError, ValueError, OSError):
                    continue
                if not obtido:
                    continue
                conteudo, extensao, nome, _ = obtido
                destino = self._destino_unico(
                    pasta, indice=indice, extensao=extensao, nome_sugerido=nome
                )
                destino.write_bytes(conteudo)
                return ResultadoLinkDownload(
                    indice, url, "OK", destino, "Documento localizado na página Adobe."
                )

            # Tenta capturar JSON embutido e pesquisar recursivamente por strings URL.
            # Isso cobre páginas que serializam metadados em application/json.
            urls_json: list[str] = []
            for bloco in re.findall(
                r'<script[^>]+type=["\']application/(?:ld\+)?json["\'][^>]*>(.*?)</script>',
                texto,
                flags=re.IGNORECASE | re.DOTALL,
            ):
                try:
                    obj = json.loads(html.unescape(bloco))
                except Exception:
                    continue

                def caminhar(valor):
                    if isinstance(valor, dict):
                        for k, v in valor.items():
                            if isinstance(v, str) and any(
                                termo in str(k).casefold()
                                for termo in ("url", "uri", "download", "asset", "file", "content")
                            ):
                                urls_json.append(v)
                            caminhar(v)
                    elif isinstance(valor, list):
                        for v in valor:
                            caminhar(v)

                caminhar(obj)

            for bruto in urls_json[:20]:
                candidato = urljoin(final_url, self._desescapar_url(bruto))
                try:
                    p = urlsplit(candidato)
                    host = (p.hostname or "").casefold()
                except ValueError:
                    continue
                if not any(host == d or host.endswith("." + d) for d in DOMINIOS_CANDIDATOS_ADOBE):
                    continue
                try:
                    obtido = self._baixar_resposta_documento(
                        opener, candidato, referer=final_url, timeout=timeout
                    )
                except (HTTPError, URLError, TimeoutError, ValueError, OSError):
                    continue
                if obtido:
                    conteudo, extensao, nome, _ = obtido
                    destino = self._destino_unico(
                        pasta, indice=indice, extensao=extensao, nome_sugerido=nome
                    )
                    destino.write_bytes(conteudo)
                    return ResultadoLinkDownload(
                        indice, url, "OK", destino, "Documento localizado nos metadados Adobe."
                    )

            return ResultadoLinkDownload(
                indice,
                url,
                "MANUAL",
                None,
                "O Adobe não expôs um arquivo direto; abra este link no navegador e baixe manualmente.",
            )

        except HTTPError as erro:
            status = "MANUAL" if erro.code in {401, 403, 404, 429} else "ERRO"
            return ResultadoLinkDownload(
                indice, url, status, None, f"Adobe respondeu HTTP {erro.code}."
            )
        except URLError as erro:
            return ResultadoLinkDownload(
                indice, url, "ERRO", None, f"Falha de conexão: {getattr(erro, 'reason', erro)}"
            )
        except TimeoutError:
            return ResultadoLinkDownload(indice, url, "ERRO", None, "Tempo de conexão esgotado.")
        except Exception as erro:
            return ResultadoLinkDownload(indice, url, "ERRO", None, str(erro))

    def baixar_lote(
        self,
        texto: str,
        *,
        competencia: str,
        pasta_destino: str | Path | None = None,
        progresso: Callable[[ResultadoLinkDownload, int, int], None] | None = None,
        timeout: int = 25,
    ) -> ResultadoLoteDownload:
        links = self.extrair_links(texto)
        if not links:
            raise ValueError("Nenhum link do Adobe Acrobat foi encontrado no texto colado.")

        if pasta_destino:
            pasta = Path(pasta_destino).expanduser().resolve()
            pasta.mkdir(parents=True, exist_ok=True)
        else:
            pasta = self.pasta_competencia(competencia)
        resultados: list[ResultadoLinkDownload] = []
        total = len(links)

        for indice, url in enumerate(links, 1):
            resultado = self._baixar_um(url, pasta, indice, timeout)
            resultados.append(resultado)
            if progresso:
                progresso(resultado, indice, total)

        baixados = sum(r.status == "OK" for r in resultados)
        manuais = sum(r.status == "MANUAL" for r in resultados)
        erros = sum(r.status == "ERRO" for r in resultados)

        linhas = [
            "FISCALPRO - DOWNLOAD DE DOCUMENTOS DO ADOBE",
            f"Competência: {competencia}",
            f"Gerado em: {time.strftime('%d/%m/%Y %H:%M:%S')}",
            "",
            f"Links: {total}",
            f"Baixados: {baixados}",
            f"Abrir manualmente: {manuais}",
            f"Erros: {erros}",
            "",
        ]
        for r in resultados:
            linhas.append(f"[{r.status}] {r.indice:03d} - {r.url}")
            if r.caminho:
                linhas.append(f"    Arquivo: {r.caminho.name}")
            linhas.append(f"    {r.mensagem}")
        relatorio = pasta / "RELATORIO_DOWNLOAD_ADOBE.txt"
        relatorio.write_text("\n".join(linhas), encoding="utf-8-sig")

        pendentes = [r for r in resultados if r.status != "OK"]
        if pendentes:
            (pasta / "LINKS_NAO_BAIXADOS.txt").write_text(
                "\n\n".join(f"{r.url}\n{r.status}: {r.mensagem}" for r in pendentes),
                encoding="utf-8-sig",
            )

        return ResultadoLoteDownload(
            pasta=pasta,
            total_links=total,
            baixados=baixados,
            manuais=manuais,
            erros=erros,
            resultados=tuple(resultados),
            relatorio=relatorio,
        )
