"""
=========================================
FiscalPro
Controller
Versão 0.7.0
=========================================
"""

from src.leitor_sped import LeitorSPED
from src.analisador import AnalisadorSPED
from src.formatador import FormatadorAuditoria


class FiscalController:

    def abrir_sped(self, arquivo):

        leitor = LeitorSPED(arquivo)
        leitor.carregar()

        analisador = AnalisadorSPED(leitor.linhas)

        resultado = analisador.analisar()

        registro = leitor.obter_registro_0000()

        resumo = ""

        if registro:

            resumo = FormatadorAuditoria.montar_resumo(
                registro[6],
                f"{registro[4]} até {registro[5]}",
                leitor,
                resultado
            )

        return {
            "leitor": leitor,
            "resultado": resultado,
            "registro": registro,
            "resumo": resumo
        }