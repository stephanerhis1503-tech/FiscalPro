"""
=========================================
FiscalPro
Versão 0.5.0

Corretor Automático de CHV_CTE
=========================================
"""


class CorretorCTe:

    def __init__(self, linhas_sped, xmls):

        self.linhas = linhas_sped
        self.xmls = xmls

        self.corrigidos = 0
        self.nao_encontrados = 0

    def corrigir(self):

        novo_sped = []

        for linha in self.linhas:

            if not linha.startswith("|D100|"):

                novo_sped.append(linha)
                continue

            campos = linha.strip().split("|")

            numero_cte = campos[9]

            chave_sped = campos[10]

            chave_xml = self.xmls.get(numero_cte)

            if chave_xml is None:

                self.nao_encontrados += 1

                novo_sped.append(linha)

                continue

            if chave_xml != chave_sped:

                campos[10] = chave_xml

                linha = "|".join(campos) + "\n"

                self.corrigidos += 1

            novo_sped.append(linha)

        return novo_sped