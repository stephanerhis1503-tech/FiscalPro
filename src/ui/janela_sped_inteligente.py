from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Frame, Label, StringVar, Text, Toplevel, filedialog, messagebox, simpledialog, ttk

from src.sped import MotorSPED
from src.services.cte_sped_sem_credito_service import process as processar_cte_sem_credito
from .estilos import COR_CARD, COR_FUNDO, COR_PRIMARIA, COR_TEXTO, FONTE_NORMAL, FONTE_TITULO
from .layout_responsivo import dimensionar_janela, vincular_wraplength
from .painel_detalhes import abrir_detalhes_ampliados


class JanelaSPEDInteligente(Toplevel):
    REGISTROS_DESTAQUE = ("0000", "0150", "0200", "C100", "C170", "C190", "D100", "E110", "H010", "9999")
    OPCOES_CODIGO_ESTORNO = {
        "MG50000100 — TTS / Regime Especial": "MG50000100",
        "MG50000999 — Outros ajustes (confirmar fundamento)": "MG50000999",
        "MG50000018 — Reproduzir modelo anterior (revisar FEM)": "MG50000018",
    }

    def __init__(self, master=None):
        super().__init__(master)
        self.title("FiscalPro — SPED Inteligente")
        dimensionar_janela(self, 1380, 900, 980, 620)
        self.configure(bg=COR_FUNDO)
        self.motor = MotorSPED()
        self.resultado = None
        self.analise_correcoes = None
        self.caminho_excel = None
        self.validacao_excel = None
        self.conferencia_excel = []
        self.conferencia_excel_filtrada = []
        self.conferencia_excel_executada = False
        self.filtro_conf_registro_var = StringVar(master=self, value="Todos")
        self.filtro_conf_tipo_var = StringVar(master=self, value="Todos")
        self.filtro_conf_categoria_var = StringVar(master=self, value="Todas")
        self.filtro_conf_busca_var = StringVar(master=self, value="")
        self.pre_validacao_pva = None
        self.preparacao_assistida = None
        self.importacao_cte_xml = None
        self.analise_chaves_cte = None
        self.importacao_nfe_xml = None
        self.auditoria_tributaria = None
        self.preparacao_correcao_tributaria = None
        self.analise_estorno_icms = None
        self.analise_danfe_icms = None
        self.analise_exclusao_icms_creditos = None
        self.auditoria_difal = None
        self.codigo_estorno_var = StringVar(master=self, value="MG50000100 — TTS / Regime Especial")

        # O rodapé de status é criado antes dos demais componentes. Assim,
        # qualquer callback de leitura já encontra a barra de progresso, mesmo
        # durante a montagem das abas ou após atualizações parciais do programa.
        self.progresso = None
        self.lbl_status = None
        self._criar_rodape_status()
        self._criar_interface()

    def _criar_rodape_status(self):
        """Cria o rodapé antes do restante da tela.

        A criação antecipada evita que callbacks do MotorSPED tentem atualizar
        ``self.progresso`` antes de o widget existir. O método é idempotente
        para também proteger reaberturas ou reconstruções futuras da interface.
        """
        if self.progresso is not None and self.lbl_status is not None:
            return

        rodape = Frame(self, bg=COR_FUNDO)
        rodape.pack(side="bottom", fill=X, padx=12, pady=(2, 7))
        self.progresso = ttk.Progressbar(rodape, maximum=100)
        self.progresso.pack(fill=X)
        self.lbl_status = Label(
            rodape, text="Pronto.", bg=COR_FUNDO, fg=COR_TEXTO,
            anchor="w", font=("Segoe UI", 9),
        )
        self.lbl_status.pack(fill=X, pady=(2, 0))

    def _criar_interface(self):
        """Monta a tela com comandos compactos e resultados expansíveis.

        Na Sprint 15.8, as antigas seis barras verticais de comandos foram
        reunidas em uma faixa de abas. Isso devolve a maior parte da altura da
        janela para as tabelas e relatórios de todas as etapas do SPED.
        """
        cabecalho = Frame(self, bg=COR_PRIMARIA, height=54)
        cabecalho.pack(fill=X)
        cabecalho.pack_propagate(False)
        Label(
            cabecalho,
            text="SPED Inteligente",
            bg=COR_PRIMARIA,
            fg="white",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(6, 0))
        Label(
            cabecalho,
            text="Leitura, auditoria, correções, pré-PVA e conversões em uma tela responsiva",
            bg=COR_PRIMARIA,
            fg="white",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20)

        comandos = ttk.Notebook(self)
        comandos.pack(fill=X, padx=8, pady=(6, 3))

        aba_comandos_sped = ttk.Frame(comandos, padding=(8, 5))
        aba_comandos_cte = ttk.Frame(comandos, padding=(8, 5))
        aba_comandos_aud = ttk.Frame(comandos, padding=(8, 5))
        aba_comandos_excel = ttk.Frame(comandos, padding=(8, 5))
        comandos.add(aba_comandos_sped, text="SPED")
        comandos.add(aba_comandos_cte, text="CT-e / XML")
        comandos.add(aba_comandos_aud, text="Auditoria tributária")
        comandos.add(aba_comandos_excel, text="Excel, PVA e correções")

        # Ações principais do SPED.
        ttk.Button(aba_comandos_sped, text="📂 Abrir SPED", command=self.abrir_sped).grid(row=0, column=0, sticky="ew")
        self.btn_exportar = ttk.Button(
            aba_comandos_sped, text="📊 Exportar Excel organizado",
            command=self.exportar_excel, state="disabled",
        )
        self.btn_exportar.grid(row=0, column=1, sticky="ew", padx=(7, 0))
        self.btn_analisar = ttk.Button(
            aba_comandos_sped, text="🔎 Analisar correções",
            command=self.analisar_correcoes, state="disabled",
        )
        self.btn_analisar.grid(row=0, column=2, sticky="ew", padx=(7, 0))
        self.btn_corrigir = ttk.Button(
            aba_comandos_sped, text="🛠 Gerar SPED corrigido",
            command=self.gerar_sped_corrigido, state="disabled",
        )
        self.btn_corrigir.grid(row=0, column=3, sticky="ew", padx=(7, 0))
        self.btn_estorno_icms = ttk.Button(
            aba_comandos_sped, text="↩ Estorno créditos ICMS",
            command=self.analisar_estorno_creditos_icms, state="disabled",
        )
        self.btn_estorno_icms.grid(row=0, column=4, sticky="ew", padx=(7, 0))
        self.lbl_arquivo = Label(
            aba_comandos_sped, text="Nenhum arquivo selecionado",
            bg=COR_FUNDO, fg=COR_TEXTO, font=FONTE_NORMAL,
            anchor="w", justify="left",
        )
        self.lbl_arquivo.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        for coluna in range(5):
            aba_comandos_sped.grid_columnconfigure(coluna, weight=1, uniform="cmd_sped")
        vincular_wraplength(self.lbl_arquivo, margem=30, minimo=420)

        # CT-e / XML.
        ttk.Button(aba_comandos_cte, text="📁 Pasta de XMLs", command=self.selecionar_pasta_xml_cte).grid(row=0, column=0, sticky="ew")
        ttk.Button(aba_comandos_cte, text="📦 XMLs ou ZIP", command=self.selecionar_xml_zip_cte).grid(row=0, column=1, sticky="ew", padx=(7, 0))
        self.btn_analisar_cte = ttk.Button(
            aba_comandos_cte, text="🔎 Conferir chaves",
            command=self.analisar_chaves_cte, state="disabled",
        )
        self.btn_analisar_cte.grid(row=0, column=2, sticky="ew", padx=(7, 0))
        self.btn_corrigir_cte = ttk.Button(
            aba_comandos_cte, text="🛠 Corrigir chaves",
            command=self.corrigir_chaves_cte, state="disabled",
        )
        self.btn_corrigir_cte.grid(row=0, column=3, sticky="ew", padx=(7, 0))
        self.btn_incluir_cte_sem_credito = ttk.Button(
            aba_comandos_cte, text="➕ Incluir CT-e sem crédito",
            command=self.incluir_ctes_sem_credito, state="disabled",
        )
        self.btn_incluir_cte_sem_credito.grid(row=0, column=4, sticky="ew", padx=(7, 0))
        self.lbl_cte = Label(
            aba_comandos_cte, text="Nenhum XML de CT-e importado",
            bg=COR_FUNDO, fg=COR_TEXTO, font=FONTE_NORMAL, anchor="w", justify="left",
        )
        self.lbl_cte.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        for coluna in range(5):
            aba_comandos_cte.grid_columnconfigure(coluna, weight=1, uniform="cmd_cte")
        vincular_wraplength(self.lbl_cte, margem=30, minimo=420)

        # Auditoria tributária.
        ttk.Button(aba_comandos_aud, text="📁 Pasta NF-e", command=self.selecionar_pasta_xml_nfe).grid(row=0, column=0, sticky="ew")
        ttk.Button(aba_comandos_aud, text="📦 XMLs NF-e ou ZIP", command=self.selecionar_xml_zip_nfe).grid(row=0, column=1, sticky="ew", padx=(7, 0))
        self.btn_auditar_tributacao = ttk.Button(
            aba_comandos_aud, text="🧠 Cruzar Ficha Tributária",
            command=self.executar_auditoria_tributaria, state="disabled",
        )
        self.btn_auditar_tributacao.grid(row=0, column=2, sticky="ew", padx=(7, 0))
        self.btn_relatorio_tributario = ttk.Button(
            aba_comandos_aud, text="💾 Salvar relatório",
            command=self.salvar_relatorio_tributario, state="disabled",
        )
        self.btn_relatorio_tributario.grid(row=0, column=3, sticky="ew", padx=(7, 0))
        self.btn_preparar_tributaria = ttk.Button(
            aba_comandos_aud, text="🧭 Preparar correções",
            command=self.preparar_correcoes_tributarias, state="disabled",
        )
        self.btn_preparar_tributaria.grid(row=0, column=4, sticky="ew", padx=(7, 0))
        self.lbl_auditoria_xml = Label(
            aba_comandos_aud,
            text="XML de NF-e opcional — a Ficha também pode ser cruzada somente com o SPED.",
            bg=COR_FUNDO, fg=COR_TEXTO, font=FONTE_NORMAL, anchor="w", justify="left",
        )
        self.lbl_auditoria_xml.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        ttk.Label(aba_comandos_aud, text="DIFAL", font=("Segoe UI", 8, "bold")).grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        self.btn_auditar_difal = ttk.Button(
            aba_comandos_aud, text="⚡ Auditar DIFAL automático",
            command=self.executar_auditoria_difal, state="disabled",
        )
        self.btn_auditar_difal.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(7, 0), pady=(6, 0))
        self.btn_relatorio_difal = ttk.Button(
            aba_comandos_aud, text="💾 Relatório DIFAL",
            command=self.salvar_relatorio_difal, state="disabled",
        )
        self.btn_relatorio_difal.grid(row=2, column=3, sticky="ew", padx=(7, 0), pady=(6, 0))
        self.btn_excel_difal = ttk.Button(
            aba_comandos_aud, text="📊 Exportar Excel",
            command=self.salvar_excel_difal, state="disabled",
        )
        self.btn_excel_difal.grid(row=2, column=4, sticky="ew", padx=(7, 0), pady=(6, 0))
        self.lbl_difal_comando = Label(
            aba_comandos_aud,
            text=("Abra um SPED Fiscal. Com XML a conferência é por chave; sem XML o FiscalPro calcula "
                  "uma memória estimada pelo SPED e pelas alíquotas vigentes."),
            bg=COR_FUNDO, fg=COR_TEXTO, font=("Segoe UI", 8), anchor="w", justify="left",
        )
        self.lbl_difal_comando.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(4, 0))
        for coluna in range(5):
            aba_comandos_aud.grid_columnconfigure(coluna, weight=1, uniform="cmd_aud")
        vincular_wraplength(self.lbl_auditoria_xml, margem=30, minimo=420)
        vincular_wraplength(self.lbl_difal_comando, margem=20, minimo=220)

        # Excel, pré-PVA e correção assistida no mesmo painel, sem consumir
        # a altura da área de resultados quando não estão em uso.
        ttk.Label(aba_comandos_excel, text="Excel → TXT", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        self.btn_importar_excel = ttk.Button(aba_comandos_excel, text="📥 Importar Excel", command=self.importar_excel)
        self.btn_importar_excel.grid(row=0, column=1, sticky="ew", padx=(7, 0))
        self.btn_validar_excel = ttk.Button(
            aba_comandos_excel, text="✅ Validar planilha", command=self.validar_excel, state="disabled"
        )
        self.btn_validar_excel.grid(row=0, column=2, sticky="ew", padx=(7, 0))
        self.btn_gerar_txt = ttk.Button(
            aba_comandos_excel, text="📝 Gerar SPED TXT", command=self.gerar_sped_txt, state="disabled"
        )
        self.btn_gerar_txt.grid(row=0, column=3, sticky="ew", padx=(7, 0))
        self.btn_conferir_excel = ttk.Button(
            aba_comandos_excel,
            text="🔎 Conferir alterações",
            command=self.conferir_alteracoes_excel,
            state="disabled",
        )
        self.btn_conferir_excel.grid(row=0, column=4, sticky="ew", padx=(7, 0))
        self.lbl_excel = Label(
            aba_comandos_excel, text="Nenhuma planilha selecionada",
            bg=COR_FUNDO, fg=COR_TEXTO, font=FONTE_NORMAL, anchor="w",
        )
        self.lbl_excel.grid(row=0, column=5, columnspan=3, sticky="ew", padx=(10, 0))

        ttk.Label(aba_comandos_excel, text="Pré-PVA", font=("Segoe UI", 8, "bold")).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.btn_validar_pva = ttk.Button(
            aba_comandos_excel, text="✅ Validar antes do PVA", command=self.validar_antes_pva, state="disabled"
        )
        self.btn_validar_pva.grid(row=1, column=1, sticky="ew", padx=(7, 0), pady=(6, 0))
        self.btn_relatorio_pva = ttk.Button(
            aba_comandos_excel, text="💾 Salvar relatório", command=self.salvar_relatorio_pva, state="disabled"
        )
        self.btn_relatorio_pva.grid(row=1, column=2, sticky="ew", padx=(7, 0), pady=(6, 0))
        self.lbl_pva = Label(
            aba_comandos_excel, text="Abra um SPED para executar a pré-validação.",
            bg=COR_FUNDO, fg=COR_TEXTO, font=("Segoe UI", 8), anchor="w",
        )
        self.lbl_pva.grid(row=1, column=3, sticky="ew", padx=(8, 4), pady=(6, 0))

        ttk.Label(aba_comandos_excel, text="Assistida", font=("Segoe UI", 8, "bold")).grid(row=1, column=4, sticky="w", padx=(8, 0), pady=(6, 0))
        self.btn_preparar_assistida = ttk.Button(
            aba_comandos_excel, text="🧭 Preparar", command=self.preparar_correcoes_assistidas, state="disabled"
        )
        self.btn_preparar_assistida.grid(row=1, column=5, sticky="ew", padx=(7, 0), pady=(6, 0))
        self.btn_aplicar_assistida = ttk.Button(
            aba_comandos_excel, text="🛠 Aplicar", command=self.aplicar_correcoes_assistidas, state="disabled"
        )
        self.btn_aplicar_assistida.grid(row=1, column=6, sticky="ew", padx=(7, 0), pady=(6, 0))
        self.lbl_assistida = Label(
            aba_comandos_excel, text="Valide o SPED para preparar sugestões.",
            bg=COR_FUNDO, fg=COR_TEXTO, font=("Segoe UI", 8), anchor="w",
        )
        self.lbl_assistida.grid(row=1, column=7, sticky="ew", padx=(8, 0), pady=(6, 0))

        ttk.Label(aba_comandos_excel, text="Créditos", font=("Segoe UI", 8, "bold")).grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        self.btn_excluir_icms_piscofins = ttk.Button(
            aba_comandos_excel,
            text="🧮 ICMS Fiscal → PIS/COFINS",
            command=self.excluir_icms_bases_piscofins,
            state="disabled",
        )
        self.btn_excluir_icms_piscofins.grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(7, 0), pady=(6, 0)
        )
        self.lbl_icms_piscofins = Label(
            aba_comandos_excel,
            text="Abra uma EFD Contribuições para importar o ICMS próprio do SPED Fiscal corrigido.",
            bg=COR_FUNDO, fg=COR_TEXTO, font=("Segoe UI", 8), anchor="w", justify="left",
        )
        self.lbl_icms_piscofins.grid(
            row=2, column=3, columnspan=5, sticky="ew", padx=(8, 0), pady=(6, 0)
        )
        for coluna in range(1, 8):
            aba_comandos_excel.grid_columnconfigure(coluna, weight=1)

        # Informações do arquivo em uma única faixa compacta.
        info = Frame(self, bg=COR_CARD, bd=1, relief="solid")
        info.pack(fill=X, padx=12, pady=(0, 5))
        self.lbl_empresa = self._campo_info(info, "Empresa", 0, 0)
        self.lbl_cnpj = self._campo_info(info, "CNPJ", 0, 1)
        self.lbl_periodo = self._campo_info(info, "Período", 0, 2)
        self.lbl_layout = self._campo_info(info, "Tipo / Layout", 0, 3)

        # Todas as abas de resultado recebem o espaço restante da janela.
        self.abas = ttk.Notebook(self)
        self.abas.pack(fill=BOTH, expand=True, padx=12, pady=(2, 2))

        self.aba_mapa = Frame(self.abas, bg=COR_FUNDO)
        self.aba_cte = Frame(self.abas, bg=COR_FUNDO)
        self.aba_correcoes = Frame(self.abas, bg=COR_FUNDO)
        self.aba_tributaria = Frame(self.abas, bg=COR_FUNDO)
        self.aba_difal = Frame(self.abas, bg=COR_FUNDO)
        self.aba_correcao_tributaria = Frame(self.abas, bg=COR_FUNDO)
        self.aba_estorno_icms = Frame(self.abas, bg=COR_FUNDO)
        self.aba_pre_pva = Frame(self.abas, bg=COR_FUNDO)
        self.aba_assistida = Frame(self.abas, bg=COR_FUNDO)
        self.aba_excel = Frame(self.abas, bg=COR_FUNDO)
        self.aba_conferencia_excel = Frame(self.abas, bg=COR_FUNDO)
        self.abas.add(self.aba_mapa, text="Mapa e diagnóstico")
        self.abas.add(self.aba_cte, text="Chaves CT-e / XML")
        self.abas.add(self.aba_correcoes, text="Correções inteligentes")
        self.abas.add(self.aba_tributaria, text="Auditoria Tributária")
        self.abas.add(self.aba_difal, text="DIFAL automático")
        self.abas.add(self.aba_correcao_tributaria, text="Correção Tributária")
        self.abas.add(self.aba_estorno_icms, text="Estorno ICMS")
        self.abas.add(self.aba_pre_pva, text="Pré-Validador PVA")
        self.abas.add(self.aba_assistida, text="Correção assistida")
        self.abas.add(self.aba_excel, text="Excel → TXT")
        self.abas.add(self.aba_conferencia_excel, text="Conferência Excel")

        self._criar_aba_mapa()
        self._criar_aba_cte()
        self._criar_aba_correcoes()
        self._criar_aba_tributaria()
        self._criar_aba_difal()
        self._criar_aba_correcao_tributaria()
        self._criar_aba_estorno_icms()
        self._criar_aba_pre_pva()
        self._criar_aba_assistida()
        self._criar_aba_excel()
        self._criar_aba_conferencia_excel()

    def _criar_aba_mapa(self):
        corpo = Frame(self.aba_mapa, bg=COR_FUNDO)
        corpo.pack(fill=BOTH, expand=True, padx=8, pady=8)

        esquerda = Frame(corpo, bg=COR_FUNDO)
        esquerda.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
        direita = Frame(corpo, bg=COR_FUNDO, width=360)
        direita.pack(side=LEFT, fill=Y, padx=(8, 0))

        frame_mapa = ttk.LabelFrame(esquerda, text="Mapa de registros")
        frame_mapa.pack(fill=BOTH, expand=True)
        self.tabela = ttk.Treeview(frame_mapa, columns=("registro", "quantidade"), show="headings", height=10)
        self.tabela.heading("registro", text="Registro")
        self.tabela.heading("quantidade", text="Quantidade")
        self.tabela.column("registro", width=180, anchor="center")
        self.tabela.column("quantidade", width=140, anchor="e")
        self.tabela.pack(fill=BOTH, expand=True, padx=8, pady=8)

        frame_resumo = ttk.LabelFrame(direita, text="Resumo")
        frame_resumo.pack(fill=X)
        self.lbl_resumo = Label(frame_resumo, text="Abra um arquivo SPED.", justify="left", anchor="nw", bg=COR_CARD, fg=COR_TEXTO, font=FONTE_NORMAL)
        self.lbl_resumo.pack(fill=X, padx=12, pady=12)

        frame_alertas = ttk.LabelFrame(direita, text="Diagnóstico inicial")
        frame_alertas.pack(fill=BOTH, expand=True, pady=(10, 0))
        self.txt_alertas = Text(frame_alertas, wrap="word", height=8, font=FONTE_NORMAL)
        self.txt_alertas.pack(fill=BOTH, expand=True, padx=8, pady=8)
        self.txt_alertas.configure(state="disabled")

    def _criar_aba_cte(self):
        topo = Frame(self.aba_cte, bg=COR_CARD, bd=1, relief="solid")
        topo.pack(fill=X, padx=6, pady=(6, 3))
        self.lbl_resumo_cte = Label(
            topo,
            text=(
                "Importe a pasta, os XMLs avulsos ou um ZIP de CT-e. O FiscalPro cruza número e "
                "série com o D100 e substitui somente chaves divergentes com correspondência única."
            ),
            justify="left",
            anchor="w",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        )
        self.lbl_resumo_cte.pack(fill=X, padx=12, pady=10)

        frame_tabela = ttk.LabelFrame(self.aba_cte, text="Conferência das chaves dos CT-e")
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))
        colunas = ("status", "linha", "numero", "serie", "chave_sped", "chave_xml", "arquivo")
        self.tabela_cte = ttk.Treeview(frame_tabela, columns=colunas, show="headings", height=10)
        titulos = {
            "status": "Situação",
            "linha": "Linha",
            "numero": "Nº CT-e",
            "serie": "Série",
            "chave_sped": "Chave no SPED",
            "chave_xml": "Chave no XML",
            "arquivo": "Arquivo XML",
        }
        larguras = {
            "status": 120, "linha": 75, "numero": 110, "serie": 70,
            "chave_sped": 330, "chave_xml": 330, "arquivo": 280,
        }
        for coluna in colunas:
            self.tabela_cte.heading(coluna, text=titulos[coluna])
            self.tabela_cte.column(coluna, width=larguras[coluna], anchor="w")
        self.tabela_cte.tag_configure("CORRIGIR", foreground="#B00020")
        self.tabela_cte.tag_configure("CORRETA", foreground="#0B6B2A")
        self.tabela_cte.tag_configure("NÃO ENCONTRADO", foreground="#8A5A00")
        self.tabela_cte.tag_configure("AMBÍGUO", foreground="#8A5A00")

        rolagem_y = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tabela_cte.yview)
        rolagem_x = ttk.Scrollbar(frame_tabela, orient="horizontal", command=self.tabela_cte.xview)
        self.tabela_cte.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)
        self.tabela_cte.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _criar_aba_correcoes(self):
        topo = Frame(self.aba_correcoes, bg=COR_CARD, bd=1, relief="solid")
        topo.pack(fill=X, padx=6, pady=(6, 3))
        self.lbl_resumo_correcoes = Label(
            topo,
            text=(
                "Abra um SPED e clique em “Analisar correções”. Nesta sprint, o FiscalPro corrige "
                "somente situações estruturais seguras; tributos e valores fiscais não são recalculados."
            ),
            justify="left",
            anchor="w",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        )
        self.lbl_resumo_correcoes.pack(fill=X, padx=12, pady=10)

        frame_tabela = ttk.LabelFrame(self.aba_correcoes, text="Problemas encontrados e ações sugeridas")
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))

        colunas = ("modo", "gravidade", "registro", "linha", "produto", "problema", "acao")
        self.tabela_correcoes = ttk.Treeview(frame_tabela, columns=colunas, show="headings", height=10)
        titulos = {
            "modo": "Tratamento",
            "gravidade": "Gravidade",
            "registro": "Registro",
            "linha": "Linha",
            "produto": "Produto",
            "problema": "Problema",
            "acao": "Ação",
        }
        larguras = {
            "modo": 115,
            "gravidade": 80,
            "registro": 70,
            "linha": 70,
            "produto": 110,
            "problema": 300,
            "acao": 370,
        }
        for coluna in colunas:
            self.tabela_correcoes.heading(coluna, text=titulos[coluna])
            self.tabela_correcoes.column(coluna, width=larguras[coluna], anchor="w")

        rolagem_y = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tabela_correcoes.yview)
        rolagem_x = ttk.Scrollbar(frame_tabela, orient="horizontal", command=self.tabela_correcoes.xview)
        self.tabela_correcoes.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)
        self.tabela_correcoes.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _criar_aba_tributaria(self):
        self.aud_empresa_var = StringVar(value="")
        self.aud_regime_var = StringVar(value="")
        self.aud_finalidade_var = StringVar(value="REVENDA")
        self.aud_contribuinte_var = StringVar(value="AUTOMÁTICO")
        self.aud_filtro_var = StringVar(value="Todos")
        self.mapa_auditoria_itens = {}

        contexto = ttk.LabelFrame(
            self.aba_tributaria,
            text="Contexto padrão para selecionar a regra da Ficha Tributária",
        )
        contexto.pack(fill=X, padx=6, pady=(6, 3))

        ttk.Label(contexto, text="Empresa:").grid(row=0, column=0, padx=(10, 4), pady=8, sticky="w")
        ttk.Entry(contexto, textvariable=self.aud_empresa_var, width=36).grid(
            row=0, column=1, padx=(0, 10), pady=8, sticky="ew"
        )
        ttk.Label(contexto, text="Regime:").grid(row=0, column=2, padx=(4, 4), pady=8, sticky="w")
        ttk.Combobox(
            contexto,
            textvariable=self.aud_regime_var,
            state="readonly",
            width=22,
            values=("", "LUCRO REAL", "LUCRO PRESUMIDO", "SIMPLES NACIONAL", "MEI", "OUTRO"),
        ).grid(row=0, column=3, padx=(0, 10), pady=8, sticky="w")
        ttk.Label(contexto, text="Finalidade:").grid(row=0, column=4, padx=(4, 4), pady=8, sticky="w")
        ttk.Combobox(
            contexto,
            textvariable=self.aud_finalidade_var,
            state="readonly",
            width=20,
            values=("", "REVENDA", "INDUSTRIALIZAÇÃO", "INSUMO", "USO E CONSUMO", "ATIVO IMOBILIZADO", "SERVIÇO", "OUTRA"),
        ).grid(row=0, column=5, padx=(0, 10), pady=8, sticky="w")
        ttk.Label(contexto, text="Contribuinte:").grid(row=0, column=6, padx=(4, 4), pady=8, sticky="w")
        ttk.Combobox(
            contexto,
            textvariable=self.aud_contribuinte_var,
            state="readonly",
            width=18,
            values=("AUTOMÁTICO", "CONTRIBUINTE", "NÃO CONTRIBUINTE", "TODOS"),
        ).grid(row=0, column=7, padx=(0, 10), pady=8, sticky="w")
        contexto.grid_columnconfigure(1, weight=1)

        resumo = Frame(self.aba_tributaria, bg=COR_CARD, bd=1, relief="solid")
        resumo.pack(fill=X, padx=8, pady=4)
        self.lbl_resumo_tributario = Label(
            resumo,
            text=(
                "Abra um SPED e clique em “Cruzar Ficha Tributária”. Os XMLs de NF-e são opcionais; "
                "quando importados, também serão comparados com o C170 e o 0200."
            ),
            justify="left",
            anchor="w",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        )
        self.lbl_resumo_tributario.pack(fill=X, padx=12, pady=10)

        filtros = Frame(self.aba_tributaria, bg=COR_FUNDO)
        filtros.pack(fill=X, padx=8, pady=(4, 0))
        Label(filtros, text="Mostrar:", bg=COR_FUNDO, fg=COR_TEXTO).pack(side=LEFT)
        combo_filtro = ttk.Combobox(
            filtros,
            textvariable=self.aud_filtro_var,
            state="readonly",
            width=24,
            values=(
                "Todos", "Erros", "Avisos", "Sem regra", "Ficha Tributária", "XML NF-e", "Cadastro 0200", "Base Legal"
            ),
        )
        combo_filtro.pack(side=LEFT, padx=(6, 10))
        combo_filtro.bind("<<ComboboxSelected>>", lambda _e: self._exibir_auditoria_tributaria())
        ttk.Button(
            filtros,
            text="🔍 Ver divergência completa",
            command=self.abrir_detalhe_auditoria_tributaria,
        ).pack(side=LEFT)
        ttk.Button(
            filtros,
            text="🧾 Abrir ficha do NCM",
            command=self.abrir_ficha_ncm_auditoria,
        ).pack(side=LEFT, padx=(7, 0))

        frame_tabela = ttk.LabelFrame(self.aba_tributaria, text="Divergências e pendências por item")
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))
        colunas = (
            "nivel", "origem", "linha", "nota", "item", "codigo", "ncm",
            "campo", "atual", "esperado", "regra", "aderencia", "mensagem",
        )
        self.tabela_tributaria = ttk.Treeview(
            frame_tabela, columns=colunas, show="headings", height=16
        )
        titulos = {
            "nivel": "Nível", "origem": "Origem", "linha": "Linha", "nota": "NF",
            "item": "Item", "codigo": "Produto", "ncm": "NCM", "campo": "Campo",
            "atual": "No SPED", "esperado": "Esperado", "regra": "Regra",
            "aderencia": "Aderência", "mensagem": "Problema / orientação",
        }
        larguras = {
            "nivel": 70, "origem": 125, "linha": 70, "nota": 90, "item": 55,
            "codigo": 110, "ncm": 85, "campo": 120, "atual": 110, "esperado": 110,
            "regra": 65, "aderencia": 80, "mensagem": 470,
        }
        for coluna in colunas:
            self.tabela_tributaria.heading(coluna, text=titulos[coluna])
            self.tabela_tributaria.column(coluna, width=larguras[coluna], anchor="w")
        self.tabela_tributaria.tag_configure("ERRO", foreground="#B00020")
        self.tabela_tributaria.tag_configure("AVISO", foreground="#8A5A00")
        self.tabela_tributaria.bind("<Double-1>", self.abrir_detalhe_auditoria_tributaria)

        rolagem_y = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tabela_tributaria.yview)
        rolagem_x = ttk.Scrollbar(frame_tabela, orient="horizontal", command=self.tabela_tributaria.xview)
        self.tabela_tributaria.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)
        self.tabela_tributaria.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _criar_aba_difal(self):
        topo = Frame(self.aba_difal, bg=COR_CARD, bd=1, relief="solid")
        topo.pack(fill=X, padx=6, pady=(6, 3))
        self.lbl_resumo_difal = Label(
            topo,
            text=(
                "Abra um SPED Fiscal e clique em “Auditar DIFAL automático”. "
                "Importe os XMLs de saída para confirmar indFinal/indIEDest e conferir o C101 por chave."
            ),
            justify="left", anchor="w", bg=COR_CARD, fg=COR_TEXTO, font=FONTE_NORMAL,
        )
        self.lbl_resumo_difal.pack(fill=X, padx=12, pady=10)

        frame_tabela = ttk.LabelFrame(self.aba_difal, text="DIFAL/FCP por NF-e")
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))
        colunas = (
            "nivel", "linha", "nota", "uf", "cfop", "evidencia", "origem", "c101",
            "base", "interna", "inter_xml", "inter_sped", "difal_sped", "difal_xml", "difal_devido", "difal_sped_origem", "memoria", "dif_difal",
            "fcp_sped", "fcp_xml", "fcp_devido", "mensagem",
        )
        self.tabela_difal = ttk.Treeview(frame_tabela, columns=colunas, show="headings", height=16)
        titulos = {
            "nivel": "Nível", "linha": "Linha", "nota": "NF", "uf": "UF dest.",
            "cfop": "CFOP", "evidencia": "Evidência", "origem": "Origem cálculo", "c101": "C101",
            "base": "Base cálculo", "interna": "Alíq. interna devida",
            "inter_xml": "Alíq. inter. XML", "inter_sped": "Alíq. inter. SPED/CST",
            "difal_sped": "DIFAL SPED", "difal_xml": "DIFAL XML", "difal_devido": "DIFAL devido",
            "difal_sped_origem": "DIFAL cenário SPED/CST", "memoria": "Memória cálculo SPED/CST", "dif_difal": "Dif. SPED - devido",
            "fcp_sped": "FCP SPED", "fcp_xml": "FCP XML", "fcp_devido": "FCP devido",
            "mensagem": "Diagnóstico / orientação",
        }
        larguras = {
            "nivel": 70, "linha": 70, "nota": 90, "uf": 65, "cfop": 90,
            "evidencia": 260, "origem": 190, "c101": 60, "base": 105, "interna": 105,
            "inter_xml": 105, "inter_sped": 125,
            "difal_sped": 100, "difal_xml": 100, "difal_devido": 110, "difal_sped_origem": 135, "memoria": 420, "dif_difal": 120,
            "fcp_sped": 95, "fcp_xml": 95, "fcp_devido": 100, "mensagem": 520,
        }
        for coluna in colunas:
            self.tabela_difal.heading(coluna, text=titulos[coluna])
            self.tabela_difal.column(coluna, width=larguras[coluna], anchor="w")
        self.tabela_difal.tag_configure("ERRO", foreground="#B00020")
        self.tabela_difal.tag_configure("AVISO", foreground="#8A5A00")
        self.tabela_difal.tag_configure("REVISAR", foreground="#8A5A00")
        self.tabela_difal.tag_configure("OK", foreground="#176B35")

        rolagem_y = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tabela_difal.yview)
        rolagem_x = ttk.Scrollbar(frame_tabela, orient="horizontal", command=self.tabela_difal.xview)
        self.tabela_difal.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)
        self.tabela_difal.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _criar_aba_correcao_tributaria(self):
        self.mapa_correcao_tributaria = {}

        topo = Frame(self.aba_correcao_tributaria, bg=COR_CARD, bd=1, relief="solid")
        topo.pack(fill=X, padx=6, pady=(6, 3))
        self.lbl_resumo_correcao_tributaria = Label(
            topo,
            text=(
                "Execute a Auditoria Tributária e prepare as propostas. Nenhuma correção fiscal "
                "vem marcada automaticamente; Ficha e XML são apresentados para sua confirmação."
            ),
            justify="left",
            anchor="w",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        )
        self.lbl_resumo_correcao_tributaria.pack(fill=X, padx=12, pady=10)

        acoes = Frame(self.aba_correcao_tributaria, bg=COR_FUNDO)
        acoes.pack(fill=X, padx=8, pady=(4, 4))
        ttk.Button(
            acoes, text="✅ Marcar alta confiança", command=self.marcar_correcoes_tributarias_confiaveis
        ).pack(side=LEFT)
        ttk.Button(
            acoes, text="☐ Desmarcar todas", command=self.desmarcar_correcoes_tributarias
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Button(
            acoes, text="✏ Escolher/editar valor", command=self.editar_valor_correcao_tributaria
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Button(
            acoes, text="↔ Marcar/desmarcar", command=self.alternar_correcao_tributaria
        ).pack(side=LEFT, padx=(8, 0))
        self.btn_aplicar_tributaria = ttk.Button(
            acoes,
            text="🛠 Aplicar selecionadas",
            command=self.aplicar_correcoes_tributarias,
            state="disabled",
        )
        self.btn_aplicar_tributaria.pack(side=LEFT, padx=(8, 0))
        Label(
            acoes,
            text="Duplo clique alterna a seleção. Conflitos precisam de um valor escolhido.",
            bg=COR_FUNDO,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        ).pack(side=LEFT, padx=12)

        frame_tabela = ttk.LabelFrame(
            self.aba_correcao_tributaria,
            text="Propostas baseadas na Ficha Tributária e nos XMLs de NF-e",
        )
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))
        colunas = (
            "aplicar", "modo", "origem", "registro", "linha", "nota", "item",
            "codigo", "ncm", "campo", "atual", "sugerido", "regra", "aderencia", "motivo",
        )
        self.tabela_correcao_tributaria = ttk.Treeview(
            frame_tabela, columns=colunas, show="headings", height=16
        )
        titulos = {
            "aplicar": "Aplicar", "modo": "Tratamento", "origem": "Origem",
            "registro": "Registro", "linha": "Linha", "nota": "NF", "item": "Item",
            "codigo": "Produto", "ncm": "NCM", "campo": "Campo",
            "atual": "Valor atual", "sugerido": "Valor sugerido", "regra": "Regra",
            "aderencia": "Aderência", "motivo": "Motivo / cuidado",
        }
        larguras = {
            "aplicar": 65, "modo": 190, "origem": 150, "registro": 75, "linha": 70,
            "nota": 90, "item": 55, "codigo": 105, "ncm": 85, "campo": 120,
            "atual": 120, "sugerido": 150, "regra": 70, "aderencia": 80, "motivo": 480,
        }
        for coluna in colunas:
            self.tabela_correcao_tributaria.heading(coluna, text=titulos[coluna])
            self.tabela_correcao_tributaria.column(coluna, width=larguras[coluna], anchor="w")
        self.tabela_correcao_tributaria.tag_configure("MARCADA", foreground="#0B6B2A")
        self.tabela_correcao_tributaria.tag_configure("CONFLITO", foreground="#B00020")
        self.tabela_correcao_tributaria.tag_configure("REVISAO", foreground="#8A5A00")
        self.tabela_correcao_tributaria.bind(
            "<Double-1>", lambda _evento: self.alternar_correcao_tributaria()
        )

        rolagem_y = ttk.Scrollbar(
            frame_tabela, orient="vertical", command=self.tabela_correcao_tributaria.yview
        )
        rolagem_x = ttk.Scrollbar(
            frame_tabela, orient="horizontal", command=self.tabela_correcao_tributaria.xview
        )
        self.tabela_correcao_tributaria.configure(
            yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set
        )
        self.tabela_correcao_tributaria.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _criar_aba_estorno_icms(self):
        topo = Frame(self.aba_estorno_icms, bg=COR_CARD, bd=1, relief="solid")
        topo.pack(fill=X, padx=6, pady=(6, 3))
        self.lbl_resumo_estorno = Label(
            topo,
            text=(
                "Fluxo em duas etapas: primeiro confira os XMLs das NF-e de entrada (preferencial) ou PDFs/DANFEs "
                "das compras para revenda, confira/corrija o CFOP de entrada e preencha o ICMS próprio nos C170/C190; depois analise e gere os C195/C197 de estorno. "
                "O FiscalPro bloqueia C197 automático quando o C170 não tem BC/alíquota/VL_ICMS positivos ou é CFOP de uso/consumo. "
                "O arquivo original permanece intacto."
            ),
            justify="left", anchor="w", bg=COR_CARD, fg=COR_TEXTO, font=FONTE_NORMAL,
        )
        self.lbl_resumo_estorno.pack(fill=X, padx=12, pady=10)
        vincular_wraplength(self.lbl_resumo_estorno, margem=34, minimo=500)

        danfe = Frame(self.aba_estorno_icms, bg=COR_FUNDO)
        danfe.pack(fill=X, padx=8, pady=(3, 2))
        Label(
            danfe, text="1. ICMS + CFOP das compras", bg=COR_FUNDO, fg=COR_TEXTO,
            font=("Segoe UI", 8, "bold"),
        ).pack(side=LEFT)
        self.btn_selecionar_danfes_icms = ttk.Button(
            danfe, text="📄 Selecionar XMLs/PDFs/ZIP", command=self.selecionar_danfes_icms,
            state="disabled",
        )
        self.btn_selecionar_danfes_icms.pack(side=LEFT, padx=(8, 6))
        self.btn_gerar_icms_danfe = ttk.Button(
            danfe, text="💾 Gerar SPED ICMS + CFOP", command=self.gerar_sped_icms_danfe,
            state="disabled",
        )
        self.btn_gerar_icms_danfe.pack(side=LEFT)
        self.lbl_danfe_icms = Label(
            danfe, text="Abra um SPED e selecione os XMLs das entradas (preferencial) ou PDFs/DANFEs.",
            bg=COR_FUNDO, fg=COR_TEXTO, font=("Segoe UI", 8), anchor="w",
        )
        self.lbl_danfe_icms.pack(side=LEFT, fill=X, expand=True, padx=(10, 0))

        configuracao = Frame(self.aba_estorno_icms, bg=COR_FUNDO)
        configuracao.pack(fill=X, padx=8, pady=(3, 4))
        Label(
            configuracao, text="2. Código do ajuste C197", bg=COR_FUNDO, fg=COR_TEXTO,
            font=("Segoe UI", 8, "bold"),
        ).pack(side=LEFT)
        self.cmb_codigo_estorno = ttk.Combobox(
            configuracao, textvariable=self.codigo_estorno_var, state="readonly",
            values=list(self.OPCOES_CODIGO_ESTORNO), width=52,
        )
        self.cmb_codigo_estorno.pack(side=LEFT, padx=(8, 10))
        self.btn_gerar_estorno = ttk.Button(
            configuracao, text="💾 Gerar SPED estornado",
            command=self.gerar_sped_estornado, state="disabled",
        )
        self.btn_gerar_estorno.pack(side=LEFT)
        self.btn_conferir_estorno_nf = ttk.Button(
            configuracao, text="🔎 Conferir por NF",
            command=self.abrir_conferencia_estorno_por_nf, state="disabled",
        )
        self.btn_conferir_estorno_nf.pack(side=LEFT, padx=(8, 0))

        self.lbl_alerta_estorno = Label(
            self.aba_estorno_icms, text="Abra um SPED e execute a análise.",
            justify="left", anchor="w", bg=COR_FUNDO, fg="#8A5A00", font=("Segoe UI", 9),
        )
        self.lbl_alerta_estorno.pack(fill=X, padx=12, pady=(0, 4))
        vincular_wraplength(self.lbl_alerta_estorno, margem=38, minimo=500)

        frame_tabela = ttk.LabelFrame(
            self.aba_estorno_icms, text="Créditos de entrada e situação do estorno"
        )
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))
        colunas = (
            "status", "nf", "data", "fornecedor", "item", "descricao",
            "cfop", "base", "aliquota", "icms", "ajuste", "observacao",
        )
        self.tabela_estorno = ttk.Treeview(
            frame_tabela, columns=colunas, show="headings", height=14
        )
        titulos = {
            "status": "Situação", "nf": "NF", "data": "Entrada",
            "fornecedor": "Fornecedor", "item": "Item", "descricao": "Descrição",
            "cfop": "CFOP", "base": "Base ICMS", "aliquota": "Alíquota",
            "icms": "Crédito ICMS", "ajuste": "C197 existente",
            "observacao": "Conferência",
        }
        larguras = {
            "status": 100, "nf": 85, "data": 85, "fornecedor": 220,
            "item": 115, "descricao": 240, "cfop": 75, "base": 100,
            "aliquota": 80, "icms": 105, "ajuste": 115, "observacao": 430,
        }
        for coluna in colunas:
            self.tabela_estorno.heading(coluna, text=titulos[coluna])
            self.tabela_estorno.column(coluna, width=larguras[coluna], anchor="w")
        self.tabela_estorno.tag_configure("PENDENTE", foreground="#8A5A00")
        self.tabela_estorno.tag_configure("EXISTENTE", foreground="#0B6B2A")
        self.tabela_estorno.tag_configure("REVISAR", foreground="#B00020")

        rolagem_y = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tabela_estorno.yview)
        rolagem_x = ttk.Scrollbar(frame_tabela, orient="horizontal", command=self.tabela_estorno.xview)
        self.tabela_estorno.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)
        self.tabela_estorno.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _criar_aba_pre_pva(self):
        topo = Frame(self.aba_pre_pva, bg=COR_CARD, bd=1, relief="solid")
        topo.pack(fill=X, padx=6, pady=(6, 3))
        self.lbl_resumo_pva = Label(
            topo,
            text=(
                "Abra um SPED e clique em “Validar antes do PVA”. O FiscalPro conferirá "
                "estrutura, totalizadores, cadastros, vínculos de documentos e cálculos de PIS/COFINS."
            ),
            justify="left",
            anchor="w",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        )
        self.lbl_resumo_pva.pack(fill=X, padx=12, pady=(8, 4))

        # 17.8.79 — ações do Pré-PVA ficam visíveis dentro da própria aba.
        # Antes, os comandos existiam apenas na faixa superior "Excel, PVA e correções",
        # o que fazia a aba parecer sem botão quando o usuário navegava direto pelo diagnóstico.
        acoes_pva = Frame(topo, bg=COR_CARD)
        acoes_pva.pack(fill=X, padx=12, pady=(0, 8))
        self.btn_validar_pva_aba = ttk.Button(
            acoes_pva,
            text="✅ Validar antes do PVA",
            command=self.validar_antes_pva,
            state="disabled",
        )
        self.btn_validar_pva_aba.pack(side=LEFT)
        self.btn_relatorio_pva_aba = ttk.Button(
            acoes_pva,
            text="💾 Salvar relatório",
            command=self.salvar_relatorio_pva,
            state="disabled",
        )
        self.btn_relatorio_pva_aba.pack(side=LEFT, padx=(8, 0))

        frame_tabela = ttk.LabelFrame(self.aba_pre_pva, text="Erros e avisos antes da validação oficial")
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))
        colunas = ("nivel", "categoria", "registro", "linha", "documento", "item", "campo", "mensagem")
        self.tabela_pva = ttk.Treeview(frame_tabela, columns=colunas, show="headings", height=10)
        titulos = {
            "nivel": "Nível",
            "categoria": "Categoria",
            "registro": "Registro",
            "linha": "Linha",
            "documento": "Documento",
            "item": "Item",
            "campo": "Campo",
            "mensagem": "Problema / orientação",
        }
        larguras = {
            "nivel": 70,
            "categoria": 130,
            "registro": 75,
            "linha": 70,
            "documento": 230,
            "item": 105,
            "campo": 105,
            "mensagem": 550,
        }
        for coluna in colunas:
            self.tabela_pva.heading(coluna, text=titulos[coluna])
            self.tabela_pva.column(coluna, width=larguras[coluna], anchor="w")

        self.tabela_pva.tag_configure("ERRO", foreground="#B00020")
        self.tabela_pva.tag_configure("AVISO", foreground="#8A5A00")
        self.tabela_pva.tag_configure("REVISÃO FISCALPRO", foreground="#6B5B00")
        rolagem_y = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tabela_pva.yview)
        rolagem_x = ttk.Scrollbar(frame_tabela, orient="horizontal", command=self.tabela_pva.xview)
        self.tabela_pva.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)
        self.tabela_pva.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _criar_aba_assistida(self):
        topo = Frame(self.aba_assistida, bg=COR_CARD, bd=1, relief="solid")
        topo.pack(fill=X, padx=6, pady=(6, 3))
        self.lbl_resumo_assistida = Label(
            topo,
            text=(
                "Depois da pré-validação, clique em “Preparar correções”. Formatações seguras "
                "podem vir marcadas; cálculos, unidades e dados fiscais exigem sua confirmação."
            ),
            justify="left",
            anchor="w",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        )
        self.lbl_resumo_assistida.pack(fill=X, padx=12, pady=10)

        acoes = Frame(self.aba_assistida, bg=COR_FUNDO)
        acoes.pack(fill=X, padx=8, pady=(4, 4))
        ttk.Button(acoes, text="✅ Marcar seguras", command=self.marcar_correcoes_seguras).pack(side=LEFT)
        ttk.Button(
            acoes,
            text="☑ Marcar todas aplicáveis",
            command=self.marcar_todas_correcoes_aplicaveis,
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Button(acoes, text="☐ Desmarcar todas", command=self.desmarcar_correcoes_assistidas).pack(side=LEFT, padx=(8, 0))
        ttk.Button(acoes, text="✏ Editar valor selecionado", command=self.editar_valor_assistido).pack(side=LEFT, padx=(8, 0))
        ttk.Button(acoes, text="↔ Marcar/desmarcar", command=self.alternar_correcao_assistida).pack(side=LEFT, padx=(8, 0))
        self.btn_final_unificado = ttk.Button(
            acoes,
            text="💾 Gerar final + estorno",
            command=self.gerar_sped_final_unificado,
            state="disabled",
        )
        self.btn_final_unificado.pack(side=RIGHT)
        Label(
            acoes,
            text="Use ‘Marcar todas aplicáveis’ para não precisar confirmar linha por linha. CST 08 de entrada e alíquotas básicas podem ser corrigidos em lote; o Bloco M é sincronizado quando a apuração for determinística.",
            bg=COR_FUNDO,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        ).pack(side=LEFT, padx=12)

        frame_tabela = ttk.LabelFrame(self.aba_assistida, text="Sugestões e preenchimentos antes de gerar a nova cópia")
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))
        colunas = (
            "aplicar", "modo", "nivel", "registro", "linha", "documento",
            "item", "campo", "atual", "sugerido", "motivo"
        )
        self.tabela_assistida = ttk.Treeview(frame_tabela, columns=colunas, show="headings", height=10)
        titulos = {
            "aplicar": "Aplicar", "modo": "Tratamento", "nivel": "Nível",
            "registro": "Registro", "linha": "Linha", "documento": "Documento",
            "item": "Item", "campo": "Campo", "atual": "Valor atual",
            "sugerido": "Valor sugerido", "motivo": "Motivo / cuidado",
        }
        larguras = {
            "aplicar": 65, "modo": 165, "nivel": 65, "registro": 75,
            "linha": 70, "documento": 190, "item": 110, "campo": 115,
            "atual": 170, "sugerido": 190, "motivo": 440,
        }
        for coluna in colunas:
            self.tabela_assistida.heading(coluna, text=titulos[coluna])
            self.tabela_assistida.column(coluna, width=larguras[coluna], anchor="w")
        self.tabela_assistida.tag_configure("MARCADA", foreground="#0B6B2A")
        self.tabela_assistida.tag_configure("ERRO", foreground="#B00020")
        self.tabela_assistida.tag_configure("AVISO", foreground="#8A5A00")
        self.tabela_assistida.bind("<Double-1>", lambda _evento: self.alternar_correcao_assistida())

        rolagem_y = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tabela_assistida.yview)
        rolagem_x = ttk.Scrollbar(frame_tabela, orient="horizontal", command=self.tabela_assistida.xview)
        self.tabela_assistida.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)
        self.tabela_assistida.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _criar_aba_excel(self):
        topo = Frame(self.aba_excel, bg=COR_CARD, bd=1, relief="solid")
        topo.pack(fill=X, padx=6, pady=(6, 3))
        self.lbl_resumo_excel = Label(
            topo,
            text=(
                "Selecione uma planilha exportada pelo FiscalPro. Antes de liberar o TXT, o sistema "
                "valida a estrutura, reconstrói o SPED em memória e executa um Pré-PVA comparativo. "
                "Somente novos erros criados pela edição do Excel bloqueiam a geração."
            ),
            justify="left",
            anchor="w",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        )
        self.lbl_resumo_excel.pack(fill=X, padx=12, pady=10)

        # 17.8.81 — fluxo Excel → TXT visível e operacional dentro da própria aba.
        # O botão de geração direta grava ao lado da planilha validada, evitando
        # depender da caixa "Salvar como" da faixa superior.
        acoes_excel_txt = ttk.LabelFrame(self.aba_excel, text="Fluxo Excel → TXT")
        acoes_excel_txt.pack(fill=X, padx=6, pady=(3, 3))
        self.btn_importar_excel_aba = ttk.Button(
            acoes_excel_txt, text="📂 Selecionar Excel", command=self.importar_excel
        )
        self.btn_importar_excel_aba.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=6)
        self.btn_validar_excel_aba = ttk.Button(
            acoes_excel_txt, text="✅ Validar planilha", command=self.validar_excel, state="disabled"
        )
        self.btn_validar_excel_aba.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        self.btn_gerar_txt_aba = ttk.Button(
            acoes_excel_txt,
            text="📝 Gerar SPED TXT agora",
            command=self.gerar_sped_txt_direto,
            state="disabled",
        )
        self.btn_gerar_txt_aba.grid(row=0, column=2, sticky="ew", padx=4, pady=6)
        self.btn_conferir_excel_aba = ttk.Button(
            acoes_excel_txt, text="🔎 Conferir alterações", command=self.conferir_alteracoes_excel, state="disabled"
        )
        self.btn_conferir_excel_aba.grid(row=0, column=3, sticky="ew", padx=(4, 8), pady=6)
        for coluna in range(4):
            acoes_excel_txt.grid_columnconfigure(coluna, weight=1, uniform="fluxo_excel_txt")

        self.lbl_destino_txt = Label(
            acoes_excel_txt,
            text="Depois da validação, o TXT será salvo ao lado do Excel, sem substituir o SPED original.",
            bg=COR_FUNDO, fg=COR_TEXTO, font=("Segoe UI", 8), anchor="w", justify="left",
        )
        self.lbl_destino_txt.grid(row=1, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 6))

        frame_tabela = ttk.LabelFrame(self.aba_excel, text="Resultado da validação")
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))
        colunas = ("nivel", "sequencia", "registro", "aba", "linha", "mensagem")
        self.tabela_excel = ttk.Treeview(
            frame_tabela, columns=colunas, show="headings", height=16
        )
        titulos = {
            "nivel": "Nível",
            "sequencia": "Sequência",
            "registro": "Registro",
            "aba": "Aba",
            "linha": "Linha Excel",
            "mensagem": "Detalhe",
        }
        larguras = {
            "nivel": 75,
            "sequencia": 85,
            "registro": 75,
            "aba": 180,
            "linha": 85,
            "mensagem": 620,
        }
        for coluna in colunas:
            self.tabela_excel.heading(coluna, text=titulos[coluna])
            self.tabela_excel.column(coluna, width=larguras[coluna], anchor="w")

        rolagem_y = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tabela_excel.yview)
        rolagem_x = ttk.Scrollbar(frame_tabela, orient="horizontal", command=self.tabela_excel.xview)
        self.tabela_excel.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)
        self.tabela_excel.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _criar_aba_conferencia_excel(self):
        topo = Frame(self.aba_conferencia_excel, bg=COR_CARD, bd=1, relief="solid")
        topo.pack(fill=X, padx=6, pady=(6, 3))
        self.lbl_resumo_conferencia_excel = Label(
            topo,
            text=(
                "Valide uma planilha e clique em “Conferir alterações”. O FiscalPro mostrará "
                "Original × Novo e também os ajustes automáticos seguros feitos na reconstrução."
            ),
            justify="left",
            anchor="w",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=FONTE_NORMAL,
        )
        self.lbl_resumo_conferencia_excel.pack(fill=X, padx=12, pady=10)
        vincular_wraplength(self.lbl_resumo_conferencia_excel, margem=34, minimo=500)

        # 17.8.80 — o fluxo Excel fica visível dentro da própria aba de conferência.
        # A faixa superior continua disponível, mas a usuária não precisa trocar de aba
        # para selecionar, validar e conferir a planilha.
        acoes_excel = ttk.LabelFrame(self.aba_conferencia_excel, text="Fluxo da planilha")
        acoes_excel.pack(fill=X, padx=6, pady=(3, 3))
        self.btn_importar_excel_conf = ttk.Button(
            acoes_excel, text="📂 Selecionar Excel", command=self.importar_excel
        )
        self.btn_importar_excel_conf.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=6)
        self.btn_validar_excel_conf = ttk.Button(
            acoes_excel, text="✅ Validar planilha", command=self.validar_excel, state="disabled"
        )
        self.btn_validar_excel_conf.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        self.btn_conferir_excel_conf = ttk.Button(
            acoes_excel, text="🔎 Conferir alterações", command=self.conferir_alteracoes_excel, state="disabled"
        )
        self.btn_conferir_excel_conf.grid(row=0, column=2, sticky="ew", padx=4, pady=6)
        self.btn_relatorio_conferencia_excel = ttk.Button(
            acoes_excel, text="💾 Gerar relatório", command=self.salvar_relatorio_conferencia_excel, state="disabled"
        )
        self.btn_relatorio_conferencia_excel.grid(row=0, column=3, sticky="ew", padx=(4, 8), pady=6)
        for coluna in range(4):
            acoes_excel.grid_columnconfigure(coluna, weight=1, uniform="fluxo_excel")

        filtros = ttk.LabelFrame(self.aba_conferencia_excel, text="Filtros da conferência")
        filtros.pack(fill=X, padx=6, pady=(3, 3))

        ttk.Label(filtros, text="Registro").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=6)
        self.cmb_conf_registro = ttk.Combobox(
            filtros,
            textvariable=self.filtro_conf_registro_var,
            values=["Todos"],
            state="readonly",
            width=14,
        )
        self.cmb_conf_registro.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(filtros, text="Tipo").grid(row=0, column=2, sticky="w", padx=(10, 4), pady=6)
        self.cmb_conf_tipo = ttk.Combobox(
            filtros,
            textvariable=self.filtro_conf_tipo_var,
            values=["Todos", "Alteração", "Ajuste automático", "Inclusão", "Exclusão"],
            state="readonly",
            width=14,
        )
        self.cmb_conf_tipo.grid(row=0, column=3, sticky="ew", pady=6)

        ttk.Label(filtros, text="Categoria").grid(row=0, column=4, sticky="w", padx=(10, 4), pady=6)
        self.cmb_conf_categoria = ttk.Combobox(
            filtros,
            textvariable=self.filtro_conf_categoria_var,
            values=["Todas", "Identificação", "Tributário", "Valor", "Cadastral", "Outro"],
            state="readonly",
            width=16,
        )
        self.cmb_conf_categoria.grid(row=0, column=5, sticky="ew", pady=6)

        ttk.Label(filtros, text="Busca").grid(row=0, column=6, sticky="w", padx=(10, 4), pady=6)
        self.entry_conf_busca = ttk.Entry(filtros, textvariable=self.filtro_conf_busca_var)
        self.entry_conf_busca.grid(row=0, column=7, sticky="ew", pady=6)

        ttk.Button(
            filtros,
            text="Limpar filtros",
            command=self.limpar_filtros_conferencia_excel,
        ).grid(row=0, column=8, padx=(8, 4), pady=6)
        for coluna in (1, 3, 5):
            filtros.grid_columnconfigure(coluna, weight=0)
        filtros.grid_columnconfigure(7, weight=1)

        for combo in (self.cmb_conf_registro, self.cmb_conf_tipo, self.cmb_conf_categoria):
            combo.bind("<<ComboboxSelected>>", lambda _evento: self._exibir_conferencia_excel())
        self.entry_conf_busca.bind("<KeyRelease>", lambda _evento: self._exibir_conferencia_excel())

        frame_tabela = ttk.LabelFrame(
            self.aba_conferencia_excel,
            text="Original × Novo — alterações detectadas",
        )
        frame_tabela.pack(fill=BOTH, expand=True, padx=6, pady=(3, 6))
        colunas = (
            "tipo", "categoria", "registro", "sequencia", "aba",
            "linha", "campo", "original", "novo",
        )
        self.tabela_conferencia_excel = ttk.Treeview(
            frame_tabela, columns=colunas, show="headings", height=16
        )
        titulos = {
            "tipo": "Tipo",
            "categoria": "Categoria",
            "registro": "Registro",
            "sequencia": "Sequência",
            "aba": "Aba",
            "linha": "Linha Excel",
            "campo": "Campo",
            "original": "Original",
            "novo": "Novo",
        }
        larguras = {
            "tipo": 90,
            "categoria": 105,
            "registro": 75,
            "sequencia": 80,
            "aba": 150,
            "linha": 85,
            "campo": 145,
            "original": 280,
            "novo": 280,
        }
        for coluna in colunas:
            self.tabela_conferencia_excel.heading(coluna, text=titulos[coluna])
            self.tabela_conferencia_excel.column(coluna, width=larguras[coluna], anchor="w")

        rolagem_y = ttk.Scrollbar(
            frame_tabela, orient="vertical", command=self.tabela_conferencia_excel.yview
        )
        rolagem_x = ttk.Scrollbar(
            frame_tabela, orient="horizontal", command=self.tabela_conferencia_excel.xview
        )
        self.tabela_conferencia_excel.configure(
            yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set
        )
        self.tabela_conferencia_excel.grid(
            row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0)
        )
        rolagem_y.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 0))
        rolagem_x.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        frame_tabela.grid_rowconfigure(0, weight=1)
        frame_tabela.grid_columnconfigure(0, weight=1)

    def _campo_info(self, master, titulo, linha, coluna):
        frame = Frame(master, bg=COR_CARD)
        frame.grid(row=linha, column=coluna, sticky="ew", padx=14, pady=9)
        master.grid_columnconfigure(coluna, weight=1)
        Label(frame, text=titulo, bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        valor = Label(frame, text="-", bg=COR_CARD, fg=COR_TEXTO, font=FONTE_NORMAL)
        valor.pack(anchor="w")
        return valor

    def abrir_sped(self):
        arquivo = filedialog.askopenfilename(
            title="Selecione o arquivo SPED",
            filetypes=[("Arquivo SPED", "*.txt"), ("Todos os arquivos", "*.*")],
            parent=self,
        )
        if not arquivo:
            return
        self._carregar_sped(arquivo)

    def _carregar_sped(self, arquivo):
        try:
            self.resultado = self.motor.abrir(arquivo, self._atualizar_progresso)
            self.analise_correcoes = None
            self.pre_validacao_pva = None
            self.preparacao_assistida = None
            self.analise_chaves_cte = None
            self.auditoria_tributaria = None
            self.preparacao_correcao_tributaria = None
            self.analise_estorno_icms = None
            self.analise_danfe_icms = None
            self.analise_exclusao_icms_creditos = None
            self.auditoria_difal = None
            self._exibir_resultado()
            self._limpar_chaves_cte()
            self._limpar_correcoes()
            self._limpar_auditoria_tributaria()
            self._limpar_difal()
            self._limpar_correcao_tributaria()
            self._limpar_estorno_icms()
            self._limpar_pre_pva()
            self._limpar_assistida()

            # Hotfix 17.7.1 — a EFD Contribuições precisa chegar ao Excel
            # somente depois de o PGE gerar a apuração do Bloco M.  O aviso
            # aparece já na abertura e o botão fica bloqueado para evitar que
            # o problema só seja descoberto depois de milhares de ajustes.
            diagnostico_m = self.motor.verificar_apuracao_bloco_m()
            if diagnostico_m.bloqueado:
                self.btn_exportar.configure(state="disabled")
                self.lbl_status.config(text="Bloco M não apurado — gere as apurações no PGE antes do Excel.")
                messagebox.showwarning(
                    "FiscalPro — Bloco M não apurado",
                    diagnostico_m.mensagem_bloqueio(),
                    parent=self,
                )
            else:
                self.btn_exportar.configure(state="normal")

            self.btn_analisar.configure(state="normal")
            self.btn_corrigir.configure(state="disabled")
            self.btn_estorno_icms.configure(state="normal")
            self.btn_selecionar_danfes_icms.configure(state="normal")
            self.btn_validar_pva.configure(state="normal")
            self.btn_validar_pva_aba.configure(state="normal")
            self.btn_relatorio_pva.configure(state="disabled")
            self.btn_relatorio_pva_aba.configure(state="disabled")
            self.btn_auditar_tributacao.configure(state="normal")
            eh_fiscal = bool(
                self.resultado
                and self.resultado.estatisticas.tipo_sped == "EFD ICMS/IPI (Fiscal)"
            )
            self.btn_auditar_difal.configure(state="normal" if eh_fiscal else "disabled")
            self.btn_relatorio_difal.configure(state="disabled")
            self.btn_excel_difal.configure(state="disabled")
            self.lbl_difal_comando.config(
                text=(
                    "SPED Fiscal carregado. Com XML a conferência é exata; sem XML, o FiscalPro calcula o DIFAL devido estimado pelo SPED."
                    if eh_fiscal
                    else "DIFAL automático é habilitado somente para EFD ICMS/IPI (SPED Fiscal)."
                )
            )
            self.btn_relatorio_tributario.configure(state="disabled")
            self.btn_preparar_tributaria.configure(state="disabled")
            self.btn_aplicar_tributaria.configure(state="disabled")
            self.btn_preparar_assistida.configure(state="normal")
            self.btn_aplicar_assistida.configure(state="disabled")
            self.btn_final_unificado.configure(state="disabled")
            eh_contribuicoes = bool(
                self.resultado
                and self.resultado.estatisticas.tipo_sped == "EFD Contribuições"
            )
            self.btn_excluir_icms_piscofins.configure(
                state="normal" if eh_contribuicoes else "disabled"
            )
            self.lbl_icms_piscofins.config(
                text=(
                    "Selecione o SPED Fiscal corrigido para excluir o ICMS próprio das bases de crédito."
                    if eh_contribuicoes
                    else "Este recurso é habilitado somente para EFD Contribuições."
                )
            )
            self.btn_analisar_cte.configure(
                state="normal" if self.importacao_cte_xml is not None else "disabled"
            )
            self.btn_corrigir_cte.configure(state="disabled")
            self.btn_incluir_cte_sem_credito.configure(
                state="normal" if eh_fiscal else "disabled"
            )
            self.lbl_pva.config(text="SPED carregado. Clique em Validar antes do PVA.")
            self.lbl_assistida.config(text="SPED carregado. Prepare as correções após a pré-validação.")
            self.aud_empresa_var.set(self.resultado.estatisticas.empresa if self.resultado else "")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao carregar o arquivo.")

    def excluir_icms_bases_piscofins(self):
        if self.resultado is None:
            messagebox.showwarning(
                "FiscalPro", "Abra uma EFD Contribuições antes de importar o ICMS.", parent=self
            )
            return
        if self.resultado.estatisticas.tipo_sped != "EFD Contribuições":
            messagebox.showwarning(
                "FiscalPro",
                "Este recurso funciona somente com a EFD Contribuições aberta.",
                parent=self,
            )
            return

        fiscal = filedialog.askopenfilename(
            title="Selecione o SPED Fiscal corrigido com os créditos de ICMS",
            filetypes=[("Arquivo SPED Fiscal", "*.txt"), ("Todos os arquivos", "*.*")],
            parent=self,
        )
        if not fiscal:
            return

        try:
            self.btn_excluir_icms_piscofins.configure(state="disabled")
            self.lbl_icms_piscofins.config(text="Cruzando notas e itens com o SPED Fiscal corrigido...")
            analise = self.motor.analisar_exclusao_icms_creditos_piscofins(
                fiscal, self._atualizar_progresso
            )
            self.analise_exclusao_icms_creditos = analise

            if analise.inconsistencias:
                amostra = "\n".join(f"• {x}" for x in analise.inconsistencias[:8])
                if len(analise.inconsistencias) > 8:
                    amostra += f"\n• ... e mais {len(analise.inconsistencias) - 8} item(ns)."
                messagebox.showwarning(
                    "FiscalPro — ICMS → PIS/COFINS",
                    (
                        "O cruzamento encontrou divergências e, por segurança, não vai gerar uma correção parcial.\n\n"
                        + amostra
                    ),
                    parent=self,
                )
                self.lbl_icms_piscofins.config(
                    text=f"Cruzamento bloqueado: {len(analise.inconsistencias)} divergência(s)."
                )
                return

            if not analise.itens_aptos:
                messagebox.showinfo(
                    "FiscalPro — ICMS → PIS/COFINS",
                    (
                        "Nenhum item novo precisa de exclusão.\n\n"
                        f"Itens já com base líquida de ICMS: {len(analise.itens_ja_excluidos)}"
                    ),
                    parent=self,
                )
                self.lbl_icms_piscofins.config(text="Nenhum item novo para corrigir.")
                return

            resumo = (
                "O FiscalPro cruzou os dois arquivos com segurança.\n\n"
                f"Notas encontradas: {analise.documentos_aptos}\n"
                f"Itens a corrigir: {analise.itens_alterar}\n"
                f"ICMS próprio a excluir das bases: {self._fmt_moeda(analise.total_icms_excluir)}\n"
                f"Redução estimada de PIS: {self._fmt_moeda(analise.reducao_pis_estimada)}\n"
                f"Redução estimada de COFINS: {self._fmt_moeda(analise.reducao_cofins_estimada)}\n\n"
                "Ele vai recalcular os C170, totais C100 e os créditos/apuração do Bloco M. "
                "O arquivo original não será alterado. Deseja continuar?"
            )
            if not messagebox.askyesno(
                "FiscalPro — Excluir ICMS das bases PIS/COFINS", resumo, parent=self
            ):
                return

            nome = f"{self.resultado.caminho.stem}_ICMS_FORA_BC_PISCOFINS.txt"
            caminho = filedialog.asksaveasfilename(
                title="Salvar EFD Contribuições com ICMS fora da base PIS/COFINS",
                defaultextension=".txt",
                initialdir=str(self.resultado.caminho.parent),
                initialfile=nome,
                filetypes=[("Arquivo SPED", "*.txt")],
                parent=self,
            )
            if not caminho:
                return

            geracao = self.motor.gerar_contribuicoes_com_icms_fora_da_base(
                caminho, self._atualizar_progresso
            )
            self.lbl_icms_piscofins.config(
                text=(
                    f"Concluído: {geracao.itens_alterados} itens • "
                    f"ICMS excluído {self._fmt_moeda(geracao.total_icms_excluido)} • "
                    f"Pré-PVA {geracao.pre_validador_erros} erro(s)."
                )
            )
            carregar = messagebox.askyesno(
                "FiscalPro — ICMS → PIS/COFINS",
                (
                    "Nova EFD Contribuições gerada com sucesso!\n\n"
                    f"Notas alteradas: {geracao.documentos_alterados}\n"
                    f"Itens alterados: {geracao.itens_alterados}\n"
                    f"ICMS excluído das bases: {self._fmt_moeda(geracao.total_icms_excluido)}\n"
                    f"Redução de PIS: {self._fmt_moeda(geracao.reducao_pis)}\n"
                    f"Redução de COFINS: {self._fmt_moeda(geracao.reducao_cofins)}\n"
                    f"Bloco M sincronizado: {geracao.alteracoes_bloco_m} campo(s)\n"
                    f"Pré-Validador: {geracao.pre_validador_erros} erro(s) / {geracao.pre_validador_avisos} aviso(s)\n\n"
                    f"Relatório: {geracao.caminho_relatorio}\n\n"
                    "Deseja abrir a nova cópia no FiscalPro agora?"
                ),
                parent=self,
            )
            if carregar:
                self._carregar_sped(str(geracao.caminho_sped))
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao excluir o ICMS das bases de PIS/COFINS.")
        finally:
            if self.resultado is not None and self.resultado.estatisticas.tipo_sped == "EFD Contribuições":
                self.btn_excluir_icms_piscofins.configure(state="normal")

    def selecionar_pasta_xml_cte(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta com XMLs de CT-e", parent=self)
        if pasta:
            self._importar_fontes_cte([pasta])

    def selecionar_xml_zip_cte(self):
        arquivos = filedialog.askopenfilenames(
            title="Selecione XMLs de CT-e ou um arquivo ZIP",
            filetypes=[
                ("XML ou ZIP de CT-e", "*.xml *.zip"),
                ("Arquivos XML", "*.xml"),
                ("Arquivo ZIP", "*.zip"),
                ("Todos os arquivos", "*.*"),
            ],
            parent=self,
        )
        if arquivos:
            self._importar_fontes_cte(list(arquivos))

    def _importar_fontes_cte(self, fontes):
        try:
            self.btn_analisar_cte.configure(state="disabled")
            self.btn_corrigir_cte.configure(state="disabled")
            self.importacao_cte_xml = self.motor.carregar_xmls_cte(
                fontes, self._atualizar_progresso
            )
            self.analise_chaves_cte = None
            self._limpar_chaves_cte()
            total = self.importacao_cte_xml.total_cte_validos
            erros = self.importacao_cte_xml.total_erros
            ignorados = self.importacao_cte_xml.total_ignorados
            self.lbl_cte.config(
                text=f"{total:,} CT-e(s) carregado(s) • {erros} erro(s) • {ignorados} ignorado(s)".replace(",", ".")
            )
            if self.resultado is not None:
                self.btn_analisar_cte.configure(state="normal")
            messagebox.showinfo(
                "FiscalPro",
                (
                    "XMLs de CT-e importados com sucesso!\n\n"
                    f"XMLs encontrados: {self.importacao_cte_xml.total_arquivos_xml:,}\n"
                    f"CT-e válidos: {total:,}\n"
                    f"Duplicados ignorados: {self.importacao_cte_xml.total_duplicados:,}\n"
                    f"Arquivos ignorados: {ignorados:,}\n"
                    f"Erros de leitura: {erros:,}"
                ).replace(",", "."),
                parent=self,
            )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao importar XMLs de CT-e.")

    def analisar_chaves_cte(self):
        if self.resultado is None:
            messagebox.showwarning("FiscalPro", "Abra um SPED antes de conferir as chaves.", parent=self)
            return
        if self.importacao_cte_xml is None:
            messagebox.showwarning("FiscalPro", "Importe primeiro os XMLs ou o ZIP de CT-e.", parent=self)
            return
        try:
            self.btn_analisar_cte.configure(state="disabled")
            self.btn_corrigir_cte.configure(state="disabled")
            self.analise_chaves_cte = self.motor.analisar_chaves_cte(
                self._atualizar_progresso
            )
            self._exibir_chaves_cte()
            self.abas.select(self.aba_cte)
            if self.analise_chaves_cte.pode_corrigir:
                self.btn_corrigir_cte.configure(state="normal")
            messagebox.showinfo(
                "FiscalPro",
                (
                    f"D100 de CT-e analisados: {self.analise_chaves_cte.total_d100_cte:,}\n\n"
                    f"Chaves corretas: {self.analise_chaves_cte.corretas:,}\n"
                    f"Chaves divergentes: {self.analise_chaves_cte.divergentes:,}\n"
                    f"XML não encontrado: {self.analise_chaves_cte.nao_encontradas:,}\n"
                    f"Correspondências ambíguas: {self.analise_chaves_cte.ambiguas:,}"
                ).replace(",", "."),
                parent=self,
            )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao conferir chaves de CT-e.")
        finally:
            self.btn_analisar_cte.configure(state="normal")

    def corrigir_chaves_cte(self):
        if self.resultado is None or self.analise_chaves_cte is None:
            messagebox.showwarning("FiscalPro", "Confira primeiro as chaves dos CT-e.", parent=self)
            return
        if not self.analise_chaves_cte.pode_corrigir:
            messagebox.showinfo("FiscalPro", "Não existem chaves divergentes para corrigir.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar SPED com chaves de CT-e corrigidas",
            defaultextension=".txt",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=f"{self.resultado.caminho.stem}_CTE_CORRIGIDO.txt",
            filetypes=[("Arquivo SPED", "*.txt")],
            parent=self,
        )
        if not caminho:
            return
        confirmar = messagebox.askyesno(
            "FiscalPro",
            (
                f"Serão corrigidas {self.analise_chaves_cte.divergentes:,} chave(s) de CT-e "
                "em uma NOVA CÓPIA.\n\nO arquivo original não será alterado. Deseja continuar?"
            ).replace(",", "."),
            parent=self,
        )
        if not confirmar:
            return
        try:
            self.btn_corrigir_cte.configure(state="disabled")
            geracao = self.motor.corrigir_chaves_cte(caminho, self._atualizar_progresso)
            carregar = messagebox.askyesno(
                "FiscalPro",
                (
                    "Chaves de CT-e corrigidas com sucesso!\n\n"
                    f"Correções aplicadas: {geracao.corrigidas:,}\n"
                    f"XML não encontrado: {geracao.nao_encontradas:,}\n"
                    f"Correspondências ambíguas: {geracao.ambiguas:,}\n\n"
                    f"SPED corrigido:\n{geracao.caminho_sped}\n\n"
                    f"Relatório:\n{geracao.caminho_relatorio}\n\n"
                    "Deseja carregar agora esta cópia no SPED Inteligente para continuar o trabalho?"
                ).replace(",", "."),
                parent=self,
            )
            if carregar:
                self._carregar_sped(str(geracao.caminho_sped))
                self.lbl_status.config(text="Cópia com chaves corrigidas carregada no SPED Inteligente.")
            else:
                self.lbl_status.config(text="SPED com chaves de CT-e corrigidas e relatório gerados.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao corrigir chaves de CT-e.")
        finally:
            if self.analise_chaves_cte and self.analise_chaves_cte.pode_corrigir:
                self.btn_corrigir_cte.configure(state="normal")

    def incluir_ctes_sem_credito(self):
        """Inclui CT-e ausentes no Bloco D sem apropriar crédito de ICMS."""
        if self.resultado is None:
            messagebox.showwarning(
                "FiscalPro", "Abra um SPED Fiscal antes de incluir os CT-e.", parent=self
            )
            return
        if self.resultado.estatisticas.tipo_sped != "EFD ICMS/IPI (Fiscal)":
            messagebox.showwarning(
                "FiscalPro",
                "A inclusão de CT-e sem crédito é exclusiva do SPED Fiscal (EFD ICMS/IPI).",
                parent=self,
            )
            return

        cte_zip = filedialog.askopenfilename(
            title="Selecione o ZIP com os XMLs de CT-e",
            filetypes=[("Arquivo ZIP de CT-e", "*.zip"), ("Todos os arquivos", "*.*")],
            parent=self,
        )
        if not cte_zip:
            return

        origem = Path(self.resultado.caminho)
        caminho = filedialog.asksaveasfilename(
            title="Salvar SPED com CT-e incluídos sem crédito",
            defaultextension=".txt",
            initialdir=str(origem.parent),
            initialfile=f"{origem.stem}_COM_CTE_SEM_CREDITO.txt",
            filetypes=[("Arquivo SPED", "*.txt")],
            parent=self,
        )
        if not caminho:
            return

        destino = Path(caminho)
        relatorio = destino.with_name(f"{destino.stem}_RELATORIO_CTE.csv")
        confirmar = messagebox.askyesno(
            "FiscalPro — Incluir CT-e sem crédito",
            (
                "O FiscalPro vai incluir somente CT-e autorizados, do período do SPED, "
                "em que a empresa é tomadora do frete.\n\n"
                "Os CT-e já existentes não serão duplicados. O ICMS destacado nos XMLs "
                "NÃO será apropriado como crédito. A apuração E110 original será preservada.\n\n"
                "O arquivo SPED original não será alterado. Deseja continuar?"
            ),
            parent=self,
        )
        if not confirmar:
            return

        try:
            self.btn_incluir_cte_sem_credito.configure(state="disabled")
            self.lbl_status.config(text="Incluindo CT-e no SPED sem apropriação de crédito...")
            self.update_idletasks()
            resumo = processar_cte_sem_credito(origem, Path(cte_zip), destino, relatorio)

            incluido = int(resumo.get("ctes_incluidos", 0))
            participantes = int(resumo.get("participantes_adicionados", 0))
            valor = resumo.get("valor_frete", 0)
            icms = resumo.get("icms_original_nao_apropriado", 0)
            ignorados = resumo.get("skipped", {}) or {}
            ja_existentes = int(ignorados.get("ja_no_sped", 0))

            carregar = messagebox.askyesno(
                "FiscalPro",
                (
                    "CT-e processados com sucesso!\n\n"
                    f"CT-e incluídos: {incluido:,}\n"
                    f"CT-e já existentes: {ja_existentes:,}\n"
                    f"Participantes 0150 adicionados: {participantes:,}\n"
                    f"Valor total dos fretes incluídos: R$ {valor:,.2f}\n"
                    f"ICMS dos XMLs NÃO apropriado: R$ {icms:,.2f}\n"
                    "Crédito de ICMS gerado: R$ 0,00\n\n"
                    f"Novo SPED:\n{destino}\n\n"
                    f"Relatório:\n{relatorio}\n\n"
                    "Deseja carregar agora esta cópia no SPED Inteligente?"
                ).replace(",", "X").replace(".", ",").replace("X", "."),
                parent=self,
            )
            if carregar:
                self._carregar_sped(str(destino))
                self.lbl_status.config(text="SPED com CT-e sem crédito carregado para continuidade.")
            else:
                self.lbl_status.config(text="SPED com CT-e sem crédito e relatório gerados.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao incluir CT-e sem crédito no SPED.")
        finally:
            if (
                self.resultado is not None
                and self.resultado.estatisticas.tipo_sped == "EFD ICMS/IPI (Fiscal)"
            ):
                self.btn_incluir_cte_sem_credito.configure(state="normal")

    def selecionar_pasta_xml_nfe(self):
        pasta = filedialog.askdirectory(
            title="Selecione a pasta com XMLs de NF-e", parent=self
        )
        if pasta:
            self._importar_fontes_nfe([pasta])

    def selecionar_xml_zip_nfe(self):
        arquivos = filedialog.askopenfilenames(
            title="Selecione XMLs de NF-e ou arquivos ZIP",
            filetypes=[
                ("XML ou ZIP de NF-e", "*.xml *.zip"),
                ("Arquivos XML", "*.xml"),
                ("Arquivos ZIP", "*.zip"),
                ("Todos os arquivos", "*.*"),
            ],
            parent=self,
        )
        if arquivos:
            self._importar_fontes_nfe(list(arquivos))

    def _importar_fontes_nfe(self, fontes):
        try:
            self.btn_auditar_tributacao.configure(state="disabled")
            self.btn_relatorio_tributario.configure(state="disabled")
            self.importacao_nfe_xml = self.motor.carregar_xmls_nfe(
                fontes, self._atualizar_progresso
            )
            self.auditoria_tributaria = None
            self.auditoria_difal = None
            self.preparacao_correcao_tributaria = None
            self._limpar_auditoria_tributaria()
            self._limpar_difal()
            self.btn_relatorio_difal.configure(state="disabled")
            self._limpar_correcao_tributaria()
            self.btn_preparar_tributaria.configure(state="disabled")
            self.btn_aplicar_tributaria.configure(state="disabled")
            total = self.importacao_nfe_xml.total_nfe_validas
            erros = self.importacao_nfe_xml.total_erros
            ignoradas = self.importacao_nfe_xml.total_ignoradas
            self.lbl_auditoria_xml.config(
                text=(
                    f"{total:,} NF-e(s) carregada(s) • "
                    f"{self.importacao_nfe_xml.total_duplicadas:,} duplicada(s) • "
                    f"{erros:,} erro(s) • {ignoradas:,} ignorada(s)"
                ).replace(",", ".")
            )
            if self.resultado is not None:
                self.btn_auditar_tributacao.configure(state="normal")
                if self.resultado.estatisticas.tipo_sped == "EFD ICMS/IPI (Fiscal)":
                    self.btn_auditar_difal.configure(state="normal")
            messagebox.showinfo(
                "FiscalPro",
                (
                    "XMLs de NF-e importados com sucesso!\n\n"
                    f"Arquivos XML encontrados: {self.importacao_nfe_xml.total_arquivos_xml:,}\n"
                    f"NF-e válidas: {total:,}\n"
                    f"Duplicadas ignoradas: {self.importacao_nfe_xml.total_duplicadas:,}\n"
                    f"Arquivos ignorados: {ignoradas:,}\n"
                    f"Erros de leitura: {erros:,}\n\n"
                    "Agora clique em Cruzar Ficha Tributária."
                ).replace(",", "."),
                parent=self,
            )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao importar XMLs de NF-e.")
        finally:
            if self.resultado is not None:
                self.btn_auditar_tributacao.configure(state="normal")

    def executar_auditoria_tributaria(self):
        if self.resultado is None:
            messagebox.showwarning(
                "FiscalPro", "Abra um SPED antes de executar a auditoria tributária.", parent=self
            )
            return
        contexto = {
            "empresa": self.aud_empresa_var.get().strip(),
            "regime": self.aud_regime_var.get().strip(),
            "finalidade": self.aud_finalidade_var.get().strip(),
            "contribuinte": self.aud_contribuinte_var.get().strip(),
        }
        if not contexto["regime"]:
            continuar = messagebox.askyesno(
                "FiscalPro",
                (
                    "O regime tributário não foi informado. A auditoria pode usar somente regras "
                    "genéricas e gerar mais avisos de baixa aderência.\n\nDeseja continuar mesmo assim?"
                ),
                parent=self,
            )
            if not continuar:
                self.abas.select(self.aba_tributaria)
                return
        try:
            self.btn_auditar_tributacao.configure(state="disabled")
            self.btn_relatorio_tributario.configure(state="disabled")
            self.btn_preparar_tributaria.configure(state="disabled")
            self.btn_aplicar_tributaria.configure(state="disabled")
            self.preparacao_correcao_tributaria = None
            self._limpar_correcao_tributaria()
            self.auditoria_tributaria = self.motor.auditar_tributacao(
                contexto, self._atualizar_progresso
            )
            self._exibir_auditoria_tributaria()
            self.abas.select(self.aba_tributaria)
            self.btn_relatorio_tributario.configure(state="normal")
            self.btn_preparar_tributaria.configure(
                state="normal" if self.auditoria_tributaria.apontamentos else "disabled"
            )
            resumo = self.auditoria_tributaria
            mensagem = (
                f"Itens C170 auditados: {resumo.total_itens:,}\n"
                f"Itens com regra tributária: {resumo.itens_com_regra:,}\n"
                f"Itens sem regra: {resumo.itens_sem_regra:,}\n"
                f"Erros: {resumo.erros:,}\n"
                f"Avisos: {resumo.avisos:,}\n"
                f"Conformidade por item: {resumo.conformidade:.2f}%"
            ).replace(",", ".")
            if resumo.erros:
                messagebox.showwarning(
                    "FiscalPro — Auditoria Tributária",
                    mensagem + "\n\nRevise os apontamentos antes de corrigir o SPED.",
                    parent=self,
                )
            else:
                messagebox.showinfo(
                    "FiscalPro — Auditoria Tributária",
                    mensagem + "\n\nNenhuma divergência bloqueante foi encontrada nas regras executadas.",
                    parent=self,
                )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha na auditoria tributária integrada.")
        finally:
            self.btn_auditar_tributacao.configure(state="normal")

    def salvar_relatorio_tributario(self):
        if self.resultado is None or self.auditoria_tributaria is None:
            messagebox.showwarning(
                "FiscalPro", "Execute primeiro a auditoria tributária integrada.", parent=self
            )
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar relatório da auditoria tributária",
            defaultextension=".txt",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=f"{self.resultado.caminho.stem}_AUDITORIA_TRIBUTARIA.txt",
            filetypes=[("Relatório de texto", "*.txt")],
            parent=self,
        )
        if not caminho:
            return
        try:
            destino = self.motor.salvar_relatorio_auditoria_tributaria(caminho)
            messagebox.showinfo(
                "FiscalPro", f"Relatório salvo com sucesso!\n\n{destino}", parent=self
            )
            self.lbl_status.config(text="Relatório da auditoria tributária salvo.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def executar_auditoria_difal(self):
        if self.resultado is None:
            messagebox.showwarning("FiscalPro", "Abra um SPED Fiscal antes de auditar o DIFAL.", parent=self)
            return
        if self.resultado.estatisticas.tipo_sped != "EFD ICMS/IPI (Fiscal)":
            messagebox.showwarning(
                "FiscalPro", "A auditoria automática de DIFAL funciona somente no SPED Fiscal.", parent=self
            )
            return
        try:
            self.btn_auditar_difal.configure(state="disabled")
            self.btn_relatorio_difal.configure(state="disabled")
            self.btn_excel_difal.configure(state="disabled")
            self.auditoria_difal = self.motor.auditar_difal(self._atualizar_progresso)
            self._exibir_difal()
            self.abas.select(self.aba_difal)
            self.btn_relatorio_difal.configure(state="normal")
            self.btn_excel_difal.configure(state="normal")
            r = self.auditoria_difal
            xml_texto = (
                f"XMLs localizados: {r.total_xml_localizados:,}."
                if self.importacao_nfe_xml is not None
                else "XMLs não importados: resultado preliminar por CFOP/C101."
            )
            mensagem = (
                f"NF-e interestaduais: {r.total_interestaduais:,}\n"
                f"Consumidor final não contribuinte confirmado: {r.total_final_nao_contribuinte_confirmado:,}\n"
                f"Confirmadas sem C101: {r.total_sem_c101_quando_confirmado:,}\n"
                f"Erros: {r.erros:,} | Avisos/Revisões: {r.avisos:,}\n"
                f"Sem XML com cálculo reconstruído: {r.total_calculados_sem_xml:,}\n"
                f"Divergências origem/CST SPED x XML: {r.total_divergencias_origem:,}\n"
                f"NF-e com origens/CST mistas: {r.total_origem_mista_sped:,}\n"
                f"DIFAL devido total: {self._moeda_difal(r.valor_difal_devido)}\n"
                f"{xml_texto}"
            ).replace(",", ".")
            if r.erros:
                messagebox.showwarning(
                    "FiscalPro — DIFAL automático",
                    mensagem + "\n\nRevise as notas destacadas antes do fechamento do SPED.",
                    parent=self,
                )
            else:
                messagebox.showinfo("FiscalPro — DIFAL automático", mensagem, parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha na auditoria automática de DIFAL.")
        finally:
            if self.resultado is not None and self.resultado.estatisticas.tipo_sped == "EFD ICMS/IPI (Fiscal)":
                self.btn_auditar_difal.configure(state="normal")

    def salvar_relatorio_difal(self):
        if self.resultado is None or self.auditoria_difal is None:
            messagebox.showwarning("FiscalPro", "Execute primeiro a auditoria automática de DIFAL.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar relatório de DIFAL/FCP",
            defaultextension=".txt",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=f"{self.resultado.caminho.stem}_AUDITORIA_DIFAL.txt",
            filetypes=[("Relatório de texto", "*.txt")],
            parent=self,
        )
        if not caminho:
            return
        try:
            destino = self.motor.salvar_relatorio_difal(caminho)
            messagebox.showinfo("FiscalPro", f"Relatório de DIFAL salvo com sucesso!\n\n{destino}", parent=self)
            self.lbl_status.config(text="Relatório de DIFAL salvo.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def salvar_excel_difal(self):
        if self.resultado is None or self.auditoria_difal is None:
            messagebox.showwarning("FiscalPro", "Execute primeiro a auditoria automática de DIFAL.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            title="Exportar auditoria DIFAL/FCP para Excel",
            defaultextension=".xlsx",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=f"{self.resultado.caminho.stem}_AUDITORIA_DIFAL.xlsx",
            filetypes=[("Planilha Excel", "*.xlsx")],
            parent=self,
        )
        if not caminho:
            return
        try:
            destino = self.motor.salvar_excel_difal(caminho)
            messagebox.showinfo("FiscalPro", f"Excel do DIFAL exportado com sucesso!\n\n{destino}", parent=self)
            self.lbl_status.config(text="Excel da auditoria DIFAL exportado.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)


    def abrir_detalhe_auditoria_tributaria(self, _evento=None):
        selecao = self.tabela_tributaria.selection()
        if not selecao:
            messagebox.showwarning(
                "FiscalPro", "Selecione uma divergência ou pendência na tabela.", parent=self
            )
            return

        apontamento = self.mapa_auditoria_itens.get(selecao[0])
        if apontamento is None:
            messagebox.showwarning(
                "FiscalPro", "Não foi possível localizar o detalhe do apontamento selecionado.", parent=self
            )
            return

        mensagem = getattr(apontamento, "mensagem", "") or "-"
        orientacao = getattr(apontamento, "orientacao", "") or "-"
        divergencia = "\n\n".join((
            "PROBLEMA / DIVERGÊNCIA",
            mensagem,
            "ORIENTAÇÃO DO FISCALPRO",
            orientacao,
        ))
        comparacao = "\n".join((
            f"Campo: {getattr(apontamento, 'campo', '') or '-'}",
            f"No SPED / documento: {getattr(apontamento, 'atual', '') or '-'}",
            f"Esperado: {getattr(apontamento, 'esperado', '') or '-'}",
            f"Regra: {getattr(apontamento, 'regra_id', '') or '-'}",
            f"Aderência: {getattr(apontamento, 'aderencia', 0):.0f}%" if getattr(apontamento, 'aderencia', 0) else "Aderência: -",
        ))
        contexto = "\n".join((
            f"Nível: {getattr(apontamento, 'nivel', '') or '-'}",
            f"Origem da conferência: {getattr(apontamento, 'origem', '') or '-'}",
            f"Linha: {getattr(apontamento, 'linha', '') or '-'}",
            f"NF / documento: {getattr(apontamento, 'documento', '') or '-'}",
            f"Item: {getattr(apontamento, 'item', '') or '-'}",
            f"Produto: {getattr(apontamento, 'codigo', '') or '-'}",
            f"NCM: {getattr(apontamento, 'ncm', '') or '-'}",
        ))

        abrir_detalhes_ampliados(
            self,
            titulo="FiscalPro — Divergência tributária ampliada",
            cabecalho=(
                f"{getattr(apontamento, 'nivel', '') or 'APONTAMENTO'} — "
                f"{getattr(apontamento, 'campo', '') or 'Conferência tributária'} | "
                f"NCM {getattr(apontamento, 'ncm', '') or '-'}"
            ),
            abas=(
                ("Divergência / orientação", divergencia),
                ("Comparação", comparacao),
                ("Contexto do item", contexto),
            ),
            rodape="Duplo clique em qualquer linha abre esta visão ampliada. F11 maximiza/restaura.",
        )

    def abrir_ficha_ncm_auditoria(self):
        selecao = self.tabela_tributaria.selection()
        if not selecao:
            messagebox.showwarning(
                "FiscalPro", "Selecione um apontamento que possua NCM.", parent=self
            )
            return
        apontamento = self.mapa_auditoria_itens.get(selecao[0])
        ncm = getattr(apontamento, "ncm", "") if apontamento else ""
        if len("".join(c for c in str(ncm) if c.isdigit())) != 8:
            messagebox.showwarning(
                "FiscalPro", "O apontamento selecionado não possui um NCM válido.", parent=self
            )
            return
        from src.ui.janela_ficha_tributaria import JanelaFichaTributaria

        contexto = {
            "empresa": self.aud_empresa_var.get().strip(),
            "regime": self.aud_regime_var.get().strip(),
            "finalidade": self.aud_finalidade_var.get().strip(),
        }
        JanelaFichaTributaria(self, contexto=contexto, ncm=ncm)

    def preparar_correcoes_tributarias(self):
        if self.resultado is None or self.auditoria_tributaria is None:
            messagebox.showwarning(
                "FiscalPro",
                "Execute primeiro a Auditoria Tributária integrada.",
                parent=self,
            )
            return
        try:
            self.btn_preparar_tributaria.configure(state="disabled")
            self.btn_aplicar_tributaria.configure(state="disabled")
            self.preparacao_correcao_tributaria = self.motor.preparar_correcoes_tributarias(
                self._atualizar_progresso
            )
            self._exibir_correcao_tributaria()
            self.abas.select(self.aba_correcao_tributaria)
            preparacao = self.preparacao_correcao_tributaria
            aplicaveis = len([p for p in preparacao.propostas if p.aplicavel])
            self.btn_aplicar_tributaria.configure(
                state="normal" if aplicaveis else "disabled"
            )
            mensagem = (
                f"Propostas preparadas: {preparacao.total:,}\n"
                f"Alta confiança: {len(preparacao.alta_confianca):,}\n"
                f"Conflitos para escolher: {len(preparacao.conflitos):,}\n"
                f"Aplicáveis após confirmação: {aplicaveis:,}\n\n"
                "Nenhuma correção fiscal foi marcada automaticamente."
            ).replace(",", ".")
            if preparacao.conflitos:
                messagebox.showwarning(
                    "FiscalPro — Correção Tributária",
                    mensagem + "\n\nRevise os conflitos entre Ficha e XML antes de aplicar.",
                    parent=self,
                )
            else:
                messagebox.showinfo(
                    "FiscalPro — Correção Tributária", mensagem, parent=self
                )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao preparar correções tributárias.")
        finally:
            if self.auditoria_tributaria is not None:
                self.btn_preparar_tributaria.configure(state="normal")

    def _proposta_correcao_tributaria_selecionada(self):
        selecao = self.tabela_correcao_tributaria.selection()
        if not selecao:
            messagebox.showwarning(
                "FiscalPro", "Selecione uma proposta tributária.", parent=self
            )
            return None
        proposta = self.mapa_correcao_tributaria.get(selecao[0])
        if proposta is None:
            messagebox.showwarning(
                "FiscalPro", "A proposta selecionada não está mais disponível.", parent=self
            )
        return proposta

    def marcar_correcoes_tributarias_confiaveis(self):
        if self.preparacao_correcao_tributaria is None:
            messagebox.showwarning(
                "FiscalPro", "Prepare primeiro as correções tributárias.", parent=self
            )
            return
        marcadas = 0
        for proposta in self.preparacao_correcao_tributaria.alta_confianca:
            self.motor.atualizar_correcao_tributaria(
                proposta.identificador, selecionada=True
            )
            marcadas += 1
        self._exibir_correcao_tributaria()
        self._atualizar_botao_aplicar_tributaria()
        messagebox.showinfo(
            "FiscalPro",
            (
                f"{marcadas:,} proposta(s) de alta confiança foram marcadas.\n\n"
                "Revise os valores antes de aplicar; a confirmação final continua sendo sua."
            ).replace(",", "."),
            parent=self,
        )

    def desmarcar_correcoes_tributarias(self):
        if self.preparacao_correcao_tributaria is None:
            return
        for proposta in self.preparacao_correcao_tributaria.propostas:
            if proposta.selecionada:
                self.motor.atualizar_correcao_tributaria(
                    proposta.identificador, selecionada=False
                )
        self._exibir_correcao_tributaria()
        self._atualizar_botao_aplicar_tributaria()

    def alternar_correcao_tributaria(self):
        proposta = self._proposta_correcao_tributaria_selecionada()
        if proposta is None:
            return
        if not proposta.aplicavel:
            if proposta.modo == "Conflito — escolher valor":
                messagebox.showwarning(
                    "FiscalPro",
                    "A Ficha e o XML divergem. Clique em Escolher/editar valor antes de marcar.",
                    parent=self,
                )
            else:
                messagebox.showwarning(
                    "FiscalPro",
                    "Esta proposta é somente para revisão e não pode ser aplicada diretamente.",
                    parent=self,
                )
            return
        try:
            self.motor.atualizar_correcao_tributaria(
                proposta.identificador, selecionada=not proposta.selecionada
            )
            self._exibir_correcao_tributaria(proposta.identificador)
            self._atualizar_botao_aplicar_tributaria()
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def editar_valor_correcao_tributaria(self):
        proposta = self._proposta_correcao_tributaria_selecionada()
        if proposta is None:
            return
        if not proposta.editavel:
            messagebox.showwarning(
                "FiscalPro", "Esta proposta não aceita edição direta.", parent=self
            )
            return
        alternativas = ""
        if proposta.alternativas:
            alternativas = "\nAlternativas encontradas: " + " / ".join(proposta.alternativas)
        valor = simpledialog.askstring(
            "FiscalPro — Escolher valor tributário",
            (
                f"Registro: {proposta.registro} — linha {proposta.numero_linha or '-'}\n"
                f"Produto: {proposta.codigo or '-'} — campo {proposta.campo}\n"
                f"Valor atual: {proposta.valor_atual or '(vazio)'}"
                f"{alternativas}\n\nInforme o valor que deverá ser gravado:"
            ),
            initialvalue=proposta.valor_sugerido,
            parent=self,
        )
        if valor is None:
            return
        try:
            self.motor.atualizar_correcao_tributaria(
                proposta.identificador, valor_novo=valor
            )
            self._exibir_correcao_tributaria(proposta.identificador)
            self._atualizar_botao_aplicar_tributaria()
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def _atualizar_botao_aplicar_tributaria(self):
        selecionadas = (
            self.preparacao_correcao_tributaria.selecionadas
            if self.preparacao_correcao_tributaria is not None
            else []
        )
        self.btn_aplicar_tributaria.configure(
            state="normal" if selecionadas else "disabled"
        )

    def aplicar_correcoes_tributarias(self):
        if self.resultado is None or self.preparacao_correcao_tributaria is None:
            messagebox.showwarning(
                "FiscalPro", "Prepare primeiro as correções tributárias.", parent=self
            )
            return
        selecionadas = self.preparacao_correcao_tributaria.selecionadas
        if not selecionadas:
            messagebox.showwarning(
                "FiscalPro", "Marque pelo menos uma correção para aplicar.", parent=self
            )
            return
        confirmar = messagebox.askyesno(
            "FiscalPro — Confirmar correções tributárias",
            (
                f"Serão aplicadas {len(selecionadas):,} alteração(ões) em uma NOVA CÓPIA.\n\n"
                "O arquivo original não será alterado. As sugestões podem mudar CST, CFOP, "
                "NCM, CEST ou alíquotas. Quando uma alíquota de PIS/COFINS for alterada, "
                "o FiscalPro recalculará o valor do item e os totais do C100.\n\n"
                "A apuração do Bloco M deverá ser regenerada e validada no PVA oficial. "
                "Confirme que você revisou a operação e a base legal.\n\nDeseja continuar?"
            ).replace(",", "."),
            parent=self,
        )
        if not confirmar:
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar SPED com correções tributárias",
            defaultextension=".txt",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=f"{self.resultado.caminho.stem}_TRIBUTARIO_CORRIGIDO.txt",
            filetypes=[("Arquivo SPED", "*.txt")],
            parent=self,
        )
        if not caminho:
            return
        try:
            self.btn_aplicar_tributaria.configure(state="disabled")
            resultado = self.motor.aplicar_correcoes_tributarias(
                caminho, self._atualizar_progresso
            )
            mensagem = (
                "Correção tributária concluída!\n\n"
                f"Correções confirmadas: {resultado.total_confirmadas:,}\n"
                f"Recálculos automáticos: {resultado.total_recalculadas:,}\n"
                f"Ações totais gravadas: {resultado.total_aplicadas:,}\n"
                f"Documentos C100 retotalizados: {resultado.documentos_retotalizados:,}\n"
                f"Conflitos ainda pendentes: {resultado.total_conflitos:,}\n"
                f"Erros da auditoria: {resultado.erros_auditoria_antes:,} → "
                f"{resultado.erros_auditoria_depois:,}\n"
                f"Avisos da auditoria: {resultado.avisos_auditoria_antes:,} → "
                f"{resultado.avisos_auditoria_depois:,}\n"
                f"Erros no Pré-PVA da cópia: {resultado.erros_pre_pva_depois:,}\n"
                f"Avisos no Pré-PVA da cópia: {resultado.avisos_pre_pva_depois:,}\n\n"
                f"SPED: {resultado.caminho_sped}\n"
                f"Relatório: {resultado.caminho_relatorio}"
            ).replace(",", ".")
            if resultado.requer_reapuracao_bloco_m:
                mensagem += (
                    "\n\nATENÇÃO: os documentos foram corrigidos, mas a apuração do Bloco M "
                    "precisa ser regenerada e validada no PVA oficial antes da transmissão."
                )
            if resultado.avisos_recalculo:
                mensagem += "\n\nAvisos do recálculo: " + str(len(resultado.avisos_recalculo))
            carregar = messagebox.askyesno(
                "FiscalPro — Correção Tributária",
                mensagem + "\n\nDeseja carregar a nova cópia no SPED Inteligente agora?",
                parent=self,
            )
            if carregar:
                self._carregar_sped(str(resultado.caminho_sped))
            else:
                self.lbl_status.config(
                    text="SPED com correções tributárias e relatório gerados."
                )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao aplicar correções tributárias.")
        finally:
            self._atualizar_botao_aplicar_tributaria()

    def exportar_excel(self):
        if self.resultado is None:
            messagebox.showwarning("FiscalPro", "Abra um arquivo SPED antes de exportar.", parent=self)
            return

        diagnostico_m = self.motor.verificar_apuracao_bloco_m()
        if diagnostico_m.bloqueado:
            messagebox.showwarning(
                "FiscalPro — Bloco M não apurado",
                diagnostico_m.mensagem_bloqueio(),
                parent=self,
            )
            self.lbl_status.config(text="Exportação bloqueada: gere as apurações no PGE.")
            return

        nome_sugerido = f"{self.resultado.caminho.stem}_ORGANIZADO.xlsx"
        caminho = filedialog.asksaveasfilename(
            title="Salvar exportação SPED em Excel",
            defaultextension=".xlsx",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=nome_sugerido,
            filetypes=[("Planilha do Excel", "*.xlsx")],
            parent=self,
        )
        if not caminho:
            return

        try:
            self.btn_exportar.configure(state="disabled")
            exportacao = self.motor.exportar_excel(caminho, self._atualizar_progresso)
            total_linhas = f"{exportacao.total_linhas:,}".replace(",", ".")
            total_registros = f"{exportacao.total_registros:,}".replace(",", ".")
            messagebox.showinfo(
                "FiscalPro",
                (
                    "Exportação concluída com sucesso!\n\n"
                    f"Abas organizadas por registro: {exportacao.total_abas}\n"
                    f"Linhas do arquivo: {total_linhas}\n"
                    f"Registros exportados: {total_registros}\n\n"
                    f"Arquivo salvo em:\n{exportacao.caminho}"
                ),
                parent=self,
            )
            self.lbl_status.config(text="Excel organizado gerado com sucesso.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao exportar para Excel.")
        finally:
            self.btn_exportar.configure(state="normal")

    def analisar_correcoes(self):
        if self.resultado is None:
            messagebox.showwarning("FiscalPro", "Abra um arquivo SPED antes de analisar.", parent=self)
            return
        try:
            self.btn_analisar.configure(state="disabled")
            self.btn_corrigir.configure(state="disabled")
            self.analise_correcoes = self.motor.analisar_correcoes(self._atualizar_progresso)
            self._exibir_correcoes()
            self.abas.select(self.aba_correcoes)
            if self.analise_correcoes.total_automaticas:
                self.btn_corrigir.configure(state="normal")
            else:
                total = self.analise_correcoes.total
                manuais = self.analise_correcoes.total_manuais
                messagebox.showinfo(
                    "FiscalPro",
                    (
                        f"Análise concluída: {total} apontamentos.\n\n"
                        f"{manuais} pendências precisam de revisão manual. "
                        "Nenhuma delas será alterada automaticamente.\n\n"
                        "Consulte os detalhes na aba Correções inteligentes."
                    ),
                    parent=self,
                )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao analisar correções.")
        finally:
            self.btn_analisar.configure(state="normal")

    def gerar_sped_corrigido(self):
        if self.resultado is None or self.analise_correcoes is None:
            messagebox.showwarning("FiscalPro", "Faça primeiro a análise de correções.", parent=self)
            return
        if not self.analise_correcoes.total_automaticas:
            messagebox.showinfo("FiscalPro", "Não existem correções automáticas seguras para aplicar.", parent=self)
            return

        nome_sugerido = f"{self.resultado.caminho.stem}_INTELIGENTE_CORRIGIDO.txt"
        caminho = filedialog.asksaveasfilename(
            title="Salvar nova cópia corrigida do SPED",
            defaultextension=".txt",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=nome_sugerido,
            filetypes=[("Arquivo SPED", "*.txt")],
            parent=self,
        )
        if not caminho:
            return

        confirmar = messagebox.askyesno(
            "FiscalPro",
            (
                f"Serão aplicadas {self.analise_correcoes.total_automaticas} correções estruturais seguras "
                "em uma NOVA CÓPIA do arquivo.\n\n"
                "Nenhuma base, alíquota, CST ou valor fiscal será recalculado nesta sprint.\n\n"
                "Deseja continuar?"
            ),
            parent=self,
        )
        if not confirmar:
            return

        try:
            self.btn_corrigir.configure(state="disabled")
            geracao = self.motor.gerar_sped_corrigido(caminho, self._atualizar_progresso)
            messagebox.showinfo(
                "FiscalPro",
                (
                    "Nova cópia do SPED gerada com sucesso!\n\n"
                    f"Correções aplicadas: {geracao.total_aplicadas}\n"
                    f"Pendências manuais: {geracao.total_pendencias_manuais}\n\n"
                    f"SPED corrigido:\n{geracao.caminho_sped}\n\n"
                    f"Relatório:\n{geracao.caminho_relatorio}"
                ),
                parent=self,
            )
            self.lbl_status.config(text="SPED corrigido e relatório gerados com sucesso.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao gerar a cópia corrigida.")
        finally:
            self.btn_corrigir.configure(state="normal")

    def selecionar_danfes_icms(self):
        if self.resultado is None:
            messagebox.showwarning(
                "FiscalPro", "Abra um arquivo SPED antes de selecionar os XMLs/PDFs das entradas.", parent=self
            )
            return
        arquivos = filedialog.askopenfilenames(
            title="Selecione XMLs, PDFs ou ZIP das compras para revenda",
            filetypes=[
                ("NF-e XML, DANFE PDF ou ZIP", "*.xml *.pdf *.zip"),
                ("Arquivos XML de NF-e", "*.xml"),
                ("DANFE em PDF", "*.pdf"),
                ("Arquivos ZIP", "*.zip"),
                ("Todos os arquivos", "*.*"),
            ],
            parent=self,
        )
        if not arquivos:
            return
        try:
            self.btn_selecionar_danfes_icms.configure(state="disabled")
            self.btn_gerar_icms_danfe.configure(state="disabled")
            self.analise_danfe_icms = self.motor.analisar_danfes_icms(
                list(arquivos), self._atualizar_progresso
            )
            analise = self.analise_danfe_icms
            self.lbl_danfe_icms.config(
                text=(
                    f"Documentos: {analise.total_pdfs}  •  Aptas: {analise.total_aptas}  •  "
                    f"Itens: {analise.total_itens_aptos}  •  CFOPs a corrigir: {analise.total_cfop_corrigir}  •  ICMS: "
                    f"{self._fmt_moeda(analise.total_icms_apto)}  •  "
                    f"Sem crédito: {analise.total_sem_credito}  •  Revisão: {analise.total_revisao}"
                ),
                fg="#0B6B2A" if analise.pode_gerar else "#8A5A00",
            )
            if analise.pode_gerar:
                self.btn_gerar_icms_danfe.configure(state="normal")
            messagebox.showinfo(
                "FiscalPro — Conferência das NF-e de entrada",
                (
                    f"Documentos lidos: {analise.total_pdfs}\n"
                    f"Notas aptas: {analise.total_aptas}\n"
                    f"Itens aptos: {analise.total_itens_aptos}\n"
                    f"CFOPs de entrada a corrigir: {analise.total_cfop_corrigir}\n"
                    f"ICMS próprio localizado: {self._fmt_moeda(analise.total_icms_apto)}\n"
                    f"Notas sem ICMS próprio: {analise.total_sem_credito}\n"
                    f"Notas para revisão: {analise.total_revisao}\n"
                    f"Não encontradas no SPED: {analise.total_nao_encontradas}\n\n"
                    "Somente as notas aptas serão alteradas na nova cópia do SPED."
                ),
                parent=self,
            )
            self.abas.select(self.aba_estorno_icms)
            self.lbl_status.config(text="NF-e de entrada conferidas contra o SPED.")
        except Exception as erro:
            self.analise_danfe_icms = None
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao conferir as NF-e de entrada.")
        finally:
            self.btn_selecionar_danfes_icms.configure(state="normal")

    def gerar_sped_icms_danfe(self):
        if self.resultado is None or self.analise_danfe_icms is None:
            messagebox.showwarning(
                "FiscalPro", "Selecione e confira primeiro os XMLs/PDFs/ZIP das compras.", parent=self
            )
            return
        if not self.analise_danfe_icms.pode_gerar:
            messagebox.showwarning(
                "FiscalPro", "Nenhuma NF-e apta foi encontrada para preencher o ICMS.", parent=self
            )
            return
        nome = f"{self.resultado.caminho.stem}_ICMS_CFOP_ENTRADAS_CORRIGIDO.txt"
        caminho = filedialog.asksaveasfilename(
            title="Salvar nova cópia do SPED com ICMS das compras",
            defaultextension=".txt",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=nome,
            filetypes=[("Arquivo SPED", "*.txt")],
            parent=self,
        )
        if not caminho:
            return
        try:
            self.btn_gerar_icms_danfe.configure(state="disabled")
            geracao = self.motor.gerar_sped_com_icms_danfe(
                caminho, self._atualizar_progresso
            )
            carregar = messagebox.askyesno(
                "FiscalPro",
                (
                    "Nova cópia do SPED gerada com sucesso!\n\n"
                    f"Notas alteradas: {geracao.notas_alteradas}\n"
                    f"Itens preenchidos: {geracao.itens_alterados}\n"
                    f"CFOPs corrigidos: {geracao.cfops_corrigidos}\n"
                    f"ICMS incluído: {self._fmt_moeda(geracao.total_icms)}\n\n"
                    f"SPED: {geracao.caminho_sped}\n\n"
                    f"Memória: {geracao.caminho_memoria}\n\n"
                    f"Relatório: {geracao.caminho_relatorio}\n\n"
                    "Deseja abrir esta nova cópia e preparar o estorno agora?"
                ),
                parent=self,
            )
            self.lbl_status.config(text="SPED com ICMS e CFOPs das NF-e de entrada gerado com sucesso.")
            if carregar:
                self._carregar_sped(str(geracao.caminho_sped))
                self.analisar_estorno_creditos_icms()
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao gerar o SPED com ICMS das NF-e de entrada.")
        finally:
            if self.analise_danfe_icms is not None and self.analise_danfe_icms.pode_gerar:
                self.btn_gerar_icms_danfe.configure(state="normal")

    def analisar_estorno_creditos_icms(self):
        if self.resultado is None:
            messagebox.showwarning(
                "FiscalPro", "Abra um arquivo SPED antes de analisar os créditos.", parent=self
            )
            return
        try:
            self.btn_estorno_icms.configure(state="disabled")
            self.btn_gerar_estorno.configure(state="disabled")
            self.analise_estorno_icms = self.motor.analisar_estorno_creditos_icms(
                self._atualizar_progresso
            )
            self._exibir_estorno_icms()
            if hasattr(self, "btn_conferir_estorno_nf"):
                self.btn_conferir_estorno_nf.configure(state="normal")
            self.abas.select(self.aba_estorno_icms)
            if self.analise_estorno_icms.pode_gerar:
                self.btn_gerar_estorno.configure(state="normal")
            elif self.analise_estorno_icms.total_existente > 0:
                messagebox.showinfo(
                    "FiscalPro",
                    "Os créditos localizados já possuem estorno C197 correspondente. Nada será duplicado.",
                    parent=self,
                )
            else:
                messagebox.showwarning(
                    "FiscalPro",
                    "Não foram encontrados créditos seguros para estorno automático. Consulte os itens em revisão.",
                    parent=self,
                )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao analisar o estorno de créditos.")
        finally:
            self.btn_estorno_icms.configure(state="normal")

    def gerar_sped_estornado(self):
        if self.resultado is None or self.analise_estorno_icms is None:
            messagebox.showwarning(
                "FiscalPro", "Execute primeiro a análise dos créditos de ICMS.", parent=self
            )
            return
        opcao = self.codigo_estorno_var.get().strip()
        codigo = self.OPCOES_CODIGO_ESTORNO.get(opcao, "")
        if not codigo:
            messagebox.showwarning("FiscalPro", "Selecione o código do ajuste C197.", parent=self)
            return

        alerta = (
            f"Código selecionado: {codigo}\n\n"
            f"Créditos a estornar: {self._fmt_moeda(self.analise_estorno_icms.total_pendente)}\n"
            f"Notas aptas: {self.analise_estorno_icms.notas_pendentes}\n"
            f"Itens: {self.analise_estorno_icms.itens_pendentes}\n\n"
            "O arquivo original não será alterado. Confirme que o código corresponde ao regime especial vigente."
        )
        if codigo == "MG50000018":
            alerta += (
                "\n\nATENÇÃO: a tabela vigente da SEF/MG associa MG50000018 ao FEM em entrada "
                "devolvida. Use esta opção somente para reproduzir o modelo anterior com orientação expressa."
            )
        if not messagebox.askyesno("FiscalPro — Estorno de ICMS", alerta, parent=self):
            return

        nome = f"{self.resultado.caminho.stem}_ESTORNO_ICMS.txt"
        caminho = filedialog.asksaveasfilename(
            title="Salvar nova cópia do SPED com estorno de créditos",
            defaultextension=".txt", initialdir=str(self.resultado.caminho.parent),
            initialfile=nome, filetypes=[("Arquivo SPED", "*.txt")], parent=self,
        )
        if not caminho:
            return
        try:
            self.btn_gerar_estorno.configure(state="disabled")
            geracao = self.motor.gerar_sped_com_estorno_icms(
                caminho, codigo, "ESTORNO DE CREDITO DE ICMS", self._atualizar_progresso
            )
            messagebox.showinfo(
                "FiscalPro",
                (
                    "SPED com estorno gerado com sucesso!\n\n"
                    f"Notas alteradas: {geracao.notas_alteradas}\n"
                    f"Itens ajustados: {geracao.itens_ajustados}\n"
                    f"Total estornado: {self._fmt_moeda(geracao.total_estornado)}\n"
                    f"Código C197: {geracao.codigo_ajuste}\n\n"
                    f"SPED: {geracao.caminho_sped}\n\n"
                    f"Memória: {geracao.caminho_memoria}\n\n"
                    f"Relatório: {geracao.caminho_relatorio}\n\n"
                    "Valide a nova cópia no PVA antes da entrega."
                ),
                parent=self,
            )
            self.lbl_status.config(text="SPED com estorno de créditos gerado com sucesso.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao gerar o SPED com estorno de créditos.")
        finally:
            self.btn_gerar_estorno.configure(
                state="normal" if self.analise_estorno_icms.pode_gerar else "disabled"
            )

    def _limpar_estorno_icms(self):
        self.analise_estorno_icms = None
        self.analise_danfe_icms = None
        if hasattr(self, "tabela_estorno"):
            for item in self.tabela_estorno.get_children():
                self.tabela_estorno.delete(item)
        if hasattr(self, "btn_gerar_estorno"):
            self.btn_gerar_estorno.configure(state="disabled")
        if hasattr(self, "btn_conferir_estorno_nf"):
            self.btn_conferir_estorno_nf.configure(state="disabled")
        if hasattr(self, "btn_gerar_icms_danfe"):
            self.btn_gerar_icms_danfe.configure(state="disabled")
        if hasattr(self, "lbl_danfe_icms"):
            self.lbl_danfe_icms.config(
                text="Selecione os XMLs/PDFs/ZIP das compras para revenda.", fg=COR_TEXTO
            )
        if hasattr(self, "lbl_resumo_estorno"):
            self.lbl_resumo_estorno.config(
                text=(
                    "Fluxo em duas etapas: primeiro confira os XMLs das NF-e de entrada (preferencial) ou PDFs/DANFEs "
                    "das compras para revenda, confira/corrija o CFOP de entrada e preencha o ICMS próprio nos C170/C190; depois analise e gere os C195/C197 de estorno. "
                    "O arquivo original permanece intacto."
                )
            )
        if hasattr(self, "lbl_alerta_estorno"):
            self.lbl_alerta_estorno.config(text="Abra um SPED e execute a análise.")

    def _exibir_estorno_icms(self):
        analise = self.analise_estorno_icms
        if analise is None:
            return
        for linha in self.tabela_estorno.get_children():
            self.tabela_estorno.delete(linha)
        for nota in analise.notas:
            for item in nota.itens:
                self.tabela_estorno.insert(
                    "", "end",
                    values=(
                        item.status, item.numero_documento, self._fmt_data(item.data_entrada),
                        item.participante, item.codigo_item, item.descricao_item, item.cfop,
                        self._fmt_moeda(item.base_icms), self._fmt_numero(item.aliquota_icms) + "%",
                        self._fmt_moeda(item.valor_icms),
                        (
                            f"{item.codigo_existente} — {self._fmt_moeda(item.valor_c197_existente)}"
                            if item.codigo_existente and item.valor_c197_existente > 0
                            else item.codigo_existente
                        ),
                        item.observacao,
                    ),
                    tags=(item.status,),
                )
        regime = analise.regime_especial or "não identificado"
        self.lbl_resumo_estorno.config(
            text=(
                f"Regime especial detectado: {regime}  •  Créditos de entrada: "
                f"{self._fmt_moeda(analise.total_creditos_entradas)}  •  Pendentes: "
                f"{self._fmt_moeda(analise.total_pendente)} ({analise.notas_pendentes} notas / "
                f"{analise.itens_pendentes} itens)  •  Já estornados: "
                f"{self._fmt_moeda(analise.total_existente)}  •  Revisão: "
                f"{self._fmt_moeda(analise.total_revisao)}  •  "
                f"Reconciliação de arredondamento prevista: {self._fmt_moeda(sum((nota.ajuste_arredondamento for nota in analise.notas), 0))}"
            )
        )
        alerta = analise.alerta_codigo_modelo or (
            "Selecione e confirme o código do ajuste antes de gerar a nova cópia."
        )
        self.lbl_alerta_estorno.config(text=alerta)

    def abrir_conferencia_estorno_por_nf(self):
        analise = self.analise_estorno_icms
        if analise is None:
            messagebox.showwarning(
                "FiscalPro", "Execute primeiro a análise do estorno de ICMS.", parent=self
            )
            return

        janela = Toplevel(self)
        janela.title("FiscalPro — Conferência do estorno por NF")
        dimensionar_janela(janela, 1280, 720, 900, 520)
        janela.configure(bg=COR_FUNDO)
        janela.transient(self)

        notas = list(analise.notas)
        total_c100 = sum((nota.valor_icms_c100 for nota in notas), 0)
        total_c170 = sum((nota.valor_itens for nota in notas), 0)
        total_c197 = sum((nota.valor_c197_existente for nota in notas), 0)
        total_previsto = sum((nota.valor_previsto_estorno for nota in notas), 0)
        ajuste_previsto = sum((nota.ajuste_arredondamento for nota in notas), 0)
        total_teorico = sum((nota.valor_icms_teorico for nota in notas), 0)
        notas_reconciliadas = sum(1 for nota in notas if nota.ajuste_arredondamento != 0)
        diferenca_c170 = total_c170 - total_c100
        diferenca_c197 = total_c197 - total_c100 if total_c197 else 0

        resumo = Label(
            janela,
            text=(
                f"ICMS C100: {self._fmt_moeda(total_c100)}  •  Soma C170: {self._fmt_moeda(total_c170)}  •  "
                f"Dif. C170-C100: {self._fmt_moeda(diferenca_c170)}\n"
                f"ICMS teórico (BC × alíquota): {self._fmt_moeda(total_teorico)}  •  "
                f"C197 existente: {self._fmt_moeda(total_c197)}  •  Estorno previsto: {self._fmt_moeda(total_previsto)}\n"
                f"Reconciliação automática: {self._fmt_moeda(ajuste_previsto)} em {notas_reconciliadas} NF(s)"
            ),
            justify="left", anchor="w", bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 9, "bold"),
        )
        resumo.pack(fill=X, padx=8, pady=(8, 4), ipady=7)

        Label(
            janela,
            text=(
                "As notas com diferença aparecem primeiro. O FiscalPro reconcilia centavos por NF. Acima de R$ 0,01, "
                "a correção só é automática quando cada C170 coincide com BC × alíquota arredondado e o C100 coincide "
                "exatamente com a soma teórica sem arredondar item a item. Caso contrário, a NF fica em REVISAR. "
                "Dê dois cliques em uma NF para localizar seus itens na tabela principal."
            ),
            justify="left", anchor="w", bg=COR_FUNDO, fg="#8A5A00", font=("Segoe UI", 9),
        ).pack(fill=X, padx=10, pady=(0, 6))

        frame = ttk.Frame(janela)
        frame.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))
        colunas = (
            "situacao", "nf", "entrada", "fornecedor", "c100", "c170",
            "teorico", "impacto", "limite", "c197", "previsto", "ajuste",
        )
        tabela = ttk.Treeview(frame, columns=colunas, show="headings", height=18)
        titulos = {
            "situacao": "Situação", "nf": "NF", "entrada": "Entrada", "fornecedor": "Fornecedor",
            "c100": "ICMS C100", "c170": "Soma C170", "teorico": "ICMS teórico", "impacto": "Impacto bruto",
            "limite": "Teto arredond.", "c197": "C197 existente", "previsto": "Estorno previsto", "ajuste": "Ajuste centavos",
        }
        larguras = {
            "situacao": 110, "nf": 90, "entrada": 85, "fornecedor": 235, "c100": 100,
            "c170": 100, "teorico": 105, "impacto": 95, "limite": 105, "c197": 110, "previsto": 115, "ajuste": 105,
        }
        for coluna in colunas:
            tabela.heading(coluna, text=titulos[coluna])
            tabela.column(coluna, width=larguras[coluna], anchor="w")
        tabela.tag_configure("DIVERGENCIA", foreground="#B00020")
        tabela.tag_configure("AJUSTE", foreground="#8A5A00")
        tabela.tag_configure("OK", foreground="#0B6B2A")

        def chave_ordem(nota):
            impacto = nota.diferenca_c197_c100 if nota.valor_c197_existente else nota.diferenca_c170_c100
            return (0 if impacto else 1, -abs(impacto), nota.numero_documento)

        for nota in sorted(notas, key=chave_ordem):
            impacto = nota.diferenca_c197_c100 if nota.valor_c197_existente else nota.diferenca_c170_c100
            if nota.ajuste_arredondamento != 0 and nota.status == "PENDENTE":
                tag = "AJUSTE"
                situacao = "ARREDOND."
            elif impacto != 0:
                tag = "DIVERGENCIA"
                situacao = "DIVERGÊNCIA"
            else:
                tag = "OK"
                situacao = "OK"
            previsto = nota.valor_previsto_estorno if nota.status == "PENDENTE" else nota.valor_c197_existente
            tabela.insert(
                "", "end",
                values=(
                    situacao, nota.numero_documento, self._fmt_data(nota.data_entrada), nota.participante,
                    self._fmt_moeda(nota.valor_icms_c100), self._fmt_moeda(nota.valor_itens),
                    self._fmt_moeda(nota.valor_icms_teorico), self._fmt_moeda(impacto),
                    self._fmt_moeda(nota.limite_arredondamento), self._fmt_moeda(nota.valor_c197_existente),
                    self._fmt_moeda(previsto), self._fmt_moeda(nota.ajuste_arredondamento),
                ),
                tags=(tag,),
            )

        barra_y = ttk.Scrollbar(frame, orient="vertical", command=tabela.yview)
        barra_x = ttk.Scrollbar(frame, orient="horizontal", command=tabela.xview)
        tabela.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        tabela.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        def focar_nf(_evento=None):
            selecionado = tabela.selection()
            if not selecionado:
                return
            valores = tabela.item(selecionado[0], "values")
            if len(valores) < 2:
                return
            nf = str(valores[1])
            for iid in self.tabela_estorno.get_children():
                dados = self.tabela_estorno.item(iid, "values")
                if len(dados) > 1 and str(dados[1]) == nf:
                    self.tabela_estorno.selection_set(iid)
                    self.tabela_estorno.focus(iid)
                    self.tabela_estorno.see(iid)
                    self.abas.select(self.aba_estorno_icms)
                    janela.destroy()
                    return

        tabela.bind("<Double-1>", focar_nf)

    @staticmethod
    def _fmt_numero(valor):
        texto = format(valor, "f").rstrip("0").rstrip(".")
        return (texto or "0").replace(".", ",")

    @classmethod
    def _fmt_moeda(cls, valor):
        numero = f"{valor:,.2f}"
        return "R$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _fmt_data(valor):
        texto = (valor or "").strip()
        return f"{texto[:2]}/{texto[2:4]}/{texto[4:]}" if len(texto) == 8 else texto

    def validar_antes_pva(self):
        if self.resultado is None:
            messagebox.showwarning(
                "FiscalPro", "Abra um arquivo SPED antes de validar para o PVA.", parent=self
            )
            return
        try:
            self.btn_validar_pva.configure(state="disabled")
            self.btn_validar_pva_aba.configure(state="disabled")
            self.btn_relatorio_pva.configure(state="disabled")
            self.btn_relatorio_pva_aba.configure(state="disabled")
            self.pre_validacao_pva = self.motor.validar_antes_pva(self._atualizar_progresso)
            self.preparacao_assistida = None
            self._limpar_assistida()
            self._exibir_pre_validacao()
            self.abas.select(self.aba_pre_pva)
            self.btn_relatorio_pva.configure(state="normal")
            self.btn_relatorio_pva_aba.configure(state="normal")
            self.btn_preparar_assistida.configure(state="normal")
            erros = len(self.pre_validacao_pva.erros)
            avisos = len(self.pre_validacao_pva.avisos)
            revisoes = len(self.pre_validacao_pva.revisoes)
            erros_pge = self.pre_validacao_pva.erros_pge_estimados or erros
            if erros:
                messagebox.showwarning(
                    "FiscalPro",
                    (
                        f"Pré-validação concluída com {erros} causa(s) raiz e {avisos} aviso(s) PVA/PGE.\n"
                        f"Revisões extras FiscalPro: {revisoes}.\n"
                        f"Equivalência estimada no PGE: {erros_pge} ocorrência(s).\n\n"
                        "O PGE pode repetir a mesma causa em mais de uma regra e gerar erros "
                        "encadeados durante a apuração. Consulte a aba Pré-Validador PVA."
                    ),
                    parent=self,
                )
            else:
                messagebox.showinfo(
                    "FiscalPro",
                    (
                        f"Pré-validação PVA/PGE concluída sem erros.\n\n"
                        f"Avisos PVA/PGE: {avisos}\n"
                        f"Revisões extras FiscalPro: {revisoes}\n"
                        f"Regras executadas: {self.pre_validacao_pva.regras_executadas}\n\n"
                        "Revisões FiscalPro são conferências adicionais e não bloqueiam. "
                        "Agora faça a validação oficial no PVA/PGE."
                    ),
                    parent=self,
                )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha na pré-validação do PVA.")
        finally:
            self.btn_validar_pva.configure(state="normal")
            self.btn_validar_pva_aba.configure(state="normal")

    def salvar_relatorio_pva(self):
        if self.resultado is None or self.pre_validacao_pva is None:
            messagebox.showwarning(
                "FiscalPro", "Execute primeiro a validação antes do PVA.", parent=self
            )
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar relatório da pré-validação",
            defaultextension=".txt",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=f"{self.resultado.caminho.stem}_PRE_VALIDACAO_PVA.txt",
            filetypes=[("Relatório de texto", "*.txt")],
            parent=self,
        )
        if not caminho:
            return
        try:
            destino = self.motor.salvar_relatorio_pre_pva(caminho)
            messagebox.showinfo(
                "FiscalPro", f"Relatório salvo com sucesso!\n\n{destino}", parent=self
            )
            self.lbl_status.config(text="Relatório da pré-validação salvo com sucesso.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def preparar_correcoes_assistidas(self):
        if self.resultado is None:
            messagebox.showwarning("FiscalPro", "Abra um SPED antes de preparar correções.", parent=self)
            return
        try:
            self.btn_preparar_assistida.configure(state="disabled")
            self.btn_aplicar_assistida.configure(state="disabled")
            self.preparacao_assistida = self.motor.preparar_correcoes_assistidas(
                self._atualizar_progresso
            )
            self.pre_validacao_pva = self.motor.pre_validacao_pva
            if self.pre_validacao_pva is not None:
                self._exibir_pre_validacao()
            self._exibir_correcoes_assistidas()
            self.abas.select(self.aba_assistida)
            if self.preparacao_assistida.selecionadas:
                self.btn_aplicar_assistida.configure(state="normal")
            messagebox.showinfo(
                "FiscalPro",
                (
                    f"Correção assistida preparada com {self.preparacao_assistida.total} item(ns).\n\n"
                    f"Marcadas automaticamente: {len(self.preparacao_assistida.selecionadas)}\n"
                    f"Sugestões para confirmar: {len(self.preparacao_assistida.sugestoes)}\n"
                    f"Preenchimentos manuais: {len(self.preparacao_assistida.preenchimentos)}\n\n"
                    "Revise a aba Correção assistida antes de gerar a nova cópia."
                ),
                parent=self,
            )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao preparar correções assistidas.")
        finally:
            self.btn_preparar_assistida.configure(state="normal")

    def marcar_correcoes_seguras(self):
        if self.preparacao_assistida is None:
            messagebox.showwarning("FiscalPro", "Prepare primeiro as correções assistidas.", parent=self)
            return
        for proposta in self.preparacao_assistida.propostas:
            if proposta.segura and proposta.aplicavel:
                proposta.selecionada = True
        self._exibir_correcoes_assistidas()

    def marcar_todas_correcoes_aplicaveis(self):
        if self.preparacao_assistida is None:
            messagebox.showwarning("FiscalPro", "Prepare primeiro as correções assistidas.", parent=self)
            return

        aplicaveis = [p for p in self.preparacao_assistida.propostas if p.aplicavel]
        if not aplicaveis:
            messagebox.showinfo(
                "FiscalPro",
                "Não há correções com valor sugerido prontas para marcação em lote.",
                parent=self,
            )
            return

        seguras = sum(1 for p in aplicaveis if p.segura)
        sugestoes = sum(1 for p in aplicaveis if not p.segura)
        ja_marcadas = sum(1 for p in aplicaveis if p.selecionada)
        confirmar = messagebox.askyesno(
            "FiscalPro — Marcar em lote",
            (
                f"Serão marcadas {len(aplicaveis):,} correção(ões) aplicável(is) de uma vez.\n\n"
                f"• Automáticas seguras: {seguras:,}\n"
                f"• Sugestões com valor calculado: {sugestoes:,}\n"
                f"• Já estavam marcadas: {ja_marcadas:,}\n\n"
                "Itens somente para revisão ou sem valor sugerido continuarão DESMARCADOS.\n"
                "O arquivo original não será alterado; as mudanças só serão gravadas na nova cópia.\n\n"
                "Deseja marcar todas as aplicáveis?"
            ),
            parent=self,
        )
        if not confirmar:
            return

        total_marcadas = self.preparacao_assistida.marcar_todas_aplicaveis()
        self._exibir_correcoes_assistidas()
        self.lbl_status.config(
            text=f"{total_marcadas:,} correção(ões) aplicável(is) marcadas em lote."
        )

    def desmarcar_correcoes_assistidas(self):
        if self.preparacao_assistida is None:
            return
        for proposta in self.preparacao_assistida.propostas:
            proposta.selecionada = False
        self._exibir_correcoes_assistidas()

    def _obter_proposta_assistida_selecionada(self):
        if self.preparacao_assistida is None:
            return None
        selecionados = self.tabela_assistida.selection()
        if not selecionados:
            messagebox.showwarning("FiscalPro", "Selecione uma linha da correção assistida.", parent=self)
            return None
        identificador = int(selecionados[0].split("_")[-1])
        return self.preparacao_assistida.obter(identificador)

    def alternar_correcao_assistida(self):
        proposta = self._obter_proposta_assistida_selecionada()
        if proposta is None:
            return
        try:
            self.motor.atualizar_correcao_assistida(
                proposta.identificador, selecionada=not proposta.selecionada
            )
            self._exibir_correcoes_assistidas(proposta.identificador)
        except Exception as erro:
            messagebox.showwarning(
                "FiscalPro",
                f"{erro}\n\nUse “Editar valor selecionado” quando for necessário preencher o campo.",
                parent=self,
            )

    def editar_valor_assistido(self):
        proposta = self._obter_proposta_assistida_selecionada()
        if proposta is None:
            return
        if not proposta.editavel:
            messagebox.showinfo(
                "FiscalPro",
                "Este apontamento exige revisão estrutural e não permite editar apenas um campo.",
                parent=self,
            )
            return
        novo = simpledialog.askstring(
            "FiscalPro — Editar valor",
            (
                f"Registro: {proposta.registro} | Linha: {proposta.numero_linha}\n"
                f"Campo: {proposta.campo}\n"
                f"Valor atual: {proposta.valor_atual or '(vazio)'}\n\n"
                "Informe o valor que deverá ser gravado na nova cópia:"
            ),
            initialvalue=proposta.valor_sugerido or proposta.valor_atual,
            parent=self,
        )
        if novo is None:
            return
        try:
            self.motor.atualizar_correcao_assistida(
                proposta.identificador, valor_novo=novo
            )
            self._exibir_correcoes_assistidas(proposta.identificador)
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def aplicar_correcoes_assistidas(self):
        if self.resultado is None or self.preparacao_assistida is None:
            messagebox.showwarning("FiscalPro", "Prepare primeiro as correções assistidas.", parent=self)
            return
        selecionadas = self.preparacao_assistida.selecionadas
        if not selecionadas:
            messagebox.showinfo("FiscalPro", "Nenhuma correção está marcada para aplicar.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar nova cópia com correções assistidas",
            defaultextension=".txt",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=f"{self.resultado.caminho.stem}_ASSISTIDO_CORRIGIDO.txt",
            filetypes=[("Arquivo SPED", "*.txt")],
            parent=self,
        )
        if not caminho:
            return
        confirmar = messagebox.askyesno(
            "FiscalPro",
            (
                f"Serão aplicadas {len(selecionadas)} correção(ões) marcada(s) em uma NOVA CÓPIA.\n\n"
                "O arquivo original não será alterado. Depois da gravação, o FiscalPro executará "
                "uma nova pré-validação e gerará um relatório comparativo.\n\n"
                "Deseja continuar?"
            ),
            parent=self,
        )
        if not confirmar:
            return
        try:
            self.btn_aplicar_assistida.configure(state="disabled")
            geracao = self.motor.aplicar_correcoes_assistidas(
                caminho, self._atualizar_progresso
            )
            messagebox.showinfo(
                "FiscalPro",
                (
                    "Nova cópia gerada e revalidada com sucesso!\n\n"
                    f"Ações aplicadas: {geracao.total_aplicadas}\n"
                    f"Erros: {geracao.erros_antes} → {geracao.erros_depois}\n"
                    f"Avisos: {geracao.avisos_antes} → {geracao.avisos_depois}\n\n"
                    f"SPED corrigido:\n{geracao.caminho_sped}\n\n"
                    f"Relatório:\n{geracao.caminho_relatorio}\n\n"
                    "Faça ainda a validação oficial no PVA."
                ),
                parent=self,
            )
            self.lbl_status.config(text="Correções assistidas aplicadas e cópia revalidada.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao aplicar correções assistidas.")
        finally:
            if self.preparacao_assistida and self.preparacao_assistida.selecionadas:
                self.btn_aplicar_assistida.configure(state="normal")

    def gerar_sped_final_unificado(self):
        if self.resultado is None or self.preparacao_assistida is None:
            messagebox.showwarning(
                "FiscalPro", "Prepare primeiro as correções assistidas.", parent=self
            )
            return
        selecionadas = self.preparacao_assistida.selecionadas
        if not selecionadas:
            messagebox.showinfo(
                "FiscalPro", "Nenhuma correção está marcada para aplicar.", parent=self
            )
            return

        opcao = self.codigo_estorno_var.get().strip()
        codigo = self.OPCOES_CODIGO_ESTORNO.get(opcao, "")
        if not codigo:
            messagebox.showwarning(
                "FiscalPro",
                "Selecione o código do ajuste C197 na aba Estorno ICMS.",
                parent=self,
            )
            return

        caminho = filedialog.asksaveasfilename(
            title="Salvar SPED final corrigido e estornado",
            defaultextension=".txt",
            initialdir=str(self.resultado.caminho.parent),
            initialfile=f"{self.resultado.caminho.stem}_FINAL_CORRIGIDO_ESTORNADO.txt",
            filetypes=[("Arquivo SPED", "*.txt")],
            parent=self,
        )
        if not caminho:
            return

        confirmar = messagebox.askyesno(
            "FiscalPro — Arquivo final unificado",
            (
                f"Correções assistidas marcadas: {len(selecionadas)}\n"
                f"Código do estorno C197: {codigo}\n\n"
                "O FiscalPro aplicará as correções primeiro, recalculará o estorno sobre "
                "o arquivo já corrigido e gerará somente um TXT final. Os arquivos "
                "intermediários serão descartados automaticamente.\n\n"
                "Deseja continuar?"
            ),
            parent=self,
        )
        if not confirmar:
            return

        try:
            self.btn_final_unificado.configure(state="disabled")
            self.btn_aplicar_assistida.configure(state="disabled")
            geracao = self.motor.gerar_sped_final_unificado(
                caminho,
                codigo,
                "ESTORNO DE CREDITO DE ICMS",
                self._atualizar_progresso,
            )
            messagebox.showinfo(
                "FiscalPro",
                (
                    "Arquivo final unificado gerado com sucesso!\n\n"
                    f"Correções aplicadas: {geracao.correcoes_aplicadas}\n"
                    f"Notas estornadas: {geracao.notas_estornadas}\n"
                    f"Itens estornados: {geracao.itens_estornados}\n"
                    f"Total estornado: {self._fmt_moeda(geracao.total_estornado)}\n"
                    f"Erros na pré-validação final: {geracao.erros_depois}\n"
                    f"Avisos na pré-validação final: {geracao.avisos_depois}\n\n"
                    f"SPED final:\n{geracao.caminho_sped}\n\n"
                    f"Relatório final:\n{geracao.caminho_relatorio}\n\n"
                    "Faça a validação oficial no PVA antes da transmissão."
                ),
                parent=self,
            )
            self.lbl_status.config(text="SPED final corrigido e estornado gerado com sucesso.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao gerar o arquivo final unificado.")
        finally:
            if self.preparacao_assistida and self.preparacao_assistida.selecionadas:
                self.btn_aplicar_assistida.configure(state="normal")
                self.btn_final_unificado.configure(state="normal")


    def _sincronizar_fluxo_excel_txt(self):
        """Mantém os atalhos internos do Excel → TXT coerentes com a validação atual."""
        tem_excel = self.caminho_excel is not None
        validacao_ok = bool(self.validacao_excel is not None and self.validacao_excel.valido)
        if hasattr(self, "btn_validar_excel_aba"):
            self.btn_validar_excel_aba.configure(state="normal" if tem_excel else "disabled")
        if hasattr(self, "btn_gerar_txt_aba"):
            self.btn_gerar_txt_aba.configure(state="normal" if validacao_ok else "disabled")
        if hasattr(self, "btn_conferir_excel_aba"):
            self.btn_conferir_excel_aba.configure(
                state="normal" if self.validacao_excel is not None else "disabled"
            )
        if hasattr(self, "lbl_destino_txt"):
            if validacao_ok:
                self.lbl_destino_txt.config(
                    text=f"Pronto para gerar: {os.path.basename(self._destino_txt_padrao())}"
                )
            elif tem_excel:
                self.lbl_destino_txt.config(text="Planilha selecionada. Valide antes de gerar o TXT.")
            else:
                self.lbl_destino_txt.config(
                    text="Depois da validação, o TXT será salvo ao lado do Excel, sem substituir o SPED original."
                )

    def _sincronizar_fluxo_conferencia_excel(self):
        """Mantém os atalhos da Conferência Excel coerentes com o fluxo superior."""
        self._sincronizar_fluxo_excel_txt()
        if hasattr(self, "btn_validar_excel_conf"):
            self.btn_validar_excel_conf.configure(
                state="normal" if self.caminho_excel is not None else "disabled"
            )
        if hasattr(self, "btn_conferir_excel_conf"):
            self.btn_conferir_excel_conf.configure(
                state="normal" if self.validacao_excel is not None else "disabled"
            )
        if hasattr(self, "btn_relatorio_conferencia_excel"):
            self.btn_relatorio_conferencia_excel.configure(
                state="normal" if self.conferencia_excel_executada else "disabled"
            )

    def importar_excel(self):
        arquivo = filedialog.askopenfilename(
            title="Selecione a planilha exportada pelo FiscalPro",
            filetypes=[("Planilha do Excel", "*.xlsx")],
            parent=self,
        )
        if not arquivo:
            return
        try:
            self.caminho_excel = self.motor.selecionar_excel(arquivo)
            self.validacao_excel = None
            self.conferencia_excel_executada = False
            self.lbl_excel.config(text=os.path.basename(self.caminho_excel))
            self.btn_validar_excel.configure(state="normal")
            self.btn_gerar_txt.configure(state="disabled")
            self.btn_conferir_excel.configure(state="disabled")
            self._limpar_excel()
            self._sincronizar_fluxo_conferencia_excel()
            self.abas.select(self.aba_conferencia_excel)
            self.lbl_status.config(text="Planilha selecionada. Clique em Validar planilha.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def validar_excel(self):
        if self.caminho_excel is None:
            messagebox.showwarning(
                "FiscalPro", "Selecione uma planilha Excel antes de validar.", parent=self
            )
            return
        try:
            self.btn_validar_excel.configure(state="disabled")
            if hasattr(self, "btn_validar_excel_conf"):
                self.btn_validar_excel_conf.configure(state="disabled")
            self.btn_gerar_txt.configure(state="disabled")
            self.validacao_excel = self.motor.validar_excel(
                self.caminho_excel, self._atualizar_progresso
            )
            self._exibir_validacao_excel()
            self.btn_conferir_excel.configure(state="normal")

            # Hotfix 17.8.122 — a validação já alimenta a grade Original × Novo.
            # Antes, a planilha era validada mas a tabela permanecia vazia até o
            # usuário clicar em "Conferir alterações", apesar de a validação já
            # possuir todas as alterações e ajustes automáticos em memória.
            self.conferencia_excel = self.motor.conferir_alteracoes_excel()
            self.conferencia_excel_executada = True
            registros = sorted(
                {item.registro for item in self.conferencia_excel if item.registro}
            )
            self.cmb_conf_registro.configure(values=["Todos", *registros])
            if self.filtro_conf_registro_var.get() not in {"Todos", *registros}:
                self.filtro_conf_registro_var.set("Todos")
            self._exibir_conferencia_excel()

            self._sincronizar_fluxo_conferencia_excel()
            self.abas.select(self.aba_conferencia_excel)
            self.lbl_status.config(
                text=(
                    f"Planilha validada: {self.validacao_excel.total_alteracoes:,} campo(s) alterado(s); "
                    f"{len(self.conferencia_excel):,} item(ns) na conferência Original × Novo."
                ).replace(",", ".")
            )
            if self.validacao_excel.valido:
                self.btn_gerar_txt.configure(state="normal")
                messagebox.showinfo(
                    "FiscalPro",
                    (
                        "Planilha validada com sucesso!\n\n"
                        f"Linhas: {self.validacao_excel.total_linhas:,}\n"
                        f"Registros: {self.validacao_excel.total_registros:,}\n"
                        f"Campos alterados no Excel: {self.validacao_excel.total_alteracoes:,}\n"
                        f"Itens exibidos na conferência Original × Novo: {len(self.conferencia_excel):,}\n"
                        f"Ajustes automáticos C100: {self.validacao_excel.total_ajustes_automaticos_c100:,} "
                        f"em {self.validacao_excel.total_documentos_c100_retotalizados:,} documento(s)\n"
                        f"Ajustes automáticos C190: {self.validacao_excel.total_ajustes_automaticos_c190:,} "
                        f"em {self.validacao_excel.total_documentos_c190_reconstruidos:,} documento(s)\n"
                        f"Ajustes automáticos Bloco M: {self.validacao_excel.total_ajustes_automaticos_bloco_m:,}\n"
                        f"Créditos M100/M500 consolidados: {self.validacao_excel.total_grupos_credito_bloco_m_consolidados:,} grupo(s)\n"
                        f"Duplicidades consolidadas: "
                        f"{self.validacao_excel.total_duplicidades_consolidadas:,}\n"
                        f"Linhas duplicadas removidas: "
                        f"{self.validacao_excel.total_linhas_removidas:,}\n"
                        f"Fórmulas utilizadas: {self.validacao_excel.total_formulas:,}\n"
                        f"Pré-PVA — erros origem: {self.validacao_excel.pre_pva_erros_origem:,}\n"
                        f"Pré-PVA — erros reconstruído: {self.validacao_excel.pre_pva_erros_reconstruido:,}\n"
                        f"Pré-PVA — novos erros pela planilha: {self.validacao_excel.pre_pva_novos_erros:,}\n"
                        f"Avisos: {len(self.validacao_excel.avisos):,}\n\n"
                        "Agora você pode gerar o SPED TXT."
                    ).replace(",", "."),
                    parent=self,
                )
            else:
                messagebox.showwarning(
                    "FiscalPro",
                    (
                        f"A validação encontrou {len(self.validacao_excel.erros)} erro(s).\n\n"
                        "Consulte a aba Excel → TXT. O arquivo não será gerado até "
                        "que os erros sejam corrigidos."
                    ),
                    parent=self,
                )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao validar a planilha.")
        finally:
            self.btn_validar_excel.configure(state="normal")
            self._sincronizar_fluxo_conferencia_excel()

    def conferir_alteracoes_excel(self):
        if self.validacao_excel is None:
            messagebox.showwarning(
                "FiscalPro", "Valide a planilha antes de conferir as alterações.", parent=self
            )
            return
        try:
            self.conferencia_excel = self.motor.conferir_alteracoes_excel()
            self.conferencia_excel_executada = True
            registros = sorted(
                {item.registro for item in self.conferencia_excel if item.registro}
            )
            self.cmb_conf_registro.configure(values=["Todos", *registros])
            if self.filtro_conf_registro_var.get() not in {"Todos", *registros}:
                self.filtro_conf_registro_var.set("Todos")
            self._exibir_conferencia_excel()
            self._sincronizar_fluxo_conferencia_excel()
            self.abas.select(self.aba_conferencia_excel)
            self.lbl_status.config(
                text=(
                    f"Conferência concluída: {len(self.conferencia_excel):,} alteração(ões) "
                    "encontrada(s)."
                ).replace(",", ".")
            )
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao conferir as alterações do Excel.")

    def limpar_filtros_conferencia_excel(self):
        self.filtro_conf_registro_var.set("Todos")
        self.filtro_conf_tipo_var.set("Todos")
        self.filtro_conf_categoria_var.set("Todas")
        self.filtro_conf_busca_var.set("")
        self._exibir_conferencia_excel()

    def _exibir_conferencia_excel(self):
        if not hasattr(self, "tabela_conferencia_excel"):
            return
        for item in self.tabela_conferencia_excel.get_children():
            self.tabela_conferencia_excel.delete(item)

        if not self.conferencia_excel:
            self.conferencia_excel_filtrada = []
            self.lbl_resumo_conferencia_excel.config(
                text=(
                    "Nenhuma alteração foi encontrada entre o SPED original e a planilha validada. "
                    "O TXT reconstruído reproduzirá os mesmos campos, respeitando as validações da 17.4.1."
                )
            )
            return

        self.conferencia_excel_filtrada = self.motor.filtrar_conferencia_excel(
            self.conferencia_excel,
            registro=self.filtro_conf_registro_var.get(),
            tipo=self.filtro_conf_tipo_var.get(),
            categoria=self.filtro_conf_categoria_var.get(),
            busca=self.filtro_conf_busca_var.get(),
        )
        for item in self.conferencia_excel_filtrada:
            self.tabela_conferencia_excel.insert(
                "",
                END,
                values=(
                    item.tipo,
                    item.categoria,
                    item.registro or "-",
                    item.sequencia or "-",
                    item.aba or "-",
                    item.linha_excel or "-",
                    item.campo or "-",
                    item.original,
                    item.novo,
                ),
            )

        total = len(self.conferencia_excel)
        exibidas = len(self.conferencia_excel_filtrada)
        categorias = {}
        for item in self.conferencia_excel_filtrada:
            categorias[item.categoria] = categorias.get(item.categoria, 0) + 1
        resumo_categorias = ", ".join(
            f"{categoria}: {quantidade}"
            for categoria, quantidade in sorted(categorias.items())
        ) or "nenhuma"
        self.lbl_resumo_conferencia_excel.config(
            text=(
                f"Conferência Original × Novo — {exibidas:,} de {total:,} alteração(ões) exibida(s). "
                f"Categorias na visão atual: {resumo_categorias}. "
                f"Pré-PVA: {self.validacao_excel.pre_pva_novos_erros:,} novo(s) erro(s) e "
                f"{self.validacao_excel.pre_pva_novos_avisos:,} novo(s) aviso(s)."
            ).replace(",", ".")
        )

    def salvar_relatorio_conferencia_excel(self):
        if self.validacao_excel is None:
            messagebox.showwarning(
                "FiscalPro", "Valide a planilha antes de gerar o relatório.", parent=self
            )
            return
        nome_base = os.path.splitext(os.path.basename(self.caminho_excel or "conferencia"))[0]
        caminho = filedialog.asksaveasfilename(
            title="Salvar relatório da conferência Excel → SPED",
            defaultextension=".txt",
            initialdir=os.path.dirname(self.caminho_excel) if self.caminho_excel else None,
            initialfile=f"{nome_base}_CONFERENCIA_ALTERACOES.txt",
            filetypes=[("Relatório de texto", "*.txt")],
            parent=self,
        )
        if not caminho:
            return
        try:
            itens = (
                self.conferencia_excel_filtrada
                if self.conferencia_excel
                else []
            )
            destino = self.motor.salvar_relatorio_conferencia_excel(caminho, itens=itens)
            messagebox.showinfo(
                "FiscalPro",
                f"Relatório da conferência salvo com sucesso!\n\n{destino}",
                parent=self,
            )
            self.lbl_status.config(text="Relatório da conferência Excel → SPED salvo.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)

    def _destino_txt_padrao(self) -> str:
        """Retorna um destino novo ao lado do Excel, sem sobrescrever arquivo existente."""
        if self.caminho_excel is None:
            raise RuntimeError("Selecione uma planilha Excel antes de gerar o TXT.")
        pasta = os.path.dirname(self.caminho_excel)
        nome_base = os.path.splitext(os.path.basename(self.caminho_excel))[0]
        if nome_base.upper().endswith("_ORGANIZADO"):
            nome_base = nome_base[:-11]
        base = os.path.join(pasta, f"{nome_base}_CONVERTIDO.txt")
        if not os.path.exists(base):
            return base
        indice = 2
        while True:
            candidato = os.path.join(pasta, f"{nome_base}_CONVERTIDO_{indice}.txt")
            if not os.path.exists(candidato):
                return candidato
            indice += 1

    def gerar_sped_txt_direto(self):
        """Gera o TXT diretamente ao lado da planilha já validada.

        Esta rota evita a caixa de diálogo de salvamento que, em algumas
        instalações do Windows, pode não ganhar foco e dar a impressão de que
        o botão não respondeu.
        """
        if self.caminho_excel is None or self.validacao_excel is None:
            messagebox.showwarning(
                "FiscalPro", "Selecione e valide a planilha antes de gerar o TXT.", parent=self
            )
            return
        if not self.validacao_excel.valido:
            messagebox.showwarning(
                "FiscalPro", "A planilha possui erros. Corrija e valide novamente.", parent=self
            )
            return

        caminho = self._destino_txt_padrao()
        confirmar = messagebox.askyesno(
            "FiscalPro",
            (
                "Gerar o SPED TXT agora?\n\n"
                f"Linhas validadas: {self.validacao_excel.total_linhas:,}\n"
                f"Campos alterados: {self.validacao_excel.total_alteracoes:,}\n"
                f"Avisos não bloqueantes: {len(self.validacao_excel.avisos):,}\n\n"
                f"O arquivo será salvo em:\n{caminho}\n\n"
                "O SPED original não será substituído."
            ).replace(",", "."),
            parent=self,
        )
        if not confirmar:
            return

        try:
            self.btn_gerar_txt.configure(state="disabled")
            if hasattr(self, "btn_gerar_txt_aba"):
                self.btn_gerar_txt_aba.configure(state="disabled")
            self.lbl_status.config(text="Gerando SPED TXT a partir da planilha validada...")
            self.update_idletasks()
            geracao = self.motor.gerar_sped_de_excel(
                caminho, self.caminho_excel, self._atualizar_progresso
            )
            if hasattr(self, "lbl_destino_txt"):
                self.lbl_destino_txt.config(text=f"TXT gerado: {geracao.caminho_sped}")
            messagebox.showinfo(
                "FiscalPro",
                (
                    "SPED TXT gerado com sucesso!\n\n"
                    f"Linhas: {geracao.total_linhas:,}\n"
                    f"Registros: {geracao.total_registros:,}\n"
                    f"Campos alterados: {geracao.total_alteracoes:,}\n"
                    f"Avisos: {geracao.total_avisos:,}\n"
                    f"Novos erros no Pré-PVA: {geracao.pre_pva_novos_erros:,}\n\n"
                    f"TXT:\n{geracao.caminho_sped}\n\n"
                    f"Relatório:\n{geracao.caminho_relatorio}"
                ).replace(",", "."),
                parent=self,
            )
            self.lbl_status.config(text=f"SPED TXT gerado: {geracao.caminho_sped}")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao gerar o SPED TXT.")
        finally:
            if self.validacao_excel and self.validacao_excel.valido:
                self.btn_gerar_txt.configure(state="normal")
            self._sincronizar_fluxo_excel_txt()

    def gerar_sped_txt(self):
        if self.caminho_excel is None or self.validacao_excel is None:
            messagebox.showwarning(
                "FiscalPro", "Selecione e valide a planilha antes de gerar o TXT.", parent=self
            )
            return
        if not self.validacao_excel.valido:
            messagebox.showwarning(
                "FiscalPro", "A planilha possui erros. Corrija e valide novamente.", parent=self
            )
            return

        nome_base = os.path.splitext(os.path.basename(self.caminho_excel))[0]
        if nome_base.upper().endswith("_ORGANIZADO"):
            nome_base = nome_base[:-11]
        caminho = filedialog.asksaveasfilename(
            title="Salvar SPED convertido do Excel",
            defaultextension=".txt",
            initialdir=os.path.dirname(self.caminho_excel),
            initialfile=f"{nome_base}_CONVERTIDO.txt",
            filetypes=[("Arquivo SPED", "*.txt")],
            parent=self,
        )
        if not caminho:
            return

        confirmar = messagebox.askyesno(
            "FiscalPro",
            (
                f"O FiscalPro reconstruirá {self.validacao_excel.total_linhas:,} linhas, "
                f"aplicará {self.validacao_excel.total_alteracoes:,} alteração(ões) de campo "
                f"e consolidará {self.validacao_excel.total_duplicidades_consolidadas:,} "
                f"grupo(s) duplicado(s).\n\n"
                "O arquivo Excel não será alterado. Depois, valide o novo TXT no PVA.\n\n"
                "Deseja continuar?"
            ).replace(",", "."),
            parent=self,
        )
        if not confirmar:
            return

        try:
            self.btn_gerar_txt.configure(state="disabled")
            geracao = self.motor.gerar_sped_de_excel(
                caminho, self.caminho_excel, self._atualizar_progresso
            )
            messagebox.showinfo(
                "FiscalPro",
                (
                    "SPED TXT gerado com sucesso!\n\n"
                    f"Linhas: {geracao.total_linhas:,}\n"
                    f"Registros: {geracao.total_registros:,}\n"
                    f"Campos alterados: {geracao.total_alteracoes:,}\n"
                    f"Duplicidades consolidadas: "
                    f"{geracao.total_duplicidades_consolidadas:,}\n"
                    f"Linhas duplicadas removidas: {geracao.total_linhas_removidas:,}\n"
                    f"Pré-PVA — erros no reconstruído: {geracao.pre_pva_erros_reconstruido:,}\n"
                    f"Pré-PVA — novos erros pela planilha: {geracao.pre_pva_novos_erros:,}\n\n"
                    f"TXT:\n{geracao.caminho_sped}\n\n"
                    f"Relatório:\n{geracao.caminho_relatorio}"
                ).replace(",", "."),
                parent=self,
            )
            self.lbl_status.config(text="SPED TXT e relatório gerados com sucesso.")
        except Exception as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self)
            self.lbl_status.config(text="Falha ao gerar o SPED TXT.")
        finally:
            if self.validacao_excel and self.validacao_excel.valido:
                self.btn_gerar_txt.configure(state="normal")

    def _atualizar_progresso(self, percentual, mensagem):
        """Atualiza o andamento sem interromper a leitura do SPED.

        Além da criação antecipada do rodapé, este tratamento defensivo evita
        que uma atualização parcial, um widget já destruído ou um cache antigo
        impeça a abertura do arquivo fiscal.
        """
        barra = getattr(self, "progresso", None)
        status = getattr(self, "lbl_status", None)

        try:
            if barra is not None and barra.winfo_exists():
                barra["value"] = percentual
        except Exception:
            # A barra é apenas informativa; falhas visuais não podem cancelar
            # a leitura, auditoria ou geração do SPED.
            pass

        try:
            if status is not None and status.winfo_exists():
                status.config(text=f"{datetime.now():%H:%M:%S}  {mensagem}")
        except Exception:
            pass

        try:
            self.update_idletasks()
        except Exception:
            pass

    def _exibir_resultado(self):
        estat = self.resultado.estatisticas
        self.lbl_arquivo.config(text=os.path.basename(self.resultado.caminho))
        self.lbl_empresa.config(text=estat.empresa)
        self.lbl_cnpj.config(text=estat.cnpj)
        self.lbl_periodo.config(text=estat.periodo)
        self.lbl_layout.config(text=f"{estat.tipo_sped} — {estat.layout}")

        for item in self.tabela.get_children():
            self.tabela.delete(item)
        codigos = list(self.REGISTROS_DESTAQUE)
        codigos += [c for c in sorted(estat.contagens) if c not in codigos]
        for codigo in codigos:
            quantidade = estat.contagens.get(codigo, 0)
            if quantidade or codigo in self.REGISTROS_DESTAQUE:
                self.tabela.insert("", END, values=(codigo, f"{quantidade:,}".replace(",", ".")))

        resumo = (
            f"Linhas: {estat.total_linhas:,}\n"
            f"Registros válidos: {estat.total_registros_validos:,}\n"
            f"Produtos (0200): {estat.produtos:,}\n"
            f"Participantes (0150): {estat.participantes:,}\n"
            f"Documentos (C100): {estat.documentos:,}\n"
            f"Itens (C170): {estat.itens:,}\n"
            f"CT-e (D100): {estat.ctes:,}\n"
            f"Codificação: {self.resultado.encoding}\n"
            f"Tempo: {self.resultado.tempo_processamento:.3f}s"
        ).replace(",", ".")
        self.lbl_resumo.config(text=resumo)

        self.txt_alertas.configure(state="normal")
        self.txt_alertas.delete("1.0", END)
        if self.resultado.alertas:
            for alerta in self.resultado.alertas:
                self.txt_alertas.insert(END, f"[{alerta.nivel}] {alerta.mensagem}\n\n")
        else:
            self.txt_alertas.insert(END, "Nenhuma inconsistência estrutural básica encontrada.")
        self.txt_alertas.configure(state="disabled")

    def _limpar_chaves_cte(self):
        if hasattr(self, "tabela_cte"):
            for item in self.tabela_cte.get_children():
                self.tabela_cte.delete(item)
        if hasattr(self, "lbl_resumo_cte"):
            self.lbl_resumo_cte.config(
                text=(
                    "Importe os XMLs de CT-e e clique em “Conferir chaves”. Somente uma "
                    "correspondência única por número e série poderá ser aplicada automaticamente."
                )
            )

    def _exibir_chaves_cte(self):
        for item in self.tabela_cte.get_children():
            self.tabela_cte.delete(item)
        if self.analise_chaves_cte is None:
            return
        ordem = {"CORRIGIR": 0, "NÃO ENCONTRADO": 1, "AMBÍGUO": 2, "CORRETA": 3}
        apontamentos = sorted(
            self.analise_chaves_cte.apontamentos,
            key=lambda item: (ordem.get(item.status, 9), item.numero_linha),
        )
        for item in apontamentos:
            self.tabela_cte.insert(
                "",
                END,
                values=(
                    item.status, item.numero_linha, item.numero_cte, item.serie or "-",
                    item.chave_sped or "(vazio)", item.chave_xml or "-",
                    item.arquivo_xml or item.detalhe,
                ),
                tags=(item.status,),
            )
        a = self.analise_chaves_cte
        self.lbl_resumo_cte.config(
            text=(
                f"{a.total_d100_cte:,} CT-e(s) analisado(s): {a.corretas:,} correto(s), "
                f"{a.divergentes:,} divergente(s), {a.nao_encontradas:,} sem XML e "
                f"{a.ambiguas:,} ambíguo(s). Somente os divergentes com correspondência única serão alterados."
            ).replace(",", ".")
        )
        self.lbl_cte.config(
            text=f"{a.divergentes:,} chave(s) para corrigir • {a.nao_encontradas:,} sem XML".replace(",", ".")
        )

    def _limpar_correcoes(self):
        for item in self.tabela_correcoes.get_children():
            self.tabela_correcoes.delete(item)
        self.lbl_resumo_correcoes.config(
            text=(
                "Clique em “Analisar correções”. O FiscalPro fará cruzamentos entre 0200 e C170, "
                "separando correções automáticas seguras de situações que precisam de revisão manual."
            )
        )

    def _limpar_auditoria_tributaria(self):
        if hasattr(self, "tabela_tributaria"):
            for item in self.tabela_tributaria.get_children():
                self.tabela_tributaria.delete(item)
        self.mapa_auditoria_itens = {}
        if hasattr(self, "lbl_resumo_tributario"):
            self.lbl_resumo_tributario.config(
                text=(
                    "Clique em “Cruzar Ficha Tributária”. O FiscalPro comparará 0200, C170, "
                    "regras vigentes, base legal e, quando importados, os XMLs de NF-e."
                )
            )

    def _exibir_auditoria_tributaria(self):
        for item in self.tabela_tributaria.get_children():
            self.tabela_tributaria.delete(item)
        self.mapa_auditoria_itens = {}
        if self.auditoria_tributaria is None:
            return

        filtro = self.aud_filtro_var.get()
        apontamentos = list(self.auditoria_tributaria.apontamentos)
        if filtro == "Erros":
            apontamentos = [item for item in apontamentos if item.nivel == "ERRO"]
        elif filtro == "Avisos":
            apontamentos = [item for item in apontamentos if item.nivel == "AVISO"]
        elif filtro == "Sem regra":
            apontamentos = [item for item in apontamentos if item.campo == "Regra tributária"]
        elif filtro in {"Ficha Tributária", "XML NF-e", "Cadastro 0200", "Base Legal"}:
            origem = filtro.upper() if filtro != "Ficha Tributária" else "FICHA TRIBUTÁRIA"
            if filtro == "Cadastro 0200":
                origem = "CADASTRO 0200"
            elif filtro == "Base Legal":
                origem = "BASE LEGAL"
            apontamentos = [item for item in apontamentos if item.origem == origem]

        ordem = {"ERRO": 0, "AVISO": 1}
        apontamentos.sort(key=lambda item: (ordem.get(item.nivel, 9), item.linha, item.campo))
        for apontamento in apontamentos:
            detalhe = apontamento.mensagem
            if apontamento.orientacao:
                detalhe = f"{detalhe} — {apontamento.orientacao}"
            iid = self.tabela_tributaria.insert(
                "",
                END,
                values=(
                    apontamento.nivel,
                    apontamento.origem,
                    apontamento.linha or "-",
                    apontamento.documento or "-",
                    apontamento.item or "-",
                    apontamento.codigo or "-",
                    apontamento.ncm or "-",
                    apontamento.campo or "-",
                    apontamento.atual or "-",
                    apontamento.esperado or "-",
                    apontamento.regra_id or "-",
                    f"{apontamento.aderencia:.0f}%" if apontamento.aderencia else "-",
                    detalhe,
                ),
                tags=(apontamento.nivel,),
            )
            self.mapa_auditoria_itens[iid] = apontamento

        a = self.auditoria_tributaria
        xml_texto = (
            f"XML: {a.itens_com_xml:,} item(ns) localizado(s), {a.itens_sem_xml:,} sem correspondência."
            if self.importacao_nfe_xml is not None
            else "XML de NF-e não importado nesta análise."
        )
        self.lbl_resumo_tributario.config(
            text=(
                f"{a.total_itens:,} item(ns) auditado(s) • {a.itens_com_regra:,} com regra • "
                f"{a.itens_sem_regra:,} sem regra • {a.erros:,} erro(s) • {a.avisos:,} aviso(s) • "
                f"conformidade {a.conformidade:.2f}%. {xml_texto} "
                f"Filtro atual: {filtro} ({len(apontamentos):,} linha(s))."
            ).replace(",", ".")
        )
        if not apontamentos:
            self.tabela_tributaria.insert(
                "", END,
                values=("OK", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "Nenhum apontamento para o filtro selecionado."),
            )

    def _limpar_difal(self):
        if hasattr(self, "tabela_difal"):
            for item in self.tabela_difal.get_children():
                self.tabela_difal.delete(item)
        if hasattr(self, "lbl_resumo_difal"):
            self.lbl_resumo_difal.config(
                text=(
                    "Abra um SPED Fiscal e execute a auditoria. Com XMLs de saída importados, "
                    "o FiscalPro confirma consumidor final, condição do IE e valores ICMSUFDest."
                )
            )

    @staticmethod
    def _moeda_difal(valor):
        try:
            numero = float(valor or 0)
        except (TypeError, ValueError):
            numero = 0.0
        texto = f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"

    def _exibir_difal(self):
        for item in self.tabela_difal.get_children():
            self.tabela_difal.delete(item)
        if self.auditoria_difal is None:
            return
        ordem = {"ERRO": 0, "REVISAR": 1, "AVISO": 2, "OK": 3}
        apontamentos = sorted(
            self.auditoria_difal.apontamentos,
            key=lambda a: (ordem.get(a.nivel, 9), a.linha, a.numero),
        )
        for a in apontamentos:
            detalhe = a.mensagem + (f" — {a.orientacao}" if a.orientacao else "")
            self.tabela_difal.insert(
                "", END,
                values=(
                    a.nivel, a.linha or "-", a.numero or "-", a.uf_destino or "-", a.cfops or "-",
                    a.evidencia or "-", a.origem_calculo or "-", "SIM" if a.c101_presente else "NÃO",
                    self._moeda_difal(a.base_calculo or a.base_xml),
                    f"{a.aliquota_interna}%" if a.aliquota_interna else "-",
                    a.aliquota_interestadual_xml_texto or "-",
                    a.aliquota_interestadual_sped_texto or "-",
                    self._moeda_difal(a.difal_sped), self._moeda_difal(a.difal_xml),
                    self._moeda_difal(a.difal_devido), self._moeda_difal(a.difal_sped_origem),
                    a.memoria_calculo_sped or a.detalhe_origem_sped or "-",
                    self._moeda_difal(a.diferenca_difal),
                    self._moeda_difal(a.fcp_sped), self._moeda_difal(a.fcp_xml),
                    (self._moeda_difal(a.fcp_devido) if a.fcp_calculado else "REVISAR"), detalhe,
                ),
                tags=(a.nivel,),
            )
        r = self.auditoria_difal
        xml_texto = (
            f"{r.total_xml_localizados:,} XML(s) localizado(s) por chave"
            if r.usou_xml else
            f"sem XML: {r.total_calculados_sem_xml:,} cálculo(s) reconstruído(s) pelo SPED"
        )
        self.lbl_resumo_difal.config(
            text=(
                f"{r.total_interestaduais:,} NF-e interestadual(is) • "
                f"{r.total_final_nao_contribuinte_confirmado:,} consumidor final não contribuinte confirmado(s) • "
                f"{r.total_com_c101:,} com C101 • {r.total_sem_c101_quando_confirmado:,} confirmado(s) sem C101 • "
                f"{r.erros:,} erro(s) • {r.avisos:,} aviso(s)/revisão(ões) • {xml_texto}. "
                f"DIFAL C101 {self._moeda_difal(r.valor_difal_sped)} | XML {self._moeda_difal(r.valor_difal_xml)} | "
                f"DEVIDO {self._moeda_difal(r.valor_difal_devido)} • "
                f"Origem SPED×XML: {r.total_divergencias_origem:,} divergência(s) • "
                f"Origem mista: {r.total_origem_mista_sped:,} NF-e."
            ).replace(",", ".")
        )
        if not apontamentos:
            self.tabela_difal.insert(
                "", END,
                values=("OK",) + ("-",) * (len(self.tabela_difal["columns"]) - 2) + ("Nenhuma pendência identificada nas regras executadas.",),
                tags=("OK",),
            )

    def _limpar_correcao_tributaria(self):
        if hasattr(self, "tabela_correcao_tributaria"):
            for item in self.tabela_correcao_tributaria.get_children():
                self.tabela_correcao_tributaria.delete(item)
        self.mapa_correcao_tributaria = {}
        if hasattr(self, "lbl_resumo_correcao_tributaria"):
            self.lbl_resumo_correcao_tributaria.config(
                text=(
                    "Execute a Auditoria Tributária e clique em “Preparar correções”. "
                    "Nenhuma alteração fiscal será marcada sem sua confirmação."
                )
            )

    def _exibir_correcao_tributaria(self, selecionar_identificador=None):
        for item in self.tabela_correcao_tributaria.get_children():
            self.tabela_correcao_tributaria.delete(item)
        self.mapa_correcao_tributaria = {}
        if self.preparacao_correcao_tributaria is None:
            return

        iid_selecionar = None
        propostas = list(self.preparacao_correcao_tributaria.propostas)
        for proposta in propostas:
            if proposta.selecionada:
                tag = "MARCADA"
            elif proposta.modo == "Conflito — escolher valor":
                tag = "CONFLITO"
            elif not proposta.aplicavel:
                tag = "REVISAO"
            else:
                tag = ""
            sugerido = proposta.valor_sugerido
            if not sugerido and proposta.alternativas:
                sugerido = " / ".join(proposta.alternativas)
            iid = self.tabela_correcao_tributaria.insert(
                "",
                END,
                values=(
                    "SIM" if proposta.selecionada else "NÃO",
                    proposta.modo,
                    proposta.origem,
                    proposta.registro,
                    proposta.numero_linha or "-",
                    proposta.documento or "-",
                    proposta.item or "-",
                    proposta.codigo or "-",
                    proposta.ncm or "-",
                    proposta.campo,
                    proposta.valor_atual or "(vazio)",
                    sugerido or "-",
                    proposta.regra_id or "-",
                    f"{proposta.aderencia:.0f}%" if proposta.aderencia else "-",
                    proposta.justificativa,
                ),
                tags=(tag,) if tag else (),
            )
            self.mapa_correcao_tributaria[iid] = proposta
            if proposta.identificador == selecionar_identificador:
                iid_selecionar = iid

        if iid_selecionar:
            self.tabela_correcao_tributaria.selection_set(iid_selecionar)
            self.tabela_correcao_tributaria.focus(iid_selecionar)
            self.tabela_correcao_tributaria.see(iid_selecionar)

        preparacao = self.preparacao_correcao_tributaria
        aplicaveis = len([p for p in propostas if p.aplicavel])
        self.lbl_resumo_correcao_tributaria.config(
            text=(
                f"{preparacao.total:,} proposta(s) • {len(preparacao.alta_confianca):,} de alta confiança • "
                f"{len(preparacao.conflitos):,} conflito(s) • {aplicaveis:,} aplicável(is) • "
                f"{len(preparacao.selecionadas):,} marcada(s). O arquivo original não será alterado."
            ).replace(",", ".")
        )

    def _limpar_pre_pva(self):
        for item in self.tabela_pva.get_children():
            self.tabela_pva.delete(item)
        self.lbl_resumo_pva.config(
            text=(
                "Clique em “Validar antes do PVA”. O FiscalPro verificará estrutura, totalizadores, "
                "cadastros, referências, notas, itens e cálculos de PIS/COFINS sem alterar o arquivo."
            )
        )

    def _exibir_pre_validacao(self):
        for item in self.tabela_pva.get_children():
            self.tabela_pva.delete(item)

        for apontamento in self.pre_validacao_pva.apontamentos:
            detalhe = apontamento.mensagem
            if apontamento.sugestao:
                detalhe = f"{detalhe} — {apontamento.sugestao}"
            self.tabela_pva.insert(
                "",
                END,
                values=(
                    apontamento.nivel,
                    apontamento.categoria,
                    apontamento.registro or "-",
                    apontamento.numero_linha or "-",
                    apontamento.documento or "-",
                    apontamento.codigo_item or "-",
                    apontamento.campo or "-",
                    detalhe,
                ),
                tags=(apontamento.nivel,),
            )

        erros = len(self.pre_validacao_pva.erros)
        avisos = len(self.pre_validacao_pva.avisos)
        revisoes = len(self.pre_validacao_pva.revisoes)
        erros_pge = self.pre_validacao_pva.erros_pge_estimados or erros
        if erros:
            texto = (
                f"Arquivo com {erros} causa(s) raiz e {avisos} aviso(s) PVA/PGE nas "
                f"{self.pre_validacao_pva.regras_executadas} regras executadas. "
                f"Revisões extras FiscalPro: {revisoes}. "
                f"Equivalência estimada: {erros_pge} ocorrência(s) no PGE. "
                "Corrija as causas raiz e valide novamente."
            )
            self.lbl_pva.config(
                text=(
                    f"{erros} causa(s) • ≈ {erros_pge} PGE • {avisos} aviso(s) "
                    f"• {revisoes} revisão(ões) FiscalPro"
                )
            )
        else:
            texto = (
                f"Nenhum erro PVA/PGE encontrado; {avisos} aviso(s) PVA/PGE em "
                f"{self.pre_validacao_pva.regras_executadas} regras. "
                f"Revisões extras FiscalPro: {revisoes}. "
                "O arquivo ainda deve passar pela validação oficial no PVA/PGE."
            )
            self.lbl_pva.config(
                text=f"Sem erros PVA/PGE • {avisos} aviso(s) • {revisoes} revisão(ões) FiscalPro"
            )
            if not self.pre_validacao_pva.apontamentos:
                self.tabela_pva.insert(
                    "", END, values=("OK", "-", "-", "-", "-", "-", "-", "Nenhum erro ou aviso encontrado.")
                )
        self.lbl_resumo_pva.config(text=texto)

    def _limpar_assistida(self):
        if hasattr(self, "tabela_assistida"):
            for item in self.tabela_assistida.get_children():
                self.tabela_assistida.delete(item)
        if hasattr(self, "lbl_resumo_assistida"):
            self.lbl_resumo_assistida.config(
                text=(
                    "Depois da pré-validação, clique em “Preparar correções”. Formatações seguras "
                    "podem vir marcadas; cálculos, unidades e dados fiscais exigem sua confirmação."
                )
            )
        if hasattr(self, "btn_aplicar_assistida"):
            self.btn_aplicar_assistida.configure(state="disabled")
        if hasattr(self, "btn_final_unificado"):
            self.btn_final_unificado.configure(state="disabled")

    def _exibir_correcoes_assistidas(self, manter_id=None):
        for item in self.tabela_assistida.get_children():
            self.tabela_assistida.delete(item)
        if self.preparacao_assistida is None:
            return
        for proposta in self.preparacao_assistida.propostas:
            marcado = "SIM" if proposta.selecionada else "NÃO"
            tags = ("MARCADA",) if proposta.selecionada else (proposta.nivel,)
            iid = f"assistida_{proposta.identificador}"
            self.tabela_assistida.insert(
                "",
                END,
                iid=iid,
                values=(
                    marcado, proposta.modo, proposta.nivel, proposta.registro,
                    proposta.numero_linha or "-", proposta.documento or "-",
                    proposta.codigo_item or "-", proposta.campo,
                    proposta.valor_atual or "(vazio)",
                    proposta.valor_sugerido or "(informar)", proposta.justificativa,
                ),
                tags=tags,
            )
        selecionadas = len(self.preparacao_assistida.selecionadas)
        seguras = len(self.preparacao_assistida.automaticas_seguras)
        sugestoes = len(self.preparacao_assistida.sugestoes)
        preencher = len(self.preparacao_assistida.preenchimentos)
        revisao = len(self.preparacao_assistida.somente_revisao)
        self.lbl_resumo_assistida.config(
            text=(
                f"{self.preparacao_assistida.total} item(ns): {seguras} automático(s) seguro(s), "
                f"{sugestoes} sugestão(ões), {preencher} preenchimento(s) e {revisao} somente para revisão. "
                f"Marcados para a nova cópia: {selecionadas}."
            )
        )
        self.lbl_assistida.config(text=f"{selecionadas} correção(ões) marcada(s)")
        estado = "normal" if selecionadas else "disabled"
        self.btn_aplicar_assistida.configure(state=estado)
        if hasattr(self, "btn_final_unificado"):
            self.btn_final_unificado.configure(state=estado)
        if manter_id is not None:
            iid = f"assistida_{manter_id}"
            if self.tabela_assistida.exists(iid):
                self.tabela_assistida.selection_set(iid)
                self.tabela_assistida.focus(iid)
                self.tabela_assistida.see(iid)

    def _limpar_excel(self):
        for item in self.tabela_excel.get_children():
            self.tabela_excel.delete(item)
        self.conferencia_excel = []
        self.conferencia_excel_filtrada = []
        self.conferencia_excel_executada = False
        self.filtro_conf_registro_var.set("Todos")
        self.filtro_conf_tipo_var.set("Todos")
        self.filtro_conf_categoria_var.set("Todas")
        self.filtro_conf_busca_var.set("")
        if hasattr(self, "cmb_conf_registro"):
            self.cmb_conf_registro.configure(values=["Todos"])
        if hasattr(self, "tabela_conferencia_excel"):
            for item in self.tabela_conferencia_excel.get_children():
                self.tabela_conferencia_excel.delete(item)
        self._sincronizar_fluxo_conferencia_excel()
        if hasattr(self, "lbl_resumo_conferencia_excel"):
            self.lbl_resumo_conferencia_excel.config(
                text=(
                    "Valide uma planilha e clique em “Conferir alterações”. O FiscalPro mostrará "
                    "Original × Novo sem modificar o Excel ou o SPED automaticamente."
                )
            )
        self.lbl_resumo_excel.config(
            text=(
                "Planilha selecionada. Clique em “Validar planilha”. O FiscalPro verificará "
                "a ordem dos registros, identificadores ocultos, resultados de fórmulas, linhas "
                "incluídas ou excluídas, campos alterados, duplicidades C190/D190 e executará um "
                "Pré-PVA comparativo sobre o TXT reconstruído em memória."
            )
        )

    def _exibir_validacao_excel(self):
        for item in self.tabela_excel.get_children():
            self.tabela_excel.delete(item)

        for problema in self.validacao_excel.problemas:
            self.tabela_excel.insert(
                "",
                END,
                values=(
                    problema.nivel,
                    problema.sequencia or "-",
                    problema.registro or "-",
                    problema.aba or "-",
                    problema.linha_excel or "-",
                    problema.mensagem,
                ),
            )

        if self.validacao_excel.valido:
            texto = (
                f"Planilha válida — {self.validacao_excel.total_linhas:,} linhas, "
                f"{self.validacao_excel.total_registros:,} registros e "
                f"{self.validacao_excel.total_alteracoes:,} campos alterados, "
                f"C190: {self.validacao_excel.total_ajustes_automaticos_c190:,} ajuste(s) automático(s) em "
                f"{self.validacao_excel.total_documentos_c190_reconstruidos:,} documento(s), "
                f"Bloco M: {self.validacao_excel.total_ajustes_automaticos_bloco_m:,} ajuste(s) automático(s) / "
                f"{self.validacao_excel.total_grupos_credito_bloco_m_consolidados:,} crédito(s) consolidado(s), "
                f"{self.validacao_excel.total_duplicidades_consolidadas:,} grupo(s) duplicado(s) "
                f"consolidado(s), {self.validacao_excel.total_linhas_removidas:,} linha(s) removida(s) e "
                f"{self.validacao_excel.total_formulas:,} fórmula(s) utilizada(s). "
                f"Pré-PVA: {self.validacao_excel.pre_pva_erros_origem:,} → "
                f"{self.validacao_excel.pre_pva_erros_reconstruido:,} erro(s), "
                f"{self.validacao_excel.pre_pva_novos_erros:,} novo(s). "
                f"Avisos: {len(self.validacao_excel.avisos):,}."
            ).replace(",", ".")
            if not self.validacao_excel.problemas:
                self.tabela_excel.insert(
                    "", END, values=("OK", "-", "-", "-", "-", "Nenhum erro ou aviso encontrado.")
                )
        else:
            texto = (
                f"Planilha bloqueada — {len(self.validacao_excel.erros)} erro(s) e "
                f"{len(self.validacao_excel.avisos)} aviso(s). Corrija os erros e valide novamente."
            )
        self.lbl_resumo_excel.config(text=texto)

    def _exibir_correcoes(self):
        for item in self.tabela_correcoes.get_children():
            self.tabela_correcoes.delete(item)

        for correcao in self.analise_correcoes.correcoes:
            self.tabela_correcoes.insert(
                "",
                END,
                values=(
                    correcao.modo,
                    correcao.gravidade,
                    correcao.registro,
                    correcao.numero_linha,
                    correcao.codigo_item or "-",
                    correcao.problema,
                    correcao.acao,
                ),
            )

        total = self.analise_correcoes.total
        automaticas = self.analise_correcoes.total_automaticas
        manuais = self.analise_correcoes.total_manuais
        if total:
            texto = (
                f"Análise concluída: {total} apontamentos — {automaticas} correções automáticas seguras "
                f"e {manuais} pendências para revisão manual. Tributos e valores fiscais não foram alterados."
            )
        else:
            texto = "Análise concluída: nenhuma inconsistência de 0200/C170 encontrada pelas regras desta sprint."
        self.lbl_resumo_correcoes.config(text=texto)
