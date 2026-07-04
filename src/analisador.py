from src.auditor import AuditorFiscal


class AnalisadorSPED:

    def __init__(self, linhas):

        self.linhas = linhas

    def analisar(self):

        auditor = AuditorFiscal(self.linhas)

        return auditor.auditar()