class ExtratorProdutos:

    def extrair(self, root):

        ns = {
            "nfe": "http://www.portalfiscal.inf.br/nfe"
        }

        produtos = []

        for det in root.findall(".//nfe:det", ns):

            prod = det.find("nfe:prod", ns)

            if prod is None:
                continue

            produtos.append({

                "codigo": prod.findtext("nfe:cProd", default="", namespaces=ns),

                "descricao": prod.findtext("nfe:xProd", default="", namespaces=ns),

                "ncm": prod.findtext("nfe:NCM", default="", namespaces=ns),

                "cfop": prod.findtext("nfe:CFOP", default="", namespaces=ns),

                "quantidade": prod.findtext("nfe:qCom", default="", namespaces=ns),

                "valor": prod.findtext("nfe:vUnCom", default="", namespaces=ns)

            })

        return produtos