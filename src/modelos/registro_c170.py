"""
=========================================
FiscalPro
Versão: 0.6.1

Modelo do Registro C170
=========================================
"""

from src.utils.conversores import texto_para_float


class RegistroC170:

    def __init__(self, linha):

        self.linha_original = linha

        campos = linha.strip().split("|")

        self.numero_item = self._campo(campos, 2)
        self.codigo = self._campo(campos, 3)
        self.descricao_complementar = self._campo(campos, 4)
        self.quantidade = texto_para_float(self._campo(campos, 5))
        self.unidade = self._campo(campos, 6)
        self.valor_item = texto_para_float(self._campo(campos, 7))
        self.desconto = self._campo(campos, 8)
        self.movimentacao = self._campo(campos, 9)
        self.cst_icms = self._campo(campos, 10)
        self.cfop = self._campo(campos, 11)
        self.ncm = ""
        self.cst_pis = ""
        self.cst_cofins = ""
        self.base_icms = 0.0
        self.valor_icms = 0.0
        self.base_st = 0.0
        self.valor_st = 0.0
        self.aliquota_icms = 0.0

    def _campo(self, campos, indice):

        if indice < len(campos):
            return campos[indice].strip()

        return ""