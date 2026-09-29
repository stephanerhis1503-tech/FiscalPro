from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable
import re
import zipfile
import xml.etree.ElementTree as ET

ProgressoCallback = Callable[[int, str], None]


@dataclass(slots=True, frozen=True)
class CTeXML:
    numero: str
    serie: str
    chave: str
    arquivo: str
    origem: str


@dataclass(slots=True)
class ResultadoImportacaoCTeXML:
    fontes: list[Path]
    documentos: list[CTeXML]
    total_arquivos_xml: int = 0
    total_cte_validos: int = 0
    total_ignorados: int = 0
    total_erros: int = 0
    total_duplicados: int = 0
    mensagens: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class ApontamentoChaveCTe:
    status: str
    numero_linha: int
    numero_cte: str
    serie: str
    chave_sped: str
    chave_xml: str
    arquivo_xml: str
    detalhe: str


@dataclass(slots=True)
class ResultadoAnaliseChavesCTe:
    total_d100_cte: int
    corretas: int
    divergentes: int
    nao_encontradas: int
    ambiguas: int
    apontamentos: list[ApontamentoChaveCTe]

    @property
    def pode_corrigir(self) -> bool:
        return self.divergentes > 0


@dataclass(slots=True)
class ResultadoCorrecaoChavesCTe:
    caminho_sped: Path
    caminho_relatorio: Path
    corrigidas: int
    corretas: int
    nao_encontradas: int
    ambiguas: int


