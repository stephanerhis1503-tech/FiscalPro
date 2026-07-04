"""
=========================================
FiscalPro
Janela Principal
=========================================
"""

from tkinter import *
from tkinter import ttk

from .estilos import *
from .componentes import *
from .dashboard import Dashboard
from .painel_info import PainelInfo


class JanelaPrincipal:

    def __init__(self):

        self.janela = Tk()

        self.janela.title("FiscalPro v0.6.1")

        self.janela.geometry("1100x720")

        self.janela.configure(bg=COR_FUNDO)

        self.janela.resizable(False, False)

        self.criar_interface()

    def criar_interface(self):

        self.criar_cabecalho()

        self.dashboard = Dashboard(self.janela)

        self.painel_info = PainelInfo(self.janela)

    def criar_cabecalho(self):

        frame = Frame(
            self.janela,
            bg=COR_PRIMARIA,
            height=80
        )

        frame.pack(fill=X)

        titulo = criar_titulo(
            frame,
            "FiscalPro"
        )

        titulo.pack(anchor="w", padx=20)

        subtitulo = criar_subtitulo(
            frame,
            "Assistente Fiscal Inteligente"
        )

        subtitulo.pack(anchor="w", padx=22)

    def executar(self):

        self.janela.mainloop()

    def criar_informacoes(self):

        self.frame_info = ttk.LabelFrame(
            self.janela,
            text="Informações"
        )
    
        self.frame_info.pack(fill=X, padx=15, pady=10)

        self.lbl_empresa = ttk.Label(
            self.frame_info,
            text="Empresa: -"
        )

        self.lbl_empresa.grid(row=0, column=0, sticky="w", padx=10, pady=5)

        self.lbl_periodo = ttk.Label(
            self.frame_info,
            text="Período: -"  
        )

        self.lbl_periodo.grid(row=1, column=0, sticky="w", padx=10, pady=5)

        self.lbl_sped = ttk.Label(
            self.frame_info,
            text="SPED: -"
        )

        self.lbl_sped.grid(row=2, column=0, sticky="w", padx=10, pady=5)

        self.lbl_xml = ttk.Label(
            self.frame_info,
            text="XML: -"
        )

        self.lbl_xml.grid(row=3, column=0, sticky="w", padx=10, pady=5)
from tkinter import *
from tkinter import ttk

from .estilos import *
from .componentes import *
from .dashboard import Dashboard
from .painel_info import PainelInfo

class JanelaPrincipal:

    def __init__(self):
        self.janela = Tk()
        self.janela.title("FiscalPro v0.6.1")
        self.janela.geometry("1100x720")
        self.janela.configure(bg=COR_FUNDO)
        self.janela.resizable(False, False)
        self.criar_interface()

    def criar_interface(self):
        self.criar_cabecalho()
        self.dashboard = Dashboard(self.janela)
        self.painel_info = PainelInfo(self.janela)
        self.criar_informacoes()
        self.criar_botoes()  # Adiciona os botões

    def criar_cabecalho(self):
        frame = Frame(self.janela, bg=COR_PRIMARIA, height=80)
        frame.pack(fill=X)
        titulo = criar_titulo(frame, "FiscalPro")
        titulo.pack(anchor="w", padx=20)
        subtitulo = criar_subtitulo(frame, "Assistente Fiscal Inteligente")
        subtitulo.pack(anchor="w", padx=22)

    def criar_informacoes(self):
        self.frame_info = ttk.LabelFrame(self.janela, text="Informações")
        self.frame_info.pack(fill=X, padx=15, pady=10)

        self.lbl_empresa = ttk.Label(self.frame_info, text="Empresa: -")
        self.lbl_empresa.grid(row=0, column=0, sticky="w", padx=10, pady=5)

        self.lbl_periodo = ttk.Label(self.frame_info, text="Período: -")
        self.lbl_periodo.grid(row=1, column=0, sticky="w", padx=10, pady=5)

        self.lbl_sped = ttk.Label(self.frame_info, text="SPED: -")
        self.lbl_sped.grid(row=2, column=0, sticky="w", padx=10, pady=5)

        self.lbl_xml = ttk.Label(self.frame_info, text="XML: -")
        self.lbl_xml.grid(row=3, column=0, sticky="w", padx=10, pady=5)

    def criar_botoes(self):
        frame_botoes = Frame(self.janela, bg=COR_FUNDO)
        frame_botoes.pack(pady=10)

        btn_corrigir_sped = Button(frame_botoes, text="Corrigir SPED", command=self.corrigir_sped)
        btn_corrigir_sped.pack(side=LEFT, padx=5)

        btn_corrigir_xml = Button(frame_botoes, text="Corrigir XML", command=self.corrigir_xml)
        btn_corrigir_xml.pack(side=LEFT, padx=5)

    def corrigir_sped(self):
        print("Corrigindo arquivo SPED...")
        # Lógica de correção para SPED

    def corrigir_xml(self):
        print("Corrigindo arquivo XML...")
        # Lógica de correção para XML

    def executar(self):
        self.janela.mainloop()