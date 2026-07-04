"""
=========================================
FiscalPro
Versão: 0.6.2

Validador do Registro C170
=========================================
"""

from src.modelos.registro_c170 import RegistroC170


class ValidadorC170:

    def __init__(self, linhas):
        self.linhas = linhas

    def validar(self):

        resultado = {
            "itens": 0,
            "erros": []
        }

        for numero_linha, linha in enumerate(self.linhas, start=1):

            if not linha.startswith("|C170|"):
                continue

            registro = RegistroC170(linha)

            resultado["itens"] += 1

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
                resultado["erros"].append({
                    "linha": numero_linha,
                    "produto": registro.codigo,
                    "erro": "CFOP não informado"
                })

        return resultado