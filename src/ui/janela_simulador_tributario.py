"""Interface do Simulador Tributário — Sprint 13.7."""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from src.parecer.motor_parecer import MotorParecer
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository
from src.simulador.exportadores import ExportadorSimulacao
from src.simulador.historico import HistoricoSimuladorRepository
from src.simulador.motor_simulador import EntradaSimulacao, MotorSimuladorTributario, ResultadoSimulacao
from src.simulador.tabela_difal import FONTE_TABELA_DIFAL, aliquotas_automaticas
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.ui.layout_responsivo import dimensionar_janela


_UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")
_REGIMES = ("", "SIMPLES NACIONAL", "LUCRO PRESUMIDO", "LUCRO REAL", "MEI", "OUTRO")
_OPERACOES = ("ENTRADA", "SAÍDA", "DEVOLUÇÃO", "TRANSFERÊNCIA", "IMPORTAÇÃO", "EXPORTAÇÃO")
_FINALIDADES = ("REVENDA", "INDUSTRIALIZAÇÃO", "USO E CONSUMO", "ATIVO IMOBILIZADO", "SERVIÇO", "OUTRA")
_CONTRIBUINTES = ("TODOS", "CONTRIBUINTE", "NÃO CONTRIBUINTE")


def _moeda(valor: Any) -> str:
    try:
        texto = f"{float(valor):,.2f}"
    except (TypeError, ValueError):
        return "R$ 0,00"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _numero_br(valor: Any, casas: int = 4) -> str:
    try:
        texto = f"{float(valor):.{casas}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return ""
    return texto.replace(".", ",")


def _data_br(valor: Any) -> str:
    texto = str(valor or "").strip()
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return texto


class _FrameRolavel(ttk.Frame):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.barra = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.interno = ttk.Frame(self.canvas, padding=(0, 0, 8, 8))
        self.janela = self.canvas.create_window((0, 0), window=self.interno, anchor="nw")
        self.canvas.configure(yscrollcommand=self.barra.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.barra.pack(side=tk.RIGHT, fill=tk.Y)
        self.interno.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.janela, width=e.width))
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._rolar))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _rolar(self, evento):
        self.canvas.yview_scroll(-1 if evento.delta > 0 else 1, "units")
        return "break"


