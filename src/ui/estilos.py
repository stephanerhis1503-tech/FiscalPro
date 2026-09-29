"""Identidade visual compartilhada do FiscalPro.

Sprint 15.8 — Refinamento visual, tipografia compacta e relatórios ampliados.
Mantém as constantes antigas para compatibilidade com todas as janelas já
existentes e acrescenta estilos ttk reutilizáveis.
"""

from __future__ import annotations

from tkinter import Tk
from tkinter import ttk

from src.core.app_info import VERSAO_INTERFACE

# Paleta principal
COR_PRIMARIA = "#0F4C81"
COR_SECUNDARIA = "#0A365C"
COR_DESTAQUE = "#18A999"
COR_DESTAQUE_ESCURO = "#118579"

COR_FUNDO = "#F3F6FA"
COR_CARD = "#FFFFFF"
COR_BORDA = "#DCE5EF"
COR_BORDA_FORTE = "#C8D5E3"

COR_TEXTO = "#1E293B"
COR_TEXTO_SUAVE = "#64748B"
COR_TEXTO_CLARO = "#F8FAFC"

COR_SUCESSO = "#2E7D32"
COR_ALERTA = "#E59A13"
COR_ERRO = "#C83E4D"
COR_INFO = "#2563A8"

# Fontes
FONTE_TITULO = ("Segoe UI", 20, "bold")
FONTE_SUBTITULO = ("Segoe UI", 9)
FONTE_NORMAL = ("Segoe UI", 9)
FONTE_RESULTADO = ("Consolas", 9)
FONTE_SECAO = ("Segoe UI", 12, "bold")
FONTE_DESTAQUE = ("Segoe UI", 10, "bold")
FONTE_PEQUENA = ("Segoe UI", 8)



