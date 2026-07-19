import tkinter as tk
from tkinter import ttk, messagebox

from src.tributario.motor import MotorTributario


class TelaConsultaTributaria(tk.Toplevel):

    def __init__(self, master=None):
        super().__init__(master)

        self.title("FiscalPro - Consulta Tributária")
        self.geometry("700x500")

        self.motor = MotorTributario()

        self.criar_interface()

    def criar_interface(self):

        # Configura o layout da janela
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        # ===== Pesquisa =====
        frame_pesquisa = ttk.LabelFrame(self, text="Consulta")
        frame_pesquisa.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ttk.Label(frame_pesquisa, text="NCM:").grid(row=0, column=0, padx=5, pady=10)

        self.entry_ncm = ttk.Entry(frame_pesquisa, width=30)
        self.entry_ncm.grid(row=0, column=1, padx=5)

        ttk.Button(
            frame_pesquisa,
            text="Consultar",
            command=self.consultar
        ).grid(row=0, column=2, padx=10)

        # ===== Notebook =====
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

        # Abas
        self.aba_produto = ttk.Frame(self.notebook)
        self.aba_tributacao = ttk.Frame(self.notebook)
        self.aba_reforma = ttk.Frame(self.notebook)
        self.aba_legislacao = ttk.Frame(self.notebook)
        self.aba_observacoes = ttk.Frame(self.notebook)

        self.notebook.add(self.aba_produto, text="Produto")
        self.notebook.add(self.aba_tributacao, text="Tributação")
        self.notebook.add(self.aba_reforma, text="Reforma Tributária")
        self.notebook.add(self.aba_legislacao, text="Legislação")
        self.notebook.add(self.aba_observacoes, text="Observações")

        frame_produto = ttk.LabelFrame(
            self.aba_produto,
            text="Informações do Produto"
        )

        frame_produto.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )
        
        ttk.Label(frame_produto, text="NCM:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.lbl_ncm = ttk.Label(frame_produto, text="-")
        self.lbl_ncm.grid(row=0, column=1, sticky="w")

        ttk.Label(frame_produto, text="Descrição:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.lbl_descricao = ttk.Label(frame_produto, text="-")
        self.lbl_descricao.grid(row=1, column=1, sticky="w")

        ttk.Label(frame_produto, text="CEST:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.lbl_cest = ttk.Label(frame_produto, text="-")
        self.lbl_cest.grid(row=2, column=1, sticky="w")

        frame_tributacao = ttk.LabelFrame(
            self.aba_tributacao,
            text="Tributação Atual"
        )

        frame_tributacao.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )
        
        ttk.Label(frame_tributacao, text="PIS CST:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.lbl_pis = ttk.Label(frame_tributacao, text="-")
        self.lbl_pis.grid(row=0, column=1, sticky="w")

        ttk.Label(frame_tributacao, text="COFINS CST:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.lbl_cofins = ttk.Label(frame_tributacao, text="-")
        self.lbl_cofins.grid(row=1, column=1, sticky="w")

        ttk.Label(frame_tributacao, text="ICMS:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.lbl_icms = ttk.Label(frame_tributacao, text="-")
        self.lbl_icms.grid(row=2, column=1, sticky="w")

        ttk.Label(frame_tributacao, text="ICMS-ST:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.lbl_st = ttk.Label(frame_tributacao, text="-")
        self.lbl_st.grid(row=3, column=1, sticky="w")

    def consultar(self):

        ncm = self.entry_ncm.get().strip()

        if not ncm:

            messagebox.showwarning(
                "Aviso",
                "Informe um NCM."
            )
            return

        dados = self.motor.consultar_ncm(ncm)
        print(dados)

        if not dados["encontrado"]:

            self.resultado.insert(
                tk.END,
                "NCM não encontrado."
            )

            return

        produto = dados["produto"]

        self.lbl_ncm.config(text=produto["ncm"])

        self.lbl_descricao.config(text=produto["descricao"])

        self.lbl_cest.config(text=produto["cest"])