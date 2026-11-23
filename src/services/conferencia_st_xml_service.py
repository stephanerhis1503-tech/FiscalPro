"""Conferencia DOCUMENTAL ICMS-ST de C170 com NF-e, somente leitura.

A presenca de vICMSST/vICMSSTRet no XML nao comprova responsabilidade
do destinatario, imposto a recolher, direito a credito ou enquadramento legal.
O resultado nunca cria regra, altera SPED, nem alimenta motor de apuracao.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

CAMPOS_ST_XML = (
    "vBCST", "vICMSST", "vBCSTRet", "vICMSSTRet", "vFCPST", "vFCPSTRet",
)

CHAVES_EVIDENCIA = (
    "st_xml_status", "st_xml_acao", "st_xml_responsabilidade",
    "st_xml_arquivo", "st_xml_ncm", "st_xml_cest", "st_xml_cfop",
    "st_xml_cst", "st_xml_codigo", "st_xml_item",
    "st_xml_vBCST", "st_xml_vICMSST", "st_xml_vBCSTRet",
    "st_xml_vICMSSTRet", "st_xml_vFCPST", "st_xml_vFCPSTRet",
)


def _texto(valor: Any) -> str:
    return str(valor if valor is not None else "").strip()


def _digitos(valor: Any) -> str:
    return "".join(c for c in _texto(valor) if c.isdigit())


def _numero(valor: Any) -> Decimal | None:
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return Decimal(texto.replace(",", "."))
    except InvalidOperation:
        return None


def conferir_item_st_xml(
    referencia: dict[str, Any],
    documento_xml: Any = None,
    item_xml: Any = None,
    vinculo_duvidoso: bool = False,
    xml_importado: bool = False,
) -> dict[str, str]:
    """Confronta apenas entradas INTERNAS MG para uso/consumo.

    OK significa exclusivamente valor ST legivel presente no item XML.
    Nao significa ST devida, recolhida, credito permitido ou regra aprovada.
    """
    if not (
        _texto(referencia.get("operacao")).upper() == "ENTRADA"
        and _texto(referencia.get("finalidade")).upper() == "USO E CONSUMO"
        and _texto(referencia.get("uf_origem")).upper() == "MG"
        and _texto(referencia.get("uf_destino")).upper() == "MG"
    ):
        return {}

    resultado = {campo: "" for campo in CHAVES_EVIDENCIA}
    resultado["st_xml_responsabilidade"] = (
        "NAO DETERMINADA: verificar fornecedor, destinatario, operacao, "
        "regime especial e fundamento legal; nunca gerar imposto automaticamente."
    )

    def situacao(status: str, acao: str) -> dict[str, str]:
        resultado["st_xml_status"] = status
        resultado["st_xml_acao"] = acao
        return resultado

    if not xml_importado:
        return situacao(
            "REVISAR - XML AINDA NAO IMPORTADO",
            "Importar XML NF-e modelo 55 correspondente e repetir o cruzamento.",
        )
    if documento_xml is None:
        return situacao(
            "REVISAR - NF-E SEM XML CORRESPONDENTE",
            "Conferir chave de 44 digitos do C100 e localizar o XML original.",
        )
    resultado["st_xml_arquivo"] = _texto(getattr(documento_xml, "arquivo_origem", ""))
    if item_xml is None:
        return situacao(
            "REVISAR - ITEM C170 SEM VINCULO XML",
            "Conferir nItem e codigo do produto; nao vincular por semelhanca.",
        )
    resultado.update({
        "st_xml_ncm": _digitos(getattr(item_xml, "ncm", "")),
        "st_xml_cest": _digitos(getattr(item_xml, "cest", "")),
        "st_xml_cfop": _digitos(getattr(item_xml, "cfop", "")),
        "st_xml_cst": _texto(getattr(item_xml, "cst_icms", "")),
        "st_xml_codigo": _texto(getattr(item_xml, "codigo", "")),
        "st_xml_item": _texto(getattr(item_xml, "numero_item", "")),
    })
    valores = getattr(item_xml, "valores_st_xml", {}) or {}
    for campo in CAMPOS_ST_XML:
        resultado["st_xml_" + campo] = _texto(valores.get(campo))
    if vinculo_duvidoso:
        return situacao(
            "DIVERGENCIA DOCUMENTAL - ITEM XML INCOMPATIVEL COM C170",
            "Numero do item coincide, mas codigo e NCM divergem; validar vinculo manualmente.",
        )
    ncm_sped = _digitos(referencia.get("ncm"))
    ncm_xml = resultado["st_xml_ncm"]
    if ncm_sped and ncm_xml and ncm_sped != ncm_xml:
        return situacao(
            "DIVERGENCIA DOCUMENTAL - NCM SPED X XML",
            "Conferir cadastro 0200 e NCM da NF-e; nao corrigir automaticamente.",
        )

    campos_presentes = {k: _texto(valores[k]) for k in CAMPOS_ST_XML if k in valores}
    if not campos_presentes:
        if resultado["st_xml_cfop"] == "5929":
            return situacao(
                "INFORMATIVO - CFOP 5929: NF-E VINCULADA A CUPOM, SEM TAG ST",
                "NF-e referente a operacao ja acobertada por documento fiscal do varejo. "
                "A ausencia de tag ST nesta NF-e nao gera alerta tributario autonomo; "
                "conferir o cupom de origem e evitar duplicidade na escrituracao.",
            )
        return situacao(
            "REVISAR - ITEM XML SEM TAG ST",
            "Ausencia de destaque/retencao no XML nao prova inexistencia de obrigacao.",
        )
    numeros = {campo: _numero(valor) for campo, valor in campos_presentes.items()}
    if any(valor is None or valor < 0 for valor in numeros.values()):
        return situacao(
            "DIVERGENCIA DOCUMENTAL - VALOR ST INVALIDO NO XML",
            "Rever o XML importado; valores negativos ou nao numericos nao sao aceitos.",
        )

    destacado = numeros.get("vICMSST", Decimal("0")) > 0
    retido = numeros.get("vICMSSTRet", Decimal("0")) > 0
    if resultado["st_xml_cfop"] == "5929":
        # CFOP 5929 NAO representa uma nova venda: a NF-e documenta
        # operacao ja acobertada por documento fiscal do varejo.
        # A falta de tag ST e informativa, mas valor ST destacado
        # merece revisao para prevenir duplicidade de incidencia.
        if destacado:
            return situacao(
                "REVISAR - ST DESTACADA EM NF-E VINCULADA A CUPOM (CFOP 5929)",
                "Conferir cupom vinculado, operacao e imposto destacado: "
                "nao duplicar apuracao nem gerar guia com base nesta NF-e.",
            )
        if retido:
            return situacao(
                "INFORMATIVO - CFOP 5929: NF-E VINCULADA A CUPOM COM ST RETIDA",
                "Valor vICMSSTRet consta do XML para rastreabilidade. "
                "Nao presumir novo recolhimento; conferir documento varejista vinculado.",
            )
        return situacao(
            "INFORMATIVO - CFOP 5929: NF-E VINCULADA A CUPOM, SEM ST POSITIVA",
            "Tags ST presentes sem valor positivo. A NF-e nao constitui "
            "nova operacao autonomamente; conferir cupom vinculado.",
        )
    if destacado and retido:
        return situacao(
            "REVISAR - ST DESTACADA E RETIDA NO MESMO ITEM",
            "Conferir CST/CSOSN e a natureza dos dois valores antes de concluir.",
        )
    if destacado:
        return situacao(
            "OK DOCUMENTAL - VINCULO XML COM ST DESTACADA",
            "Ha vICMSST positivo na nota; verificar quem e responsavel pelo recolhimento.",
        )
    if retido:
        return situacao(
            "OK DOCUMENTAL - VINCULO XML COM ST RETIDA ANTERIORMENTE",
            "Ha vICMSSTRet positivo na nota; nao presumir novo recolhimento.",
        )
    return situacao(
        "REVISAR - XML SEM VALOR ICMS-ST POSITIVO",
        "Conferir base, CST/CSOSN, tags disponiveis e eventual regime especial.",
    )
