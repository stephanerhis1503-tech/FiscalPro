import xml.etree.ElementTree as ET
from pathlib import Path


class LeitorXML:

    def ler_pasta(self, pasta):

        xmls = []

        pasta = Path(pasta)

        for arquivo in pasta.glob("*.xml"):

            try:

                xmls.append(self.ler_xml(arquivo))

            except Exception as erro:

                print(f"Erro em {arquivo.name}: {erro}")

        return xmls

    def ler_xml(self, arquivo):

        tree = ET.parse(arquivo)

        root = tree.getroot()

        return root