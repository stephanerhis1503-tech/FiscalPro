"""Painel de referencia IBS/CBS 2026-2027, SEM impacto na apuracao fiscal.

A CBS de 2027 e exibida somente como cenario TCU opt-in.
"""
from __future__ import annotations

from decimal import Decimal
from tkinter import BOTH, LEFT, X, StringVar, BooleanVar, ttk, messagebox

from src.services.rtc_aliquotas_service import (
    DATA_VERIFICACAO,
    REGIMES,
    ServicoAliquotasRTC,
)


def _moeda(valor: Decimal | None) -> str:
    if valor is None:
        return "Nao calculado"
    return "R$ " + f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _taxa(valor: Decimal | None) -> str:
    if valor is None:
        return "A DEFINIR"
    return f"{valor:.2f}".replace(".", ",") + "%"


class PainelAliquotasRTC(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.servico = ServicoAliquotasRTC()
        self.var_ano = StringVar(value="2026")
        self.var_base = StringVar(value="1.000,00")
        self.var_cst = StringVar(value="000")
        self.var_class = StringVar(value="000001")
        self.var_regime = StringVar(value="Lucro Real")
        self.var_cenario = BooleanVar(value=False)
        self.var_cbs = StringVar(value="")
        self.var_ibsu = StringVar(value="")
        self.var_ibsm = StringVar(value="")
        self.var_status_regra = StringVar(value="")
        self.var_fonte = StringVar(value="")
        self.var_resultado = StringVar(value="Selecione os dados e clique em Simular.")
        self._montar()
        self._atualizar_regra()

    def _montar(self):
        cab = ttk.LabelFrame(self, text="RTC | Aliquotas IBS/CBS 2026-2027", padding=12)
        cab.pack(fill=X, padx=10, pady=(8, 6))
        ttk.Label(
            cab, text="Consulta historica e SIMULADOR local. Nao altera XML, "
                      "nao gera recolhimento, nao reconhece credito e nao muda a "
                      "CBS Oficial ou a Apuracao Local.",
            wraplength=1000,
        ).pack(anchor="w", pady=(0, 10))

        linha = ttk.Frame(cab)
        linha.pack(fill=X)
        ttk.Label(linha, text="Ano").pack(side=LEFT)
        ano = ttk.Combobox(linha, textvariable=self.var_ano, values=("2026", "2027"),
                           width=8, state="readonly")
        ano.pack(side=LEFT, padx=(8, 22))
        ano.bind("<<ComboboxSelected>>", lambda _: self._atualizar_regra())
        ttk.Label(linha, text="Status da regra:").pack(side=LEFT)
        ttk.Label(linha, textvariable=self.var_status_regra,
                  wraplength=600).pack(side=LEFT, padx=8)

        taxas = ttk.LabelFrame(self, text="Aliquotas de referencia por competencia", padding=12)
        taxas.pack(fill=X, padx=10, pady=(0, 6))
        cards = ttk.Frame(taxas)
        cards.pack(fill=X)
        for titulo, variavel in (
            ("CBS", self.var_cbs), ("IBS estadual", self.var_ibsu),
            ("IBS municipal", self.var_ibsm),
        ):
            area = ttk.LabelFrame(cards, text=titulo, padding=10)
            area.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
            ttk.Label(area, textvariable=variavel,
                      font=("Segoe UI", 16, "bold")).pack(anchor="center")
        ttk.Label(taxas, textvariable=self.var_fonte, wraplength=1040).pack(
            anchor="w", pady=(8, 0)
        )
        aviso = ttk.LabelFrame(self, text="Aviso de seguranca fiscal", padding=12)
        aviso.pack(fill=X, padx=10, pady=(0, 6))
        ttk.Label(
            aviso, text=(
                "2027: CBS AINDA NAO DEFINITIVA. Referencia calculada pelo TCU: "
                "11,3%. Cenario hipotetico apos reducao legal de 0,1 ponto percentual: "
                "11,2%. NAO usar para emitir notas, gerar SPED, parametrizar ERPs, "
                "contabilizar tributos ou apropriar credito. "
                "Validar a resolucao do Senado antes da aplicacao."
            ), wraplength=1050, justify=LEFT,
        ).pack(anchor="w")

        simulacao = ttk.LabelFrame(
            self, text="Simulacao demonstrativa - apenas tributacao integral padrao",
            padding=12,
        )
        simulacao.pack(fill=X, padx=10, pady=(0, 6))
        filtros = ttk.Frame(simulacao)
        filtros.pack(fill=X)
        for rotulo, variavel, largura in (
            ("Base (R$)", self.var_base, 15),
            ("CST", self.var_cst, 7),
            ("cClassTrib", self.var_class, 12),
        ):
            ttk.Label(filtros, text=rotulo).pack(side=LEFT, padx=(0, 5))
            ttk.Entry(filtros, textvariable=variavel, width=largura).pack(
                side=LEFT, padx=(0, 16)
            )
        ttk.Label(filtros, text="Regime").pack(side=LEFT, padx=(0, 5))
        ttk.Combobox(
            filtros, textvariable=self.var_regime,
            values=REGIMES, width=18, state="readonly",
        ).pack(side=LEFT)
        opcoes = ttk.Frame(simulacao)
        opcoes.pack(fill=X, pady=(12, 8))
        self.check_cenario = ttk.Checkbutton(
            opcoes, text="Simular CBS 2027 com referencia TCU (11,2% NAO oficial)",
            variable=self.var_cenario,
        )
        self.check_cenario.pack(side=LEFT, padx=(0, 12))
        ttk.Button(opcoes, text="Simular (nao grava)", command=self._simular).pack(
            side=LEFT
        )
        ttk.Label(simulacao, textvariable=self.var_resultado,
                  wraplength=1050, justify=LEFT).pack(anchor="w", pady=(5, 0))
        ttk.Label(
            self,
            text="FiscalPro | Stephane Rhis + ChatGPT | "
                 "Regra de preparacao sem integracao com emissao ou apuracao",
        ).pack(anchor="w", padx=16, pady=8)

    def _atualizar_regra(self):
        try:
            regra = self.servico.consultar(self.var_ano.get())
        except ValueError as exc:
            messagebox.showerror("RTC | Aliquotas", str(exc), parent=self)
            return
        self.var_cenario.set(False)
        self.check_cenario.configure(
            state="normal" if regra.ano == 2027 else "disabled"
        )
        self.var_cbs.set(_taxa(regra.cbs_vigente))
        self.var_ibsu.set(_taxa(regra.ibs_uf))
        self.var_ibsm.set(_taxa(regra.ibs_municipal))
        self.var_status_regra.set(
            "Regras do ano de teste (2026)" if regra.ano == 2026
            else "CBS PENDENTE de resolucao do Senado - somente simular"
        )
        self.var_fonte.set(
            f"Fontes: {regra.fonte}. Referencias verificadas em {DATA_VERIFICACAO}."
        )
        self.var_resultado.set(
            "Selecione a base, o enquadramento e clique em Simular."
        )

    def _simular(self):
        try:
            resultado = self.servico.simular(
                self.var_ano.get(), self.var_base.get(),
                cst=self.var_cst.get(), cclass_trib=self.var_class.get(),
                regime=self.var_regime.get(), usar_cenario_tcu=self.var_cenario.get(),
            )
        except ValueError as exc:
            self.var_resultado.set(f"Dados invalidos: {exc}")
            messagebox.showwarning("RTC | Simulacao", str(exc), parent=self)
            return
        valores = (
            f"Base: {_moeda(resultado['base'])} | "
            f"IBS UF: {_moeda(resultado['ibs_uf'])} | "
            f"IBS municipal: {_moeda(resultado['ibs_municipal'])} | "
            f"CBS: {_moeda(resultado['cbs'])} | "
            f"Total demonstrativo: {_moeda(resultado['total'])}"
        )
        self.var_resultado.set(
            f"{resultado['status']} | {valores}\n{resultado['observacao']}"
        )
