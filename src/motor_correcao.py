"""
=========================================
FiscalPro
Motor de Correção
Versão 0.7.0
=========================================
"""

from pathlib import Path

from src.xml_reader import XMLReader
from src.corretor_cte import CorretorCTe


class MotorCorrecao:

    def __init__(self):

        self.relatorio = []

    def executar(self,
                 linhas_sped,
                 pasta_xml):

        # Carrega XMLs
        leitor = XMLReader(pasta_xml)

        xmls = leitor.carregar()

        # Corrige CHV_CTE
        corretor = CorretorCTe(
            linhas_sped,
            xmls
        )

        novo_sped = corretor.corrigir()

        self.relatorio = corretor.obter_relatorio()

        return {
            "linhas": novo_sped,
            "corrigidos": corretor.corrigidos,
            "nao_encontrados": corretor.nao_encontrados,
            "xml_lidos": leitor.total(),
            "xml_com_erro": leitor.total_erros(),
            "relatorio": self.relatorio
        }

    def salvar_sped(self,
                    linhas,
                    arquivo_original):

        arquivo_original = Path(arquivo_original)

        destino = arquivo_original.with_name(
            arquivo_original.stem + "_CORRIGIDO.txt"
        )

        with open(destino,
                  "w",
                  encoding="utf-8") as f:

            f.writelines(linhas)

        return str(destino)

    def salvar_relatorio(self,
                         caminho):

        with open(caminho,
                  "w",
                  encoding="utf-8") as arq:

            arq.write("=====================================\n")
            arq.write("FiscalPro v0.7.0\n")
            arq.write("RELATÓRIO DE CORREÇÕES\n")
            arq.write("=====================================\n\n")

            for item in self.relatorio:

                arq.write(f"CT-e: {item['numero']}\n")
                arq.write(f"Antes : {item['antes']}\n")
                arq.write(f"Depois: {item['depois']}\n")
                arq.write("\n")

        return caminho