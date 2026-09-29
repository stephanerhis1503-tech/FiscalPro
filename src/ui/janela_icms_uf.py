"""Tela do Motor ICMS por UF — Sprint 17.1.0.

A primeira fase cobre MG, ES, BA, RJ e SP. Para as UFs fora de MG, o motor
separa a alíquota da operação, a referência interna, o FCP/FECOP e a regra
estadual de ST. Para autopeças, exibe MVA original/ajustada, vigência e
responsabilidade em SP, ES, BA e RJ.
"""

from __future__ import annotations

from datetime import date
import tkinter as tk
from tkinter import messagebox, ttk

from src.services.icms_uf_service import ICMSUFService, UFS_COBERTURA
from src.ui.janela_difal_fcp import JanelaDIFALFCP
from src.ui.janela_icms_mg import JanelaICMSMG
from src.ui.layout_responsivo import dimensionar_janela


UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
)


class JanelaICMSUF(tk.Toplevel):
    def __init__(
        self,
        master=None,
        ncm: str = "",
        descricao: str = "",
        uf_origem: str = "MG",
        uf_destino: str = "MG",
    ):
        super().__init__(master)
        self.title("ICMS por UF — alíquota, FCP e ICMS-ST detalhado")
        dimensionar_janela(self, 1040, 820, 800, 600)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        formulario = ttk.LabelFrame(self, text="Contexto da operação", padding=12)
        formulario.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        for coluna in (1, 3, 5):
            formulario.grid_columnconfigure(coluna, weight=1)

        ttk.Label(formulario, text="NCM").grid(row=0, column=0, sticky="w")
        self.var_ncm = tk.StringVar(value=ncm)
        ttk.Entry(formulario, textvariable=self.var_ncm, width=18).grid(
            row=0, column=1, sticky="ew", padx=(7, 14)
        )

        ttk.Label(formulario, text="UF origem").grid(row=0, column=2, sticky="w")
        self.var_origem = tk.StringVar(value=(uf_origem or "MG").upper())
        ttk.Combobox(
            formulario, textvariable=self.var_origem, values=UFS,
            state="readonly", width=7,
        ).grid(row=0, column=3, sticky="ew", padx=(7, 14))

        ttk.Label(formulario, text="UF destino").grid(row=0, column=4, sticky="w")
        self.var_destino = tk.StringVar(value=(uf_destino or "MG").upper())
        combo_destino = ttk.Combobox(
            formulario, textvariable=self.var_destino, values=UFS,
            state="readonly", width=7,
        )
        combo_destino.grid(row=0, column=5, sticky="ew", padx=(7, 0))
        combo_destino.bind("<<ComboboxSelected>>", lambda _e: self._atualizar_status_cobertura())

        ttk.Label(formulario, text="Descrição do produto").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        self.var_descricao = tk.StringVar(value=descricao)
        ttk.Entry(formulario, textvariable=self.var_descricao).grid(
            row=1, column=1, columnspan=5, sticky="ew", padx=(7, 0), pady=(8, 0)
        )

        ttk.Label(formulario, text="Operação").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        self.var_operacao = tk.StringVar(value="Venda")
        ttk.Combobox(
            formulario,
            textvariable=self.var_operacao,
            state="readonly",
            values=("Venda", "Revenda", "Entrada", "Devolução", "Transferência", "Remessa"),
        ).grid(row=2, column=1, sticky="ew", padx=(7, 14), pady=(8, 0))

        ttk.Label(formulario, text="Data da operação").grid(
            row=2, column=2, sticky="w", pady=(8, 0)
        )
        self.var_data = tk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        ttk.Entry(formulario, textvariable=self.var_data).grid(
            row=2, column=3, sticky="ew", padx=(7, 14), pady=(8, 0)
        )

        opcoes = ttk.Frame(formulario)
        opcoes.grid(row=2, column=4, columnspan=2, sticky="w", pady=(8, 0))
        self.var_consumidor_final = tk.BooleanVar(value=False)
        self.var_importada = tk.BooleanVar(value=False)
        self.var_excecao_importada = tk.BooleanVar(value=False)
        self.var_fidelidade = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opcoes, text="Consumidor final", variable=self.var_consumidor_final
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            opcoes, text="Importada / conteúdo > 40%", variable=self.var_importada
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            opcoes, text="Contrato de fidelidade", variable=self.var_fidelidade
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            formulario,
            text="Exceção legal à alíquota interestadual de 4%",
            variable=self.var_excecao_importada,
        ).grid(row=3, column=0, columnspan=6, sticky="w", pady=(8, 0))

        acoes = ttk.Frame(self)
        acoes.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        for coluna in range(4):
            acoes.grid_columnconfigure(coluna, weight=1, uniform="icmsuf")
        ttk.Button(acoes, text="Analisar ICMS por UF", command=self.analisar).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(acoes, text="Abrir motor detalhado MG", command=self.abrir_mg).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )
        ttk.Button(acoes, text="Calcular DIFAL/FCP", command=self.abrir_difal).grid(
            row=0, column=2, sticky="ew", padx=(8, 0)
        )
        ttk.Button(acoes, text="Fechar", command=self.destroy).grid(
            row=0, column=3, sticky="ew", padx=(8, 0)
        )

        self.status = ttk.Label(self, anchor="w", wraplength=1000)
        self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 7))
        self._atualizar_status_cobertura()

        quadro = ttk.LabelFrame(self, text="Resultado rastreável", padding=8)
        quadro.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 14))
        quadro.grid_rowconfigure(0, weight=1)
        quadro.grid_columnconfigure(0, weight=1)
        self.resultado = tk.Text(
            quadro, wrap=tk.WORD, font=("Consolas", 10), padx=10, pady=10
        )
        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.resultado.yview)
        self.resultado.configure(yscrollcommand=barra.set)
        self.resultado.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")

        if ncm:
            self.after(120, self.analisar)

    @staticmethod
    def _percentual(valor) -> str:
        if valor is None:
            return "-"
        return f"{float(valor):.2f}%".replace(".", ",")

    def _atualizar_status_cobertura(self):
        destino = self.var_destino.get().strip().upper()
        if destino in UFS_COBERTURA:
            self.status.configure(
                text=(
                    f"Cobertura ativa para {destino}. A Sprint 17.1 detalha ICMS-ST de autopeças, "
                    "MVA, vigência e responsabilidade. Regras condicionais continuam marcadas para revisão."
                )
            )
        else:
            self.status.configure(
                text=(
                    f"{destino} ainda não está coberto nesta fase. UFs disponíveis: "
                    + ", ".join(UFS_COBERTURA)
                    + "."
                )
            )

    def _contexto(self):
        return {
            "uf_origem": self.var_origem.get(),
            "uf_destino": self.var_destino.get(),
            "operacao": self.var_operacao.get(),
            "consumidor_final": self.var_consumidor_final.get(),
            "mercadoria_importada": self.var_importada.get(),
            "excecao_aliquota_importacao": self.var_excecao_importada.get(),
            "contrato_fidelidade": self.var_fidelidade.get(),
            "data_operacao": self.var_data.get(),
        }

    def analisar(self):
        try:
            resultado = ICMSUFService.analisar(
                self.var_ncm.get().strip(),
                contexto=self._contexto(),
                descricao=self.var_descricao.get().strip(),
            )
        except ValueError as exc:
            messagebox.showwarning("FiscalPro", str(exc), parent=self)
            return
        except Exception as exc:
            messagebox.showerror(
                "FiscalPro", f"Não foi possível analisar o ICMS por UF: {exc}", parent=self
            )
            return

        linhas = [
            "============================================================",
            "MOTOR ICMS POR UF — SPRINT 17.1",
            "============================================================",
            f"NCM: {resultado.get('ncm') or '-'}",
            f"Operação: {resultado.get('uf_origem') or '-'} → {resultado.get('uf_destino') or '-'}",
            f"Data: {resultado.get('data_operacao') or '-'}",
            f"Tipo: {resultado.get('tipo_operacao') or '-'}",
            f"Status geral: {resultado.get('status') or '-'}",
            f"Exige revisão: {'SIM' if resultado.get('exige_revisao') else 'NÃO'}",
            "",
            "ALÍQUOTA DA OPERAÇÃO",
            "---------------------",
            f"Alíquota: {self._percentual(resultado.get('aliquota_operacao'))}",
            f"Status: {resultado.get('aliquota_operacao_status') or '-'}",
            f"Confirmada: {'SIM' if resultado.get('aliquota_operacao_confirmada') else 'NÃO'}",
            "",
            "ALÍQUOTA INTERNA DO DESTINO",
            "---------------------------",
            f"Alíquota interna: {self._percentual(resultado.get('aliquota_interna_destino'))}",
            f"Status: {resultado.get('aliquota_interna_status') or '-'}",
            f"Confirmada para o produto: {'SIM' if resultado.get('aliquota_interna_confirmada') else 'NÃO'}",
            f"Segurança da alíquota: {self._percentual(resultado.get('confiabilidade_aliquota'))}",
            "",
            "FCP / FECOEP / FECOP",
            "---------------------",
            f"Adicional: {self._percentual(resultado.get('fcp'))}",
            f"Alíquota total ao consumidor: {self._percentual(resultado.get('aliquota_total_consumidor'))}",
            f"Status: {resultado.get('fcp_status') or '-'}",
            f"Confirmado: {'SIM' if resultado.get('fcp_confirmado') else 'NÃO'}",
            f"Segurança: {self._percentual(resultado.get('confiabilidade_fcp'))}",
            "",
            "ICMS-ST",
            "-------",
            f"Status: {resultado.get('st_status') or '-'}",
            f"Potencial: {'SIM' if resultado.get('st_potencial') else 'NÃO'}",
            f"Aplica ST na UF/período: {'SIM' if resultado.get('st_confirmado') else 'NÃO'}",
            f"Decisão estadual confirmada: {'SIM' if resultado.get('st_decisao_confirmada') else 'NÃO'}",
            f"CEST: {resultado.get('cest') or '-'}",
            f"Segmento: {resultado.get('segmento_st') or '-'}",
            f"Descrição legal: {resultado.get('descricao_legal_st') or '-'}",
            f"Contrato de fidelidade: {'SIM' if resultado.get('contrato_fidelidade') else 'NÃO'}",
            f"MVA original: {self._percentual(resultado.get('mva_original'))}",
            f"MVA ajustada: {self._percentual(resultado.get('mva_ajustada'))}",
            f"MVA aplicada: {self._percentual(resultado.get('mva_aplicada'))}",
            f"Tipo de MVA: {resultado.get('mva_tipo') or '-'}",
            f"Vigência inicial: {resultado.get('st_vigencia_inicio') or '-'}",
            f"Vigência final: {resultado.get('st_vigencia_fim') or 'sem data final instalada'}",
            f"Responsabilidade: {resultado.get('st_responsabilidade') or '-'}",
            f"Acordo interestadual: {resultado.get('st_acordo_status') or '-'}",
            f"Segurança ST: {self._percentual(resultado.get('confiabilidade_st'))}",
            "",
            "BENEFÍCIOS E FONTES",
            "--------------------",
            f"Benefícios: {resultado.get('beneficio_status') or '-'}",
            f"Fundamento alíquota: {resultado.get('fundamento_aliquota') or '-'}",
            f"Fundamento FCP: {resultado.get('fundamento_fcp') or '-'}",
            f"Fundamento ST: {resultado.get('fundamento_st') or '-'}",
            f"Fonte alíquota: {resultado.get('fonte_aliquota') or '-'}",
            f"Fonte FCP: {resultado.get('fonte_fcp') or '-'}",
            f"Fonte ST: {resultado.get('fonte_st') or '-'}",
            "",
            "ALERTAS",
            "-------",
            resultado.get("observacao") or "-",
            "",
            "O FiscalPro usa a MVA específica da UF e da vigência instaladas. Quando a regra "
            "estadual não estiver coberta, o CEST permanece apenas como indício, sem inventar MVA.",
        ]
        self.resultado.delete("1.0", tk.END)
        self.resultado.insert(tk.END, "\n".join(linhas))
        self.status.configure(
            text=(
                "Análise confirmada para todas as camadas disponíveis."
                if resultado.get("confirmado")
                else "Análise concluída: confira os pontos marcados para revisão."
            )
        )

    def abrir_mg(self):
        JanelaICMSMG(
            self,
            ncm=self.var_ncm.get().strip(),
            descricao=self.var_descricao.get().strip(),
        )

    def abrir_difal(self):
        JanelaDIFALFCP(
            self,
            ncm=self.var_ncm.get().strip(),
            descricao=self.var_descricao.get().strip(),
            uf_origem=self.var_origem.get(),
            uf_destino=self.var_destino.get(),
        )


__all__ = ["JanelaICMSUF"]
