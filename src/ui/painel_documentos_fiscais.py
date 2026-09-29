"""Central NF-e / NFS-e sem alterar o funcionamento interno da NFS-e existente."""

from tkinter import BOTH
from tkinter import ttk

from .painel_manifestacao_nfe import PainelManifestacaoNFe
from .painel_ibscbs_xml import PainelIBSCBSXML
from .painel_nfse_nacional import PainelNFSeNacional


class PainelDocumentosFiscais(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        notebook = ttk.Notebook(self)
        notebook.pack(fill=BOTH, expand=True)

        aba_nfse = ttk.Frame(notebook, style="Page.TFrame")
        aba_nfe = ttk.Frame(notebook, style="Page.TFrame")
        aba_ibscbs = ttk.Frame(notebook, style="Page.TFrame")
        notebook.add(aba_nfse, text="  NFS-e Nacional  ")
        notebook.add(aba_nfe, text="  NF-e • Manifestação  ")
        notebook.add(aba_ibscbs, text="  IBS/CBS • XML  ")

        # A classe original permanece intacta: apenas é hospedada nesta central.
        self.painel_nfse = PainelNFSeNacional(aba_nfse)
        self.painel_nfse.pack(fill=BOTH, expand=True)

        self.painel_nfe = PainelManifestacaoNFe(aba_nfe)
        self.painel_nfe.pack(fill=BOTH, expand=True)

        self.painel_ibscbs = PainelIBSCBSXML(aba_ibscbs)
        self.painel_ibscbs.pack(fill=BOTH, expand=True)
