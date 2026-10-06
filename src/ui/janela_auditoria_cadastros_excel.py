"""Janela de auditoria tributária de cadastro importado por Excel."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from src.services.empresas_regimes_service import EmpresasRegimesService
from src.services.auditoria_cadastros_excel_service import (
    AuditoriaCadastrosExcelService,
    ExportadorAuditoriaCadastrosExcelXLSX,
    ExportadorFichaTributariaCompletaXLSX,
    ItemAuditoriaExcel,
    ResultadoAuditoriaExcel,
    STATUS_CORRIGIR,
    STATUS_OK,
    STATUS_REVISAR,
    STATUS_SERVICO,
)
from .layout_responsivo import dimensionar_janela
from .painel_detalhes import abrir_detalhes_ampliados

_UFS = ("AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO")


class JanelaAuditoriaCadastrosExcel(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Auditoria de Cadastro por Excel")
        dimensionar_janela(self, 1360, 860, 980, 620)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        self.arquivo: str = ""
        self.resultado: Optional[ResultadoAuditoriaExcel] = None
        self.itens_visiveis: List[ItemAuditoriaExcel] = []
        self._fila: queue.Queue = queue.Queue()
        self._processando = False

        self.var_arquivo = tk.StringVar(value="Nenhuma planilha selecionada.")
        self.var_empresa = tk.StringVar(value="Todas as empresas")
        self.var_empresa_info = tk.StringVar(value="Selecione a empresa para definir o regime automaticamente.")
        self.var_regime = tk.StringVar(value="Lucro Real")
        self.var_finalidade = tk.StringVar(value="Revenda")
        self.var_origem = tk.StringVar(value="MG")
        self.var_destino = tk.StringVar(value="MG")
        self.var_filtro = tk.StringVar(value="Com problemas")
        self.var_busca = tk.StringVar(value="")
        self.var_status = tk.StringVar(value="Selecione a planilha de cadastro de produtos.")
        self.var_resumo = tk.StringVar(value="Itens: 0  •  Corrigir: 0  •  Revisar: 0  •  Serviços: 0  •  OK: 0")
        self._montar()

    def _montar(self) -> None:
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        cab = ttk.Frame(self, padding=(14, 12, 14, 6))
        cab.grid(row=0, column=0, sticky="ew")
        ttk.Label(cab, text="Auditoria Tributária de Cadastro por Excel", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            cab,
            text=(
                "Importe a lista de produtos e confira NCM, CEST, PIS/Cofins e TIPI em lote. "
                "O FiscalPro não altera a planilha original nem o cadastro do ERP."
            ),
            wraplength=1230,
        ).pack(anchor="w", pady=(3, 0))

        contexto = ttk.LabelFrame(self, text="1. Contexto da auditoria", padding=10)
        contexto.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 7))
        for col in (1, 3, 5, 7):
            contexto.grid_columnconfigure(col, weight=1)
        ttk.Label(contexto, text="Regime").grid(row=0, column=0, sticky="w")
        ttk.Combobox(contexto, textvariable=self.var_regime, state="readonly", values=("Lucro Real", "Lucro Presumido", "Simples Nacional", "MEI")).grid(row=0, column=1, sticky="ew", padx=(6, 16))
        ttk.Label(contexto, text="Finalidade").grid(row=0, column=2, sticky="w")
        ttk.Combobox(contexto, textvariable=self.var_finalidade, state="readonly", values=("Revenda", "Uso e consumo", "Ativo imobilizado", "Industrialização")).grid(row=0, column=3, sticky="ew", padx=(6, 16))
        ttk.Label(contexto, text="UF origem").grid(row=0, column=4, sticky="w")
        ttk.Combobox(contexto, textvariable=self.var_origem, state="readonly", values=_UFS, width=8).grid(row=0, column=5, sticky="ew", padx=(6, 16))
        ttk.Label(contexto, text="UF destino").grid(row=0, column=6, sticky="w")
        ttk.Combobox(contexto, textvariable=self.var_destino, state="readonly", values=_UFS, width=8).grid(row=0, column=7, sticky="ew", padx=(6, 0))
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
        ).grid(row=1, column=3, columnspan=5, sticky="w", pady=(8, 0))

        fonte = ttk.LabelFrame(self, text="2. Planilha de produtos", padding=10)
        fonte.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 7))
        fonte.grid_columnconfigure(5, weight=1)
        ttk.Button(fonte, text="📊 Selecionar Excel", command=self._selecionar).grid(row=0, column=0, sticky="ew")
        self.btn_analisar = ttk.Button(fonte, text="🔎 Auditar cadastro", command=self._analisar)
        self.btn_analisar.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.btn_exportar = ttk.Button(
            fonte, text="💾 Exportar completa", command=lambda: self._exportar(False), state="disabled"
        )
        self.btn_exportar.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        self.btn_exportar_pendencias = ttk.Button(
            fonte, text="⚠️ Exportar pendências", command=lambda: self._exportar(True), state="disabled"
        )
        self.btn_exportar_pendencias.grid(row=0, column=3, sticky="ew", padx=(8, 0))
        ttk.Button(fonte, text="Limpar", command=self._limpar).grid(row=0, column=4, sticky="ew", padx=(8, 0))
        ttk.Label(fonte, textvariable=self.var_arquivo, anchor="w").grid(row=0, column=5, sticky="ew", padx=(12, 0))

        self.btn_ficha_tributaria = ttk.Button(
            fonte,
            text="📋 Gerar Ficha Tributária Completa",
            command=self._exportar_ficha_tributaria,
            state="disabled",
        )
        self.btn_ficha_tributaria.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(
            fonte,
            text=(
                "Novo: gera as 22 colunas do modelo tributário + status, referências, divergências, "
                "fundamentos e fontes do FiscalPro. A auditoria atual continua igual."
            ),
            foreground="#1F4E78",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=1, column=2, columnspan=4, sticky="w", padx=(10, 0), pady=(8, 0))
        ttk.Label(
            fonte,
            text=(
                "A exportação foi otimizada para cadastros grandes e roda em segundo plano. "
                "Use 'Exportar pendências' quando quiser somente CORRIGIR e REVISAR."
            ),
            foreground="#7F6000",
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(7, 0))

        filtros = ttk.Frame(self, padding=(14, 0, 14, 7))
        filtros.grid(row=3, column=0, sticky="ew")
        ttk.Label(filtros, textvariable=self.var_resumo, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(filtros, text="Busca:").pack(side=tk.RIGHT, padx=(10, 4))
        ent = ttk.Entry(filtros, textvariable=self.var_busca, width=28)
        ent.pack(side=tk.RIGHT)
        ent.bind("<KeyRelease>", lambda _e: self._preencher())
        ttk.Label(filtros, text="Filtro:").pack(side=tk.RIGHT, padx=(10, 4))
        combo = ttk.Combobox(filtros, textvariable=self.var_filtro, state="readonly", width=17, values=("Com problemas", "Corrigir", "Revisar", "Serviços", "OK", "Todos"))
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
        colunas = ("status", "codigo", "descricao", "ncm", "cest", "ncm_sug", "ncm_cand", "cest_sug", "problema", "seg")
        self.tabela = ttk.Treeview(quadro, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "status":"Status", "codigo":"Código", "descricao":"Descrição", "ncm":"NCM atual", "cest":"CEST atual",
            "ncm_sug":"NCM provável / sugerido", "ncm_cand":"NCM candidatos", "cest_sug":"CEST sugerido", "problema":"Problema encontrado", "seg":"Segurança",
        }
        larguras = {"status":90,"codigo":125,"descricao":300,"ncm":90,"cest":105,"ncm_sug":145,"ncm_cand":260,"cest_sug":110,"problema":420,"seg":80}
        for col in colunas:
            self.tabela.heading(col, text=titulos[col])
            self.tabela.column(col, width=larguras[col], minwidth=55, anchor="w", stretch=col in {"descricao", "problema"})
        for col in ("status", "ncm", "cest", "ncm_sug", "cest_sug", "seg"):
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
        self.tabela.tag_configure(STATUS_SERVICO, background="#E6F2FA")

        rodape = ttk.Frame(self, padding=(14, 0, 14, 10))
        rodape.grid(row=5, column=0, sticky="ew")
        ttk.Label(rodape, text="Duplo clique abre PIS/Cofins, IPI, divergências e correção sugerida.").pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self._fechar).pack(side=tk.RIGHT)

    def _selecionar(self) -> None:
        arquivo = filedialog.askopenfilename(parent=self, title="Selecione a planilha de cadastro", filetypes=(("Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")))
        if arquivo:
            self.arquivo = arquivo
            self.var_arquivo.set(Path(arquivo).name)
            self.var_status.set("Planilha selecionada. Clique em Auditar cadastro.")

    def _empresa_alterada(self, _evento=None) -> None:
        empresa = self.var_empresa.get().strip()
        perfil = EmpresasRegimesService.obter_perfil(empresa)
        if perfil is not None:
            self.var_regime.set(perfil.regime.title())
        self.var_empresa_info.set(EmpresasRegimesService.descricao_regime(empresa, self.var_regime.get()))

    def _contexto(self) -> dict:
        return {
            "empresa": "" if self.var_empresa.get().strip() == "Todas as empresas" else self.var_empresa.get().strip(),
            "regime": EmpresasRegimesService.resolver_regime(self.var_empresa.get(), self.var_regime.get()), "operacao": "Venda", "finalidade": self.var_finalidade.get(),
            "uf_origem": self.var_origem.get(), "uf_destino": self.var_destino.get(),
            "data_operacao": date.today().isoformat(), "consumidor_final": False,
        }

    def _analisar(self) -> None:
        if self._processando:
            return
        if not self.arquivo:
            messagebox.showwarning("FiscalPro", "Selecione uma planilha Excel primeiro.", parent=self)
            return
        self._processando = True
        self.btn_analisar.configure(state="disabled")
        self.btn_exportar.configure(state="disabled")
        self.btn_exportar_pendencias.configure(state="disabled")
        self.btn_ficha_tributaria.configure(state="disabled")
        self.var_status.set("Lendo e auditando os produtos... A planilha original não será alterada.")
        arquivo, contexto = self.arquivo, self._contexto()

        def progresso(atual: int, total: int, descricao: str) -> None:
            self._fila.put(("progresso", (atual, total, descricao)))

        def executar() -> None:
            try:
                valor = AuditoriaCadastrosExcelService.analisar(arquivo, contexto, progresso=progresso)
                self._fila.put(("ok", valor))
            except Exception as erro:
                self._fila.put(("erro", erro))

        threading.Thread(target=executar, daemon=True).start()
        self.after(120, self._verificar_fila)

    def _verificar_fila(self) -> None:
        recebeu_final = False
        while True:
            try:
                tipo, valor = self._fila.get_nowait()
            except queue.Empty:
                break
            if tipo == "progresso":
                atual, total, descricao = valor
                pct = (atual / total * 100) if total else 0
                self.var_status.set(f"Auditando: {atual}/{total} ({pct:.0f}%) • {descricao[:90]}")
            elif tipo == "erro":
                recebeu_final = True
                self._processando = False
                self.btn_analisar.configure(state="normal")
                self._atualizar_botoes_exportacao()
                self.var_status.set("Não foi possível concluir a auditoria.")
                messagebox.showerror("FiscalPro", str(valor), parent=self)
            elif tipo == "ok":
                recebeu_final = True
                self._processando = False
                self.btn_analisar.configure(state="normal")
                self.resultado = valor
                resumo = valor.resumo()
                self.var_resumo.set(f"Itens: {resumo['itens']}  •  Corrigir: {resumo['corrigir']}  •  Revisar: {resumo['revisar']}  •  Serviços: {resumo['servicos']}  •  OK: {resumo['ok']}")
                self.var_status.set(f"Auditoria concluída: {resumo['ncm_unicos']} NCM(s) em {resumo['itens']} item(ns), incluindo {resumo['servicos']} serviço(s). Nenhum dado foi alterado.")
                self._atualizar_botoes_exportacao()
                self._preencher()
            elif tipo == "export_progresso":
                atual, total, descricao = valor
                pct = (atual / total * 100) if total else 0
                self.var_status.set(f"Exportando: {atual}/{total} ({pct:.0f}%) • {descricao[:90]}")
            elif tipo == "export_erro":
                recebeu_final = True
                self._processando = False
                self.btn_analisar.configure(state="normal")
                self._atualizar_botoes_exportacao()
                self.var_status.set("Não foi possível concluir a exportação.")
                messagebox.showerror("FiscalPro", f"Não foi possível exportar:\n{valor}", parent=self)
            elif tipo == "export_ok":
                recebeu_final = True
                self._processando = False
                self.btn_analisar.configure(state="normal")
                self._atualizar_botoes_exportacao()
                arquivo, modo = valor
                self.var_status.set(f"Exportação concluída ({modo}).")
                messagebox.showinfo("FiscalPro", f"Auditoria exportada com sucesso:\n{arquivo}", parent=self)
        if self._processando and not recebeu_final and self.winfo_exists():
            self.after(120, self._verificar_fila)

    def _atualizar_botoes_exportacao(self) -> None:
        tem_resultado = bool(self.resultado and self.resultado.itens) and not self._processando
        self.btn_exportar.configure(state="normal" if tem_resultado else "disabled")
        self.btn_ficha_tributaria.configure(state="normal" if tem_resultado else "disabled")
        tem_pendencias = bool(
            tem_resultado and self.resultado and any(i.status in {STATUS_CORRIGIR, STATUS_REVISAR} for i in self.resultado.itens)
        )
        self.btn_exportar_pendencias.configure(state="normal" if tem_pendencias else "disabled")

    def _preencher(self) -> None:
        for iid in self.tabela.get_children():
            self.tabela.delete(iid)
        if self.resultado is None:
            self.itens_visiveis = []
            return
        filtro = self.var_filtro.get()
        busca = self.var_busca.get().strip().upper()
        candidatos: List[ItemAuditoriaExcel] = []
        for item in self.resultado.itens:
            if filtro == "Com problemas" and item.status not in {STATUS_CORRIGIR, STATUS_REVISAR}:
                continue
            if filtro == "Corrigir" and item.status != STATUS_CORRIGIR:
                continue
            if filtro == "Revisar" and item.status != STATUS_REVISAR:
                continue
            if filtro == "Serviços" and item.status != STATUS_SERVICO:
                continue
            if filtro == "OK" and item.status != STATUS_OK:
                continue
            if busca and busca not in f"{item.codigo} {item.descricao} {item.ncm_atual} {item.cest_atual} {item.ncm_sugerido} {item.ncm_candidatos}".upper():
                continue
            candidatos.append(item)
        limite = 5000
        self.itens_visiveis = candidatos[:limite]
        for idx, item in enumerate(self.itens_visiveis):
            self.tabela.insert("", "end", iid=str(idx), tags=(item.status,), values=(
                item.status, item.codigo or "-", item.descricao, item.ncm_atual or "-", item.cest_atual or "-",
                item.ncm_sugerido or "-", item.ncm_candidatos or "-", item.cest_sugerido or "-", item.problema,
                f"{item.seguranca:.0f}%" if item.seguranca else "-",
            ))
        if len(candidatos) > limite:
            self.var_status.set(f"Exibindo os primeiros {limite} de {len(candidatos)} itens do filtro. A exportação contém todos.")

    def _detalhes(self, _evento=None) -> None:
        sel = self.tabela.selection()
        if not sel:
            return
        try:
            item = self.itens_visiveis[int(sel[0])]
        except (ValueError, IndexError):
            return

        resumo = "\n".join((
            f"STATUS: {item.status} | Segurança: {item.seguranca:.1f}% | Linha Excel: {item.linha_excel}",
            f"Código: {item.codigo or '-'}",
            f"Descrição: {item.descricao}",
            f"NCM atual: {item.ncm_atual or '-'}   →   provável/sugerido: {item.ncm_sugerido or '-'}",
            f"Candidatos NCM: {item.ncm_candidatos or '-'}",
            f"CEST atual: {item.cest_atual or '-'}   →   sugerido: {item.cest_sugerido or '-'}",
        ))
        tributacao = "\n".join((
            f"PIS: {item.pis_atual_texto} → referência: {item.pis_referencia_texto}",
            f"COFINS: {item.cofins_atual_texto} → referência: {item.cofins_referencia_texto}",
            f"IPI atual: {item.ipi_atual:.2f}% → TIPI: {item.ipi_referencia if item.ipi_referencia is not None else '-'}",
        ))
        divergencias = "\n".join(
            f"• {valor}" for valor in (item.divergencias or ["Nenhuma divergência confirmada."])
        )
        revisoes = "\n".join(
            f"• {valor}" for valor in (item.pendencias or ["Nenhuma pendência."])
        )
        tratamento = "\n".join((
            "PROBLEMA ENCONTRADO",
            item.problema or "-",
            "",
            "CORREÇÃO / TRATAMENTO SUGERIDO",
            item.correcao_sugerida or "-",
            "",
            "IMPORTANTE",
            "A auditoria é analítica. NCM provável/sugerido e candidatos não substituem a classificação pela composição, função e aplicação real da mercadoria.",
        ))

        abrir_detalhes_ampliados(
            self,
            titulo=f"Auditoria ampliada — {item.codigo or item.ncm_atual or '-'}",
            cabecalho=f"{item.codigo or '-'} — {item.descricao} | {item.status}",
            abas=(
                ("Resumo", resumo),
                (f"Divergências ({len(item.divergencias)})", divergencias),
                (f"Revisões ({len(item.pendencias)})", revisoes),
                ("Tributação", tributacao),
                ("Tratamento sugerido", tratamento),
            ),
        )

    def _exportar(self, somente_pendencias: bool = False) -> None:
        if self.resultado is None or self._processando:
            return
        if somente_pendencias and not any(i.status in {STATUS_CORRIGIR, STATUS_REVISAR} for i in self.resultado.itens):
            messagebox.showinfo("FiscalPro", "Não há itens CORRIGIR/REVISAR para exportar.", parent=self)
            return

        sufixo = "Pendencias" if somente_pendencias else "Completa"
        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar auditoria",
            defaultextension=".xlsx",
            initialfile=f"Auditoria_Cadastro_Produtos_{sufixo}_{date.today().strftime('%Y%m%d')}.xlsx",
            filetypes=(("Excel", "*.xlsx"),),
        )
        if not destino:
            return

        self._processando = True
        self.btn_analisar.configure(state="disabled")
        self.btn_exportar.configure(state="disabled")
        self.btn_exportar_pendencias.configure(state="disabled")
        self.btn_ficha_tributaria.configure(state="disabled")
        modo = "somente pendências" if somente_pendencias else "completa"
        self.var_status.set(f"Preparando exportação {modo}... O FiscalPro continua responsivo.")
        resultado = self.resultado

        def progresso(atual: int, total: int, descricao: str) -> None:
            self._fila.put(("export_progresso", (atual, total, descricao)))

        def executar() -> None:
            try:
                arquivo = ExportadorAuditoriaCadastrosExcelXLSX.exportar(
                    resultado,
                    destino,
                    somente_pendencias=somente_pendencias,
                    progresso=progresso,
                )
                self._fila.put(("export_ok", (arquivo, modo)))
            except Exception as erro:
                self._fila.put(("export_erro", erro))

        threading.Thread(target=executar, daemon=True).start()
        self.after(120, self._verificar_fila)

    def _exportar_ficha_tributaria(self) -> None:
        if self.resultado is None or self._processando:
            return

        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar Ficha Tributária Completa",
            defaultextension=".xlsx",
            initialfile=f"Ficha_Tributaria_FiscalPro_{date.today().strftime('%Y%m%d')}.xlsx",
            filetypes=(("Excel", "*.xlsx"),),
        )
        if not destino:
            return

        self._processando = True
        self.btn_analisar.configure(state="disabled")
        self.btn_exportar.configure(state="disabled")
        self.btn_exportar_pendencias.configure(state="disabled")
        self.btn_ficha_tributaria.configure(state="disabled")
        self.var_status.set(
            "Gerando Ficha Tributária Completa no formato do modelo... O FiscalPro continua responsivo."
        )
        resultado = self.resultado

        def progresso(atual: int, total: int, descricao: str) -> None:
            self._fila.put(("export_progresso", (atual, total, descricao)))

        def executar() -> None:
            try:
                arquivo = ExportadorFichaTributariaCompletaXLSX.exportar(
                    resultado,
                    destino,
                    progresso=progresso,
                )
                self._fila.put(("export_ok", (arquivo, "Ficha Tributária Completa")))
            except Exception as erro:
                self._fila.put(("export_erro", erro))

        threading.Thread(target=executar, daemon=True).start()
        self.after(120, self._verificar_fila)

    def _limpar(self) -> None:
        if self._processando:
            return
        self.arquivo = ""; self.resultado = None; self.itens_visiveis = []
        self.var_arquivo.set("Nenhuma planilha selecionada.")
        self.var_status.set("Selecione a planilha de cadastro de produtos.")
        self.var_resumo.set("Itens: 0  •  Corrigir: 0  •  Revisar: 0  •  Serviços: 0  •  OK: 0")
        self.btn_exportar.configure(state="disabled")
        self.btn_exportar_pendencias.configure(state="disabled")
        self.btn_ficha_tributaria.configure(state="disabled")
        self._preencher()

    def _fechar(self) -> None:
        if self._processando and not messagebox.askyesno("FiscalPro", "Há uma auditoria ou exportação em andamento. Deseja fechar?", parent=self):
            return
        self.destroy()


__all__ = ["JanelaAuditoriaCadastrosExcel"]
