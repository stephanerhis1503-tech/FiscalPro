"""Auditoria da exclusão do ICMS-ST das bases de PIS/COFINS nas entradas.

Hotfix 17.8.18 — Etapa 1.

Este módulo é deliberadamente conservador: ele apenas cruza o SPED Contribuições
com os XMLs de entrada e classifica os itens. Nenhum arquivo SPED ou XML é
alterado por esta rotina.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, Optional
import re
import zipfile
import xml.etree.ElementTree as ET


STATUS_OK = "OK — ST JÁ FORA DA BASE"
STATUS_SEM_CREDITO = "SEM CRÉDITO — SEM IMPACTO"
STATUS_SEM_CREDITO_ZERO = "SEM CRÉDITO — PIS/COFINS ALÍQUOTA ZERO"
STATUS_REVISAR_ICMS = "OK — ST FORA; REVISAR ICMS PRÓPRIO"
STATUS_REVISAR_CST = "REVISAR CST/CRÉDITO"
STATUS_POSSIVEL_ST = "CORRIGIR — POSSÍVEL ST NA BASE"
STATUS_REVISAR_VINCULO = "REVISAR — VÍNCULO XML/SPED"
STATUS_REVISAR_BASE = "REVISAR — DIVERGÊNCIA DE BASE"

ACAO_OK = "Não excluir ST novamente."
ACAO_SEM_CREDITO = "Nenhuma alteração de base nesta etapa."
ACAO_SEM_CREDITO_ZERO = (
    "Item com PIS/COFINS a alíquota zero/monofásica no XML. "
    "Sem impacto na auditoria do ICMS-ST; eventual CST/base de crédito no SPED deve ser revisado separadamente, sem excluir ST."
)
ACAO_REVISAR_ICMS = "ICMS-ST já está fora da base. Revisar o ICMS próprio em auditoria separada; não é pendência de ST."
ACAO_REVISAR_CST = (
    "XML sem tributação PIS/COFINS, mas SPED possui crédito. "
    "Revisão tributária separada; não alterar ST automaticamente."
)
ACAO_POSSIVEL_ST = "Validar vínculo e bases antes de excluir qualquer valor."
ACAO_REVISAR_VINCULO = "Revisar o vínculo entre a NF-e/XML e o item C170 antes de qualquer ajuste."
ACAO_REVISAR_BASE = "Revisar a composição da base; a diferença não coincide com ICMS próprio nem ICMS-ST."

_TOLERANCIA = Decimal("0.02")
_CSTS_ALIQUOTA_ZERO = {"04", "06"}
_NS = {"n": "http://www.portalfiscal.inf.br/nfe"}


@dataclass(frozen=True)
class ItemAuditoriaICMSSTPISCOFINS:
    status: str
    acao: str
    confianca_vinculo: str
    chave_nfe: str
    nf: str
    serie: str
    data: str
    fornecedor: str
    cnpj: str
    crt: str
    item: int
    codigo_xml: str
    codigo_sped: str
    descricao_xml: str
    descricao_sped: str
    ncm: str
    cfop_xml: str
    cfop_sped: str
    cst_icms_xml: str
    valor_icms: Decimal
    valor_icms_st: Decimal
    cst_pis_xml: str
    base_pis_xml: Decimal
    cst_pis_sped: str
    base_pis_sped: Decimal
    diferenca_base_pis: Decimal
    cst_cofins_xml: str
    base_cofins_xml: Decimal
    cst_cofins_sped: str
    base_cofins_sped: Decimal
    diferenca_base_cofins: Decimal
    qtd_xml: Decimal
    valor_item_xml: Decimal
    valor_item_sped: Decimal
    linha_c170: int


@dataclass
class ResultadoAuditoriaICMSSTPISCOFINS:
    itens: list[ItemAuditoriaICMSSTPISCOFINS]
    xmls_lidos: int = 0
    notas_xml: int = 0
    avisos: list[str] | None = None

    def resumo(self) -> dict:
        itens = self.itens
        notas = {i.chave_nfe for i in itens if i.chave_nfe}
        sem_credito_status = {STATUS_SEM_CREDITO, STATUS_SEM_CREDITO_ZERO}
        com_credito = [
            i for i in itens
            if (i.base_pis_sped > 0 or i.base_cofins_sped > 0) and i.status not in sem_credito_status
        ]
        por_status: dict[str, int] = {}
        for item in itens:
            por_status[item.status] = por_status.get(item.status, 0) + 1
        return {
            "notas_st": len(notas),
            "itens_st": len(itens),
            "icms_st_total": sum((i.valor_icms_st for i in itens), Decimal("0")),
            "itens_com_credito": len(com_credito),
            "icms_st_itens_com_credito": sum((i.valor_icms_st for i in com_credito), Decimal("0")),
            "ok": por_status.get(STATUS_OK, 0),
            "ok_revisar_icms": por_status.get(STATUS_REVISAR_ICMS, 0),
            "ok_icms_st": por_status.get(STATUS_OK, 0) + por_status.get(STATUS_REVISAR_ICMS, 0),
            "sem_credito": por_status.get(STATUS_SEM_CREDITO, 0) + por_status.get(STATUS_SEM_CREDITO_ZERO, 0),
            "sem_credito_aliquota_zero": por_status.get(STATUS_SEM_CREDITO_ZERO, 0),
            "revisar_icms": por_status.get(STATUS_REVISAR_ICMS, 0),
            "revisar_cst": por_status.get(STATUS_REVISAR_CST, 0),
            "possivel_st": por_status.get(STATUS_POSSIVEL_ST, 0),
            "revisar_vinculo": por_status.get(STATUS_REVISAR_VINCULO, 0),
            "revisar_base": por_status.get(STATUS_REVISAR_BASE, 0),
            "vinculos_altos": sum(1 for i in itens if i.confianca_vinculo == "ALTA"),
            "vinculos_medios": sum(1 for i in itens if i.confianca_vinculo == "MÉDIA"),
            "vinculos_baixos": sum(1 for i in itens if i.confianca_vinculo == "BAIXA"),
        }


@dataclass
class _ItemXML:
    item: int
    codigo: str
    descricao: str
    ncm: str
    cfop: str
    qtd: Decimal
    valor_item: Decimal
    cst_icms: str
    valor_icms: Decimal
    valor_icms_st: Decimal
    cst_pis: str
    base_pis: Decimal
    cst_cofins: str
    base_cofins: Decimal


@dataclass
class _DocumentoXML:
    chave: str
    nf: str
    serie: str
    data: str
    fornecedor: str
    cnpj: str
    crt: str
    itens: list[_ItemXML]


@dataclass
class _ItemSPED:
    linha: int
    item: int
    codigo: str
    descricao: str
    qtd: Decimal
    valor_item: Decimal
    cst_icms: str
    cfop: str
    cst_pis: str
    base_pis: Decimal
    cst_cofins: str
    base_cofins: Decimal


@dataclass
class _DocumentoSPED:
    chave: str
    itens: list[_ItemSPED]


class AuditoriaICMSSTPISCOFINSService:
    """Cruza XML de entrada × C100/C170 e classifica a composição das bases."""

    @classmethod
    def auditar(
        cls,
        caminho_sped: str,
        origem_xml: str,
        progresso: Optional[Callable[[str], None]] = None,
    ) -> ResultadoAuditoriaICMSSTPISCOFINS:
        sped = Path(caminho_sped)
        xml = Path(origem_xml)
        if not sped.is_file():
            raise FileNotFoundError("Selecione um arquivo SPED Contribuições válido.")
        if not xml.exists():
            raise FileNotFoundError("Selecione um ZIP, XML ou pasta de XMLs válida.")

        cls._progresso(progresso, "Lendo o SPED Contribuições...")
        documentos_sped = cls._ler_sped(sped)
        cls._progresso(progresso, "Lendo os XMLs de entrada...")
        documentos_xml, xmls_lidos = cls._ler_xmls(xml)

        itens: list[ItemAuditoriaICMSSTPISCOFINS] = []
        total_docs = max(len(documentos_xml), 1)
        for indice, documento_xml in enumerate(documentos_xml.values(), start=1):
            if progresso and (indice == 1 or indice == total_docs or indice % 10 == 0):
                cls._progresso(progresso, f"Cruzando NF-e {indice}/{total_docs}...")
            documento_sped = documentos_sped.get(documento_xml.chave)
            for item_xml in documento_xml.itens:
                # Etapa 1: somente ICMS-ST destacado na própria NF-e (vICMSST).
                if item_xml.valor_icms_st <= 0:
                    continue
                item_sped, confianca = cls._vincular_item(documento_sped, item_xml)
                itens.append(cls._classificar(documento_xml, item_xml, item_sped, confianca))

        itens.sort(key=lambda i: (i.data, i.nf.zfill(20), i.item, i.chave_nfe))
        avisos: list[str] = []
        if not itens:
            avisos.append("Nenhum item com vICMSST destacado foi localizado nos XMLs selecionados.")
        cls._progresso(progresso, "Auditoria concluída. Nenhum arquivo foi alterado.")
        return ResultadoAuditoriaICMSSTPISCOFINS(
            itens=itens,
            xmls_lidos=xmls_lidos,
            notas_xml=len(documentos_xml),
            avisos=avisos,
        )

    @staticmethod
    def _progresso(callback: Optional[Callable[[str], None]], texto: str) -> None:
        if callback:
            callback(texto)

    @classmethod
    def _ler_xmls(cls, origem: Path) -> tuple[dict[str, _DocumentoXML], int]:
        documentos: dict[str, _DocumentoXML] = {}
        xmls_lidos = 0
        for nome, conteudo in cls._iterar_xmls(origem):
            try:
                doc = cls._parse_xml(conteudo)
            except (ET.ParseError, ValueError):
                continue
            if doc is None or not doc.chave:
                continue
            documentos[doc.chave] = doc
            xmls_lidos += 1
        return documentos, xmls_lidos

    @staticmethod
    def _iterar_xmls(origem: Path) -> Iterable[tuple[str, bytes]]:
        if origem.is_dir():
            for arquivo in sorted(origem.rglob("*.xml")):
                try:
                    yield str(arquivo), arquivo.read_bytes()
                except OSError:
                    continue
            return
        if origem.suffix.lower() == ".zip":
            with zipfile.ZipFile(origem, "r") as zf:
                for nome in sorted(zf.namelist()):
                    if nome.lower().endswith(".xml") and not nome.endswith("/"):
                        try:
                            yield nome, zf.read(nome)
                        except (KeyError, OSError):
                            continue
            return
        if origem.suffix.lower() == ".xml":
            yield str(origem), origem.read_bytes()
            return
        raise ValueError("A origem dos XMLs deve ser uma pasta, um arquivo .ZIP ou um arquivo .XML.")

    @classmethod
    def _parse_xml(cls, conteudo: bytes) -> Optional[_DocumentoXML]:
        raiz = ET.fromstring(conteudo)
        inf = raiz.find(".//n:infNFe", _NS)
        if inf is None:
            return None
        chave = (inf.attrib.get("Id") or "").replace("NFe", "", 1).strip()
        if not chave:
            chave = cls._texto(raiz, ".//n:protNFe/n:infProt/n:chNFe")
        ide = inf.find("n:ide", _NS)
        emit = inf.find("n:emit", _NS)
        if ide is None or emit is None:
            return None
        data = (cls._texto(ide, "n:dhEmi") or cls._texto(ide, "n:dEmi"))[:10]
        itens: list[_ItemXML] = []
        for det in inf.findall("n:det", _NS):
            prod = det.find("n:prod", _NS)
            imposto = det.find("n:imposto", _NS)
            if prod is None or imposto is None:
                continue
            icms = imposto.find("n:ICMS", _NS)
            tipo_icms = list(icms)[0] if icms is not None and len(list(icms)) else None
            pis = imposto.find("n:PIS", _NS)
            tipo_pis = list(pis)[0] if pis is not None and len(list(pis)) else None
            cofins = imposto.find("n:COFINS", _NS)
            tipo_cofins = list(cofins)[0] if cofins is not None and len(list(cofins)) else None
            cst_icms = cls._texto(tipo_icms, "n:CST") if tipo_icms is not None else ""
            if not cst_icms and tipo_icms is not None:
                cst_icms = cls._texto(tipo_icms, "n:CSOSN")
            try:
                numero_item = int(det.attrib.get("nItem") or "0")
            except ValueError:
                numero_item = 0
            itens.append(
                _ItemXML(
                    item=numero_item,
                    codigo=cls._texto(prod, "n:cProd"),
                    descricao=cls._texto(prod, "n:xProd"),
                    ncm=cls._texto(prod, "n:NCM"),
                    cfop=cls._texto(prod, "n:CFOP"),
                    qtd=cls._decimal(cls._texto(prod, "n:qCom")),
                    valor_item=cls._decimal(cls._texto(prod, "n:vProd")),
                    cst_icms=cst_icms,
                    valor_icms=cls._decimal(cls._texto(tipo_icms, "n:vICMS")) if tipo_icms is not None else Decimal("0"),
                    valor_icms_st=cls._decimal(cls._texto(tipo_icms, "n:vICMSST")) if tipo_icms is not None else Decimal("0"),
                    cst_pis=cls._texto(tipo_pis, "n:CST") if tipo_pis is not None else "",
                    base_pis=cls._decimal(cls._texto(tipo_pis, "n:vBC")) if tipo_pis is not None else Decimal("0"),
                    cst_cofins=cls._texto(tipo_cofins, "n:CST") if tipo_cofins is not None else "",
                    base_cofins=cls._decimal(cls._texto(tipo_cofins, "n:vBC")) if tipo_cofins is not None else Decimal("0"),
                )
            )
        return _DocumentoXML(
            chave=chave,
            nf=cls._texto(ide, "n:nNF"),
            serie=cls._texto(ide, "n:serie"),
            data=data,
            fornecedor=cls._texto(emit, "n:xNome"),
            cnpj=cls._texto(emit, "n:CNPJ"),
            crt=cls._texto(emit, "n:CRT"),
            itens=itens,
        )

    @classmethod
    def _ler_sped(cls, caminho: Path) -> dict[str, _DocumentoSPED]:
        documentos: dict[str, _DocumentoSPED] = {}
        atual: Optional[_DocumentoSPED] = None
        with caminho.open("r", encoding="latin-1", errors="replace") as arquivo:
            for numero_linha, linha in enumerate(arquivo, start=1):
                campos = linha.rstrip("\r\n").split("|")
                if len(campos) < 2:
                    continue
                registro = campos[1]
                if registro == "C100":
                    atual = None
                    # C100 campo 02 IND_OPER = 0: entrada/aquisição.
                    if len(campos) > 9 and campos[2] == "0" and campos[9]:
                        atual = _DocumentoSPED(chave=campos[9].strip(), itens=[])
                        documentos[atual.chave] = atual
                elif registro == "C170" and atual is not None:
                    if len(campos) < 33:
                        continue
                    try:
                        item = int(campos[2] or "0")
                    except ValueError:
                        item = 0
                    atual.itens.append(
                        _ItemSPED(
                            linha=numero_linha,
                            item=item,
                            codigo=campos[3].strip(),
                            descricao=campos[4].strip(),
                            qtd=cls._decimal(campos[5]),
                            valor_item=cls._decimal(campos[7]),
                            cst_icms=campos[10].strip(),
                            cfop=campos[11].strip(),
                            cst_pis=campos[25].strip(),
                            base_pis=cls._decimal(campos[26]),
                            cst_cofins=campos[31].strip(),
                            base_cofins=cls._decimal(campos[32]),
                        )
                    )
        return documentos

    @classmethod
    def _vincular_item(
        cls, documento_sped: Optional[_DocumentoSPED], item_xml: _ItemXML
    ) -> tuple[Optional[_ItemSPED], str]:
        if documento_sped is None:
            return None, "BAIXA"
        pelo_numero = [i for i in documento_sped.itens if i.item == item_xml.item]
        if pelo_numero:
            item = pelo_numero[0]
            codigo_igual = cls._normalizar_codigo(item.codigo) == cls._normalizar_codigo(item_xml.codigo)
            qtd_igual = cls._proximo(item.qtd, item_xml.qtd, Decimal("0.0001"))
            valor_igual = cls._proximo(item.valor_item, item_xml.valor_item)
            # Regra reproduz a auditoria validada de julho/2026:
            # código coerente OU quantidade+valor coerentes = vínculo alto.
            if codigo_igual or (qtd_igual and valor_igual):
                return item, "ALTA"
            if valor_igual:
                return item, "MÉDIA"
            return item, "BAIXA"

        codigo = cls._normalizar_codigo(item_xml.codigo)
        candidatos = [
            i
            for i in documento_sped.itens
            if cls._normalizar_codigo(i.codigo) == codigo and cls._proximo(i.valor_item, item_xml.valor_item)
        ]
        if len(candidatos) == 1:
            return candidatos[0], "MÉDIA"
        candidatos = [
            i
            for i in documento_sped.itens
            if cls._proximo(i.valor_item, item_xml.valor_item)
            and cls._proximo(i.qtd, item_xml.qtd, Decimal("0.0001"))
        ]
        if len(candidatos) == 1:
            return candidatos[0], "BAIXA"
        return None, "BAIXA"

    @classmethod
    def _classificar(
        cls,
        documento_xml: _DocumentoXML,
        item_xml: _ItemXML,
        item_sped: Optional[_ItemSPED],
        confianca: str,
    ) -> ItemAuditoriaICMSSTPISCOFINS:
        if item_sped is None:
            status, acao = STATUS_REVISAR_VINCULO, ACAO_REVISAR_VINCULO
            base_pis_sped = base_cofins_sped = Decimal("0")
            cst_pis_sped = cst_cofins_sped = cfop_sped = codigo_sped = descricao_sped = ""
            valor_item_sped = Decimal("0")
            linha_c170 = 0
        else:
            base_pis_sped = item_sped.base_pis
            base_cofins_sped = item_sped.base_cofins
            cst_pis_sped = item_sped.cst_pis
            cst_cofins_sped = item_sped.cst_cofins
            cfop_sped = item_sped.cfop
            codigo_sped = item_sped.codigo
            descricao_sped = item_sped.descricao
            valor_item_sped = item_sped.valor_item
            linha_c170 = item_sped.linha

            dif_pis = base_pis_sped - item_xml.base_pis
            dif_cofins = base_cofins_sped - item_xml.base_cofins

            if base_pis_sped <= 0 and base_cofins_sped <= 0:
                status, acao = STATUS_SEM_CREDITO, ACAO_SEM_CREDITO
            elif cls._item_aliquota_zero(item_xml):
                status, acao = STATUS_SEM_CREDITO_ZERO, ACAO_SEM_CREDITO_ZERO
            elif item_xml.base_pis <= 0 and item_xml.base_cofins <= 0:
                status, acao = STATUS_REVISAR_CST, ACAO_REVISAR_CST
            elif cls._proximo(base_pis_sped, item_xml.base_pis) and cls._proximo(base_cofins_sped, item_xml.base_cofins):
                status, acao = STATUS_OK, ACAO_OK
            elif cls._proximo(dif_pis, item_xml.valor_icms) and cls._proximo(dif_cofins, item_xml.valor_icms):
                status, acao = STATUS_REVISAR_ICMS, ACAO_REVISAR_ICMS
            elif (
                confianca in {"ALTA", "MÉDIA"}
                and cls._proximo(dif_pis, item_xml.valor_icms_st)
                and cls._proximo(dif_cofins, item_xml.valor_icms_st)
            ):
                status, acao = STATUS_POSSIVEL_ST, ACAO_POSSIVEL_ST
            else:
                status, acao = STATUS_REVISAR_BASE, ACAO_REVISAR_BASE

        diferenca_pis = base_pis_sped - item_xml.base_pis
        diferenca_cofins = base_cofins_sped - item_xml.base_cofins
        return ItemAuditoriaICMSSTPISCOFINS(
            status=status,
            acao=acao,
            confianca_vinculo=confianca,
            chave_nfe=documento_xml.chave,
            nf=documento_xml.nf,
            serie=documento_xml.serie,
            data=documento_xml.data,
            fornecedor=documento_xml.fornecedor,
            cnpj=documento_xml.cnpj,
            crt=documento_xml.crt,
            item=item_xml.item,
            codigo_xml=item_xml.codigo,
            codigo_sped=codigo_sped,
            descricao_xml=item_xml.descricao,
            descricao_sped=descricao_sped,
            ncm=item_xml.ncm,
            cfop_xml=item_xml.cfop,
            cfop_sped=cfop_sped,
            cst_icms_xml=item_xml.cst_icms,
            valor_icms=item_xml.valor_icms,
            valor_icms_st=item_xml.valor_icms_st,
            cst_pis_xml=item_xml.cst_pis,
            base_pis_xml=item_xml.base_pis,
            cst_pis_sped=cst_pis_sped,
            base_pis_sped=base_pis_sped,
            diferenca_base_pis=diferenca_pis,
            cst_cofins_xml=item_xml.cst_cofins,
            base_cofins_xml=item_xml.base_cofins,
            cst_cofins_sped=cst_cofins_sped,
            base_cofins_sped=base_cofins_sped,
            diferenca_base_cofins=diferenca_cofins,
            qtd_xml=item_xml.qtd,
            valor_item_xml=item_xml.valor_item,
            valor_item_sped=valor_item_sped,
            linha_c170=linha_c170,
        )

    @staticmethod
    def _item_aliquota_zero(item_xml: _ItemXML) -> bool:
        """Reconhece CSTs de alíquota zero/monofásica sem base no XML.

        O reconhecimento serve apenas para retirar o item das pendências da
        auditoria de ICMS-ST. Ele não valida nem corrige eventual crédito
        escriturado no SPED Contribuições.
        """
        return (
            item_xml.base_pis <= 0
            and item_xml.base_cofins <= 0
            and item_xml.cst_pis in _CSTS_ALIQUOTA_ZERO
            and item_xml.cst_cofins in _CSTS_ALIQUOTA_ZERO
        )

    @staticmethod
    def _texto(no: Optional[ET.Element], caminho: str) -> str:
        if no is None:
            return ""
        encontrado = no.find(caminho, _NS)
        if encontrado is None or encontrado.text is None:
            return ""
        return encontrado.text.strip()

    @staticmethod
    def _decimal(valor: object) -> Decimal:
        texto = str(valor or "").strip()
        if not texto:
            return Decimal("0")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            return Decimal(texto)
        except InvalidOperation:
            return Decimal("0")

    @staticmethod
    def _normalizar_codigo(valor: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(valor or "").upper())

    @staticmethod
    def _proximo(a: Decimal, b: Decimal, tolerancia: Decimal = _TOLERANCIA) -> bool:
        return abs(a - b) <= tolerancia
