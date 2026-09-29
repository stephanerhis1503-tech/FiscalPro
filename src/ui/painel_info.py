from tkinter import X
from tkinter import ttk


class PainelInfo(ttk.LabelFrame):
    def __init__(self, master):
        super().__init__(
            master,
            text="Contexto do arquivo",
            padding=8,
            style="Card.TLabelframe",
        )
        self.pack(fill=X, padx=14, pady=(0, 7))
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.lbl_empresa = ttk.Label(self, text="Empresa: -", style="CardSubtitle.TLabel")
        self.lbl_empresa.grid(row=0, column=0, sticky="w", padx=(0, 15), pady=2)

        self.lbl_periodo = ttk.Label(self, text="Período: -", style="CardSubtitle.TLabel")
        self.lbl_periodo.grid(row=0, column=1, sticky="w", pady=2)

        self.lbl_sped = ttk.Label(
            self,
            text="SPED: -",
            style="CardSubtitle.TLabel",
            wraplength=520,
        )
        self.lbl_sped.grid(row=1, column=0, sticky="w", padx=(0, 15), pady=2)

        self.lbl_xml = ttk.Label(
            self,
            text="XML: -",
            style="CardSubtitle.TLabel",
            wraplength=520,
        )
        self.lbl_xml.grid(row=1, column=1, sticky="w", pady=2)

    def atualizar(self, empresa, periodo, sped, xml):
        self.lbl_empresa.config(text=f"Empresa: {empresa}")
        self.lbl_periodo.config(text=f"Período: {periodo}")
        self.lbl_sped.config(text=f"SPED: {sped}")
        self.lbl_xml.config(text=f"XML: {xml}")
