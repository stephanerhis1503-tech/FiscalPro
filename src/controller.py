"""
=========================================
FiscalPro
Controller
Versão 0.8.0
=========================================
"""

from src.leitor_sped import LeitorSPED
from src.analisador import AnalisadorSPED
from src.formatador import FormatadorAuditoria
from src.motor_correcao import MotorCorrecao

from src.core.logger import logger
from src.core.state import AppState


class FiscalController:

    def __init__(self):

        self.state = AppState()

    def abrir_sped(self, arquivo):

        logger.info(f"Abrindo SPED: {arquivo}")

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

        # Salva o estado atual da aplicação
        self.state.arquivo_sped = arquivo
        self.state.leitor = leitor
        self.state.resultado = resultado

        logger.info("SPED carregado com sucesso.")

        return {
            "leitor": leitor,
            "resultado": resultado,
            "registro": registro,
            "resumo": resumo
        }

    def corrigir_sped(self, linhas_sped, pasta_xml):

        logger.info("Iniciando correção do SPED.")

        motor = MotorCorrecao()

        resultado = motor.executar(
            linhas_sped,
            pasta_xml
        )

        logger.info("Correção finalizada.")

        return resultado