class JanelaSimuladorTributario(tk.Toplevel):
    def __init__(self, master=None, ncm: str = "", contexto: Optional[Dict[str, Any]] = None):
        super().__init__(master)
        contexto = contexto or {}
        self.title("FiscalPro — Simulador Tributário — Sprint 13.7.1")
        dimensionar_janela(self, 1380, 900, 980, 620)

        empresa_inicial = str(contexto.get("empresa") or "Todas as empresas")
        regime_inicial = EmpresasRegimesService.resolver_regime(
            empresa_inicial, contexto.get("regime") or ""
        )
        self.vars: Dict[str, tk.StringVar] = {
            "ncm": tk.StringVar(value=ncm),
            "empresa": tk.StringVar(value=empresa_inicial),
            "regime": tk.StringVar(value=regime_inicial),
            "operacao": tk.StringVar(value=str(contexto.get("operacao") or "SAÍDA")),
            "finalidade": tk.StringVar(value=str(contexto.get("finalidade") or "REVENDA")),
            "uf_origem": tk.StringVar(value=str(contexto.get("uf_origem") or "MG")),
            "uf_destino": tk.StringVar(value=str(contexto.get("uf_destino") or "MG")),
            "contribuinte": tk.StringVar(value=str(contexto.get("contribuinte") or "TODOS")),
            "data_operacao": tk.StringVar(value=str(contexto.get("data_operacao") or date.today().strftime("%d/%m/%Y"))),
            "descricao_cenario": tk.StringVar(value="Cenário principal"),
            "quantidade": tk.StringVar(value="1"),
            "valor_unitario": tk.StringVar(value="0,00"),
            "desconto": tk.StringVar(value="0,00"),
            "frete": tk.StringVar(value="0,00"),
            "seguro": tk.StringVar(value="0,00"),
            "outras_despesas": tk.StringVar(value="0,00"),
            "base_icms_manual": tk.StringVar(value=""),
            "base_pis_cofins_manual": tk.StringVar(value=""),
            "base_ipi_manual": tk.StringVar(value=""),
            "base_reforma_manual": tk.StringVar(value=""),
            "base_difal_manual": tk.StringVar(value=""),
            "aliquota_icms_override": tk.StringVar(value=""),
            "aliquota_fcp_override": tk.StringVar(value=""),
            "aliquota_pis_override": tk.StringVar(value=""),
            "aliquota_cofins_override": tk.StringVar(value=""),
            "aliquota_ipi_override": tk.StringVar(value=""),
            "aliquota_ibs_override": tk.StringVar(value=""),
            "aliquota_cbs_override": tk.StringVar(value=""),
            "reducao_ibs_override": tk.StringVar(value=""),
            "reducao_cbs_override": tk.StringVar(value=""),
            "mva": tk.StringVar(value=""),
            "aliquota_interna_st": tk.StringVar(value=""),
            "aliquota_interestadual": tk.StringVar(value=""),
            "aliquota_interna_destino": tk.StringVar(value=""),
            "modalidade_difal": tk.StringVar(value="POR DENTRO"),
        }
        self.bool_vars: Dict[str, tk.BooleanVar] = {
            "aplicar_substituicoes": tk.BooleanVar(value=False),
            "incluir_ipi_base_icms": tk.BooleanVar(value=False),
            "calcular_fcp": tk.BooleanVar(value=True),
            "calcular_icms_st": tk.BooleanVar(value=False),
            "incluir_ipi_base_st": tk.BooleanVar(value=True),
            "calcular_difal": tk.BooleanVar(value=False),
            "aliquotas_difal_automaticas": tk.BooleanVar(value=True),
            "mercadoria_importada": tk.BooleanVar(value=False),
            "considerar_creditos_potenciais": tk.BooleanVar(value=False),
        }
        self.status_var = tk.StringVar(value="Informe o NCM e carregue a regra da Ficha Tributária.")
        self.descricao_ncm_var = tk.StringVar(value="Nenhum NCM carregado.")
        self.regra_var = tk.StringVar(value="Regra atual: não carregada | Reforma: não carregada")
        self.empresa_regime_info_var = tk.StringVar(
            value=EmpresasRegimesService.descricao_regime(empresa_inicial, regime_inicial)
        )
        self.resumo_vars = {
            "operacao": tk.StringVar(value="R$ 0,00"),
            "atual": tk.StringVar(value="R$ 0,00"),
            "reforma": tk.StringVar(value="R$ 0,00"),
            "diferenca": tk.StringVar(value="R$ 0,00"),
            "documento": tk.StringVar(value="R$ 0,00"),
            "confianca": tk.StringVar(value="0%"),
        }

        self.dados_ficha: Dict[str, Any] = {}
        self.resultado_atual: Optional[ResultadoSimulacao] = None
        self.cenarios: List[ResultadoSimulacao] = []

        self._criar_interface()
        self.bind("<Escape>", lambda _e: self.destroy())
        HistoricoSimuladorRepository.preparar_banco()
        self._atualizar_historico()
        if ncm:
            self.after(100, self.carregar_regra)

    def _criar_interface(self) -> None:
        cabecalho = ttk.Frame(self, padding=(14, 10))
        cabecalho.pack(fill=tk.X)
        ttk.Label(cabecalho, text="🧮 Simulador Tributário", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            cabecalho,
            text="Calcule e compare cenários usando as regras cadastradas na Ficha Tributária Inteligente.",
        ).pack(anchor="w", pady=(2, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        self.aba_simulacao = ttk.Frame(self.notebook, padding=8)
        self.aba_comparacao = ttk.Frame(self.notebook, padding=8)
        self.aba_historico = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.aba_simulacao, text="🧮 Simulação")
        self.notebook.add(self.aba_comparacao, text="📊 Comparação")
        self.notebook.add(self.aba_historico, text="🕘 Histórico")

        self._criar_aba_simulacao()
        self._criar_aba_comparacao()
        self._criar_aba_historico()

        rodape = ttk.Frame(self, padding=(12, 2, 12, 10))
        rodape.pack(fill=tk.X)
        ttk.Label(rodape, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

    def _criar_aba_simulacao(self) -> None:
        painel = ttk.Panedwindow(self.aba_simulacao, orient=tk.HORIZONTAL)
        painel.pack(fill=tk.BOTH, expand=True)
        esquerda = _FrameRolavel(painel)
        direita = ttk.Frame(painel, padding=(8, 0, 0, 0))
        painel.add(esquerda, weight=2)
        painel.add(direita, weight=3)
        self._criar_formulario(esquerda.interno)
        self._criar_resultado(direita)

    def _campo(self, master: tk.Misc, linha: int, rotulo: str, chave: str, largura: int = 18, coluna: int = 0) -> ttk.Entry:
        ttk.Label(master, text=rotulo, font=("Segoe UI", 9, "bold")).grid(row=linha, column=coluna, sticky="w", padx=(0, 5), pady=3)
        entrada = ttk.Entry(master, textvariable=self.vars[chave], width=largura)
        entrada.grid(row=linha, column=coluna + 1, sticky="ew", padx=(0, 10), pady=3)
        return entrada

    def _combo(self, master: tk.Misc, linha: int, rotulo: str, chave: str, valores, coluna: int = 0, largura: int = 20, editavel: bool = False) -> ttk.Combobox:
        ttk.Label(master, text=rotulo, font=("Segoe UI", 9, "bold")).grid(row=linha, column=coluna, sticky="w", padx=(0, 5), pady=3)
        combo = ttk.Combobox(master, textvariable=self.vars[chave], values=valores, width=largura, state="normal" if editavel else "readonly")
        combo.grid(row=linha, column=coluna + 1, sticky="ew", padx=(0, 10), pady=3)
        return combo

    def _criar_formulario(self, master: ttk.Frame) -> None:
        contexto = ttk.LabelFrame(master, text="Contexto e Ficha Tributária", padding=10)
        contexto.pack(fill=tk.X, pady=(0, 8))
        self._campo(contexto, 0, "NCM", "ncm", 15)
        ttk.Button(contexto, text="🔎 Carregar regra", command=self.carregar_regra).grid(row=0, column=2, padx=4, pady=3, sticky="w")
        ttk.Button(contexto, text="🧾 Abrir ficha", command=self.abrir_ficha).grid(row=0, column=3, padx=4, pady=3, sticky="w")
        ttk.Label(contexto, textvariable=self.descricao_ncm_var, wraplength=470).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 6))
        self.combo_empresa = self._combo(
            contexto, 2, "Empresa", "empresa",
            EmpresasRegimesService.listar_empresas(incluir_todas=True),
            largura=34, editavel=True,
        )
        self.combo_empresa.bind("<<ComboboxSelected>>", self._empresa_alterada)
        self.combo_empresa.bind("<FocusOut>", self._empresa_alterada)
        self._combo(contexto, 3, "Regime", "regime", _REGIMES, editavel=True)
        self._combo(contexto, 3, "Operação", "operacao", _OPERACOES, coluna=2, editavel=True)
        self._combo(contexto, 4, "Finalidade", "finalidade", _FINALIDADES, editavel=True)
        self._combo(contexto, 4, "Destinatário", "contribuinte", _CONTRIBUINTES, coluna=2)
        self._combo(contexto, 5, "UF origem", "uf_origem", _UFS)
        self._combo(contexto, 5, "UF destino", "uf_destino", _UFS, coluna=2)
        self._campo(contexto, 6, "Data operação", "data_operacao", 14)
        self._campo(contexto, 6, "Nome do cenário", "descricao_cenario", 24, coluna=2)
        contexto.columnconfigure(1, weight=1)
        contexto.columnconfigure(3, weight=1)
        ttk.Label(
            contexto, textvariable=self.empresa_regime_info_var, foreground="#1F4E78",
            font=("Segoe UI", 9, "bold"), wraplength=470,
        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=(5, 0))
        ttk.Label(contexto, textvariable=self.regra_var, wraplength=470).grid(row=8, column=0, columnspan=4, sticky="w", pady=(5, 0))

        valores = ttk.LabelFrame(master, text="Valores da operação", padding=10)
        valores.pack(fill=tk.X, pady=(0, 8))
        self._campo(valores, 0, "Quantidade", "quantidade")
        self._campo(valores, 0, "Valor unitário", "valor_unitario", coluna=2)
        self._campo(valores, 1, "Desconto", "desconto")
        self._campo(valores, 1, "Frete", "frete", coluna=2)
        self._campo(valores, 2, "Seguro", "seguro")
        self._campo(valores, 2, "Outras despesas", "outras_despesas", coluna=2)
        valores.columnconfigure(1, weight=1)
        valores.columnconfigure(3, weight=1)

        bases = ttk.LabelFrame(master, text="Bases manuais (opcionais)", padding=10)
        bases.pack(fill=tk.X, pady=(0, 8))
        self._campo(bases, 0, "Base ICMS", "base_icms_manual")
        self._campo(bases, 0, "Base PIS/COFINS", "base_pis_cofins_manual", coluna=2)
        self._campo(bases, 1, "Base IPI", "base_ipi_manual")
        self._campo(bases, 1, "Base IBS/CBS", "base_reforma_manual", coluna=2)
        self._campo(bases, 2, "Base DIFAL", "base_difal_manual")
        ttk.Checkbutton(bases, text="Incluir IPI na base do ICMS", variable=self.bool_vars["incluir_ipi_base_icms"]).grid(row=2, column=2, columnspan=2, sticky="w", pady=3)
        bases.columnconfigure(1, weight=1)
        bases.columnconfigure(3, weight=1)

        aliquotas = ttk.LabelFrame(master, text="Alíquotas carregadas / substituições", padding=10)
        aliquotas.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(
            aliquotas,
            text="Usar os valores abaixo como substituição manual das regras da ficha",
            variable=self.bool_vars["aplicar_substituicoes"],
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 5))
        self._campo(aliquotas, 1, "ICMS %", "aliquota_icms_override")
        self._campo(aliquotas, 1, "FCP %", "aliquota_fcp_override", coluna=2)
        self._campo(aliquotas, 2, "PIS %", "aliquota_pis_override")
        self._campo(aliquotas, 2, "COFINS %", "aliquota_cofins_override", coluna=2)
        self._campo(aliquotas, 3, "IPI %", "aliquota_ipi_override")
        self._campo(aliquotas, 3, "IBS %", "aliquota_ibs_override", coluna=2)
        self._campo(aliquotas, 4, "CBS %", "aliquota_cbs_override")
        self._campo(aliquotas, 4, "Redução IBS %", "reducao_ibs_override", coluna=2)
        self._campo(aliquotas, 5, "Redução CBS %", "reducao_cbs_override")
        ttk.Checkbutton(aliquotas, text="Calcular FCP", variable=self.bool_vars["calcular_fcp"]).grid(row=5, column=2, columnspan=2, sticky="w", pady=3)
        aliquotas.columnconfigure(1, weight=1)
        aliquotas.columnconfigure(3, weight=1)

        especiais = ttk.LabelFrame(master, text="ICMS-ST, DIFAL e créditos", padding=10)
        especiais.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(especiais, text="Calcular ICMS-ST", variable=self.bool_vars["calcular_icms_st"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(especiais, text="Incluir IPI na base de ST", variable=self.bool_vars["incluir_ipi_base_st"]).grid(row=0, column=2, columnspan=2, sticky="w", pady=3)
        self._campo(especiais, 1, "MVA %", "mva")
        self._campo(especiais, 1, "Alíquota interna ST %", "aliquota_interna_st", coluna=2)
        self._campo(especiais, 2, "Alíquota interestadual %", "aliquota_interestadual")
        ttk.Checkbutton(especiais, text="Calcular DIFAL", variable=self.bool_vars["calcular_difal"]).grid(row=2, column=2, columnspan=2, sticky="w", pady=3)
        self._campo(especiais, 3, "Alíquota interna destino %", "aliquota_interna_destino")
        self._combo(especiais, 3, "Modalidade DIFAL", "modalidade_difal", ("POR DENTRO", "POR FORA"), coluna=2)
        ttk.Checkbutton(
            especiais, text="Preencher alíquotas automaticamente",
            variable=self.bool_vars["aliquotas_difal_automaticas"],
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(
            especiais, text="Mercadoria importada (interestadual 4%)",
            variable=self.bool_vars["mercadoria_importada"],
        ).grid(row=4, column=2, columnspan=2, sticky="w", pady=3)
        ttk.Button(
            especiais, text="⚡ Preencher DIFAL automático", command=self.preencher_difal_automatico,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 3))
        ttk.Checkbutton(
            especiais,
            text="Estimar créditos potenciais (somente informativo)",
            variable=self.bool_vars["considerar_creditos_potenciais"],
        ).grid(row=5, column=2, columnspan=2, sticky="w", pady=3)
        ttk.Label(
            especiais, text=f"Fonte da tabela automática: {FONTE_TABELA_DIFAL}", wraplength=470,
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(4, 0))
        especiais.columnconfigure(1, weight=1)
        especiais.columnconfigure(3, weight=1)

        acoes = ttk.Frame(master)
        acoes.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(acoes, text="🧮 Simular operação", command=self.simular).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(acoes, text="💾 Salvar no histórico", command=self.salvar_historico).pack(side=tk.LEFT, padx=5)
        ttk.Button(acoes, text="➕ Adicionar à comparação", command=self.adicionar_comparacao).pack(side=tk.LEFT, padx=5)
        ttk.Button(acoes, text="Limpar valores", command=self.limpar_valores).pack(side=tk.RIGHT)

    def _criar_resultado(self, master: ttk.Frame) -> None:
        resumo = ttk.LabelFrame(master, text="Resumo do cenário", padding=8)
        resumo.pack(fill=tk.X, pady=(0, 8))
        itens = (
            ("Valor da operação", "operacao"), ("Tributos atuais", "atual"),
            ("IBS/CBS", "reforma"), ("Diferença", "diferenca"),
            ("Documento estimado", "documento"), ("Confiança", "confianca"),
        )
        for indice, (rotulo, chave) in enumerate(itens):
            frame = ttk.Frame(resumo, padding=5)
            frame.grid(row=indice // 3, column=indice % 3, sticky="nsew", padx=3, pady=3)
            ttk.Label(frame, text=rotulo, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            ttk.Label(frame, textvariable=self.resumo_vars[chave], font=("Segoe UI", 13, "bold")).pack(anchor="w")
            resumo.columnconfigure(indice % 3, weight=1)

        quadro = ttk.LabelFrame(master, text="Memória de cálculo", padding=6)
        quadro.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        colunas = ("tributo", "base", "aliquota", "valor", "observacao")
        self.tree_resultado = ttk.Treeview(quadro, columns=colunas, show="headings", selectmode="browse")
        larguras = {"tributo": 120, "base": 110, "aliquota": 90, "valor": 110, "observacao": 310}
        cabecalhos = {"tributo": "Tributo", "base": "Base", "aliquota": "Alíquota", "valor": "Valor", "observacao": "Observação"}
        for coluna in colunas:
            self.tree_resultado.heading(coluna, text=cabecalhos[coluna])
            self.tree_resultado.column(coluna, width=larguras[coluna], anchor="w", stretch=coluna == "observacao")
        barra_y = ttk.Scrollbar(quadro, orient=tk.VERTICAL, command=self.tree_resultado.yview)
        barra_x = ttk.Scrollbar(quadro, orient=tk.HORIZONTAL, command=self.tree_resultado.xview)
        self.tree_resultado.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        self.tree_resultado.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)

        avisos = ttk.LabelFrame(master, text="Premissas e alertas", padding=6)
        avisos.pack(fill=tk.BOTH, expand=False)
        self.texto_avisos = tk.Text(avisos, height=10, wrap=tk.WORD, font=("Segoe UI", 9), state=tk.DISABLED)
        barra = ttk.Scrollbar(avisos, orient=tk.VERTICAL, command=self.texto_avisos.yview)
        self.texto_avisos.configure(yscrollcommand=barra.set)
        self.texto_avisos.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        barra.pack(side=tk.RIGHT, fill=tk.Y)

    def _criar_aba_comparacao(self) -> None:
        acoes = ttk.Frame(self.aba_comparacao)
        acoes.pack(fill=tk.X, pady=(0, 7))
        ttk.Button(acoes, text="➕ Adicionar cenário atual", command=self.adicionar_comparacao).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(acoes, text="🗑 Remover selecionado", command=self.remover_comparacao).pack(side=tk.LEFT, padx=5)
        ttk.Button(acoes, text="Limpar comparação", command=self.limpar_comparacao).pack(side=tk.LEFT, padx=5)
        ttk.Button(acoes, text="📊 Exportar Excel", command=self.exportar_excel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(acoes, text="📄 Exportar PDF", command=self.exportar_pdf).pack(side=tk.RIGHT, padx=5)

        colunas = ("cenario", "ncm", "uf", "regime", "operacao", "valor", "atual", "carga_atual", "reforma", "carga_reforma", "diferenca", "documento", "confianca")
        self.tree_comparacao = ttk.Treeview(self.aba_comparacao, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "cenario": "Cenário", "ncm": "NCM", "uf": "UF", "regime": "Regime", "operacao": "Operação",
            "valor": "Valor operação", "atual": "Tributos atuais", "carga_atual": "Carga atual", "reforma": "IBS/CBS",
            "carga_reforma": "Carga reforma", "diferenca": "Diferença", "documento": "Documento estimado", "confianca": "Confiança",
        }
        larguras = {"cenario": 200, "ncm": 90, "uf": 95, "regime": 145, "operacao": 100, "valor": 115, "atual": 115, "carga_atual": 95, "reforma": 110, "carga_reforma": 105, "diferenca": 110, "documento": 125, "confianca": 85}
        for coluna in colunas:
            self.tree_comparacao.heading(coluna, text=titulos[coluna])
            self.tree_comparacao.column(coluna, width=larguras[coluna], anchor="w", stretch=False)
        barra_y = ttk.Scrollbar(self.aba_comparacao, orient=tk.VERTICAL, command=self.tree_comparacao.yview)
        barra_x = ttk.Scrollbar(self.aba_comparacao, orient=tk.HORIZONTAL, command=self.tree_comparacao.xview)
        self.tree_comparacao.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        self.tree_comparacao.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        barra_y.place(relx=1.0, rely=0.055, relheight=0.9, anchor="ne")
        barra_x.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(
            self.aba_comparacao,
            text="A diferença compara a soma demonstrativa do sistema atual com IBS/CBS. Confirme sempre a legislação e o período de transição.",
        ).pack(anchor="w", pady=(7, 0))

    def _criar_aba_historico(self) -> None:
        acoes = ttk.Frame(self.aba_historico)
        acoes.pack(fill=tk.X, pady=(0, 7))
        ttk.Label(acoes, text="Filtrar NCM:").pack(side=tk.LEFT)
        self.filtro_historico_var = tk.StringVar(value="")
        ttk.Entry(acoes, textvariable=self.filtro_historico_var, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(acoes, text="↻ Atualizar", command=self._atualizar_historico).pack(side=tk.LEFT, padx=4)
        ttk.Button(acoes, text="📂 Abrir selecionado", command=self.abrir_historico).pack(side=tk.LEFT, padx=4)
        ttk.Button(acoes, text="🗑 Excluir", command=self.excluir_historico).pack(side=tk.LEFT, padx=4)
        colunas = ("id", "data", "cenario", "ncm", "empresa", "regime", "operacao", "uf", "valor", "atual", "reforma", "diferenca", "confianca")
        self.tree_historico = ttk.Treeview(self.aba_historico, columns=colunas, show="headings", selectmode="browse")
        titulos = {"id": "ID", "data": "Criado em", "cenario": "Cenário", "ncm": "NCM", "empresa": "Empresa", "regime": "Regime", "operacao": "Operação", "uf": "UF", "valor": "Valor operação", "atual": "Tributos atuais", "reforma": "IBS/CBS", "diferenca": "Diferença", "confianca": "Confiança"}
        larguras = {"id": 55, "data": 130, "cenario": 190, "ncm": 90, "empresa": 180, "regime": 140, "operacao": 100, "uf": 90, "valor": 115, "atual": 115, "reforma": 110, "diferenca": 110, "confianca": 85}
        for coluna in colunas:
            self.tree_historico.heading(coluna, text=titulos[coluna])
            self.tree_historico.column(coluna, width=larguras[coluna], anchor="w", stretch=False)
        barra_y = ttk.Scrollbar(self.aba_historico, orient=tk.VERTICAL, command=self.tree_historico.yview)
        barra_x = ttk.Scrollbar(self.aba_historico, orient=tk.HORIZONTAL, command=self.tree_historico.xview)
        self.tree_historico.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        self.tree_historico.pack(fill=tk.BOTH, expand=True)
        barra_y.place(relx=1.0, rely=0.055, relheight=0.9, anchor="ne")
        barra_x.pack(fill=tk.X)
        self.tree_historico.bind("<Double-1>", lambda _e: self.abrir_historico())

    def _empresa_alterada(self, _evento=None) -> None:
        empresa = self.vars["empresa"].get().strip()
        perfil = EmpresasRegimesService.obter_perfil(empresa)
        if perfil is not None:
            self.vars["regime"].set(perfil.regime)
        self.empresa_regime_info_var.set(
            EmpresasRegimesService.descricao_regime(empresa, self.vars["regime"].get())
        )

    def _contexto_atual(self) -> Dict[str, str]:
        contexto = {chave: self.vars[chave].get().strip() for chave in ("empresa", "regime", "operacao", "finalidade", "uf_origem", "uf_destino", "contribuinte", "data_operacao")}
        if contexto["empresa"] == "Todas as empresas":
            contexto["empresa"] = ""
        contexto = EmpresasRegimesService.aplicar_contexto(contexto)
        if contexto.get("regime"):
            self.vars["regime"].set(str(contexto["regime"]))
        return contexto

    def carregar_regra(self) -> None:
        try:
            ncm = FichaTributariaRepository.normalizar_ncm(self.vars["ncm"].get())
            empresa_txt = self.vars["empresa"].get().strip()
            empresa = "" if empresa_txt in {"", "Todas as empresas"} else empresa_txt
            self.dados_ficha = FichaTributariaRepository.carregar_ficha(ncm, empresa=empresa)
            empresas = list(EmpresasRegimesService.listar_empresas(incluir_todas=True))
            vistos = {item.casefold() for item in empresas}
            for nome in self.dados_ficha.get("empresas", []):
                texto = str(nome or "").strip()
                if texto and texto.casefold() not in vistos:
                    empresas.append(texto)
                    vistos.add(texto.casefold())
            self.combo_empresa.configure(values=empresas)
            self._empresa_alterada()
            parecer = MotorParecer.gerar(self.dados_ficha, self._contexto_atual())
            regra = parecer.tributacao_atual
            reforma = parecer.reforma
            mapeamento = {
                "aliquota_icms_override": regra.get("ICMS"),
                "aliquota_fcp_override": regra.get("FCP"),
                "aliquota_pis_override": regra.get("PIS"),
                "aliquota_cofins_override": regra.get("COFINS"),
                "aliquota_ipi_override": regra.get("IPI"),
                "aliquota_ibs_override": reforma.get("IBS"),
                "aliquota_cbs_override": reforma.get("CBS"),
                "reducao_ibs_override": reforma.get("Redução IBS"),
                "reducao_cbs_override": reforma.get("Redução CBS"),
            }
            for chave, valor in mapeamento.items():
                self.vars[chave].set(_numero_br(valor))
            dados = self.dados_ficha.get("dados_gerais", {})
            self.descricao_ncm_var.set(f"NCM {ncm} — {dados.get('descricao') or 'Descrição não cadastrada'}")
            self.regra_var.set(
                f"Regra atual: {regra.get('ID da regra') or 'não localizada'} | aderência {regra.get('Aderência ao contexto') or '0%'} | "
                f"Reforma: {reforma.get('ID da regra') or 'não localizada'} | aderência {reforma.get('Aderência ao contexto') or '0%'}"
            )
            self.status_var.set("Ficha carregada. As alíquotas exibidas só substituem a regra quando a opção manual estiver marcada.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível carregar a regra:\n{erro}", parent=self)
            self.status_var.set("Falha ao carregar a Ficha Tributária.")

    def abrir_ficha(self) -> None:
        try:
            from src.ui.janela_ficha_tributaria import JanelaFichaTributaria
            JanelaFichaTributaria(self, ncm=self.vars["ncm"].get(), contexto=self._contexto_atual())
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def preencher_difal_automatico(self, exibir_mensagem: bool = True) -> bool:
        try:
            interna, interestadual = aliquotas_automaticas(
                self.vars["uf_origem"].get(),
                self.vars["uf_destino"].get(),
                self.bool_vars["mercadoria_importada"].get(),
            )
            self.vars["aliquota_interna_destino"].set(_numero_br(interna))
            self.vars["aliquota_interestadual"].set(_numero_br(interestadual))
            self.bool_vars["aliquotas_difal_automaticas"].set(True)
            self.bool_vars["calcular_difal"].set(True)
            if interestadual == Decimal("0"):
                texto = "Origem e destino são iguais. O DIFAL será mantido em zero."
            else:
                texto = (
                    f"DIFAL automático preenchido: interna {_numero_br(interna)}% | "
                    f"interestadual {_numero_br(interestadual)}% | {self.vars['modalidade_difal'].get()}."
                )
            self.status_var.set(texto)
            if exibir_mensagem:
                messagebox.showinfo("FiscalPro", texto, parent=self)
            return True
        except Exception as erro:
            if exibir_mensagem:
                messagebox.showerror("FiscalPro", f"Não foi possível preencher o DIFAL:\n{erro}", parent=self)
            self.status_var.set("Não foi possível preencher as alíquotas automáticas do DIFAL.")
            return False

    def _dados_entrada(self) -> Dict[str, Any]:
        dados = {chave: var.get().strip() for chave, var in self.vars.items()}
        if not self.bool_vars["aplicar_substituicoes"].get():
            for chave in (
                "aliquota_icms_override", "aliquota_fcp_override", "aliquota_pis_override", "aliquota_cofins_override",
                "aliquota_ipi_override", "aliquota_ibs_override", "aliquota_cbs_override", "reducao_ibs_override", "reducao_cbs_override",
            ):
                dados[chave] = ""
        for chave, var in self.bool_vars.items():
            if chave != "aplicar_substituicoes":
                dados[chave] = var.get()
        return dados

    def simular(self) -> None:
        try:
            if self.bool_vars["calcular_difal"].get() and self.bool_vars["aliquotas_difal_automaticas"].get():
                if not self.preencher_difal_automatico(exibir_mensagem=False):
                    return
            ncm = FichaTributariaRepository.normalizar_ncm(self.vars["ncm"].get())
            empresa_txt = self.vars["empresa"].get().strip()
            empresa = "" if empresa_txt in {"", "Todas as empresas"} else empresa_txt
            self.dados_ficha = FichaTributariaRepository.carregar_ficha(ncm, empresa=empresa)
            entrada = EntradaSimulacao.de_dict(self._dados_entrada())
            self.resultado_atual = MotorSimuladorTributario.simular(self.dados_ficha, entrada)
            self._mostrar_resultado(self.resultado_atual)
            self.status_var.set("Simulação concluída. Revise as premissas antes de usar os valores.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível simular:\n{erro}", parent=self)
            self.status_var.set("A simulação não foi concluída.")

    def _mostrar_resultado(self, resultado: ResultadoSimulacao) -> None:
        self.tree_resultado.delete(*self.tree_resultado.get_children())
        for linha in resultado.linhas:
            self.tree_resultado.insert("", tk.END, values=(
                linha.tributo, _moeda(linha.base), _numero_br(linha.aliquota) + "%", _moeda(linha.valor), linha.observacao,
            ))
        self.resumo_vars["operacao"].set(_moeda(resultado.valor_operacao))
        self.resumo_vars["atual"].set(f"{_moeda(resultado.total_tributos_atual)} ({_numero_br(resultado.carga_percentual_atual, 2)}%)")
        self.resumo_vars["reforma"].set(f"{_moeda(resultado.total_reforma)} ({_numero_br(resultado.carga_percentual_reforma, 2)}%)")
        self.resumo_vars["diferenca"].set(_moeda(resultado.diferenca_reforma_atual))
        self.resumo_vars["documento"].set(_moeda(resultado.valor_estimado_documento))
        self.resumo_vars["confianca"].set(f"{_numero_br(resultado.confiabilidade, 0)}% — {resultado.nivel_confiabilidade}")
        self.regra_var.set(
            f"Regra atual: {resultado.regra_atual_id or 'não localizada'} | aderência {resultado.aderencia_regra_atual} | "
            f"Reforma: {resultado.regra_reforma_id or 'não localizada'} | aderência {resultado.aderencia_regra_reforma}"
        )
        self.descricao_ncm_var.set(f"NCM {resultado.entrada.ncm} — {resultado.descricao_ncm}")
        self.texto_avisos.configure(state=tk.NORMAL)
        self.texto_avisos.delete("1.0", tk.END)
        self.texto_avisos.insert(tk.END, "PREMISSAS\n" + "=" * 70 + "\n")
        for texto in resultado.premissas:
            self.texto_avisos.insert(tk.END, f"• {texto}\n")
        self.texto_avisos.insert(tk.END, "\nALERTAS\n" + "=" * 70 + "\n")
        if resultado.alertas:
            for texto in resultado.alertas:
                self.texto_avisos.insert(tk.END, f"⚠ {texto}\n")
        else:
            self.texto_avisos.insert(tk.END, "Nenhum alerta adicional foi gerado.\n")
        self.texto_avisos.configure(state=tk.DISABLED)

    def salvar_historico(self) -> None:
        if self.resultado_atual is None:
            self.simular()
        if self.resultado_atual is None:
            return
        try:
            registro_id = HistoricoSimuladorRepository.salvar(self.resultado_atual)
            self._atualizar_historico()
            self.status_var.set(f"Simulação salva no histórico com o ID {registro_id}.")
            messagebox.showinfo("FiscalPro", f"Cenário salvo no histórico com o ID {registro_id}.", parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def adicionar_comparacao(self) -> None:
        if self.resultado_atual is None:
            self.simular()
        if self.resultado_atual is None:
            return
        self.cenarios.append(self.resultado_atual)
        self._atualizar_comparacao()
        self.notebook.select(self.aba_comparacao)
        self.status_var.set(f"Cenário adicionado. A comparação possui {len(self.cenarios)} cenário(s).")

    def _atualizar_comparacao(self) -> None:
        self.tree_comparacao.delete(*self.tree_comparacao.get_children())
        for indice, item in enumerate(MotorSimuladorTributario.comparar(self.cenarios)):
            self.tree_comparacao.insert("", tk.END, iid=str(indice), values=(
                item["cenario"], item["ncm"], item["uf"], item["regime"], item["operacao"],
                _moeda(item["valor_operacao"]), _moeda(item["tributos_atual"]), _numero_br(item["carga_atual"], 2) + "%",
                _moeda(item["reforma"]), _numero_br(item["carga_reforma"], 2) + "%", _moeda(item["diferenca"]),
                _moeda(item["valor_documento"]), _numero_br(item["confiabilidade"], 0) + "%",
            ))

    def remover_comparacao(self) -> None:
        selecionado = self.tree_comparacao.selection()
        if not selecionado:
            return
        indice = int(selecionado[0])
        if 0 <= indice < len(self.cenarios):
            self.cenarios.pop(indice)
        self._atualizar_comparacao()

    def limpar_comparacao(self) -> None:
        self.cenarios.clear()
        self._atualizar_comparacao()

    def exportar_excel(self) -> None:
        resultados = self.cenarios or ([self.resultado_atual] if self.resultado_atual else [])
        if not resultados:
            messagebox.showwarning("FiscalPro", "Simule ao menos um cenário antes de exportar.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            parent=self, title="Salvar comparação tributária", defaultextension=".xlsx",
            filetypes=[("Planilha Excel", "*.xlsx")], initialfile="SIMULACAO_TRIBUTARIA.xlsx",
        )
        if not caminho:
            return
        try:
            ExportadorSimulacao.para_excel(resultados, caminho)
            messagebox.showinfo("FiscalPro", f"Excel gerado com sucesso:\n{caminho}", parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def exportar_pdf(self) -> None:
        resultados = self.cenarios or ([self.resultado_atual] if self.resultado_atual else [])
        if not resultados:
            messagebox.showwarning("FiscalPro", "Simule ao menos um cenário antes de exportar.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            parent=self, title="Salvar simulação tributária", defaultextension=".pdf",
            filetypes=[("Documento PDF", "*.pdf")], initialfile="SIMULACAO_TRIBUTARIA.pdf",
        )
        if not caminho:
            return
        try:
            ExportadorSimulacao.para_pdf(resultados, caminho)
            messagebox.showinfo("FiscalPro", f"PDF gerado com sucesso:\n{caminho}", parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def _atualizar_historico(self) -> None:
        if not hasattr(self, "tree_historico"):
            return
        self.tree_historico.delete(*self.tree_historico.get_children())
        try:
            linhas = HistoricoSimuladorRepository.listar(self.filtro_historico_var.get(), limite=300)
            for item in linhas:
                self.tree_historico.insert("", tk.END, iid=str(item["id"]), values=(
                    item["id"], item.get("criado_em") or "", item.get("descricao_cenario") or "",
                    item.get("ncm") or "", item.get("empresa") or "", item.get("regime") or "",
                    item.get("operacao") or "", f"{item.get('uf_origem') or ''} → {item.get('uf_destino') or ''}",
                    _moeda(item.get("valor_operacao")), _moeda(item.get("total_tributos_atual")),
                    _moeda(item.get("total_reforma")), _moeda(item.get("diferenca")),
                    _numero_br(item.get("confiabilidade"), 0) + "%",
                ))
        except Exception as erro:
            self.status_var.set(f"Não foi possível carregar o histórico: {erro}")

    def abrir_historico(self) -> None:
        selecionado = self.tree_historico.selection()
        if not selecionado:
            return
        try:
            resultado = HistoricoSimuladorRepository.buscar(int(selecionado[0]))
            if resultado is None:
                raise ValueError("Simulação não encontrada.")
            self._preencher_entrada(resultado.entrada)
            self.resultado_atual = resultado
            self._mostrar_resultado(resultado)
            self.notebook.select(self.aba_simulacao)
            self.status_var.set(f"Simulação histórica ID {selecionado[0]} carregada.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def excluir_historico(self) -> None:
        selecionado = self.tree_historico.selection()
        if not selecionado:
            return
        if not messagebox.askyesno("FiscalPro", "Excluir a simulação selecionada do histórico?", parent=self):
            return
        HistoricoSimuladorRepository.excluir(int(selecionado[0]))
        self._atualizar_historico()

    def _preencher_entrada(self, entrada: EntradaSimulacao) -> None:
        dados = entrada.para_dict()
        for chave, var in self.vars.items():
            if chave in dados:
                valor = dados[chave]
                if chave == "data_operacao":
                    valor = _data_br(valor)
                elif chave not in {"ncm", "empresa", "regime", "operacao", "finalidade", "uf_origem", "uf_destino", "contribuinte", "descricao_cenario", "modalidade_difal"}:
                    valor = _numero_br(valor)
                var.set(str(valor))
        for chave, var in self.bool_vars.items():
            if chave in dados:
                var.set(bool(dados[chave]))

    def limpar_valores(self) -> None:
        for chave in ("valor_unitario", "desconto", "frete", "seguro", "outras_despesas"):
            self.vars[chave].set("0,00")
        self.vars["quantidade"].set("1")
        for chave in ("base_icms_manual", "base_pis_cofins_manual", "base_ipi_manual", "base_reforma_manual", "base_difal_manual", "mva", "aliquota_interna_st", "aliquota_interestadual", "aliquota_interna_destino"):
            self.vars[chave].set("")
        self.resultado_atual = None
        self.tree_resultado.delete(*self.tree_resultado.get_children())
        for var in self.resumo_vars.values():
            var.set("R$ 0,00")
        self.resumo_vars["confianca"].set("0%")
        self.status_var.set("Valores limpos. A regra carregada foi mantida.")


__all__ = ["JanelaSimuladorTributario"]
