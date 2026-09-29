"""Nomes técnicos oficiais dos campos usados na exportação SPED → Excel.

Hotfix 17.7.2
---------------
A exportação passa a respeitar o tipo da escrituração. Registros que existem
nas duas EFDs (por exemplo 0000, 0200, C170 e D100) possuem leiautes distintos
e, portanto, não podem compartilhar cegamente o mesmo cabeçalho.

Os nomes abaixo seguem os identificadores técnicos dos campos do leiaute
(REG, COD_ITEM, CST_PIS, VL_BC_PIS, etc.). O importador Excel → TXT continua
reversível por posição e pelo identificador técnico oculto; os cabeçalhos são
apenas a representação legível para a usuária.
"""

from __future__ import annotations


# EFD-Contribuições — campos usados nos blocos e registros suportados pelo
# FiscalPro. A lista inclui também registros normalmente criados pelo PGE na
# etapa "Gerar Apurações" (0111, M600 e M610).
CAMPOS_EFD_CONTRIBUICOES: dict[str, tuple[str, ...]] = {
    "0000": (
        "REG", "COD_VER", "TIPO_ESCRIT", "IND_SIT_ESP", "NUM_REC_ANTERIOR",
        "DT_INI", "DT_FIN", "NOME", "CNPJ", "UF", "COD_MUN", "SUFRAMA",
        "IND_NAT_PJ", "IND_ATIV",
    ),
    "0001": ("REG", "IND_MOV"),
    "0100": (
        "REG", "NOME", "CPF", "CRC", "CNPJ", "CEP", "END", "NUM", "COMPL",
        "BAIRRO", "FONE", "FAX", "EMAIL", "COD_MUN",
    ),
    "0110": ("REG", "COD_INC_TRIB", "IND_APRO_CRED", "COD_TIPO_CONT", "IND_REG_CUM"),
    "0111": (
        "REG", "REC_BRU_NCUM_TRIB_MI", "REC_BRU_NCUM_NT_MI", "REC_BRU_NCUM_EXP",
        "REC_BRU_CUM", "REC_BRU_TOTAL",
    ),
    "0140": ("REG", "COD_EST", "NOME", "CNPJ", "UF", "IE", "COD_MUN", "IM", "SUFRAMA"),
    "0150": (
        "REG", "COD_PART", "NOME", "COD_PAIS", "CNPJ", "CPF", "IE", "COD_MUN",
        "SUFRAMA", "END", "NUM", "COMPL", "BAIRRO",
    ),
    "0190": ("REG", "UNID", "DESCR"),
    "0200": (
        "REG", "COD_ITEM", "DESCR_ITEM", "COD_BARRA", "COD_ANT_ITEM", "UNID_INV",
        "TIPO_ITEM", "COD_NCM", "EX_IPI", "COD_GEN", "COD_LST", "ALIQ_ICMS",
    ),
    "0400": ("REG", "COD_NAT", "DESCR_NAT"),
    "0450": ("REG", "COD_INF", "TXT"),
    "0500": (
        "REG", "DT_ALT", "COD_NAT_CC", "IND_CTA", "NIVEL", "COD_CTA", "NOME_CTA",
        "COD_CTA_REF", "CNPJ_EST",
    ),
    "0990": ("REG", "QTD_LIN_0"),
    "1001": ("REG", "IND_MOV"),
    "1990": ("REG", "QTD_LIN_1"),
    "9001": ("REG", "IND_MOV"),
    "9900": ("REG", "REG_BLC", "QTD_REG_BLC"),
    "9990": ("REG", "QTD_LIN_9"),
    "9999": ("REG", "QTD_LIN"),

    "A001": ("REG", "IND_MOV"),
    "A010": ("REG", "CNPJ"),
    "A100": (
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_SIT", "SER", "SUB", "NUM_DOC",
        "CHV_NFSE", "DT_DOC", "DT_EXE_SERV", "VL_DOC", "IND_PGTO", "VL_DESC",
        "VL_BC_PIS", "VL_PIS", "VL_BC_COFINS", "VL_COFINS", "VL_PIS_RET",
        "VL_COFINS_RET", "IND_NAT_RET",
    ),
    "A170": (
        "REG", "NUM_ITEM", "COD_ITEM", "DESCR_COMPL", "VL_ITEM", "VL_DESC", "NAT_BC_CRED",
        "IND_ORIG_CRED", "CST_PIS", "VL_BC_PIS", "ALIQ_PIS", "VL_PIS", "CST_COFINS",
        "VL_BC_COFINS", "ALIQ_COFINS", "VL_COFINS", "COD_CTA", "COD_CCUS",
    ),
    "A990": ("REG", "QTD_LIN_A"),

    "C001": ("REG", "IND_MOV"),
    "C010": ("REG", "CNPJ", "IND_ESCRI"),
    "C100": (
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT", "SER", "NUM_DOC",
        "CHV_NFE", "DT_DOC", "DT_E_S", "VL_DOC", "IND_PGTO", "VL_DESC", "VL_ABAT_NT",
        "VL_MERC", "IND_FRT", "VL_FRT", "VL_SEG", "VL_OUT_DA", "VL_BC_ICMS", "VL_ICMS",
        "VL_BC_ICMS_ST", "VL_ICMS_ST", "VL_IPI", "VL_PIS", "VL_COFINS", "VL_PIS_ST",
        "VL_COFINS_ST",
    ),
    "C110": ("REG", "COD_INF", "TXT_COMPL"),
    "C170": (
        "REG", "NUM_ITEM", "COD_ITEM", "DESCR_COMPL", "QTD", "UNID", "VL_ITEM", "VL_DESC",
        "IND_MOV", "CST_ICMS", "CFOP", "COD_NAT", "VL_BC_ICMS", "ALIQ_ICMS", "VL_ICMS",
        "VL_BC_ICMS_ST", "ALIQ_ST", "VL_ICMS_ST", "IND_APUR", "CST_IPI", "COD_ENQ",
        "VL_BC_IPI", "ALIQ_IPI", "VL_IPI", "CST_PIS", "VL_BC_PIS", "ALIQ_PIS",
        "QUANT_BC_PIS", "ALIQ_PIS_QUANT", "VL_PIS", "CST_COFINS", "VL_BC_COFINS",
        "ALIQ_COFINS", "QUANT_BC_COFINS", "ALIQ_COFINS_QUANT", "VL_COFINS", "COD_CTA",
    ),
    # Hotfix 17.7.6 — o C175 também precisa sair com o leiaute real. Até a
    # 17.7.5 esta aba ainda caía no fallback CAMPO_02/CAMPO_03, justamente nos
    # campos em que a usuária precisa distinguir alíquota percentual, alíquota
    # por quantidade e valor da contribuição.
    "C175": (
        "REG", "CFOP", "VL_OPR", "VL_DESC", "CST_PIS", "VL_BC_PIS",
        "ALIQ_PIS", "QUANT_BC_PIS", "ALIQ_PIS_QUANT", "VL_PIS",
        "CST_COFINS", "VL_BC_COFINS", "ALIQ_COFINS", "QUANT_BC_COFINS",
        "ALIQ_COFINS_QUANT", "VL_COFINS", "COD_CTA", "INFO_COMPL",
    ),
    "C990": ("REG", "QTD_LIN_C"),

    "D001": ("REG", "IND_MOV"),
    "D010": ("REG", "CNPJ"),
    "D100": (
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT", "SER", "SUB",
        "NUM_DOC", "CHV_CTE", "DT_DOC", "DT_A_P", "TP_CT-e", "CHV_CTE_REF", "VL_DOC",
        "VL_DESC", "IND_FRT", "VL_SERV", "VL_BC_ICMS", "VL_ICMS", "VL_NT", "COD_INF",
        "COD_CTA",
    ),
    "D101": (
        "REG", "IND_NAT_FRT", "VL_ITEM", "CST_PIS", "NAT_BC_CRED", "VL_BC_PIS",
        "ALIQ_PIS", "VL_PIS", "COD_CTA",
    ),
    "D105": (
        "REG", "IND_NAT_FRT", "VL_ITEM", "CST_COFINS", "NAT_BC_CRED", "VL_BC_COFINS",
        "ALIQ_COFINS", "VL_COFINS", "COD_CTA",
    ),
    "D990": ("REG", "QTD_LIN_D"),

    "F001": ("REG", "IND_MOV"),
    "F990": ("REG", "QTD_LIN_F"),

    "M001": ("REG", "IND_MOV"),
    "M100": (
        "REG", "COD_CRED", "IND_CRED_ORI", "VL_BC_PIS", "ALIQ_PIS", "QUANT_BC_PIS",
        "ALIQ_PIS_QUANT", "VL_CRED", "VL_AJUS_ACRES", "VL_AJUS_REDUC", "VL_CRED_DIF",
        "VL_CRED_DISP", "IND_DESC_CRED", "VL_CRED_DESC", "SLD_CRED",
    ),
    "M105": (
        "REG", "NAT_BC_CRED", "CST_PIS", "VL_BC_PIS_TOT", "VL_BC_PIS_CUM",
        "VL_BC_PIS_NC", "VL_BC_PIS", "QUANT_BC_PIS_TOT", "QUANT_BC_PIS", "DESC_CRED",
    ),
    "M200": (
        "REG", "VL_TOT_CONT_NC_PER", "VL_TOT_CRED_DESC", "VL_TOT_CRED_DESC_ANT",
        "VL_TOT_CONT_NC_DEV", "VL_RET_NC", "VL_OUT_DED_NC", "VL_CONT_NC_REC",
        "VL_TOT_CONT_CUM_PER", "VL_RET_CUM", "VL_OUT_DED_CUM", "VL_CONT_CUM_REC",
        "VL_TOT_CONT_REC",
    ),
    "M210": (
        "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "VL_AJUS_ACRES_BC_PIS",
        "VL_AJUS_REDUC_BC_PIS", "VL_BC_CONT_AJUS", "ALIQ_PIS", "QUANT_BC_PIS",
        "ALIQ_PIS_QUANT", "VL_CONT_APUR", "VL_AJUS_ACRES", "VL_AJUS_REDUC",
        "VL_CONT_DIFER", "VL_CONT_DIFER_ANT", "VL_CONT_PER",
    ),
    "M400": ("REG", "CST_PIS", "VL_TOT_REC", "COD_CTA", "DESC_COMPL"),
    "M410": ("REG", "NAT_REC", "VL_REC", "COD_CTA", "DESC_COMPL"),
    "M500": (
        "REG", "COD_CRED", "IND_CRED_ORI", "VL_BC_COFINS", "ALIQ_COFINS", "QUANT_BC_COFINS",
        "ALIQ_COFINS_QUANT", "VL_CRED", "VL_AJUS_ACRES", "VL_AJUS_REDUC", "VL_CRED_DIF",
        "VL_CRED_DISP", "IND_DESC_CRED", "VL_CRED_DESC", "SLD_CRED",
    ),
    "M505": (
        "REG", "NAT_BC_CRED", "CST_COFINS", "VL_BC_COFINS_TOT", "VL_BC_COFINS_CUM",
        "VL_BC_COFINS_NC", "VL_BC_COFINS", "QUANT_BC_COFINS_TOT", "QUANT_BC_COFINS",
        "DESC_CRED",
    ),
    "M600": (
        "REG", "VL_TOT_CONT_NC_PER", "VL_TOT_CRED_DESC", "VL_TOT_CRED_DESC_ANT",
        "VL_TOT_CONT_NC_DEV", "VL_RET_NC", "VL_OUT_DED_NC", "VL_CONT_NC_REC",
        "VL_TOT_CONT_CUM_PER", "VL_RET_CUM", "VL_OUT_DED_CUM", "VL_CONT_CUM_REC",
        "VL_TOT_CONT_REC",
    ),
    "M610": (
        "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "VL_AJUS_ACRES_BC_COFINS",
        "VL_AJUS_REDUC_BC_COFINS", "VL_BC_CONT_AJUS", "ALIQ_COFINS", "QUANT_BC_COFINS",
        "ALIQ_COFINS_QUANT", "VL_CONT_APUR", "VL_AJUS_ACRES", "VL_AJUS_REDUC",
        "VL_CONT_DIFER", "VL_CONT_DIFER_ANT", "VL_CONT_PER",
    ),
    "M800": ("REG", "CST_COFINS", "VL_TOT_REC", "COD_CTA", "DESC_COMPL"),
    "M810": ("REG", "NAT_REC", "VL_REC", "COD_CTA", "DESC_COMPL"),
    "M990": ("REG", "QTD_LIN_M"),
}


