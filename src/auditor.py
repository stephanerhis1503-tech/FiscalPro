"""
FiscalPro
Versão: 0.6.0
Sprint 6

Responsável pela coordenação das auditorias.
"""

from collections import Counter

from src.validadores.validador_0200 import Validador0200
from src.validadores.validador_c170 import ValidadorC170
from src.validadores.validador_escrituracao import ValidadorEscrituracao


class AuditorFiscal:

    def __init__(self, linhas):

        self.linhas = linhas
        self.registros = Counter()

    def auditar(self):

        # Contagem dos registros
        for linha in self.linhas:

            if not linha.startswith("|"):
                continue

            campos = linha.strip().split("|")

            if len(campos) > 1:
                self.registros[campos[1]] += 1

        # Auditoria do Registro 0200
        auditor_0200 = Validador0200(self.linhas)
        resultado_0200 = auditor_0200.validar()

        # Auditoria do Registro C170
        auditor_c170 = ValidadorC170(self.linhas)
        resultado_c170 = auditor_c170.validar()

        # Auditoria da Escrituração
        auditor_escrituracao = ValidadorEscrituracao(self.linhas)
        resultado_escrituracao = auditor_escrituracao.validar()

        retorno = {
            "registros": self.registros,
            "auditoria_0200": resultado_0200,
            "auditoria_c170": resultado_c170,
        }

        retorno.update(resultado_escrituracao)

        return retorno