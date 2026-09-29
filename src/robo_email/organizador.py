"""Organização automática e nomenclatura padronizada dos documentos do robô."""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .classificador import classificar_arquivo, nome_seguro, normalizar_texto, pasta_empresa_segura


PASTA_REVISAO = "_Revisar"

_MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

_GUIAS = (
    ("PIS_COFINS", ("pis cofins", "pis/cofins", "pis e cofins")),
    ("IRPJ_CSLL", ("irpj csll", "irpj/csll", "irpj e csll")),
    ("GNRE", ("gnre",)),
    ("DARF", ("darf",)),
    ("DAE", ("dae",)),
    ("DAS", ("das", "simples nacional")),
    ("FGTS", ("fgts",)),
    ("INSS", ("inss",)),
    ("GPS", ("gps",)),
    ("ICMS", ("icms",)),
)


@dataclass(slots=True, frozen=True)
class MetadadosXML:
    tipo: str = "XML"
    numero: str = ""
    chave: str = ""
    data_emissao: datetime | None = None


@dataclass(slots=True, frozen=True)
class PlanoOrganizacao:
    """Destino calculado antes de qualquer gravação no disco."""

    empresa: str | None
    empresa_banco: str
    pasta_empresa: str
    categoria: str
    ano: int
    mes: int
    competencia: str
    origem_competencia: str
    nome_original: str
    nome_padronizado: str
    tipo_documento: str
    identificador: str
    pasta_destino: Path
    caminho_sugerido: Path
    precisa_revisao: bool
    observacao: str


