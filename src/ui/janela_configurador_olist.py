"""Tela Produto → Configuração Olist — Hotfix 17.8.50."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.configurador_olist_service import ConfiguradorOlistService
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.ui.janela_catalogo_ncm import JanelaCatalogoNCM
from src.ui.layout_responsivo import dimensionar_janela
from src.ui.recursos import aplicar_icone


UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
)


class JanelaConfiguradorOlist(tk.Toplevel):
    """Consulta enxuta voltada à configuração tributária de vendas no Olist."""

    def __init__(self, master=None):
        super().__init__(master)
        self.title("FiscalPro — Configurador Tributário para Olist")
        dimensionar_janela(self, 1260, 900, 960, 680)
        aplicar_icone(self)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)
        self.resultado_atual = None

        self.produto_var = tk.StringVar()
        self.ncm_var = tk.StringVar()
        self.empresa_var = tk.StringVar()
        self.regime_var = tk.StringVar(value="Lucro Real")
        self.regime_info_var = tk.StringVar(
            value="Empresa nova: informe o regime. Empresa cadastrada: o FiscalPro aplica o regime automaticamente."
        )
        self.origem_var = tk.StringVar(value="MG")
        self.destino_var = tk.StringVar(value="ES")
        self.destinatario_var = tk.StringVar(value="Não contribuinte")
        self.consumidor_final_var = tk.BooleanVar(value=True)
        self.valor_var = tk.StringVar()

        self.perfil_var = tk.StringVar(value="Comerciante")
        self.situacao_st_var = tk.StringVar(value="Não informado")
        self.importada_var = tk.BooleanVar(value=False)
        self.excecao_4_var = tk.BooleanVar(value=False)
        self.fidelidade_var = tk.BooleanVar(value=False)

        self.status_var = tk.StringVar(
            value="Informe o produto e a operação. O FiscalPro só confirma o que estiver sustentado pelas bases instaladas."
        )

        self._criar_interface()
        self.produto_entry.focus_set()

    def _criar_interface(self) -> None:
        cab = ttk.Frame(self, padding=(14, 12, 14, 5))
        cab.grid(row=0, column=0, sticky="ew")
        ttk.Label(cab, text="Produto → configuração tributária do Olist", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            cab,
            text=(
                "Informe o produto, a empresa e o destino. O FiscalPro reúne CFOP, CST/CSOSN, ICMS, ST, "
                "DIFAL/FCP, PIS/COFINS e a orientação de configuração da nota."
            ),
        ).pack(anchor="w", pady=(2, 0))

        principal = ttk.LabelFrame(self, text="Produto e venda", padding=10)
        principal.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 7))
        for coluna in range(8):
            principal.grid_columnconfigure(coluna, weight=1 if coluna in {1, 3, 5, 7} else 0)

        ttk.Label(principal, text="Produto / descrição").grid(row=0, column=0, sticky="w")
        self.produto_entry = ttk.Entry(principal, textvariable=self.produto_var)
        self.produto_entry.grid(row=0, column=1, columnspan=5, sticky="ew", padx=(6, 8))
        self.produto_entry.bind("<Return>", lambda _e: self.abrir_catalogo())
        self.produto_entry.bind("<KP_Enter>", lambda _e: self.abrir_catalogo())
        ttk.Button(principal, text="Buscar NCM no catálogo", command=self.abrir_catalogo).grid(
            row=0, column=6, columnspan=2, sticky="ew"
        )

        ttk.Label(principal, text="NCM").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ncm_entry = ttk.Entry(principal, textvariable=self.ncm_var, width=18)
        ncm_entry.grid(row=1, column=1, sticky="ew", padx=(6, 12), pady=(8, 0))
        ncm_entry.bind("<Return>", lambda _e: self.analisar())
        ncm_entry.bind("<KP_Enter>", lambda _e: self.analisar())

        ttk.Label(principal, text="Empresa").grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.combo_empresa = ttk.Combobox(
            principal,
            textvariable=self.empresa_var,
            values=EmpresasRegimesService.listar_empresas(),
            state="normal",
        )
        self.combo_empresa.grid(row=1, column=3, columnspan=2, sticky="ew", padx=(6, 12), pady=(8, 0))
        self.combo_empresa.bind("<<ComboboxSelected>>", self._empresa_alterada)
        self.combo_empresa.bind("<FocusOut>", self._empresa_alterada)

        ttk.Label(principal, text="Regime").grid(row=1, column=5, sticky="w", pady=(8, 0))
        ttk.Combobox(
            principal,
            textvariable=self.regime_var,
            values=("Lucro Real", "Lucro Presumido", "Simples Nacional", "MEI", "Outro"),
            state="readonly",
        ).grid(row=1, column=6, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        ttk.Label(
            principal,
            textvariable=self.regime_info_var,
            foreground="#1F4E78",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=2, column=0, columnspan=8, sticky="w", pady=(7, 0))

        ttk.Label(principal, text="UF origem").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(principal, textvariable=self.origem_var, values=UFS, state="readonly", width=7).grid(
            row=3, column=1, sticky="ew", padx=(6, 12), pady=(8, 0)
        )
        ttk.Label(principal, text="UF destino").grid(row=3, column=2, sticky="w", pady=(8, 0))
        ttk.Combobox(principal, textvariable=self.destino_var, values=UFS, state="readonly", width=7).grid(
            row=3, column=3, sticky="ew", padx=(6, 12), pady=(8, 0)
        )
        ttk.Label(principal, text="Destinatário").grid(row=3, column=4, sticky="w", pady=(8, 0))
        ttk.Combobox(
            principal,
            textvariable=self.destinatario_var,
            values=("Não contribuinte", "Contribuinte", "Não informado"),
            state="readonly",
        ).grid(row=3, column=5, sticky="ew", padx=(6, 12), pady=(8, 0))
        ttk.Checkbutton(
            principal,
            text="Consumidor final",
            variable=self.consumidor_final_var,
        ).grid(row=3, column=6, sticky="w", pady=(8, 0))

        ttk.Label(principal, text="Valor da operação (opcional)").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(principal, textvariable=self.valor_var).grid(
            row=4, column=1, sticky="ew", padx=(6, 12), pady=(8, 0)
        )
        ttk.Label(
            principal,
            text="Preencha o valor quando quiser também a memória de cálculo do DIFAL/FCP.",
        ).grid(row=4, column=2, columnspan=6, sticky="w", pady=(8, 0))

        avancado = ttk.LabelFrame(self, text="Detalhes avançados — use quando a operação exigir", padding=9)
        avancado.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 7))
        for coluna in range(6):
            avancado.grid_columnconfigure(coluna, weight=1 if coluna in {1, 3, 5} else 0)

        ttk.Label(avancado, text="Perfil do remetente").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            avancado,
            textvariable=self.perfil_var,
            values=("Comerciante", "Fabricante", "Importador", "Fabricante/Importador"),
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", padx=(6, 12))

        ttk.Label(avancado, text="Situação ICMS-ST").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            avancado,
            textvariable=self.situacao_st_var,
            values=(
                "Não informado",
                "ICMS-ST já retido na entrada",
                "Responsável por reter ICMS-ST nesta saída",
                "Mercadoria sem retenção de ICMS-ST",
            ),
            state="readonly",
        ).grid(row=0, column=3, columnspan=3, sticky="ew", padx=(6, 0))

        ttk.Checkbutton(avancado, text="Mercadoria importada", variable=self.importada_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(7, 0)
        )
        ttk.Checkbutton(avancado, text="Exceção legal à alíquota de 4%", variable=self.excecao_4_var).grid(
            row=1, column=2, columnspan=2, sticky="w", pady=(7, 0)
        )
        ttk.Checkbutton(avancado, text="Contrato de fidelidade / MVA específica", variable=self.fidelidade_var).grid(
            row=1, column=4, columnspan=2, sticky="w", pady=(7, 0)
        )

        acoes = ttk.Frame(self, padding=(14, 0, 14, 7))
        acoes.grid(row=3, column=0, sticky="ew")
        ttk.Button(
            acoes,
            text="🧾 GERAR CONFIGURAÇÃO OLIST",
            command=self.analisar,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(acoes, text="Copiar configuração", command=self.copiar_configuracao).pack(side="left", padx=(7, 0))
        ttk.Button(acoes, text="Salvar relatório", command=self.salvar_relatorio).pack(side="left", padx=(7, 0))
        ttk.Button(acoes, text="Limpar", command=self.limpar).pack(side="left", padx=(7, 0))

        ttk.Label(self, textvariable=self.status_var, anchor="w", wraplength=1180).grid(
            row=4, column=0, sticky="ew", padx=14, pady=(0, 7)
        )

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=5, column=0, sticky="nsew", padx=14, pady=(0, 14))

        self.aba_resumo = ttk.Frame(self.notebook, padding=8)
        self.aba_olist = ttk.Frame(self.notebook, padding=8)
        self.aba_relatorio = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.aba_resumo, text="  Resumo fiscal  ")
        self.notebook.add(self.aba_olist, text="  Configuração Olist  ")
        self.notebook.add(self.aba_relatorio, text="  Relatório completo  ")

        for aba in (self.aba_resumo, self.aba_olist, self.aba_relatorio):
            aba.grid_rowconfigure(0, weight=1)
            aba.grid_columnconfigure(0, weight=1)

        self.txt_resumo = tk.Text(self.aba_resumo, wrap=tk.WORD, font=("Consolas", 10), padx=10, pady=10)
        barra_resumo = ttk.Scrollbar(self.aba_resumo, orient="vertical", command=self.txt_resumo.yview)
        self.txt_resumo.configure(yscrollcommand=barra_resumo.set)
        self.txt_resumo.grid(row=0, column=0, sticky="nsew")
        barra_resumo.grid(row=0, column=1, sticky="ns")
        self.txt_resumo.insert(tk.END, "A configuração aparecerá aqui depois da análise.\n")

        colunas = ("grupo", "campo", "valor", "status")
        self.tabela = ttk.Treeview(self.aba_olist, columns=colunas, show="headings", height=16)
        self.tabela.heading("grupo", text="Grupo")
        self.tabela.heading("campo", text="Campo")
        self.tabela.heading("valor", text="Valor / configuração")
        self.tabela.heading("status", text="Status")
        self.tabela.column("grupo", width=110, anchor="w", stretch=False)
        self.tabela.column("campo", width=285, anchor="w")
        self.tabela.column("valor", width=540, anchor="w")
        self.tabela.column("status", width=110, anchor="center", stretch=False)
        barra_y = ttk.Scrollbar(self.aba_olist, orient="vertical", command=self.tabela.yview)
        barra_x = ttk.Scrollbar(self.aba_olist, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")

        self.txt_relatorio = tk.Text(self.aba_relatorio, wrap=tk.WORD, font=("Consolas", 9), padx=10, pady=10)
        barra_relatorio = ttk.Scrollbar(self.aba_relatorio, orient="vertical", command=self.txt_relatorio.yview)
        self.txt_relatorio.configure(yscrollcommand=barra_relatorio.set)
        self.txt_relatorio.grid(row=0, column=0, sticky="nsew")
        barra_relatorio.grid(row=0, column=1, sticky="ns")

    def _empresa_alterada(self, _evento=None) -> None:
        empresa = self.empresa_var.get().strip()
        perfil = EmpresasRegimesService.obter_perfil(empresa)
        if perfil is not None:
            self.regime_var.set(perfil.regime.title())
            self.regime_info_var.set(EmpresasRegimesService.descricao_regime(empresa, perfil.regime))
            return
        if empresa:
            self.regime_info_var.set(
                "Empresa nova / não cadastrada: o regime selecionado nesta tela será usado somente nesta análise."
            )
        else:
            self.regime_info_var.set(
                "Você pode digitar o nome da nova empresa. Depois informe o regime tributário."
            )

    def abrir_catalogo(self) -> None:
        janela = JanelaCatalogoNCM(self, ao_selecionar=self._usar_ncm_catalogo)
        termo = self.produto_var.get().strip()
        if termo:
            janela.termo.delete(0, tk.END)
            janela.termo.insert(0, termo)
            janela.pesquisar()

    def _usar_ncm_catalogo(self, ncm: str) -> None:
        self.ncm_var.set(ncm)
        if not self.produto_var.get().strip():
            itens = BaseOficialRepository.buscar_ncm_catalogo(ncm, limite=1)
            if itens:
                self.produto_var.set(
                    str(itens[0].get("descricao_completa") or itens[0].get("descricao") or "")
                )
        self.status_var.set(f"NCM {ncm} selecionado. Confira a operação e gere a configuração.")

    def _destinatario_contribuinte(self):
        texto = self.destinatario_var.get().strip().lower()
        if texto == "contribuinte":
            return True
        if texto == "não contribuinte":
            return False
        return None

    def analisar(self) -> None:
        self._empresa_alterada()
        try:
            resultado = ConfiguradorOlistService.analisar(
                ncm=self.ncm_var.get(),
                descricao_produto=self.produto_var.get(),
                empresa=self.empresa_var.get(),
                regime=self.regime_var.get(),
                uf_origem=self.origem_var.get(),
                uf_destino=self.destino_var.get(),
                destinatario_contribuinte=self._destinatario_contribuinte(),
                consumidor_final=bool(self.consumidor_final_var.get()),
                valor_operacao=self.valor_var.get().strip() or None,
                perfil_remetente=self.perfil_var.get(),
                situacao_icms_st=self.situacao_st_var.get(),
                mercadoria_importada=bool(self.importada_var.get()),
                excecao_aliquota_importacao=bool(self.excecao_4_var.get()),
                contrato_fidelidade=bool(self.fidelidade_var.get()),
            )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            return

        self.resultado_atual = resultado
        self._preencher_resultado()

    def _preencher_resultado(self) -> None:
        resultado = self.resultado_atual
        if resultado is None:
            return
        c = resultado.consulta
        decisao = resultado.robo.decisao_operacao
        difal = resultado.difal
        icms = resultado.icms_uf

        linhas = [
            "CONFIGURAÇÃO TRIBUTÁRIA DA VENDA",
            "=" * 74,
            f"Produto: {c.descricao_produto or '-'}",
            f"NCM: {c.ncm}",
            f"Empresa / regime: {c.empresa or 'Empresa nova'} / {c.regime}",
            f"Rota: {c.uf_origem} → {c.uf_destino}",
            f"Status geral: {resultado.status}",
            f"Segurança conservadora: {resultado.confiabilidade:.0f}%" if resultado.confiabilidade else "Segurança conservadora: -",
            "",
        ]
        if decisao is not None:
            linhas.extend(
                [
                    f"CFOP provável: {decisao.cfop.valor or '-'}  [{decisao.cfop.status}]",
                    f"CST/CSOSN: {decisao.icms.valor or '-'}  [{decisao.icms.status}]",
                    f"Destaque ICMS: {decisao.destaque_icms.valor or '-'}  [{decisao.destaque_icms.status}]",
                    f"ICMS-ST: {decisao.icms_st.valor or '-'}  [{decisao.icms_st.status}]",
                    f"PIS: {decisao.pis.valor or '-'}  [{decisao.pis.status}]",
                    f"COFINS: {decisao.cofins.valor or '-'}  [{decisao.cofins.status}]",
                    f"DIFAL/FCP: {decisao.difal.valor or '-'}  [{decisao.difal.status}]",
                ]
            )
        linhas.extend(
            [
                "",
                f"Alíquota da operação: {ConfiguradorOlistService._percentual(icms.get('aliquota_operacao'))}",
                f"Alíquota interna destino: {ConfiguradorOlistService._percentual(difal.get('aliquota_interna_destino'))}",
                f"FCP: {ConfiguradorOlistService._percentual(difal.get('aliquota_fcp'))}",
                f"CEST: {icms.get('cest') or '-'}",
                f"MVA: {ConfiguradorOlistService._percentual(icms.get('mva_aplicada'))}",
            ]
        )
        if difal.get("valor_operacao") is not None:
            linhas.extend(
                [
                    "",
                    f"Valor da operação: {ConfiguradorOlistService._moeda(difal.get('valor_operacao'))}",
                    f"DIFAL esperado: {ConfiguradorOlistService._moeda(difal.get('valor_difal'))}",
                    f"FCP esperado: {ConfiguradorOlistService._moeda(difal.get('valor_fcp'))}",
                ]
            )
        if resultado.alertas:
            linhas.extend(["", "REVISAR ANTES DE APLICAR", "-" * 74])
            linhas.extend(f"• {a}" for a in dict.fromkeys(resultado.alertas))

        self.txt_resumo.delete("1.0", tk.END)
        self.txt_resumo.insert(tk.END, "\n".join(linhas))

        for item in self.tabela.get_children():
            self.tabela.delete(item)
        for campo in resultado.campos_olist:
            item_id = self.tabela.insert(
                "",
                "end",
                values=(campo.grupo, campo.campo, campo.valor, campo.status),
            )
            if campo.observacao:
                self.tabela.insert(
                    "",
                    "end",
                    values=("", "↳ orientação", campo.observacao, ""),
                )

        self.txt_relatorio.delete("1.0", tk.END)
        self.txt_relatorio.insert(tk.END, resultado.relatorio)
        self.status_var.set(
            f"Resultado: {resultado.status} • segurança {resultado.confiabilidade:.0f}% • "
            "abra a aba 'Configuração Olist' para ver campo por campo."
        )
        self.notebook.select(self.aba_olist)

    def copiar_configuracao(self) -> None:
        if self.resultado_atual is None:
            messagebox.showwarning("FiscalPro", "Gere primeiro a configuração.", parent=self)
            return
        texto = self.resultado_atual.relatorio
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update_idletasks()
        self.status_var.set("Configuração copiada para a área de transferência.")

    def salvar_relatorio(self) -> None:
        if self.resultado_atual is None:
            messagebox.showwarning("FiscalPro", "Gere primeiro a configuração.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar configuração tributária do Olist",
            defaultextension=".txt",
            initialfile=f"CONFIGURACAO_OLIST_{self.resultado_atual.consulta.ncm}.txt",
            filetypes=(("Arquivo de texto", "*.txt"), ("Todos os arquivos", "*.*")),
        )
        if not caminho:
            return
        Path(caminho).write_text(self.resultado_atual.relatorio, encoding="utf-8")
        self.status_var.set(f"Relatório salvo em {caminho}")

    def limpar(self) -> None:
        self.resultado_atual = None
        self.produto_var.set("")
        self.ncm_var.set("")
        self.empresa_var.set("")
        self.regime_var.set("Lucro Real")
        self.origem_var.set("MG")
        self.destino_var.set("ES")
        self.destinatario_var.set("Não contribuinte")
        self.consumidor_final_var.set(True)
        self.valor_var.set("")
        self.perfil_var.set("Comerciante")
        self.situacao_st_var.set("Não informado")
        self.importada_var.set(False)
        self.excecao_4_var.set(False)
        self.fidelidade_var.set(False)
        self.regime_info_var.set(
            "Você pode digitar o nome da nova empresa. Depois informe o regime tributário."
        )
        self.txt_resumo.delete("1.0", tk.END)
        self.txt_resumo.insert(tk.END, "A configuração aparecerá aqui depois da análise.\n")
        self.txt_relatorio.delete("1.0", tk.END)
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        self.status_var.set("Informe o produto e a operação.")
        self.produto_entry.focus_set()


__all__ = ["JanelaConfiguradorOlist"]
