"""
=========================================
FiscalPro
Versão 0.7.0

Corretor Automático de CHV_CTE
=========================================
"""


class CorretorCTe:

    def __init__(self, linhas_sped, xmls):

        self.linhas = linhas_sped
        self.xmls = xmls

        self.corrigidos = 0
        self.nao_encontrados = 0
        self.relatorio = []

    def corrigir(self):

        novo_sped = []

        for linha in self.linhas:

            if not linha.startswith("|D100|"):
                novo_sped.append(linha)
                continue

            campos = linha.rstrip("\n").split("|")

            if len(campos) <= 10:
                novo_sped.append(linha)
                continue

            numero_cte = campos[9]
            chave_sped = campos[10]

            xml = self.xmls.get(numero_cte)

            if xml is None:
                self.nao_encontrados += 1
                novo_sped.append(linha)
                continue

            chave_xml = xml["chave"]

            if chave_xml and chave_xml != chave_sped:

                self.relatorio.append({
                    "numero": numero_cte,
                    "antes": chave_sped,
                    "depois": chave_xml,
                    "arquivo": xml["arquivo"]
                })

                campos[10] = chave_xml
                linha = "|".join(campos) + "\n"

                self.corrigidos += 1

            novo_sped.append(linha)

        return novo_sped

    def obter_relatorio(self):
        return self.relatorio