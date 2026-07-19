from services.tributacao_service import TributacaoService

service = TributacaoService()

print("NCM cadastrados:\n")

for item in service.listar_ncm():
    print(item)