"""Painel gráfico do Robô FiscalPro — Gmail e links seguros."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    Y,
    BooleanVar,
    IntVar,
    StringVar,
    Text,
    Toplevel,
    filedialog,
    messagebox,
)
from tkinter import ttk

from src.robo_email.config import (
    CATEGORIAS_DOCUMENTOS_ESPERADOS,
    EMAIL_PRINCIPAL,
    EMPRESAS_POR_ALIAS,
    INSTRUCOES_PATH,
    ConfiguracaoRoboEmail,
)
from src.robo_email.painel_mensal import (
    DocumentoMensal,
    PainelMensalService,
    ResumoEmpresaMensal,
)
from src.robo_email.repositorio import RoboEmailRepositorio
from src.robo_email.servico import ResultadoProcessamento, RoboEmailService
from src.ui.layout_responsivo import dimensionar_janela


class PainelRoboEmail(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=14)
        self.configuracao = ConfiguracaoRoboEmail.carregar()
        self.em_execucao = False
        self.janela_links: Toplevel | None = None
        self.tabela_links: ttk.Treeview | None = None
        self.janela_painel_mensal: Toplevel | None = None
        self.tabela_painel_mensal: ttk.Treeview | None = None
        self.var_mes_painel: StringVar | None = None
        self.var_ano_painel: IntVar | None = None
        self.var_resumo_painel: StringVar | None = None
        self.resumos_painel: list[ResumoEmpresaMensal] = []
        self.documentos_painel: list[DocumentoMensal] = []

        self.var_credenciais = StringVar(value=self.configuracao.caminho_credenciais)
        self.var_destino = StringVar(value=self.configuracao.pasta_destino)
        self.var_dias = IntVar(value=self.configuracao.dias_retroativos)
        self.var_nao_lidos = BooleanVar(value=self.configuracao.somente_nao_lidos)
        self.var_limite = IntVar(value=self.configuracao.limite_mensagens)
        self.var_registrar_links = BooleanVar(value=self.configuracao.registrar_links)
        self.var_auto_links = BooleanVar(value=self.configuracao.baixar_links_automaticamente)
        self.var_dominios = StringVar(value=", ".join(self.configuracao.dominios_confiaveis))
        self.var_max_mb = IntVar(value=self.configuracao.tamanho_maximo_link_mb)

        self.var_status = StringVar(value="Aguardando")
        self.var_emails = StringVar(value="0")
        self.var_arquivos = StringVar(value="0")
        self.var_duplicados = StringVar(value="0")
        self.var_links = StringVar(value="0")
        self.var_pendentes = StringVar(value="0")
        self.var_erros = StringVar(value="0")

        self._montar_tela()

    def _montar_tela(self) -> None:
        cabecalho = ttk.LabelFrame(self, text="Robô FiscalPro — Gmail", padding=14)
        cabecalho.pack(fill=X, pady=(0, 10))

        ttk.Label(
            cabecalho,
            text="Baixa anexos e identifica links de guias com proteção por domínio autorizado.",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Label(cabecalho, text="Conta principal:").grid(row=1, column=0, sticky="w")
        ttk.Label(cabecalho, text=EMAIL_PRINCIPAL).grid(row=1, column=1, columnspan=3, sticky="w")

        configuracao = ttk.LabelFrame(self, text="Configuração", padding=12)
        configuracao.pack(fill=X, pady=(0, 10))
        configuracao.columnconfigure(1, weight=1)

        ttk.Label(configuracao, text="Credenciais Google (JSON):").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4
        )
        ttk.Entry(configuracao, textvariable=self.var_credenciais).grid(
            row=0, column=1, sticky="ew", pady=4
        )
        ttk.Button(configuracao, text="Selecionar", command=self._selecionar_credenciais).grid(
            row=0, column=2, padx=(8, 0), pady=4
        )

        ttk.Label(configuracao, text="Pasta dos documentos:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=4
        )
        ttk.Entry(configuracao, textvariable=self.var_destino).grid(
            row=1, column=1, sticky="ew", pady=4
        )
        ttk.Button(configuracao, text="Selecionar", command=self._selecionar_destino).grid(
            row=1, column=2, padx=(8, 0), pady=4
        )

        opcoes = ttk.Frame(configuracao)
        opcoes.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        ttk.Label(opcoes, text="Buscar últimos").pack(side=LEFT)
        ttk.Spinbox(opcoes, from_=1, to=3650, width=7, textvariable=self.var_dias).pack(
            side=LEFT, padx=5
        )
        ttk.Label(opcoes, text="dias").pack(side=LEFT)
        ttk.Checkbutton(
            opcoes, text="Somente e-mails não lidos (opcional)", variable=self.var_nao_lidos
        ).pack(side=LEFT, padx=18)
        ttk.Label(opcoes, text="Limite:").pack(side=LEFT)
        ttk.Spinbox(
            opcoes, from_=1, to=5000, increment=50, width=8, textvariable=self.var_limite
        ).pack(side=LEFT, padx=5)

        ttk.Label(
            configuracao,
            text=(
                "Recomendado: deixe 'Somente e-mails não lidos' desmarcado. "
                "O FiscalPro já ignora mensagens processadas pelo ID do Gmail."
            ),
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 4))

        links = ttk.LabelFrame(configuracao, text="Links seguros", padding=8)
        links.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        links.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            links,
            text="Identificar links de guias e documentos",
            variable=self.var_registrar_links,
        ).grid(row=0, column=0, sticky="w", padx=(0, 15), pady=3)
        ttk.Checkbutton(
            links,
            text="Baixar automaticamente somente de domínios autorizados",
            variable=self.var_auto_links,
        ).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(links, text="Domínios autorizados:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(links, textvariable=self.var_dominios).grid(
            row=1, column=1, sticky="ew", pady=3
        )
        ttk.Label(links, text="Máx. por link:").grid(
            row=1, column=2, sticky="e", padx=(10, 4), pady=3
        )
        ttk.Spinbox(links, from_=1, to=200, width=6, textvariable=self.var_max_mb).grid(
            row=1, column=3, sticky="w", pady=3
        )
        ttk.Label(links, text="MB").grid(row=1, column=4, sticky="w", padx=(3, 0), pady=3)
        ttk.Label(
            links,
            text="Cadastre somente o domínio verdadeiro do portal da contabilidade. Links desconhecidos ficam pendentes.",
        ).grid(row=2, column=0, columnspan=5, sticky="w", pady=(4, 0))

        botoes = ttk.Frame(self)
        botoes.pack(fill=X, pady=(0, 10))
        for coluna in range(5):
            botoes.columnconfigure(coluna, weight=1)

        self.btn_salvar = ttk.Button(
            botoes, text="💾 Salvar configuração", command=self._salvar_configuracao
        )
        self.btn_salvar.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=3)
        self.btn_conectar = ttk.Button(
            botoes, text="🔐 Conectar ao Gmail", command=self._conectar
        )
        self.btn_conectar.grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        self.btn_buscar = ttk.Button(
            botoes, text="📥 Buscar documentos", command=self._buscar
        )
        self.btn_buscar.grid(row=0, column=2, sticky="ew", padx=4, pady=3)
        self.btn_painel_mensal = ttk.Button(
            botoes, text="📊 Painel mensal", command=self._abrir_painel_mensal
        )
        self.btn_painel_mensal.grid(row=0, column=3, sticky="ew", padx=4, pady=3)
        ttk.Button(botoes, text="🛡️ Links pendentes", command=self._abrir_links).grid(
            row=0, column=4, sticky="ew", padx=(4, 0), pady=3
        )

        self.btn_baixar_links = ttk.Button(
            botoes,
            text="🔗 Baixar links autorizados",
            command=self._baixar_links_autorizados,
        )
        self.btn_baixar_links.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=3)
        ttk.Button(botoes, text="📁 Abrir pasta", command=self._abrir_pasta).grid(
            row=1, column=1, sticky="ew", padx=4, pady=3
        )
        ttk.Button(botoes, text="📋 Ampliar relatório", command=self._ampliar_relatorio).grid(
            row=1, column=2, sticky="ew", padx=4, pady=3
        )
        ttk.Button(botoes, text="❓ Instruções", command=self._abrir_instrucoes).grid(
            row=1, column=3, sticky="ew", padx=4, pady=3
        )
        ttk.Button(
            botoes,
            text="🔎 Revisar não identificados",
            command=self._abrir_revisar_atual,
        ).grid(row=1, column=4, sticky="ew", padx=(4, 0), pady=3)

        resumo = ttk.LabelFrame(self, text="Resumo da execução", padding=10)
        resumo.pack(fill=X, pady=(0, 10))
        ttk.Label(resumo, text="Status:").grid(row=0, column=0, sticky="w")
        ttk.Label(
            resumo, textvariable=self.var_status, font=("Segoe UI", 10, "bold")
        ).grid(row=0, column=1, columnspan=11, sticky="w", padx=(5, 0))
        self._card(resumo, 1, 0, "E-mails", self.var_emails)
        self._card(resumo, 1, 2, "Arquivos", self.var_arquivos)
        self._card(resumo, 1, 4, "Duplicados", self.var_duplicados)
        self._card(resumo, 1, 6, "Links baixados", self.var_links)
        self._card(resumo, 1, 8, "Pendentes", self.var_pendentes)
        self._card(resumo, 1, 10, "Erros", self.var_erros)

        log_frame = ttk.LabelFrame(self, text="Relatório", padding=8)
        log_frame.pack(fill=BOTH, expand=True)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.txt_log = Text(log_frame, wrap="none", height=10)
        barra_log_y = ttk.Scrollbar(log_frame, orient="vertical", command=self.txt_log.yview)
        barra_log_x = ttk.Scrollbar(log_frame, orient="horizontal", command=self.txt_log.xview)
        self.txt_log.configure(yscrollcommand=barra_log_y.set, xscrollcommand=barra_log_x.set)
        self.txt_log.grid(row=0, column=0, sticky="nsew")
        barra_log_y.grid(row=0, column=1, sticky="ns")
        barra_log_x.grid(row=1, column=0, sticky="ew")
        self._log("O robô usa permissão de leitura do Gmail.")
        self._log("Links nunca são abertos automaticamente quando o domínio não está autorizado.")

    @staticmethod
    def _card(master, linha: int, coluna: int, titulo: str, variavel: StringVar) -> None:
        ttk.Label(master, text=f"{titulo}:").grid(
            row=linha, column=coluna, sticky="w", padx=(0, 4), pady=(8, 0)
        )
        ttk.Label(master, textvariable=variavel, font=("Segoe UI", 10, "bold")).grid(
            row=linha,
            column=coluna + 1,
            sticky="w",
            padx=(0, 20),
            pady=(8, 0),
        )

    def _selecionar_credenciais(self) -> None:
        arquivo = filedialog.askopenfilename(
            title="Selecione o JSON de credenciais do Google",
            filetypes=[("Arquivo JSON", "*.json")],
        )
        if arquivo:
            self.var_credenciais.set(arquivo)

    def _selecionar_destino(self) -> None:
        pasta = filedialog.askdirectory(title="Selecione a pasta para os documentos fiscais")
        if pasta:
            self.var_destino.set(pasta)

    def _configuracao_da_tela(self) -> ConfiguracaoRoboEmail:
        return ConfiguracaoRoboEmail(
            caminho_credenciais=self.var_credenciais.get().strip(),
            pasta_destino=self.var_destino.get().strip(),
            dias_retroativos=int(self.var_dias.get()),
            somente_nao_lidos=bool(self.var_nao_lidos.get()),
            limite_mensagens=int(self.var_limite.get()),
            registrar_links=bool(self.var_registrar_links.get()),
            baixar_links_automaticamente=bool(self.var_auto_links.get()),
            dominios_confiaveis=ConfiguracaoRoboEmail.normalizar_dominios(
                self.var_dominios.get()
            ),
            tamanho_maximo_link_mb=int(self.var_max_mb.get()),
            documentos_esperados=self.configuracao.documentos_esperados,
            cnpjs_empresas=self.configuracao.cnpjs_empresas,
        )

    def _salvar_configuracao(
        self, mostrar_mensagem: bool = True
    ) -> ConfiguracaoRoboEmail | None:
        try:
            configuracao = self._configuracao_da_tela()
            erros = configuracao.validar()
            # Para salvar preferências de links antes de conectar, ignoramos apenas
            # a ausência temporária do JSON. Os demais erros continuam bloqueando.
            erros_reais = [
                erro
                for erro in erros
                if not erro.startswith("Selecione o arquivo JSON")
                and not erro.startswith("O arquivo JSON")
            ]
            if erros_reais:
                raise ValueError("\n".join(erros_reais))
            configuracao.salvar()
            self.configuracao = configuracao
            self.var_dominios.set(", ".join(configuracao.dominios_confiaveis))
            if mostrar_mensagem:
                messagebox.showinfo("Robô FiscalPro", "Configuração salva com sucesso.")
            return configuracao
        except (ValueError, OSError) as erro:
            messagebox.showerror("Robô FiscalPro", f"Não foi possível salvar: {erro}")
            return None

    def _conectar(self) -> None:
        configuracao = self._salvar_configuracao(mostrar_mensagem=False)
        if not configuracao:
            return
        self._executar_em_thread("Conectando ao Gmail...", self._tarefa_conectar)

    def _tarefa_conectar(self) -> None:
        servico = RoboEmailService(self.configuracao, log=self._log_threadsafe)
        perfil = servico.conectar()
        email = perfil.get("emailAddress", EMAIL_PRINCIPAL)
        self.after(0, lambda: self.var_status.set(f"Conectado: {email}"))
        self._log_threadsafe("Conexão autorizada com sucesso.")

    def _buscar(self) -> None:
        configuracao = self._salvar_configuracao(mostrar_mensagem=False)
        if not configuracao:
            return
        self._executar_em_thread("Buscando documentos e links...", self._tarefa_buscar)

    def _tarefa_buscar(self) -> None:
        servico = RoboEmailService(self.configuracao, log=self._log_threadsafe)
        resultado = servico.processar()
        self.after(0, lambda: self._mostrar_resultado(resultado, "Busca concluída"))

    def _baixar_links_autorizados(self) -> None:
        configuracao = self._salvar_configuracao(mostrar_mensagem=False)
        if not configuracao:
            return
        self._executar_em_thread(
            "Verificando links autorizados...", self._tarefa_baixar_links_autorizados
        )

    def _tarefa_baixar_links_autorizados(self) -> None:
        servico = RoboEmailService(self.configuracao, log=self._log_threadsafe)
        resultado = servico.processar_links_autorizados()
        self.after(
            0,
            lambda: self._mostrar_resultado(
                resultado, "Processamento dos links concluído"
            ),
        )

    def _mostrar_resultado(
        self, resultado: ResultadoProcessamento, titulo: str = "Processamento concluído"
    ) -> None:
        self.var_emails.set(str(resultado.mensagens_processadas))
        self.var_arquivos.set(str(resultado.arquivos_baixados))
        self.var_duplicados.set(str(resultado.arquivos_duplicados))
        self.var_links.set(str(resultado.links_baixados))
        self.var_pendentes.set(str(resultado.links_pendentes))
        self.var_erros.set(str(resultado.erros + resultado.links_bloqueados))
        possui_pendencias = bool(
            resultado.erros or resultado.links_pendentes or resultado.links_bloqueados
        )
        self.var_status.set("Concluído com pendências" if possui_pendencias else "Concluído")
        mensagem = (
            f"{titulo}.\n\n"
            f"Mensagens encontradas: {resultado.mensagens_encontradas}\n"
            f"Mensagens processadas: {resultado.mensagens_processadas}\n"
            f"Já processadas: {resultado.mensagens_ja_processadas}\n"
            f"Arquivos baixados: {resultado.arquivos_baixados}\n"
            f"Duplicados ignorados: {resultado.arquivos_duplicados}\n"
            f"Links encontrados: {resultado.links_encontrados}\n"
            f"Links baixados: {resultado.links_baixados}\n"
            f"Links pendentes: {resultado.links_pendentes}\n"
            f"Links bloqueados: {resultado.links_bloqueados}\n"
            f"Empresas não identificadas: {resultado.empresas_nao_identificadas}\n"
            f"Erros: {resultado.erros}"
        )
        messagebox.showinfo("Robô FiscalPro", mensagem)
        self._atualizar_tabela_links()
        self._atualizar_painel_mensal()

    def _abrir_links(self) -> None:
        if self.janela_links and self.janela_links.winfo_exists():
            self.janela_links.lift()
            self._atualizar_tabela_links()
            return

        janela = Toplevel(self)
        janela.title("Robô FiscalPro — Links recebidos")
        dimensionar_janela(janela, 1420, 720, 900, 500)
        self.janela_links = janela

        topo = ttk.Frame(janela, padding=10)
        topo.pack(fill=X)
        ttk.Label(
            topo,
            text="Links não são considerados seguros apenas porque chegaram por e-mail. Confira remetente, empresa e domínio.",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=LEFT)

        quadro = ttk.Frame(janela, padding=(10, 0, 10, 10))
        quadro.pack(fill=BOTH, expand=True)
        colunas = ("id", "data", "empresa", "dominio", "status", "assunto", "detalhe")
        tabela = ttk.Treeview(quadro, columns=colunas, show="headings", selectmode="browse")
        self.tabela_links = tabela
        larguras = {
            "id": 55,
            "data": 120,
            "empresa": 175,
            "dominio": 210,
            "status": 175,
            "assunto": 300,
            "detalhe": 430,
        }
        titulos = {
            "id": "ID",
            "data": "Data",
            "empresa": "Empresa",
            "dominio": "Domínio",
            "status": "Situação",
            "assunto": "Assunto",
            "detalhe": "Detalhes / motivo",
        }
        for coluna in colunas:
            tabela.heading(coluna, text=titulos[coluna])
            tabela.column(coluna, width=larguras[coluna], anchor="w")

        barra = ttk.Scrollbar(quadro, orient="vertical", command=tabela.yview)
        tabela.configure(yscrollcommand=barra.set)
        tabela.pack(side=LEFT, fill=BOTH, expand=True)
        barra.pack(side=RIGHT, fill=Y)

        acoes = ttk.Frame(janela, padding=(10, 0, 10, 10))
        acoes.pack(fill=X)
        ttk.Button(acoes, text="Atualizar", command=self._atualizar_tabela_links).pack(
            side=LEFT, padx=(0, 5)
        )
        ttk.Button(acoes, text="Autorizar domínio", command=self._autorizar_dominio_selecionado).pack(
            side=LEFT, padx=5
        )
        ttk.Button(acoes, text="Baixar selecionado", command=self._baixar_link_selecionado).pack(
            side=LEFT, padx=5
        )
        ttk.Button(acoes, text="Abrir manualmente", command=self._abrir_link_selecionado).pack(
            side=LEFT, padx=5
        )
        ttk.Button(acoes, text="Abrir e capturar download", command=self._abrir_e_capturar_download).pack(
            side=LEFT, padx=5
        )
        ttk.Button(acoes, text="Abrir arquivo salvo", command=self._abrir_arquivo_link).pack(
            side=LEFT, padx=5
        )
        ttk.Button(acoes, text="Fechar", command=janela.destroy).pack(side=RIGHT)

        self._atualizar_tabela_links()

    def _atualizar_tabela_links(self) -> None:
        tabela = self.tabela_links
        if not tabela or not tabela.winfo_exists():
            return
        for item in tabela.get_children():
            tabela.delete(item)

        repositorio = RoboEmailRepositorio()
        for linha in repositorio.listar_links(limite=1000):
            data = self._formatar_data(linha["data_email"])
            tabela.insert(
                "",
                END,
                iid=str(linha["id"]),
                values=(
                    linha["id"],
                    data,
                    linha["empresa"] or "Não identificada",
                    linha["dominio"],
                    linha["status"],
                    linha["assunto"] or "(sem assunto)",
                    linha["detalhe"] or "",
                ),
            )

    def _link_selecionado(self):
        tabela = self.tabela_links
        if not tabela:
            return None
        selecao = tabela.selection()
        if not selecao:
            messagebox.showwarning("Robô FiscalPro", "Selecione um link na lista.")
            return None
        return RoboEmailRepositorio().obter_link(int(selecao[0]))

    def _autorizar_dominio_selecionado(self) -> None:
        linha = self._link_selecionado()
        if not linha:
            return
        dominio = linha["dominio"]
        confirmar = messagebox.askyesno(
            "Autorizar domínio",
            f"Autorizar exatamente o domínio abaixo?\n\n{dominio}\n\n"
            "Faça isso somente após confirmar que ele pertence à contabilidade ou ao órgão oficial.",
        )
        if not confirmar:
            return

        dominios = ConfiguracaoRoboEmail.normalizar_dominios(
            [*self.configuracao.dominios_confiaveis, dominio]
        )
        self.configuracao.dominios_confiaveis = dominios
        self.configuracao.salvar()
        self.var_dominios.set(", ".join(dominios))
        self._log(f"Domínio autorizado pela usuária: {dominio}")
        messagebox.showinfo(
            "Robô FiscalPro",
            "Domínio autorizado. Clique em “Baixar links autorizados” ou baixe o item selecionado.",
        )

    def _baixar_link_selecionado(self) -> None:
        linha = self._link_selecionado()
        if not linha:
            return
        configuracao = self._salvar_configuracao(mostrar_mensagem=False)
        if not configuracao:
            return
        link_id = int(linha["id"])

        def tarefa() -> None:
            servico = RoboEmailService(configuracao, log=self._log_threadsafe)
            resultado = servico.baixar_link_por_id(link_id)
            self.after(
                0,
                lambda: self._mostrar_resultado(
                    resultado, "Download do link selecionado concluído"
                ),
            )

        self._executar_em_thread("Baixando link selecionado...", tarefa)

    def _abrir_e_capturar_download(self) -> None:
        linha = self._link_selecionado()
        if not linha:
            return
        configuracao = self._salvar_configuracao(mostrar_mensagem=False)
        if not configuracao:
            return

        confirmar = messagebox.askyesno(
            "Download assistido",
            "O portal será aberto no navegador. Faça o login, confira a guia e baixe o arquivo.\n\n"
            "Depois volte ao FiscalPro para selecionar o PDF, ZIP ou XML que foi baixado.\n\n"
            f"Domínio: {linha['dominio']}\nRemetente: {linha['remetente']}",
        )
        if not confirmar:
            return

        webbrowser.open(linha["url"], new=2)
        messagebox.showinfo(
            "Download assistido",
            "No navegador, faça o login no portal e clique para baixar a guia.\n\n"
            "Quando o download terminar, volte aqui e clique em OK para localizar o arquivo.",
        )
        arquivo = filedialog.askopenfilename(
            title="Selecione a guia baixada do portal",
            initialdir=str(Path.home() / "Downloads"),
            filetypes=[
                ("Documentos fiscais", "*.pdf *.zip *.xml"),
                ("PDF", "*.pdf"),
                ("ZIP", "*.zip"),
                ("XML", "*.xml"),
            ],
        )
        if not arquivo:
            self._log("Download assistido cancelado: nenhum arquivo selecionado.")
            return

        link_id = int(linha["id"])

        def tarefa() -> None:
            servico = RoboEmailService(configuracao, log=self._log_threadsafe)
            resultado = servico.importar_arquivo_link(link_id, arquivo)
            self.after(
                0,
                lambda: self._mostrar_resultado(
                    resultado, "Documento do portal arquivado"
                ),
            )

        self._executar_em_thread("Arquivando documento baixado do portal...", tarefa)

    def _abrir_link_selecionado(self) -> None:
        linha = self._link_selecionado()
        if not linha:
            return
        confirmar = messagebox.askyesno(
            "Abrir link manualmente",
            f"Abrir o link no navegador?\n\nDomínio: {linha['dominio']}\n"
            f"Remetente: {linha['remetente']}\n\n"
            "Confira o endereço no navegador antes de informar senha ou certificado.",
        )
        if confirmar:
            webbrowser.open(linha["url"], new=2)

    def _abrir_arquivo_link(self) -> None:
        linha = self._link_selecionado()
        if not linha:
            return
        caminho = Path(linha["caminho_salvo"] or "")
        if not caminho.is_file():
            messagebox.showwarning("Robô FiscalPro", "Este link ainda não possui arquivo salvo.")
            return
        self._abrir_caminho(caminho)

    def _abrir_painel_mensal(self) -> None:
        if self.janela_painel_mensal and self.janela_painel_mensal.winfo_exists():
            self.janela_painel_mensal.lift()
            self._atualizar_painel_mensal()
            return

        agora = datetime.now()
        janela = Toplevel(self)
        janela.title("Robô FiscalPro — Controle mensal de documentos e pendências")
        dimensionar_janela(janela, 1500, 800, 1000, 540)
        self.janela_painel_mensal = janela

        filtros = ttk.LabelFrame(janela, text="Período", padding=10)
        filtros.pack(fill=X, padx=10, pady=(10, 6))
        meses = (
            "01 — Janeiro", "02 — Fevereiro", "03 — Março", "04 — Abril",
            "05 — Maio", "06 — Junho", "07 — Julho", "08 — Agosto",
            "09 — Setembro", "10 — Outubro", "11 — Novembro", "12 — Dezembro",
        )
        self.var_mes_painel = StringVar(value=meses[agora.month - 1])
        self.var_ano_painel = IntVar(value=agora.year)
        self.var_resumo_painel = StringVar(value="Aguardando atualização")

        ttk.Label(filtros, text="Mês:").pack(side=LEFT)
        combo_mes = ttk.Combobox(
            filtros,
            values=meses,
            textvariable=self.var_mes_painel,
            state="readonly",
            width=18,
        )
        combo_mes.pack(side=LEFT, padx=(5, 14))
        ttk.Label(filtros, text="Ano:").pack(side=LEFT)
        ttk.Spinbox(
            filtros, from_=2000, to=2100, width=8, textvariable=self.var_ano_painel
        ).pack(side=LEFT, padx=(5, 14))
        ttk.Button(filtros, text="🔄 Atualizar painel", command=self._atualizar_painel_mensal).pack(
            side=LEFT, padx=4
        )
        ttk.Button(filtros, text="📥 Processar Gmail", command=self._buscar).pack(
            side=LEFT, padx=4
        )
        ttk.Label(
            filtros,
            textvariable=self.var_resumo_painel,
            font=("Segoe UI", 10, "bold"),
        ).pack(side=RIGHT)

        quadro = ttk.Frame(janela, padding=(10, 0, 10, 8))
        quadro.pack(fill=BOTH, expand=True)
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)

        colunas = (
            "empresa", "emails", "xml", "guias", "pdf", "zip", "outros",
            "esperados", "faltantes", "pendentes", "duplicados", "erros",
            "conferencia", "ultimo", "situacao",
        )
        tabela = ttk.Treeview(
            quadro, columns=colunas, show="headings", selectmode="browse"
        )
        self.tabela_painel_mensal = tabela
        titulos = {
            "empresa": "Empresa",
            "emails": "E-mails",
            "xml": "XML",
            "guias": "Guias",
            "pdf": "PDF",
            "zip": "ZIP",
            "outros": "Outros",
            "esperados": "Esperados",
            "faltantes": "Faltando",
            "pendentes": "Links pendentes",
            "duplicados": "Duplicados",
            "erros": "Erros",
            "conferencia": "Conferência",
            "ultimo": "Último processamento",
            "situacao": "Situação",
        }
        larguras = {
            "empresa": 205, "emails": 70, "xml": 65, "guias": 65,
            "pdf": 60, "zip": 60, "outros": 65, "esperados": 145,
            "faltantes": 145, "pendentes": 105, "duplicados": 80,
            "erros": 60, "conferencia": 145, "ultimo": 145, "situacao": 175,
        }
        for coluna in colunas:
            tabela.heading(coluna, text=titulos[coluna])
            ancora = "w" if coluna in {
                "empresa", "esperados", "faltantes", "conferencia", "ultimo", "situacao"
            } else "center"
            tabela.column(coluna, width=larguras[coluna], anchor=ancora, stretch=True)

        tabela.tag_configure("recebido", background="#E2F0D9")
        tabela.tag_configure("revisar", background="#FFF2CC")
        tabela.tag_configure("vazio", background="#FCE4D6")
        tabela.bind("<Double-1>", lambda _evento: self._abrir_pasta_empresa_painel())

        barra_y = ttk.Scrollbar(quadro, orient="vertical", command=tabela.yview)
        barra_x = ttk.Scrollbar(quadro, orient="horizontal", command=tabela.xview)
        tabela.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        tabela.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")

        acoes = ttk.Frame(janela, padding=(10, 0, 10, 10))
        acoes.pack(fill=X)
        ttk.Button(
            acoes, text="📁 Abrir pasta da empresa", command=self._abrir_pasta_empresa_painel
        ).pack(side=LEFT, padx=(0, 5))
        ttk.Button(
            acoes,
            text="📄 Ver documentos salvos",
            command=self._abrir_documentos_salvos,
        ).pack(side=LEFT, padx=5)
        ttk.Button(
            acoes, text="🛡️ Ver links pendentes", command=self._abrir_links
        ).pack(side=LEFT, padx=5)
        ttk.Button(
            acoes,
            text="⚙️ Documentos esperados",
            command=self._abrir_documentos_esperados,
        ).pack(side=LEFT, padx=5)
        ttk.Button(
            acoes, text="📤 Exportar relatório CSV", command=self._exportar_painel_mensal
        ).pack(side=LEFT, padx=5)
        ttk.Button(
            acoes,
            text="🔎 Revisar não identificados",
            command=self._abrir_revisar_periodo,
        ).pack(side=LEFT, padx=5)
        ttk.Button(acoes, text="Fechar", command=janela.destroy).pack(side=RIGHT)

        self._atualizar_painel_mensal()

    def _abrir_documentos_esperados(self) -> None:
        """Configura o checklist mensal sem expor opções técnicas do robô."""

        janela = Toplevel(self)
        janela.title("Robô FiscalPro — Documentos esperados por empresa")
        dimensionar_janela(janela, 1220, 650, 860, 460)
        janela.transient(self.winfo_toplevel())

        topo = ttk.Frame(janela, padding=(14, 12, 14, 8))
        topo.pack(fill=X)
        ttk.Label(
            topo,
            text="Marque os documentos mensais e informe o CNPJ de cada empresa.",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            topo,
            text=(
                "O CNPJ permite conferir se XMLs e guias pertencem à empresa correta. "
                "O painel só apontará como faltante aquilo que estiver marcado."
            ),
            wraplength=800,
        ).pack(anchor="w", pady=(4, 0))

        grade = ttk.LabelFrame(janela, text="Checklist mensal", padding=10)
        grade.pack(fill=BOTH, expand=True, padx=14, pady=(0, 10))
        grade.columnconfigure(0, weight=1)

        ttk.Label(grade, text="Empresa", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(4, 14), pady=(0, 7)
        )
        ttk.Label(grade, text="CNPJ", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=1, padx=10, pady=(0, 7)
        )
        for coluna, categoria in enumerate(CATEGORIAS_DOCUMENTOS_ESPERADOS, start=2):
            ttk.Label(grade, text=categoria, font=("Segoe UI", 9, "bold")).grid(
                row=0, column=coluna, padx=12, pady=(0, 7)
            )

        atuais = ConfiguracaoRoboEmail.normalizar_documentos_esperados(
            self.configuracao.documentos_esperados
        )
        cnpjs_atuais = ConfiguracaoRoboEmail.normalizar_cnpjs_empresas(
            self.configuracao.cnpjs_empresas
        )
        variaveis: dict[tuple[str, str], BooleanVar] = {}
        variaveis_cnpj: dict[str, StringVar] = {}
        for linha, empresa in enumerate(EMPRESAS_POR_ALIAS.values(), start=1):
            ttk.Label(grade, text=empresa).grid(
                row=linha, column=0, sticky="w", padx=(4, 14), pady=7
            )
            variavel_cnpj = StringVar(value=cnpjs_atuais.get(empresa, ""))
            variaveis_cnpj[empresa] = variavel_cnpj
            ttk.Entry(grade, textvariable=variavel_cnpj, width=20).grid(
                row=linha, column=1, padx=10, pady=7
            )
            for coluna, categoria in enumerate(CATEGORIAS_DOCUMENTOS_ESPERADOS, start=2):
                variavel = BooleanVar(value=categoria in atuais.get(empresa, []))
                variaveis[(empresa, categoria)] = variavel
                ttk.Checkbutton(grade, variable=variavel).grid(
                    row=linha, column=coluna, padx=18, pady=7
                )

        rodape = ttk.Frame(janela, padding=(14, 0, 14, 12))
        rodape.pack(fill=X)

        def salvar() -> None:
            novos = {
                empresa: [
                    categoria
                    for categoria in CATEGORIAS_DOCUMENTOS_ESPERADOS
                    if variaveis[(empresa, categoria)].get()
                ]
                for empresa in EMPRESAS_POR_ALIAS.values()
            }
            try:
                configuracao = self._configuracao_da_tela()
                configuracao.documentos_esperados = novos
                configuracao.cnpjs_empresas = {
                    empresa: variaveis_cnpj[empresa].get().strip()
                    for empresa in EMPRESAS_POR_ALIAS.values()
                }
                erros = configuracao.validar()
                erros_cnpj = [erro for erro in erros if erro.startswith("CNPJ inválido")]
                if erros_cnpj:
                    raise ValueError("\n".join(erros_cnpj))
                configuracao.salvar()
                self.configuracao = configuracao
                janela.destroy()
                self._atualizar_painel_mensal()
                messagebox.showinfo(
                    "Robô FiscalPro",
                    "Checklist mensal salvo. O painel foi atualizado.",
                )
            except (OSError, ValueError) as erro:
                messagebox.showerror(
                    "Robô FiscalPro",
                    f"Não foi possível salvar o checklist: {erro}",
                )

        ttk.Button(rodape, text="💾 Salvar checklist", command=salvar).pack(side=LEFT)
        ttk.Button(rodape, text="Cancelar", command=janela.destroy).pack(side=RIGHT)

    def _periodo_painel_mensal(self) -> tuple[int, int] | None:
        if not self.var_mes_painel or not self.var_ano_painel:
            return None
        try:
            mes = int(self.var_mes_painel.get().split("—", 1)[0].strip())
            ano = int(self.var_ano_painel.get())
            if not 1 <= mes <= 12 or not 2000 <= ano <= 2100:
                raise ValueError
            return ano, mes
        except (ValueError, TypeError):
            messagebox.showerror("Robô FiscalPro", "Informe um mês e um ano válidos.")
            return None

    def _atualizar_painel_mensal(self) -> None:
        tabela = self.tabela_painel_mensal
        if not tabela or not tabela.winfo_exists():
            return
        periodo = self._periodo_painel_mensal()
        if not periodo:
            return
        ano, mes = periodo
        try:
            configuracao = self._configuracao_da_tela()
            servico = PainelMensalService(configuracao)
            self.resumos_painel = servico.gerar(ano, mes)
            total_revisar = len(servico.listar_revisar(ano, mes))
        except (OSError, ValueError) as erro:
            messagebox.showerror("Robô FiscalPro", f"Não foi possível montar o painel: {erro}")
            return

        for item in tabela.get_children():
            tabela.delete(item)

        total_documentos = 0
        total_pendencias = 0
        for indice, resumo in enumerate(self.resumos_painel, start=1):
            total_documentos += resumo.total_documentos
            total_pendencias += resumo.total_pendencias
            if resumo.situacao == "Completo":
                tag = "recebido"
            elif resumo.situacao == "Sem documentos":
                tag = "vazio"
            else:
                tag = "revisar"
            tabela.insert(
                "",
                END,
                iid=str(indice),
                tags=(tag,),
                values=(
                    resumo.empresa,
                    resumo.emails,
                    resumo.xml,
                    resumo.guias,
                    resumo.pdf,
                    resumo.zip,
                    resumo.outros,
                    resumo.esperados_texto,
                    resumo.faltantes_texto,
                    resumo.links_pendentes,
                    resumo.duplicados,
                    resumo.erros,
                    resumo.conferencia_texto,
                    resumo.ultimo_processamento,
                    resumo.situacao,
                ),
            )

        if self.var_resumo_painel:
            self.var_resumo_painel.set(
                f"{total_documentos} documento(s) | {total_pendencias} pendência(s) | "
                f"{total_revisar} para revisar"
            )

    def _resumo_painel_selecionado(self) -> ResumoEmpresaMensal | None:
        tabela = self.tabela_painel_mensal
        if not tabela:
            return None
        selecao = tabela.selection()
        if not selecao:
            messagebox.showwarning("Robô FiscalPro", "Selecione uma empresa no painel.")
            return None
        indice = int(selecao[0]) - 1
        if not 0 <= indice < len(self.resumos_painel):
            return None
        return self.resumos_painel[indice]

    def _abrir_pasta_empresa_painel(self) -> None:
        resumo = self._resumo_painel_selecionado()
        periodo = self._periodo_painel_mensal()
        if not resumo or not periodo:
            return
        ano, mes = periodo
        servico = PainelMensalService(self._configuracao_da_tela())
        pasta = servico.pasta_empresa(resumo.empresa, ano, mes)
        pasta.mkdir(parents=True, exist_ok=True)
        self._abrir_caminho(pasta)

    def _abrir_documentos_salvos(self) -> None:
        resumo = self._resumo_painel_selecionado()
        periodo = self._periodo_painel_mensal()
        if not resumo or not periodo:
            return
        ano, mes = periodo
        try:
            servico = PainelMensalService(self._configuracao_da_tela())
            documentos = servico.listar_documentos(resumo.empresa, ano, mes)
        except (OSError, ValueError) as erro:
            messagebox.showerror(
                "Robô FiscalPro",
                f"Não foi possível listar os documentos salvos: {erro}",
            )
            return

        if not documentos:
            messagebox.showinfo(
                "Robô FiscalPro",
                f"Nenhum documento foi localizado para {resumo.empresa} em {mes:02d}/{ano:04d}.",
            )
            return

        self.documentos_painel = documentos
        janela = Toplevel(self)
        janela.title(
            f"Robô FiscalPro — Documentos salvos — {resumo.empresa} — {mes:02d}/{ano:04d}"
        )
        dimensionar_janela(janela, 1540, 780, 980, 520)
        janela.transient(self.winfo_toplevel())

        topo = ttk.Frame(janela, padding=(12, 10, 12, 6))
        topo.pack(fill=X)
        ttk.Label(
            topo,
            text=(
                f"{len(documentos)} documento(s) encontrado(s). "
                "O nome original e o caminho exato ficam registrados abaixo."
            ),
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        quadro = ttk.Frame(janela, padding=(12, 0, 12, 8))
        quadro.pack(fill=BOTH, expand=True)
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)

        colunas = (
            "categoria", "original", "salvo", "documento", "cnpj",
            "competencia", "valor", "vencimento", "conferencia", "alertas",
            "origem", "data", "caminho",
        )
        tabela = ttk.Treeview(
            quadro,
            columns=colunas,
            show="headings",
            selectmode="browse",
        )
        titulos = {
            "categoria": "Tipo",
            "original": "Nome original",
            "salvo": "Nome organizado",
            "documento": "Documento / tributo",
            "cnpj": "CNPJ localizado",
            "competencia": "Competência",
            "valor": "Valor",
            "vencimento": "Vencimento",
            "conferencia": "Conferência",
            "alertas": "Alertas",
            "origem": "Origem",
            "data": "Salvo em",
            "caminho": "Caminho completo",
        }
        larguras = {
            "categoria": 80, "original": 210, "salvo": 280,
            "documento": 175, "cnpj": 135, "competencia": 90,
            "valor": 105, "vencimento": 95, "conferencia": 145,
            "alertas": 290, "origem": 115, "data": 125, "caminho": 430,
        }
        for coluna in colunas:
            tabela.heading(coluna, text=titulos[coluna])
            tabela.column(
                coluna,
                width=larguras[coluna],
                anchor="center" if coluna in {
                    "categoria", "cnpj", "competencia", "valor", "vencimento", "conferencia"
                } else "w",
                stretch=True,
            )

        for indice, documento in enumerate(documentos):
            conferencia = documento.status_conferencia.upper()
            if conferencia == "CONFERIDO":
                tag = "conferido"
            elif conferencia == "VENCIMENTO PASSADO":
                tag = "vencido"
            elif conferencia in {"REVISAR", "NÃO ANALISADO"} or documento.status.upper() == "REVISAR":
                tag = "revisar"
            else:
                tag = "normal"
            cnpj = documento.cnpj
            if len(cnpj) == 14:
                cnpj = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
            descricao_documento = documento.resumo_leitura or " — ".join(
                item for item in (documento.documento_tipo, documento.tributo) if item
            )
            tabela.insert(
                "",
                END,
                iid=str(indice),
                tags=(tag,),
                values=(
                    documento.categoria,
                    documento.nome_original,
                    documento.nome_salvo,
                    descricao_documento or "—",
                    cnpj or "—",
                    documento.competencia_documento or "—",
                    documento.valor_texto,
                    documento.vencimento_texto,
                    documento.status_conferencia,
                    documento.alertas or "—",
                    documento.origem,
                    documento.salvo_em,
                    str(documento.caminho),
                ),
            )
        tabela.tag_configure("conferido", background="#E2F0D9")
        tabela.tag_configure("revisar", background="#FFF2CC")
        tabela.tag_configure("vencido", background="#FCE4D6")
        tabela.bind(
            "<Double-1>",
            lambda _evento: abrir_selecionado(abrir_pasta=False),
        )

        barra_y = ttk.Scrollbar(quadro, orient="vertical", command=tabela.yview)
        barra_x = ttk.Scrollbar(quadro, orient="horizontal", command=tabela.xview)
        tabela.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        tabela.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")

        def documento_selecionado() -> DocumentoMensal | None:
            selecao = tabela.selection()
            if not selecao:
                messagebox.showwarning(
                    "Robô FiscalPro",
                    "Selecione um documento.",
                    parent=janela,
                )
                return None
            indice = int(selecao[0])
            if not 0 <= indice < len(documentos):
                return None
            return documentos[indice]

        def abrir_selecionado(*, abrir_pasta: bool) -> None:
            documento = documento_selecionado()
            if not documento:
                return
            caminho = documento.pasta if abrir_pasta else documento.caminho
            if not caminho.exists():
                messagebox.showwarning(
                    "Robô FiscalPro",
                    f"O caminho registrado não foi encontrado:\n\n{caminho}",
                    parent=janela,
                )
                return
            self._abrir_caminho(caminho)

        def ver_conferencia() -> None:
            documento = documento_selecionado()
            if not documento:
                return
            cnpj = documento.cnpj or "—"
            if len(cnpj) == 14:
                cnpj = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
            texto = (
                f"Documento: {documento.nome_salvo}\n\n"
                f"Leitura: {documento.resumo_leitura or '—'}\n"
                f"CNPJ: {cnpj}\n"
                f"Competência: {documento.competencia_documento or '—'}\n"
                f"Valor: {documento.valor_texto}\n"
                f"Vencimento: {documento.vencimento_texto}\n"
                f"Fonte da leitura: {documento.fonte_leitura or '—'}\n"
                f"Conferência: {documento.status_conferencia}\n\n"
                f"Alertas:\n{documento.alertas or 'Nenhum alerta.'}"
            )
            messagebox.showinfo("Conferência inteligente", texto, parent=janela)

        def reanalisar() -> None:
            try:
                resultado = servico.reanalisar_documentos(resumo.empresa, ano, mes)
            except (OSError, ValueError) as erro:
                messagebox.showerror(
                    "Robô FiscalPro",
                    f"Não foi possível analisar os documentos: {erro}",
                    parent=janela,
                )
                return
            messagebox.showinfo(
                "Robô FiscalPro",
                "Leitura concluída.\n\n"
                f"Analisados: {resultado['analisados']}\n"
                f"Conferidos: {resultado['conferidos']}\n"
                f"Revisar: {resultado['revisar']}\n"
                f"Vencimento passado: {resultado['vencidos']}\n"
                f"Erros: {resultado['erros']}",
                parent=janela,
            )
            selecao_painel = (
                self.tabela_painel_mensal.selection()
                if self.tabela_painel_mensal
                else ()
            )
            janela.destroy()
            self._atualizar_painel_mensal()
            if selecao_painel and self.tabela_painel_mensal:
                self.tabela_painel_mensal.selection_set(selecao_painel[0])
                self.tabela_painel_mensal.focus(selecao_painel[0])
            self._abrir_documentos_salvos()

        rodape = ttk.Frame(janela, padding=(12, 0, 12, 10))
        rodape.pack(fill=X)
        ttk.Button(
            rodape,
            text="📄 Abrir documento",
            command=lambda: abrir_selecionado(abrir_pasta=False),
        ).pack(side=LEFT, padx=(0, 5))
        ttk.Button(
            rodape,
            text="📁 Abrir local do arquivo",
            command=lambda: abrir_selecionado(abrir_pasta=True),
        ).pack(side=LEFT, padx=5)
        ttk.Button(
            rodape,
            text="🔎 Ver conferência",
            command=ver_conferencia,
        ).pack(side=LEFT, padx=5)
        ttk.Button(
            rodape,
            text="🔄 Analisar documentos",
            command=reanalisar,
        ).pack(side=LEFT, padx=5)
        ttk.Button(rodape, text="Fechar", command=janela.destroy).pack(side=RIGHT)

    def _abrir_revisar_atual(self) -> None:
        agora = datetime.now()
        try:
            servico = PainelMensalService(self._configuracao_da_tela())
            pasta = servico.pasta_revisar(agora.year, agora.month)
            pasta.mkdir(parents=True, exist_ok=True)
            self._abrir_caminho(pasta)
        except (OSError, ValueError) as erro:
            messagebox.showerror(
                "Robô FiscalPro",
                f"Não foi possível abrir a pasta de revisão: {erro}",
            )

    def _abrir_revisar_periodo(self) -> None:
        periodo = self._periodo_painel_mensal()
        if not periodo:
            return
        ano, mes = periodo
        try:
            servico = PainelMensalService(self._configuracao_da_tela())
            pasta = servico.pasta_revisar(ano, mes)
            pasta.mkdir(parents=True, exist_ok=True)
            self._abrir_caminho(pasta)
        except (OSError, ValueError) as erro:
            messagebox.showerror(
                "Robô FiscalPro",
                f"Não foi possível abrir a pasta de revisão: {erro}",
            )

    def _exportar_painel_mensal(self) -> None:
        periodo = self._periodo_painel_mensal()
        if not periodo:
            return
        ano, mes = periodo
        destino = filedialog.asksaveasfilename(
            title="Salvar relatório mensal do Robô FiscalPro",
            defaultextension=".csv",
            initialfile=f"Robo_FiscalPro_Painel_{ano:04d}_{mes:02d}.csv",
            filetypes=[("Arquivo CSV", "*.csv")],
        )
        if not destino:
            return
        try:
            servico = PainelMensalService(self._configuracao_da_tela())
            caminho = servico.exportar_csv(destino, ano, mes, self.resumos_painel)
            messagebox.showinfo(
                "Robô FiscalPro",
                f"Relatório exportado com sucesso.\n\n{caminho}",
            )
        except (OSError, ValueError) as erro:
            messagebox.showerror("Robô FiscalPro", f"Não foi possível exportar: {erro}")

    def _executar_em_thread(self, status: str, tarefa) -> None:
        if self.em_execucao:
            messagebox.showwarning("Robô FiscalPro", "Já existe uma operação em andamento.")
            return
        self.em_execucao = True
        self._alterar_botoes(False)
        self.var_status.set(status)
        self._log(status)

        def executar() -> None:
            try:
                tarefa()
            except Exception as erro:
                mensagem_erro = str(erro)
                self.after(0, lambda: self.var_status.set("Erro"))
                self._log_threadsafe(f"ERRO: {mensagem_erro}")
                self.after(
                    0,
                    lambda texto=mensagem_erro: messagebox.showerror(
                        "Robô FiscalPro", texto
                    ),
                )
            finally:
                self.after(0, self._finalizar_thread)

        threading.Thread(target=executar, daemon=True).start()

    def _finalizar_thread(self) -> None:
        self.em_execucao = False
        self._alterar_botoes(True)

    def _alterar_botoes(self, habilitar: bool) -> None:
        estado = "normal" if habilitar else "disabled"
        self.btn_salvar.configure(state=estado)
        self.btn_conectar.configure(state=estado)
        self.btn_buscar.configure(state=estado)
        self.btn_baixar_links.configure(state=estado)
        self.btn_painel_mensal.configure(state=estado)

    def _log_threadsafe(self, texto: str) -> None:
        self.after(0, lambda: self._log(texto))

    def _log(self, texto: str) -> None:
        horario = datetime.now().strftime("%H:%M:%S")
        self.txt_log.insert(END, f"[{horario}] {texto}\n")
        self.txt_log.see(END)

    def _ampliar_relatorio(self) -> None:
        janela = Toplevel(self)
        janela.title("FiscalPro — Relatório completo do Robô Fiscal")
        dimensionar_janela(janela, 1180, 760, 760, 500)

        quadro = ttk.Frame(janela, padding=10)
        quadro.pack(fill=BOTH, expand=True)
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)

        texto = Text(quadro, wrap="none")
        barra_y = ttk.Scrollbar(quadro, orient="vertical", command=texto.yview)
        barra_x = ttk.Scrollbar(quadro, orient="horizontal", command=texto.xview)
        texto.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        texto.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        texto.insert("1.0", self.txt_log.get("1.0", END))
        texto.configure(state="disabled")

    def _abrir_pasta(self) -> None:
        pasta = Path(self.var_destino.get().strip()).expanduser()
        pasta.mkdir(parents=True, exist_ok=True)
        self._abrir_caminho(pasta)

    def _abrir_instrucoes(self) -> None:
        if not INSTRUCOES_PATH.exists():
            messagebox.showwarning("Robô FiscalPro", "Arquivo de instruções não encontrado.")
            return
        self._abrir_caminho(INSTRUCOES_PATH)

    @staticmethod
    def _abrir_caminho(caminho: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(caminho))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(caminho)])
            else:
                subprocess.Popen(["xdg-open", str(caminho)])
        except OSError as erro:
            messagebox.showerror("Robô FiscalPro", f"Não foi possível abrir: {erro}")

    @staticmethod
    def _formatar_data(valor: str) -> str:
        try:
            return datetime.fromisoformat(valor).strftime("%d/%m/%Y %H:%M")
        except (TypeError, ValueError):
            return valor or ""
