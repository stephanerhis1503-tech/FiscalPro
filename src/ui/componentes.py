"""
=========================================
FiscalPro
Componentes da Interface
=========================================
"""

from tkinter import *

from .estilos import *


def criar_titulo(master, texto):

    return Label(
        master,
        text=texto,
        bg=COR_PRIMARIA,
        fg="white",
        font=FONTE_TITULO
    )


def criar_subtitulo(master, texto):

    return Label(
        master,
        text=texto,
        bg=COR_PRIMARIA,
        fg="white",
        font=FONTE_SUBTITULO
    )


def criar_card(master, titulo):

    frame = LabelFrame(
        master,
        text=titulo,
        bg=COR_CARD,
        padx=15,
        pady=10
    )

    return frame


def criar_botao(master, texto, comando=None):

    return Button(
        master,
        text=texto,
        command=comando,
        bg=COR_PRIMARIA,
        fg="white",
        activebackground=COR_SECUNDARIA,
        activeforeground="white",
        relief="flat",
        cursor="hand2",
        font=("Segoe UI", 10, "bold"),
        padx=15,
        pady=8
    )