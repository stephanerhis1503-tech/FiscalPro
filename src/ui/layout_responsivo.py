"""Utilitários de layout responsivo compartilhados pelo FiscalPro.

Sprint 15.6 — adapta janelas e áreas de resultado ao tamanho útil do monitor,
sem alterar regras fiscais ou fluxos de negócio.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


def dimensionar_janela(
    janela: tk.Misc,
    largura_ideal: int,
    altura_ideal: int,
    largura_minima: int = 900,
    altura_minima: int = 600,
    margem_horizontal: int = 48,
    margem_vertical: int = 96,
    maximizar_em_tela_baixa: bool = True,
) -> tuple[int, int]:
    """Dimensiona e centraliza uma janela sem ultrapassar a área do monitor.

    Em monitores com pouca altura (comuns em notebooks), a janela é maximizada
    no Windows para que as áreas de resultado não sejam comprimidas.
    """

    janela.update_idletasks()
    largura_tela = max(800, int(janela.winfo_screenwidth()))
    altura_tela = max(600, int(janela.winfo_screenheight()))

    largura = min(largura_ideal, max(760, largura_tela - margem_horizontal))
    altura = min(altura_ideal, max(520, altura_tela - margem_vertical))
    x = max(0, (largura_tela - largura) // 2)
    y = max(0, (altura_tela - altura) // 2 - 10)

    janela.geometry(f"{largura}x{altura}+{x}+{y}")
    janela.minsize(
        min(largura_minima, max(760, largura_tela - 80)),
        min(altura_minima, max(520, altura_tela - 120)),
    )

    if maximizar_em_tela_baixa and altura_tela <= 820:
        def _maximizar() -> None:
            try:
                janela.state("zoomed")
            except tk.TclError:
                try:
                    janela.attributes("-zoomed", True)
                except tk.TclError:
                    pass
        janela.after_idle(_maximizar)

    habilitar_atalhos_janela(janela)
    return largura, altura


def habilitar_atalhos_janela(janela: tk.Misc) -> None:
    """F11 alterna maximização e Escape fecha apenas janelas secundárias."""

    estado = {"maximizada": False, "geometria": ""}

    def alternar(_evento=None):
        try:
            atual = str(janela.state())
            if atual == "zoomed":
                janela.state("normal")
                estado["maximizada"] = False
            else:
                estado["geometria"] = str(janela.geometry())
                janela.state("zoomed")
                estado["maximizada"] = True
        except tk.TclError:
            try:
                ativo = bool(janela.attributes("-zoomed"))
                janela.attributes("-zoomed", not ativo)
            except tk.TclError:
                return None
        return "break"

    janela.bind("<F11>", alternar, add="+")


def configurar_grid_expansivel(widget: tk.Misc, linha: int = 0, coluna: int = 0) -> None:
    widget.grid_rowconfigure(linha, weight=1)
    widget.grid_columnconfigure(coluna, weight=1)


class FrameRolavel(ttk.Frame):
    """Frame vertical rolável que acompanha a largura disponível."""

    def __init__(self, master, *, background: str = "#F3F6FA", padding: int = 0):
        super().__init__(master)
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0, bd=0)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.interno = ttk.Frame(self.canvas, padding=padding)
        self._janela = self.canvas.create_window((0, 0), window=self.interno, anchor="nw")

        self.canvas.configure(yscrollcommand=self.barra.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.barra.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.interno.bind("<Configure>", self._atualizar_regiao)
        self.canvas.bind("<Configure>", self._ajustar_largura)
        self.canvas.bind("<Enter>", self._ativar_roda)
        self.canvas.bind("<Leave>", self._desativar_roda)

    def _atualizar_regiao(self, _evento=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _ajustar_largura(self, evento):
        self.canvas.itemconfigure(self._janela, width=evento.width)

    def _rolar(self, evento):
        if getattr(evento, "delta", 0):
            passos = -1 if evento.delta > 0 else 1
        else:
            passos = -1 if getattr(evento, "num", 0) == 4 else 1
        self.canvas.yview_scroll(passos, "units")
        return "break"

    def _ativar_roda(self, _evento=None):
        self.canvas.bind_all("<MouseWheel>", self._rolar)
        self.canvas.bind_all("<Button-4>", self._rolar)
        self.canvas.bind_all("<Button-5>", self._rolar)

    def _desativar_roda(self, _evento=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")


def criar_treeview_rolavel(
    master,
    *,
    colunas: tuple[str, ...],
    altura: int = 12,
    selecionar: str = "browse",
) -> tuple[ttk.Treeview, ttk.Scrollbar, ttk.Scrollbar]:
    """Cria uma tabela com rolagem completa e expansão automática."""

    tree = ttk.Treeview(
        master,
        columns=colunas,
        show="headings",
        height=altura,
        selectmode=selecionar,
    )
    barra_y = ttk.Scrollbar(master, orient="vertical", command=tree.yview)
    barra_x = ttk.Scrollbar(master, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
    tree.grid(row=0, column=0, sticky="nsew")
    barra_y.grid(row=0, column=1, sticky="ns")
    barra_x.grid(row=1, column=0, sticky="ew")
    configurar_grid_expansivel(master)
    return tree, barra_y, barra_x


def vincular_wraplength(label: tk.Label | ttk.Label, margem: int = 30, minimo: int = 260) -> None:
    """Faz o texto acompanhar a largura real do contêiner."""

    def ajustar(evento):
        largura = max(minimo, int(evento.width) - margem)
        try:
            label.configure(wraplength=largura)
        except tk.TclError:
            pass

    pai = label.master
    pai.bind("<Configure>", ajustar, add="+")


def adicionar_botao_expandir(
    master,
    alvo: tk.Widget,
    *,
    texto: str = "⛶ Expandir resultado",
    ao_alternar: Callable[[bool], None] | None = None,
) -> ttk.Button:
    """Cria um botão que destaca temporariamente uma área de resultado."""

    estado = {"expandido": False, "manager": "", "info": {}}

    def alternar():
        expandido = not estado["expandido"]
        estado["expandido"] = expandido
        janela = alvo.winfo_toplevel()
        if ao_alternar:
            ao_alternar(expandido)
        try:
            janela.state("zoomed" if expandido else "normal")
        except tk.TclError:
            pass
        botao.configure(text="↙ Restaurar painel" if expandido else texto)

    botao = ttk.Button(master, text=texto, command=alternar, style="Secondary.TButton")
    return botao
