"""Janela principal do FiscalPro.

Sprint 15.8 — Refinamento visual e áreas de relatório ampliadas.
Mantém a identidade visual aprovada e acrescenta proteção dos dados pelo
menu do usuário, sem aumentar a quantidade de botões na tela principal.
"""

from __future__ import annotations

from tkinter import BOTH, END, LEFT, RIGHT, WORD, X, Y, Canvas, Frame, Label, Menu, StringVar, Text, Tk
from tkinter import messagebox, ttk

from src.auth.models import SessaoUsuario
from src.core.app_info import NOME_COMPLETO
from src.auth.service import ServicoAutenticacao
from src.banco.conexao import Banco
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository

from .dashboard import Dashboard
from .estilos import (
    COR_BORDA,
    COR_CARD,
    COR_DESTAQUE,
    COR_FUNDO,
    COR_PRIMARIA,
    COR_SECUNDARIA,
    COR_TEXTO,
    COR_TEXTO_SUAVE,
    FONTE_NORMAL,
    FONTE_RESULTADO,
    VERSAO_INTERFACE,
    configurar_tema,
)
from .janela_consulta_ncm import JanelaConsultaNCM
from .janela_login import JanelaAlterarSenha
from .janela_backup import JanelaBackup
from .janela_sobre import JanelaSobre
from .recursos import aplicar_icone, carregar_imagem
from .janela_ficha_tributaria import JanelaFichaTributaria
from .janela_simulador_tributario import JanelaSimuladorTributario
from .janela_comparar_cenarios_tributarios import JanelaCompararCenariosTributarios
from .janela_cobertura_tributaria import JanelaCoberturaTributaria
from .janela_configurador_olist import JanelaConfiguradorOlist
from .janela_calculo_icms_st import JanelaCalculoICMSSTMG
from .janela_difal_fcp import JanelaDIFALFCP
from .janela_sped_inteligente import JanelaSPEDInteligente
from .janela_xml_icms_st import JanelaXMLICMSST
from .janela_analise_lote import JanelaAnaliseTributariaLote
from .janela_auditoria_cadastros_xml import JanelaAuditoriaCadastrosXML
from .janela_auditoria_cadastros_excel import JanelaAuditoriaCadastrosExcel
from .janela_auditoria_icms_st_piscofins import JanelaAuditoriaICMSSTPISCOFINS
from .janela_auditoria_icms_st_piscofins_saidas import JanelaAuditoriaICMSSTPISCOFINSSaidas
from .janela_robo_tributario import JanelaRoboTributario
from .layout_responsivo import dimensionar_janela, vincular_wraplength
from .painel_info import PainelInfo
from .painel_contas_pagar import PainelContasPagar
from .painel_empresas import PainelEmpresas
from .painel_entregas import PainelEntregas
from .painel_documentos_fiscais import PainelDocumentosFiscais
from .painel_dere import PainelDeRE


