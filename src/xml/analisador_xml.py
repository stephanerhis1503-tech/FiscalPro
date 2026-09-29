from src.xml.leitor_xml import LeitorXML
from src.xml.extrator_produtos import ExtratorProdutos
from src.repositorios.tributacao_repository import TributacaoRepository


class AnalisadorXML:

    def analisar_pasta(self, pasta):

        leitor = LeitorXML()
        extrator = ExtratorProdutos()

        documentos = leitor.ler_pasta(pasta)

        resultado = []

        for documento in documentos:

            produtos = extrator.extrair(documento)

            for produto in produtos:

                ficha = TributacaoRepository.buscar_ficha(produto["ncm"])

                if ficha is None:
                    status = "❌ NCM NÃO CADASTRADO"

                elif ficha.status == "SEM_TRIBUTACAO":
                    status = "⚠ SEM TRIBUTAÇÃO"

                else:
                    status = "✅ TRIBUTAÇÃO OK"

                resultado.append({

                    "codigo": produto["codigo"],
                    "descricao": produto["descricao"],
                    "ncm": produto["ncm"],
                    "cfop": produto["cfop"],
                    "quantidade": produto["quantidade"],
                    "valor": produto["valor"],

                    "status": status,

                    "ficha": ficha

                })

        return resultado