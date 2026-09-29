import tkinter as tk
from tkinter import ttk, messagebox
import threading

from src.inteligencia.motor_tributario import MotorTributario
from src.inteligencia.consulta_tributaria import ConsultaTributaria
from src.services.atualizador_fontes_oficiais import AtualizadorFontesOficiais
from src.services.assistente_tributario_oficial import AssistenteTributarioOficial
from src.ui.janela_ficha_tributaria import JanelaFichaTributaria
from src.ui.janela_catalogo_ncm import JanelaCatalogoNCM
from src.ui.janela_piscofins_nacional import JanelaPISCOFINSNacional
from src.ui.janela_icms_uf import JanelaICMSUF
from src.ui.janela_difal_fcp import JanelaDIFALFCP
from src.services.base_ncm_nacional_service import BaseNCMNacionalService
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.ui.layout_responsivo import dimensionar_janela


class JanelaConsultaNCM(tk.Toplevel):

    def __init__(self, master=None):
        super().__init__(master)

        self.title("Consulta Tributária")
        dimensionar_janela(self, 1120, 760, 820, 520)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        formulario = ttk.LabelFrame(self, text="Consulta por NCM", padding=12)
        formulario.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        formulario.grid_columnconfigure(1, weight=1)
        ttk.Label(formulario, text="NCM").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.ncm = ttk.Entry(formulario, width=30)
        self.ncm.grid(row=0, column=1, sticky="ew")
        self.ncm.bind("<Return>", lambda _e: self.consultar())
        self.ncm.bind("<KP_Enter>", lambda _e: self.consultar())

        self.empresa_var = tk.StringVar(value="Todas as empresas")
        self.regime_var = tk.StringVar(value="Lucro Real")
        self.regime_info_var = tk.StringVar(value="Selecione a empresa para definir o regime automaticamente.")
        ttk.Label(formulario, text="Empresa").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.combo_empresa = ttk.Combobox(
            formulario, textvariable=self.empresa_var, state="readonly",
            values=EmpresasRegimesService.listar_empresas(incluir_todas=True),
        )
        self.combo_empresa.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.combo_empresa.bind("<<ComboboxSelected>>", self._empresa_alterada)
        ttk.Label(formulario, text="Regime").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Combobox(
            formulario, textvariable=self.regime_var, state="readonly",
            values=("Lucro Real", "Lucro Presumido", "Simples Nacional", "MEI"),
        ).grid(row=2, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(
            formulario, textvariable=self.regime_info_var, foreground="#1F4E78",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(7, 0))

        botoes = ttk.Frame(self)
        botoes.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        for coluna in range(8):
            botoes.grid_columnconfigure(coluna, weight=1, uniform="consulta")

        ttk.Button(botoes, text="Consultar", command=self.consultar).grid(row=0, column=0, sticky="ew")
        self.botao_atualizar = ttk.Button(
            botoes, text="Atualizar fontes oficiais", command=self.atualizar_fontes
        )
        self.botao_atualizar.grid(row=0, column=1, sticky="ew", padx=(7, 0))
        self.botao_ia = ttk.Button(
            botoes, text="Analisar com IA oficial", command=self.analisar_com_ia
        )
        self.botao_ia.grid(row=0, column=2, sticky="ew", padx=(7, 0))
        self.botao_catalogo = ttk.Button(
            botoes, text="Catálogo de NCM", command=self.abrir_catalogo
        )
        self.botao_catalogo.grid(row=0, column=3, sticky="ew", padx=(7, 0))
        self.botao_piscofins = ttk.Button(
            botoes, text="Base PIS/COFINS", command=self.abrir_piscofins
        )
        self.botao_piscofins.grid(row=0, column=4, sticky="ew", padx=(7, 0))
        self.botao_icms_uf = ttk.Button(
            botoes, text="ICMS por UF", command=self.abrir_icms_uf
        )
        self.botao_icms_uf.grid(row=0, column=5, sticky="ew", padx=(7, 0))
        self.botao_difal = ttk.Button(
            botoes, text="DIFAL/FCP", command=self.abrir_difal_fcp
        )
        self.botao_difal.grid(row=0, column=6, sticky="ew", padx=(7, 0))
        self.botao_ficha = ttk.Button(
            botoes, text="Abrir ficha tributária", command=self.abrir_ficha
        )
        self.botao_ficha.grid(row=0, column=7, sticky="ew", padx=(7, 0))

        base_nacional = BaseNCMNacionalService.garantir_instalada()
        self.status_fontes = ttk.Label(
            self,
            text=(
                f"Base nacional offline: {base_nacional.total_ncm:,} NCMs e "
                f"{base_nacional.total_tipi:,} registros TIPI."
            ).replace(",", "."),
            anchor="w",
        )
        self.status_fontes.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 7))

        resultado_frame = ttk.LabelFrame(self, text="Resultado da consulta", padding=8)
        resultado_frame.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 14))
        resultado_frame.grid_rowconfigure(0, weight=1)
        resultado_frame.grid_columnconfigure(0, weight=1)

        self.resultado = tk.Text(
            resultado_frame, wrap=tk.WORD, font=("Consolas", 10), padx=10, pady=10
        )
        barra = ttk.Scrollbar(resultado_frame, orient="vertical", command=self.resultado.yview)
        self.resultado.configure(yscrollcommand=barra.set)
        self.resultado.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.ncm.focus_set()

    def _empresa_alterada(self, _evento=None):
        empresa = self.empresa_var.get().strip()
        perfil = EmpresasRegimesService.obter_perfil(empresa)
        if perfil is not None:
            self.regime_var.set(perfil.regime.title())
        self.regime_info_var.set(EmpresasRegimesService.descricao_regime(empresa, self.regime_var.get()))

    def abrir_catalogo(self):
        JanelaCatalogoNCM(self, ao_selecionar=self._usar_ncm_catalogo)

    def _usar_ncm_catalogo(self, ncm):
        self.ncm.delete(0, tk.END)
        self.ncm.insert(0, ncm)
        self.consultar()

    def atualizar_fontes(self):
        self.botao_atualizar.config(state=tk.DISABLED)
        self.status_fontes.config(text="Baixando a tabela NCM oficial da Receita Federal...")

        def executar():
            resultado = AtualizadorFontesOficiais().atualizar_todas()
            self.after(0, lambda: self._finalizar_atualizacao(resultado))

        threading.Thread(target=executar, daemon=True).start()

    def _finalizar_atualizacao(self, resultado):
        self.botao_atualizar.config(state=tk.NORMAL)
        if resultado.status in {"SUCESSO", "PARCIAL"}:
            prefixo = "Sincronização concluída" if resultado.status == "SUCESSO" else "Sincronização parcial"
            texto = f"{prefixo}: {resultado.mensagem}"
            self.status_fontes.config(text=texto)
            messagebox.showinfo("FiscalPro", texto + "\n\n" + "\n".join(resultado.detalhes))
        else:
            self.status_fontes.config(text="Falha ao atualizar. Verifique a internet.")
            messagebox.showerror("FiscalPro", resultado.mensagem)

    def analisar_com_ia(self):
        ficha = getattr(self, "ultima_ficha", None)
        self.ultima_ficha = ficha

        if ficha is None:
            messagebox.showwarning("FiscalPro", "Faça primeiro a consulta do NCM.")
            return
        relatorio = AssistenteTributarioOficial.analisar(ficha)
        self.resultado.delete("1.0", tk.END)
        self.resultado.insert(tk.END, relatorio)

    def abrir_piscofins(self):
        ficha = getattr(self, "ultima_ficha", None)
        ncm = self.ncm.get().strip()
        descricao = getattr(ficha, "descricao", "") if ficha is not None else ""
        empresa = "" if self.empresa_var.get().strip() == "Todas as empresas" else self.empresa_var.get().strip()
        JanelaPISCOFINSNacional(
            self, ncm=ncm, descricao=descricao, empresa=empresa,
            regime=EmpresasRegimesService.resolver_regime(empresa, self.regime_var.get()),
        )

    def abrir_icms_uf(self):
        ficha = getattr(self, "ultima_ficha", None)
        ncm = self.ncm.get().strip()
        descricao = getattr(ficha, "descricao", "") if ficha is not None else ""
        JanelaICMSUF(
            self, ncm=ncm, descricao=descricao, uf_origem="MG", uf_destino="MG"
        )

    def abrir_difal_fcp(self):
        ficha = getattr(self, "ultima_ficha", None)
        ncm = self.ncm.get().strip()
        descricao = getattr(ficha, "descricao", "") if ficha is not None else ""
        JanelaDIFALFCP(
            self,
            ncm=ncm,
            descricao=descricao,
            uf_origem="MG",
            uf_destino="ES",
        )

    def abrir_ficha(self):
        ficha = getattr(self, "ultima_ficha", None)
        if ficha is None:
            messagebox.showwarning("FiscalPro", "Faça primeiro a consulta do NCM.")
            return
        empresa = "" if self.empresa_var.get().strip() == "Todas as empresas" else self.empresa_var.get().strip()
        contexto = {
            "empresa": empresa,
            "regime": EmpresasRegimesService.resolver_regime(empresa, self.regime_var.get()),
            "operacao": ficha.operacao or "Venda",
            "finalidade": "Revenda",
            "uf_origem": "MG",
            "uf_destino": ficha.uf or "MG",
            "consumidor_final": "Sim",
        }
        JanelaFichaTributaria(self, ficha, contexto)

    def consultar(self):

        ncm = self.ncm.get().strip()

        if not ncm:
            messagebox.showwarning(
                "FiscalPro",
                "Informe um NCM."
            )
            return

        empresa = "" if self.empresa_var.get().strip() == "Todas as empresas" else self.empresa_var.get().strip()
        consulta = ConsultaTributaria(
            ncm=ncm,
            uf_origem="MG",
            uf_destino="MG",
            regime=EmpresasRegimesService.resolver_regime(empresa, self.regime_var.get()),
            operacao="Venda",
            consumidor_final=True,
            empresa=empresa,
        )

        ficha = MotorTributario().consultar(consulta)

        self.resultado.delete("1.0", tk.END)

        self.ultima_ficha = ficha

        if ficha is None:

            self.resultado.insert(
                tk.END,
                "NCM/tributação não encontrados em base validada.\n\n"
                "A pesquisa foi colocada na fila da inteligência tributária. "
                "Atualize as fontes oficiais e tente novamente."
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

CFOP: {ficha.cfop}

CST ICMS: {ficha.cst_icms}

PIS CST: {ficha.pis_cst}

COFINS CST: {ficha.cofins_cst}

Alíquota PIS: {ficha.aliquota_pis:.2f} %

Alíquota COFINS: {ficha.aliquota_cofins:.2f} %

------------------------------
MOTOR NACIONAL PIS/COFINS
------------------------------

Status: {ficha.piscofins_status or "Não analisado"}

Enquadramento: {ficha.piscofins_enquadramento or "-"}

Confirmação automática: {"SIM" if ficha.piscofins_confirmado else "NÃO"}

Sugestão CST PIS: {ficha.piscofins_sugestao_cst_pis or "-"}

Sugestão PIS: {ficha.piscofins_sugestao_aliquota_pis:.2f} %

Sugestão CST COFINS: {ficha.piscofins_sugestao_cst_cofins or "-"}

Sugestão COFINS: {ficha.piscofins_sugestao_aliquota_cofins:.2f} %

Tabela EFD: {ficha.piscofins_tabela_efd or "-"}

Fundamento: {ficha.piscofins_fundamento or "-"}

Confiabilidade: {ficha.piscofins_confiabilidade:.0f}%

Aviso: {ficha.piscofins_observacoes or "-"}

------------------------------
MOTOR ICMS/MG — SPRINT 16.6
------------------------------

Status: {ficha.icms_mg_status or "Não analisado"}

Tipo de operação: {ficha.icms_mg_tipo_operacao or "-"}

Alíquota nominal: {ficha.icms_mg_aliquota_nominal:.2f} %

Status da alíquota: {ficha.icms_mg_aliquota_status or "-"}

Alíquota confirmada: {"SIM" if ficha.icms_mg_confirmado else "NÃO"}

Confiança da alíquota: {ficha.icms_mg_confiabilidade:.0f}%

ICMS-ST: {ficha.icms_mg_st_status or "-"}

CEST oficial MG: {ficha.icms_mg_cest or "-"}

MVA original: {ficha.icms_mg_mva:.2f} %

Benefício: {ficha.icms_mg_beneficio_status or "Não identificado automaticamente"}

Redução de base: {ficha.icms_mg_reducao_base:.2f} %

Fundamento: {ficha.icms_mg_fundamento or "-"}

Aviso: {ficha.icms_mg_observacoes or "-"}

ICMS operacional gravado: {ficha.icms:.2f} %

ICMS ST: {ficha.icms_st}

FCP: {ficha.fcp:.2f} %

CST IPI: {ficha.cst_ipi}

IPI: {ficha.ipi:.2f} %

------------------------------
REFORMA TRIBUTÁRIA — 2026
------------------------------

Situação: {ficha.reforma_status}

Classificação: {ficha.cclasstrib}

Crédito Presumido: {ficha.ccredpres}

CST IBS: {ficha.cst_ibs}

CST CBS: {ficha.cst_cbs}

IBS: {ficha.aliquota_ibs:.2f} %

CBS: {ficha.aliquota_cbs:.2f} %

Imposto Seletivo: {ficha.imposto_seletivo}

Aviso da Reforma:
{ficha.reforma_observacoes or "-"}

------------------------------
ORIGEM E CONFIABILIDADE
------------------------------

Fonte: {", ".join(ficha.fontes) if ficha.fontes else "Não informada"}

Confiabilidade: {ficha.confiabilidade:.0f}%

Produtos encontrados: {ficha.quantidade_produtos}

Variações tributárias: {ficha.quantidade_variacoes}

Observações:
{ficha.observacoes or "-"}
"""

        self.resultado.insert(tk.END, texto)