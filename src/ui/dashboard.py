from tkinter import *
from tkinter import ttk

from .cards import Card


class Dashboard(ttk.Frame):

    def __init__(self, master):
        super().__init__(master)

        self.pack(fill=X, padx=15, pady=10)

        self.card_registros = Card(self, "Registros")
        self.card_registros.grid(row=0, column=0, padx=8)

        self.card_erros = Card(self, "Erros")
        self.card_erros.grid(row=0, column=1, padx=8)

        self.card_avisos = Card(self, "Avisos")
        self.card_avisos.grid(row=0, column=2, padx=8)

        self.card_xml = Card(self, "XML")
        self.card_xml.grid(row=0, column=3, padx=8)

    def atualizar(self, registros, erros, avisos, xml):

        self.card_registros.atualizar(registros)
        self.card_erros.atualizar(erros)
        self.card_avisos.atualizar(avisos)
        self.card_xml.atualizar(xml)