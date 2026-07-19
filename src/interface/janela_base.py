import tkinter as tk
from .estilos import *

class JanelaBase(tk.Frame):

    def __init__(self, master):

        super().__init__(master, bg=COR_FUNDO)

        self.pack(fill="both", expand=True)

        master.title("FiscalPro Enterprise")

        master.geometry("1100x700")

        master.configure(bg=COR_FUNDO)