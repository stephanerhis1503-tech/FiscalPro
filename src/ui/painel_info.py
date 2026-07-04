from tkinter import *
from tkinter import ttk


class PainelInfo(ttk.LabelFrame):

    def __init__(self, master):
        super().__init__(master, text="Informações")

        self.pack(fill=X, padx=15, pady=10)

        self.lbl_empresa = ttk.Label(self, text="Empresa: -")
        self.lbl_empresa.grid(row=0, column=0, sticky="w", padx=10, pady=5)

        self.lbl_periodo = ttk.Label(self, text="Período: -")
        self.lbl_periodo.grid(row=1, column=0, sticky="w", padx=10, pady=5)

        self.lbl_sped = ttk.Label(self, text="SPED: -")
        self.lbl_sped.grid(row=2, column=0, sticky="w", padx=10, pady=5)

        self.lbl_xml = ttk.Label(self, text="XML: -")
        self.lbl_xml.grid(row=3, column=0, sticky="w", padx=10, pady=5)

    def atualizar(self, empresa, periodo, sped, xml):

        self.lbl_empresa.config(text=f"Empresa: {empresa}")
        self.lbl_periodo.config(text=f"Período: {periodo}")
        self.lbl_sped.config(text=f"SPED: {sped}")
        self.lbl_xml.config(text=f"XML: {xml}")