"""Leitura conservadora de XML, PDF e guias do Robô FiscalPro.

A leitura organiza metadados úteis para conferência. Ela não substitui a
validação fiscal nem presume que uma guia foi paga apenas porque o arquivo existe.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .classificador import normalizar_texto


_TRIBUTOS = (
    ("PIS/COFINS", ("pis cofins", "pis/cofins", "pis e cofins")),
    ("IRPJ/CSLL", ("irpj csll", "irpj/csll", "irpj e csll")),
    ("GNRE", ("gnre",)),
    ("DARF", ("darf",)),
    ("DAE", ("dae",)),
    ("DAS", ("documento de arrecadacao do simples", "simples nacional", " das ")),
    ("FGTS", ("fgts",)),
    ("INSS", ("inss",)),
    ("GPS", ("guia da previdencia social", " gps ")),
    ("ICMS", ("icms",)),
)


@dataclass(slots=True, frozen=True)
class LeituraDocumento:
    empresa_identificada: str | None = None
    tipo_documento: str = "Documento"
    numero_documento: str = ""
    cnpjs: tuple[str, ...] = ()
    competencia: str = ""
    valor: float | None = None
    vencimento: str = ""
    tributo: str = ""
    fonte: str = "Nome/assunto"
    status: str = "REVISAR"
    alertas: tuple[str, ...] = ()

    @property
    def cnpj_principal(self) -> str:
        return self.cnpjs[0] if self.cnpjs else ""

    @property
    def valor_texto(self) -> str:
        if self.valor is None:
            return ""
        return f"R$ {self.valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @property
    def vencimento_texto(self) -> str:
        if not self.vencimento:
            return ""
        try:
            return datetime.strptime(self.vencimento, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return self.vencimento

    @property
    def resumo(self) -> str:
        partes = [self.tipo_documento]
        if self.tributo and self.tributo.casefold() != self.tipo_documento.casefold():
            partes.append(self.tributo)
        if self.numero_documento:
            partes.append(f"nº {self.numero_documento}")
        if self.competencia:
            partes.append(f"comp. {self.competencia[5:7]}/{self.competencia[:4]}")
        if self.valor is not None:
            partes.append(self.valor_texto)
        if self.vencimento:
            partes.append(f"vence {self.vencimento_texto}")
        return " — ".join(partes)


class LeitorInteligenteDocumentos:
    """Extrai somente dados sustentados pelo conteúdo do documento."""

    def __init__(self, cnpjs_empresas: dict[str, str] | None = None):
        self.cnpjs_empresas = {
            empresa: self.normalizar_cnpj(cnpj)
            for empresa, cnpj in (cnpjs_empresas or {}).items()
            if self.normalizar_cnpj(cnpj)
        }
        self.empresas_por_cnpj = {
            cnpj: empresa for empresa, cnpj in self.cnpjs_empresas.items()
        }

    def analisar(
        self,
        *,
        nome_original: str,
        dados: bytes,
        categoria: str,
        empresa_informada: str | None,
        data_email: datetime,
        assunto: str = "",
        contexto: str = "",
    ) -> LeituraDocumento:
        extensao = Path(nome_original).suffix.lower()
        if categoria == "XML" or extensao == ".xml":
            base = self._analisar_xml(dados)
        elif categoria in {"PDF", "Guias"} or extensao == ".pdf":
            texto_pdf, erro_pdf = self._extrair_texto_pdf(dados)
            base = self._analisar_texto(
                f"{texto_pdf}\n{nome_original}\n{assunto}\n{contexto}",
                categoria=categoria,
                data_email=data_email,
                fonte="Texto do PDF" if texto_pdf else "Nome/assunto",
                alerta_inicial=erro_pdf,
            )
        else:
            base = self._analisar_texto(
                f"{nome_original}\n{assunto}\n{contexto}",
                categoria=categoria,
                data_email=data_email,
                fonte="Nome/assunto",
            )
        return self._conferir_empresa(base, empresa_informada)

    def _conferir_empresa(
        self,
        leitura: LeituraDocumento,
        empresa_informada: str | None,
    ) -> LeituraDocumento:
        empresas_encontradas = {
            self.empresas_por_cnpj[cnpj]
            for cnpj in leitura.cnpjs
            if cnpj in self.empresas_por_cnpj
        }
        empresa_identificada = (
            next(iter(empresas_encontradas)) if len(empresas_encontradas) == 1 else None
        )
        alertas = list(leitura.alertas)

        if len(empresas_encontradas) > 1:
            alertas.append("O documento contém CNPJs cadastrados para mais de uma empresa.")

        if empresa_informada:
            esperado = self.cnpjs_empresas.get(empresa_informada, "")
            if esperado and leitura.cnpjs and esperado not in leitura.cnpjs:
                encontrado = ", ".join(self.formatar_cnpj(item) for item in leitura.cnpjs)
                alertas.append(
                    f"Empresa divergente: o CNPJ de {empresa_informada} não aparece no documento "
                    f"(localizado: {encontrado})."
                )
            elif esperado and not leitura.cnpjs:
                alertas.append("Não foi possível localizar CNPJ no conteúdo do documento.")
        elif not empresa_identificada:
            alertas.append("Empresa não identificada pelo e-mail nem pelos CNPJs cadastrados.")

        status = leitura.status
        if any(
            texto.startswith((
                "Empresa divergente",
                "Empresa não identificada",
                "Não foi possível localizar CNPJ",
            ))
            or "mais de uma empresa" in texto
            for texto in alertas
        ):
            status = "REVISAR"

        cnpjs = list(leitura.cnpjs)
        cnpj_preferido = ""
        if empresa_informada:
            cnpj_preferido = self.cnpjs_empresas.get(empresa_informada, "")
        elif empresa_identificada:
            cnpj_preferido = self.cnpjs_empresas.get(empresa_identificada, "")
        if cnpj_preferido in cnpjs:
            cnpjs.remove(cnpj_preferido)
            cnpjs.insert(0, cnpj_preferido)

        return LeituraDocumento(
            empresa_identificada=empresa_identificada,
            tipo_documento=leitura.tipo_documento,
            numero_documento=leitura.numero_documento,
            cnpjs=tuple(cnpjs),
            competencia=leitura.competencia,
            valor=leitura.valor,
            vencimento=leitura.vencimento,
            tributo=leitura.tributo,
            fonte=leitura.fonte,
            status=status,
            alertas=tuple(dict.fromkeys(alertas)),
        )

    def _analisar_xml(self, dados: bytes) -> LeituraDocumento:
        alertas: list[str] = []
        try:
            raiz = ET.fromstring(dados)
        except (ET.ParseError, ValueError):
            return LeituraDocumento(
                tipo_documento="XML",
                fonte="XML",
                status="REVISAR",
                alertas=("XML inválido ou incompleto; não foi possível ler os dados.",),
            )

        def local(tag: str) -> str:
            return tag.rsplit("}", 1)[-1]

        elementos = list(raiz.iter())
        inf_nfe = next((item for item in elementos if local(item.tag) == "infNFe"), None)
        inf_cte = next((item for item in elementos if local(item.tag) == "infCte"), None)
        alvo = inf_nfe if inf_nfe is not None else inf_cte
        if alvo is None:
            alertas.append("XML reconhecido, mas não é uma NF-e ou CT-e estruturada.")
            alvo = raiz

        tipo = "NF-e" if inf_nfe is not None else "CT-e" if inf_cte is not None else "XML"
        numero_tags = ("nNF",) if tipo == "NF-e" else ("nCT",) if tipo == "CT-e" else ()
        numero = self._primeiro_texto(alvo, numero_tags, local)
        data_emissao = self._data_xml(self._primeiro_texto(alvo, ("dhEmi", "dEmi"), local))
        competencia = data_emissao.strftime("%Y-%m") if data_emissao else ""
        if not competencia:
            alertas.append("Data de emissão não localizada no XML.")

        cnpjs = tuple(
            dict.fromkeys(
                cnpj
                for item in alvo.iter()
                if local(item.tag) == "CNPJ"
                for cnpj in [self.normalizar_cnpj(item.text or "")]
                if cnpj
            )
        )
        valor = self._decimal_xml(
            self._primeiro_texto(alvo, ("vNF", "vTPrest", "vServ", "vRec"), local)
        )
        vencimento_dt = self._data_xml(
            self._primeiro_texto(alvo, ("dVenc",), local)
        )
        vencimento = vencimento_dt.strftime("%Y-%m-%d") if vencimento_dt else ""

        if not cnpjs:
            alertas.append("CNPJ não localizado no XML.")
        if valor is None:
            alertas.append("Valor total não localizado no XML.")

        status = "CONFERIDO" if tipo in {"NF-e", "CT-e"} and numero and cnpjs else "REVISAR"
        return LeituraDocumento(
            tipo_documento=tipo,
            numero_documento=numero,
            cnpjs=cnpjs,
            competencia=competencia,
            valor=valor,
            vencimento=vencimento,
            fonte="XML estruturado",
            status=status,
            alertas=tuple(alertas),
        )

    def _analisar_texto(
        self,
        texto: str,
        *,
        categoria: str,
        data_email: datetime,
        fonte: str,
        alerta_inicial: str = "",
    ) -> LeituraDocumento:
        normalizado = normalizar_texto(texto)
        alertas = [alerta_inicial] if alerta_inicial else []
        cnpjs = tuple(dict.fromkeys(self._extrair_cnpjs(texto)))
        tributo = self._identificar_tributo(normalizado)
        tipo = "Guia" if categoria == "Guias" or tributo else (categoria or "Documento")
        competencia = self._extrair_competencia(texto)
        vencimento = self._extrair_vencimento(texto)
        valor = self._extrair_valor(texto)
        numero = self._extrair_numero(texto)

        if not competencia:
            competencia = data_email.strftime("%Y-%m")
            alertas.append("Competência não localizada no documento; usada a data do e-mail.")
        if tipo == "Guia":
            if valor is None:
                alertas.append("Valor da guia não localizado automaticamente.")
            if not vencimento:
                alertas.append("Vencimento da guia não localizado automaticamente.")
        if fonte != "Texto do PDF" and Path(str(texto).splitlines()[0] or "").suffix.lower() == ".pdf":
            alertas.append("O PDF não forneceu texto pesquisável; conferir manualmente.")

        status = "REVISAR" if alertas else "CONFERIDO"
        if vencimento:
            try:
                if datetime.strptime(vencimento, "%Y-%m-%d").date() < date.today():
                    alertas.append("Vencimento passado; conferir se a guia já foi paga ou atualizada.")
                    status = "VENCIMENTO PASSADO"
            except ValueError:
                pass

        return LeituraDocumento(
            tipo_documento=tipo,
            numero_documento=numero,
            cnpjs=cnpjs,
            competencia=competencia,
            valor=valor,
            vencimento=vencimento,
            tributo=tributo,
            fonte=fonte,
            status=status,
            alertas=tuple(dict.fromkeys(alertas)),
        )

    @staticmethod
    def _extrair_texto_pdf(dados: bytes) -> tuple[str, str]:
        if not dados:
            return "", "PDF vazio; não foi possível realizar a leitura."
        try:
            from pypdf import PdfReader
        except ImportError:
            return "", "Biblioteca pypdf ausente; execute INSTALAR_ROBO_EMAIL.bat."
        try:
            leitor = PdfReader(io.BytesIO(dados), strict=False)
            paginas: list[str] = []
            for pagina in leitor.pages[:20]:
                paginas.append(pagina.extract_text() or "")
            texto = "\n".join(paginas).strip()
            if not texto:
                return "", "PDF sem texto pesquisável; pode ser uma imagem digitalizada."
            return texto[:200_000], ""
        except Exception as erro:
            return "", f"Falha ao ler o PDF: {erro}"

    @classmethod
    def _extrair_cnpjs(cls, texto: str) -> Iterable[str]:
        for encontrado in re.findall(
            r"(?<!\d)(?:\d{2}[.\s]?\d{3}[.\s]?\d{3}[\/\s]?\d{4}[-\s]?\d{2}|\d{14})(?!\d)",
            texto or "",
        ):
            cnpj = cls.normalizar_cnpj(encontrado)
            if cnpj:
                yield cnpj

    @staticmethod
    def _extrair_competencia(texto: str) -> str:
        normalizado = normalizar_texto(texto)
        rotulo = re.search(
            r"(?:competencia|periodo de apuracao|referencia|apuracao|periodo)"
            r"\D{0,24}(0?[1-9]|1[0-2])\s*[-/.]\s*((?:19|20)\d{2})",
            normalizado,
        )
        if rotulo:
            return f"{int(rotulo.group(2)):04d}-{int(rotulo.group(1)):02d}"
        inverso = re.search(
            r"(?:competencia|periodo de apuracao|referencia|apuracao|periodo)"
            r"\D{0,24}((?:19|20)\d{2})\s*[-/.]\s*(0?[1-9]|1[0-2])",
            normalizado,
        )
        if inverso:
            return f"{int(inverso.group(1)):04d}-{int(inverso.group(2)):02d}"
        return ""

    @staticmethod
    def _extrair_vencimento(texto: str) -> str:
        normalizado = normalizar_texto(texto)
        encontrado = re.search(
            r"(?:vencimento|data de vencimento|vence em|pagar ate|venc\.?)[^\d]{0,24}"
            r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*((?:19|20)\d{2})",
            normalizado,
        )
        if not encontrado:
            return ""
        dia, mes, ano = map(int, encontrado.groups())
        try:
            return date(ano, mes, dia).isoformat()
        except ValueError:
            return ""

    @staticmethod
    def _extrair_valor(texto: str) -> float | None:
        normalizado = normalizar_texto(texto)
        padroes = (
            r"(?:valor total|total a pagar|valor a recolher|valor do documento|valor principal)"
            r"\D{0,18}(?:r\$\s*)?([0-9][0-9.]*,[0-9]{2})",
            r"(?:r\$\s*)([0-9][0-9.]*,[0-9]{2})",
        )
        for padrao in padroes:
            encontrado = re.search(padrao, normalizado)
            if encontrado:
                try:
                    return float(encontrado.group(1).replace(".", "").replace(",", "."))
                except ValueError:
                    continue
        return None

    @staticmethod
    def _extrair_numero(texto: str) -> str:
        normalizado = normalizar_texto(texto)
        encontrado = re.search(
            r"(?:numero do documento|numero da guia|n(?:umero|º|o)\.?|documento)"
            r"\D{0,12}([0-9][0-9./-]{3,30})",
            normalizado,
        )
        return encontrado.group(1).strip(" ./-") if encontrado else ""

    @staticmethod
    def _identificar_tributo(texto_normalizado: str) -> str:
        texto = f" {texto_normalizado} "
        for tributo, termos in _TRIBUTOS:
            if any(termo in texto for termo in termos):
                return tributo
        return ""

    @staticmethod
    def _primeiro_texto(elemento, tags: tuple[str, ...], local) -> str:
        if not tags:
            return ""
        for item in elemento.iter():
            if local(item.tag) in tags and (item.text or "").strip():
                return (item.text or "").strip()
        return ""

    @staticmethod
    def _data_xml(valor: str) -> datetime | None:
        if not valor:
            return None
        try:
            return datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(valor[:10], "%Y-%m-%d")
            except ValueError:
                return None

    @staticmethod
    def _decimal_xml(valor: str) -> float | None:
        try:
            return float(valor.replace(",", ".")) if valor else None
        except ValueError:
            return None

    @staticmethod
    def normalizar_cnpj(valor: str) -> str:
        digitos = re.sub(r"\D", "", valor or "")
        return digitos if len(digitos) == 14 else ""

    @staticmethod
    def formatar_cnpj(cnpj: str) -> str:
        digitos = re.sub(r"\D", "", cnpj or "")
        if len(digitos) != 14:
            return cnpj
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


__all__ = ["LeitorInteligenteDocumentos", "LeituraDocumento"]
