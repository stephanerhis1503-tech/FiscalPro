"""Tela de análise nacional de PIS/Pasep e Cofins — Sprint 16.5."""

from __future__ import annotations

from datetime import date
import tkinter as tk
from tkinter import messagebox, ttk

from src.services.piscofins_nacional_service import PISCOFINSNacionalService
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.ui.layout_responsivo import dimensionar_janela


class JanelaPISCOFINSNacional(tk.Toplevel):
    def __init__(self, master=None, ncm: str = "", descricao: str = "", empresa: str = "", regime: str = ""):
        super().__init__(master)
        self.title("Base Nacional de PIS/COFINS")
        dimensionar_janela(self, 900, 720, 720, 560)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        formulario = ttk.LabelFrame(
            self,
            text="Contexto da operação",
            padding=12,
        )
        formulario.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        formulario.grid_columnconfigure(1, weight=1)
        formulario.grid_columnconfigure(3, weight=1)

        ttk.Label(formulario, text="NCM").grid(row=0, column=0, sticky="w")
        self.var_ncm = tk.StringVar(value=ncm)
        ttk.Entry(formulario, textvariable=self.var_ncm, width=22).grid(
            row=0, column=1, sticky="ew", padx=(8, 16)
        )

        ttk.Label(formulario, text="EX TIPI").grid(row=0, column=2, sticky="w")
        self.var_ex = tk.StringVar()
        ttk.Entry(formulario, textvariable=self.var_ex, width=12).grid(
            row=0, column=3, sticky="ew", padx=(8, 0)
        )

        ttk.Label(formulario, text="Descrição do produto").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        self.var_descricao = tk.StringVar(value=descricao)
        ttk.Entry(formulario, textvariable=self.var_descricao).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        self.var_empresa = tk.StringVar(value=empresa or "Todas as empresas")
        regime_inicial = EmpresasRegimesService.resolver_regime(empresa, regime or "Lucro Real") or "Lucro Real"
        self.var_empresa_info = tk.StringVar(value=EmpresasRegimesService.descricao_regime(empresa, regime_inicial))

        ttk.Label(formulario, text="Regime").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        self.var_regime = tk.StringVar(value=regime_inicial.title())
        ttk.Combobox(
            formulario,
            textvariable=self.var_regime,
            state="readonly",
            values=("Lucro Real", "Lucro Presumido", "Simples Nacional"),
        ).grid(row=2, column=1, sticky="ew", padx=(8, 16), pady=(8, 0))

        ttk.Label(formulario, text="Operação").grid(
            row=2, column=2, sticky="w", pady=(8, 0)
        )
        self.var_operacao = tk.StringVar(value="Venda")
        ttk.Combobox(
            formulario,
            textvariable=self.var_operacao,
            state="readonly",
            values=("Venda", "Revenda", "Entrada", "Devolução", "Exportação"),
        ).grid(row=2, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(formulario, text="Finalidade").grid(
            row=3, column=0, sticky="w", pady=(8, 0)
        )
        self.var_finalidade = tk.StringVar(value="Revenda")
        ttk.Combobox(
            formulario,
            textvariable=self.var_finalidade,
            state="readonly",
            values=("Revenda", "Industrialização", "Uso e consumo", "Ativo imobilizado"),
        ).grid(row=3, column=1, sticky="ew", padx=(8, 16), pady=(8, 0))

        ttk.Label(formulario, text="Data da operação").grid(
            row=3, column=2, sticky="w", pady=(8, 0)
        )
        self.var_data = tk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        ttk.Entry(formulario, textvariable=self.var_data).grid(
            row=3, column=3, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        ttk.Label(formulario, text="Empresa").grid(
            row=4, column=0, sticky="w", pady=(8, 0)
        )
        self.combo_empresa = ttk.Combobox(
            formulario,
            textvariable=self.var_empresa,
            state="readonly",
            values=EmpresasRegimesService.listar_empresas(incluir_todas=True),
        )
        self.combo_empresa.grid(row=4, column=1, sticky="ew", padx=(8, 16), pady=(8, 0))
        self.combo_empresa.bind("<<ComboboxSelected>>", self._empresa_alterada)
        ttk.Label(
            formulario,
            textvariable=self.var_empresa_info,
            foreground="#1F4E78",
            font=("Segoe UI", 9, "bold"),
            wraplength=400,
        ).grid(row=4, column=2, columnspan=2, sticky="w", pady=(8, 0))

        acoes = ttk.Frame(self)
        acoes.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        acoes.grid_columnconfigure(0, weight=1)
        acoes.grid_columnconfigure(1, weight=1)
        ttk.Button(acoes, text="Analisar PIS/COFINS", command=self.analisar).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(acoes, text="Fechar", command=self.destroy).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )

        quadro = ttk.LabelFrame(self, text="Resultado rastreável", padding=8)
        quadro.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        quadro.grid_rowconfigure(0, weight=1)
        quadro.grid_columnconfigure(0, weight=1)

        self.resultado = tk.Text(
            quadro,
            wrap=tk.WORD,
            font=("Consolas", 10),
            padx=10,
            pady=10,
        )
        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.resultado.yview)
        self.resultado.configure(yscrollcommand=barra.set)
        self.resultado.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")

        if ncm:
            self.after(100, self.analisar)

    def _empresa_alterada(self, _evento=None) -> None:
        empresa = self.var_empresa.get().strip()
        perfil = EmpresasRegimesService.obter_perfil(empresa)
        if perfil is not None:
            self.var_regime.set(perfil.regime.title())
        self.var_empresa_info.set(
            EmpresasRegimesService.descricao_regime(empresa, self.var_regime.get())
        )

    @staticmethod
    def _percentual(valor) -> str:
        return f"{float(valor or 0):.2f}%".replace(".", ",")

    def analisar(self):
        ncm = self.var_ncm.get().strip()
        if not ncm:
            messagebox.showwarning("FiscalPro", "Informe o NCM.")
            return

        try:
            resultado = PISCOFINSNacionalService.analisar(
                ncm,
                contexto={
                    "empresa": "" if self.var_empresa.get().strip() == "Todas as empresas" else self.var_empresa.get().strip(),
                    "regime": EmpresasRegimesService.resolver_regime(self.var_empresa.get(), self.var_regime.get()),
                    "operacao": self.var_operacao.get(),
                    "finalidade": self.var_finalidade.get(),
                    "data_operacao": self.var_data.get(),
                },
                descricao=self.var_descricao.get(),
                ex_tipi=self.var_ex.get(),
            )
        except ValueError as exc:
            messagebox.showwarning("FiscalPro", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("FiscalPro", f"Não foi possível analisar: {exc}")
            return

        confirmado = "SIM" if resultado.get("confirmado") else "NÃO"
        linhas = [
            "==============================================",
            "BASE NACIONAL DE PIS/COFINS — SPRINT 16.5",
            "==============================================",
            f"NCM: {resultado.get('ncm', '')}",
            f"Status: {resultado.get('status', '')}",
            f"Enquadramento: {resultado.get('enquadramento', '')}",
            f"Confirmado automaticamente: {confirmado}",
            f"Confiança da regra: {self._percentual(resultado.get('confiabilidade'))}",
            "",
        ]

        if resultado.get("confirmado"):
            linhas.extend(
                [
                    "TRIBUTAÇÃO CONFIRMADA",
                    "----------------------",
                    f"CST PIS: {resultado.get('cst_pis') or '-'}",
                    f"Alíquota PIS: {self._percentual(resultado.get('aliquota_pis'))}",
                    f"CST COFINS: {resultado.get('cst_cofins') or '-'}",
                    f"Alíquota COFINS: {self._percentual(resultado.get('aliquota_cofins'))}",
                    "",
                ]
            )
        elif resultado.get("sugestao_cst_pis") or resultado.get("sugestao_cst_cofins"):
            linhas.extend(
                [
                    "SUGESTÃO CONDICIONAL — NÃO GRAVADA",
                    "-----------------------------------",
                    f"CST PIS sugerido: {resultado.get('sugestao_cst_pis') or '-'}",
                    f"Alíquota PIS sugerida: {self._percentual(resultado.get('sugestao_aliquota_pis'))}",
                    f"CST COFINS sugerido: {resultado.get('sugestao_cst_cofins') or '-'}",
                    f"Alíquota COFINS sugerida: {self._percentual(resultado.get('sugestao_aliquota_cofins'))}",
                    "",
                ]
            )

        linhas.extend(
            [
                "BASE LEGAL E RASTREABILIDADE",
                "-----------------------------",
                f"Fundamento: {resultado.get('fundamento') or '-'}",
                f"Dispositivo: {resultado.get('artigo') or '-'}",
                f"Tabela EFD: {resultado.get('tabela_efd') or '-'}",
                f"Fonte: {resultado.get('fonte_url') or '-'}",
                "",
                "OBSERVAÇÃO",
                "----------",
                resultado.get("observacao") or "-",
                "",
                "O FiscalPro só grava automaticamente conclusões confirmadas. Sugestões",
                "condicionais exigem conferência da descrição, operação e legislação vigente.",
            ]
        )

        self.resultado.delete("1.0", tk.END)
        self.resultado.insert(tk.END, "\n".join(linhas))