class OrganizadorDocumentos:
    """Define competência, pasta e nome seguro de forma conservadora."""

    def __init__(self, pasta_base: str | Path):
        self.pasta_base = Path(pasta_base).expanduser()

    def planejar(
        self,
        *,
        nome_original: str,
        dados: bytes,
        empresa: str | None,
        data_email: datetime,
        mime_type: str = "",
        assunto: str = "",
        contexto: str = "",
        categoria_preferida: str | None = None,
        competencia_preferida: str = "",
        tipo_documento_preferido: str = "",
        identificador_preferido: str = "",
    ) -> PlanoOrganizacao:
        categoria = categoria_preferida or classificar_arquivo(nome_original, mime_type)
        categoria = categoria if categoria in {"XML", "Guias", "PDF", "ZIP", "Outros", "Links"} else "Outros"

        xml = self._ler_xml(dados) if categoria == "XML" else MetadadosXML()
        competencia_data, origem_competencia = self._competencia(
            nome_original=nome_original,
            assunto=assunto,
            contexto=contexto,
            data_email=data_email,
            data_xml=xml.data_emissao,
            competencia_preferida=competencia_preferida,
        )
        ano, mes = competencia_data.year, competencia_data.month
        competencia = f"{ano:04d}-{mes:02d}"

        pasta_empresa = pasta_empresa_segura(empresa) if empresa else PASTA_REVISAO
        empresa_banco = empresa or "Não Identificada"
        pasta_destino = self.pasta_base / pasta_empresa / f"{ano:04d}" / f"{mes:02d}" / categoria

        tipo_documento, identificador = self._tipo_e_identificador(
            categoria=categoria,
            nome_original=nome_original,
            assunto=assunto,
            contexto=contexto,
            xml=xml,
        )
        if tipo_documento_preferido:
            tipo_documento = tipo_documento_preferido
        if identificador_preferido:
            identificador = identificador_preferido
        nome_padronizado = self._nome_padronizado(
            nome_original=nome_original,
            competencia=competencia,
            categoria=categoria,
            tipo_documento=tipo_documento,
            identificador=identificador,
            xml=xml,
        )

        precisa_revisao = not empresa or categoria in {"Outros", "Links"}
        motivos: list[str] = [f"Competência definida pela {origem_competencia}."]
        if not empresa:
            motivos.append("Empresa não identificada; arquivo enviado para a pasta _Revisar.")
        if categoria in {"Outros", "Links"}:
            motivos.append("Tipo de documento não confirmado; revisar a classificação.")

        return PlanoOrganizacao(
            empresa=empresa,
            empresa_banco=empresa_banco,
            pasta_empresa=pasta_empresa,
            categoria=categoria,
            ano=ano,
            mes=mes,
            competencia=competencia,
            origem_competencia=origem_competencia,
            nome_original=Path(nome_original or "documento").name,
            nome_padronizado=nome_padronizado,
            tipo_documento=tipo_documento,
            identificador=identificador,
            pasta_destino=pasta_destino,
            caminho_sugerido=pasta_destino / nome_padronizado,
            precisa_revisao=precisa_revisao,
            observacao=" ".join(motivos),
        )

    @classmethod
    def _competencia(
        cls,
        *,
        nome_original: str,
        assunto: str,
        contexto: str,
        data_email: datetime,
        data_xml: datetime | None,
        competencia_preferida: str = "",
    ) -> tuple[datetime, str]:
        if competencia_preferida:
            try:
                return datetime.strptime(competencia_preferida, "%Y-%m"), "conteúdo do documento"
            except ValueError:
                pass
        if data_xml is not None:
            return data_xml, "data de emissão do XML"

        texto = f"{nome_original} {assunto} {contexto}"
        encontrada = cls._competencia_texto(texto)
        if encontrada is not None:
            ano, mes = encontrada
            return datetime(ano, mes, 1), "competência informada no nome/assunto"

        return data_email, "data do e-mail"

    @staticmethod
    def _competencia_texto(texto: str) -> tuple[int, int] | None:
        normalizado = normalizar_texto(texto)

        padrao_rotulado = re.search(
            r"(?:competencia|comp\.?|referencia|ref\.?|periodo|apuracao)"
            r"\D{0,18}(0?[1-9]|1[0-2])\s*[-/_.]\s*((?:19|20)\d{2})",
            normalizado,
        )
        if padrao_rotulado:
            mes, ano = int(padrao_rotulado.group(1)), int(padrao_rotulado.group(2))
            if 2000 <= ano <= 2100:
                return ano, mes

        padrao_rotulado_inverso = re.search(
            r"(?:competencia|comp\.?|referencia|ref\.?|periodo|apuracao)"
            r"\D{0,18}((?:19|20)\d{2})\s*[-/_.]\s*(0?[1-9]|1[0-2])",
            normalizado,
        )
        if padrao_rotulado_inverso:
            ano, mes = int(padrao_rotulado_inverso.group(1)), int(padrao_rotulado_inverso.group(2))
            if 2000 <= ano <= 2100:
                return ano, mes

        for nome_mes, mes in _MESES.items():
            encontrado = re.search(rf"\b{nome_mes}\b\D{{0,8}}((?:19|20)\d{{2}})", normalizado)
            if encontrado:
                ano = int(encontrado.group(1))
                if 2000 <= ano <= 2100:
                    return ano, mes

        # Remove datas completas para não confundir vencimento 31/08/2026 com
        # uma competência explícita 08/2026.
        sem_datas_completas = re.sub(
            r"\b\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*(?:19|20)\d{2}\b",
            " ",
            normalizado,
        )
        generico = re.search(
            r"(?<!\d)(0?[1-9]|1[0-2])\s*[-/_.]\s*((?:19|20)\d{2})(?!\d)",
            sem_datas_completas,
        )
        if generico:
            mes, ano = int(generico.group(1)), int(generico.group(2))
            if 2000 <= ano <= 2100:
                return ano, mes

        generico_inverso = re.search(
            r"(?<!\d)((?:19|20)\d{2})\s*[-/_.]\s*(0?[1-9]|1[0-2])(?!\d)",
            sem_datas_completas,
        )
        if generico_inverso:
            ano, mes = int(generico_inverso.group(1)), int(generico_inverso.group(2))
            if 2000 <= ano <= 2100:
                return ano, mes
        return None

    @classmethod
    def _tipo_e_identificador(
        cls,
        *,
        categoria: str,
        nome_original: str,
        assunto: str,
        contexto: str,
        xml: MetadadosXML,
    ) -> tuple[str, str]:
        if categoria == "XML":
            return xml.tipo or "XML", xml.numero or xml.chave
        if categoria == "Guias":
            tipo = cls._tipo_guia(f"{nome_original} {assunto} {contexto}")
            return "Guia", tipo
        if categoria == "PDF":
            return "PDF", ""
        if categoria == "ZIP":
            return "ZIP", ""
        return "Documento", ""

    @staticmethod
    def _tipo_guia(texto: str) -> str:
        normalizado = normalizar_texto(texto)
        for tipo, termos in _GUIAS:
            if any(
                re.search(
                    rf"(?<!\w){re.escape(termo).replace(r'\ ', r'\s+')}(?!\w)",
                    normalizado,
                )
                for termo in termos
            ):
                return tipo
        return "GUIA"

    @classmethod
    def _nome_padronizado(
        cls,
        *,
        nome_original: str,
        competencia: str,
        categoria: str,
        tipo_documento: str,
        identificador: str,
        xml: MetadadosXML,
    ) -> str:
        original = Path(nome_original or "documento")
        extensao = original.suffix.lower()
        if not extensao:
            extensao = {"XML": ".xml", "PDF": ".pdf", "Guias": ".pdf", "ZIP": ".zip"}.get(categoria, "")

        stem = cls._fragmento(original.stem, 72) or "documento"
        partes = [competencia]

        if categoria == "XML":
            partes.append(cls._fragmento(xml.tipo or "XML", 16) or "XML")
            if xml.numero:
                partes.append(cls._fragmento(xml.numero, 20))
            if xml.chave:
                partes.append(cls._fragmento(xml.chave, 48))
            elif not xml.numero:
                partes.append(stem)
        elif categoria == "Guias":
            partes.extend(["Guia", cls._fragmento(identificador or "GUIA", 24)])
            if stem.casefold() not in {parte.casefold() for parte in partes}:
                partes.append(stem)
        elif categoria == "PDF":
            partes.extend(["PDF", stem])
        elif categoria == "ZIP":
            partes.extend(["ZIP", stem])
        else:
            partes.extend(["Revisar", stem])

        base = "_".join(parte for parte in partes if parte)
        return nome_seguro(f"{base}{extensao}", f"{competencia}_documento{extensao}")

    @staticmethod
    def _fragmento(texto: str, limite: int) -> str:
        valor = unicodedata.normalize("NFKD", texto or "")
        valor = "".join(letra for letra in valor if not unicodedata.combining(letra))
        valor = re.sub(r"[^A-Za-z0-9]+", "_", valor).strip("_")
        valor = re.sub(r"_+", "_", valor)
        return valor[:limite].strip("_")

    @staticmethod
    def _ler_xml(dados: bytes) -> MetadadosXML:
        if not dados:
            return MetadadosXML()
        try:
            raiz = ET.fromstring(dados)
        except (ET.ParseError, ValueError):
            return MetadadosXML()

        def local(tag: str) -> str:
            return tag.rsplit("}", 1)[-1]

        elementos = list(raiz.iter())
        inf_nfe = next((item for item in elementos if local(item.tag) == "infNFe"), None)
        inf_cte = next((item for item in elementos if local(item.tag) == "infCte"), None)
        alvo = inf_nfe if inf_nfe is not None else inf_cte
        if alvo is None:
            return MetadadosXML()

        tipo = "NFe" if inf_nfe is not None else "CTe"
        atributo = str(alvo.attrib.get("Id", ""))
        chave = re.sub(r"\D", "", atributo)
        if len(chave) != 44:
            chave = ""

        numero_tag = "nNF" if tipo == "NFe" else "nCT"
        numero = ""
        data_texto = ""
        for item in alvo.iter():
            nome = local(item.tag)
            if nome == numero_tag and not numero:
                numero = (item.text or "").strip()
            if nome in {"dhEmi", "dEmi"} and not data_texto:
                data_texto = (item.text or "").strip()

        data_emissao = None
        if data_texto:
            try:
                data_emissao = datetime.fromisoformat(data_texto.replace("Z", "+00:00"))
            except ValueError:
                try:
                    data_emissao = datetime.strptime(data_texto[:10], "%Y-%m-%d")
                except ValueError:
                    data_emissao = None

        return MetadadosXML(tipo=tipo, numero=numero, chave=chave, data_emissao=data_emissao)


__all__ = [
    "MetadadosXML",
    "OrganizadorDocumentos",
    "PASTA_REVISAO",
    "PlanoOrganizacao",
]
