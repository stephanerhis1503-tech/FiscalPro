"""Interface do Robô Tributário Inteligente — Sprint 17.5.2."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.inteligencia.consulta_tributaria import ConsultaTributaria
from src.services.robo_tributario_service import RoboTributarioService
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.ui.layout_responsivo import dimensionar_janela
from src.ui.recursos import aplicar_icone


UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
)


class JanelaRoboTributario(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("FiscalPro — Robô Tributário Inteligente")
        dimensionar_janela(self, 1280, 900, 960, 680)
        aplicar_icone(self)
        self.resultado_atual = None

        self.ncm_var = tk.StringVar()
        self.descricao_var = tk.StringVar()
        self.empresa_var = tk.StringVar(value="Todas as empresas")
        self.empresa_regime_info_var = tk.StringVar(value="Selecione uma empresa para definir o regime automaticamente.")
        self.uf_origem_var = tk.StringVar(value="MG")
        self.uf_destino_var = tk.StringVar(value="MG")
        self.regime_var = tk.StringVar(value="Lucro Real")
        self.operacao_var = tk.StringVar(value="Venda")
        self.finalidade_var = tk.StringVar(value="Revenda")
        self.perfil_var = tk.StringVar(value="Comerciante")
        self.situacao_st_var = tk.StringVar(value="Não informado")
        self.destinatario_var = tk.StringVar(value="Não informado")
        self.consumidor_var = tk.BooleanVar(value=False)
        self.importada_var = tk.BooleanVar(value=False)
        self.excecao_4_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Informe a operação e clique em Analisar operação.")

        self.decisao_status_var = tk.StringVar(value="Decisão: aguardando análise")
        self.decisao_cfop_var = tk.StringVar(value="-")
        self.decisao_icms_var = tk.StringVar(value="-")
        self.decisao_pis_var = tk.StringVar(value="-")
        self.decisao_cofins_var = tk.StringVar(value="-")
        self.decisao_difal_var = tk.StringVar(value="-")
        self.decisao_destaque_var = tk.StringVar(value="-")

        self._criar_interface()
        self.ncm_entry.focus_set()

    def _criar_interface(self):
        self.grid_rowconfigure(5, weight=1)
        self.grid_columnconfigure(0, weight=1)

        cabecalho = ttk.Frame(self, padding=(14, 12, 14, 4))
        cabecalho.grid(row=0, column=0, sticky="ew")
        ttk.Label(cabecalho, text="Robô Tributário Inteligente", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            cabecalho,
            text="Cruza o contexto da operação com os motores do FiscalPro e separa o que está confirmado do que exige revisão.",
        ).pack(anchor="w", pady=(2, 0))

        form = ttk.LabelFrame(self, text="Contexto da operação", padding=10)
        form.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 7))
        for c in range(8):
            form.grid_columnconfigure(c, weight=1 if c in {1, 3, 5, 7} else 0)

        ttk.Label(form, text="NCM").grid(row=0, column=0, sticky="w")
        self.ncm_entry = ttk.Entry(form, textvariable=self.ncm_var, width=18)
        self.ncm_entry.grid(row=0, column=1, sticky="ew", padx=(6, 12))

        ttk.Label(form, text="Descrição").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.descricao_var).grid(row=0, column=3, columnspan=5, sticky="ew", padx=(6, 0))

        ttk.Label(form, text="UF origem").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(form, textvariable=self.uf_origem_var, values=UFS, state="readonly", width=8).grid(
            row=1, column=1, sticky="ew", padx=(6, 12), pady=(8, 0)
        )
        ttk.Label(form, text="UF destino").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Combobox(form, textvariable=self.uf_destino_var, values=UFS, state="readonly", width=8).grid(
            row=1, column=3, sticky="ew", padx=(6, 12), pady=(8, 0)
        )
        ttk.Label(form, text="Regime").grid(row=1, column=4, sticky="w", pady=(8, 0))
        ttk.Combobox(
            form,
            textvariable=self.regime_var,
            values=("Lucro Real", "Lucro Presumido", "Simples Nacional"),
            state="readonly",
        ).grid(row=1, column=5, sticky="ew", padx=(6, 12), pady=(8, 0))
        ttk.Label(form, text="Operação").grid(row=1, column=6, sticky="w", pady=(8, 0))
        ttk.Combobox(
            form,
            textvariable=self.operacao_var,
            values=("Venda", "Compra", "Devolução", "Transferência", "Remessa"),
            state="readonly",
        ).grid(row=1, column=7, sticky="ew", padx=(6, 0), pady=(8, 0))

        ttk.Label(form, text="Finalidade").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            form,
            textvariable=self.finalidade_var,
            values=("Revenda", "Uso/Consumo", "Ativo Imobilizado", "Industrialização"),
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", padx=(6, 12), pady=(8, 0))

        ttk.Label(form, text="Perfil remetente").grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Combobox(
            form,
            textvariable=self.perfil_var,
            values=("Comerciante", "Fabricante", "Importador", "Fabricante/Importador"),
            state="readonly",
        ).grid(row=2, column=3, sticky="ew", padx=(6, 12), pady=(8, 0))

        ttk.Label(form, text="Situação ICMS-ST").grid(row=2, column=4, sticky="w", pady=(8, 0))
        ttk.Combobox(
            form,
            textvariable=self.situacao_st_var,
            values=(
                "Não informado",
                "ICMS-ST já retido na entrada",
                "Responsável por reter ICMS-ST nesta saída",
                "Mercadoria sem retenção de ICMS-ST",
            ),
            state="readonly",
        ).grid(row=2, column=5, columnspan=2, sticky="ew", padx=(6, 12), pady=(8, 0))

        ttk.Checkbutton(form, text="Consumidor final", variable=self.consumidor_var).grid(
            row=2, column=7, sticky="w", pady=(8, 0)
        )
        ttk.Label(form, text="Destinatário ICMS").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            form,
            textvariable=self.destinatario_var,
            values=("Não informado", "Contribuinte", "Não contribuinte"),
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", padx=(6, 12), pady=(8, 0))

        ttk.Checkbutton(form, text="Mercadoria importada", variable=self.importada_var).grid(
            row=3, column=2, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(form, text="Exceção à alíquota de 4%", variable=self.excecao_4_var).grid(
            row=3, column=4, columnspan=2, sticky="w", pady=(8, 0)
        )

        ttk.Label(form, text="Empresa").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.combo_empresa = ttk.Combobox(
            form,
            textvariable=self.empresa_var,
            values=EmpresasRegimesService.listar_empresas(incluir_todas=True),
            state="readonly",
        )
        self.combo_empresa.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(6, 12), pady=(8, 0))
        self.combo_empresa.bind("<<ComboboxSelected>>", self._empresa_alterada)
        ttk.Label(
            form,
            textvariable=self.empresa_regime_info_var,
            foreground="#1F4E78",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=4, column=3, columnspan=5, sticky="w", pady=(8, 0))

        ttk.Label(
            form,
            text=(
                "Para ST, informe quem reteve/reterá o imposto. Em venda interestadual, informe também "
                "se o destinatário é contribuinte do ICMS para o robô decidir CFOP e DIFAL com segurança."
            ),
        ).grid(row=5, column=0, columnspan=8, sticky="w", pady=(7, 0))

        botoes = ttk.Frame(self, padding=(14, 0, 14, 6))
        botoes.grid(row=2, column=0, sticky="ew")
        ttk.Button(botoes, text="🧠 Analisar operação", command=self.analisar).pack(side="left")
        ttk.Button(botoes, text="Limpar", command=self.limpar).pack(side="left", padx=(7, 0))
        self.btn_salvar = ttk.Button(botoes, text="💾 Salvar relatório", command=self.salvar_relatorio, state="disabled")
        self.btn_salvar.pack(side="left", padx=(7, 0))
        ttk.Label(botoes, textvariable=self.status_var).pack(side="left", padx=(16, 0))

        quadro = ttk.LabelFrame(self, text="Diagnóstico do robô", padding=7)
        quadro.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 7))
        quadro.grid_columnconfigure(0, weight=1)
        colunas = ("tributo", "status", "confianca", "resumo")
        self.tabela = ttk.Treeview(quadro, columns=colunas, show="headings", height=7)
        self.tabela.heading("tributo", text="Tributo")
        self.tabela.heading("status", text="Status")
        self.tabela.heading("confianca", text="Segurança")
        self.tabela.heading("resumo", text="Resumo")
        self.tabela.column("tributo", width=120, anchor="w", stretch=False)
        self.tabela.column("status", width=110, anchor="center", stretch=False)
        self.tabela.column("confianca", width=90, anchor="center", stretch=False)
        self.tabela.column("resumo", width=760, anchor="w")
        barra_h = ttk.Scrollbar(quadro, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(xscrollcommand=barra_h.set)
        self.tabela.grid(row=0, column=0, sticky="ew")
        barra_h.grid(row=1, column=0, sticky="ew")

        decisao_frame = ttk.LabelFrame(self, text="Decisão da operação — Sprint 17.5.2", padding=8)
        decisao_frame.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 7))
        for c in range(6):
            decisao_frame.grid_columnconfigure(c, weight=1)

        campos = (
            ("CFOP provável", self.decisao_cfop_var),
            ("ICMS", self.decisao_icms_var),
            ("Destaque ICMS", self.decisao_destaque_var),
            ("PIS", self.decisao_pis_var),
            ("COFINS", self.decisao_cofins_var),
            ("DIFAL/FCP", self.decisao_difal_var),
        )
        for coluna, (titulo, variavel) in enumerate(campos):
            ttk.Label(decisao_frame, text=titulo, font=("Segoe UI", 9, "bold")).grid(
                row=0, column=coluna, sticky="w", padx=(0, 8)
            )
            ttk.Label(decisao_frame, textvariable=variavel).grid(
                row=1, column=coluna, sticky="w", padx=(0, 8), pady=(2, 0)
            )
        ttk.Label(decisao_frame, textvariable=self.decisao_status_var).grid(
            row=2, column=0, columnspan=6, sticky="w", pady=(6, 0)
        )

        relatorio_frame = ttk.LabelFrame(self, text="Parecer explicável", padding=7)
        relatorio_frame.grid(row=5, column=0, sticky="nsew", padx=14, pady=(0, 14))
        relatorio_frame.grid_rowconfigure(0, weight=1)
        relatorio_frame.grid_columnconfigure(0, weight=1)
        self.relatorio = tk.Text(relatorio_frame, wrap=tk.WORD, font=("Consolas", 9), padx=8, pady=8)
        barra = ttk.Scrollbar(relatorio_frame, orient="vertical", command=self.relatorio.yview)
        self.relatorio.configure(yscrollcommand=barra.set)
        self.relatorio.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.relatorio.insert(
            tk.END,
            "O robô é assistivo: confirma somente o que os motores e bases instaladas conseguem sustentar.\n",
        )

    def _empresa_alterada(self, _evento=None) -> None:
        empresa = self.empresa_var.get().strip()
        perfil = EmpresasRegimesService.obter_perfil(empresa)
        if perfil is not None:
            self.regime_var.set(perfil.regime.title())
        self.empresa_regime_info_var.set(
            EmpresasRegimesService.descricao_regime(empresa, self.regime_var.get())
        )

    def _consulta(self) -> ConsultaTributaria:
        return ConsultaTributaria(
            ncm=self.ncm_var.get().strip(),
            descricao_produto=self.descricao_var.get().strip(),
            uf_origem=self.uf_origem_var.get().strip(),
            uf_destino=self.uf_destino_var.get().strip(),
            regime=EmpresasRegimesService.resolver_regime(self.empresa_var.get(), self.regime_var.get()),
            operacao=self.operacao_var.get().strip(),
            empresa="" if self.empresa_var.get().strip() == "Todas as empresas" else self.empresa_var.get().strip(),
            finalidade=self.finalidade_var.get().strip(),
            perfil_remetente=self.perfil_var.get().strip(),
            situacao_icms_st=self.situacao_st_var.get().strip(),
            destinatario_contribuinte=self._destinatario_contribuinte(),
            consumidor_final=bool(self.consumidor_var.get()),
            mercadoria_importada=bool(self.importada_var.get()),
            excecao_aliquota_importacao=bool(self.excecao_4_var.get()),
        )

    def _destinatario_contribuinte(self):
        valor = self.destinatario_var.get().strip().lower()
        if valor == "contribuinte":
            return True
        if valor == "não contribuinte":
            return False
        return None

    def analisar(self):
        try:
            resultado = RoboTributarioService.analisar(self._consulta())
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            return

        self.resultado_atual = resultado
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        for diagnostico in resultado.diagnosticos:
            self.tabela.insert(
                "",
                "end",
                values=(
                    diagnostico.tributo,
                    diagnostico.status,
                    f"{diagnostico.confiabilidade:.0f}%" if diagnostico.confiabilidade else "-",
                    diagnostico.resumo,
                ),
            )

        decisao = resultado.decisao_operacao
        if decisao is not None:
            self.decisao_cfop_var.set(
                f"{decisao.cfop.valor or '-'} • {decisao.cfop.status}"
            )
            self.decisao_icms_var.set(
                f"{decisao.icms.valor or '-'} • {decisao.icms.status}"
            )
            self.decisao_destaque_var.set(
                f"{decisao.destaque_icms.valor or '-'} • {decisao.destaque_icms.status}"
            )
            self.decisao_pis_var.set(
                f"{decisao.pis.valor or '-'} • {decisao.pis.status}"
            )
            self.decisao_cofins_var.set(
                f"{decisao.cofins.valor or '-'} • {decisao.cofins.status}"
            )
            self.decisao_difal_var.set(
                f"{decisao.difal.valor or '-'} • {decisao.difal.status}"
            )
            self.decisao_status_var.set(
                f"Decisão: {decisao.status} • segurança {decisao.confiabilidade:.0f}%"
            )
        else:
            self._limpar_decisao()

        self.relatorio.delete("1.0", tk.END)
        self.relatorio.insert(tk.END, resultado.relatorio)
        self.btn_salvar.config(state="normal")
        self.status_var.set(
            f"Status: {resultado.status} • segurança conservadora {resultado.confiabilidade:.0f}%"
        )

    def _limpar_decisao(self):
        self.decisao_cfop_var.set("-")
        self.decisao_icms_var.set("-")
        self.decisao_destaque_var.set("-")
        self.decisao_pis_var.set("-")
        self.decisao_cofins_var.set("-")
        self.decisao_difal_var.set("-")
        self.decisao_status_var.set("Decisão: aguardando análise")

    def limpar(self):
        self.resultado_atual = None
        self.ncm_var.set("")
        self.descricao_var.set("")
        self.empresa_var.set("Todas as empresas")
        self.empresa_regime_info_var.set("Selecione uma empresa para definir o regime automaticamente.")
        self.uf_origem_var.set("MG")
        self.uf_destino_var.set("MG")
        self.regime_var.set("Lucro Real")
        self.operacao_var.set("Venda")
        self.finalidade_var.set("Revenda")
        self.perfil_var.set("Comerciante")
        self.situacao_st_var.set("Não informado")
        self.destinatario_var.set("Não informado")
        self.consumidor_var.set(False)
        self.importada_var.set(False)
        self.excecao_4_var.set(False)
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        self.relatorio.delete("1.0", tk.END)
        self._limpar_decisao()
        self.status_var.set("Informe a operação e clique em Analisar operação.")
        self.btn_salvar.config(state="disabled")
        self.ncm_entry.focus_set()

    def salvar_relatorio(self):
        if self.resultado_atual is None:
            return
        ncm = "".join(c for c in self.ncm_var.get() if c.isdigit()) or "NCM"
        caminho = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar relatório do Robô Tributário",
            defaultextension=".txt",
            initialfile=f"ROBO_TRIBUTARIO_{ncm}.txt",
            filetypes=(("Arquivo de texto", "*.txt"), ("Todos os arquivos", "*.*")),
        )
        if not caminho:
            return
        Path(caminho).write_text(self.resultado_atual.relatorio, encoding="utf-8")
        self.status_var.set(f"Relatório salvo em {caminho}")