def configurar_tema(root: Tk) -> ttk.Style:
    """Aplica um tema claro e profissional sem dependências externas."""

    style = ttk.Style(root)
    temas = style.theme_names()
    if "clam" in temas:
        style.theme_use("clam")

    root.configure(bg=COR_FUNDO)
    root.option_add("*Font", "{Segoe UI} 9")
    root.option_add("*Text.background", COR_CARD)
    root.option_add("*Text.foreground", COR_TEXTO)
    root.option_add("*Text.insertBackground", COR_TEXTO)
    root.option_add("*Text.selectBackground", COR_PRIMARIA)
    root.option_add("*Text.selectForeground", "white")
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.borderWidth", 0)
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightBackground", COR_BORDA)
    root.option_add("*Text.highlightColor", COR_PRIMARIA)

    style.configure(".", font=FONTE_NORMAL)
    style.configure("TFrame", background=COR_FUNDO)
    style.configure("Page.TFrame", background=COR_FUNDO)
    style.configure("Card.TFrame", background=COR_CARD, relief="flat")
    style.configure("Header.TFrame", background=COR_PRIMARIA)
    style.configure("Footer.TFrame", background=COR_CARD)

    style.configure("TLabel", background=COR_FUNDO, foreground=COR_TEXTO)
    style.configure(
        "Header.TLabel",
        background=COR_PRIMARIA,
        foreground=COR_TEXTO_CLARO,
    )
    style.configure(
        "HeaderTitle.TLabel",
        background=COR_PRIMARIA,
        foreground="white",
        font=FONTE_TITULO,
    )
    style.configure(
        "HeaderSubtitle.TLabel",
        background=COR_PRIMARIA,
        foreground="#DCEAF5",
        font=FONTE_SUBTITULO,
    )
    style.configure(
        "CardTitle.TLabel",
        background=COR_CARD,
        foreground=COR_TEXTO,
        font=FONTE_SECAO,
    )
    style.configure(
        "CardSubtitle.TLabel",
        background=COR_CARD,
        foreground=COR_TEXTO_SUAVE,
        font=FONTE_NORMAL,
    )
    style.configure(
        "Muted.TLabel",
        background=COR_FUNDO,
        foreground=COR_TEXTO_SUAVE,
        font=FONTE_PEQUENA,
    )
    style.configure(
        "CardMuted.TLabel",
        background=COR_CARD,
        foreground=COR_TEXTO_SUAVE,
        font=FONTE_PEQUENA,
    )
    style.configure(
        "Status.TLabel",
        background=COR_SECUNDARIA,
        foreground="white",
        font=("Segoe UI", 9, "bold"),
        padding=(10, 4),
    )
    style.configure(
        "SuccessStatus.TLabel",
        background=COR_SUCESSO,
        foreground="white",
        font=("Segoe UI", 9, "bold"),
        padding=(10, 4),
    )

    style.configure(
        "TButton",
        background="#E7EEF6",
        foreground=COR_TEXTO,
        borderwidth=0,
        focusthickness=0,
        focuscolor="none",
        padding=(10, 5),
        font=("Segoe UI", 9, "bold"),
    )
    style.map(
        "TButton",
        background=[("disabled", "#EEF2F6"), ("active", "#D9E4EF")],
        foreground=[("disabled", "#9AA7B5")],
    )

    style.configure(
        "Primary.TButton",
        background=COR_PRIMARIA,
        foreground="white",
        padding=(12, 6),
    )
    style.map(
        "Primary.TButton",
        background=[("pressed", COR_SECUNDARIA), ("active", "#12609F"), ("disabled", "#A9BED0")],
        foreground=[("disabled", "#F3F6FA")],
    )

    style.configure(
        "Accent.TButton",
        background=COR_DESTAQUE,
        foreground="white",
        padding=(12, 6),
    )
    style.map(
        "Accent.TButton",
        background=[("pressed", COR_DESTAQUE_ESCURO), ("active", "#1EB6A5"), ("disabled", "#A8D7D1")],
    )

    style.configure(
        "Secondary.TButton",
        background=COR_CARD,
        foreground=COR_PRIMARIA,
        borderwidth=1,
        relief="solid",
        padding=(11, 6),
    )
    style.map(
        "Secondary.TButton",
        background=[("pressed", "#E7EEF6"), ("active", "#F1F6FA")],
        foreground=[("active", COR_SECUNDARIA)],
    )

    style.configure(
        "Danger.TButton",
        background=COR_ERRO,
        foreground="white",
    )
    style.map("Danger.TButton", background=[("active", "#B43240")])


    style.configure(
        "Link.TButton",
        background=COR_CARD,
        foreground=COR_PRIMARIA,
        borderwidth=0,
        padding=(6, 4),
        font=("Segoe UI", 9, "underline"),
    )
    style.map(
        "Link.TButton",
        background=[("active", COR_CARD), ("pressed", COR_CARD)],
        foreground=[("active", COR_SECUNDARIA)],
    )

    style.configure(
        "Account.TMenubutton",
        background=COR_CARD,
        foreground=COR_PRIMARIA,
        borderwidth=0,
        padding=(10, 6),
        font=("Segoe UI", 9, "bold"),
        arrowcolor=COR_PRIMARIA,
    )
    style.map(
        "Account.TMenubutton",
        background=[("active", "#E7EEF6"), ("pressed", "#D9E4EF")],
        foreground=[("active", COR_SECUNDARIA)],
    )

    style.configure(
        "TNotebook",
        background=COR_FUNDO,
        borderwidth=0,
        tabmargins=(0, 8, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background="#E7EEF6",
        foreground=COR_TEXTO_SUAVE,
        borderwidth=0,
        padding=(12, 6),
        font=("Segoe UI", 9, "bold"),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COR_CARD), ("active", "#DCE7F1")],
        foreground=[("selected", COR_PRIMARIA), ("active", COR_TEXTO)],
        expand=[("selected", (0, 0, 0, 2))],
    )

    style.configure(
        "TLabelframe",
        background=COR_CARD,
        bordercolor=COR_BORDA,
        lightcolor=COR_BORDA,
        darkcolor=COR_BORDA,
        relief="solid",
        borderwidth=1,
        padding=8,
    )
    style.configure(
        "TLabelframe.Label",
        background=COR_CARD,
        foreground=COR_TEXTO,
        font=("Segoe UI", 9, "bold"),
    )
    style.configure("Card.TLabelframe", background=COR_CARD, padding=10)
    style.configure(
        "Card.TLabelframe.Label",
        background=COR_CARD,
        foreground=COR_PRIMARIA,
        font=("Segoe UI", 10, "bold"),
    )

    style.configure(
        "TEntry",
        fieldbackground=COR_CARD,
        foreground=COR_TEXTO,
        bordercolor=COR_BORDA_FORTE,
        lightcolor=COR_BORDA_FORTE,
        darkcolor=COR_BORDA_FORTE,
        insertcolor=COR_TEXTO,
        padding=5,
    )
    style.map("TEntry", bordercolor=[("focus", COR_PRIMARIA)])
    style.configure(
        "TCombobox",
        fieldbackground=COR_CARD,
        background=COR_CARD,
        foreground=COR_TEXTO,
        arrowcolor=COR_PRIMARIA,
        bordercolor=COR_BORDA_FORTE,
        padding=5,
    )
    style.map("TCombobox", bordercolor=[("focus", COR_PRIMARIA)])
    style.configure("TSpinbox", fieldbackground=COR_CARD, padding=4)
    style.configure("TCheckbutton", background=COR_FUNDO, foreground=COR_TEXTO)
    style.configure("Card.TCheckbutton", background=COR_CARD, foreground=COR_TEXTO)
    style.configure("TRadiobutton", background=COR_FUNDO, foreground=COR_TEXTO)

    style.configure(
        "Treeview",
        background=COR_CARD,
        fieldbackground=COR_CARD,
        foreground=COR_TEXTO,
        rowheight=24,
        bordercolor=COR_BORDA,
        borderwidth=1,
    )
    style.map("Treeview", background=[("selected", "#DCEAF5")], foreground=[("selected", COR_TEXTO)])
    style.configure(
        "Treeview.Heading",
        background="#E7EEF6",
        foreground=COR_TEXTO,
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        padding=(7, 5),
    )
    style.map("Treeview.Heading", background=[("active", "#D8E4EF")])

    style.configure("Vertical.TScrollbar", background="#D6E0EA", troughcolor=COR_FUNDO)
    style.configure("Horizontal.TScrollbar", background="#D6E0EA", troughcolor=COR_FUNDO)

    return style
