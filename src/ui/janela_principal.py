"""
=========================================
FiscalPro
Janela Principal
Versão 0.7.0
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

        self.janela.title("FiscalPro v0.7.0")

        self.janela.geometry("1100x720")

        self.janela.configure(bg=COR_FUNDO)

        self.janela.resizable(False, False)

        self.criar_interface()

    def criar_interface(self):

        self.criar_cabecalho()

        self.dashboard = Dashboard(self.janela)

        self.painel_info = PainelInfo(self.janela)

        self.criar_botoes()

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

    def criar_botoes(self):

        frame = Frame(
            self.janela,
            bg=COR_FUNDO
        )

        frame.pack(fill=X, padx=15, pady=10)

        ttk.Button(
            frame,
            text="📂 Abrir SPED",
            command=self.abrir_sped
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            frame,
            text="📁 Selecionar XML",
            command=self.selecionar_xml
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            frame,
            text="🔧 Corrigir SPED",
            command=self.corrigir_sped
        ).pack(side=LEFT, padx=5)

    def abrir_sped(self):

        print("Abrir SPED")

    def selecionar_xml(self):

        print("Selecionar XML")

    def corrigir_sped(self):

        print("Corrigir SPED")

    def atualizar_info(self,
                       empresa,
                       periodo,
                       sped,
                       xml):

        self.painel_info.atualizar(
            empresa,
            periodo,
            sped,
            xml
        )

    def executar(self):

        self.janela.mainloop()