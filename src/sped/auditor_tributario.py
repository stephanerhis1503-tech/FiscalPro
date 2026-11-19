"""Auditoria tributária integrada do SPED — Sprint 13.5.

Cruza o cadastro 0200, os itens C170, XMLs de NF-e (quando importados) e as
regras da Ficha Tributária Inteligente. O módulo é somente leitura: nenhuma
linha do SPED ou XML é alterada.
"""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from src.banco.conexao import Banco
from src.modelos.registro_0200 import Registro0200
from src.modelos.registro_c170 import RegistroC170
from src.parecer.motor_parecer import MotorParecer
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository

ProgressoCallback = Callable[[int, str], None]


# Código inicial do município IBGE -> UF.
_UF_POR_PREFIXO_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _numero(valor: Any) -> float:
    if valor in (None, ""):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("%", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except (TypeError, ValueError):
        return 0.0


def _numero_br(valor: Any) -> str:
    numero = _numero(valor)
    texto = f"{numero:.6f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",") if texto else "0"


def _data_iso_sped(valor: Any) -> str:
    texto = _digitos(valor)
    if len(texto) != 8:
        return ""
    try:
        return datetime.strptime(texto, "%d%m%Y").date().isoformat()
    except ValueError:
        return ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _filho(elemento: Optional[ET.Element], nome: str) -> Optional[ET.Element]:
    if elemento is None:
        return None
    for filho in list(elemento):
        if _local(filho.tag) == nome:
            return filho
    return None


def _descendente(elemento: Optional[ET.Element], nome: str) -> Optional[ET.Element]:
    if elemento is None:
        return None
    for item in elemento.iter():
        if _local(item.tag) == nome:
            return item
    return None


def _valor_filho(elemento: Optional[ET.Element], nome: str) -> str:
    filho = _filho(elemento, nome)
    return _texto(filho.text if filho is not None else "")


def _valor_descendente(elemento: Optional[ET.Element], nome: str) -> str:
    filho = _descendente(elemento, nome)
    return _texto(filho.text if filho is not None else "")


@dataclass(slots=True)
class ItemXMLNFe:
    numero_item: str
    codigo: str
    descricao: str
    ncm: str
    cest: str
    cfop: str
    cst_icms: str
    aliquota_icms: float
    cst_pis: str
    aliquota_pis: float
    cst_cofins: str
    aliquota_cofins: float
    cst_ipi: str
    aliquota_ipi: float
    # Sprint 17.4.0 — memória do grupo ICMSUFDest para auditoria automática de DIFAL.
    valor_produto: float = 0.0
    tem_icms_uf_dest: bool = False
    base_difal: float = 0.0
    base_fcp_difal: float = 0.0
    aliquota_fcp_destino: float = 0.0
    aliquota_icms_destino: float = 0.0
    aliquota_icms_interestadual: float = 0.0
    percentual_partilha_destino: float = 0.0
    valor_fcp_destino: float = 0.0
    valor_icms_destino: float = 0.0
    valor_icms_remetente: float = 0.0


@dataclass(slots=True)
class DocumentoXMLNFe:
    chave: str
    numero: str
    serie: str
    emitente_cnpj: str
    destinatario_cnpj: str
    arquivo_origem: str
    itens: list[ItemXMLNFe] = field(default_factory=list)
    # Dados de enquadramento do DIFAL extraídos do XML autorizado.
    uf_emitente: str = ""
    uf_destinatario: str = ""
    id_destino: str = ""
    consumidor_final: bool = False
    indicador_ie_dest: str = ""
    destinatario_contribuinte: Optional[bool] = None
    valor_nota: float = 0.0
    modelo: str = "55"

    def localizar_item(self, numero_item: str, codigo: str) -> Optional[ItemXMLNFe]:
        """Correlacao conservadora; evita fallback incorreto quando nItem diverge."""
        numero_item = _texto(numero_item)
        codigo = _texto(codigo).upper()
        if numero_item:
            encontrados = [item for item in self.itens if _texto(item.numero_item) == numero_item]
            if len(encontrados) == 1:
                return encontrados[0]
            # Se o item numerado nao existe no XML, nao presumir que um
            # cProd identico (que pode ser reutilizado) representa a mesma linha.
            return None
        if codigo:
            encontrados = [item for item in self.itens if _texto(item.codigo).upper() == codigo]
            if len(encontrados) == 1:
                return encontrados[0]
        return None


@dataclass(slots=True)
class ResultadoImportacaoXMLNFe:
    """Lote acumulado de NF-e 55 e NFC-e 65, separado por modelo."""
    documentos: dict[str, DocumentoXMLNFe] = field(default_factory=dict)
    documentos_nfce: dict[str, DocumentoXMLNFe] = field(default_factory=dict)
    fontes_importadas: list[str] = field(default_factory=list)
    total_fontes: int = 0
    total_arquivos_xml: int = 0
    total_nfe_validas: int = 0
    total_nfce_validas: int = 0
    total_duplicadas: int = 0
    total_ignoradas: int = 0
    total_erros: int = 0
    erros: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ApontamentoAuditoriaTributaria:
    nivel: str
    origem: str
    linha: int
    registro: str
    documento: str
    chave: str
    item: str
    codigo: str
    descricao: str
    ncm: str
    campo: str
    atual: str
    esperado: str
    regra_id: str
    aderencia: float
    mensagem: str
    orientacao: str


@dataclass(slots=True)
class ResultadoAuditoriaTributaria:
    total_itens: int = 0
    itens_com_0200: int = 0
    itens_sem_0200: int = 0
    itens_com_regra: int = 0
    itens_sem_regra: int = 0
    itens_com_xml: int = 0
    itens_sem_xml: int = 0
    notas_com_xml: int = 0
    notas_sem_xml: int = 0
    erros: int = 0
    avisos: int = 0
    divergencias_ficha: int = 0
    divergencias_xml: int = 0
    ncms_validos_unicos: int = 0
    ncms_com_regra_cadastrada: int = 0
    diagnostico_regras: str = ""
    referencias_fiscais: list[dict[str, Any]] = field(default_factory=list)
    itens_ncm_oficial_localizados: int = 0
    itens_ncm_nao_localizados: int = 0
    consultas_fiscais_com_falha: int = 0
    xml_importado: bool = False
    xml_validos_importados: int = 0
    nfce_validas_importadas: int = 0
    xml_ignorados_importacao: int = 0
    xml_erros_importacao: int = 0
    notas_sped_chaves_unicas: int = 0
    notas_sped_chaves_por_mes: dict[str, int] = field(default_factory=dict)
    notas_sped_chaves_coincidentes: int = 0
    notas_c170_chaves_unicas: int = 0
    notas_c170_chaves_coincidentes: int = 0
    c170_notas_entrada: int = 0
    c170_notas_saida: int = 0
    c170_notas_entrada_com_xml: int = 0
    c170_notas_saida_com_xml: int = 0
    xml_importados_c100_sem_c170: int = 0
    documentos_c170: list[dict[str, Any]] = field(default_factory=list)
    documentos_xml_importados: list[dict[str, Any]] = field(default_factory=list)
    diagnostico_xml: str = ""
    apontamentos: list[ApontamentoAuditoriaTributaria] = field(default_factory=list)
    contexto: dict[str, str] = field(default_factory=dict)

    @property
    def total_apontamentos(self) -> int:
        return len(self.apontamentos)

    @property
    def cobertura_regras(self) -> float:
        if self.total_itens <= 0:
            return 0.0
        return round(100.0 * self.itens_com_regra / self.total_itens, 2)

    @property
    def auditoria_tributaria_inconclusiva(self) -> bool:
        return self.total_itens == 0 or self.itens_com_regra == 0

    @property
    def conformidade_exibicao(self) -> str:
        if self.auditoria_tributaria_inconclusiva:
            return "NAO AVALIAVEL - sem regras tributarias aplicadas"
        return f"{self.conformidade:.2f}% (cobertura de regras: {self.cobertura_regras:.2f}%)".replace(".", ",")

    @property
    def conformidade(self) -> float:
        """Indicador parcial: nunca representa homologacao tributaria integral."""
        if self.total_itens <= 0:
            return 0.0
        itens_com_problema = len({(a.linha, a.codigo) for a in self.apontamentos if a.nivel == "ERRO"})
        return round(max(0.0, 100.0 - (itens_com_problema / self.total_itens * 100.0)), 2)


class ImportadorXMLNFe:
    """Lê NF-e avulsas, pastas e ZIPs sem alterar os documentos."""

    def importar(
        self,
        fontes: Iterable[str | Path],
        progresso: ProgressoCallback | None = None,
        anterior: ResultadoImportacaoXMLNFe | None = None,
    ) -> ResultadoImportacaoXMLNFe:
        """Acumula pastas/ZIPs sem perder documentos da mesma sessao SPED.

        Chaves duplicadas nao sao somadas duas vezes. NF-e modelo 55 fica em
        documentos (usado pelo C100/DIFAL); NFC-e 65 fica isolada para nao
        produzir falsos cruzamentos com C170.
        """
        resultado = anterior if anterior is not None else ResultadoImportacaoXMLNFe()
        fontes = [Path(fonte) for fonte in fontes]
        ja_importadas = set(resultado.fontes_importadas)
        candidatos: list[tuple[str, bytes]] = []

        self._progresso(progresso, 5, "Localizando XMLs de NF-e e NFC-e...")
        for fonte in fontes:
            chave_fonte = str(fonte.expanduser().resolve()).casefold()
            if chave_fonte in ja_importadas:
                continue
            if fonte.is_dir():
                for arquivo in fonte.rglob("*"):
                    if arquivo.is_file() and arquivo.suffix.lower() in {".xml", ".zip"}:
                        candidatos.extend(self._ler_fonte(arquivo, resultado))
            elif fonte.is_file():
                candidatos.extend(self._ler_fonte(fonte, resultado))
            else:
                resultado.total_erros += 1
                resultado.erros.append(f"Fonte não encontrada: {fonte}")
                continue
            resultado.fontes_importadas.append(chave_fonte)
            ja_importadas.add(chave_fonte)

        resultado.total_fontes = len(resultado.fontes_importadas)
        total = max(1, len(candidatos))
        for indice, (origem, conteudo) in enumerate(candidatos, start=1):
            try:
                documento = self._interpretar_xml(conteudo, origem)
                resultado.total_arquivos_xml += 1
                if documento is None:
                    resultado.total_ignoradas += 1
                    continue
                destino = (
                    resultado.documentos_nfce
                    if documento.modelo == "65" else resultado.documentos
                )
                if documento.chave in destino:
                    resultado.total_duplicadas += 1
                    continue
                destino[documento.chave] = documento
                if documento.modelo == "65":
                    resultado.total_nfce_validas += 1
                else:
                    resultado.total_nfe_validas += 1
            except Exception as erro:  # XML inválido não deve interromper o lote.
                resultado.total_erros += 1
                resultado.erros.append(f"{origem}: {erro}")
            percentual = 15 + int(indice / total * 80)
            self._progresso(progresso, percentual, f"XMLs lidos: {indice:,}/{total:,}")

        self._progresso(progresso, 100, "XMLs acumulados na auditoria.")
        return resultado

    def _ler_fonte(
        self, arquivo: Path, resultado: ResultadoImportacaoXMLNFe
    ) -> list[tuple[str, bytes]]:
        if arquivo.suffix.lower() == ".xml":
            try:
                return [(str(arquivo), arquivo.read_bytes())]
            except OSError as erro:
                resultado.total_erros += 1
                resultado.erros.append(f"{arquivo}: {erro}")
                return []
        if arquivo.suffix.lower() == ".zip":
            itens: list[tuple[str, bytes]] = []
            try:
                with zipfile.ZipFile(arquivo) as pacote:
                    for nome in pacote.namelist():
                        if nome.lower().endswith(".xml") and not nome.endswith("/"):
                            itens.append((f"{arquivo.name}::{nome}", pacote.read(nome)))
            except (OSError, zipfile.BadZipFile, RuntimeError) as erro:
                resultado.total_erros += 1
                resultado.erros.append(f"{arquivo}: {erro}")
            return itens
        return []

    def _interpretar_xml(self, conteudo: bytes, origem: str) -> Optional[DocumentoXMLNFe]:
        raiz = ET.parse(io.BytesIO(conteudo)).getroot()
        inf_nfe = _descendente(raiz, "infNFe")
        if inf_nfe is None:
            return None

        chave = _digitos(inf_nfe.attrib.get("Id", ""))
        if len(chave) != 44:
            chave = _digitos(_valor_descendente(raiz, "chNFe"))
        if len(chave) != 44:
            return None

        ide = _filho(inf_nfe, "ide")
        modelo_informado = _valor_filho(ide, "mod")
        # Na ausencia da tag mod, usar apenas modelo conhecido na chave;
        # manter o comportamento legado para documentos de teste sem modelo.
        modelo = modelo_informado or (chave[20:22] if chave[20:22] in {"55", "65"} else "55")
        if modelo not in {"55", "65"}:
            return None
        emit = _filho(inf_nfe, "emit")
        dest = _filho(inf_nfe, "dest")
        ender_emit = _filho(emit, "enderEmit")
        ender_dest = _filho(dest, "enderDest")
        ind_ie_dest = _valor_filho(dest, "indIEDest")
        contribuinte_dest: Optional[bool]
        if ind_ie_dest == "1":
            contribuinte_dest = True
        elif ind_ie_dest == "9":
            contribuinte_dest = False
        else:
            contribuinte_dest = None
        documento = DocumentoXMLNFe(
            chave=chave,
            numero=_valor_filho(ide, "nNF"),
            serie=_valor_filho(ide, "serie"),
            emitente_cnpj=_digitos(_valor_filho(emit, "CNPJ") or _valor_filho(emit, "CPF")),
            destinatario_cnpj=_digitos(_valor_filho(dest, "CNPJ") or _valor_filho(dest, "CPF")),
            arquivo_origem=origem,
            uf_emitente=_valor_filho(ender_emit, "UF").upper(),
            uf_destinatario=_valor_filho(ender_dest, "UF").upper(),
            id_destino=_valor_filho(ide, "idDest"),
            consumidor_final=_valor_filho(ide, "indFinal") == "1",
            indicador_ie_dest=ind_ie_dest,
            destinatario_contribuinte=contribuinte_dest,
            valor_nota=_numero(_valor_descendente(_filho(inf_nfe, "total"), "vNF")),
            modelo=modelo,
        )

        for det in list(inf_nfe):
            if _local(det.tag) != "det":
                continue
            prod = _filho(det, "prod")
            imposto = _filho(det, "imposto")
            if prod is None:
                continue
            icms_uf_dest = _filho(imposto, "ICMSUFDest")
            documento.itens.append(
                ItemXMLNFe(
                    numero_item=_texto(det.attrib.get("nItem", "")),
                    codigo=_valor_filho(prod, "cProd"),
                    descricao=_valor_filho(prod, "xProd"),
                    ncm=_digitos(_valor_filho(prod, "NCM")),
                    cest=_digitos(_valor_filho(prod, "CEST")),
                    cfop=_digitos(_valor_filho(prod, "CFOP")),
                    cst_icms=self._cst_grupo(imposto, "ICMS", ("CST", "CSOSN")),
                    aliquota_icms=self._aliquota_grupo(imposto, "ICMS", "pICMS"),
                    cst_pis=self._cst_grupo(imposto, "PIS", ("CST",)),
                    aliquota_pis=self._aliquota_grupo(imposto, "PIS", "pPIS"),
                    cst_cofins=self._cst_grupo(imposto, "COFINS", ("CST",)),
                    aliquota_cofins=self._aliquota_grupo(imposto, "COFINS", "pCOFINS"),
                    cst_ipi=self._cst_grupo(imposto, "IPI", ("CST",)),
                    aliquota_ipi=self._aliquota_grupo(imposto, "IPI", "pIPI"),
                    valor_produto=_numero(_valor_filho(prod, "vProd")),
                    tem_icms_uf_dest=icms_uf_dest is not None,
                    base_difal=_numero(_valor_filho(icms_uf_dest, "vBCUFDest")),
                    base_fcp_difal=_numero(
                        _valor_filho(icms_uf_dest, "vBCFCPUFDest")
                        or _valor_filho(icms_uf_dest, "vBCUFDest")
                    ),
                    aliquota_fcp_destino=_numero(_valor_filho(icms_uf_dest, "pFCPUFDest")),
                    aliquota_icms_destino=_numero(_valor_filho(icms_uf_dest, "pICMSUFDest")),
                    aliquota_icms_interestadual=_numero(_valor_filho(icms_uf_dest, "pICMSInter")),
                    percentual_partilha_destino=_numero(_valor_filho(icms_uf_dest, "pICMSInterPart")),
                    valor_fcp_destino=_numero(_valor_filho(icms_uf_dest, "vFCPUFDest")),
                    valor_icms_destino=_numero(_valor_filho(icms_uf_dest, "vICMSUFDest")),
                    valor_icms_remetente=_numero(_valor_filho(icms_uf_dest, "vICMSUFRemet")),
                )
            )
        return documento

    @staticmethod
    def _grupo_imposto(imposto: Optional[ET.Element], grupo: str) -> Optional[ET.Element]:
        raiz_grupo = _filho(imposto, grupo)
        if raiz_grupo is None:
            return None
        # ICMS, PIS, COFINS e IPI guardam a tributação em um filho variável.
        # No IPI pode existir cEnq antes de IPITrib/IPINT; por isso procuramos
        # primeiro o filho que realmente contém CST ou a alíquota.
        filhos = list(raiz_grupo)
        for filho in filhos:
            if _descendente(filho, "CST") is not None or _descendente(filho, "CSOSN") is not None:
                return filho
        for filho in filhos:
            if list(filho):
                return filho
        return raiz_grupo

    @classmethod
    def _cst_grupo(
        cls, imposto: Optional[ET.Element], grupo: str, campos: tuple[str, ...]
    ) -> str:
        elemento = cls._grupo_imposto(imposto, grupo)
        for campo in campos:
            valor = _valor_descendente(elemento, campo)
            if valor:
                return _digitos(valor)
        return ""

    @classmethod
    def _aliquota_grupo(cls, imposto: Optional[ET.Element], grupo: str, campo: str) -> float:
        elemento = cls._grupo_imposto(imposto, grupo)
        return _numero(_valor_descendente(elemento, campo))

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(max(0, min(100, percentual)), mensagem)


class AuditorTributarioSPED:
    """Executa o cruzamento tributário item a item."""

    CAMPOS_REGRA = (
        ("CFOP", "cfop", "cfop", "texto"),
        ("CST ICMS", "cst_icms", "cst_icms", "texto"),
        ("Alíquota ICMS", "aliquota_icms", "icms", "numero"),
        ("CST PIS", "cst_pis", "cst_pis", "texto"),
        ("Alíquota PIS", "aliquota_pis", "aliquota_pis", "numero"),
        ("CST COFINS", "cst_cofins", "cst_cofins", "texto"),
        ("Alíquota COFINS", "aliquota_cofins", "aliquota_cofins", "numero"),
        ("CST IPI", "cst_ipi", "cst_ipi", "texto"),
        ("Alíquota IPI", "aliquota_ipi", "ipi", "numero"),
    )

    CAMPOS_XML = (
        ("NCM", "ncm", "ncm", "texto"),
        ("CEST", "cest", "cest", "texto"),
        ("CFOP", "cfop", "cfop", "texto"),
        ("CST ICMS", "cst_icms", "cst_icms", "texto"),
        ("Alíquota ICMS", "aliquota_icms", "aliquota_icms", "numero"),
        ("CST PIS", "cst_pis", "cst_pis", "texto"),
        ("Alíquota PIS", "aliquota_pis", "aliquota_pis", "numero"),
        ("CST COFINS", "cst_cofins", "cst_cofins", "texto"),
        ("Alíquota COFINS", "aliquota_cofins", "aliquota_cofins", "numero"),
        ("CST IPI", "cst_ipi", "cst_ipi", "texto"),
        ("Alíquota IPI", "aliquota_ipi", "aliquota_ipi", "numero"),
    )

    def auditar(
        self,
        linhas: list[str],
        tipo_sped: str,
        empresa_sped: str,
        contexto_padrao: Optional[dict[str, Any]] = None,
        importacao_xml: Optional[ResultadoImportacaoXMLNFe] = None,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAuditoriaTributaria:
        contexto_padrao = dict(contexto_padrao or {})
        resultado = ResultadoAuditoriaTributaria(
            contexto={
                "empresa": _texto(contexto_padrao.get("empresa") or empresa_sped),
                "regime": _texto(contexto_padrao.get("regime")),
                "finalidade": _texto(contexto_padrao.get("finalidade")),
                "contribuinte": _texto(contexto_padrao.get("contribuinte") or "AUTOMÁTICO"),
            }
        )
        self._progresso(progresso, 3, "Preparando cadastros do SPED...")

        cadastros, duplicados_0200 = self._carregar_0200(linhas)
        participantes = self._carregar_0150(linhas)
        uf_empresa = self._uf_empresa(linhas, tipo_sped)
        notas = self._carregar_notas_itens(linhas)
        total = max(1, sum(len(nota["itens"]) for nota in notas))
        xmls = importacao_xml.documentos if importacao_xml else {}
        resultado.xml_importado = importacao_xml is not None
        if importacao_xml is not None:
            resultado.xml_validos_importados = importacao_xml.total_nfe_validas
            resultado.nfce_validas_importadas = importacao_xml.total_nfce_validas
            resultado.xml_ignorados_importacao = importacao_xml.total_ignoradas
            resultado.xml_erros_importacao = importacao_xml.total_erros
        chaves_sped = {
            chave
            for nota in notas
            for chave in [_digitos(nota.get("chave"))]
            if len(chave) == 44
        }
        resultado.notas_sped_chaves_unicas = len(chaves_sped)
        resultado.notas_sped_chaves_coincidentes = len(chaves_sped.intersection(xmls))
        # A cobertura dos C170 precisa considerar apenas C100 com itens e
        # modelo NF-e 55. O C100 inteiro pode trazer documentos sem C170
        # e nao indica milhares de itens obrigatoriamente sem XML.
        chaves_c170 = {
            chave
            for nota in notas
            if nota.get("itens") and str(nota.get("modelo") or "").zfill(2) == "55"
            for chave in [_digitos(nota.get("chave"))]
            if len(chave) == 44
        }
        resultado.notas_c170_chaves_unicas = len(chaves_c170)
        resultado.notas_c170_chaves_coincidentes = len(chaves_c170.intersection(xmls))
        # Relatorio de rastreabilidade: chaves C100 com itens C170 versus XMLs
        # importados. Nao inferir que um documento sem C170 tenha XML faltante.
        vistos_c170: set[str] = set()
        for nota in notas:
            chave = _digitos(nota.get("chave"))
            if (
                str(nota.get("modelo") or "").zfill(2) != "55"
                or not nota.get("itens") or len(chave) != 44
                or chave in vistos_c170
            ):
                continue
            vistos_c170.add(chave)
            entrada = nota.get("ind_oper") == "0"
            xml = xmls.get(chave)
            if entrada:
                resultado.c170_notas_entrada += 1
                if xml:
                    resultado.c170_notas_entrada_com_xml += 1
            else:
                resultado.c170_notas_saida += 1
                if xml:
                    resultado.c170_notas_saida_com_xml += 1
            resultado.documentos_c170.append({
                "operacao": "ENTRADA" if entrada else "SAIDA",
                "numero": str(nota.get("numero") or ""),
                "serie": str(nota.get("serie") or ""),
                "chave": chave,
                "mes_chave": f"20{chave[2:4]}-{chave[4:6]}",
                "cnpj_emitente": chave[6:20],
                "itens_c170": len(nota.get("itens") or []),
                "situacao": "LOCALIZADO" if xml else "SEM XML CORRESPONDENTE",
                "origem_xml": xml.arquivo_origem if xml else "",
            })
        for chave, xml in sorted(xmls.items()):
            if chave in chaves_c170:
                situacao = "CORRESPONDE A C170"
            elif chave in chaves_sped:
                situacao = "NO C100 SEM C170"
                resultado.xml_importados_c100_sem_c170 += 1
            else:
                situacao = "SEM CHAVE C100 NO SPED"
            resultado.documentos_xml_importados.append({
                "numero": xml.numero,
                "serie": xml.serie,
                "chave": chave,
                "mes_chave": f"20{chave[2:4]}-{chave[4:6]}",
                "emitente": xml.emitente_cnpj,
                "destinatario": xml.destinatario_cnpj,
                "itens_xml": len(xml.itens),
                "situacao": situacao,
                "origem_xml": xml.arquivo_origem,
            })
        por_mes: dict[str, int] = {}
        for chave in chaves_sped:
            mes = f"20{chave[2:4]}-{chave[4:6]}"
            por_mes[mes] = por_mes.get(mes, 0) + 1
        resultado.notas_sped_chaves_por_mes = dict(sorted(por_mes.items()))
        ncms_usados = {
            cadastro.ncm
            for nota in notas
            for _numero_linha, linha_item in nota["itens"]
            for codigo in [RegistroC170(linha_item).codigo]
            for cadastro in [cadastros.get(codigo)]
            if cadastro is not None and len(cadastro.ncm) == 8
        }
        regras_contexto, regras_produto, ncms_com_base_legal = self._carregar_regras_lote(ncms_usados)
        resultado.ncms_validos_unicos = len(ncms_usados)
        resultado.ncms_com_regra_cadastrada = sum(
            1 for ncm in ncms_usados
            if regras_contexto.get(ncm)
            or any(chave[0] == ncm for chave in regras_produto)
        )
        cache_selecao: dict[tuple[str, ...], Any] = {}
        # Consultas oficiais em camada separada de regras operacionais.
        # Nao converte resultados em ERRO nem em sugestoes de correcao.
        from src.services.referencias_auditoria_sped_service import (
            ReferenciasAuditoriaSPEDService,
        )
        consulta_referencial = ReferenciasAuditoriaSPEDService()
        notas_xml_localizadas: set[str] = set()
        notas_xml_ausentes: set[str] = set()
        xml_ausente_emitido: set[str] = set()
        avisos_regra_emitidos: set[tuple[str, str, str]] = set()
        sem_regra_emitidos: set[tuple[str, str, str, str, str]] = set()

        for codigo in sorted(duplicados_0200):
            cadastro = cadastros.get(codigo)
            resultado.apontamentos.append(
                ApontamentoAuditoriaTributaria(
                    nivel="AVISO", origem="CADASTRO 0200", linha=0, registro="0200",
                    documento="", chave="", item="", codigo=codigo,
                    descricao=cadastro.descricao if cadastro else "", ncm=cadastro.ncm if cadastro else "",
                    campo="Código do produto", atual=codigo, esperado="Único",
                    regra_id="", aderencia=0,
                    mensagem="Código de produto duplicado no registro 0200.",
                    orientacao="Confira se os cadastros duplicados possuem os mesmos dados antes de corrigir.",
                )
            )

        processados = 0
        for nota in notas:
            chave = _digitos(nota["chave"])
            documento_xml = xmls.get(chave) if chave else None
            if importacao_xml is not None:
                if documento_xml:
                    notas_xml_localizadas.add(chave or nota["numero"])
                else:
                    notas_xml_ausentes.add(chave or nota["numero"])

            participante = participantes.get(nota["cod_part"], {})
            contexto_nota = self._contexto_nota(
                resultado.contexto,
                nota,
                participante,
                uf_empresa,
            )

            for numero_linha, linha_c170 in nota["itens"]:
                processados += 1
                item = RegistroC170(linha_c170)
                resultado.total_itens += 1
                cadastro = cadastros.get(item.codigo)
                if cadastro is None:
                    resultado.itens_sem_0200 += 1
                    self._adicionar(
                        resultado, "ERRO", "CADASTRO 0200", numero_linha, nota, item, "NCM",
                        "", "Cadastro 0200", "", 0,
                        "Produto utilizado no C170 sem cadastro correspondente no 0200.",
                        "Cadastre o produto no 0200 e informe NCM, unidade e descrição corretos.",
                    )
                    ncm = ""
                else:
                    resultado.itens_com_0200 += 1
                    item.vincular_cadastro(cadastro)
                    ncm = cadastro.ncm

                item_xml = documento_xml.localizar_item(item.numero_item, item.codigo) if documento_xml else None
                if item_xml:
                    resultado.itens_com_xml += 1
                    # cProd do fornecedor pode diferir do codigo interno, mas
                    # quando AMBOS codigo e NCM divergem, nItem isolado nao
                    # comprova que este e o mesmo produto.
                    vinculo_duvidoso = bool(
                        _texto(item.codigo).upper() != _texto(item_xml.codigo).upper()
                        and item.ncm and item_xml.ncm
                        and _digitos(item.ncm) != _digitos(item_xml.ncm)
                    )
                    if vinculo_duvidoso:
                        self._adicionar(
                            resultado, "AVISO", "XML NF-e", numero_linha, nota, item,
                            "Vinculo XML", item.codigo, item_xml.codigo, "", 0,
                            "Numero do item coincide, mas codigo e NCM divergem; vinculo nao confirmado.",
                            "Confira fisicamente a correspondencia antes de comparar ou corrigir NCM/CST.",
                        )
                    else:
                        self._comparar_xml(
                            resultado, numero_linha, nota, item, item_xml,
                            entrada=nota.get("ind_oper") == "0",
                        )
                elif importacao_xml is not None:
                    resultado.itens_sem_xml += 1
                    origem = "XML NF-e"
                    mensagem = (
                        "NF-e localizada, mas o item não foi associado ao XML."
                        if documento_xml else
                        "XML da NF-e não localizado pela chave do C100."
                    )
                    chave_aviso = chave or f"{nota.get('serie', '')}-{nota.get('numero', '')}"
                    if documento_xml or chave_aviso not in xml_ausente_emitido:
                        self._adicionar(
                            resultado, "AVISO", origem, numero_linha, nota, item, "XML",
                            item.numero_item, "Item correspondente", "", 0, mensagem,
                            "Confira a chave da NF-e e se o XML importado corresponde ao documento escriturado.",
                        )
                        xml_ausente_emitido.add(chave_aviso)

                if ncm and len(ncm) == 8:
                    # Referencias isoladas da Ficha: fontes oficiais sao
                    # evidencia documental, nunca regras operacionais criadas.
                    descricao_consulta = (
                        (cadastro.descricao if cadastro else "")
                        or item.descricao_complementar
                        or (item_xml.descricao if item_xml else "")
                    )
                    referencia = consulta_referencial.consultar_item(
                        ncm=ncm, descricao=descricao_consulta,
                        contexto=contexto_nota,
                        ex_tipi=cadastro.ex_ipi if cadastro else "",
                    )
                    referencia.update({
                        "linha_sped": numero_linha,
                        "nota": str(nota.get("numero") or ""),
                        "chave": str(nota.get("chave") or ""),
                        "item": str(item.numero_item or ""),
                        "codigo_produto": str(item.codigo or ""),
                        "cfop_sped": str(item.cfop or ""),
                        "descricao_sped": str(descricao_consulta or ""),
                    })
                    resultado.referencias_fiscais.append(referencia)
                    if referencia.get("ncm_status") == "NAO LOCALIZADO NA BASE INSTALADA":
                        resultado.itens_ncm_nao_localizados += 1
                    elif referencia.get("ncm_status") not in {
                        "FALHA NA CONSULTA DA BASE NCM", "NCM INVALIDO PARA CONSULTA",
                    }:
                        resultado.itens_ncm_oficial_localizados += 1
                    if referencia.get("falha_tecnica"):
                        resultado.consultas_fiscais_com_falha += 1
                    contexto_motor = MotorParecer._contexto_normalizado(contexto_nota)
                    chave_selecao = (
                        ncm,
                        _texto(item.codigo).upper(),
                        contexto_motor.get("empresa", ""),
                        contexto_motor.get("regime", ""),
                        contexto_motor.get("operacao", ""),
                        contexto_motor.get("finalidade", ""),
                        contexto_motor.get("uf_origem", ""),
                        contexto_motor.get("uf_destino", ""),
                        contexto_motor.get("contribuinte", ""),
                        contexto_motor.get("data_operacao", ""),
                    )
                    if chave_selecao not in cache_selecao:
                        candidatas = list(regras_contexto.get(ncm, []))
                        candidatas.extend(regras_produto.get((ncm, _texto(item.codigo).upper()), []))
                        candidatas.extend(regras_produto.get((ncm, ""), []))
                        cache_selecao[chave_selecao] = MotorParecer._selecionar_regra(
                            candidatas, contexto_motor
                        )
                    selecao = cache_selecao[chave_selecao]
                    if selecao.regra:
                        resultado.itens_com_regra += 1
                        self._comparar_regra(
                            resultado, numero_linha, nota, item, cadastro, selecao.regra,
                            selecao.aderencia,
                            confiavel=selecao.aderencia >= 60 and selecao.empatadas <= 1
                        )
                        regra_id = str(selecao.regra.get("id") or "")
                        if selecao.empatadas > 1:
                            self._adicionar(
                                resultado, "AVISO", "FICHA TRIBUTÁRIA", numero_linha, nota, item,
                                "Empate entre regras", str(selecao.empatadas), "Revisão manual",
                                regra_id, selecao.aderencia,
                                "Duas ou mais regras tributarias possuem a mesma pontuacao.",
                                "Verifique a vigencia e o contexto antes de corrigir os valores do SPED.",
                            )
                        if selecao.aderencia < 60 and (ncm, regra_id, "ADERENCIA") not in avisos_regra_emitidos:
                            self._adicionar(
                                resultado, "AVISO", "FICHA TRIBUTÁRIA", numero_linha, nota, item,
                                "Aderência da regra", f"{selecao.aderencia:.0f}%", "Regra mais específica",
                                regra_id, selecao.aderencia,
                                "A regra encontrada é genérica ou possui baixa aderência ao contexto da nota.",
                                "Cadastre uma regra com empresa, regime, UF, operação e finalidade mais específicos.",
                            )
                            avisos_regra_emitidos.add((ncm, regra_id, "ADERENCIA"))
                        if (
                            ncm not in ncms_com_base_legal
                            and not _texto(selecao.regra.get("fonte"))
                            and (ncm, regra_id, "BASE_LEGAL") not in avisos_regra_emitidos
                        ):
                            self._adicionar(
                                resultado, "AVISO", "BASE LEGAL", numero_linha, nota, item,
                                "Fundamentação", "Não cadastrada", "Fonte oficial",
                                regra_id, selecao.aderencia,
                                "A regra aplicada não possui fonte nem base legal cadastrada.",
                                "Abra a Ficha Tributária e vincule a norma oficial que fundamenta a tributação.",
                            )
                            avisos_regra_emitidos.add((ncm, regra_id, "BASE_LEGAL"))
                    else:
                        resultado.itens_sem_regra += 1
                        chave_sem_regra = (
                            ncm,
                            contexto_motor.get("operacao", ""),
                            contexto_motor.get("uf_origem", ""),
                            contexto_motor.get("uf_destino", ""),
                            contexto_motor.get("regime", ""),
                        )
                        if chave_sem_regra not in sem_regra_emitidos:
                            self._adicionar(
                                resultado, "AVISO", "FICHA TRIBUTÁRIA", numero_linha, nota, item,
                                "Regra tributária", "Não encontrada", "Regra vigente para o contexto",
                                "", 0,
                                "Nenhuma regra da Ficha Tributária atende ao NCM e ao contexto desta operação.",
                                "Abra a ficha do NCM e cadastre a tributação por empresa, UF, regime, operação e vigência.",
                            )
                            sem_regra_emitidos.add(chave_sem_regra)
                else:
                    resultado.itens_sem_regra += 1

                percentual = 8 + int(processados / total * 90)
                self._progresso(
                    progresso, percentual,
                    f"Auditando item {processados:,} de {total:,}...",
                )

        resultado.notas_com_xml = len(notas_xml_localizadas)
        resultado.notas_sem_xml = len(notas_xml_ausentes)
        resultado.erros = sum(1 for item in resultado.apontamentos if item.nivel == "ERRO")
        resultado.avisos = sum(1 for item in resultado.apontamentos if item.nivel == "AVISO")
        resultado.divergencias_ficha = sum(1 for item in resultado.apontamentos if item.origem == "FICHA TRIBUTÁRIA" and item.campo not in {"Regra tributária", "Aderência da regra"})
        resultado.divergencias_xml = sum(1 for item in resultado.apontamentos if item.origem == "XML NF-e" and item.campo != "XML")
        if resultado.total_itens and not resultado.itens_com_regra:
            if not resultado.ncms_validos_unicos:
                resultado.diagnostico_regras = (
                    "Nenhum NCM valido de 8 digitos foi obtido dos cadastros 0200 dos itens C170. "
                    "Confira a vinculacao entre C170 e 0200 e o cadastro de NCM."
                )
            elif not resultado.ncms_com_regra_cadastrada:
                resultado.diagnostico_regras = (
                    f"Nenhuma regra da Ficha Tributaria foi localizada no banco fiscalpro.db "
                    f"para os {resultado.ncms_validos_unicos} NCM(s) distintos do SPED. "
                    "Bases NCM/TIPI e ST oficiais nao substituem regras de operacao cadastradas."
                )
            else:
                resultado.diagnostico_regras = (
                    f"Ha regras cadastradas para {resultado.ncms_com_regra_cadastrada} "
                    f"de {resultado.ncms_validos_unicos} NCM(s), mas nenhuma foi aplicavel. "
                    "Confira empresa, regime, UF, finalidade e vigencia na Ficha Tributaria."
                )
        elif resultado.itens_sem_regra:
            resultado.diagnostico_regras = (
                f"Auditoria parcial: {resultado.itens_sem_regra} de "
                f"{resultado.total_itens} itens sem regra aplicavel. "
                "Os itens sem cobertura exigem revisao individual."
            )
        if resultado.referencias_fiscais:
            resultado.diagnostico_regras += (
                f" Camada referencial independente: "
                f"{len(resultado.referencias_fiscais)} itens consultados; "
                f"{resultado.itens_ncm_oficial_localizados} NCMs de itens localizados "
                f"na base oficial instalada e "
                f"{resultado.itens_ncm_nao_localizados} nao localizados. "
                "Consultas de PIS/Cofins e ICMS/MG estao na aba Referencias "
                "do Excel, sem gerar CST, creditos ou ajustes automaticos."
            )
        if resultado.total_itens and not _texto(resultado.contexto.get("regime")):
            resultado.diagnostico_regras += (
                " Regime tributario nao selecionado na tela da auditoria. "
                "Informe o regime real da empresa antes de reexecutar; "
                "isso nao cria regras tributarias ausentes no banco."
            )

        meses = ", ".join(
            f"{mes} ({qtd})"
            for mes, qtd in resultado.notas_sped_chaves_por_mes.items()
        ) or "nenhum periodo identificado"
        operacoes_c170 = (
            f"NF-e com C170: entrada {resultado.c170_notas_entrada} "
            f"(com XML {resultado.c170_notas_entrada_com_xml}), "
            f"saida {resultado.c170_notas_saida} "
            f"(com XML {resultado.c170_notas_saida_com_xml}). "
        )
        if not resultado.xml_importado:
            resultado.diagnostico_xml = (
                "Nenhum XML de NF-e foi importado nesta sessao do SPED Inteligente. "
                "Use Pasta NF-e ou XML/ZIP NF-e antes de cruzar, se desejar conferencia documental."
            )
        elif not resultado.xml_validos_importados and resultado.nfce_validas_importadas:
            resultado.diagnostico_xml = (
                f"{resultado.nfce_validas_importadas} NFC-e(s) modelo 65 importada(s), "
                "mas nenhuma NF-e modelo 55. O cruzamento atual de C100/C170 "
                "usa somente NF-e; NFC-e permanece separada e nao integra "
                "os totais de XML localizado no C170. "
                "Adicione a pasta de NF-e para esta auditoria, se houver."
            )
        elif not resultado.xml_validos_importados:
            resultado.diagnostico_xml = (
                "Importacao sem NF-e valida para confronto. "
                f"Arquivos ignorados: {resultado.xml_ignorados_importacao}; "
                f"erros de leitura: {resultado.xml_erros_importacao}. "
                "Verifique se a pasta/ZIP contem NF-e autorizadas com chave de 44 digitos."
            )
        elif resultado.notas_c170_chaves_unicas == 0:
            resultado.diagnostico_xml = (
                f"O SPED contem {resultado.notas_sped_chaves_unicas} chaves C100, "
                "mas nao foi localizada NF-e modelo 55 com itens C170 e chave valida. "
                "Confira quais registros precisam de confronto de XML. "
                f"Meses das chaves C100: {meses}."
            )
        elif not resultado.notas_c170_chaves_coincidentes:
            resultado.diagnostico_xml = (
                f"Foram importadas {resultado.xml_validos_importados} NF-e 55, mas "
                f"nenhuma das {resultado.notas_c170_chaves_unicas} chaves C100 "
                "com itens C170 coincidiu com os XMLs. "
                f"O arquivo contem {resultado.notas_sped_chaves_unicas} chaves C100 "
                "no total, inclusive documentos sem C170. "
                f"Meses das chaves C100: {meses}."
            )
        elif resultado.notas_c170_chaves_coincidentes < resultado.notas_c170_chaves_unicas:
            resultado.diagnostico_xml = (
                f"Cruzamento parcial: {resultado.notas_c170_chaves_coincidentes} de "
                f"{resultado.notas_c170_chaves_unicas} NF-e 55 com itens C170 "
                f"localizadas entre {resultado.xml_validos_importados} XML(s) importado(s). "
                f"O SPED possui {resultado.notas_sped_chaves_unicas} chaves C100 "
                "no total, inclusive notas sem C170; nao use esse total como "
                f"denominador dos itens auditados. Meses do C100: {meses}."
            )
        else:
            resultado.diagnostico_xml = (
                f"Todas as {resultado.notas_c170_chaves_unicas} NF-e modelo 55 "
                "com C170 e chave valida foram localizadas nos XMLs importados. "
                f"Ha {resultado.notas_sped_chaves_unicas} chaves C100 no SPED "
                "no total, incluindo documentos que nao possuem C170."
            )
        if resultado.xml_importado:
            resultado.diagnostico_xml += (
                " " + operacoes_c170
                + f"Das {resultado.xml_validos_importados} NF-e importadas, "
                + f"{resultado.xml_importados_c100_sem_c170} estao no C100 "
                "sem itens C170. O Excel da auditoria relaciona as chaves "
                "do SPED e as origens dos XMLs para conferencia."
            )
            # Diferencie a importacao das saidas proprias de NF-e recebidas
            # de fornecedores. Isso evita que 0 cruzamentos seja tratado como
            # possivel corrupcao do SPED quando as colecoes sao distintas.
            empresa_cnpj = ""
            for linha_0000 in linhas:
                if linha_0000.startswith("|0000|"):
                    campos_0000 = linha_0000.rstrip("\r\n").split("|")
                    empresa_cnpj = _digitos(
                        campos_0000[7] if len(campos_0000) > 7 else ""
                    )
                    break
            somente_saida_propria = (
                len(empresa_cnpj) == 14
                and bool(xmls)
                and all(
                    _digitos(doc.emitente_cnpj) == empresa_cnpj
                    for doc in xmls.values()
                )
            )
            somente_entradas_terceiros = (
                bool(resultado.documentos_c170)
                and resultado.c170_notas_saida == 0
                and all(
                    doc["operacao"] == "ENTRADA"
                    and doc["cnpj_emitente"] != empresa_cnpj
                    for doc in resultado.documentos_c170
                )
            )
            if (
                somente_saida_propria
                and somente_entradas_terceiros
                and resultado.notas_c170_chaves_coincidentes == 0
            ):
                resultado.diagnostico_xml += (
                    " DIAGNOSTICO: os XMLs NF-e 55 importados foram emitidos "
                    "pela propria empresa (saidas), mas as NF-e com itens C170 "
                    "sao entradas emitidas por terceiros (fornecedores). "
                    "Para cruzar essas entradas, importe os XMLs das compras "
                    "e demais NF-e recebidas, inclusive as emitidas em meses "
                    "anteriores que foram escrituradas na competencia."
                )
        self._progresso(progresso, 100, "Auditoria tributária concluída.")
        return resultado

    @staticmethod
    def _carregar_regras_lote(
        ncms: set[str],
    ) -> tuple[
        dict[str, list[dict[str, Any]]],
        dict[tuple[str, str], list[dict[str, Any]]],
        set[str],
    ]:
        """Carrega as regras de todos os NCMs com uma única preparação do banco.

        Evita executar as migrações e os índices novamente para cada item/NCM do
        SPED, o que é essencial em arquivos com milhares de C170.
        """
        regras_contexto: dict[str, list[dict[str, Any]]] = {ncm: [] for ncm in ncms}
        regras_produto: dict[tuple[str, str], list[dict[str, Any]]] = {}
        com_base_legal: set[str] = set()
        if not ncms:
            return regras_contexto, regras_produto, com_base_legal

        FichaTributariaRepository.preparar_banco()
        conn = Banco.conectar()
        try:
            lista_ncms = sorted(ncms)
            for inicio in range(0, len(lista_ncms), 800):
                lote = lista_ncms[inicio:inicio + 800]
                marcadores = ",".join("?" for _ in lote)
                cursor = conn.execute(
                    f"""
                    SELECT id, ncm, COALESCE(empresa, '') AS empresa,
                           COALESCE(NULLIF(uf_origem, ''), '') AS uf_origem,
                           COALESCE(NULLIF(uf_destino, ''), NULLIF(uf, ''), '') AS uf_destino,
                           COALESCE(regime, '') AS regime, COALESCE(operacao, '') AS operacao,
                           COALESCE(finalidade, '') AS finalidade,
                           COALESCE(contribuinte, 'TODOS') AS contribuinte,
                           COALESCE(cfop, '') AS cfop, COALESCE(cst_icms, '') AS cst_icms,
                           COALESCE(pis_cst, '') AS cst_pis, COALESCE(cofins_cst, '') AS cst_cofins,
                           aliquota_pis, aliquota_cofins, icms, COALESCE(icms_st, '') AS icms_st,
                           fcp, COALESCE(cst_ipi, '') AS cst_ipi, ipi,
                           COALESCE(beneficio, '') AS beneficio,
                           vigencia_inicio, vigencia_fim, COALESCE(fonte, '') AS fonte,
                           COALESCE(confiabilidade, 50) AS confiabilidade,
                           COALESCE(observacoes, '') AS observacoes,
                           COALESCE(status, 'VIGENTE') AS status, criado_em, atualizado_em
                    FROM tributacao_atual
                    WHERE ncm IN ({marcadores})
                    """,
                    lote,
                )
                for linha in cursor.fetchall():
                    item = dict(linha)
                    item.update(
                        {
                            "origem": "Regra por operação",
                            "tipo_origem": "tributacao_atual",
                            "empresa": item.get("empresa") or "Todas",
                            "codigo_produto": "",
                            "descricao_produto": "",
                            "ultima_validacao": item.get("atualizado_em") or item.get("vigencia_inicio"),
                        }
                    )
                    regras_contexto.setdefault(str(item.get("ncm") or ""), []).append(item)

                cursor = conn.execute(
                    f"""
                    SELECT id, empresa, codigo_produto, descricao_produto, ncm, cest, cfop,
                           cst_icms, icms, icms_st, fcp, cst_pis, aliquota_pis,
                           cst_cofins, aliquota_cofins, cst_ipi, ipi, ibs, cbs,
                           classificacao, beneficio, fonte, confiabilidade,
                           ultima_validacao, observacoes, atualizado_em
                    FROM tributacao_base
                    WHERE ncm IN ({marcadores}) AND ativo = 1
                    """,
                    lote,
                )
                for linha in cursor.fetchall():
                    item = dict(linha)
                    item.update(
                        {
                            "origem": "Cadastro por produto",
                            "tipo_origem": "tributacao_base",
                            "uf_origem": "",
                            "uf_destino": "",
                            "regime": "",
                            "operacao": "",
                            "finalidade": "",
                            "contribuinte": "",
                            "vigencia_inicio": item.get("ultima_validacao"),
                            "vigencia_fim": None,
                            "status": "OPERACIONAL",
                        }
                    )
                    chave_produto = (
                        str(item.get("ncm") or ""),
                        _texto(item.get("codigo_produto")).upper(),
                    )
                    regras_produto.setdefault(chave_produto, []).append(item)

                cursor = conn.execute(
                    f"""
                    SELECT DISTINCT ncm
                    FROM ficha_base_legal
                    WHERE ncm IN ({marcadores})
                      AND COALESCE(status, 'VIGENTE') <> 'RASCUNHO'
                    """,
                    lote,
                )
                com_base_legal.update(str(linha["ncm"]) for linha in cursor.fetchall())
        finally:
            conn.close()
        return regras_contexto, regras_produto, com_base_legal

    @staticmethod
    def _carregar_0200(linhas: list[str]) -> tuple[dict[str, Registro0200], set[str]]:
        cadastros: dict[str, Registro0200] = {}
        duplicados: set[str] = set()
        for linha in linhas:
            if not linha.startswith("|0200|"):
                continue
            cadastro = Registro0200(linha)
            if not cadastro.codigo:
                continue
            if cadastro.codigo in cadastros:
                duplicados.add(cadastro.codigo)
            cadastros[cadastro.codigo] = cadastro
        return cadastros, duplicados

    @staticmethod
    def _carregar_0150(linhas: list[str]) -> dict[str, dict[str, str]]:
        participantes: dict[str, dict[str, str]] = {}
        for linha in linhas:
            if not linha.startswith("|0150|"):
                continue
            campos = linha.rstrip("\r\n").split("|")
            codigo = campos[2].strip() if len(campos) > 2 else ""
            cod_mun = _digitos(campos[8] if len(campos) > 8 else "")
            ie = _texto(campos[7] if len(campos) > 7 else "")
            participantes[codigo] = {
                "nome": _texto(campos[3] if len(campos) > 3 else ""),
                "ie": ie,
                "cod_mun": cod_mun,
                "uf": _UF_POR_PREFIXO_IBGE.get(cod_mun[:2], ""),
            }
        return participantes

    @staticmethod
    def _uf_empresa(linhas: list[str], tipo_sped: str) -> str:
        for linha in linhas:
            if not linha.startswith("|0000|"):
                continue
            campos = linha.rstrip("\r\n").split("|")
            indice = 10 if tipo_sped == "EFD Contribuições" else 9
            return _texto(campos[indice] if len(campos) > indice else "").upper()
        return ""

    @staticmethod
    def _carregar_notas_itens(linhas: list[str]) -> list[dict[str, Any]]:
        notas: list[dict[str, Any]] = []
        atual: Optional[dict[str, Any]] = None
        for numero_linha, linha in enumerate(linhas, start=1):
            if linha.startswith("|C100|"):
                campos = linha.rstrip("\r\n").split("|")
                atual = {
                    "linha": numero_linha,
                    "ind_oper": _texto(campos[2] if len(campos) > 2 else ""),
                    "ind_emit": _texto(campos[3] if len(campos) > 3 else ""),
                    "cod_part": _texto(campos[4] if len(campos) > 4 else ""),
                    "modelo": _texto(campos[5] if len(campos) > 5 else ""),
                    "serie": _texto(campos[7] if len(campos) > 7 else ""),
                    "numero": _texto(campos[8] if len(campos) > 8 else ""),
                    "chave": _digitos(campos[9] if len(campos) > 9 else ""),
                    "data_doc": _texto(campos[10] if len(campos) > 10 else ""),
                    "data_es": _texto(campos[11] if len(campos) > 11 else ""),
                    "itens": [],
                }
                notas.append(atual)
            elif linha.startswith("|C170|") and atual is not None:
                atual["itens"].append((numero_linha, linha))
        return notas

    @staticmethod
    def _contexto_nota(
        padrao: dict[str, str], nota: dict[str, Any], participante: dict[str, str], uf_empresa: str
    ) -> dict[str, str]:
        entrada = nota.get("ind_oper") == "0"
        uf_participante = participante.get("uf", "")
        contribuinte_padrao = _texto(padrao.get("contribuinte") or "AUTOMÁTICO").upper()
        if contribuinte_padrao in {"AUTOMÁTICO", "AUTOMATICO", ""}:
            ie = _texto(participante.get("ie"))
            contribuinte = "CONTRIBUINTE" if ie and ie.upper() != "ISENTO" else "NÃO CONTRIBUINTE"
        else:
            contribuinte = contribuinte_padrao
        return {
            "empresa": _texto(padrao.get("empresa")),
            "regime": _texto(padrao.get("regime")),
            "operacao": "ENTRADA" if entrada else "SAÍDA",
            "finalidade": _texto(padrao.get("finalidade")),
            "uf_origem": uf_participante if entrada else uf_empresa,
            "uf_destino": uf_empresa if entrada else uf_participante,
            "contribuinte": contribuinte,
            "data_operacao": _data_iso_sped(nota.get("data_es") or nota.get("data_doc")),
        }

    def _comparar_regra(
        self,
        resultado: ResultadoAuditoriaTributaria,
        linha: int,
        nota: dict[str, Any],
        item: RegistroC170,
        cadastro: Registro0200,
        regra: dict[str, Any],
        aderencia: float,
        *,
        confiavel: bool = True,
    ) -> None:
        regra_id = str(regra.get("id") or "")
        for nome, atributo_item, campo_regra, tipo in self.CAMPOS_REGRA:
            atual = getattr(item, atributo_item, "")
            esperado = regra.get(campo_regra)
            if self._divergente(atual, esperado, tipo):
                self._adicionar(
                    resultado, "ERRO" if confiavel else "AVISO",
                    "FICHA TRIBUTÁRIA", linha, nota, item, nome,
                    self._formatar(atual, tipo), self._formatar(esperado, tipo), regra_id, aderencia,
                    f"{nome} do C170 diverge da regra tributária selecionada.",
                    "Confira a operação e a base legal. Depois corrija o SPED ou ajuste a regra, conforme o caso.",
                )
        cest_esperado = regra.get("cest")
        if cest_esperado and self._divergente(cadastro.cest, cest_esperado, "texto"):
            self._adicionar(
                resultado, "ERRO" if confiavel else "AVISO", "FICHA TRIBUTÁRIA", linha, nota, item, "CEST",
                cadastro.cest, _digitos(cest_esperado), regra_id, aderencia,
                "CEST do cadastro 0200 diverge da regra tributária selecionada.",
                "Revise o cadastro do produto e confirme o enquadramento legal de ICMS-ST.",
            )

        st_esperado = _texto(regra.get("icms_st")).upper()
        if st_esperado in {"SIM", "S", "1", "ST", "NÃO", "NAO", "N", "0"}:
            tem_st = item.valor_st > 0 or item.base_st > 0
            esperado_sim = st_esperado in {"SIM", "S", "1", "ST"}
            if tem_st != esperado_sim:
                self._adicionar(
                    resultado, "AVISO", "FICHA TRIBUTÁRIA", linha, nota, item, "ICMS-ST",
                    "Com ST" if tem_st else "Sem ST", "Com ST" if esperado_sim else "Sem ST",
                    regra_id, aderencia,
                    "Tratamento de ICMS-ST do item difere da regra cadastrada.",
                    "Confirme CEST, protocolo/convênio, UF e natureza da operação antes de alterar.",
                )

    def _comparar_xml(
        self,
        resultado: ResultadoAuditoriaTributaria,
        linha: int,
        nota: dict[str, Any],
        item: RegistroC170,
        xml: ItemXMLNFe,
        *,
        entrada: bool = False,
    ) -> None:
        for nome, atributo_item, atributo_xml, tipo in self.CAMPOS_XML:
            # Na entrada, CFOP, CST e aliquotas de escrituracao do adquirente
            # nao sao necessariamente iguais aos de emissao do fornecedor.
            # Comparar NCM/CEST como cadastro documental; nao criar sugestao
            # automatica de alteracao fiscal a partir do XML de compra.
            if entrada and nome not in {"NCM", "CEST"}:
                continue
            atual = getattr(item, atributo_item, "")
            if nome == "NCM":
                atual = item.ncm
            elif nome == "CEST":
                atual = item.cest
            esperado = getattr(xml, atributo_xml, "")
            if self._divergente(atual, esperado, tipo):
                self._adicionar(
                    resultado, "AVISO" if entrada else "ERRO", "XML NF-e", linha, nota, item, nome,
                    self._formatar(atual, tipo), self._formatar(esperado, tipo), "", 0,
                    (
                        f"{nome} do cadastro da entrada difere do XML do fornecedor; revisar classificacao."
                        if entrada else f"{nome} do SPED diverge do XML da NF-e."
                    ),
                    (
                        "Confronte o cadastro com o documento e a classificacao fiscal; nao corrija o SPED automaticamente."
                        if entrada else "Confira o XML autorizado antes de corrigir a escrituracao."
                    ),
                )

    @staticmethod
    def _divergente(atual: Any, esperado: Any, tipo: str) -> bool:
        if esperado in (None, ""):
            return False
        if tipo == "numero":
            return abs(_numero(atual) - _numero(esperado)) > 0.005
        return _digitos(atual) != _digitos(esperado) if re.search(r"\d", str(esperado)) else _texto(atual).upper() != _texto(esperado).upper()

    @staticmethod
    def _formatar(valor: Any, tipo: str) -> str:
        return _numero_br(valor) if tipo == "numero" else _texto(valor)

    @staticmethod
    def _adicionar(
        resultado: ResultadoAuditoriaTributaria,
        nivel: str,
        origem: str,
        linha: int,
        nota: dict[str, Any],
        item: RegistroC170,
        campo: str,
        atual: Any,
        esperado: Any,
        regra_id: str,
        aderencia: float,
        mensagem: str,
        orientacao: str,
    ) -> None:
        resultado.apontamentos.append(
            ApontamentoAuditoriaTributaria(
                nivel=nivel,
                origem=origem,
                linha=linha,
                registro="C170",
                documento=_texto(nota.get("numero")),
                chave=_texto(nota.get("chave")),
                item=_texto(item.numero_item),
                codigo=_texto(item.codigo),
                descricao=_texto(item.descricao_0200 or item.descricao_complementar),
                ncm=_texto(item.ncm),
                campo=campo,
                atual=_texto(atual),
                esperado=_texto(esperado),
                regra_id=regra_id,
                aderencia=aderencia,
                mensagem=mensagem,
                orientacao=orientacao,
            )
        )

    @staticmethod
    def salvar_relatorio(
        resultado: ResultadoAuditoriaTributaria,
        caminho_saida: str | Path,
        caminho_sped: str | Path,
    ) -> Path:
        destino = Path(caminho_saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        linhas = [
            "FISCALPRO — AUDITORIA TRIBUTÁRIA INTEGRADA",
            "=" * 96,
            f"Arquivo SPED: {caminho_sped}",
            f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"Empresa: {resultado.contexto.get('empresa', '')}",
            f"Regime: {resultado.contexto.get('regime', '')}",
            f"Finalidade padrão: {resultado.contexto.get('finalidade', '')}",
            f"Contribuinte: {resultado.contexto.get('contribuinte', '')}",
            "",
            "RESUMO",
            "-" * 96,
            f"Itens C170 auditados: {resultado.total_itens}",
            f"Itens com cadastro 0200: {resultado.itens_com_0200}",
            f"Itens sem cadastro 0200: {resultado.itens_sem_0200}",
            f"Itens com regra tributária: {resultado.itens_com_regra}",
            f"Itens sem regra tributária: {resultado.itens_sem_regra}",
            f"Itens encontrados nos XMLs: {resultado.itens_com_xml}",
            f"Itens sem correspondência XML: {resultado.itens_sem_xml}",
            f"Erros: {resultado.erros}",
            f"Avisos: {resultado.avisos}",
            f"Cobertura das regras: {resultado.cobertura_regras:.2f}%".replace(".", ","),
            f"Conformidade parcial: {resultado.conformidade_exibicao}",
            f"Diagnostico da cobertura: {resultado.diagnostico_regras or 'Sem ressalvas de cobertura identificadas'}",
            f"NF-e validas importadas: {resultado.xml_validos_importados}",
            f"NFC-e validas importadas: {resultado.nfce_validas_importadas}",
            f"Chaves C100 totais / com XML localizado: {resultado.notas_sped_chaves_unicas} / {resultado.notas_sped_chaves_coincidentes}",
            f"NF-e 55 com C170 / com XML localizado: {resultado.notas_c170_chaves_unicas} / {resultado.notas_c170_chaves_coincidentes}",
            f"Diagnostico do XML: {resultado.diagnostico_xml or 'Sem ressalvas de XML identificadas'}",
            "",
            "APONTAMENTOS",
            "-" * 96,
        ]
        if not resultado.apontamentos:
            linhas.append("Nenhuma divergência encontrada nas regras executadas.")
        for apontamento in resultado.apontamentos:
            linhas.extend(
                [
                    f"[{apontamento.nivel}] {apontamento.origem} — linha {apontamento.linha} — "
                    f"NF {apontamento.documento} — item {apontamento.item} — produto {apontamento.codigo}",
                    f"NCM: {apontamento.ncm} | Campo: {apontamento.campo}",
                    f"Atual: {apontamento.atual}",
                    f"Esperado: {apontamento.esperado}",
                    f"Regra: {apontamento.regra_id or '-'} | Aderência: {apontamento.aderencia:.0f}%",
                    f"Problema: {apontamento.mensagem}",
                    f"Orientação: {apontamento.orientacao}",
                    "",
                ]
            )
        destino.write_text("\n".join(linhas), encoding="utf-8")
        return destino

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(max(0, min(100, percentual)), mensagem)
