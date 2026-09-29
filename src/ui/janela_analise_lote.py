"""Tela da análise e correção tributária em lote — Sprint 17.3.0."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List

from src.services.empresas_regimes_service import EmpresasRegimesService
from src.services.analise_tributaria_lote_service import (
    AnaliseTributariaLoteService,
    ExportadorAnaliseTributariaLoteXLSX,
    ResultadoAnaliseLote,
    ResultadoItemLote,
)
from src.ui.layout_responsivo import dimensionar_janela
from src.ui.painel_detalhes import abrir_detalhes_ampliados
from src.ui.janela_correcao_lote import JanelaCorrecaoTributariaLote
from src.ui.seletor_data import SeletorDataPopup


UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
)


class JanelaAnaliseTributariaLote(tk.Toplevel):
    """Importa XML, ZIP ou SPED e apresenta a conferência item a item."""

    def __init__(self, master=None):
        super().__init__(master)
        self.title("FiscalPro — Análise tributária em lote")
        dimensionar_janela(self, 1250, 850, 940, 640)
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        self.fontes: List[str] = []
        self.resultado: ResultadoAnaliseLote | None = None
        self.itens_visiveis: List[ResultadoItemLote] = []
        self._processando = False
        self._fila_resultado: queue.Queue = queue.Queue()

        self.var_empresa = tk.StringVar(value="Todas as empresas")
        self.var_empresa_info = tk.StringVar(value="Selecione a empresa para definir o regime automaticamente.")
        self.var_regime = tk.StringVar(value="Lucro Real")
        self.var_operacao = tk.StringVar(value="Venda")
        self.var_finalidade = tk.StringVar(value="Revenda")
        self.var_origem = tk.StringVar(value="MG")
        self.var_destino = tk.StringVar(value="MG")
        self.var_data = tk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        self.var_consumidor_final = tk.BooleanVar(value=False)
        self.var_fidelidade = tk.BooleanVar(value=False)
        self.var_usar_documento = tk.BooleanVar(value=True)
        self.var_usar_operacao_sped = tk.BooleanVar(value=True)
        self.var_filtro = tk.StringVar(value="Todos")
        self.var_status = tk.StringVar(value="Adicione XMLs, ZIPs, uma pasta ou um arquivo SPED.")
        self.var_fontes = tk.StringVar(value="Nenhuma fonte selecionada.")
        self.var_resumo = tk.StringVar(value="Itens: 0  •  Confirmados: 0  •  Divergências: 0  •  Revisar: 0")

        self._montar()

    def _montar(self) -> None:
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        cabecalho = ttk.Frame(self, padding=(14, 12, 14, 6))
        cabecalho.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            cabecalho,
            text="Análise tributária em lote",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            cabecalho,
            text=(
                "Leia NF-e XML, arquivos ZIP, pastas e SPED C170. O FiscalPro aponta "
                "divergências confirmadas e mantém regras condicionais marcadas para revisão."
            ),
            wraplength=1120,
        ).pack(anchor="w", pady=(3, 0))

        contexto = ttk.LabelFrame(self, text="1. Contexto da análise", padding=10)
        contexto.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 7))
        for coluna in (1, 3, 5, 7):
            contexto.grid_columnconfigure(coluna, weight=1)

        ttk.Label(contexto, text="Regime").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            contexto, textvariable=self.var_regime, state="readonly",
            values=("Lucro Real", "Lucro Presumido", "Simples Nacional", "MEI"),
        ).grid(row=0, column=1, sticky="ew", padx=(6, 12))

        ttk.Label(contexto, text="Operação padrão").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            contexto, textvariable=self.var_operacao, state="readonly",
            values=("Venda", "Revenda", "Entrada", "Compra", "Exportação", "Devolução", "Transferência"),
        ).grid(row=0, column=3, sticky="ew", padx=(6, 12))

        ttk.Label(contexto, text="Finalidade").grid(row=0, column=4, sticky="w")
        ttk.Combobox(
            contexto, textvariable=self.var_finalidade, state="readonly",
            values=("Revenda", "Uso e consumo", "Ativo imobilizado", "Industrialização"),
        ).grid(row=0, column=5, sticky="ew", padx=(6, 12))

        ttk.Label(contexto, text="Data padrão").grid(row=0, column=6, sticky="w")
        data_frame = ttk.Frame(contexto)
        data_frame.grid(row=0, column=7, sticky="ew", padx=(6, 0))
        data_frame.grid_columnconfigure(0, weight=1)
        ttk.Entry(data_frame, textvariable=self.var_data, width=12).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            data_frame, text="📅", width=4,
            command=lambda: SeletorDataPopup(self, self.var_data, titulo="Data da análise"),
        ).grid(row=0, column=1, padx=(4, 0))

        ttk.Label(contexto, text="UF origem padrão").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            contexto, textvariable=self.var_origem, values=UFS, state="readonly", width=7,
        ).grid(row=1, column=1, sticky="ew", padx=(6, 12), pady=(8, 0))
        ttk.Label(contexto, text="UF destino padrão").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Combobox(
            contexto, textvariable=self.var_destino, values=UFS, state="readonly", width=7,
        ).grid(row=1, column=3, sticky="ew", padx=(6, 12), pady=(8, 0))

        opcoes = ttk.Frame(contexto)
        opcoes.grid(row=1, column=4, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Checkbutton(opcoes, text="Consumidor final", variable=self.var_consumidor_final).pack(side=tk.LEFT)
        ttk.Checkbutton(opcoes, text="Contrato de fidelidade", variable=self.var_fidelidade).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            opcoes, text="Usar UFs e data do XML", variable=self.var_usar_documento,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            opcoes, text="Usar entrada/saída do SPED", variable=self.var_usar_operacao_sped,
        ).pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(contexto, text="Empresa").grid(row=2, column=0, sticky="w", pady=(8, 0))
        combo_empresa = ttk.Combobox(
            contexto, textvariable=self.var_empresa, state="readonly",
            values=EmpresasRegimesService.listar_empresas(incluir_todas=True),
        )
        combo_empresa.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(6, 12), pady=(8, 0))
        combo_empresa.bind("<<ComboboxSelected>>", self._empresa_alterada)
        ttk.Label(
            contexto, textvariable=self.var_empresa_info, foreground="#1F4E78",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=2, column=3, columnspan=5, sticky="w", pady=(8, 0))

        fontes = ttk.LabelFrame(self, text="2. Documentos", padding=10)
        fontes.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 7))
        fontes.grid_columnconfigure(6, weight=1)
        ttk.Button(fontes, text="＋ XML / ZIP / SPED", command=self._adicionar_arquivos).grid(row=0, column=0, sticky="ew")
        ttk.Button(fontes, text="📁 Pasta", command=self._adicionar_pasta).grid(row=0, column=1, sticky="ew", padx=(7, 0))
        ttk.Button(fontes, text="Limpar", command=self._limpar_fontes).grid(row=0, column=2, sticky="ew", padx=(7, 0))
        self.btn_analisar = ttk.Button(fontes, text="Analisar lote", command=self._analisar)
        self.btn_analisar.grid(row=0, column=3, sticky="ew", padx=(14, 0))
        self.btn_exportar = ttk.Button(fontes, text="Exportar Excel", command=self._exportar, state="disabled")
        self.btn_exportar.grid(row=0, column=4, sticky="ew", padx=(7, 0))
        self.btn_corrigir = ttk.Button(
            fontes, text="Corrigir divergências", command=self._abrir_correcao, state="disabled"
        )
        self.btn_corrigir.grid(row=0, column=5, sticky="ew", padx=(7, 0))
        ttk.Label(fontes, textvariable=self.var_fontes, anchor="w").grid(row=0, column=6, sticky="ew", padx=(12, 0))

        area = ttk.Frame(self)
        area.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 7))
        area.grid_rowconfigure(2, weight=1)
        area.grid_columnconfigure(0, weight=1)

        barra = ttk.Frame(area)
        barra.grid(row=0, column=0, sticky="ew")
        ttk.Label(barra, textvariable=self.var_resumo, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(barra, text="Filtro:").pack(side=tk.RIGHT, padx=(8, 4))
        filtro = ttk.Combobox(
            barra, textvariable=self.var_filtro, state="readonly", width=16,
            values=("Todos", "Confirmados", "Divergências", "Revisar", "Sem NCM"),
        )
        filtro.pack(side=tk.RIGHT)
        filtro.bind("<<ComboboxSelected>>", lambda _e: self._preencher_tabela())

        ttk.Label(area, textvariable=self.var_status, anchor="w").grid(row=1, column=0, sticky="ew", pady=(4, 4))

        quadro_tabela = ttk.Frame(area)
        quadro_tabela.grid(row=2, column=0, sticky="nsew")
        quadro_tabela.grid_rowconfigure(0, weight=1)
        quadro_tabela.grid_columnconfigure(0, weight=1)
        colunas = ("fonte", "documento", "item", "ncm", "descricao", "pis", "icms", "st", "status")
        self.tabela = ttk.Treeview(quadro_tabela, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "fonte": "Fonte", "documento": "Documento", "item": "Item", "ncm": "NCM",
            "descricao": "Descrição", "pis": "PIS/Cofins", "icms": "ICMS", "st": "ICMS-ST", "status": "Status",
        }
        larguras = {"fonte": 105, "documento": 150, "item": 60, "ncm": 90, "descricao": 300, "pis": 155, "icms": 145, "st": 170, "status": 100}
        for coluna in colunas:
            self.tabela.heading(coluna, text=titulos[coluna])
            self.tabela.column(coluna, width=larguras[coluna], minwidth=55, anchor="w")
        self.tabela.column("item", anchor="center")
        self.tabela.column("ncm", anchor="center")
        self.tabela.column("status", anchor="center")
        rolagem_y = ttk.Scrollbar(quadro_tabela, orient="vertical", command=self.tabela.yview)
        rolagem_x = ttk.Scrollbar(quadro_tabela, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        rolagem_y.grid(row=0, column=1, sticky="ns")
        rolagem_x.grid(row=1, column=0, sticky="ew")
        self.tabela.bind("<Double-1>", self._mostrar_detalhes)

        self.tabela.tag_configure("CONFIRMADO", background="#E7F4E4")
        self.tabela.tag_configure("DIVERGÊNCIA", background="#FCE8E6")
        self.tabela.tag_configure("REVISAR", background="#FFF6D8")
        self.tabela.tag_configure("SEM NCM", background="#ECECEC")

        rodape = ttk.Frame(self, padding=(14, 0, 14, 10))
        rodape.grid(row=4, column=0, sticky="ew")
        ttk.Label(
            rodape,
            text="Dê dois cliques em um item para ver divergências, pendências, fundamentos e fontes.",
        ).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self._fechar).pack(side=tk.RIGHT)

    def _adicionar_arquivos(self) -> None:
        arquivos = filedialog.askopenfilenames(
            title="Selecione XMLs, ZIPs ou SPEDs",
            parent=self,
            filetypes=(
                ("Documentos fiscais", "*.xml *.zip *.txt"),
                ("NF-e XML", "*.xml"),
                ("Arquivo ZIP", "*.zip"),
                ("SPED TXT", "*.txt"),
                ("Todos os arquivos", "*.*"),
            ),
        )
        self._incluir_fontes(list(arquivos))

    def _adicionar_pasta(self) -> None:
        pasta = filedialog.askdirectory(title="Selecione a pasta com XMLs ou SPEDs", parent=self)
        if pasta:
            self._incluir_fontes([pasta])

    def _incluir_fontes(self, caminhos: List[str]) -> None:
        existentes = {str(Path(item).resolve()).lower() for item in self.fontes if Path(item).exists()}
        for caminho in caminhos:
            try:
                chave = str(Path(caminho).resolve()).lower()
            except OSError:
                chave = caminho.lower()
            if chave not in existentes:
                self.fontes.append(caminho)
                existentes.add(chave)
        self._atualizar_rotulo_fontes()

    def _limpar_fontes(self) -> None:
        if self._processando:
            return
        self.fontes.clear()
        self.resultado = None
        self.itens_visiveis.clear()
        self._atualizar_rotulo_fontes()
        self._preencher_tabela()
        self.var_resumo.set("Itens: 0  •  Confirmados: 0  •  Divergências: 0  •  Revisar: 0")
        self.btn_exportar.configure(state="disabled")

    def _atualizar_rotulo_fontes(self) -> None:
        if not self.fontes:
            self.var_fontes.set("Nenhuma fonte selecionada.")
            return
        nomes = [Path(item).name or item for item in self.fontes]
        previa = ", ".join(nomes[:3])
        if len(nomes) > 3:
            previa += f" e mais {len(nomes) - 3}"
        self.var_fontes.set(f"{len(nomes)} fonte(s): {previa}")

    def _empresa_alterada(self, _evento=None) -> None:
        empresa = self.var_empresa.get().strip()
        perfil = EmpresasRegimesService.obter_perfil(empresa)
        if perfil is not None:
            self.var_regime.set(perfil.regime.title())
        self.var_empresa_info.set(
            EmpresasRegimesService.descricao_regime(empresa, self.var_regime.get())
        )

    def _contexto(self) -> dict:
        return {
            "empresa": "" if self.var_empresa.get().strip() == "Todas as empresas" else self.var_empresa.get().strip(),
            "regime": EmpresasRegimesService.resolver_regime(self.var_empresa.get(), self.var_regime.get()),
            "operacao": self.var_operacao.get(),
            "finalidade": self.var_finalidade.get(),
            "uf_origem": self.var_origem.get(),
            "uf_destino": self.var_destino.get(),
            "data_operacao": self.var_data.get(),
            "consumidor_final": self.var_consumidor_final.get(),
            "contrato_fidelidade": self.var_fidelidade.get(),
            "usar_uf_data_documento": self.var_usar_documento.get(),
            "usar_operacao_sped": self.var_usar_operacao_sped.get(),
        }

    def _analisar(self) -> None:
        if self._processando:
            return
        if not self.fontes:
            messagebox.showwarning("FiscalPro", "Adicione ao menos um XML, ZIP, SPED ou pasta.", parent=self)
            return
        fontes = list(self.fontes)
        contexto = self._contexto()
        self._processando = True
        self.btn_analisar.configure(state="disabled")
        self.btn_exportar.configure(state="disabled")
        self.btn_corrigir.configure(state="disabled")
        self.var_status.set("Analisando os documentos... O FiscalPro não altera os arquivos originais.")
        self.update_idletasks()

        def executar() -> None:
            try:
                resultado = AnaliseTributariaLoteService().analisar(fontes, contexto)
                self._fila_resultado.put(("ok", resultado))
            except Exception as erro:  # pragma: no cover - proteção da interface.
                self._fila_resultado.put(("erro", erro))

        threading.Thread(target=executar, daemon=True).start()
        self.after(100, self._verificar_fila_resultado)

    def _verificar_fila_resultado(self) -> None:
        try:
            tipo, valor = self._fila_resultado.get_nowait()
        except queue.Empty:
            if self._processando and self.winfo_exists():
                self.after(100, self._verificar_fila_resultado)
            return
        if tipo == "ok":
            self._analise_concluida(valor)
        else:
            self._analise_falhou(valor)

    def _analise_concluida(self, resultado: ResultadoAnaliseLote) -> None:
        self.resultado = resultado
        self._processando = False
        self.btn_analisar.configure(state="normal")
        self.btn_exportar.configure(state="normal" if resultado.itens else "disabled")
        possui_sped_divergente = any(
            item.status == "DIVERGÊNCIA" and item.fonte_tipo.upper().startswith("SPED")
            for item in resultado.itens
        )
        self.btn_corrigir.configure(state="normal" if possui_sped_divergente else "disabled")
        resumo = resultado.resumo()
        self.var_resumo.set(
            f"Itens: {resumo['itens']}  •  Confirmados: {resumo['confirmados']}  •  "
            f"Divergências: {resumo['divergencias']}  •  Revisar: {resumo['revisar']}  •  Sem NCM: {resumo['sem_ncm']}"
        )
        aviso = f"Análise concluída em {resumo['arquivos_processados']} arquivo(s)."
        if resultado.erros:
            aviso += f" {len(resultado.erros)} aviso(s) de leitura foram registrados no relatório."
        self.var_status.set(aviso)
        self._preencher_tabela()

    def _analise_falhou(self, erro: Exception) -> None:
        self._processando = False
        self.btn_analisar.configure(state="normal")
        self.btn_corrigir.configure(state="disabled")
        self.var_status.set("Não foi possível concluir a análise.")
        messagebox.showerror("FiscalPro", str(erro), parent=self)

    def _preencher_tabela(self) -> None:
        for iid in self.tabela.get_children():
            self.tabela.delete(iid)
        if self.resultado is None:
            self.itens_visiveis = []
            return
        filtro = self.var_filtro.get()
        mapa = {
            "Confirmados": "CONFIRMADO",
            "Divergências": "DIVERGÊNCIA",
            "Revisar": "REVISAR",
            "Sem NCM": "SEM NCM",
        }
        status_filtro = mapa.get(filtro)
        self.itens_visiveis = [
            item for item in self.resultado.itens
            if not status_filtro or item.status == status_filtro
        ]
        for indice, item in enumerate(self.itens_visiveis):
            pis = item.piscofins_status or "-"
            icms = (
                f"{item.aliquota_icms_esperada:.2f}%"
                if item.aliquota_icms_esperada is not None else item.icms_status or "-"
            )
            st = item.st_status or ("CEST " + item.cest_esperado if item.cest_esperado else "-")
            self.tabela.insert(
                "", "end", iid=str(indice), tags=(item.status,),
                values=(
                    item.fonte_tipo, item.documento, item.numero_item, item.ncm or "-",
                    item.descricao, pis, icms, st, item.status,
                ),
            )

    def _mostrar_detalhes(self, _evento=None) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            return
        try:
            item = self.itens_visiveis[int(selecao[0])]
        except (IndexError, ValueError):
            return

        resumo = "\n".join((
            f"STATUS: {item.status}  |  Segurança: {item.confiabilidade:.2f}%",
            f"Fonte: {item.fonte_tipo} — {item.arquivo}",
            f"Documento: {item.documento}  |  Item: {item.numero_item}  |  Linha SPED: {item.numero_linha_fonte or '-'}",
            f"Produto: {item.codigo} — {item.descricao}",
            f"NCM: {item.ncm} — {item.ncm_oficial}",
            f"Operação: {item.uf_origem} → {item.uf_destino} em {item.data_operacao} | CFOP {item.cfop}",
        ))

        tributacao = "\n".join((
            "PIS/COFINS",
            f"Status: {item.piscofins_status}",
            f"PIS: CST {item.cst_pis_atual or '-'} / {item.aliquota_pis_atual:.2f}%  →  CST {item.cst_pis_esperado or '-'} / {self._fmt(item.aliquota_pis_esperada)}",
            f"COFINS: CST {item.cst_cofins_atual or '-'} / {item.aliquota_cofins_atual:.2f}%  →  CST {item.cst_cofins_esperado or '-'} / {self._fmt(item.aliquota_cofins_esperada)}",
            "",
            "ICMS / ICMS-ST",
            f"Status ICMS: {item.icms_status}",
            f"Alíquota: {item.aliquota_icms_atual:.2f}% → {self._fmt(item.aliquota_icms_esperada)}",
            f"CEST: {item.cest_atual or '-'} → {item.cest_esperado or '-'}",
            f"Status ST: {item.st_status}",
            f"MVA no documento: {self._fmt(item.mva_st_atual)}",
            f"MVA original: {self._fmt(item.mva_original)} | MVA ajustada: {self._fmt(item.mva_ajustada)}",
            f"MVA aplicada: {self._fmt(item.mva_aplicada)} | Tipo: {item.mva_tipo or '-'}",
            f"FCP/FEM: {self._fmt(item.aliquota_fcp_st_atual)} → {self._fmt(item.fcp_esperado)}",
            f"Status FCP/FEM: {item.fcp_status or '-'}",
            f"Vigência/referência ST: {item.st_vigencia_referencia or '-'}",
        ))

        divergencias = "\n".join(
            f"• {valor}" for valor in (item.divergencias or ["Nenhuma divergência confirmada."])
        )
        pendencias = "\n".join(
            f"• {valor}" for valor in (item.pendencias or ["Nenhuma pendência registrada."])
        )
        fundamentos = "\n".join((
            "PIS/COFINS",
            f"Fundamento: {item.fundamento_piscofins or '-'}",
            f"Fonte: {item.fonte_piscofins or '-'}",
            "",
            "ICMS / ICMS-ST",
            f"Fundamento: {item.fundamento_icms or '-'}",
            f"Fonte: {item.fonte_icms or '-'}",
            "",
            "OBSERVAÇÃO",
            item.observacao or "-",
        ))

        abrir_detalhes_ampliados(
            self,
            titulo=f"Detalhes ampliados — NCM {item.ncm or '-'}",
            cabecalho=f"{item.codigo or '-'} — {item.descricao} | {item.status}",
            abas=(
                ("Resumo", resumo),
                (f"Divergências ({len(item.divergencias)})", divergencias),
                (f"Revisões ({len(item.pendencias)})", pendencias),
                ("Tributação", tributacao),
                ("Fundamentos", fundamentos),
            ),
        )

    @staticmethod
    def _fmt(valor) -> str:
        return "-" if valor is None else f"{float(valor):.2f}%"

    def _abrir_correcao(self) -> None:
        if self.resultado is None:
            messagebox.showwarning("FiscalPro", "Execute a análise antes de preparar correções.", parent=self)
            return
        JanelaCorrecaoTributariaLote(self, self.resultado)

    def _exportar(self) -> None:
        if self.resultado is None or not self.resultado.itens:
            messagebox.showwarning("FiscalPro", "Execute a análise antes de exportar.", parent=self)
            return
        nome = f"Analise_Tributaria_Lote_{date.today().strftime('%Y%m%d')}.xlsx"
        caminho = filedialog.asksaveasfilename(
            title="Salvar análise tributária em lote",
            parent=self,
            defaultextension=".xlsx",
            initialfile=nome,
            filetypes=(("Planilha Excel", "*.xlsx"),),
        )
        if not caminho:
            return
        try:
            arquivo = ExportadorAnaliseTributariaLoteXLSX.exportar(self.resultado, caminho)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível gerar a planilha:\n{erro}", parent=self)
            return
        messagebox.showinfo("FiscalPro", f"Planilha gerada com sucesso:\n{arquivo}", parent=self)

    def _fechar(self) -> None:
        if self._processando:
            sair = messagebox.askyesno(
                "FiscalPro", "A análise ainda está em andamento. Deseja fechar a tela?", parent=self,
            )
            if not sair:
                return
        self.destroy()


__all__ = ["JanelaAnaliseTributariaLote"]
