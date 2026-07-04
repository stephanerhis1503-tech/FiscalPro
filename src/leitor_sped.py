class LeitorSPED:

    def __init__(self, caminho):
        self.caminho = caminho
        self.linhas = []

    def carregar(self):
        with open(self.caminho, "r", encoding="latin1") as arquivo:
            self.linhas = arquivo.readlines()

    def total_linhas(self):
        return len(self.linhas)

    def contar_registros(self, registro):
        return sum(
            1
            for linha in self.linhas
            if linha.startswith(f"|{registro}|")
        )

    def obter_registro_0000(self):
        for linha in self.linhas:
            if linha.startswith("|0000|"):
                return linha.strip().split("|")
        return None