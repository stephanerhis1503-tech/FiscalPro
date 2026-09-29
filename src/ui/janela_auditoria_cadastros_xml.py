"""Tela da Auditoria de Cadastros por XML de Saída — Sprint 17.7.0."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List

from src.services.empresas_regimes_service import EmpresasRegimesService
from src.services.auditoria_cadastros_xml_service import (
    AuditoriaCadastrosXMLService,
    CadastroAuditado,
    ExportadorAuditoriaCadastrosXMLXLSX,
    ResultadoAuditoriaCadastrosXML,
    STATUS_CORRIGIR,
    STATUS_OK,
    STATUS_REVISAR,
)
from src.ui.layout_responsivo import dimensionar_janela
from src.ui.painel_detalhes import abrir_detalhes_ampliados


class JanelaAuditoriaCadastrosXML(tk.Toplevel):
    """Aponta cadastros com indícios de tributação incorreta a partir das NF-e de saída."""

    def __init__(self, master=None):
        super().__init__(master)
        self.title("FiscalPro — Auditoria de Cadastros por XML de Saída")
        dimensionar_janela(self, 1320, 860, 980, 640)
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        self.fontes: List[str] = []
        self.resultado: ResultadoAuditoriaCadastrosXML | None = None
        self.produtos_visiveis: List[CadastroAuditado] = []
        self._processando = False
        self._fila: queue.Queue = queue.Queue()

        self.var_empresa = tk.StringVar(value="Todas as empresas")
        self.var_empresa_info = tk.StringVar(value="Selecione a empresa para definir o regime automaticamente.")
        self.var_regime = tk.StringVar(value="Lucro Real")
        self.var_finalidade = tk.StringVar(value="Revenda")
        self.var_origem = tk.StringVar(value="MG")
        self.var_filtro = tk.StringVar(value="Todos")
        self.var_busca = tk.StringVar(value="")
        self.var_fontes = tk.StringVar(value="Nenhuma fonte selecionada.")
        self.var_status = tk.StringVar(value="Selecione a pasta que contém os XMLs de saída.")
        self.var_resumo = tk.StringVar(value="Produtos: 0  •  Corrigir: 0  •  Revisar: 0  •  OK: 0")

        self._montar()

    def _montar(self) -> None:
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        cab = ttk.Frame(self, padding=(14, 12, 14, 6))
        cab.grid(row=0, column=0, sticky="ew")
        ttk.Label(cab, text="Auditoria de Cadastros por XML de Saída", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            cab,
            text=(
                "Agrupa as NF-e por código de produto, compara a tributação usada nas saídas com os motores "
                "do FiscalPro e destaca quais cadastros devem ser corrigidos ou revisados. O módulo não altera o ERP nem os XMLs."
            ),
            wraplength=1220,
        ).pack(anchor="w", pady=(3, 0))

        contexto = ttk.LabelFrame(self, text="1. Contexto", padding=10)
        contexto.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 7))
        for col in (1, 3, 5):
            contexto.grid_columnconfigure(col, weight=1)
        ttk.Label(contexto, text="Regime").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            contexto, textvariable=self.var_regime, state="readonly",
            values=("Lucro Real", "Lucro Presumido", "Simples Nacional", "MEI"),
        ).grid(row=0, column=1, sticky="ew", padx=(6, 16))
        ttk.Label(contexto, text="Finalidade").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            contexto, textvariable=self.var_finalidade, state="readonly",
            values=("Revenda", "Uso e consumo", "Ativo imobilizado", "Industrialização"),
        ).grid(row=0, column=3, sticky="ew", padx=(6, 16))
        ttk.Label(contexto, text="UF da empresa").grid(row=0, column=4, sticky="w")
        ttk.Combobox(
            contexto, textvariable=self.var_origem, state="readonly",
            values=("AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"),
        ).grid(row=0, column=5, sticky="ew", padx=(6, 0))
        ttk.Label(contexto, text="Empresa").grid(row=1, column=0, sticky="w", pady=(8, 0))
        combo_empresa = ttk.Combobox(
            contexto, textvariable=self.var_empresa, state="readonly",
            values=EmpresasRegimesService.listar_empresas(incluir_todas=True),
        )
        combo_empresa.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(6, 16), pady=(8, 0))
        combo_empresa.bind("<<ComboboxSelected>>", self._empresa_alterada)
        ttk.Label(
            contexto, textvariable=self.var_empresa_info, foreground="#1F4E78",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=1, column=3, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(
            contexto,
            text="As UFs e a data de cada NF-e são lidas do próprio XML. Itens de entrada (CFOP 1/2/3) são ignorados.",
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(7, 0))

        fontes = ttk.LabelFrame(self, text="2. XMLs de saída", padding=10)
        fontes.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 7))
        fontes.grid_columnconfigure(5, weight=1)
        ttk.Button(fontes, text="📁 Selecionar pasta", command=self._adicionar_pasta).grid(row=0, column=0, sticky="ew")
        ttk.Button(fontes, text="＋ XML / ZIP", command=self._adicionar_arquivos).grid(row=0, column=1, sticky="ew", padx=(7, 0))
        ttk.Button(fontes, text="Limpar", command=self._limpar).grid(row=0, column=2, sticky="ew", padx=(7, 0))
        self.btn_analisar = ttk.Button(fontes, text="🔎 Auditar cadastros", command=self._analisar)
        self.btn_analisar.grid(row=0, column=3, sticky="ew", padx=(14, 0))
        self.btn_exportar = ttk.Button(fontes, text="💾 Exportar Excel", command=self._exportar, state="disabled")
        self.btn_exportar.grid(row=0, column=4, sticky="ew", padx=(7, 0))
        ttk.Label(fontes, textvariable=self.var_fontes, anchor="w").grid(row=0, column=5, sticky="ew", padx=(12, 0))

        filtros = ttk.Frame(self, padding=(14, 0, 14, 7))
        filtros.grid(row=3, column=0, sticky="ew")
        ttk.Label(filtros, textvariable=self.var_resumo, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(filtros, text="Busca:").pack(side=tk.RIGHT, padx=(10, 4))
        entrada = ttk.Entry(filtros, textvariable=self.var_busca, width=28)
        entrada.pack(side=tk.RIGHT)
        entrada.bind("<KeyRelease>", lambda _e: self._preencher())
        ttk.Label(filtros, text="Filtro:").pack(side=tk.RIGHT, padx=(10, 4))
        combo = ttk.Combobox(
            filtros, textvariable=self.var_filtro, state="readonly", width=15,
            values=("Todos", "Corrigir", "Revisar", "OK", "Inconsistentes"),
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
        colunas = ("status", "codigo", "descricao", "ncm", "ocorr", "docs", "trat", "cfop", "pis", "cofins", "seg")
        self.tabela = ttk.Treeview(quadro, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "status":"Status", "codigo":"Código", "descricao":"Descrição", "ncm":"NCM",
            "ocorr":"Ocorrências", "docs":"NF-e", "trat":"Tratamentos", "cfop":"CFOPs",
            "pis":"PIS observado", "cofins":"COFINS observado", "seg":"Segurança",
        }
        larguras = {"status":95,"codigo":120,"descricao":285,"ncm":90,"ocorr":82,"docs":62,"trat":85,"cfop":150,"pis":190,"cofins":190,"seg":82}
        for col in colunas:
            self.tabela.heading(col, text=titulos[col])
            self.tabela.column(col, width=larguras[col], minwidth=55, anchor="w")
        for col in ("status", "ncm", "ocorr", "docs", "trat", "seg"):
            self.tabela.column(col, anchor="center")
        y = ttk.Scrollbar(quadro, orient="vertical", command=self.tabela.yview)
        x = ttk.Scrollbar(quadro, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        self.tabela.bind("<Double-1>", self._detalhes)
        self.tabela.tag_configure(STATUS_CORRIGIR, background="#FDE9E7")
        self.tabela.tag_configure(STATUS_REVISAR, background="#FFF4D6")
        self.tabela.tag_configure(STATUS_OK, background="#E7F4E4")

        rodape = ttk.Frame(self, padding=(14, 0, 14, 10))
        rodape.grid(row=5, column=0, sticky="ew")
        ttk.Label(
            rodape,
            text="Dica: duplo clique em um produto para ver divergências, correção sugerida e exemplos de NF-e.",
        ).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self._fechar).pack(side=tk.RIGHT)

    def _adicionar_pasta(self) -> None:
        pasta = filedialog.askdirectory(title="Selecione a pasta dos XMLs de saída", parent=self)
        if pasta:
            self.fontes = [pasta]
            self._atualizar_fontes()

    def _adicionar_arquivos(self) -> None:
        arquivos = filedialog.askopenfilenames(
            title="Selecione XMLs ou ZIPs de saída",
            parent=self,
            filetypes=(("XML ou ZIP", "*.xml *.zip"), ("Todos os arquivos", "*.*")),
        )
        if arquivos:
            self.fontes.extend(a for a in arquivos if a not in self.fontes)
            self._atualizar_fontes()

    def _limpar(self) -> None:
        if self._processando:
            return
        self.fontes.clear()
        self.resultado = None
        self.produtos_visiveis = []
        self._atualizar_fontes()
        self.var_resumo.set("Produtos: 0  •  Corrigir: 0  •  Revisar: 0  •  OK: 0")
        self.var_status.set("Selecione a pasta que contém os XMLs de saída.")
        self.btn_exportar.configure(state="disabled")
        self._preencher()

    def _atualizar_fontes(self) -> None:
        if not self.fontes:
            self.var_fontes.set("Nenhuma fonte selecionada.")
            return
        nomes = [Path(p).name or str(p) for p in self.fontes]
        previa = ", ".join(nomes[:3]) + (f" +{len(nomes)-3}" if len(nomes) > 3 else "")
        self.var_fontes.set(f"{len(nomes)} fonte(s): {previa}")

    def _empresa_alterada(self, _evento=None) -> None:
        empresa = self.var_empresa.get().strip()
        perfil = EmpresasRegimesService.obter_perfil(empresa)
        if perfil is not None:
            self.var_regime.set(perfil.regime.title())
        self.var_empresa_info.set(EmpresasRegimesService.descricao_regime(empresa, self.var_regime.get()))

    def _contexto(self) -> dict:
        return {
            "empresa": "" if self.var_empresa.get().strip() == "Todas as empresas" else self.var_empresa.get().strip(),
            "regime": EmpresasRegimesService.resolver_regime(self.var_empresa.get(), self.var_regime.get()),
            "operacao": "Venda",
            "finalidade": self.var_finalidade.get(),
            "uf_origem": self.var_origem.get(),
            "uf_destino": self.var_origem.get(),
            "data_operacao": date.today().isoformat(),
            "usar_uf_data_documento": True,
            "consumidor_final": False,
        }

    def _analisar(self) -> None:
        if self._processando:
            return
        if not self.fontes:
            messagebox.showwarning("FiscalPro", "Selecione uma pasta, XML ou ZIP antes de analisar.", parent=self)
            return
        fontes = list(self.fontes)
        contexto = self._contexto()
        self._processando = True
        self.btn_analisar.configure(state="disabled")
        self.btn_exportar.configure(state="disabled")
        self.var_status.set("Analisando os XMLs e agrupando os produtos... Nenhum arquivo será alterado.")
        self.update_idletasks()

        def executar() -> None:
            try:
                self._fila.put(("ok", AuditoriaCadastrosXMLService.analisar(fontes, contexto)))
            except Exception as erro:
                self._fila.put(("erro", erro))

        threading.Thread(target=executar, daemon=True).start()
        self.after(100, self._verificar_fila)

    def _verificar_fila(self) -> None:
        try:
            tipo, valor = self._fila.get_nowait()
        except queue.Empty:
            if self._processando and self.winfo_exists():
                self.after(100, self._verificar_fila)
            return
        self._processando = False
        self.btn_analisar.configure(state="normal")
        if tipo == "erro":
            self.var_status.set("Não foi possível concluir a auditoria.")
            messagebox.showerror("FiscalPro", str(valor), parent=self)
            return
        self.resultado = valor
        resumo = valor.resumo()
        self.var_resumo.set(
            f"Produtos: {resumo['produtos']}  •  Corrigir: {resumo['corrigir']}  •  "
            f"Revisar: {resumo['revisar']}  •  OK: {resumo['ok']}  •  Inconsistentes: {resumo['inconsistentes']}"
        )
        texto = f"Auditoria concluída: {resumo['itens_saida']} item(ns) de saída em {resumo['produtos']} produto(s)."
        if resumo["itens_ignorados_entrada"]:
            texto += f" {resumo['itens_ignorados_entrada']} item(ns) de entrada foram ignorados."
        if valor.erros:
            texto += f" {len(valor.erros)} aviso(s) de leitura/revisão."
        self.var_status.set(texto)
        self.btn_exportar.configure(state="normal" if valor.produtos else "disabled")
        self._preencher()

    def _preencher(self) -> None:
        for iid in self.tabela.get_children():
            self.tabela.delete(iid)
        if self.resultado is None:
            self.produtos_visiveis = []
            return
        filtro = self.var_filtro.get()
        busca = self.var_busca.get().strip().upper()
        produtos = []
        for p in self.resultado.produtos:
            if filtro == "Corrigir" and p.status != STATUS_CORRIGIR:
                continue
            if filtro == "Revisar" and p.status != STATUS_REVISAR:
                continue
            if filtro == "OK" and p.status != STATUS_OK:
                continue
            if filtro == "Inconsistentes" and not p.inconsistencia_interna:
                continue
            if busca and busca not in f"{p.codigo} {p.descricao} {p.ncm}".upper():
                continue
            produtos.append(p)
        self.produtos_visiveis = produtos
        for idx, p in enumerate(produtos):
            self.tabela.insert(
                "", "end", iid=str(idx), tags=(p.status,),
                values=(
                    p.status, p.codigo or "-", p.descricao, p.ncm or "-", p.ocorrencias,
                    p.documentos, p.tratamentos_distintos, p.cfops_observados,
                    p.pis_observado, p.cofins_observado,
                    f"{p.confiabilidade:.0f}%" if p.confiabilidade else "-",
                ),
            )

    def _detalhes(self, _evento=None) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            return
        try:
            produto = self.produtos_visiveis[int(selecao[0])]
        except (IndexError, ValueError):
            return

        resumo = "\n".join((
            f"STATUS: {produto.status}  |  Segurança mínima: {produto.confiabilidade:.2f}%",
            f"Código: {produto.codigo or '-'}",
            f"Produto: {produto.descricao}",
            f"NCM: {produto.ncm or '-'}",
            f"Ocorrências: {produto.ocorrencias} em {produto.documentos} NF-e",
            f"Tratamentos tributários distintos: {produto.tratamentos_distintos}",
            f"Inconsistência em operações equivalentes: {'SIM' if produto.inconsistencia_interna else 'NÃO'}",
        ))
        tributacao = "\n".join((
            f"CFOPs: {produto.cfops_observados}",
            f"CST ICMS: {produto.cst_icms_observados}",
            f"PIS: {produto.pis_observado}",
            f"COFINS: {produto.cofins_observado}",
            f"CEST: {produto.cest_observado}",
        ))
        divergencias = "\n".join(
            f"• {valor}" for valor in (produto.divergencias or ["Nenhuma divergência confirmada."])
        )
        revisoes = "\n".join(
            f"• {valor}" for valor in (produto.pendencias or ["Nenhuma pendência registrada."])
        )
        documentos = "\n".join(
            f"• {valor}" for valor in (produto.exemplos_documentos or ["-"])
        )
        sugestao = "\n".join((
            "CORREÇÃO / TRATAMENTO SUGERIDO PELO FISCALPRO",
            produto.sugestao or "-",
            "",
            "IMPORTANTE",
            "O XML mostra como a NF-e foi emitida. O resultado indica cadastro/regra do ERP a revisar, mas não altera automaticamente o cadastro do sistema emissor.",
        ))

        abrir_detalhes_ampliados(
            self,
            titulo=f"Auditoria ampliada — {produto.codigo or produto.ncm or '-'}",
            cabecalho=f"{produto.codigo or '-'} — {produto.descricao} | {produto.status}",
            abas=(
                ("Resumo", resumo),
                (f"Divergências ({len(produto.divergencias)})", divergencias),
                (f"Revisões ({len(produto.pendencias)})", revisoes),
                ("Tributação observada", tributacao),
                ("Tratamento sugerido", sugestao),
                ("Exemplos de NF-e", documentos),
            ),
        )

    def _exportar(self) -> None:
        if self.resultado is None or not self.resultado.produtos:
            messagebox.showwarning("FiscalPro", "Execute a auditoria antes de exportar.", parent=self)
            return
        destino = filedialog.asksaveasfilename(
            title="Salvar auditoria de cadastros",
            parent=self,
            defaultextension=".xlsx",
            initialfile=f"Auditoria_Cadastros_XML_Saida_{date.today().strftime('%Y%m%d')}.xlsx",
            filetypes=(("Planilha Excel", "*.xlsx"),),
        )
        if not destino:
            return
        try:
            arquivo = ExportadorAuditoriaCadastrosXMLXLSX.exportar(self.resultado, destino)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível gerar a planilha:\n{erro}", parent=self)
            return
        messagebox.showinfo("FiscalPro", f"Relatório gerado com sucesso:\n{arquivo}", parent=self)

    def _fechar(self) -> None:
        if self._processando:
            if not messagebox.askyesno("FiscalPro", "A auditoria ainda está em andamento. Deseja fechar?", parent=self):
                return
        self.destroy()


__all__ = ["JanelaAuditoriaCadastrosXML"]
