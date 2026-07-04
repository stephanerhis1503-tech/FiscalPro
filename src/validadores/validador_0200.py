"""
FiscalPro
Versão: 0.4.1

Validador do Registro 0200
"""

class Validador0200:

    def __init__(self, linhas):
        self.linhas = linhas

    def validar(self):

        resultado = {
            "produtos": 0,
            "sem_descricao": [],
            "sem_unidade": [],
            "sem_ncm": [],
            "ncm_invalido": []
        }

        for numero_linha, linha in enumerate(self.linhas, start=1):

            if not linha.startswith("|0200|"):
                continue

            resultado["produtos"] += 1

            campos = linha.strip().split("|")

            codigo = campos[2]
            descricao = campos[3]
            unidade = campos[6]
            ncm = campos[8]

            if descricao.strip() == "":
                resultado["sem_descricao"].append(codigo)

            if unidade.strip() == "":
                resultado["sem_unidade"].append(codigo)

            if ncm.strip() == "":
                resultado["sem_ncm"].append(codigo)

            elif not (len(ncm) == 8 and ncm.isdigit()):
                resultado["ncm_invalido"].append(codigo)

        return resultado