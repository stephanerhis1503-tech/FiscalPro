"""
=========================================
FiscalPro

Índice dos XML

Versão 0.5.1
=========================================
"""


class IndiceXML:

    def __init__(self):

        self.xmls = {}

    def adicionar(self, numero, chave, arquivo):

        self.xmls[numero] = {

            "chave": chave,

            "arquivo": arquivo

        }

    def existe(self, numero):

        return numero in self.xmls

    def chave(self, numero):

        return self.xmls[numero]["chave"]

    def arquivo(self, numero):

        return self.xmls[numero]["arquivo"]

    def total(self):

        return len(self.xmls)