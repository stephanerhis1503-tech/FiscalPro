"""Componentes visuais reutilizáveis do FiscalPro."""

from tkinter import Button, Label, LabelFrame

from .estilos import (
    COR_CARD,
    COR_PRIMARIA,
    COR_SECUNDARIA,
    COR_TEXTO,
    FONTE_DESTAQUE,
    FONTE_SUBTITULO,
    FONTE_TITULO,
)


def criar_titulo(master, texto):
    return Label(
        master,
        text=texto,
        bg=COR_PRIMARIA,
        fg="white",
        font=FONTE_TITULO,
    )


def criar_subtitulo(master, texto):
    return Label(
        master,
        text=texto,
        bg=COR_PRIMARIA,
        fg="#DCEAF5",
        font=FONTE_SUBTITULO,
    )


def criar_card(master, titulo):
    return LabelFrame(
        master,
        text=titulo,
        bg=COR_CARD,
        fg=COR_TEXTO,
        font=FONTE_DESTAQUE,
        padx=15,
        pady=10,
        bd=0,
        highlightthickness=1,
        highlightbackground="#DCE5EF",
    )


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
        pady=9,
        bd=0,
    )
