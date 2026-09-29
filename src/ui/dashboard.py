from tkinter import X
from tkinter import ttk

from .cards import Card
from .estilos import COR_ALERTA, COR_DESTAQUE, COR_ERRO, COR_PRIMARIA


class Dashboard(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.pack(fill=X, padx=14, pady=(0, 7))

        for coluna in range(4):
            self.columnconfigure(coluna, weight=1, uniform="cards")

        self.card_registros = Card(self, "LINHAS DO SPED", destaque=COR_PRIMARIA)
        self.card_registros.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.card_erros = Card(self, "ERROS ENCONTRADOS", destaque=COR_ERRO)
        self.card_erros.grid(row=0, column=1, sticky="ew", padx=4)

        self.card_avisos = Card(self, "AVISOS", destaque=COR_ALERTA)
        self.card_avisos.grid(row=0, column=2, sticky="ew", padx=4)

        self.card_xml = Card(self, "XML VINCULADOS", destaque=COR_DESTAQUE)
        self.card_xml.grid(row=0, column=3, sticky="ew", padx=(4, 0))

    def atualizar(self, registros, erros, avisos, xml):
        self.card_registros.atualizar(registros)
        self.card_erros.atualizar(erros)
        self.card_avisos.atualizar(avisos)
        self.card_xml.atualizar(xml)
