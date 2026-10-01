"""Documentos financeiros e pacote mensal para a contabilidade.

Hotfix 17.8.105:
- usa o número do documento como identificador principal do nome do anexo;
- mantém fornecedor e vencimento no nome para facilitar a conferência;
- quando não houver número, usa SEM_DOC_ID_<id>;
- aplica o mesmo padrão aos arquivos do pacote mensal para a contabilidade.

Hotfix 17.8.102:
- internaliza PDFs/imagens anexados às contas em ``dados/financeiro/documentos``;
- gera pacote ZIP por competência/empresa;
- gera planilha de conferência com status de anexo e relação de documentos faltantes.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Any


EXTENSOES_DOCUMENTO = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


def _nome_seguro(texto: object, limite: int = 70) -> str:
    valor = re.sub(r"[^A-Za-z0-9À-ÿ._ -]+", "_", str(texto or "").strip())
    valor = re.sub(r"\s+", "_", valor).strip("._ ")
    return (valor or "SEM_NOME")[:limite]


def _nome_documento_financeiro(
    *,
    conta_id: int,
    numero_documento: object,
    fornecedor: object,
    vencimento: object = "",
    extensao: str,
) -> str:
    """Nome legível do anexo, priorizando o número do documento."""

    numero_raw = str(numero_documento or "").strip()
    if numero_raw:
        identificador = "DOC_" + _nome_seguro(numero_raw, 45)
    else:
        identificador = f"SEM_DOC_ID_{int(conta_id):06d}"

    fornecedor_nome = _nome_seguro(fornecedor, 45)
    data_nome = re.sub(r"[^0-9]", "", str(vencimento or "")) or "SEM_DATA"
    ext = str(extensao or "").casefold()
    return f"{identificador}_{fornecedor_nome}_{data_nome}{ext}"


def _celula(linha: Mapping[str, Any], chave: str, padrao: Any = "") -> Any:
    try:
        return linha[chave]
    except (KeyError, IndexError, TypeError):
        return padrao


def _formatar_cnpj(valor: object) -> str:
    digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
    if len(digitos) == 14:
        return (
            f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/"
            f"{digitos[8:12]}-{digitos[12:]}"
        )
    return str(valor or "").strip()


@dataclass(frozen=True)
class ResumoDocumentosCompetencia:
    total_contas: int
    com_documento: int
    sem_documento: int
    documentos_invalidos: int


@dataclass(frozen=True)
class ResultadoPacoteContabilidade:
    caminho_zip: Path
    total_contas: int
    documentos_incluidos: int
    documentos_faltantes: int
    empresas: tuple[str, ...]


class GestorDocumentosFinanceiros:
    """Organiza anexos permanentes e exporta o pacote mensal."""

    def __init__(self, pasta_financeiro: str | Path):
        self.pasta_financeiro = Path(pasta_financeiro).expanduser().resolve()
        self.pasta_documentos = self.pasta_financeiro / "documentos"

    def eh_documento_interno(self, caminho: str | Path) -> bool:
        try:
            Path(caminho).expanduser().resolve().relative_to(self.pasta_documentos.resolve())
            return True
        except (OSError, ValueError):
            return False

    def internalizar(
        self,
        origem: str | Path,
        *,
        conta_id: int,
        empresa: str,
        competencia: str,
        fornecedor: str,
        vencimento: str = "",
        numero_documento: object = "",
    ) -> Path:
        """Copia um anexo local para a área persistente do FiscalPro.

        Se o arquivo já estiver dentro da pasta interna, apenas devolve o caminho.
        """

        fonte = Path(origem).expanduser()
        if not fonte.is_file():
            raise FileNotFoundError("O documento selecionado não foi encontrado.")
        if fonte.suffix.casefold() not in EXTENSOES_DOCUMENTO:
            raise ValueError("Use um documento PDF ou uma imagem JPG, JPEG, PNG ou WEBP.")

        fonte = fonte.resolve()
        if self.eh_documento_interno(fonte):
            return fonte

        comp = competencia if re.fullmatch(r"\d{4}-\d{2}", competencia or "") else "SEM_COMPETENCIA"
        pasta = self.pasta_documentos / comp / _nome_seguro(empresa)
        pasta.mkdir(parents=True, exist_ok=True)

        nome = _nome_documento_financeiro(
            conta_id=int(conta_id),
            numero_documento=numero_documento,
            fornecedor=fornecedor,
            vencimento=vencimento,
            extensao=fonte.suffix,
        )
        destino = pasta / nome

        # Se já existir um arquivo com o mesmo nome e conteúdo/tamanho, reutiliza.
        if destino.is_file() and destino.stat().st_size == fonte.stat().st_size:
            return destino.resolve()

        # Evita sobrescrever um anexo diferente da mesma conta.
        if destino.exists():
            indice = 2
            while True:
                candidato = destino.with_name(f"{destino.stem}_{indice}{destino.suffix}")
                if not candidato.exists():
                    destino = candidato
                    break
                indice += 1

        shutil.copy2(fonte, destino)
        return destino.resolve()

    @staticmethod
    def resumo(contas: Iterable[Mapping[str, Any]]) -> ResumoDocumentosCompetencia:
        total = com = invalidos = 0
        for conta in contas:
            total += 1
            caminho = str(_celula(conta, "caminho_documento", "") or "").strip()
            if caminho and Path(caminho).is_file():
                com += 1
            elif caminho:
                invalidos += 1
        return ResumoDocumentosCompetencia(
            total_contas=total,
            com_documento=com,
            sem_documento=total - com,
            documentos_invalidos=invalidos,
        )

    def gerar_pacote(
        self,
        contas: Iterable[Mapping[str, Any]],
        destino: str | Path,
        *,
        competencia: str,
        empresas: Iterable[str],
    ) -> ResultadoPacoteContabilidade:
        """Gera ZIP com anexos organizados e planilha de conferência."""

        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError as erro:
            raise RuntimeError("Instale o pacote openpyxl para gerar o pacote da contabilidade.") from erro

        empresas_tuple = tuple(dict.fromkeys(str(e).strip() for e in empresas if str(e).strip()))
        linhas = list(contas)
        if not re.fullmatch(r"\d{4}-\d{2}", competencia or ""):
            raise ValueError("Competência inválida para o pacote da contabilidade.")
        if not empresas_tuple:
            raise ValueError("Selecione pelo menos uma empresa.")

        pasta_destino = Path(destino).expanduser().resolve()
        pasta_destino.mkdir(parents=True, exist_ok=True)
        comp_br = f"{competencia[5:7]}-{competencia[:4]}"
        zip_final = pasta_destino / f"CONTABILIDADE_{comp_br}.zip"

        with tempfile.TemporaryDirectory(prefix="fiscalpro_contabilidade_") as temporaria:
            raiz = Path(temporaria) / f"CONTABILIDADE_{comp_br}"
            raiz.mkdir(parents=True, exist_ok=True)

            wb = Workbook()
            ws = wb.active
            ws.title = "Conferência"
            cabecalhos = [
                "Empresa", "Fornecedor", "CNPJ do fornecedor", "Descrição",
                "Nº Documento", "Vencimento", "Valor", "Categoria", "Status",
                "Competência", "Anexo", "Arquivo"
            ]
            ws.append(cabecalhos)
            azul = "1F4E78"
            for celula in ws[1]:
                celula.fill = PatternFill("solid", fgColor=azul)
                celula.font = Font(color="FFFFFF", bold=True)
                celula.alignment = Alignment(horizontal="center", vertical="center")

            documentos_incluidos = 0
            faltantes: list[str] = []
            nomes_usados: dict[Path, set[str]] = {}

            for conta in linhas:
                empresa = str(_celula(conta, "empresa", "") or "")
                if empresa not in empresas_tuple:
                    continue
                pasta_empresa = raiz / _nome_seguro(empresa)
                pasta_empresa.mkdir(parents=True, exist_ok=True)

                caminho_txt = str(_celula(conta, "caminho_documento", "") or "").strip()
                fonte = Path(caminho_txt).expanduser() if caminho_txt else None
                anexo_ok = bool(fonte and fonte.is_file())
                arquivo_pacote = ""

                if anexo_ok and fonte is not None:
                    conta_id = int(_celula(conta, "id", 0) or 0)
                    nome_base = _nome_documento_financeiro(
                        conta_id=conta_id,
                        numero_documento=_celula(conta, "numero_documento", ""),
                        fornecedor=_celula(conta, "fornecedor", ""),
                        vencimento=_celula(conta, "vencimento", ""),
                        extensao=fonte.suffix,
                    )
                    usados = nomes_usados.setdefault(pasta_empresa, set())
                    nome = nome_base
                    indice = 2
                    while nome.casefold() in usados:
                        nome = f"{Path(nome_base).stem}_{indice}{Path(nome_base).suffix}"
                        indice += 1
                    usados.add(nome.casefold())
                    alvo = pasta_empresa / nome
                    shutil.copy2(fonte, alvo)
                    arquivo_pacote = f"{pasta_empresa.name}/{nome}"
                    documentos_incluidos += 1
                else:
                    faltantes.append(
                        f"ID {_celula(conta, 'id', '')} | {empresa} | "
                        f"{_celula(conta, 'fornecedor', '')} | "
                        f"Venc. {_celula(conta, 'vencimento', '')} | "
                        f"R$ {float(_celula(conta, 'valor', 0) or 0):.2f}"
                    )

                ws.append([
                    empresa,
                    _celula(conta, "fornecedor", ""),
                    _formatar_cnpj(
                        _celula(conta, "fornecedor_cnpj_relatorio", "")
                        or _celula(conta, "fornecedor_cnpj", "")
                    ),
                    _celula(conta, "descricao", ""),
                    _celula(conta, "numero_documento", ""),
                    _celula(conta, "vencimento", ""),
                    float(_celula(conta, "valor", 0) or 0),
                    _celula(conta, "categoria", ""),
                    _celula(conta, "status", ""),
                    _celula(conta, "competencia", ""),
                    "SIM" if anexo_ok else "NÃO",
                    arquivo_pacote,
                ])

            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            larguras = [24, 30, 21, 34, 18, 14, 14, 22, 14, 14, 12, 55]
            for indice, largura in enumerate(larguras, 1):
                ws.column_dimensions[chr(64 + indice)].width = largura
            for celula in ws["G"][1:]:
                celula.number_format = 'R$ #,##0.00'
            for linha in ws.iter_rows(min_row=2):
                for celula in linha:
                    celula.alignment = Alignment(vertical="top", wrap_text=True)

            relatorio = raiz / f"RELATORIO_DOCUMENTOS_{comp_br}.xlsx"
            wb.save(relatorio)

            if faltantes:
                (raiz / "DOCUMENTOS_FALTANTES.txt").write_text(
                    "DOCUMENTOS SEM ANEXO OU COM CAMINHO INVÁLIDO\n"
                    f"Competência: {comp_br}\n\n" + "\n".join(faltantes),
                    encoding="utf-8-sig",
                )

            temporario_zip = zip_final.with_suffix(".zip.tmp")
            temporario_zip.unlink(missing_ok=True)
            with zipfile.ZipFile(temporario_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for arquivo in sorted(raiz.rglob("*")):
                    if arquivo.is_file():
                        zf.write(arquivo, arquivo.relative_to(raiz.parent).as_posix())
            temporario_zip.replace(zip_final)

        return ResultadoPacoteContabilidade(
            caminho_zip=zip_final,
            total_contas=len(linhas),
            documentos_incluidos=documentos_incluidos,
            documentos_faltantes=len(faltantes),
            empresas=empresas_tuple,
        )
