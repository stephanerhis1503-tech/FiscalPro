"""
=========================================
FiscalPro
Motor Fiscal
Versão: 0.1.0
=========================================
"""

from src.services.tributacao_service import TributacaoService


class MotorFiscal:

    def __init__(self):

        self.tributacao = TributacaoService()

    # ---------------------------------
    # CONSULTAS
    # ---------------------------------

    def consultar_ncm(self, codigo):

        return self.tributacao.consultar_ncm(codigo)

    def existe_ncm(self, codigo):

        return self.tributacao.existe_ncm(codigo)

    # ---------------------------------
    # VALIDAÇÕES
    # ---------------------------------

    def validar_ncm(self, codigo):

        dados = self.consultar_ncm(codigo)

        if dados is None:

            return {
                "ok": False,
                "codigo": "FP200",
                "mensagem": "NCM não cadastrado."
            }

        return {
            "ok": True,
            "dados": dados
        }

    def validar_cfop(self, cfop):

        if not cfop:

            return {
                "ok": False,
                "codigo": "FP201",
                "mensagem": "CFOP não informado."
            }

        return {
            "ok": True
        }

    def validar_cst(self, cst):

        if not cst:

            return {
                "ok": False,
                "codigo": "FP202",
                "mensagem": "CST não informado."
            }

        return {
            "ok": True
        }