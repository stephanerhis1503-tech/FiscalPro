from tributacao import BancoTributario

banco = BancoTributario()

for ncm in banco.listar_ncm():
    print(ncm)

banco.fechar()