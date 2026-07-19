import tkinter as tk
from tkinter import ttk, messagebox

from src.inteligencia.motor_tributario import MotorTributario
from src.inteligencia.consulta_tributaria import ConsultaTributaria


class JanelaConsultaNCM(tk.Toplevel):

    def __init__(self, master=None):
        super().__init__(master)

        self.title("Consulta Tributária")
        self.geometry("720x650")

        ttk.Label(self, text="NCM").pack(pady=5)

        self.ncm = ttk.Entry(self, width=30)
        self.ncm.pack()

        ttk.Button(
            self,
            text="Consultar",
            command=self.consultar
        ).pack(pady=10)

        self.resultado = tk.Text(
            self,
            width=85,
            height=30
        )

        self.resultado.pack(padx=10, pady=10)

    def consultar(self):

        ncm = self.ncm.get().strip()

        if not ncm:
            messagebox.showwarning(
                "FiscalPro",
                "Informe um NCM."
            )
            return

        consulta = ConsultaTributaria(
            ncm=ncm,
            uf_origem="MG",
            uf_destino="MG",
            regime="Lucro Real",
            operacao="Venda",
            consumidor_final=True
        )

        ficha = MotorTributario().consultar(consulta)

        self.resultado.delete("1.0", tk.END)

        if ficha is None:

            self.resultado.insert(
                tk.END,
                "NCM não encontrado na base do FiscalPro.\n\n"
                "Em breve o Pesquisador Fiscal fará a consulta automática."
            )

            return

        texto = f"""
==============================
CONSULTA TRIBUTÁRIA
==============================

NCM: {ficha.ncm}

Descrição:
{ficha.descricao}

CEST:
{ficha.cest}

Status:
{ficha.status}

------------------------------
TRIBUTAÇÃO ATUAL
------------------------------

UF: {ficha.uf}

Regime: {ficha.regime}

Operação: {ficha.operacao}

PIS CST: {ficha.pis_cst}

COFINS CST: {ficha.cofins_cst}

Alíquota PIS: {ficha.aliquota_pis:.2f} %

Alíquota COFINS: {ficha.aliquota_cofins:.2f} %

ICMS: {ficha.icms:.2f} %

ICMS ST: {ficha.icms_st}

FCP: {ficha.fcp:.2f} %

IPI: {ficha.ipi:.2f} %

------------------------------
REFORMA TRIBUTÁRIA
------------------------------

Classificação: {ficha.cclasstrib}

Crédito Presumido: {ficha.ccredpres}

CST IBS: {ficha.cst_ibs}

CST CBS: {ficha.cst_cbs}

IBS: {ficha.aliquota_ibs:.2f} %

CBS: {ficha.aliquota_cbs:.2f} %

Imposto Seletivo: {ficha.imposto_seletivo}
"""

        self.resultado.insert(tk.END, texto)