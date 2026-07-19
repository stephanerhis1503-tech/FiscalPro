from src.tributacao import BancoTributario


class TributacaoService:

    def __init__(self):
        self.banco = BancoTributario()

    def consultar_ncm(self, codigo):
        return self.banco.consultar_ncm(codigo)

    def listar_ncm(self):
        return self.banco.listar_ncm()

    def pesquisar_descricao(self, texto):
        return self.banco.pesquisar_descricao(texto)

    def existe_ncm(self, codigo):
        return self.banco.existe_ncm(codigo)
        
    def fechar(self):
        self.banco.fechar()