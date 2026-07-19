from src.modelos.diagnostico import Diagnostico


class ValidadorEscrituracao:

    def __init__(self, linhas):
        self.linhas = linhas

    def validar(self):

        diagnosticos = []

        numero_nf = ""

        for linha in self.linhas:

            if linha.startswith("|C100|"):

                campos = linha.split("|")

                if len(campos) > 8:
                    numero_nf = campos[8]

            elif linha.startswith("|C170|"):

                campos = linha.split("|")

                if len(campos) < 11:
                    continue

                item = campos[2]
                cfop = campos[11] if len(campos) > 11 else ""
                ncm = campos[10] if len(campos) > 10 else ""

                # NCM vazio
                if not ncm:

                    diagnosticos.append(

                        Diagnostico(

                            codigo="FP100",

                            titulo="Produto sem NCM",

                            nota=numero_nf,

                            item=int(item),

                            gravidade="Alta",

                            problema="Item escriturado sem NCM.",

                            causa="Cadastro do produto incompleto.",

                            correcao="Cadastrar corretamente o NCM do produto.",

                            automatico=False

                        )

                    )

                # CFOP vazio
                if not cfop:

                    diagnosticos.append(

                        Diagnostico(

                            codigo="FP101",

                            titulo="Produto sem CFOP",

                            nota=numero_nf,

                            item=int(item),

                            gravidade="Alta",

                            problema="Item escriturado sem CFOP.",

                            causa="Erro de escrituração.",

                            correcao="Reescriturar a nota.",

                            automatico=False

                        )

                    )

        return {
            "diagnosticos_escrituracao": diagnosticos
        }