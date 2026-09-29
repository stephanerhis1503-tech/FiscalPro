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

    def localizar_item(self, numero_item: str, codigo: str) -> Optional[ItemXMLNFe]:
        numero_item = _texto(numero_item)
        codigo = _texto(codigo).upper()
        if numero_item:
            encontrados = [item for item in self.itens if _texto(item.numero_item) == numero_item]
            if len(encontrados) == 1:
                return encontrados[0]
        if codigo:
            encontrados = [item for item in self.itens if _texto(item.codigo).upper() == codigo]
            if len(encontrados) == 1:
                return encontrados[0]
        return None


@dataclass(slots=True)
class ResultadoImportacaoXMLNFe:
    documentos: dict[str, DocumentoXMLNFe] = field(default_factory=dict)
    total_fontes: int = 0
    total_arquivos_xml: int = 0
    total_nfe_validas: int = 0
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
    apontamentos: list[ApontamentoAuditoriaTributaria] = field(default_factory=list)
    contexto: dict[str, str] = field(default_factory=dict)

    @property
    def total_apontamentos(self) -> int:
        return len(self.apontamentos)

    @property
    def conformidade(self) -> float:
        if self.total_itens <= 0:
            return 100.0
        itens_com_problema = len({(a.linha, a.codigo) for a in self.apontamentos if a.nivel == "ERRO"})
        return round(max(0.0, 100.0 - (itens_com_problema / self.total_itens * 100.0)), 2)


class ImportadorXMLNFe:
    """Lê NF-e avulsas, pastas e ZIPs sem alterar os documentos."""

    def importar(
        self,
        fontes: Iterable[str | Path],
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoImportacaoXMLNFe:
        resultado = ResultadoImportacaoXMLNFe()
        fontes = [Path(fonte) for fonte in fontes]
        resultado.total_fontes = len(fontes)
        candidatos: list[tuple[str, bytes]] = []

        self._progresso(progresso, 5, "Localizando XMLs de NF-e...")
        for fonte in fontes:
            if fonte.is_dir():
                for arquivo in fonte.rglob("*"):
                    if arquivo.is_file() and arquivo.suffix.lower() in {".xml", ".zip"}:
                        candidatos.extend(self._ler_fonte(arquivo, resultado))
            elif fonte.is_file():
                candidatos.extend(self._ler_fonte(fonte, resultado))
            else:
                resultado.total_erros += 1
                resultado.erros.append(f"Fonte não encontrada: {fonte}")

        total = max(1, len(candidatos))
        for indice, (origem, conteudo) in enumerate(candidatos, start=1):
            try:
                documento = self._interpretar_xml(conteudo, origem)
                resultado.total_arquivos_xml += 1
                if documento is None:
                    resultado.total_ignoradas += 1
                    continue
                if documento.chave in resultado.documentos:
                    resultado.total_duplicadas += 1
                    continue
                resultado.documentos[documento.chave] = documento
                resultado.total_nfe_validas += 1
            except Exception as erro:  # XML inválido não deve interromper o lote.
                resultado.total_erros += 1
                resultado.erros.append(f"{origem}: {erro}")
            percentual = 15 + int(indice / total * 80)
            self._progresso(progresso, percentual, f"NF-e lidas: {indice:,}/{total:,}")

        self._progresso(progresso, 100, "XMLs de NF-e importados.")
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
        ncms_usados = {
            cadastro.ncm
            for nota in notas
            for _numero_linha, linha_item in nota["itens"]
            for codigo in [RegistroC170(linha_item).codigo]
            for cadastro in [cadastros.get(codigo)]
            if cadastro is not None and len(cadastro.ncm) == 8
        }
        regras_contexto, regras_produto, ncms_com_base_legal = self._carregar_regras_lote(ncms_usados)
        cache_selecao: dict[tuple[str, ...], Any] = {}
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
                    self._comparar_xml(resultado, numero_linha, nota, item, item_xml)
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
                            resultado, numero_linha, nota, item, cadastro, selecao.regra, selecao.aderencia
                        )
                        regra_id = str(selecao.regra.get("id") or "")
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
    ) -> None:
        regra_id = str(regra.get("id") or "")
        for nome, atributo_item, campo_regra, tipo in self.CAMPOS_REGRA:
            atual = getattr(item, atributo_item, "")
            esperado = regra.get(campo_regra)
            if self._divergente(atual, esperado, tipo):
                self._adicionar(
                    resultado, "ERRO", "FICHA TRIBUTÁRIA", linha, nota, item, nome,
                    self._formatar(atual, tipo), self._formatar(esperado, tipo), regra_id, aderencia,
                    f"{nome} do C170 diverge da regra tributária selecionada.",
                    "Confira a operação e a base legal. Depois corrija o SPED ou ajuste a regra, conforme o caso.",
                )
        cest_esperado = regra.get("cest")
        if cest_esperado and self._divergente(cadastro.cest, cest_esperado, "texto"):
            self._adicionar(
                resultado, "ERRO", "FICHA TRIBUTÁRIA", linha, nota, item, "CEST",
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
    ) -> None:
        for nome, atributo_item, atributo_xml, tipo in self.CAMPOS_XML:
            atual = getattr(item, atributo_item, "")
            if nome == "NCM":
                atual = item.ncm
            elif nome == "CEST":
                atual = item.cest
            esperado = getattr(xml, atributo_xml, "")
            if self._divergente(atual, esperado, tipo):
                self._adicionar(
                    resultado, "ERRO", "XML NF-e", linha, nota, item, nome,
                    self._formatar(atual, tipo), self._formatar(esperado, tipo), "", 0,
                    f"{nome} do SPED diverge do XML da NF-e.",
                    "Confira o XML autorizado e corrija a escrituração para refletir o documento fiscal.",
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
            f"Conformidade por item: {resultado.conformidade:.2f}%".replace(".", ","),
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
