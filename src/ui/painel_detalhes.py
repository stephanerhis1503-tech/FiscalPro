"""Painel ampliado para divergências, revisões e fundamentos do FiscalPro.

Hotfix 17.8.85 — melhora apenas a leitura das auditorias. Nenhuma regra fiscal
ou dado persistente é alterado por este módulo.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Iterable, Sequence, Tuple

from .layout_responsivo import dimensionar_janela


AbaDetalhe = Tuple[str, str]


def _normalizar_texto(conteudo: object) -> str:
    if conteudo is None:
        return "-"
    if isinstance(conteudo, str):
        return conteudo.strip() or "-"
    if isinstance(conteudo, Iterable):
        valores = [str(v).strip() for v in conteudo if str(v).strip()]
        return "\n".join(valores) if valores else "-"
    return str(conteudo)


def abrir_detalhes_ampliados(
    parent: tk.Misc,
    *,
    titulo: str,
    cabecalho: str,
    abas: Sequence[AbaDetalhe],
    rodape: str = "Dica: use F11 para alternar a maximização da janela.",
) -> tk.Toplevel:
    """Abre uma janela grande com cada grupo de informação em uma aba própria."""

    janela = tk.Toplevel(parent)
    janela.title(titulo)
    dimensionar_janela(janela, 1220, 820, 900, 600)
    janela.grid_rowconfigure(1, weight=1)
    janela.grid_columnconfigure(0, weight=1)

    topo = ttk.Frame(janela, padding=(16, 12, 16, 8))
    topo.grid(row=0, column=0, sticky="ew")
    ttk.Label(
        topo,
        text=cabecalho,
        justify="left",
        anchor="w",
        font=("Segoe UI", 11, "bold"),
        wraplength=1120,
    ).pack(fill="x")

    notebook = ttk.Notebook(janela)
    notebook.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))

    textos: list[tk.Text] = []
    for nome, conteudo in abas:
        quadro = ttk.Frame(notebook, padding=8)
        quadro.grid_rowconfigure(0, weight=1)
        quadro.grid_columnconfigure(0, weight=1)
        notebook.add(quadro, text=nome)

        texto = tk.Text(
            quadro,
            wrap="word",
            padx=16,
            pady=14,
            font=("Segoe UI", 10),
            spacing1=2,
            spacing3=5,
            undo=False,
        )
        barra = ttk.Scrollbar(quadro, orient="vertical", command=texto.yview)
        texto.configure(yscrollcommand=barra.set)
        texto.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        texto.insert("1.0", _normalizar_texto(conteudo))
        texto.configure(state="disabled")
        textos.append(texto)

    botoes = ttk.Frame(janela, padding=(14, 0, 14, 10))
    botoes.grid(row=2, column=0, sticky="ew")
    ttk.Label(botoes, text=rodape).pack(side="left")

    def copiar_aba() -> None:
        indice = notebook.index(notebook.select())
        if not (0 <= indice < len(textos)):
            return
        texto = textos[indice]
        conteudo = texto.get("1.0", "end-1c")
        janela.clipboard_clear()
        janela.clipboard_append(conteudo)

    ttk.Button(botoes, text="Copiar aba", command=copiar_aba).pack(side="right", padx=(6, 0))
    ttk.Button(botoes, text="Fechar", command=janela.destroy).pack(side="right")

    janela.transient(parent)
    janela.lift()
    return janela