class JanelaPrincipal:
    def __init__(
        self,
        sessao: SessaoUsuario | None = None,
        servico_autenticacao: ServicoAutenticacao | None = None,
    ):
        self.sessao = sessao or SessaoUsuario(0, "Usuário", "usuario", "ADMINISTRADOR")
        self.servico_autenticacao = servico_autenticacao or ServicoAutenticacao()
        self.acao_saida = "encerrar"

        self.janela = Tk()
        self.janela.title(NOME_COMPLETO)
        self.janela.resizable(True, True)
        self.janela.protocol("WM_DELETE_WINDOW", self._encerrar)
        configurar_tema(self.janela)
        aplicar_icone(self.janela)
        dimensionar_janela(self.janela, 1360, 880, 980, 620)

        self.var_status_rodape = StringVar(value="Sistema pronto")

        self.criar_interface()

    def criar_interface(self):
        self.criar_cabecalho()
        self.criar_rodape()
        self.criar_abas()

    def criar_cabecalho(self):
        cabecalho = Frame(self.janela, bg=COR_PRIMARIA, height=70)
        cabecalho.pack(fill=X)
        cabecalho.pack_propagate(False)

        marca = Frame(cabecalho, bg=COR_PRIMARIA)
        marca.pack(side=LEFT, fill=Y, padx=16, pady=7)

        self.logo_cabecalho = carregar_imagem(self.janela, "fiscalpro_mark_48.png")
        if self.logo_cabecalho is not None:
            Label(
                marca,
                image=self.logo_cabecalho,
                bg=COR_PRIMARIA,
                bd=0,
            ).pack(side=LEFT, padx=(0, 14))
        else:
            Label(
                marca,
                text="FP",
                bg=COR_DESTAQUE,
                fg="white",
                font=("Segoe UI", 13, "bold"),
                width=3,
                height=2,
                bd=0,
            ).pack(side=LEFT, padx=(0, 14))

        textos = Frame(marca, bg=COR_PRIMARIA)
        textos.pack(side=LEFT, fill=Y)
        ttk.Label(textos, text="FiscalPro", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(
            textos,
            text="Assistente Fiscal Inteligente • simples, seguro e rastreável",
            style="HeaderSubtitle.TLabel",
        ).pack(anchor="w", pady=(1, 0))

        status = Frame(cabecalho, bg=COR_PRIMARIA)
        status.pack(side=RIGHT, padx=16, pady=9)

        conta = ttk.Menubutton(
            status,
            text=f"{self.sessao.nome}  ▾",
            style="Account.TMenubutton",
        )
        menu_conta = Menu(conta, tearoff=False, font=("Segoe UI", 9))
        menu_conta.add_command(label="Sobre o FiscalPro", command=self._abrir_sobre)
        menu_conta.add_command(label="Backup e restauração", command=self._abrir_backup)
        menu_conta.add_separator()
        menu_conta.add_command(label="Alterar senha", command=self._abrir_alterar_senha)
        menu_conta.add_separator()
        menu_conta.add_command(label="Sair do FiscalPro", command=self._logout)
        conta.configure(menu=menu_conta)
        conta.pack(side=RIGHT)

        info_usuario = Frame(status, bg=COR_PRIMARIA)
        info_usuario.pack(side=RIGHT, padx=(0, 12))
        ttk.Label(
            info_usuario,
            text=f"{self.sessao.perfil.title()}",
            style="HeaderSubtitle.TLabel",
        ).pack(anchor="e")
        ttk.Label(
            info_usuario,
            text=f"● Sistema operacional  •  Interface {VERSAO_INTERFACE}",
            style="HeaderSubtitle.TLabel",
        ).pack(anchor="e", pady=(2, 0))

    def criar_rodape(self):
        rodape = Frame(
            self.janela,
            bg=COR_CARD,
            height=30,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
        )
        rodape.pack(side="bottom", fill=X)
        rodape.pack_propagate(False)

        Label(
            rodape,
            textvariable=self.var_status_rodape,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8),
        ).pack(side=LEFT, padx=14)
        Label(
            rodape,
            text="FiscalPro • Stephane Rhis + ChatGPT",
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8),
        ).pack(side=RIGHT, padx=14)

    def criar_abas(self):
        area = ttk.Frame(self.janela, style="Page.TFrame")
        area.pack(fill=BOTH, expand=True, padx=8, pady=(4, 4))

        self.notebook = ttk.Notebook(area)
        self.notebook.pack(fill=BOTH, expand=True)

        self.aba_sped = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_empresas = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_tributacao = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_correcoes = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_dere = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_relatorios = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_financeiro = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_entregas = ttk.Frame(self.notebook, style="Page.TFrame")
        self.aba_nfse = ttk.Frame(self.notebook, style="Page.TFrame")

        self.notebook.add(self.aba_sped, text="  SPED  ")
        self.notebook.add(self.aba_empresas, text="  Empresas  ")
        self.notebook.add(self.aba_tributacao, text="  Tributação  ")
        self.notebook.add(self.aba_correcoes, text="  Correções  ")
        self.notebook.add(self.aba_dere, text="  DeRE  ")
        self.notebook.add(self.aba_relatorios, text="  Relatórios  ")
        self.notebook.add(self.aba_financeiro, text="  Contas a Pagar  ")
        self.notebook.add(self.aba_entregas, text="  Controle de Entregas  ")
        self.notebook.add(self.aba_nfse, text="  NF-e / NFS-e  ")

        self.criar_painel_sped()
        self.criar_painel_empresas()
        self.criar_painel_tributacao()
        self.criar_painel_correcoes()
        self.criar_painel_dere()
        self.criar_painel_relatorios()
        self.criar_painel_financeiro()
        self.criar_painel_entregas()
        self.criar_painel_nfse()

    def _cabecalho_pagina(self, master, titulo: str, descricao: str):
        quadro = Frame(
            master,
            bg=COR_CARD,
            bd=0,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
        )
        quadro.pack(fill=X, padx=10, pady=(7, 6))

        barra = Frame(quadro, bg=COR_DESTAQUE, height=3)
        barra.pack(fill=X)

        conteudo = Frame(quadro, bg=COR_CARD, padx=12, pady=6)
        conteudo.pack(fill=X)
        Label(
            conteudo,
            text=titulo,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        descricao_label = Label(
            conteudo,
            text=descricao,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=FONTE_NORMAL,
            wraplength=1050,
            justify=LEFT,
        )
        descricao_label.pack(anchor="w", fill=X, pady=(2, 0))
        vincular_wraplength(descricao_label, margem=36, minimo=380)
        return quadro

    def criar_painel_sped(self):
        self._cabecalho_pagina(
            self.aba_sped,
            "Central de análise SPED",
            "Use o SPED Inteligente, vincule XMLs quando necessário e acompanhe a auditoria em uma única tela.",
        )

        self.dashboard = Dashboard(self.aba_sped)
        self.painel_info = PainelInfo(self.aba_sped)
        self.criar_botoes(self.aba_sped)
        self.criar_resultado()

    def criar_botoes(self, master):
        frame = ttk.LabelFrame(
            master,
            text="Ações rápidas",
            padding=8,
            style="Card.TLabelframe",
        )
        frame.pack(fill=X, padx=10, pady=(0, 6))
        for coluna in range(4):
            frame.columnconfigure(coluna, weight=1, uniform="acoes")

        ttk.Button(
            frame,
            text="SPED Inteligente",
            command=self.abrir_sped_inteligente,
            style="Accent.TButton",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=2)
        ttk.Button(
            frame,
            text="XML → Planilha ST",
            command=self.abrir_xml_icms_st,
            style="Secondary.TButton",
        ).grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        ttk.Button(
            frame,
            text="Consulta tributária",
            command=self.abrir_consulta_tributaria,
            style="Secondary.TButton",
        ).grid(row=0, column=2, sticky="ew", padx=5, pady=2)
        ttk.Button(
            frame,
            text="Ficha inteligente",
            command=self.abrir_ficha_tributaria,
            style="Secondary.TButton",
        ).grid(row=0, column=3, sticky="ew", padx=(5, 0), pady=2)

    def criar_resultado(self):
        frame = ttk.LabelFrame(
            self.aba_sped,
            text="Resultado da análise",
            padding=7,
            style="Card.TLabelframe",
        )
        frame.pack(fill=BOTH, expand=True, padx=10, pady=(0, 7))
        frame.configure(height=180)
        frame.grid_propagate(False)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.txt_resultado = Text(frame, wrap=WORD, font=FONTE_RESULTADO, padx=8, pady=6)
        barra = ttk.Scrollbar(frame, orient="vertical", command=self.txt_resultado.yview)
        self.txt_resultado.configure(yscrollcommand=barra.set)
        self.txt_resultado.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.txt_resultado.insert(
            END,
            "Bem-vinda ao FiscalPro. Use o SPED Inteligente para iniciar a análise.\n",
        )

    def _card_acao(self, master, coluna, titulo, descricao, botao, comando, estilo, linha=0, columnspan=1):
        card = Frame(
            master,
            bg=COR_CARD,
            bd=0,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=14,
            pady=11,
        )
        card.grid(row=linha, column=coluna, columnspan=columnspan, sticky="nsew", padx=6, pady=6)
        Label(
            card,
            text=titulo,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        Label(
            card,
            text=descricao,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=FONTE_NORMAL,
            wraplength=620 if columnspan > 1 else 300,
            justify=LEFT,
        ).pack(anchor="w", fill=X, expand=True, pady=(5, 9))
        ttk.Button(card, text=botao, command=comando, style=estilo).pack(fill=X)

    def _grupo_tributario(self, master, coluna, titulo, descricao, acoes, linha=0):
        card = Frame(
            master,
            bg=COR_CARD,
            bd=0,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=14,
            pady=12,
        )
        card.grid(row=linha, column=coluna, sticky="nsew", padx=6, pady=6)
        Label(
            card,
            text=titulo,
            bg=COR_CARD,
            fg=COR_PRIMARIA,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        Label(
            card,
            text=descricao,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=FONTE_NORMAL,
            justify=LEFT,
            anchor="w",
            wraplength=360,
        ).pack(anchor="w", fill=X, pady=(3, 9))
        for indice, (rotulo, comando, estilo) in enumerate(acoes):
            ttk.Button(card, text=rotulo, command=comando, style=estilo).pack(
                fill=X, pady=(0 if indice == 0 else 4, 0)
            )

    def _obter_saude_base_tributaria(self):
        itens = []
        try:
            conn = Banco.conectar()
            try:
                consultas = (
                    ("NCM oficial", "ncm_oficial"),
                    ("TIPI oficial", "tipi_oficial"),
                    ("ICMS-ST/MG", "st_mg_oficial"),
                )
                for rotulo, tabela in consultas:
                    total = int(conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0])
                    texto_total = f"{total:,}".replace(",", ".")
                    itens.append((rotulo, f"{texto_total} registros", "#2E7D32" if total else "#E59A13"))
            finally:
                conn.close()
        except Exception:
            itens = [
                ("NCM oficial", "Verificar base", "#E59A13"),
                ("TIPI oficial", "Verificar base", "#E59A13"),
                ("ICMS-ST/MG", "Verificar base", "#E59A13"),
            ]
        itens.append(("PIS/COFINS", "Motor nacional ativo", "#2E7D32"))
        return itens

    def _tributacao_empresa_alterada(self, _evento=None):
        empresa = self.trib_empresa_var.get().strip()
        regime = EmpresasRegimesService.resolver_regime(empresa, "")
        self.trib_regime_var.set(
            EmpresasRegimesService.descricao_regime(empresa, regime)
            if regime
            else "Selecione uma empresa para aplicar o regime automaticamente."
        )

    def abrir_ficha_tributaria_rapida(self):
        termo = self.trib_pesquisa_var.get().strip()
        if not termo:
            messagebox.showwarning(
                "FiscalPro",
                "Informe um NCM ou uma descrição do produto para analisar.",
                parent=self.janela,
            )
            return
        empresa = self.trib_empresa_var.get().strip()
        if empresa in {"", "Todas as empresas"}:
            messagebox.showwarning(
                "FiscalPro",
                "Selecione uma empresa antes de analisar. Assim o FiscalPro aplica o regime e as alíquotas de PIS/COFINS corretos.",
                parent=self.janela,
            )
            return
        empresa_contexto = empresa
        regime = EmpresasRegimesService.resolver_regime(empresa_contexto, "")
        contexto = {
            "empresa": empresa_contexto,
            "regime": regime,
            "operacao": self.trib_operacao_var.get().strip(),
            "uf_origem": self.trib_uf_origem_var.get().strip(),
            "uf_destino": self.trib_uf_destino_var.get().strip(),
            "finalidade": "REVENDA",
        }
        janela = JanelaFichaTributaria(self.janela, contexto=contexto, ncm=termo)
        self._vincular_atualizacao_central_ao_fechar(janela)

    @staticmethod
    def _texto_curto(texto: str, limite: int = 38) -> str:
        texto = " ".join(str(texto or "").split())
        return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"

    def _vincular_atualizacao_central_ao_fechar(self, janela):
        def ao_destruir(evento):
            if evento.widget is janela and hasattr(self, "trib_acessos_frame"):
                try:
                    self.janela.after_idle(self._atualizar_acessos_tributarios)
                except Exception:
                    pass
        janela.bind("<Destroy>", ao_destruir, add="+")

    def _abrir_consulta_recente(self, item):
        self.trib_pesquisa_var.set(str(item.get("ncm") or ""))
        empresa = str(item.get("empresa") or "").strip()
        if empresa in EmpresasRegimesService.listar_empresas(incluir_todas=True):
            self.trib_empresa_var.set(empresa)
        self.trib_operacao_var.set(str(item.get("operacao") or "SAÍDA") or "SAÍDA")
        uf_origem = str(item.get("uf_origem") or "MG") or "MG"
        uf_destino = str(item.get("uf_destino") or "MG") or "MG"
        self.trib_uf_origem_var.set(uf_origem)
        self.trib_uf_destino_var.set(uf_destino)
        self._tributacao_empresa_alterada()
        self.abrir_ficha_tributaria_rapida()

    def _usar_favorito_tributario(self, item):
        self.trib_pesquisa_var.set(str(item.get("ncm") or ""))
        empresa = self.trib_empresa_var.get().strip()
        if empresa not in {"", "Todas as empresas"}:
            self.abrir_ficha_tributaria_rapida()
        else:
            self.var_status_rodape.set("Favorito carregado. Selecione a empresa para analisar com o regime correto.")

    def _limpar_acessos_frame(self, frame):
        for filho in frame.winfo_children():
            filho.destroy()

    def _preencher_lista_acesso(self, frame, itens, tipo: str):
        self._limpar_acessos_frame(frame)
        if not itens:
            mensagem = "As próximas consultas aparecerão aqui." if tipo == "recente" else "Favorite um NCM na Ficha Inteligente para acessá-lo daqui."
            Label(frame, text=mensagem, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8), anchor="w").pack(fill=X, pady=3)
            return
        for item in itens[:4]:
            ncm = str(item.get("ncm") or "")
            descricao = self._texto_curto(item.get("descricao") or "", 28 if tipo == "recente" else 34)
            if tipo == "recente":
                empresa = self._texto_curto(item.get("empresa") or "", 20)
                uf_origem = str(item.get("uf_origem") or "-").strip().upper() or "-"
                uf_destino = str(item.get("uf_destino") or "-").strip().upper() or "-"
                contexto = f"{empresa} • {uf_origem}→{uf_destino}" if empresa else f"{uf_origem}→{uf_destino}"
                texto = f"{ncm}  •  {contexto}  •  {descricao}"
            else:
                texto = f"{ncm}  •  {descricao}"
            comando = (lambda dado=dict(item): self._abrir_consulta_recente(dado)) if tipo == "recente" else (lambda dado=dict(item): self._usar_favorito_tributario(dado))
            ttk.Button(frame, text=texto, command=comando, style="Secondary.TButton").pack(fill=X, pady=(0, 4))

    def _atualizar_acessos_tributarios(self):
        if not hasattr(self, "trib_recentes_lista") or not hasattr(self, "trib_favoritos_lista"):
            return
        try:
            recentes = FichaTributariaRepository.listar_consultas_recentes(limite=4)
            favoritos = FichaTributariaRepository.listar_favoritos()[:4]
        except Exception:
            recentes, favoritos = [], []
        self._preencher_lista_acesso(self.trib_recentes_lista, recentes, "recente")
        self._preencher_lista_acesso(self.trib_favoritos_lista, favoritos, "favorito")

    def abrir_comparador_tributario(self):
        termo = self.trib_pesquisa_var.get().strip() if hasattr(self, "trib_pesquisa_var") else ""
        empresa = self.trib_empresa_var.get().strip() if hasattr(self, "trib_empresa_var") else ""
        if empresa == "Todas as empresas":
            empresa = ""
        contexto = {
            "empresa": empresa,
            "regime": EmpresasRegimesService.resolver_regime(empresa, ""),
            "operacao": self.trib_operacao_var.get().strip() if hasattr(self, "trib_operacao_var") else "SAÍDA",
            "uf_origem": self.trib_uf_origem_var.get().strip() if hasattr(self, "trib_uf_origem_var") else "MG",
            "uf_destino": self.trib_uf_destino_var.get().strip() if hasattr(self, "trib_uf_destino_var") else "MG",
            "finalidade": "REVENDA",
        }
        JanelaCompararCenariosTributarios(self.janela, ncm=termo, contexto_base=contexto)

    def abrir_mapa_cobertura_tributaria(self):
        JanelaCoberturaTributaria(self.janela)

    def abrir_calculo_icms_st_direto(self):
        # A calculadora passou a exigir o contexto da operação e os dados do
        # enquadramento. No acesso direto da Central Tributária ela deve abrir
        # em modo manual, sem depender de uma Ficha/NCM previamente consultados.
        empresa = self.trib_empresa_var.get().strip() if hasattr(self, "trib_empresa_var") else ""
        if empresa == "Todas as empresas":
            empresa = ""
        contexto = {
            "empresa": empresa,
            "regime": EmpresasRegimesService.resolver_regime(empresa, ""),
            "operacao": self.trib_operacao_var.get().strip() if hasattr(self, "trib_operacao_var") else "SAÍDA",
            "uf_origem": self.trib_uf_origem_var.get().strip() if hasattr(self, "trib_uf_origem_var") else "MG",
            "uf_destino": self.trib_uf_destino_var.get().strip() if hasattr(self, "trib_uf_destino_var") else "MG",
            "finalidade": "REVENDA",
        }
        JanelaCalculoICMSSTMG(
            self.janela,
            ncm="",
            descricao="Cálculo manual",
            enquadramento_st={},
            contexto=contexto,
        )

    def abrir_difal_fcp_direto(self):
        JanelaDIFALFCP(self.janela)

    def criar_painel_tributacao(self):
        # Central Tributária Inteligente — 17.8.28.
        # Mantém os motores já validados e reorganiza a experiência em:
        # consulta rápida, saúde da base e ferramentas por finalidade.
        contenedor = ttk.Frame(self.aba_tributacao, style="Page.TFrame")
        contenedor.pack(fill=BOTH, expand=True)
        contenedor.rowconfigure(0, weight=1)
        contenedor.columnconfigure(0, weight=1)

        canvas = Canvas(contenedor, bg=COR_FUNDO, highlightthickness=0, bd=0)
        barra = ttk.Scrollbar(contenedor, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=barra.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")

        conteudo = ttk.Frame(canvas, style="Page.TFrame")
        janela_canvas = canvas.create_window((0, 0), window=conteudo, anchor="nw")

        def ajustar_regiao(_evento=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def ajustar_largura(evento):
            canvas.itemconfigure(janela_canvas, width=evento.width)

        conteudo.bind("<Configure>", ajustar_regiao)
        canvas.bind("<Configure>", ajustar_largura)

        def rolar(evento):
            canvas.yview_scroll(-1 if evento.delta > 0 else 1, "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", rolar))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        self._cabecalho_pagina(
            conteudo,
            "Central Tributária Inteligente",
            "Comece pelo produto e deixe o FiscalPro aplicar empresa, regime e exceções antes de mostrar os tributos. Ferramentas técnicas continuam disponíveis sem poluir a consulta principal.",
        )

        # Consulta rápida
        consulta = Frame(
            conteudo,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=14,
            pady=12,
        )
        consulta.pack(fill=X, padx=14, pady=(0, 6))
        Label(
            consulta,
            text="Consulta rápida",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        Label(
            consulta,
            text="NCM ou descrição do produto  •  Enter = analisar",
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=FONTE_NORMAL,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 3))

        self.trib_pesquisa_var = StringVar()
        self.trib_empresa_var = StringVar(value="Todas as empresas")
        self.trib_operacao_var = StringVar(value="SAÍDA")
        self.trib_uf_origem_var = StringVar(value="MG")
        self.trib_uf_destino_var = StringVar(value="MG")
        self.trib_regime_var = StringVar(value="Selecione uma empresa para aplicar o regime automaticamente.")

        entrada = ttk.Entry(consulta, textvariable=self.trib_pesquisa_var, font=("Segoe UI", 11))
        entrada.grid(row=2, column=0, columnspan=3, sticky="ew", padx=(0, 8))
        entrada.bind("<Return>", lambda _e: self.abrir_ficha_tributaria_rapida())
        entrada.bind("<KP_Enter>", lambda _e: self.abrir_ficha_tributaria_rapida())
        ttk.Button(
            consulta,
            text="ANALISAR TRIBUTAÇÃO",
            command=self.abrir_ficha_tributaria_rapida,
            style="Accent.TButton",
        ).grid(row=2, column=3, sticky="ew")

        campos = (
            ("Empresa", self.trib_empresa_var, EmpresasRegimesService.listar_empresas(incluir_todas=True)),
            ("Operação", self.trib_operacao_var, ("ENTRADA", "SAÍDA", "DEVOLUÇÃO", "TRANSFERÊNCIA", "IMPORTAÇÃO", "EXPORTAÇÃO")),
            ("UF origem", self.trib_uf_origem_var, ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")),
            ("UF destino", self.trib_uf_destino_var, ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")),
        )
        for coluna, (rotulo, variavel, valores) in enumerate(campos):
            Label(consulta, text=rotulo, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=FONTE_NORMAL).grid(
                row=3, column=coluna, sticky="w", pady=(10, 3)
            )
            combo = ttk.Combobox(consulta, textvariable=variavel, state="readonly", values=valores)
            combo.grid(row=4, column=coluna, sticky="ew", padx=(0, 8 if coluna < 3 else 0))
            if coluna == 0:
                combo.bind("<<ComboboxSelected>>", self._tributacao_empresa_alterada)

        Label(
            consulta,
            textvariable=self.trib_regime_var,
            bg=COR_CARD,
            fg=COR_PRIMARIA,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        for coluna in range(4):
            consulta.columnconfigure(coluna, weight=1)

        # Saúde da base tributária
        titulo_saude = Frame(conteudo, bg=COR_FUNDO)
        titulo_saude.pack(fill=X, padx=14, pady=(5, 0))
        Label(titulo_saude, text="Saúde das bases", bg=COR_FUNDO, fg=COR_TEXTO, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Label(titulo_saude, text="  Bases usadas na análise automática", bg=COR_FUNDO, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).pack(side=LEFT)

        ttk.Button(
            titulo_saude,
            text="Mapa de cobertura por UF",
            command=self.abrir_mapa_cobertura_tributaria,
            style="Secondary.TButton",
        ).pack(side=RIGHT)

        saude = Frame(conteudo, bg=COR_FUNDO)
        saude.pack(fill=X, padx=8, pady=(0, 4))
        for coluna in range(4):
            saude.columnconfigure(coluna, weight=1, uniform="saude")
        for coluna, (rotulo, valor, cor) in enumerate(self._obter_saude_base_tributaria()):
            card = Frame(saude, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA, padx=12, pady=8)
            card.grid(row=0, column=coluna, sticky="nsew", padx=6, pady=4)
            Frame(card, bg=cor, height=4).pack(fill=X, pady=(0, 7))
            cab = Frame(card, bg=COR_CARD)
            cab.pack(fill=X)
            Label(cab, text=rotulo, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8, "bold")).pack(side=LEFT)
            Label(cab, text="✓ ATIVO" if cor == "#2E7D32" else "⚠ REVISAR", bg=COR_CARD, fg=cor, font=("Segoe UI", 7, "bold")).pack(side=RIGHT)
            Label(card, text=valor, bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(3, 0))

        # Acesso rápido — últimas consultas e favoritos.
        self.trib_acessos_frame = Frame(conteudo, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA, padx=12, pady=10)
        self.trib_acessos_frame.pack(fill=X, padx=14, pady=(2, 8))
        topo_acesso = Frame(self.trib_acessos_frame, bg=COR_CARD)
        topo_acesso.pack(fill=X, pady=(0, 6))
        Label(topo_acesso, text="Acesso rápido", bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Label(topo_acesso, text="Consulte de novo ou retome seus NCMs favoritos", bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).pack(side=LEFT, padx=(10, 0))
        ttk.Button(topo_acesso, text="↻ Atualizar", command=self._atualizar_acessos_tributarios, style="Secondary.TButton").pack(side=RIGHT)

        colunas_acesso = Frame(self.trib_acessos_frame, bg=COR_CARD)
        colunas_acesso.pack(fill=X)
        colunas_acesso.columnconfigure(0, weight=1, uniform="acesso")
        colunas_acesso.columnconfigure(1, weight=1, uniform="acesso")
        recentes_box = Frame(colunas_acesso, bg=COR_CARD, padx=4)
        favoritos_box = Frame(colunas_acesso, bg=COR_CARD, padx=4)
        recentes_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        favoritos_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        Label(recentes_box, text="🕘 ÚLTIMAS CONSULTAS", bg=COR_CARD, fg=COR_PRIMARIA, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        Label(favoritos_box, text="★ FAVORITOS", bg=COR_CARD, fg=COR_PRIMARIA, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        self.trib_recentes_lista = Frame(recentes_box, bg=COR_CARD)
        self.trib_favoritos_lista = Frame(favoritos_box, bg=COR_CARD)
        self.trib_recentes_lista.pack(fill=X)
        self.trib_favoritos_lista.pack(fill=X)
        self._atualizar_acessos_tributarios()

        # Ferramentas por intenção
        grupos = ttk.Frame(conteudo, style="Page.TFrame")
        grupos.pack(fill=X, padx=8, pady=(0, 6))
        for coluna in range(3):
            grupos.columnconfigure(coluna, weight=1, uniform="grupos")

        self._grupo_tributario(
            grupos, 0, "CONSULTAR",
            "Para descobrir o tratamento fiscal de um produto ou comparar cenários.",
            (
                ("Ficha Inteligente", self.abrir_ficha_tributaria, "Primary.TButton"),
                ("Comparar cenários", self.abrir_comparador_tributario, "Accent.TButton"),
                ("Mapa de cobertura por UF", self.abrir_mapa_cobertura_tributaria, "Secondary.TButton"),
                ("Robô Tributário", self.abrir_robo_tributario, "Secondary.TButton"),
                ("Simulador", self.abrir_simulador_tributario, "Secondary.TButton"),
            ),
        )
        self._grupo_tributario(
            grupos, 1, "AUDITAR",
            "Para conferir cadastros e operações em lote antes de chegar ao SPED.",
            (
                ("Auditoria de cadastro por Excel", self.abrir_auditoria_cadastros_excel, "Accent.TButton"),
                ("Auditoria de cadastro por XML", self.abrir_auditoria_cadastros_xml, "Secondary.TButton"),
                ("Análise em lote", self.abrir_analise_tributaria_lote, "Secondary.TButton"),
            ),
        )
        self._grupo_tributario(
            grupos, 2, "CALCULAR",
            "Para memórias de cálculo e conferências específicas da operação.",
            (
                ("ICMS-ST / MVA", self.abrir_calculo_icms_st_direto, "Primary.TButton"),
                ("XML → Planilha ST", self.abrir_xml_icms_st, "Secondary.TButton"),
                ("DIFAL / FCP", self.abrir_difal_fcp_direto, "Secondary.TButton"),
                ("Configurar venda no Olist", self.abrir_configurador_olist, "Accent.TButton"),
            ),
        )

        legenda = Frame(
            conteudo, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA, padx=14, pady=10
        )
        legenda.pack(fill=X, padx=14, pady=(0, 12))
        Label(legenda, text="Semáforo tributário", bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(0, 18))
        for simbolo, texto, cor in (
            ("●", "CONFIRMADO", "#2E7D32"),
            ("●", "REVISAR", "#E59A13"),
            ("●", "REGRA MANUAL", "#2563A8"),
            ("●", "DIVERGÊNCIA", "#C83E4D"),
        ):
            Label(legenda, text=f"{simbolo} {texto}", bg=COR_CARD, fg=cor, font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 18))

    def criar_painel_correcoes(self):
        self._cabecalho_pagina(
            self.aba_correcoes,
            "Correções e auditorias",
            "Revise divergências com segurança antes de qualquer alteração no SPED.",
        )

        acoes = ttk.Frame(self.aba_correcoes, style="Page.TFrame")
        acoes.pack(fill=X, padx=14, pady=(0, 8))
        acoes.columnconfigure(0, weight=1)
        acoes.columnconfigure(1, weight=1)
        self._card_acao(
            acoes,
            0,
            "Exclusão ICMS-ST da base PIS/COFINS — Etapa 1",
            "Cruze o SPED Contribuições com os XMLs de entrada e confirme se o ICMS-ST já está fora da base. Modo auditoria: não altera o SPED.",
            "Auditar entradas com ICMS-ST",
            self.abrir_auditoria_icms_st_piscofins,
            "Accent.TButton",
            linha=0,
            columnspan=2,
        )
        self._card_acao(
            acoes,
            0,
            "Exclusão ICMS-ST da base PIS/COFINS — Etapa 2",
            "Pré-audite as saídas pelo SPED e identifique o CFOP 5405. Os XMLs de saída serão usados na próxima validação para confirmar o ICMS-ST antes de qualquer correção.",
            "Pré-auditar saídas com ST",
            self.abrir_auditoria_icms_st_piscofins_saidas,
            "Accent.TButton",
            linha=1,
            columnspan=2,
        )

        frame = ttk.LabelFrame(
            self.aba_correcoes,
            text="Relatório de correções",
            padding=7,
            style="Card.TLabelframe",
        )
        frame.pack(fill=BOTH, expand=True, padx=14, pady=(0, 10))
        frame.configure(height=260)
        frame.grid_propagate(False)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.txt_correcoes = Text(frame, wrap=WORD, font=FONTE_RESULTADO, padx=8, pady=6)
        barra = ttk.Scrollbar(frame, orient="vertical", command=self.txt_correcoes.yview)
        self.txt_correcoes.configure(yscrollcommand=barra.set)
        self.txt_correcoes.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.txt_correcoes.insert(END, "As correções executadas serão apresentadas aqui.\n")

    def criar_painel_dere(self):
        self.painel_dere = PainelDeRE(self.aba_dere)
        self.painel_dere.pack(fill=BOTH, expand=True)

    def criar_painel_relatorios(self):
        self._cabecalho_pagina(
            self.aba_relatorios,
            "Relatórios do FiscalPro",
            "Os relatórios gerados pelos módulos permanecem disponíveis nas respectivas telas.",
        )
        quadro = Frame(
            self.aba_relatorios,
            bg=COR_CARD,
            bd=0,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=18,
            pady=18,
        )
        quadro.pack(fill=BOTH, expand=True, padx=14, pady=(0, 10))
        Label(
            quadro,
            text="Central de relatórios em evolução",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        Label(
            quadro,
            text=(
                "Nesta fase, continue gerando planilhas e pareceres diretamente pela Ficha Tributária, "
                "SPED Inteligente e XML → ICMS-ST. A central unificada será conectada em uma sprint futura."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=FONTE_NORMAL,
            wraplength=900,
            justify=LEFT,
        ).pack(anchor="w", pady=(8, 0))

    def criar_painel_empresas(self):
        self.painel_empresas = PainelEmpresas(self.aba_empresas, ao_alterar=self._empresas_atualizadas)
        self.painel_empresas.pack(fill=BOTH, expand=True)
        self.janela.bind("<<AbrirCadastroEmpresas>>", lambda _e: self._selecionar_aba_empresas(), add="+")

    def _selecionar_aba_empresas(self):
        self.notebook.select(self.aba_empresas)
        try:
            self.painel_empresas.atualizar()
        except Exception:
            pass

    def _empresas_atualizadas(self):
        """Atualiza os painéis persistentes após mudar o cadastro central."""
        try:
            self.painel_entregas.servico.sincronizar_estrutura_atual()
            self.painel_entregas.atualizar()
        except Exception:
            pass
        try:
            self.painel_contas_pagar.atualizar()
        except Exception:
            pass
        try:
            painel_nfse = self.painel_nfse.painel_nfse
            painel_nfse._carregar_empresas()
            painel_nfse._consultar_local()
        except Exception:
            pass
        try:
            painel_nfe = self.painel_nfse.painel_nfe
            painel_nfe._carregar_empresas()
        except Exception:
            pass
        self.var_status_rodape.set("Cadastro de empresas atualizado em todos os módulos")

    def criar_painel_financeiro(self):
        self.painel_contas_pagar = PainelContasPagar(self.aba_financeiro)
        self.painel_contas_pagar.pack(fill=BOTH, expand=True)

    def criar_painel_entregas(self):
        self.painel_entregas = PainelEntregas(self.aba_entregas)
        self.painel_entregas.pack(fill=BOTH, expand=True)

    def criar_painel_nfse(self):
        self.painel_nfse = PainelDocumentosFiscais(self.aba_nfse)
        self.painel_nfse.pack(fill=BOTH, expand=True)

    def _definir_status(self, texto: str):
        self.var_status_rodape.set(texto)
        self.janela.update_idletasks()

    def abrir_consulta_tributaria(self):
        JanelaConsultaNCM(self.janela)

    def abrir_ficha_tributaria(self):
        janela = JanelaFichaTributaria(self.janela)
        self._vincular_atualizacao_central_ao_fechar(janela)

    def abrir_xml_icms_st(self):
        JanelaXMLICMSST(self.janela)

    def abrir_analise_tributaria_lote(self):
        JanelaAnaliseTributariaLote(self.janela)

    def abrir_auditoria_cadastros_xml(self):
        JanelaAuditoriaCadastrosXML(self.janela)

    def abrir_auditoria_cadastros_excel(self):
        JanelaAuditoriaCadastrosExcel(self.janela)

    def abrir_auditoria_icms_st_piscofins(self):
        JanelaAuditoriaICMSSTPISCOFINS(self.janela)

    def abrir_auditoria_icms_st_piscofins_saidas(self):
        JanelaAuditoriaICMSSTPISCOFINSSaidas(self.janela)

    def abrir_robo_tributario(self):
        JanelaRoboTributario(self.janela)

    def abrir_sped_inteligente(self):
        JanelaSPEDInteligente(self.janela)

    def abrir_simulador_tributario(self):
        JanelaSimuladorTributario(self.janela)

    def abrir_configurador_olist(self):
        JanelaConfiguradorOlist(self.janela)

    def atualizar_info(self, empresa, periodo, sped, xml):
        self.painel_info.atualizar(empresa, periodo, sped, xml)

    def _abrir_sobre(self):
        JanelaSobre(self.janela)

    def _abrir_backup(self):
        JanelaBackup(self.janela, ao_restaurar=self._reiniciar_apos_restauracao)

    def _abrir_alterar_senha(self):
        JanelaAlterarSenha(self.janela, self.servico_autenticacao, self.sessao)

    def _reiniciar_apos_restauracao(self):
        self.acao_saida = "reiniciar"
        self.janela.destroy()

    def _logout(self):
        confirmar = messagebox.askyesno(
            "FiscalPro",
            "Deseja sair deste usuário e voltar para a tela de login?",
            parent=self.janela,
        )
        if not confirmar:
            return
        self.acao_saida = "logout"
        self.janela.destroy()

    def _encerrar(self):
        self.acao_saida = "encerrar"
        self.janela.destroy()

    def executar(self) -> str:
        self.janela.mainloop()
        return self.acao_saida
