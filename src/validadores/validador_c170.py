"""
=========================================
FiscalPro
Versão: 0.6.2

Validador do Registro C170
=========================================
"""

from src.modelos.registro_c170 import RegistroC170
from src.services.motor_fiscal import MotorFiscal


class ValidadorC170:

    def __init__(self, linhas):
        self.linhas = linhas
        self.motor = MotorFiscal()

    def adicionar_erro(
        self,
        resultado,
        linha,
        produto,
        codigo,
        erro,
        causa,
        correcao,
        gravidade="Alta"
):

        resultado["erros"].append({

        "codigo": codigo,

        "linha": linha,

        "produto": produto,

        "erro": erro,

        "causa": causa,

        "correcao": correcao,

        "gravidade": gravidade

    })

    def validar(self):

        resultado = {
            "itens": 0,
            "erros": []
        }

        for numero_linha, linha in enumerate(self.linhas, start=1):

            if not linha.startswith("|C170|"):
                continue

            registro = RegistroC170(linha)

            print("C170 encontrado:", registro.codigo)

            resultado["itens"] += 1
            
            print("Itens:", resultado["itens"])

            resultado_cfop = self.motor.validar_cfop(registro.cfop)

            if not resultado_cfop["ok"]:

                self.adicionar_erro(

                    resultado,

                    numero_linha,

                    registro.codigo,

                    resultado_cfop["codigo"],

                    resultado_cfop["mensagem"],

                    "CFOP inválido para a escrituração.",

                    "Revisar a Natureza da Operação no Digisat."

                )

       

            # Quantidade
            if registro.quantidade <= 0:
                resultado["erros"].append({
                    "linha": numero_linha,
                    "produto": registro.codigo,
                    "erro": "Quantidade igual a zero"
                })

            # Unidade
            if registro.unidade == "":
                resultado["erros"].append({
                    "linha": numero_linha,
                    "produto": registro.codigo,
                    "erro": "Unidade não informada"
                })

            # Valor do item
            if registro.valor_item <= 0:
                resultado["erros"].append({
                    "linha": numero_linha,
                    "produto": registro.codigo,
                    "erro": "Valor do item igual a zero"
                })

            # CST ICMS
            if registro.cst_icms == "":
                resultado["erros"].append({
                    "linha": numero_linha,
                    "produto": registro.codigo,
                    "erro": "CST ICMS não informado"
                })

           # CFOP
            if registro.cfop == "":

                self.adicionar_erro(

                    resultado,

                     numero_linha,

                    registro.codigo,

                    "FP201",

                    "CFOP não informado",

                    "Natureza da operação não preencheu o CFOP do item.",

                    "Revisar a Natureza da Operação no Digisat e reescriturar a nota."

                )

        return resultado