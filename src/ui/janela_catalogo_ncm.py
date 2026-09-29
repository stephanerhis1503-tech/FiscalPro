"""Catálogo nacional pesquisável de NCM e TIPI — Sprint 16.4."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.base_ncm_nacional_service import BaseNCMNacionalService
from src.ui.layout_responsivo import dimensionar_janela


class JanelaCatalogoNCM(tk.Toplevel):
    def __init__(
        self,
        master=None,
        ao_selecionar: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(master)
        self.title("Catálogo Nacional de NCM e TIPI")
        dimensionar_janela(self, 1080, 680, 820, 520)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.ao_selecionar = ao_selecionar
        self._agendamento = None
        self._resultados = {}

        topo = ttk.LabelFrame(self, text="Pesquisar código ou produto", padding=12)
        topo.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        topo.grid_columnconfigure(0, weight=1)

        self.termo = ttk.Entry(topo)
        self.termo.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.termo.bind("<KeyRelease>", self._agendar_pesquisa)
        self.termo.bind("<Return>", lambda _e: self.pesquisar())
        ttk.Button(topo, text="Pesquisar", command=self.pesquisar).grid(
            row=0, column=1, sticky="ew"
        )
        ttk.Label(
            topo,
            text=(
                "Exemplos: 85111000, vela ignição, pneu motocicleta, "
                "freio veículo"
            ),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        base = BaseNCMNacionalService.garantir_instalada()
        self.status = ttk.Label(
            self,
            text=(
                f"Base offline: {base.total_ncm:,} NCMs • "
                f"{base.total_tipi:,} registros TIPI • referência {base.data_publicacao}"
            ).replace(",", "."),
            anchor="w",
        )
        self.status.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        quadro = ttk.Frame(self)
        quadro.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 8))
        quadro.grid_rowconfigure(0, weight=1)
        quadro.grid_columnconfigure(0, weight=1)

        colunas = ("ncm", "descricao", "ipi", "ex", "status")
        self.tabela = ttk.Treeview(
            quadro, columns=colunas, show="headings", selectmode="browse"
        )
        self.tabela.heading("ncm", text="NCM")
        self.tabela.heading("descricao", text="Descrição oficial completa")
        self.tabela.heading("ipi", text="IPI")
        self.tabela.heading("ex", text="EX TIPI")
        self.tabela.heading("status", text="Status")
        self.tabela.column("ncm", width=105, minwidth=95, anchor="center", stretch=False)
        self.tabela.column("descricao", width=690, minwidth=360, anchor="w")
        self.tabela.column("ipi", width=85, minwidth=75, anchor="center", stretch=False)
        self.tabela.column("ex", width=80, minwidth=70, anchor="center", stretch=False)
        self.tabela.column("status", width=85, minwidth=75, anchor="center", stretch=False)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        self.tabela.bind("<Double-1>", lambda _e: self.usar_selecionado())

        barra_y = ttk.Scrollbar(quadro, orient="vertical", command=self.tabela.yview)
        barra_x = ttk.Scrollbar(quadro, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")

        botoes = ttk.Frame(self)
        botoes.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        botoes.grid_columnconfigure(0, weight=1)
        ttk.Button(
            botoes, text="Usar NCM selecionado", command=self.usar_selecionado
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(botoes, text="Copiar NCM", command=self.copiar_selecionado).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(botoes, text="Fechar", command=self.destroy).grid(
            row=0, column=3, padx=(8, 0)
        )

        self.termo.focus_set()
        self.pesquisar()

    def _agendar_pesquisa(self, _evento=None):
        if self._agendamento is not None:
            self.after_cancel(self._agendamento)
        self._agendamento = self.after(280, self.pesquisar)

    def pesquisar(self):
        self._agendamento = None
        termo = self.termo.get().strip()
        resultados = BaseOficialRepository.buscar_ncm_catalogo(termo, limite=300)
        self._resultados = {item["ncm"]: item for item in resultados}

        for item_id in self.tabela.get_children():
            self.tabela.delete(item_id)

        for item in resultados:
            ncm = str(item.get("ncm") or "")
            self.tabela.insert(
                "",
                "end",
                iid=ncm,
                values=(
                    self._formatar_ncm(ncm),
                    item.get("descricao_completa") or item.get("descricao") or "",
                    self._texto_ipi(item),
                    int(item.get("quantidade_ex") or 0),
                    item.get("status") or "ATIVO",
                ),
            )

        complemento = "Digite um termo para filtrar." if not termo else f'Busca: "{termo}".'
        self.status.config(
            text=(
                f"{len(resultados)} resultado(s) exibido(s). {complemento} "
                "Limite de 300 por pesquisa."
            )
        )
        if resultados:
            primeiro = str(resultados[0]["ncm"])
            self.tabela.selection_set(primeiro)
            self.tabela.focus(primeiro)

    def _ncm_selecionado(self) -> str:
        selecao = self.tabela.selection()
        return str(selecao[0]) if selecao else ""

    def usar_selecionado(self):
        ncm = self._ncm_selecionado()
        if not ncm:
            messagebox.showwarning("FiscalPro", "Selecione um NCM.", parent=self)
            return
        if self.ao_selecionar:
            self.ao_selecionar(ncm)
        self.destroy()

    def copiar_selecionado(self):
        ncm = self._ncm_selecionado()
        if not ncm:
            messagebox.showwarning("FiscalPro", "Selecione um NCM.", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(ncm)
        self.update_idletasks()
        self.status.config(text=f"NCM {self._formatar_ncm(ncm)} copiado.")

    @staticmethod
    def _formatar_ncm(ncm: str) -> str:
        codigo = "".join(c for c in str(ncm or "") if c.isdigit())
        if len(codigo) == 8:
            return f"{codigo[:4]}.{codigo[4:6]}.{codigo[6:]}"
        return codigo

    @staticmethod
    def _texto_ipi(item) -> str:
        texto = str(item.get("aliquota_texto") or "").strip()
        if texto.upper() == "NT":
            return "NT"
        if item.get("aliquota") is not None:
            return f"{float(item['aliquota']):.2f}%".replace(".", ",")
        if texto:
            return texto if "%" in texto else f"{texto}%"
        return "-"
