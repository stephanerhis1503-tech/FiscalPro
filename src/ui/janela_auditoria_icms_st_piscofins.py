"""Tela da Etapa 1 — auditoria do ICMS-ST nas bases de PIS/COFINS das entradas."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from src.services.auditoria_icms_st_piscofins_service import (
    AuditoriaICMSSTPISCOFINSService,
    ResultadoAuditoriaICMSSTPISCOFINS,
    STATUS_OK,
    STATUS_POSSIVEL_ST,
    STATUS_REVISAR_BASE,
    STATUS_REVISAR_CST,
    STATUS_REVISAR_ICMS,
    STATUS_REVISAR_VINCULO,
    STATUS_SEM_CREDITO,
    STATUS_SEM_CREDITO_ZERO,
)
from .layout_responsivo import dimensionar_janela


class JanelaAuditoriaICMSSTPISCOFINS(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Exclusão ICMS-ST da Base PIS/COFINS — Etapa 1")
        dimensionar_janela(self, 1420, 880, 1040, 650)
        self.transient(parent)

        self.arquivo_sped = ""
        self.origem_xml = ""
        self.resultado: Optional[ResultadoAuditoriaICMSSTPISCOFINS] = None
        self._processando = False
        self._fila: queue.Queue = queue.Queue()

        self.var_sped = tk.StringVar(value="Nenhum SPED selecionado.")
        self.var_xml = tk.StringVar(value="Nenhum ZIP/pasta de XML selecionado.")
        self.var_status = tk.StringVar(value="Modo auditoria: nenhum arquivo será alterado.")
        self.var_resumo = tk.StringVar(value="Itens ST: 0  •  OK ST: 0  •  Pendências ST: 0  •  Sem crédito: 0")
        self.var_filtro = tk.StringVar(value="Pendências ST")
        self.var_busca = tk.StringVar(value="")
        self._itens_visiveis = []
        self._montar()

    def _montar(self) -> None:
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        cab = ttk.Frame(self, padding=(14, 12, 14, 6))
        cab.grid(row=0, column=0, sticky="ew")
        ttk.Label(cab, text="Etapa 1 — Entradas com ICMS-ST destacado", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            cab,
            text=(
                "Cruza o SPED Contribuições com os XMLs de entrada e verifica se o ICMS-ST já está fora da base de PIS/COFINS. "
                "Nesta etapa o FiscalPro apenas audita: não corrige nem sobrescreve o SPED."
            ),
            wraplength=1320,
        ).pack(anchor="w", pady=(3, 0))

        fontes = ttk.LabelFrame(self, text="1. Arquivos da auditoria", padding=10)
        fontes.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 7))
        fontes.grid_columnconfigure(2, weight=1)
        ttk.Button(fontes, text="Selecionar SPED", command=self._selecionar_sped).grid(row=0, column=0, sticky="ew")
        ttk.Label(fontes, textvariable=self.var_sped, anchor="w").grid(row=0, column=1, columnspan=2, sticky="ew", padx=(10, 0))
        ttk.Button(fontes, text="Selecionar ZIP/XML", command=self._selecionar_xml_arquivo).grid(row=1, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(fontes, text="Selecionar pasta XML", command=self._selecionar_xml_pasta).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(7, 0))
        ttk.Label(fontes, textvariable=self.var_xml, anchor="w").grid(row=1, column=2, sticky="ew", padx=(10, 0), pady=(7, 0))

        acoes = ttk.Frame(self, padding=(14, 0, 14, 7))
        acoes.grid(row=2, column=0, sticky="ew")
        self.btn_auditar = ttk.Button(acoes, text="Auditar ICMS-ST", command=self._auditar)
        self.btn_auditar.pack(side=tk.LEFT)
        ttk.Button(acoes, text="Limpar", command=self._limpar).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(acoes, text="Aplicar correções no SPED", state="disabled").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            acoes,
            text="Correção automática bloqueada até a auditoria ser validada.",
            foreground="#8A5A00",
        ).pack(side=tk.LEFT, padx=(12, 0))

        filtros = ttk.Frame(self, padding=(14, 0, 14, 7))
        filtros.grid(row=3, column=0, sticky="ew")
        ttk.Label(filtros, textvariable=self.var_resumo, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(filtros, text="Busca:").pack(side=tk.RIGHT, padx=(10, 4))
        busca = ttk.Entry(filtros, textvariable=self.var_busca, width=26)
        busca.pack(side=tk.RIGHT)
        busca.bind("<KeyRelease>", lambda _e: self._preencher())
        ttk.Label(filtros, text="Filtro:").pack(side=tk.RIGHT, padx=(10, 4))
        combo = ttk.Combobox(
            filtros,
            textvariable=self.var_filtro,
            state="readonly",
            width=24,
            values=("Pendências ST", "Todos", "OK — ST fora", "OK ST + revisar ICMS próprio", "Sem crédito", "Alíquota zero", "Revisar CST/Crédito", "Possível ST na base", "Vínculo/Base"),
        )
        combo.pack(side=tk.RIGHT)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._preencher())

        area = ttk.Frame(self)
        area.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 7))
        area.grid_rowconfigure(1, weight=1)
        area.grid_columnconfigure(0, weight=1)
        ttk.Label(area, textvariable=self.var_status, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 4))

        quadro = ttk.Frame(area)
        quadro.grid(row=1, column=0, sticky="nsew")
        quadro.grid_rowconfigure(0, weight=1)
        quadro.grid_columnconfigure(0, weight=1)
        colunas = (
            "status", "nf", "fornecedor", "item", "codigo", "vicms", "vicmsst",
            "base_xml", "base_sped", "diferenca", "cst_xml", "cst_sped", "confianca", "linha",
        )
        self.tabela = ttk.Treeview(quadro, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "status": "Status", "nf": "NF", "fornecedor": "Fornecedor", "item": "Item", "codigo": "Código SPED",
            "vicms": "vICMS", "vicmsst": "vICMS-ST", "base_xml": "Base PIS XML", "base_sped": "Base PIS SPED",
            "diferenca": "Diferença", "cst_xml": "CST XML", "cst_sped": "CST SPED", "confianca": "Vínculo", "linha": "Linha C170",
        }
        larguras = {
            "status": 245, "nf": 85, "fornecedor": 270, "item": 55, "codigo": 120,
            "vicms": 85, "vicmsst": 90, "base_xml": 105, "base_sped": 105, "diferenca": 95,
            "cst_xml": 75, "cst_sped": 78, "confianca": 75, "linha": 85,
        }
        for coluna in colunas:
            self.tabela.heading(coluna, text=titulos[coluna])
            self.tabela.column(coluna, width=larguras[coluna], minwidth=50, anchor="w", stretch=coluna in {"status", "fornecedor"})
        for coluna in ("nf", "item", "vicms", "vicmsst", "base_xml", "base_sped", "diferenca", "cst_xml", "cst_sped", "confianca", "linha"):
            self.tabela.column(coluna, anchor="center")
        y = ttk.Scrollbar(quadro, orient="vertical", command=self.tabela.yview)
        x = ttk.Scrollbar(quadro, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        self.tabela.bind("<Double-1>", self._detalhes)
        self.tabela.tag_configure(STATUS_OK, background="#E7F4E4")
        self.tabela.tag_configure(STATUS_SEM_CREDITO, background="#EDF3F8")
        self.tabela.tag_configure(STATUS_SEM_CREDITO_ZERO, background="#EDF3F8")
        self.tabela.tag_configure(STATUS_REVISAR_ICMS, background="#E7F4E4")
        self.tabela.tag_configure(STATUS_REVISAR_CST, background="#FFF4D6")
        self.tabela.tag_configure(STATUS_POSSIVEL_ST, background="#FDE9E7")
        self.tabela.tag_configure(STATUS_REVISAR_VINCULO, background="#FDE9E7")
        self.tabela.tag_configure(STATUS_REVISAR_BASE, background="#FDE9E7")

        rodape = ttk.Frame(self, padding=(14, 0, 14, 10))
        rodape.grid(row=5, column=0, sticky="ew")
        ttk.Label(rodape, text="Duplo clique mostra os detalhes de PIS e COFINS do item.").pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

    def _selecionar_sped(self) -> None:
        arquivo = filedialog.askopenfilename(parent=self, title="Selecione o SPED Contribuições", filetypes=(("SPED TXT", "*.txt"), ("Todos", "*.*")))
        if arquivo:
            self.arquivo_sped = arquivo
            self.var_sped.set(Path(arquivo).name)

    def _selecionar_xml_arquivo(self) -> None:
        arquivo = filedialog.askopenfilename(parent=self, title="Selecione o ZIP ou XML de entradas", filetypes=(("ZIP/XML", "*.zip *.xml"), ("Todos", "*.*")))
        if arquivo:
            self.origem_xml = arquivo
            self.var_xml.set(Path(arquivo).name)

    def _selecionar_xml_pasta(self) -> None:
        pasta = filedialog.askdirectory(parent=self, title="Selecione a pasta dos XMLs de entrada")
        if pasta:
            self.origem_xml = pasta
            self.var_xml.set(pasta)

    def _auditar(self) -> None:
        if self._processando:
            return
        if not self.arquivo_sped:
            messagebox.showwarning("FiscalPro", "Selecione o SPED Contribuições primeiro.", parent=self)
            return
        if not self.origem_xml:
            messagebox.showwarning("FiscalPro", "Selecione o ZIP/XML ou a pasta dos XMLs de entrada.", parent=self)
            return
        self._processando = True
        self.btn_auditar.configure(state="disabled")
        self.var_status.set("Iniciando auditoria... Nenhum arquivo será alterado.")
        sped, xml = self.arquivo_sped, self.origem_xml

        def progresso(texto: str) -> None:
            self._fila.put(("progresso", texto))

        def executar() -> None:
            try:
                resultado = AuditoriaICMSSTPISCOFINSService.auditar(sped, xml, progresso=progresso)
                self._fila.put(("ok", resultado))
            except Exception as erro:
                self._fila.put(("erro", erro))

        threading.Thread(target=executar, daemon=True).start()
        self.after(100, self._verificar_fila)

    def _verificar_fila(self) -> None:
        final = False
        while True:
            try:
                tipo, valor = self._fila.get_nowait()
            except queue.Empty:
                break
            if tipo == "progresso":
                self.var_status.set(str(valor))
            elif tipo == "erro":
                final = True
                self._processando = False
                self.btn_auditar.configure(state="normal")
                self.var_status.set("Falha na auditoria.")
                messagebox.showerror("FiscalPro", str(valor), parent=self)
            elif tipo == "ok":
                final = True
                self._processando = False
                self.btn_auditar.configure(state="normal")
                self.resultado = valor
                resumo = valor.resumo()
                pendencias_st = resumo["revisar_cst"] + resumo["possivel_st"] + resumo["revisar_vinculo"] + resumo["revisar_base"]
                self.var_resumo.set(
                    f"Itens ST: {resumo['itens_st']}  •  OK ST: {resumo['ok_icms_st']} "
                    f"({resumo['ok_revisar_icms']} revisar ICMS próprio fora do escopo ST)  •  "
                    f"Pendências ST: {pendencias_st}  •  "
                    f"Sem crédito: {resumo['sem_credito']} ({resumo['sem_credito_aliquota_zero']} alíquota zero)  •  "
                    f"ST: {self._moeda(resumo['icms_st_total'])}"
                )
                self.var_status.set(
                    f"Concluído: {resumo['notas_st']} nota(s), {resumo['itens_st']} item(ns) com ST. "
                    f"Vínculos: {resumo['vinculos_altos']} altos, {resumo['vinculos_medios']} médios, {resumo['vinculos_baixos']} baixos. Nenhum arquivo foi alterado."
                )
                self._preencher()
        if self._processando and not final and self.winfo_exists():
            self.after(100, self._verificar_fila)

    def _preencher(self) -> None:
        for iid in self.tabela.get_children():
            self.tabela.delete(iid)
        if self.resultado is None:
            self._itens_visiveis = []
            return
        filtro = self.var_filtro.get()
        busca = self.var_busca.get().strip().upper()
        itens = []
        for item in self.resultado.itens:
            if filtro == "Pendências ST" and item.status in {STATUS_OK, STATUS_REVISAR_ICMS, STATUS_SEM_CREDITO, STATUS_SEM_CREDITO_ZERO}:
                continue
            if filtro == "OK — ST fora" and item.status != STATUS_OK:
                continue
            if filtro == "OK ST + revisar ICMS próprio" and item.status != STATUS_REVISAR_ICMS:
                continue
            if filtro == "Sem crédito" and item.status not in {STATUS_SEM_CREDITO, STATUS_SEM_CREDITO_ZERO}:
                continue
            if filtro == "Alíquota zero" and item.status != STATUS_SEM_CREDITO_ZERO:
                continue
            if filtro == "Revisar CST/Crédito" and item.status != STATUS_REVISAR_CST:
                continue
            if filtro == "Possível ST na base" and item.status != STATUS_POSSIVEL_ST:
                continue
            if filtro == "Vínculo/Base" and item.status not in {STATUS_REVISAR_VINCULO, STATUS_REVISAR_BASE}:
                continue
            if busca and busca not in " ".join((item.nf, item.fornecedor, item.codigo_xml, item.codigo_sped, item.descricao_xml, item.descricao_sped, item.chave_nfe)).upper():
                continue
            itens.append(item)
        self._itens_visiveis = itens
        for indice, item in enumerate(itens):
            self.tabela.insert(
                "", "end", iid=str(indice), tags=(item.status,),
                values=(
                    item.status, item.nf, item.fornecedor, item.item, item.codigo_sped or item.codigo_xml,
                    self._numero(item.valor_icms), self._numero(item.valor_icms_st), self._numero(item.base_pis_xml),
                    self._numero(item.base_pis_sped), self._numero(item.diferenca_base_pis), item.cst_pis_xml,
                    item.cst_pis_sped, item.confianca_vinculo, item.linha_c170 or "-",
                ),
            )

    def _detalhes(self, _evento=None) -> None:
        selecionado = self.tabela.selection()
        if not selecionado:
            return
        item = self._itens_visiveis[int(selecionado[0])]
        texto = (
            f"Status: {item.status}\nAção: {item.acao}\nVínculo: {item.confianca_vinculo}\n\n"
            f"NF-e: {item.nf}  Série: {item.serie}  Item: {item.item}\nChave: {item.chave_nfe}\n"
            f"Fornecedor: {item.fornecedor}  CNPJ: {item.cnpj}\n\n"
            f"Código XML: {item.codigo_xml}\nCódigo SPED: {item.codigo_sped}\n"
            f"Descrição XML: {item.descricao_xml}\nDescrição SPED: {item.descricao_sped}\nNCM: {item.ncm}\n"
            f"CFOP XML/SPED: {item.cfop_xml} / {item.cfop_sped}\n\n"
            f"vICMS: {self._moeda(item.valor_icms)}\nvICMS-ST: {self._moeda(item.valor_icms_st)}\n\n"
            f"PIS — CST XML/SPED: {item.cst_pis_xml} / {item.cst_pis_sped}\n"
            f"Base XML: {self._moeda(item.base_pis_xml)}  |  Base SPED: {self._moeda(item.base_pis_sped)}  |  Dif.: {self._moeda(item.diferenca_base_pis)}\n\n"
            f"COFINS — CST XML/SPED: {item.cst_cofins_xml} / {item.cst_cofins_sped}\n"
            f"Base XML: {self._moeda(item.base_cofins_xml)}  |  Base SPED: {self._moeda(item.base_cofins_sped)}  |  Dif.: {self._moeda(item.diferenca_base_cofins)}\n\n"
            f"Linha C170: {item.linha_c170 or '-'}"
        )
        messagebox.showinfo("Detalhes da auditoria ICMS-ST", texto, parent=self)

    def _limpar(self) -> None:
        self.resultado = None
        self._itens_visiveis = []
        self.var_resumo.set("Itens ST: 0  •  OK ST: 0  •  Pendências ST: 0  •  Sem crédito: 0")
        self.var_status.set("Modo auditoria: nenhum arquivo será alterado.")
        self._preencher()

    @staticmethod
    def _numero(valor: Decimal) -> str:
        return f"{valor:.2f}".replace(".", ",")

    @staticmethod
    def _moeda(valor: Decimal) -> str:
        bruto = f"{valor:,.2f}"
        return "R$ " + bruto.replace(",", "X").replace(".", ",").replace("X", ".")
