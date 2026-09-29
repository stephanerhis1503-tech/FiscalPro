"""Mapa de Cobertura Tributária Nacional — FiscalPro 17.8.38."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.ui.estilos import COR_BORDA, COR_CARD, COR_FUNDO, COR_PRIMARIA, COR_TEXTO, COR_TEXTO_SUAVE
from src.ui.layout_responsivo import dimensionar_janela


class JanelaCoberturaTributaria(tk.Toplevel):
    CORES = {3: "#2E7D32", 2: "#E59A13", 1: "#6B7280"}

    def __init__(self, master=None):
        super().__init__(master)
        self.title("FiscalPro — Mapa de Cobertura Tributária Nacional")
        dimensionar_janela(self, 1240, 820, 920, 620)
        self.configure(bg=COR_FUNDO)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._montar()

    @staticmethod
    def _numero(valor: int) -> str:
        return f"{int(valor):,}".replace(",", ".")

    def _card(self, master, coluna: int, titulo: str, valor: str, detalhe: str = ""):
        card = tk.Frame(master, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA, padx=12, pady=10)
        card.grid(row=0, column=coluna, sticky="nsew", padx=5)
        tk.Frame(card, bg="#2E7D32", height=4).pack(fill="x", pady=(0, 7))
        tk.Label(card, text=titulo, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(card, text=valor, bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(2, 0))
        if detalhe:
            tk.Label(card, text=detalhe, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8), wraplength=260, justify="left").pack(anchor="w", pady=(2, 0))

    def _montar(self):
        diag = CoberturaTributariaService.diagnostico()
        resumo = diag["resumo"]

        cab = tk.Frame(self, bg=COR_PRIMARIA, padx=20, pady=14)
        cab.grid(row=0, column=0, sticky="ew")
        tk.Label(cab, text="Mapa de Cobertura Tributária Nacional", bg=COR_PRIMARIA, fg="white", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(cab, text="Veja o que o FiscalPro realmente conhece por UF — sem confundir ausência de base com ausência de tributo.", bg=COR_PRIMARIA, fg="#E7EEF6", font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))

        cards = tk.Frame(self, bg=COR_FUNDO)
        cards.grid(row=1, column=0, sticky="ew", padx=12, pady=10)
        for i in range(4):
            cards.columnconfigure(i, weight=1, uniform="cards")
        self._card(cards, 0, "NCM OFICIAL", self._numero(resumo["ncm_oficial"]), "Base nacional instalada")
        self._card(cards, 1, "TIPI OFICIAL", self._numero(resumo["tipi_oficial"]), "Alíquota de referência por NCM/EX")
        self._card(cards, 2, "ICMS-ST / MG", self._numero(resumo["st_mg_registros"]), f"{resumo['st_mg_ncm']} NCMs distintos • {len(resumo['st_mg_segmentos'])} segmentos")
        self._card(cards, 3, "PIS / COFINS", "NACIONAL", "Motor federal + regras monofásicas instaladas")

        faixa = tk.Frame(self, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA, padx=12, pady=8)
        faixa.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        tk.Label(faixa, text="● COBERTURA AMPLIADA", bg=COR_CARD, fg="#2E7D32", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 18))
        tk.Label(faixa, text="● ESTADUAL PARCIAL", bg=COR_CARD, fg="#E59A13", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 18))
        tk.Label(faixa, text="● REGRA GERAL", bg=COR_CARD, fg="#6B7280", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 18))
        if diag["prioridades"]:
            tk.Label(faixa, text="Prioridade por uso recente: " + ", ".join(diag["prioridades"]), bg=COR_CARD, fg=COR_PRIMARIA, font=("Segoe UI", 8, "bold")).pack(side="right")

        corpo = ttk.Frame(self)
        corpo.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 8))
        corpo.grid_rowconfigure(0, weight=1)
        corpo.grid_columnconfigure(0, weight=1)
        colunas = ("uf", "nivel", "icms", "st", "fcp", "prioridade")
        self.grade = ttk.Treeview(corpo, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "uf": "UF", "nivel": "Cobertura", "icms": "ICMS próprio", "st": "ICMS-ST",
            "fcp": "FCP / fundo", "prioridade": "Prioridade",
        }
        larguras = {"uf": 55, "nivel": 190, "icms": 260, "st": 245, "fcp": 230, "prioridade": 100}
        for c in colunas:
            self.grade.heading(c, text=titulos[c])
            self.grade.column(c, width=larguras[c], minwidth=50, anchor="w")
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.grade.yview)
        self.grade.configure(yscrollcommand=barra.set)
        self.grade.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.grade.tag_configure("nivel3", foreground="#1B5E20")
        self.grade.tag_configure("nivel2", foreground="#9A6700")
        self.grade.tag_configure("nivel1", foreground="#59636E")
        for item in diag["ufs"]:
            self.grade.insert("", "end", iid=item["uf"], values=(item["uf"], item["status"], item["icms"], item["st"], item["fcp"], item["prioridade"]), tags=(f"nivel{item['nivel']}",))
        self.grade.bind("<<TreeviewSelect>>", self._selecionou)

        rodape = tk.Frame(self, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA, padx=12, pady=9)
        rodape.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 12))
        self.var_detalhe = tk.StringVar(value=diag["aviso"])
        tk.Label(rodape, textvariable=self.var_detalhe, bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 8), justify="left", anchor="w", wraplength=1020).pack(side="left", fill="x", expand=True)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side="right", padx=(10, 0))

    def _selecionou(self, _evento=None):
        selecionados = self.grade.selection()
        if not selecionados:
            return
        uf = selecionados[0]
        item = next((x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == uf), None)
        if item:
            self.var_detalhe.set(f"{uf} — {item['observacao']}")