# EFD ICMS/IPI — sobrescreve os registros que antes eram exibidos com títulos
# amigáveis. Os demais registros já existentes em layout_excel.py usam nomes
# técnicos e continuam sendo aproveitados pelo exportador.
CAMPOS_EFD_FISCAL: dict[str, tuple[str, ...]] = {
    "0150": (
        "REG", "COD_PART", "NOME", "COD_PAIS", "CNPJ", "CPF", "IE", "COD_MUN",
        "SUFRAMA", "END", "NUM", "COMPL", "BAIRRO",
    ),
    "0190": ("REG", "UNID", "DESCR"),
    "0200": (
        "REG", "COD_ITEM", "DESCR_ITEM", "COD_BARRA", "COD_ANT_ITEM", "UNID_INV",
        "TIPO_ITEM", "COD_NCM", "EX_IPI", "COD_GEN", "COD_LST", "ALIQ_ICMS", "CEST",
    ),
    "0400": ("REG", "COD_NAT", "DESCR_NAT"),
    "C100": (
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT", "SER", "NUM_DOC",
        "CHV_NFE", "DT_DOC", "DT_E_S", "VL_DOC", "IND_PGTO", "VL_DESC", "VL_ABAT_NT",
        "VL_MERC", "IND_FRT", "VL_FRT", "VL_SEG", "VL_OUT_DA", "VL_BC_ICMS", "VL_ICMS",
        "VL_BC_ICMS_ST", "VL_ICMS_ST", "VL_IPI", "VL_PIS", "VL_COFINS", "VL_PIS_ST",
        "VL_COFINS_ST",
    ),
    "C170": (
        "REG", "NUM_ITEM", "COD_ITEM", "DESCR_COMPL", "QTD", "UNID", "VL_ITEM", "VL_DESC",
        "IND_MOV", "CST_ICMS", "CFOP", "COD_NAT", "VL_BC_ICMS", "ALIQ_ICMS", "VL_ICMS",
        "VL_BC_ICMS_ST", "ALIQ_ST", "VL_ICMS_ST", "IND_APUR", "CST_IPI", "COD_ENQ",
        "VL_BC_IPI", "ALIQ_IPI", "VL_IPI", "CST_PIS", "VL_BC_PIS", "ALIQ_PIS",
        "QUANT_BC_PIS", "ALIQ_PIS_QUANT", "VL_PIS", "CST_COFINS", "VL_BC_COFINS",
        "ALIQ_COFINS", "QUANT_BC_COFINS", "ALIQ_COFINS_QUANT", "VL_COFINS", "COD_CTA",
        "VL_ABAT_NT",
    ),
    "C190": (
        "REG", "CST_ICMS", "CFOP", "ALIQ_ICMS", "VL_OPR", "VL_BC_ICMS", "VL_ICMS",
        "VL_BC_ICMS_ST", "VL_ICMS_ST", "VL_RED_BC", "VL_IPI", "COD_OBS",
    ),
    "D100": (
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT", "SER", "SUB",
        "NUM_DOC", "CHV_CTE", "DT_DOC", "DT_A_P", "TP_CT-e", "CHV_CTE_REF", "VL_DOC",
        "VL_DESC", "IND_FRT", "VL_SERV", "VL_BC_ICMS", "VL_ICMS", "VL_NT", "COD_INF",
        "COD_CTA", "COD_MUN_ORIG", "COD_MUN_DEST",
    ),
    "D190": (
        "REG", "CST_ICMS", "CFOP", "ALIQ_ICMS", "VL_OPR", "VL_BC_ICMS", "VL_ICMS",
        "VL_RED_BC", "COD_OBS",
    ),
}


def obter_cabecalhos_oficiais(tipo_sped: str, codigo: str) -> tuple[str, ...] | None:
    """Retorna os nomes técnicos do leiaute adequado ao tipo da EFD."""

    tipo = str(tipo_sped or "").strip().casefold()
    reg = str(codigo or "").strip().upper()
    if "contrib" in tipo:
        return CAMPOS_EFD_CONTRIBUICOES.get(reg)
    if "icms" in tipo or "fiscal" in tipo:
        return CAMPOS_EFD_FISCAL.get(reg)
    return None
