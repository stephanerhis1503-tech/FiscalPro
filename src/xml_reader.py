"""
=========================================
FiscalPro
Versão: 0.7.0

Leitor de XML de CT-e
=========================================
"""

import os
import xml.etree.ElementTree as ET
from src.core.logger import logger
from src.core.config import ENCODING


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

        if not os.path.isdir(self.pasta):
            return self.xmls

        for arquivo in os.listdir(self.pasta):

            if not arquivo.lower().endswith(".xml"):
                continue

            caminho = os.path.join(self.pasta, arquivo)

            try:

                tree = ET.parse(caminho)
                root = tree.getroot()

                chave = ""
                numero = ""
                serie = ""
                cnpj = ""

                for elemento in root.iter():

                    tag = elemento.tag.split("}")[-1]

                    if tag == "infCte":

                        chave = elemento.attrib.get("Id", "")

                        if chave.startswith("CTe"):
                            chave = chave[3:]

                    elif tag == "nCT":

                        numero = (elemento.text or "").strip()

                    elif tag == "serie":

                        serie = (elemento.text or "").strip()

                    elif tag == "CNPJ" and not cnpj:

                        cnpj = (elemento.text or "").strip()

                if numero:

                    self.xmls[numero] = {
                        "numero": numero,
                        "serie": serie,
                        "chave": chave,
                        "cnpj": cnpj,
                        "arquivo": arquivo,
                        "caminho": caminho
                    }

                    self.total_xml += 1

            except Exception as erro:

                self.erros += 1
                logger.error(f"Erro ao ler XML '{arquivo}': {erro}")

        return self.xmls

    def total(self):

        return self.total_xml

    def total_erros(self):

        return self.erros