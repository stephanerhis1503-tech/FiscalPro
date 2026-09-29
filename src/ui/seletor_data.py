"""Seletor de data em calendário, sem dependências externas.

Sprint 16.9.0 — usado pelo módulo Contas a Pagar para evitar digitação
manual de datas e erros de formato.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from tkinter import StringVar, Toplevel
from tkinter import ttk
from typing import Callable

MESES_PT = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
DIAS_PT = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def _converter_data(valor: str) -> date | None:
    texto = (valor or "").strip()
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


class SeletorDataPopup:
    """Calendário modal que grava a data selecionada em ``dd/mm/aaaa``."""

    def __init__(
        self,
        master,
        variavel: StringVar,
        *,
        titulo: str = "Selecionar data",
        permitir_limpar: bool = False,
        ao_selecionar: Callable[[str], None] | None = None,
    ) -> None:
        self.master = master
        self.variavel = variavel
        self.permitir_limpar = permitir_limpar
        self.ao_selecionar = ao_selecionar
        self.data_original = _converter_data(variavel.get())
        referencia = self.data_original or date.today()

        self.var_mes = StringVar(value=MESES_PT[referencia.month - 1])
        self.var_ano = StringVar(value=str(referencia.year))

        self.janela = Toplevel(master)
        self.janela.title(titulo)
        self.janela.transient(master.winfo_toplevel())
        self.janela.resizable(False, False)
        self.janela.protocol("WM_DELETE_WINDOW", self.janela.destroy)

        self._montar()
        self._renderizar_dias()
        self._posicionar()
        self.janela.grab_set()
        self.janela.focus_force()

    def _montar(self) -> None:
        principal = ttk.Frame(self.janela, padding=12)
        principal.pack(fill="both", expand=True)

        navegacao = ttk.Frame(principal)
        navegacao.pack(fill="x", pady=(0, 8))
        ttk.Button(navegacao, text="◀", width=4, command=lambda: self._mover_mes(-1)).pack(
            side="left"
        )

        self.cbo_mes = ttk.Combobox(
            navegacao,
            textvariable=self.var_mes,
            values=MESES_PT,
            state="readonly",
            width=13,
            justify="center",
        )
        self.cbo_mes.pack(side="left", padx=(8, 4))
        self.cbo_mes.bind("<<ComboboxSelected>>", lambda _e: self._renderizar_dias())

        ano_atual = date.today().year
        anos = tuple(str(ano) for ano in range(2020, ano_atual + 16))
        self.cbo_ano = ttk.Combobox(
            navegacao,
            textvariable=self.var_ano,
            values=anos,
            state="readonly",
            width=7,
            justify="center",
        )
        self.cbo_ano.pack(side="left", padx=(4, 8))
        self.cbo_ano.bind("<<ComboboxSelected>>", lambda _e: self._renderizar_dias())

        ttk.Button(navegacao, text="▶", width=4, command=lambda: self._mover_mes(1)).pack(
            side="left"
        )

        self.quadro_dias = ttk.Frame(principal)
        self.quadro_dias.pack(fill="both", expand=True)
        for coluna, texto in enumerate(DIAS_PT):
            ttk.Label(self.quadro_dias, text=texto, anchor="center", width=5).grid(
                row=0, column=coluna, padx=1, pady=(0, 4)
            )

        rodape = ttk.Frame(principal)
        rodape.pack(fill="x", pady=(10, 0))
        ttk.Button(rodape, text="Hoje", command=self._hoje).pack(side="left")
        if self.permitir_limpar:
            ttk.Button(rodape, text="Limpar", command=self._limpar).pack(
                side="left", padx=(6, 0)
            )
        ttk.Button(rodape, text="Cancelar", command=self.janela.destroy).pack(side="right")

    def _mes_numero(self) -> int:
        try:
            return MESES_PT.index(self.var_mes.get()) + 1
        except ValueError:
            return date.today().month

    def _ano_numero(self) -> int:
        try:
            return int(self.var_ano.get())
        except (TypeError, ValueError):
            return date.today().year

    def _renderizar_dias(self) -> None:
        for widget in self.quadro_dias.grid_slaves():
            if int(widget.grid_info().get("row", 0)) > 0:
                widget.destroy()

        ano = self._ano_numero()
        mes = self._mes_numero()
        semanas = calendar.Calendar(firstweekday=calendar.MONDAY).monthdayscalendar(ano, mes)
        hoje = date.today()

        for linha, semana in enumerate(semanas, start=1):
            for coluna, dia in enumerate(semana):
                if not dia:
                    ttk.Label(self.quadro_dias, text="", width=5).grid(
                        row=linha, column=coluna, padx=1, pady=1
                    )
                    continue
                selecionada = (
                    self.data_original is not None
                    and self.data_original.year == ano
                    and self.data_original.month == mes
                    and self.data_original.day == dia
                )
                data_dia = date(ano, mes, dia)
                estilo = "Accent.TButton" if selecionada or data_dia == hoje else "TButton"
                ttk.Button(
                    self.quadro_dias,
                    text=f"{dia:02d}",
                    width=5,
                    style=estilo,
                    command=lambda valor=dia: self._selecionar(valor),
                ).grid(row=linha, column=coluna, padx=1, pady=1)

    def _mover_mes(self, deslocamento: int) -> None:
        ano = self._ano_numero()
        mes = self._mes_numero() + deslocamento
        if mes < 1:
            mes = 12
            ano -= 1
        elif mes > 12:
            mes = 1
            ano += 1
        self.var_mes.set(MESES_PT[mes - 1])
        self.var_ano.set(str(ano))
        valores_atuais = self.cbo_ano.cget("values")
        if isinstance(valores_atuais, str):
            valores_atuais = self.janela.tk.splitlist(valores_atuais)
        if str(ano) not in valores_atuais:
            valores = sorted({*valores_atuais, str(ano)}, key=int)
            self.cbo_ano.configure(values=valores)
        self._renderizar_dias()

    def _selecionar(self, dia: int) -> None:
        escolhida = date(self._ano_numero(), self._mes_numero(), int(dia))
        texto = escolhida.strftime("%d/%m/%Y")
        self.variavel.set(texto)
        if self.ao_selecionar:
            self.ao_selecionar(texto)
        self.janela.destroy()

    def _hoje(self) -> None:
        hoje = date.today()
        self.var_mes.set(MESES_PT[hoje.month - 1])
        self.var_ano.set(str(hoje.year))
        self._selecionar(hoje.day)

    def _limpar(self) -> None:
        self.variavel.set("")
        if self.ao_selecionar:
            self.ao_selecionar("")
        self.janela.destroy()

    def _posicionar(self) -> None:
        self.janela.update_idletasks()
        largura = self.janela.winfo_reqwidth()
        altura = self.janela.winfo_reqheight()
        topo = self.master.winfo_toplevel()
        x = topo.winfo_rootx() + max(0, (topo.winfo_width() - largura) // 2)
        y = topo.winfo_rooty() + max(0, (topo.winfo_height() - altura) // 2)
        self.janela.geometry(f"+{x}+{y}")
