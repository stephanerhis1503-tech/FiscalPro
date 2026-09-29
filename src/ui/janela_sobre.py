"""Janela Sobre do FiscalPro."""

from __future__ import annotations

from tkinter import BOTH, X, Frame, Label, Toplevel
from tkinter import ttk

from src.core.app_info import (
    AVISO_LEGAL,
    CREDITOS,
    DESCRICAO_APP,
    NOME_COMPLETO,
    PUBLICADOR,
    VERSAO_APP,
)

from .estilos import (
    COR_BORDA,
    COR_CARD,
    COR_DESTAQUE,
    COR_FUNDO,
    COR_PRIMARIA,
    COR_TEXTO,
    COR_TEXTO_SUAVE,
)
from .recursos import aplicar_icone, carregar_imagem


def _centralizar(janela, largura: int, altura: int) -> None:
    janela.update_idletasks()
    x = max(0, (janela.winfo_screenwidth() - largura) // 2)
    y = max(0, (janela.winfo_screenheight() - altura) // 2)
    janela.geometry(f"{largura}x{altura}+{x}+{y}")


class JanelaSobre:
    def __init__(self, master):
        self.janela = Toplevel(master)
        self.janela.title("FiscalPro | Sobre")
        self.janela.resizable(False, False)
        self.janela.transient(master)
        self.janela.grab_set()
        self.janela.configure(bg=COR_FUNDO)
        aplicar_icone(self.janela)
        _centralizar(self.janela, 640, 640)
        self._montar()

    def _montar(self) -> None:
        card = Frame(
            self.janela,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
        )
        card.pack(fill=BOTH, expand=True, padx=26, pady=26)

        faixa = Frame(card, bg=COR_PRIMARIA, height=8)
        faixa.pack(fill=X)
        faixa.pack_propagate(False)

        conteudo = Frame(card, bg=COR_CARD, padx=34, pady=27)
        conteudo.pack(fill=BOTH, expand=True)

        self.logo = carregar_imagem(self.janela, "fiscalpro_logo_about.png")
        if self.logo is not None:
            Label(conteudo, image=self.logo, bg=COR_CARD, bd=0).pack(pady=(0, 12))
        else:
            Label(
                conteudo,
                text="FiscalPro",
                bg=COR_CARD,
                fg=COR_PRIMARIA,
                font=("Segoe UI", 27, "bold"),
            ).pack()

        Label(
            conteudo,
            text=f"Versão {VERSAO_APP}",
            bg=COR_DESTAQUE,
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=5,
        ).pack(pady=(0, 16))

        Label(
            conteudo,
            text=DESCRICAO_APP,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 10),
            wraplength=520,
            justify="center",
        ).pack()

        divisoria = Frame(conteudo, bg=COR_BORDA, height=1)
        divisoria.pack(fill=X, pady=20)

        Label(
            conteudo,
            text="Criação e direção do projeto",
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
        ).pack()
        Label(
            conteudo,
            text=PUBLICADOR,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"),
        ).pack(pady=(2, 12))

        Label(
            conteudo,
            text="Desenvolvido em parceria com ChatGPT",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 10, "bold"),
        ).pack()
        Label(
            conteudo,
            text=f"Créditos: {CREDITOS}",
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
        ).pack(pady=(3, 14))

        Label(
            conteudo,
            text=AVISO_LEGAL,
            bg="#F3F6FA",
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8),
            wraplength=510,
            justify="left",
            padx=14,
            pady=11,
        ).pack(fill=X, pady=(0, 17))

        ttk.Button(
            conteudo,
            text="Fechar",
            command=self.janela.destroy,
            style="Primary.TButton",
        ).pack(fill=X)