class ImportadorCTeXML:
    """Lê XMLs de CT-e vindos de pasta, arquivos avulsos ou ZIP."""

    def importar(
        self,
        fontes: Iterable[str | Path],
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoImportacaoCTeXML:
        caminhos = [Path(f) for f in fontes]
        if not caminhos:
            raise RuntimeError("Selecione uma pasta, XML ou ZIP de CT-e.")

        resultado = ResultadoImportacaoCTeXML(fontes=caminhos, documentos=[])
        encontrados: list[tuple[str, bytes, str]] = []

        self._progresso(progresso, 5, "Localizando XMLs de CT-e...")
        for caminho in caminhos:
            if not caminho.exists():
                resultado.total_erros += 1
                resultado.mensagens.append(f"Fonte não encontrada: {caminho}")
                continue

            if caminho.is_dir():
                for xml in sorted(caminho.rglob("*.xml")):
                    try:
                        encontrados.append((xml.name, xml.read_bytes(), str(xml)))
                    except OSError as erro:
                        resultado.total_erros += 1
                        resultado.mensagens.append(f"Falha ao ler {xml}: {erro}")
                continue

            sufixo = caminho.suffix.lower()
            if sufixo == ".xml":
                try:
                    encontrados.append((caminho.name, caminho.read_bytes(), str(caminho)))
                except OSError as erro:
                    resultado.total_erros += 1
                    resultado.mensagens.append(f"Falha ao ler {caminho}: {erro}")
            elif sufixo == ".zip":
                self._ler_zip(caminho, encontrados, resultado)
            else:
                resultado.total_ignorados += 1
                resultado.mensagens.append(f"Formato ignorado: {caminho.name}")

        resultado.total_arquivos_xml = len(encontrados)
        if not encontrados:
            raise RuntimeError("Nenhum arquivo XML foi encontrado nas fontes selecionadas.")

        vistos: set[tuple[str, str, str]] = set()
        total = len(encontrados)
        for indice, (nome, conteudo, origem) in enumerate(encontrados, start=1):
            if indice == 1 or indice % 100 == 0 or indice == total:
                percentual = 10 + int((indice / total) * 85)
                self._progresso(progresso, percentual, f"Lendo XML de CT-e {indice:,} de {total:,}...")
            try:
                documento = self._interpretar_xml(nome, conteudo, origem)
                if documento is None:
                    resultado.total_ignorados += 1
                    continue
                assinatura = (
                    self._normalizar_numero(documento.numero),
                    self._normalizar_serie(documento.serie),
                    documento.chave,
                )
                if assinatura in vistos:
                    resultado.total_duplicados += 1
                    continue
                vistos.add(assinatura)
                resultado.documentos.append(documento)
            except Exception as erro:  # XML de terceiros pode variar bastante.
                resultado.total_erros += 1
                resultado.mensagens.append(f"{nome}: {erro}")

        resultado.total_cte_validos = len(resultado.documentos)
        if not resultado.documentos:
            raise RuntimeError(
                "Os arquivos foram lidos, mas nenhum XML de CT-e válido foi encontrado."
            )
        self._progresso(
            progresso,
            100,
            f"{resultado.total_cte_validos:,} CT-e(s) carregado(s) com sucesso.",
        )
        return resultado

    @staticmethod
    def _ler_zip(
        caminho: Path,
        encontrados: list[tuple[str, bytes, str]],
        resultado: ResultadoImportacaoCTeXML,
    ) -> None:
        try:
            with zipfile.ZipFile(caminho) as arquivo_zip:
                for membro in arquivo_zip.infolist():
                    if membro.is_dir() or not membro.filename.lower().endswith(".xml"):
                        continue
                    try:
                        conteudo = arquivo_zip.read(membro)
                        encontrados.append(
                            (
                                Path(membro.filename).name,
                                conteudo,
                                f"{caminho.name}::{membro.filename}",
                            )
                        )
                    except Exception as erro:
                        resultado.total_erros += 1
                        resultado.mensagens.append(
                            f"Falha ao ler {membro.filename} dentro de {caminho.name}: {erro}"
                        )
        except (OSError, zipfile.BadZipFile) as erro:
            resultado.total_erros += 1
            resultado.mensagens.append(f"ZIP inválido {caminho}: {erro}")

    @staticmethod
    def _interpretar_xml(nome: str, conteudo: bytes, origem: str) -> CTeXML | None:
        raiz = ET.fromstring(conteudo)
        inf_cte = None
        numero = ""
        serie = ""
        chave = ""

        for elemento in raiz.iter():
            tag = elemento.tag.rsplit("}", 1)[-1]
            if tag == "infCte" and inf_cte is None:
                inf_cte = elemento
                chave = (elemento.attrib.get("Id") or "").strip()
                if chave.startswith("CTe"):
                    chave = chave[3:]
            elif tag == "nCT" and not numero:
                numero = (elemento.text or "").strip()
            elif tag == "serie" and not serie:
                serie = (elemento.text or "").strip()

        if inf_cte is None or not numero:
            return None

        somente_digitos = re.sub(r"\D", "", chave)
        if len(somente_digitos) != 44:
            correspondencias = re.findall(r"(?<!\d)(\d{44})(?!\d)", nome)
            if correspondencias:
                somente_digitos = correspondencias[0]
        if len(somente_digitos) != 44:
            raise ValueError("chave de acesso do CT-e ausente ou diferente de 44 dígitos")

        return CTeXML(
            numero=numero,
            serie=serie,
            chave=somente_digitos,
            arquivo=nome,
            origem=origem,
        )

    @staticmethod
    def _normalizar_numero(valor: str) -> str:
        digitos = re.sub(r"\D", "", valor or "")
        return digitos.lstrip("0") or "0"

    @staticmethod
    def _normalizar_serie(valor: str) -> str:
        digitos = re.sub(r"\D", "", valor or "")
        return digitos.lstrip("0") or "0"

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(percentual, mensagem)


class CorretorChavesCTeXML:
    MODELOS_CTE = {"57", "67"}

    def analisar(
        self,
        linhas_sped: list[str],
        importacao: ResultadoImportacaoCTeXML,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseChavesCTe:
        indice_exato: dict[tuple[str, str], list[CTeXML]] = {}
        indice_numero: dict[str, list[CTeXML]] = {}
        for documento in importacao.documentos:
            numero = ImportadorCTeXML._normalizar_numero(documento.numero)
            serie = ImportadorCTeXML._normalizar_serie(documento.serie)
            indice_exato.setdefault((numero, serie), []).append(documento)
            indice_numero.setdefault(numero, []).append(documento)

        total_linhas = max(len(linhas_sped), 1)
        apontamentos: list[ApontamentoChaveCTe] = []
        corretas = divergentes = nao_encontradas = ambiguas = total_d100 = 0

        self._progresso(progresso, 5, "Cruzando registros D100 com os XMLs...")
        for indice, linha in enumerate(linhas_sped):
            if indice % 3000 == 0:
                percentual = 5 + int(((indice + 1) / total_linhas) * 90)
                self._progresso(progresso, percentual, "Conferindo chaves dos CT-e...")
            texto = linha.rstrip("\r\n")
            if not texto.startswith("|D100|"):
                continue
            campos = texto.split("|")
            if len(campos) <= 10:
                continue
            modelo = campos[5].strip()
            if modelo not in self.MODELOS_CTE:
                continue

            total_d100 += 1
            serie_original = campos[7].strip()
            numero_original = campos[9].strip()
            chave_sped = re.sub(r"\D", "", campos[10].strip())
            numero = ImportadorCTeXML._normalizar_numero(numero_original)
            serie = ImportadorCTeXML._normalizar_serie(serie_original)
            candidatos = indice_exato.get((numero, serie), [])
            if not candidatos:
                candidatos = indice_numero.get(numero, [])

            candidatos_unicos = {cte.chave: cte for cte in candidatos}
            if not candidatos_unicos:
                nao_encontradas += 1
                apontamentos.append(
                    ApontamentoChaveCTe(
                        status="NÃO ENCONTRADO",
                        numero_linha=indice + 1,
                        numero_cte=numero_original,
                        serie=serie_original,
                        chave_sped=chave_sped,
                        chave_xml="",
                        arquivo_xml="",
                        detalhe="Nenhum XML compatível foi localizado pelo número e série do CT-e.",
                    )
                )
                continue
            if len(candidatos_unicos) > 1:
                ambiguas += 1
                apontamentos.append(
                    ApontamentoChaveCTe(
                        status="AMBÍGUO",
                        numero_linha=indice + 1,
                        numero_cte=numero_original,
                        serie=serie_original,
                        chave_sped=chave_sped,
                        chave_xml=" / ".join(sorted(candidatos_unicos)),
                        arquivo_xml="Vários XMLs",
                        detalhe="Há mais de uma chave possível para o mesmo número de CT-e.",
                    )
                )
                continue

            chave_xml, documento = next(iter(candidatos_unicos.items()))
            if chave_sped == chave_xml:
                corretas += 1
                status = "CORRETA"
                detalhe = "A chave do D100 já confere com o XML."
            else:
                divergentes += 1
                status = "CORRIGIR"
                detalhe = "A chave do D100 será substituída pela chave de 44 dígitos do XML."
            apontamentos.append(
                ApontamentoChaveCTe(
                    status=status,
                    numero_linha=indice + 1,
                    numero_cte=numero_original,
                    serie=serie_original,
                    chave_sped=chave_sped,
                    chave_xml=chave_xml,
                    arquivo_xml=documento.arquivo,
                    detalhe=detalhe,
                )
            )

        self._progresso(progresso, 100, "Conferência das chaves de CT-e concluída.")
        return ResultadoAnaliseChavesCTe(
            total_d100_cte=total_d100,
            corretas=corretas,
            divergentes=divergentes,
            nao_encontradas=nao_encontradas,
            ambiguas=ambiguas,
            apontamentos=apontamentos,
        )

    def corrigir_e_salvar(
        self,
        linhas_sped: list[str],
        encoding: str,
        analise: ResultadoAnaliseChavesCTe,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoCorrecaoChavesCTe:
        destino = Path(caminho_saida)
        if destino.suffix.lower() != ".txt":
            destino = destino.with_suffix(".txt")
        destino.parent.mkdir(parents=True, exist_ok=True)

        por_linha = {
            item.numero_linha: item
            for item in analise.apontamentos
            if item.status == "CORRIGIR" and len(item.chave_xml) == 44
        }
        if not por_linha:
            raise RuntimeError("Não existem chaves divergentes com correção segura para aplicar.")

        novas_linhas: list[str] = []
        total = max(len(linhas_sped), 1)
        corrigidas = 0
        for indice, linha in enumerate(linhas_sped, start=1):
            if indice % 3000 == 0:
                percentual = 5 + int((indice / total) * 80)
                self._progresso(progresso, percentual, "Aplicando chaves dos XMLs...")
            apontamento = por_linha.get(indice)
            if apontamento is None:
                novas_linhas.append(linha)
                continue
            quebra = "\r\n" if linha.endswith("\r\n") else "\n" if linha.endswith("\n") else ""
            campos = linha.rstrip("\r\n").split("|")
            if len(campos) <= 10:
                novas_linhas.append(linha)
                continue
            campos[10] = apontamento.chave_xml
            novas_linhas.append("|".join(campos) + quebra)
            corrigidas += 1

        self._progresso(progresso, 88, "Gravando nova cópia do SPED...")
        with destino.open("w", encoding=encoding, newline="") as arquivo:
            arquivo.writelines(novas_linhas)

        relatorio = destino.with_name(f"{destino.stem}_RELATORIO_CTE_XML.txt")
        self._salvar_relatorio(relatorio, analise, corrigidas)
        self._progresso(progresso, 100, "Chaves de CT-e corrigidas com sucesso.")
        return ResultadoCorrecaoChavesCTe(
            caminho_sped=destino,
            caminho_relatorio=relatorio,
            corrigidas=corrigidas,
            corretas=analise.corretas,
            nao_encontradas=analise.nao_encontradas,
            ambiguas=analise.ambiguas,
        )

    @staticmethod
    def _salvar_relatorio(
        caminho: Path,
        analise: ResultadoAnaliseChavesCTe,
        corrigidas: int,
    ) -> None:
        with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write("FISCALPRO — CORREÇÃO DE CHAVES DE CT-E POR XML\n")
            arquivo.write("=" * 72 + "\n\n")
            arquivo.write(f"Registros D100 de CT-e analisados: {analise.total_d100_cte}\n")
            arquivo.write(f"Chaves já corretas: {analise.corretas}\n")
            arquivo.write(f"Chaves corrigidas: {corrigidas}\n")
            arquivo.write(f"XML não encontrado: {analise.nao_encontradas}\n")
            arquivo.write(f"Correspondências ambíguas: {analise.ambiguas}\n\n")
            arquivo.write("ALTERAÇÕES APLICADAS\n")
            arquivo.write("-" * 72 + "\n")
            for item in analise.apontamentos:
                if item.status != "CORRIGIR":
                    continue
                arquivo.write(
                    f"Linha {item.numero_linha} | CT-e {item.numero_cte} | Série {item.serie}\n"
                )
                arquivo.write(f"Antes : {item.chave_sped or '(vazio)'}\n")
                arquivo.write(f"Depois: {item.chave_xml}\n")
                arquivo.write(f"XML   : {item.arquivo_xml}\n\n")

            pendencias = [
                item for item in analise.apontamentos if item.status in {"NÃO ENCONTRADO", "AMBÍGUO"}
            ]
            if pendencias:
                arquivo.write("PENDÊNCIAS NÃO ALTERADAS\n")
                arquivo.write("-" * 72 + "\n")
                for item in pendencias:
                    arquivo.write(
                        f"{item.status} | Linha {item.numero_linha} | CT-e {item.numero_cte} | "
                        f"Série {item.serie} | {item.detalhe}\n"
                    )

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(percentual, mensagem)
