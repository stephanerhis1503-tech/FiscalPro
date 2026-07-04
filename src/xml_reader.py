"""
=========================================
FiscalPro
Versão: 0.5.1

Leitor de XML de CT-e
=========================================
"""

import os
import xml.etree.ElementTree as ET


class XMLReader:

    def __init__(self, pasta):

        self.pasta = pasta

        self.xmls = {}

        self.total_xml = 0

        self.erros = 0

    def carregar(self):

        self.xmls.clear()

        self.total_xml = 0

        self.erros = 0

        for arquivo in os.listdir(self.pasta):

            if not arquivo.lower().endswith(".xml"):
                continue

            caminho = os.path.join(self.pasta, arquivo)

            try:

                tree = ET.parse(caminho)

                root = tree.getroot()

                chave = None
                numero = None

                for elemento in root.iter():

                    if elemento.tag.endswith("infCte"):

                        chave = elemento.attrib.get("Id", "")

                        if chave.startswith("CTe"):

                            chave = chave[3:]

                    elif elemento.tag.endswith("nCT"):

                        numero = elemento.text

                if numero and chave:

                    self.xmls[numero] = {
                        "chave": chave,
                        "arquivo": arquivo
                    }

                    self.total_xml += 1

            except Exception:

                self.erros += 1

        return self.xmls

    def total(self):

        return self.total_xml

    def total_erros(self):

        return self.erros