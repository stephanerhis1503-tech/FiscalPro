"""
=========================================
FiscalPro
Modelo do Registro C170
=========================================
"""

from src.utils.conversores import texto_para_float


class RegistroC170:

    def __init__(self, linha):

        self.linha_original = linha
        campos = linha.rstrip("\r\n").split("|")

        self.numero_item = self._campo(campos, 2)
        self.codigo = self._campo(campos, 3)
        self.descricao_complementar = self._campo(campos, 4)
        self.quantidade = texto_para_float(self._campo(campos, 5))
        self.unidade = self._campo(campos, 6)
        self.valor_item = texto_para_float(self._campo(campos, 7))
        self.desconto = texto_para_float(self._campo(campos, 8))
        self.movimentacao = self._campo(campos, 9)

        self.cst_icms = self._campo(campos, 10)
        self.cfop = self._campo(campos, 11)
        self.codigo_natureza = self._campo(campos, 12)
        self.base_icms = texto_para_float(self._campo(campos, 13))
        self.aliquota_icms = texto_para_float(self._campo(campos, 14))
        self.valor_icms = texto_para_float(self._campo(campos, 15))
        self.base_st = texto_para_float(self._campo(campos, 16))
        self.aliquota_st = texto_para_float(self._campo(campos, 17))
        self.valor_st = texto_para_float(self._campo(campos, 18))

        self.cst_ipi = self._campo(campos, 20)
        self.base_ipi = texto_para_float(self._campo(campos, 22))
        self.aliquota_ipi = texto_para_float(self._campo(campos, 23))
        self.valor_ipi = texto_para_float(self._campo(campos, 24))

        self.cst_pis = self._campo(campos, 25)
        self.base_pis = texto_para_float(self._campo(campos, 26))
        self.aliquota_pis = texto_para_float(self._campo(campos, 27))
        self.valor_pis = texto_para_float(self._campo(campos, 30))

        self.cst_cofins = self._campo(campos, 31)
        self.base_cofins = texto_para_float(self._campo(campos, 32))
        self.aliquota_cofins = texto_para_float(self._campo(campos, 33))
        self.valor_cofins = texto_para_float(self._campo(campos, 36))

        self.ncm = ""
        self.cest = ""
        self.descricao_0200 = ""

    def vincular_cadastro(self, registro_0200):

        if registro_0200 is None:
            return

        self.ncm = registro_0200.ncm
        self.cest = registro_0200.cest
        self.descricao_0200 = registro_0200.descricao

    def _campo(self, campos, indice):

        if indice < len(campos):
            return campos[indice].strip()

        return ""
