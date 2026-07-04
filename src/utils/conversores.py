"""
=========================================
FiscalPro
Versão 0.6.2

Conversores
=========================================
"""


def texto_para_float(valor):

    if valor is None:
        return 0.0

    valor = valor.strip()

    if valor == "":
        return 0.0

    valor = valor.replace(".", "")
    valor = valor.replace(",", ".")

    try:
        return float(valor)

    except ValueError:
        return 0.0


def texto_para_int(valor):

    return int(texto_para_float(valor))