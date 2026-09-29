"""Tela do Motor DIFAL/FCP Nacional — integrada ao ICMS por UF na Sprint 17.0."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from src.services.difal_fcp_nacional_service import DIFALFCPNacionalService
from src.ui.layout_responsivo import dimensionar_janela


UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
)


class JanelaDIFALFCP(tk.Toplevel):
    def __init__(
        self,
        master=None,
        ncm: str = "",
        descricao: str = "",
        uf_origem: str = "MG",
        uf_destino: str = "ES",
    ):
        super().__init__(master)
        self.title("DIFAL/FCP Nacional — Aplicabilidade e memória de cálculo")
        dimensionar_janela(self, 1040, 850, 820, 640)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        contexto = ttk.LabelFrame(self, text="Contexto da operação", padding=12)
        contexto.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        for coluna in (1, 3, 5):
            contexto.grid_columnconfigure(coluna, weight=1)

        ttk.Label(contexto, text="NCM").grid(row=0, column=0, sticky="w")
        self.var_ncm = tk.StringVar(value=ncm)
        ttk.Entry(contexto, textvariable=self.var_ncm, width=18).grid(
            row=0, column=1, sticky="ew", padx=(7, 14)
        )

        ttk.Label(contexto, text="UF origem").grid(row=0, column=2, sticky="w")
        self.var_origem = tk.StringVar(value=uf_origem or "MG")
        ttk.Combobox(
            contexto, textvariable=self.var_origem, values=UFS, state="readonly", width=7
        ).grid(row=0, column=3, sticky="ew", padx=(7, 14))

        ttk.Label(contexto, text="UF destino").grid(row=0, column=4, sticky="w")
        self.var_destino = tk.StringVar(value=uf_destino or "ES")
        ttk.Combobox(
            contexto, textvariable=self.var_destino, values=UFS, state="readonly", width=7
        ).grid(row=0, column=5, sticky="ew", padx=(7, 0))

        ttk.Label(contexto, text="Descrição do produto").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        self.var_descricao = tk.StringVar(value=descricao)
        ttk.Entry(contexto, textvariable=self.var_descricao).grid(
            row=1, column=1, columnspan=5, sticky="ew", padx=(7, 0), pady=(8, 0)
        )

        ttk.Label(contexto, text="Operação").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.var_operacao = tk.StringVar(value="Venda")
        ttk.Combobox(
            contexto,
            textvariable=self.var_operacao,
            state="readonly",
            values=("Venda", "Saída", "Revenda", "Entrada", "Devolução", "Transferência", "Remessa"),
        ).grid(row=2, column=1, sticky="ew", padx=(7, 14), pady=(8, 0))

        ttk.Label(contexto, text="Regime do remetente").grid(
            row=2, column=2, sticky="w", pady=(8, 0)
        )
        self.var_regime = tk.StringVar(value="Lucro Real")
        ttk.Combobox(
            contexto,
            textvariable=self.var_regime,
            state="readonly",
            values=("Lucro Real", "Lucro Presumido", "Simples Nacional", "MEI", "Outro"),
        ).grid(row=2, column=3, sticky="ew", padx=(7, 14), pady=(8, 0))

        ttk.Label(contexto, text="Destinatário").grid(
            row=2, column=4, sticky="w", pady=(8, 0)
        )
        self.var_contribuinte = tk.StringVar(value="Não contribuinte")
        ttk.Combobox(
            contexto,
            textvariable=self.var_contribuinte,
            state="readonly",
            values=("Não contribuinte", "Contribuinte", "Não informado"),
        ).grid(row=2, column=5, sticky="ew", padx=(7, 0), pady=(8, 0))

        opcoes = ttk.Frame(contexto)
        opcoes.grid(row=3, column=0, columnspan=6, sticky="w", pady=(9, 0))
        self.var_consumidor_final = tk.BooleanVar(value=True)
        self.var_importada = tk.BooleanVar(value=False)
        self.var_excecao_importada = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opcoes, text="Consumidor final", variable=self.var_consumidor_final
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            opcoes,
            text="Mercadoria importada / conteúdo de importação > 40%",
            variable=self.var_importada,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            opcoes,
            text="Exceção legal à alíquota de 4%",
            variable=self.var_excecao_importada,
        ).pack(side=tk.LEFT, padx=(12, 0))

        calculo = ttk.LabelFrame(self, text="Premissas da memória de cálculo", padding=12)
        calculo.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        for coluna in (1, 3, 5):
            calculo.grid_columnconfigure(coluna, weight=1)

        ttk.Label(calculo, text="Valor da operação").grid(row=0, column=0, sticky="w")
        self.var_valor = tk.StringVar(value="")
        ttk.Entry(calculo, textvariable=self.var_valor).grid(
            row=0, column=1, sticky="ew", padx=(7, 14)
        )

        ttk.Label(calculo, text="Alíquota interna destino").grid(row=0, column=2, sticky="w")
        self.var_aliquota_interna = tk.StringVar(value="")
        ttk.Entry(calculo, textvariable=self.var_aliquota_interna).grid(
            row=0, column=3, sticky="ew", padx=(7, 14)
        )

        ttk.Label(calculo, text="FCP destino").grid(row=0, column=4, sticky="w")
        self.var_fcp = tk.StringVar(value="")
        ttk.Entry(calculo, textvariable=self.var_fcp).grid(
            row=0, column=5, sticky="ew", padx=(7, 0)
        )

        ttk.Label(calculo, text="Modalidade").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.var_modalidade = tk.StringVar(value="Automática")
        ttk.Combobox(
            calculo,
            textvariable=self.var_modalidade,
            state="readonly",
            values=("Automática", "Base única por dentro", "Base dupla por dentro", "Por fora"),
        ).grid(row=1, column=1, sticky="ew", padx=(7, 14), pady=(8, 0))

        self.var_valor_inclui = tk.BooleanVar(value=True)
        self.var_confirmar_interna = tk.BooleanVar(value=False)
        self.var_confirmar_fcp = tk.BooleanVar(value=False)
        self.var_usar_referencia = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            calculo,
            text="Valor informado já inclui ICMS",
            variable=self.var_valor_inclui,
        ).grid(row=1, column=2, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            calculo,
            text="Confirmo a alíquota interna informada",
            variable=self.var_confirmar_interna,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            calculo,
            text="Confirmo o FCP informado",
            variable=self.var_confirmar_fcp,
        ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            calculo,
            text="Usar motor ICMS por UF; tabela local somente como alternativa",
            variable=self.var_usar_referencia,
        ).grid(row=2, column=4, columnspan=2, sticky="w", pady=(8, 0))

        acoes = ttk.Frame(self)
        acoes.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))
        for coluna in range(2):
            acoes.grid_columnconfigure(coluna, weight=1, uniform="difal")
        ttk.Button(acoes, text="Analisar e calcular DIFAL/FCP", command=self.analisar).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(acoes, text="Fechar", command=self.destroy).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )

        self.status = ttk.Label(
            self,
            text=(
                "O FiscalPro só confirma o DIFAL quando a condição do destinatário e as alíquotas "
                "necessárias estiverem confirmadas."
            ),
            anchor="w",
            wraplength=980,
        )
        self.status.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 7))

        quadro = ttk.LabelFrame(self, text="Resultado rastreável", padding=8)
        quadro.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 14))
        quadro.grid_rowconfigure(0, weight=1)
        quadro.grid_columnconfigure(0, weight=1)
        self.resultado = tk.Text(
            quadro, wrap=tk.WORD, font=("Consolas", 10), padx=10, pady=10
        )
        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.resultado.yview)
        self.resultado.configure(yscrollcommand=barra.set)
        self.resultado.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")

    @staticmethod
    def _percentual(valor) -> str:
        if valor is None:
            return "-"
        return f"{float(valor):.2f}%".replace(".", ",")

    @staticmethod
    def _moeda(valor) -> str:
        if valor is None:
            return "-"
        texto = f"{float(valor):,.2f}"
        return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")

    def _contribuinte(self):
        texto = self.var_contribuinte.get().strip().lower()
        if texto == "contribuinte":
            return True
        if texto == "não contribuinte":
            return False
        return None

    def _modalidade(self) -> str:
        texto = self.var_modalidade.get().strip().upper()
        return {
            "AUTOMÁTICA": "AUTO",
            "BASE ÚNICA POR DENTRO": "BASE UNICA POR DENTRO",
            "BASE DUPLA POR DENTRO": "BASE DUPLA POR DENTRO",
            "POR FORA": "POR FORA",
        }.get(texto, "AUTO")

    def analisar(self):
        try:
            resultado = DIFALFCPNacionalService.analisar(
                self.var_ncm.get().strip(),
                descricao=self.var_descricao.get().strip(),
                contexto={
                    "uf_origem": self.var_origem.get(),
                    "uf_destino": self.var_destino.get(),
                    "operacao": self.var_operacao.get(),
                    "regime": self.var_regime.get(),
                    "consumidor_final": self.var_consumidor_final.get(),
                    "destinatario_contribuinte": self._contribuinte(),
                    "mercadoria_importada": self.var_importada.get(),
                    "excecao_aliquota_importacao": self.var_excecao_importada.get(),
                    "valor_operacao": self.var_valor.get().strip(),
                    "valor_inclui_icms": self.var_valor_inclui.get(),
                    "aliquota_interna_destino": self.var_aliquota_interna.get().strip(),
                    "confirmar_aliquota_interna": self.var_confirmar_interna.get(),
                    "aliquota_fcp": self.var_fcp.get().strip(),
                    "confirmar_fcp": self.var_confirmar_fcp.get(),
                    "usar_motor_icms_uf": self.var_usar_referencia.get(),
                    "usar_tabela_referencia": self.var_usar_referencia.get(),
                    "modalidade_calculo": self._modalidade(),
                },
            )
        except ValueError as exc:
            messagebox.showwarning("FiscalPro", str(exc), parent=self)
            return
        except Exception as exc:
            messagebox.showerror(
                "FiscalPro", f"Não foi possível analisar o DIFAL/FCP: {exc}", parent=self
            )
            return

        linhas = [
            "============================================================",
            "MOTOR DIFAL/FCP NACIONAL — SPRINT 17.0",
            "============================================================",
            f"NCM: {resultado.get('ncm') or '-'}",
            f"Operação: {resultado.get('uf_origem') or '-'} → {resultado.get('uf_destino') or '-'}",
            f"Status: {resultado.get('status') or '-'}",
            f"Aplicável: {'SIM' if resultado.get('aplicavel') else 'NÃO'}",
            f"Confirmado: {'SIM' if resultado.get('confirmado') else 'NÃO'}",
            f"Segurança: {self._percentual(resultado.get('confiabilidade'))}",
            f"Motivo: {resultado.get('motivo') or '-'}",
            f"Responsável: {resultado.get('responsavel') or '-'}",
            "",
            "ALÍQUOTAS",
            "---------",
            f"Interestadual: {self._percentual(resultado.get('aliquota_interestadual'))}",
            f"Status interestadual: {resultado.get('aliquota_interestadual_status') or '-'}",
            f"Interna destino: {self._percentual(resultado.get('aliquota_interna_destino'))}",
            f"Status interna: {resultado.get('aliquota_interna_status') or '-'}",
            f"Diferencial nominal: {self._percentual(resultado.get('diferencial_percentual'))}",
            f"FCP: {self._percentual(resultado.get('aliquota_fcp'))}",
            f"Status FCP: {resultado.get('fcp_status') or '-'}",
            "",
            "MEMÓRIA DE CÁLCULO",
            "-------------------",
            f"Valor informado: {self._moeda(resultado.get('valor_operacao'))}",
            f"Valor já inclui ICMS: {'SIM' if resultado.get('valor_inclui_icms') else 'NÃO'}",
            f"Modalidade: {resultado.get('modalidade_calculo') or '-'}",
            f"Base origem: {self._moeda(resultado.get('base_origem'))}",
            f"Base destino: {self._moeda(resultado.get('base_destino'))}",
            f"ICMS origem: {self._moeda(resultado.get('valor_icms_origem'))}",
            f"ICMS destino: {self._moeda(resultado.get('valor_icms_destino'))}",
            f"DIFAL: {self._moeda(resultado.get('valor_difal'))}",
            f"FCP destino: {self._moeda(resultado.get('valor_fcp'))}",
            "",
            "FUNDAMENTO E ALERTAS",
            "---------------------",
            resultado.get("fundamento") or "-",
            resultado.get("observacao") or "-",
            "",
            "Fontes:",
            resultado.get("fontes") or "-",
            "",
            "O resultado é apoio fiscal. Benefícios, reduções e regras especiais da UF de destino devem ser conferidos.",
        ]
        self.resultado.delete("1.0", tk.END)
        self.resultado.insert(tk.END, "\n".join(linhas))
        self.status.configure(
            text=(
                "DIFAL confirmado com premissas completas."
                if resultado.get("confirmado")
                else "Resultado condicional: confira os itens indicados no campo de alertas."
            )
        )


__all__ = ["JanelaDIFALFCP"]
