"""
=========================================
FiscalPro
Modelo do Registro 0200
=========================================
"""


class Registro0200:

    def __init__(self, linha):

        self.linha_original = linha
        campos = linha.rstrip("\r\n").split("|")

        self.codigo = self._campo(campos, 2)
        self.descricao = self._campo(campos, 3)
        self.codigo_barra = self._campo(campos, 4)
        self.codigo_anterior = self._campo(campos, 5)
        self.unidade = self._campo(campos, 6)
        self.tipo_item = self._campo(campos, 7)
        self.ncm = self._somente_numeros(self._campo(campos, 8))
        self.ex_ipi = self._campo(campos, 9)
        self.codigo_genero = self._campo(campos, 10)
        self.codigo_servico = self._campo(campos, 11)
        self.aliquota_icms = self._numero(self._campo(campos, 12))
        self.cest = self._somente_numeros(self._campo(campos, 13))

    @staticmethod
    def _campo(campos, indice):

        if indice < len(campos):
            return campos[indice].strip()

        return ""

    @staticmethod
    def _somente_numeros(valor):

        return "".join(
            caractere
            for caractere in str(valor or "")
            if caractere.isdigit()
        )

    @staticmethod
    def _numero(valor):

        texto = str(valor or "").strip().replace("%", "")

        if not texto:
            return 0.0

        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", ".")

        try:
            return float(texto)
        except (TypeError, ValueError):
            return 0.0
