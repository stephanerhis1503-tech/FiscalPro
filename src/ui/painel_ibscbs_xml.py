"""Painel de leitura das tags e valores de IBS/CBS em XMLs fiscais."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Frame, Label, StringVar
from tkinter import filedialog, messagebox, ttk

from src.services.xml_ibscbs_service import ResultadoLeituraIBSCBS, ServicoXMLIBSCBS

from .estilos import COR_BORDA, COR_CARD, COR_DESTAQUE, COR_TEXTO, COR_TEXTO_SUAVE, FONTE_NORMAL


class PainelIBSCBSXML(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.servico = ServicoXMLIBSCBS()
        self.arquivos: list[Path] = []
        self.resultado = ResultadoLeituraIBSCBS()
        self.var_status = StringVar(value="Selecione XMLs, ZIPs ou uma pasta para localizar IBS/CBS.")
        self._montar()

    def _card(self, master):
        return Frame(master, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)

    def _montar(self):
        cab = self._card(self)
        cab.pack(fill=X, padx=10, pady=(7, 6))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        miolo = Frame(cab, bg=COR_CARD, padx=12, pady=8)
        miolo.pack(fill=X)
        Label(miolo, text="IBS/CBS • Leitor e Auditor de XML", bg=COR_CARD, fg=COR_TEXTO,
              font=("Segoe UI", 13, "bold")).pack(anchor="w")
        Label(
            miolo,
            text=("Localiza os blocos IBSCBS e IBSCBSTot, mostra todas as tags e valores e audita CST, cClassTrib, "
                  "alíquotas e cálculos quando a regra é determinística. Casos especiais ficam marcados para revisão. "
                  "Nenhum XML é alterado."),
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=FONTE_NORMAL, justify=LEFT,
        ).pack(anchor="w", pady=(2, 0))

        acoes = self._card(self)
        acoes.pack(fill=X, padx=10, pady=(0, 6))
        linha = Frame(acoes, bg=COR_CARD, padx=10, pady=8)
        linha.pack(fill=X)
        ttk.Button(linha, text="Selecionar XML / ZIP", command=self._selecionar_arquivos,
                   style="Primary.TButton").pack(side=LEFT, fill=X, expand=True)
        ttk.Button(linha, text="Pasta de XMLs", command=self._selecionar_pasta,
                   style="Secondary.TButton").pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
        ttk.Button(linha, text="ANALISAR IBS/CBS", command=self._analisar,
                   style="Accent.TButton").pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
        ttk.Button(linha, text="Exportar Excel", command=self._exportar,
                   style="Secondary.TButton").pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
        ttk.Button(linha, text="Limpar", command=self._limpar,
                   style="Secondary.TButton").pack(side=LEFT, fill=X, expand=True, padx=(5, 0))

        status = Frame(acoes, bg=COR_CARD, padx=10, pady=0)
        status.pack(fill=X, pady=(0, 8))
        Label(status, textvariable=self.var_status, bg=COR_CARD, fg=COR_TEXTO_SUAVE,
              font=("Segoe UI", 8), justify=LEFT).pack(side=LEFT, fill=X, expand=True)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=(0, 8))
        self.aba_resumo = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_itens = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_tags = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_auditoria = ttk.Frame(self.notebook, style="Page.TFrame")
        self.notebook.add(self.aba_resumo, text="  Resumo por XML  ")
        self.notebook.add(self.aba_itens, text="  Itens IBS/CBS  ")
        self.notebook.add(self.aba_auditoria, text="  Auditoria IBS/CBS  ")
        self.notebook.add(self.aba_tags, text="  Todas as tags e valores  ")

        self.tabela_resumo = self._criar_tabela(
            self.aba_resumo,
            (
                ("status", "Status", 90), ("arquivo", "Arquivo", 190), ("nf", "NF", 70),
                ("emitente", "Emitente", 220), ("itens", "Itens IBS/CBS", 95), ("tags", "Tags", 65),
                ("base", "Base IBS/CBS", 105), ("ibs", "IBS total", 95), ("cbs", "CBS total", 95),
                ("conferencia", "Conferência", 290),
            ),
        )
        self.tabela_itens = self._criar_tabela(
            self.aba_itens,
            (
                ("nf", "NF", 65), ("item", "Item", 50), ("codigo", "Código", 95), ("produto", "Produto", 230),
                ("ncm", "NCM", 85), ("cfop", "CFOP", 70), ("cst", "CST", 60), ("class", "cClassTrib", 90),
                ("vbc", "vBC", 85), ("pibsuf", "% IBS UF", 75), ("vibsuf", "IBS UF", 85),
                ("pibsmun", "% IBS Mun", 80), ("vibsmun", "IBS Mun", 85), ("vibs", "IBS", 85),
                ("pcbs", "% CBS", 75), ("vcbs", "CBS", 85), ("tags", "Tags", 55),
            ),
        )
        self.tabela_auditoria = self._criar_tabela(
            self.aba_auditoria,
            (
                ("status", "Status", 90), ("nf", "NF", 65), ("item", "Item", 50), ("produto", "Produto", 220),
                ("ncm", "NCM", 85), ("cfop", "CFOP", 70), ("crt", "CRT", 50),
                ("cst_xml", "CST XML", 70), ("cst_esp", "CST esperado", 85),
                ("class_xml", "cClassTrib XML", 100), ("class_esp", "cClassTrib esperado", 115),
                ("vbc", "vBC", 85),
                ("pibsuf_xml", "% IBS UF XML", 90), ("pibsuf_esp", "% IBS UF esperado", 105),
                ("pibsmun_xml", "% IBS Mun XML", 95), ("pibsmun_esp", "% IBS Mun esperado", 110),
                ("pcbs_xml", "% CBS XML", 80), ("pcbs_esp", "% CBS esperado", 95),
                ("vibs_xml", "IBS XML", 85), ("vibs_calc", "IBS calculado", 95),
                ("vcbs_xml", "CBS XML", 85), ("vcbs_calc", "CBS calculado", 95),
                ("perfil", "Perfil", 120), ("motivo", "Diagnóstico FiscalPro", 360),
            ),
        )
        self.tabela_tags = self._criar_tabela(
            self.aba_tags,
            (
                ("nf", "NF", 65), ("escopo", "Escopo", 70), ("item", "Item", 50), ("produto", "Produto", 210),
                ("bloco", "Bloco", 90), ("caminho", "Caminho da tag", 360), ("tag", "Tag", 120),
                ("valor", "Valor", 150), ("arquivo", "Arquivo", 180),
            ),
        )

    @staticmethod
    def _criar_tabela(master, definicoes):
        corpo = ttk.Frame(master, style="Page.TFrame")
        corpo.pack(fill=BOTH, expand=True)
        colunas = tuple(c[0] for c in definicoes)
        tabela = ttk.Treeview(corpo, columns=colunas, show="headings", selectmode="browse")
        for chave, titulo, largura in definicoes:
            tabela.heading(chave, text=titulo)
            tabela.column(chave, width=largura, minwidth=45, anchor="w" if chave in {"arquivo", "emitente", "produto", "conferencia", "caminho", "valor", "motivo", "perfil"} else "center")
        sy = ttk.Scrollbar(corpo, orient="vertical", command=tabela.yview)
        sx = ttk.Scrollbar(corpo, orient="horizontal", command=tabela.xview)
        tabela.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        tabela.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        corpo.rowconfigure(0, weight=1)
        corpo.columnconfigure(0, weight=1)
        return tabela

    def _selecionar_arquivos(self):
        caminhos = filedialog.askopenfilenames(
            parent=self,
            title="Selecione XMLs ou ZIPs",
            filetypes=(("XML ou ZIP", "*.xml *.zip"), ("XML", "*.xml"), ("ZIP", "*.zip"), ("Todos", "*.*")),
        )
        if caminhos:
            self.arquivos = [Path(c) for c in caminhos]
            self.var_status.set(f"{len(self.arquivos)} arquivo(s) selecionado(s). Clique em ANALISAR IBS/CBS.")

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory(parent=self, title="Selecione a pasta com XMLs/ZIPs")
        if not pasta:
            return
        self.arquivos = self.servico.listar_arquivos_pasta(pasta)
        self.var_status.set(f"{len(self.arquivos)} arquivo(s) XML/ZIP localizado(s) na pasta.")

    def _analisar(self):
        if not self.arquivos:
            messagebox.showwarning("IBS/CBS • XML", "Selecione XMLs, ZIPs ou uma pasta primeiro.", parent=self)
            return
        try:
            self.resultado = self.servico.analisar(self.arquivos)
        except Exception as exc:
            messagebox.showerror("IBS/CBS • XML", str(exc), parent=self)
            return
        self._preencher()
        r = self.resultado
        self.var_status.set(
            f"{r.arquivos} XML(s) • {r.arquivos_com_ibscbs} com IBS/CBS • {len(r.itens)} item(ns) com bloco • "
            f"Auditoria: {r.auditoria_ok} OK / {r.auditoria_revisar} revisar / {r.auditoria_especial} regra especial • "
            f"{len(r.tags)} tag(s) • {len(r.erros)} erro(s) de leitura."
        )

    def _preencher(self):
        for tabela in (self.tabela_resumo, self.tabela_itens, self.tabela_auditoria, self.tabela_tags):
            for item in tabela.get_children():
                tabela.delete(item)

        for r in self.resultado.resumos:
            self.tabela_resumo.insert("", END, values=(
                r.status, r.arquivo, r.numero_nf, r.emitente, r.itens_com_ibscbs, r.qtd_tags,
                r.total_base, r.total_ibs, r.total_cbs, r.detalhe,
            ))
        for i in self.resultado.itens:
            self.tabela_itens.insert("", END, values=(
                i.numero_nf, i.item, i.codigo_produto, i.descricao, i.ncm, i.cfop, i.cst, i.cclass_trib,
                i.vbc, i.p_ibs_uf, i.v_ibs_uf, i.p_ibs_mun, i.v_ibs_mun, i.v_ibs, i.p_cbs, i.v_cbs, i.qtd_tags,
            ))
        for a in self.resultado.auditorias:
            self.tabela_auditoria.insert("", END, values=(
                a.status, a.numero_nf, a.item, a.descricao, a.ncm, a.cfop, a.crt,
                a.cst_encontrado, a.cst_esperado, a.cclass_encontrado, a.cclass_esperado, a.vbc,
                a.p_ibs_uf_encontrado, a.p_ibs_uf_esperado, a.p_ibs_mun_encontrado, a.p_ibs_mun_esperado,
                a.p_cbs_encontrado, a.p_cbs_esperado, a.v_ibs_encontrado, a.v_ibs_calculado,
                a.v_cbs_encontrado, a.v_cbs_calculado, a.perfil, a.motivos,
            ))
        for t in self.resultado.tags:
            self.tabela_tags.insert("", END, values=(
                t.numero_nf, t.escopo, t.item, t.descricao, t.bloco, t.caminho, t.tag, t.valor, t.arquivo,
            ))

    def _exportar(self):
        if not self.resultado.resumos:
            messagebox.showwarning("IBS/CBS • XML", "Analise os XMLs antes de exportar.", parent=self)
            return
        nome = f"FiscalPro_IBS_CBS_XML_{datetime.now():%Y%m%d_%H%M}.xlsx"
        destino = filedialog.asksaveasfilename(
            parent=self, title="Exportar análise IBS/CBS", initialfile=nome,
            defaultextension=".xlsx", filetypes=(("Planilha Excel", "*.xlsx"),),
        )
        if not destino:
            return
        try:
            self.servico.exportar_excel(self.resultado, destino)
            messagebox.showinfo("IBS/CBS • XML", "Relatório exportado com sucesso.", parent=self)
        except Exception as exc:
            messagebox.showerror("IBS/CBS • XML", f"Não foi possível exportar: {exc}", parent=self)

    def _limpar(self):
        self.arquivos = []
        self.resultado = ResultadoLeituraIBSCBS()
        self._preencher()
        self.var_status.set("Selecione XMLs, ZIPs ou uma pasta para localizar IBS/CBS.")
