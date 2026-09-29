"""Carregamento seguro dos recursos visuais do FiscalPro."""

from __future__ import annotations

import os
from pathlib import Path
from tkinter import PhotoImage, TclError

from src.core.caminhos import pasta_recursos


def pasta_base() -> Path:
    return pasta_recursos()


def caminho_recurso(*partes: str) -> Path:
    return pasta_base().joinpath(*partes)


def carregar_imagem(master, nome_arquivo: str) -> PhotoImage | None:
    caminho = caminho_recurso("assets", nome_arquivo)
    if not caminho.exists():
        return None
    try:
        return PhotoImage(master=master, file=str(caminho))
    except TclError:
        return None


def aplicar_icone(janela) -> None:
    """Aplica o ícone oficial, preservando referências exigidas pelo Tk."""

    png = caminho_recurso("assets", "fiscalpro_mark_64.png")
    ico = caminho_recurso("assets", "fiscalpro.ico")

    try:
        if png.exists():
            imagem = PhotoImage(master=janela, file=str(png))
            janela.iconphoto(True, imagem)
            janela._fiscalpro_icone_png = imagem
    except TclError:
        pass

    if os.name == "nt" and ico.exists():
        try:
            janela.iconbitmap(default=str(ico))
        except TclError:
            pass
