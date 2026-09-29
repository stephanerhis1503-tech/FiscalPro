from tkinter import *
from tkinter import ttk
from tkinter import messagebox

from src.services.tributacao_service import TributacaoService


class ConsultaTributaria(Toplevel):

    def __init__(self, master=None):

        super().__init__(master)

        self.title("Consulta Tributária")

        self.geometry("700x500")

        self.resizable(False, False)

        self.service = TributacaoService()

        self.criar_interface()

    def criar_interface(self):

        frame = Frame(self)
        frame.pack(fill="x", padx=15, pady=15)

        Label(frame, text="NCM").grid(row=0, column=0, sticky="w")

        self.ed_ncm = Entry(frame, width=20)
        self.ed_ncm.grid(row=0, column=1, padx=5)

        ttk.Button(
            frame,
            text="Consultar",
            command=self.consultar
        ).grid(row=0, column=2, padx=10)

        self.txt = Text(self, height=22)
        self.txt.pack(fill="both", expand=True, padx=15, pady=10)

    def consultar(self):

        codigo = self.ed_ncm.get().strip()

        dados = self.service.consultar_ncm(codigo)

        self.txt.delete("1.0", END)

        if dados is None:
            messagebox.showwarning(
                "FiscalPro",
                "NCM não encontrado."
            )
            return

        for campo, valor in dados.items():
            self.txt.insert(
                END,
                f"{campo}: {valor}\n"
            )