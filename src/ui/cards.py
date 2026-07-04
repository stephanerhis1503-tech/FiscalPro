"""
=========================================
FiscalPro
Card Dashboard
=========================================
"""

from tkinter import *
from tkinter import ttk


class Card(ttk.Frame):

    def __init__(self, master, titulo, valor="0"):

        super().__init__(master, padding=8)

        self.configure(relief="ridge")

        self.lbl_titulo = ttk.Label(
            self,
            text=titulo,
            font=("Segoe UI", 10)
        )

        self.lbl_titulo.pack()

        self.lbl_valor = ttk.Label(
            self,
            text=valor,
            font=("Segoe UI", 20, "bold")
        )

        self.lbl_valor.pack()

    def atualizar(self, valor):

        self.lbl_valor.config(text=str(valor))