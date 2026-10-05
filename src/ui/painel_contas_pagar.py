"""Painel Contas a Pagar integrado ao FiscalPro.

Sprint 16.2.2 — relatórios semanais de sábado a sexta-feira.
"""

from __future__ import annotations

import os
import subprocess
import threading
import unicodedata
import webbrowser
from datetime import date, datetime
from pathlib import Path
from tkinter import (
    BOTH, END, LEFT, RIGHT, X, BooleanVar, Frame, Label, Listbox, StringVar, Text, Toplevel,
)
from tkinter import filedialog, messagebox, simpledialog, ttk

from src.financeiro.servico import ContasPagarServico
from src.financeiro.agenda_faturas import (
    STATUS_AGUARDANDO, STATUS_BAIXADA, STATUS_LANCADA, STATUS_PAGA,
    TIPOS_FATURA,
)
from src.ui.estilos import (
    COR_ALERTA,
    COR_BORDA,
    COR_CARD,
    COR_DESTAQUE,
    COR_ERRO,
    COR_FUNDO,
    COR_PRIMARIA,
    COR_SUCESSO,
    COR_TEXTO,
    COR_TEXTO_SUAVE,
)
from src.ui.layout_responsivo import dimensionar_janela
from src.ui.seletor_data import SeletorDataPopup


_TECLAS_NAVEGACAO_COMBO = {
    "Up", "Down", "Left", "Right", "Return", "Tab", "Escape",
    "Home", "End", "Prior", "Next", "Shift_L", "Shift_R",
    "Control_L", "Control_R", "Alt_L", "Alt_R",
}


def _normalizar_busca_combo(texto: object) -> str:
    """Normaliza texto para busca por prefixo, ignorando acentos e caixa."""

    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(letra for letra in valor if not unicodedata.combining(letra))
    return " ".join(valor.casefold().split())


def filtrar_opcoes_por_inicio(opcoes, texto: object) -> list[str]:
    """Retorna somente opções que começam com o texto informado."""

    termo = _normalizar_busca_combo(texto)
    valores = [str(opcao) for opcao in opcoes or ()]
    if not termo:
        return valores
    return [
        opcao for opcao in valores
        if _normalizar_busca_combo(opcao).startswith(termo)
    ]


class PainelContasPagar(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.servico = ContasPagarServico()
        self.var_empresa = StringVar(value="Todas")
        self.var_status = StringVar(value="Todos")
        self.var_competencia = StringVar(value="Todas")
        self.var_busca = StringVar(value="")
        self.var_agenda_resumo = StringVar(value="🔔 Agenda de faturas: carregando...")
        self.var_resumo = {
            "total": StringVar(value="R$ 0,00"),
            "pago": StringVar(value="R$ 0,00"),
            "a_vencer": StringVar(value="R$ 0,00"),
            "vencido": StringVar(value="R$ 0,00"),
            "proximos": StringVar(value="R$ 0,00"),
        }
        self._montar()
        self.atualizar()

    def _montar(self) -> None:
        cabecalho = Frame(
            self, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA
        )
        cabecalho.pack(fill=X, padx=10, pady=(7, 6))
        Frame(cabecalho, bg=COR_DESTAQUE, height=3).pack(fill=X)
        conteudo = Frame(cabecalho, bg=COR_CARD, padx=12, pady=7)
        conteudo.pack(fill=X)
        Label(
            conteudo,
            text="Contas a Pagar",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        Label(
            conteudo,
            text=(
                "Controle as empresas, anexos das contas e próximos compromissos. "
                "Os documentos podem ser guardados dentro do FiscalPro e reunidos em um "
                "pacote mensal para a contabilidade."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        filtros = ttk.LabelFrame(self, text="Filtros e ações", padding=8, style="Card.TLabelframe")
        filtros.pack(fill=X, padx=10, pady=(0, 6))
        filtros.columnconfigure(7, weight=1)

        ttk.Label(filtros, text="Empresa:").grid(row=0, column=0, sticky="w")
        self.cbo_empresa = ttk.Combobox(
            filtros, textvariable=self.var_empresa, state="readonly", width=24
        )
        self.cbo_empresa.grid(row=0, column=1, sticky="w", padx=(5, 12))
        self.cbo_empresa.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())

        ttk.Label(filtros, text="Status:").grid(row=0, column=2, sticky="w")
        self.cbo_status = ttk.Combobox(
            filtros,
            textvariable=self.var_status,
            values=("Todos", "A VENCER", "VENCIDO", "PAGO"),
            state="readonly",
            width=12,
        )
        self.cbo_status.grid(row=0, column=3, sticky="w", padx=(5, 12))
        self.cbo_status.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())

        ttk.Label(filtros, text="Competência:").grid(row=0, column=4, sticky="w")
        self.cbo_competencia = ttk.Combobox(
            filtros, textvariable=self.var_competencia, state="readonly", width=12
        )
        self.cbo_competencia.grid(row=0, column=5, sticky="w", padx=(5, 12))
        self.cbo_competencia.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())

        ttk.Label(filtros, text="Buscar:").grid(row=0, column=6, sticky="w")
        entrada_busca = ttk.Entry(filtros, textvariable=self.var_busca)
        entrada_busca.grid(row=0, column=7, sticky="ew", padx=(5, 8))
        entrada_busca.bind("<Return>", lambda _e: self.atualizar())
        ttk.Button(filtros, text="Pesquisar", command=self.atualizar).grid(
            row=0, column=8, sticky="ew"
        )

        botoes = ttk.Frame(filtros, style="Card.TFrame")
        botoes.grid(row=1, column=0, columnspan=9, sticky="ew", pady=(8, 0))
        for coluna in range(7):
            botoes.columnconfigure(coluna, weight=1)
        ttk.Button(
            botoes, text="＋ Nova conta", command=self._nova_conta, style="Primary.TButton"
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(botoes, text="Editar", command=self._editar_conta).grid(
            row=0, column=1, sticky="ew", padx=3
        )
        ttk.Button(botoes, text="Dar baixa hoje", command=self._marcar_paga).grid(
            row=0, column=2, sticky="ew", padx=3
        )
        ttk.Button(
            botoes,
            text="Dar baixa no vencimento",
            command=self._marcar_paga_no_vencimento,
        ).grid(row=0, column=3, sticky="ew", padx=3)
        ttk.Button(botoes, text="Reabrir", command=self._reabrir).grid(
            row=0, column=4, sticky="ew", padx=3
        )
        ttk.Button(botoes, text="📎 Anexar documento", command=self._anexar_documento).grid(
            row=0, column=5, sticky="ew", padx=3
        )
        ttk.Button(botoes, text="Abrir documento", command=self._abrir_documento).grid(
            row=0, column=6, sticky="ew", padx=(3, 0)
        )
        ttk.Button(botoes, text="Importar Excel", command=self._importar_excel).grid(
            row=1, column=0, sticky="ew", padx=(0, 3), pady=(5, 0)
        )
        ttk.Button(botoes, text="Exportar Excel", command=self._exportar_excel).grid(
            row=1, column=1, sticky="ew", padx=3, pady=(5, 0)
        )
        ttk.Button(
            botoes,
            text="Relatório semanal",
            command=self._relatorio_semanal,
            style="Accent.TButton",
        ).grid(row=1, column=2, sticky="ew", padx=3, pady=(5, 0))
        ttk.Button(
            botoes,
            text="📚 Contabilidade",
            command=self._abrir_central_contabilidade,
            style="Accent.TButton",
        ).grid(row=1, column=3, sticky="ew", padx=3, pady=(5, 0))
        ttk.Button(botoes, text="Atualizar", command=self.atualizar).grid(
            row=1, column=4, sticky="ew", padx=3, pady=(5, 0)
        )
        ttk.Button(
            botoes, text="Excluir", command=self._excluir, style="Danger.TButton"
        ).grid(row=1, column=5, sticky="ew", padx=(3, 0), pady=(5, 0))

        agenda_barra = Frame(
            self, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA
        )
        agenda_barra.pack(fill=X, padx=10, pady=(0, 6))
        Label(
            agenda_barra,
            textvariable=self.var_agenda_resumo,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=7,
        ).pack(side=LEFT)
        ttk.Button(
            agenda_barra,
            text="📅 Abrir Agenda de Faturas",
            command=self._abrir_agenda,
            style="Accent.TButton",
        ).pack(side=RIGHT, padx=8, pady=5)

        cards = ttk.Frame(self, style="Page.TFrame")
        cards.pack(fill=X, padx=10, pady=(0, 6))
        for coluna in range(5):
            cards.columnconfigure(coluna, weight=1, uniform="financeiro")
        self._card(cards, 0, "Total programado", self.var_resumo["total"], COR_PRIMARIA)
        self._card(cards, 1, "Pago", self.var_resumo["pago"], COR_SUCESSO)
        self._card(cards, 2, "A vencer", self.var_resumo["a_vencer"], COR_DESTAQUE)
        self._card(cards, 3, "Vencido", self.var_resumo["vencido"], COR_ERRO)
        self._card(cards, 4, "Próximos 7 dias", self.var_resumo["proximos"], COR_ALERTA)

        tabela_frame = ttk.LabelFrame(
            self, text="Lançamentos", padding=7, style="Card.TLabelframe"
        )
        tabela_frame.pack(fill=BOTH, expand=True, padx=10, pady=(0, 8))
        tabela_frame.rowconfigure(0, weight=1)
        tabela_frame.columnconfigure(0, weight=1)

        colunas = (
            "id", "vencimento", "empresa", "fornecedor", "descricao", "categoria",
            "valor", "pagamento", "status", "documento", "anexo", "origem",
        )
        self.tabela = ttk.Treeview(
            tabela_frame, columns=colunas, show="headings", selectmode="browse", height=16
        )
        titulos = {
            "id": "ID", "vencimento": "Vencimento", "empresa": "Empresa",
            "fornecedor": "Fornecedor", "descricao": "Descrição",
            "categoria": "Categoria", "valor": "Valor", "pagamento": "Data da baixa",
            "status": "Status", "documento": "Documento", "anexo": "Anexo", "origem": "Origem",
        }
        larguras = {
            "id": 55, "vencimento": 95, "empresa": 160, "fornecedor": 185,
            "descricao": 180, "categoria": 145, "valor": 105, "pagamento": 105,
            "status": 90, "documento": 135, "anexo": 75, "origem": 95,
        }
        for coluna in colunas:
            self.tabela.heading(coluna, text=titulos[coluna])
            self.tabela.column(
                coluna,
                width=larguras[coluna],
                minwidth=50,
                anchor="e" if coluna == "valor" else "center" if coluna in {
                    "id", "vencimento", "pagamento", "status", "anexo", "origem"
                } else "w",
            )
        self.tabela.tag_configure("VENCIDO", foreground=COR_ERRO)
        self.tabela.tag_configure("PAGO", foreground=COR_SUCESSO)
        self.tabela.tag_configure("A VENCER", foreground=COR_TEXTO)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        barra_y = ttk.Scrollbar(tabela_frame, orient="vertical", command=self.tabela.yview)
        barra_x = ttk.Scrollbar(tabela_frame, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        self.tabela.bind("<Double-1>", lambda _e: self._editar_conta())

    @staticmethod
    def _card(master, coluna: int, titulo: str, variavel: StringVar, cor: str) -> None:
        quadro = Frame(
            master,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=10,
            pady=8,
        )
        quadro.grid(row=0, column=coluna, sticky="nsew", padx=(0 if coluna == 0 else 4, 0))
        Frame(quadro, bg=cor, height=3).pack(fill=X, pady=(0, 5))
        Label(quadro, text=titulo, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).pack()
        Label(
            quadro,
            textvariable=variavel,
            bg=COR_CARD,
            fg=cor,
            font=("Segoe UI", 12, "bold"),
        ).pack(pady=(2, 0))

    def _filtros(self) -> tuple[str, str, str, str]:
        empresa = "" if self.var_empresa.get() == "Todas" else self.var_empresa.get()
        status = "" if self.var_status.get() == "Todos" else self.var_status.get()
        comp = self.var_competencia.get()
        competencia = ""
        if comp != "Todas" and "/" in comp:
            mes, ano = comp.split("/", 1)
            competencia = f"{ano}-{mes}"
        return empresa, status, competencia, self.var_busca.get().strip()

    def atualizar(self) -> None:
        empresas = self.servico.repositorio.listar_empresas()
        self.cbo_empresa.configure(values=("Todas", *empresas))
        if self.var_empresa.get() not in ("Todas", *empresas):
            self.var_empresa.set("Todas")

        competencias = [
            "Todas",
            *self.servico.opcoes_competencia(
                adicionais=self.servico.repositorio.listar_competencias()
            ),
        ]
        self.cbo_competencia.configure(values=competencias)
        if self.var_competencia.get() not in competencias:
            self.var_competencia.set("Todas")

        empresa, status, competencia, busca = self._filtros()
        self.servico.atualizar_status()
        contas = self.servico.repositorio.listar_contas(
            empresa=empresa, status=status, competencia=competencia, busca=busca
        )
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        for conta in contas:
            self.tabela.insert(
                "",
                END,
                iid=str(conta["id"]),
                values=(
                    conta["id"], self.servico.data_br(conta["vencimento"]),
                    conta["empresa"], conta["fornecedor"], conta["descricao"],
                    conta["categoria"], self.servico.valor_br(conta["valor"]),
                    self.servico.data_br(conta["data_pagamento"]), conta["status"],
                    conta["numero_documento"],
                    "📎 SIM" if str(conta["caminho_documento"] or "").strip() and Path(str(conta["caminho_documento"])).is_file() else "— NÃO",
                    conta["origem"],
                ),
                tags=(conta["status"],),
            )

        resumo = self.servico.resumo(empresa=empresa, competencia=competencia)
        self.var_resumo["total"].set(self.servico.valor_br(resumo["total"]))
        self.var_resumo["pago"].set(self.servico.valor_br(resumo["pago"]))
        self.var_resumo["a_vencer"].set(self.servico.valor_br(resumo["a_vencer"]))
        self.var_resumo["vencido"].set(self.servico.valor_br(resumo["vencido"]))
        self.var_resumo["proximos"].set(self.servico.valor_br(resumo["proximos_7_dias"]))

        agenda = self.servico.agenda.resumo(empresa=empresa)
        self.var_agenda_resumo.set(
            "🔔 Agenda de faturas: "
            f"{agenda['para_baixar']} para baixar • "
            f"{agenda['nao_lancadas']} não lançadas • "
            f"{agenda['vencendo_7_dias']} vencendo em 7 dias • "
            f"{agenda['concluidas_mes']} concluídas no mês"
        )

    def _abrir_agenda(self) -> None:
        JanelaAgendaFaturas(self, self.servico, ao_atualizar=self.atualizar)

    def _selecionado(self):
        selecao = self.tabela.selection()
        if not selecao:
            messagebox.showwarning("Contas a Pagar", "Selecione uma conta na tabela.", parent=self)
            return None
        return self.servico.repositorio.obter_conta(int(selecao[0]))

    def _nova_conta(self, prefill: dict[str, object] | None = None, fila_id: int | None = None) -> None:
        JanelaContaPagar(self, self.servico, dados=prefill, fila_id=fila_id, ao_salvar=self.atualizar)

    def _editar_conta(self) -> None:
        conta = self._selecionado()
        if conta:
            JanelaContaPagar(
                self, self.servico, conta=conta, conta_id=int(conta["id"]), ao_salvar=self.atualizar
            )

    def _marcar_paga(self) -> None:
        conta = self._selecionado()
        if not conta:
            return
        self.servico.dar_baixa_conta(int(conta["id"]))
        self.atualizar()

    def _marcar_paga_no_vencimento(self) -> None:
        conta = self._selecionado()
        if not conta:
            return
        vencimento = str(conta["vencimento"] or "").strip()
        if not vencimento:
            messagebox.showwarning(
                "Contas a Pagar",
                "A conta selecionada não possui data de vencimento.",
                parent=self,
            )
            return
        self.servico.dar_baixa_conta(
            int(conta["id"]), data_pagamento=vencimento
        )
        self.atualizar()

    def _reabrir(self) -> None:
        conta = self._selecionado()
        if not conta:
            return
        dados = dict(conta)
        dados["data_pagamento"] = ""
        self.servico.salvar_conta(dados, conta_id=int(conta["id"]), permitir_duplicidade=True)
        self.atualizar()

    def _excluir(self) -> None:
        conta = self._selecionado()
        if not conta:
            return
        if not messagebox.askyesno(
            "Excluir conta",
            f"Excluir a conta de {conta['fornecedor']} no valor de {self.servico.valor_br(conta['valor'])}?",
            parent=self,
        ):
            return
        self.servico.repositorio.excluir_conta(int(conta["id"]))
        self.atualizar()

    def _anexar_documento(self) -> None:
        conta = self._selecionado()
        if not conta:
            return
        try:
            comp_conta = str(conta["competencia"] or "").strip()
            comp_br = self.servico.competencia_br(comp_conta) if comp_conta else date.today().strftime("%m/%Y")
            pasta_inicial = str(self.servico.pasta_download_scans_preferida(comp_br))
        except Exception:
            pasta_inicial = str(Path.home() / "Downloads")
        arquivo = filedialog.askopenfilename(
            title="Anexar documento da conta",
            initialdir=pasta_inicial,
            filetypes=[
                ("PDF e imagens", "*.pdf *.jpg *.jpeg *.png *.webp"),
                ("PDF", "*.pdf"),
                ("Imagens", "*.jpg *.jpeg *.png *.webp"),
            ],
            parent=self,
        )
        if not arquivo:
            return
        try:
            caminho = self.servico.anexar_documento(int(conta["id"]), arquivo)
        except Exception as erro:
            messagebox.showerror("Anexar documento", str(erro), parent=self)
            return
        self.atualizar()
        messagebox.showinfo(
            "Documento anexado",
            "Documento copiado para a pasta interna do FiscalPro.\n\n" + str(caminho),
            parent=self,
        )

    def _abrir_documento(self) -> None:
        conta = self._selecionado()
        if not conta:
            return
        caminho = str(conta["caminho_documento"] or "")
        if not caminho or not Path(caminho).exists():
            messagebox.showwarning(
                "Documento", "A conta não possui um arquivo válido vinculado.", parent=self
            )
            return
        self._abrir_caminho(caminho)

    @staticmethod
    def _abrir_caminho(caminho: str) -> None:
        if os.name == "nt":
            os.startfile(caminho)  # type: ignore[attr-defined]
        elif os.name == "posix":
            subprocess.Popen(["xdg-open", caminho])

    def _importar_excel(self) -> None:
        arquivo = filedialog.askopenfilename(
            title="Importar contas da planilha",
            filetypes=[("Planilha Excel", "*.xlsx")],
            parent=self,
        )
        if not arquivo:
            return
        try:
            resultado = self.servico.importar_excel(arquivo)
        except Exception as erro:
            messagebox.showerror("Importar Excel", str(erro), parent=self)
            return
        self.atualizar()
        messagebox.showinfo(
            "Importação concluída",
            "\n".join(
                (
                    f"Linhas lidas: {resultado['lidas']}",
                    f"Contas importadas: {resultado['importadas']}",
                    f"Duplicidades ignoradas: {resultado['duplicadas']}",
                    f"Linhas ignoradas: {resultado['ignoradas']}",
                )
            ),
            parent=self,
        )

    def _exportar_excel(self) -> None:
        destino = filedialog.asksaveasfilename(
            title="Exportar Contas a Pagar",
            defaultextension=".xlsx",
            initialfile=f"CONTAS_A_PAGAR_FISCALPRO_{date.today():%Y%m%d}.xlsx",
            filetypes=[("Planilha Excel", "*.xlsx")],
            parent=self,
        )
        if not destino:
            return
        try:
            caminho = self.servico.exportar_excel(destino)
        except Exception as erro:
            messagebox.showerror("Exportar Excel", str(erro), parent=self)
            return
        messagebox.showinfo("Exportação concluída", f"Planilha salva em:\n{caminho}", parent=self)

    def _abrir_fila(self) -> None:
        JanelaFilaFinanceira(self, self.servico, ao_importar=self.atualizar)

    def _relatorio_semanal(self) -> None:
        JanelaRelatorioVencimentos(self, self.servico)

    def _abrir_central_contabilidade(self) -> None:
        competencia = self.var_competencia.get()
        if competencia == "Todas":
            competencia = date.today().strftime("%m/%Y")
        JanelaCentralContabilidade(
            self, self.servico, competencia_inicial=competencia
        )

    def _pacote_contabilidade(self) -> None:
        competencia = self.var_competencia.get()
        if competencia == "Todas":
            competencia = date.today().strftime("%m/%Y")
        JanelaPacoteContabilidade(self, self.servico, competencia_inicial=competencia)

    def _baixar_documentos_whatsapp(self) -> None:
        competencia = self.var_competencia.get()
        if competencia == "Todas":
            competencia = date.today().strftime("%m/%Y")
        JanelaDownloadDocumentosAdobe(self, self.servico, competencia_inicial=competencia)

    def _organizar_scans_baixados(self) -> None:
        competencia = self.var_competencia.get()
        if competencia == "Todas":
            competencia = date.today().strftime("%m/%Y")
        JanelaOrganizarScans(
            self, self.servico, competencia_inicial=competencia, ao_vincular=self.atualizar
        )

    def _relatorio_contas_pagas_mes(self) -> None:
        competencia = self.var_competencia.get()
        if competencia == "Todas":
            competencia = date.today().strftime("%m/%Y")
        JanelaRelatorioContasPagas(
            self, self.servico, competencia_inicial=competencia
        )

    def _cadastro_fornecedores_cnpj(self) -> None:
        JanelaFornecedoresCNPJ(self, self.servico)


class JanelaCentralContabilidade:
    """Centraliza ferramentas contábeis fora da grade operacional de lançamentos."""

    def __init__(
        self,
        master: PainelContasPagar,
        servico: ContasPagarServico,
        competencia_inicial: str,
    ):
        self.master = master
        self.servico = servico
        self.competencia_inicial = competencia_inicial
        self.janela = Toplevel(master)
        self.janela.title("Contabilidade")
        self.janela.transient(master.winfo_toplevel())
        dimensionar_janela(
            self.janela, 820, 520, 720, 460, maximizar_em_tela_baixa=False
        )
        self._montar()

    def _montar(self) -> None:
        principal = ttk.Frame(self.janela, padding=12, style="Page.TFrame")
        principal.pack(fill=BOTH, expand=True)

        cab = Frame(
            principal, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA
        )
        cab.pack(fill=X, pady=(0, 10))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        Label(
            cab,
            text="📚 Central da Contabilidade",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 14, "bold"),
            padx=12,
            pady=8,
        ).pack(anchor="w")
        Label(
            cab,
            text=(
                "Documentos, relatórios mensais e cadastro de CNPJ ficam reunidos "
                "aqui para manter o Contas a Pagar mais limpo."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
            padx=12,
            pady=3,
            justify="left",
            wraplength=760,
        ).pack(anchor="w")

        grade = ttk.Frame(principal, style="Page.TFrame")
        grade.pack(fill=BOTH, expand=True)
        grade.columnconfigure(0, weight=1, uniform="contab")
        grade.columnconfigure(1, weight=1, uniform="contab")

        self._ferramenta(
            grade, 0, 0,
            "⬇ Baixar scans do WhatsApp",
            "Cole os links do Adobe e baixe o lote para a pasta escolhida.",
            self.master._baixar_documentos_whatsapp,
        )
        self._ferramenta(
            grade, 0, 1,
            "🗂 Organizar scans baixados",
            "Abra e vincule scans já baixados às contas quando precisar.",
            self.master._organizar_scans_baixados,
        )
        self._ferramenta(
            grade, 1, 0,
            "📦 Pacote para contabilidade",
            "Reúna documentos do mês por empresa e gere o pacote mensal.",
            self.master._pacote_contabilidade,
        )
        self._ferramenta(
            grade, 1, 1,
            "💰 Contas pagas do mês",
            "Gere o Excel mensal pela data da baixa, com fornecedor e CNPJ.",
            self.master._relatorio_contas_pagas_mes,
        )
        self._ferramenta(
            grade, 2, 0,
            "🏢 Fornecedores / CNPJ",
            "Cadastre ou altere o CNPJ usado nos relatórios da contabilidade.",
            self.master._cadastro_fornecedores_cnpj,
        )

        rodape = ttk.Frame(principal, style="Page.TFrame")
        rodape.pack(fill=X, pady=(10, 0))
        ttk.Button(rodape, text="Fechar", command=self.janela.destroy).pack(side=RIGHT)

    @staticmethod
    def _ferramenta(parent, linha: int, coluna: int, titulo: str, descricao: str, comando) -> None:
        box = Frame(
            parent,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=12,
            pady=10,
        )
        box.grid(row=linha, column=coluna, sticky="nsew", padx=5, pady=5)
        Label(
            box,
            text=titulo,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        Label(
            box,
            text=descricao,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=330,
        ).pack(anchor="w", pady=(4, 9))
        ttk.Button(box, text="Abrir", command=comando, style="Accent.TButton").pack(
            anchor="e"
        )


class JanelaFornecedoresCNPJ:
    """Cadastro, CNPJ e manutenção dos fornecedores usados no Financeiro."""

    def __init__(self, master, servico: ContasPagarServico):
        self.master = master
        self.servico = servico
        self._mapa: dict[str, object] = {}
        self.janela = Toplevel(master)
        self.janela.title("Fornecedores / CNPJ")
        self.janela.transient(master.winfo_toplevel())
        self.janela.grab_set()
        dimensionar_janela(self.janela, 820, 620, 700, 520, maximizar_em_tela_baixa=False)
        self.var_busca = StringVar(value="")
        self.var_nome = StringVar(value="")
        self.var_cnpj = StringVar(value="")
        self.var_status = StringVar(value="Selecione um fornecedor para consultar ou adicionar CNPJs.")
        self._montar()
        self._carregar()

    @staticmethod
    def _formatar_cnpj(valor: object) -> str:
        digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
        if len(digitos) == 14:
            return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
        return str(valor or "").strip()

    @classmethod
    def _formatar_lista_cnpjs(cls, valor: object) -> str:
        partes = [parte.strip() for parte in str(valor or "").split("|") if parte.strip()]
        return " | ".join(cls._formatar_cnpj(parte) for parte in partes)

    def _montar(self) -> None:
        principal = ttk.Frame(self.janela, padding=12, style="Page.TFrame")
        principal.pack(fill=BOTH, expand=True)

        cab = Frame(principal, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)
        cab.pack(fill=X, pady=(0, 8))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        Label(
            cab, text="🏢 Cadastro de fornecedores", bg=COR_CARD, fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"), padx=12, pady=7,
        ).pack(anchor="w")
        Label(
            cab,
            text=(
                "Cadastre um ou vários CNPJs, corrija o nome e oculte fornecedores que não usa mais. "
                "Alterações de nome são sincronizadas com os lançamentos existentes."
            ),
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 9),
            padx=12, pady=3, justify="left", wraplength=760,
        ).pack(anchor="w")

        busca = ttk.LabelFrame(principal, text="Localizar fornecedor", padding=8, style="Card.TLabelframe")
        busca.pack(fill=X, pady=(0, 8))
        busca.columnconfigure(1, weight=1)
        ttk.Label(busca, text="Buscar:").grid(row=0, column=0, sticky="w")
        ent = ttk.Entry(busca, textvariable=self.var_busca)
        ent.grid(row=0, column=1, sticky="ew", padx=(7, 7))
        ent.bind("<KeyRelease>", lambda _e: self._carregar())
        ent.bind("<Return>", self._buscar_fornecedor_enter)
        ent.bind("<KP_Enter>", self._buscar_fornecedor_enter)
        ttk.Button(busca, text="Pesquisar", command=self._carregar).grid(row=0, column=2)

        tabela_box = ttk.LabelFrame(principal, text="Fornecedores cadastrados", padding=8, style="Card.TLabelframe")
        tabela_box.pack(fill=BOTH, expand=True, pady=(0, 8))
        tabela_box.rowconfigure(0, weight=1)
        tabela_box.columnconfigure(0, weight=1)
        self.tabela = ttk.Treeview(tabela_box, columns=("fornecedor", "cnpj"), show="headings", selectmode="browse")
        self.tabela.heading("fornecedor", text="Fornecedor")
        self.tabela.heading("cnpj", text="CNPJ(s)")
        self.tabela.column("fornecedor", width=410, anchor="w")
        self.tabela.column("cnpj", width=300, anchor="w")
        scroll = ttk.Scrollbar(tabela_box, orient="vertical", command=self.tabela.yview)
        self.tabela.configure(yscrollcommand=scroll.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tabela.bind("<<TreeviewSelect>>", lambda _e: self._selecionar())
        self.tabela.bind("<Double-1>", lambda _e: self._focar_cnpj())

        edicao = ttk.LabelFrame(principal, text="Dados do fornecedor", padding=10, style="Card.TLabelframe")
        edicao.pack(fill=X, pady=(0, 8))
        edicao.columnconfigure(1, weight=1)
        ttk.Label(edicao, text="Fornecedor:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(edicao, textvariable=self.var_nome, state="readonly").grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(edicao, text="Adicionar CNPJ:").grid(row=1, column=0, sticky="w", pady=3)
        self.ent_cnpj = ttk.Entry(edicao, textvariable=self.var_cnpj)
        self.ent_cnpj.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.ent_cnpj.bind("<Return>", lambda _e: self._salvar())
        ttk.Label(
            edicao, text="Pode digitar com ou sem pontos, barra e hífen.",
            foreground=COR_TEXTO_SUAVE, font=("Segoe UI", 8),
        ).grid(row=2, column=1, sticky="w", padx=(8, 0))

        rodape = ttk.Frame(principal, style="Page.TFrame")
        rodape.pack(fill=X)
        Label(
            rodape, textvariable=self.var_status, bg=COR_FUNDO, fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
        ).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(rodape, text="Fechar", command=self.janela.destroy).pack(side=RIGHT)
        ttk.Button(
            rodape, text="🗑 Excluir", command=self._excluir_fornecedor, style="Danger.TButton"
        ).pack(side=RIGHT, padx=(0, 8))
        ttk.Button(
            rodape, text="✏️ Renomear", command=self._renomear_fornecedor
        ).pack(side=RIGHT, padx=(0, 8))
        ttk.Button(
            rodape, text="＋ Adicionar CNPJ", command=self._salvar, style="Primary.TButton"
        ).pack(side=RIGHT, padx=(0, 8))

    def _carregar(self) -> None:
        try:
            linhas = self.servico.repositorio.listar_fornecedores_cnpj(self.var_busca.get())
        except Exception as erro:
            self.var_status.set(str(erro))
            return
        selecionado_nome = self.var_nome.get().strip()
        self._mapa.clear()
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        sem_cnpj = 0
        item_selecionar = None
        for linha in linhas:
            nome = str(linha["nome"] or "")
            cnpj = str(linha["cnpj"] or "")
            quantidade_cnpjs = (
                int(linha["quantidade_cnpjs"] or 0)
                if "quantidade_cnpjs" in linha.keys()
                else (1 if cnpj else 0)
            )
            if quantidade_cnpjs == 0:
                sem_cnpj += 1
            iid = str(linha["id"])
            self._mapa[iid] = linha
            self.tabela.insert("", END, iid=iid, values=(nome, self._formatar_lista_cnpjs(cnpj)))
            if selecionado_nome and nome.casefold() == selecionado_nome.casefold():
                item_selecionar = iid
        self.var_status.set(f"{len(linhas)} fornecedor(es) • {sem_cnpj} sem CNPJ")
        if item_selecionar:
            self.tabela.selection_set(item_selecionar)
            self.tabela.see(item_selecionar)

    def _buscar_fornecedor_enter(self, _event=None):
        """Executa a busca pelo teclado e leva a usuária ao resultado sem exigir clique."""
        self._carregar()
        itens = self.tabela.get_children()
        if not itens:
            self.var_status.set("Nenhum fornecedor encontrado para essa busca.")
            return "break"

        primeiro = itens[0]
        self.tabela.selection_set(primeiro)
        self.tabela.focus(primeiro)
        self.tabela.see(primeiro)
        self._selecionar()

        # Quando a busca chegou a um único fornecedor, já deixa o CNPJ pronto para digitar.
        if len(itens) == 1:
            self.ent_cnpj.focus_set()
            self.ent_cnpj.selection_range(0, END)
        else:
            # Havendo mais de um resultado, deixa a lista com foco para escolher pelas setas.
            self.tabela.focus_set()
        return "break"

    def _selecionar(self) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            return
        linha = self._mapa.get(selecao[0])
        if linha is None:
            return
        self.var_nome.set(str(linha["nome"] or ""))
        quantidade = (
            int(linha["quantidade_cnpjs"] or 0)
            if "quantidade_cnpjs" in linha.keys()
            else 0
        )
        if quantidade == 1:
            self.var_cnpj.set(self._formatar_lista_cnpjs(linha["cnpj"]))
        else:
            self.var_cnpj.set("")
            if quantidade > 1:
                self.var_status.set(
                    f"{self.var_nome.get()} possui {quantidade} CNPJs. Digite outro CNPJ para adicionar."
                )

    def _focar_cnpj(self) -> None:
        self._selecionar()
        self.ent_cnpj.focus_set()
        self.ent_cnpj.selection_range(0, END)

    def _atualizar_painel_principal(self) -> None:
        atualizar = getattr(self.master, "atualizar", None)
        if callable(atualizar):
            try:
                atualizar()
            except Exception:
                pass

    def _renomear_fornecedor(self) -> None:
        nome_atual = self.var_nome.get().strip()
        if not nome_atual:
            messagebox.showwarning(
                "Fornecedor", "Selecione um fornecedor para renomear.", parent=self.janela
            )
            return
        novo_nome = simpledialog.askstring(
            "Renomear fornecedor",
            "Novo nome do fornecedor:",
            initialvalue=nome_atual,
            parent=self.janela,
        )
        if novo_nome is None:
            return
        novo_nome = " ".join(novo_nome.strip().split())
        if not novo_nome:
            messagebox.showwarning(
                "Renomear fornecedor", "Informe o novo nome.", parent=self.janela
            )
            return
        if novo_nome == nome_atual:
            return
        try:
            resultado = self.servico.repositorio.renomear_fornecedor(nome_atual, novo_nome)
        except Exception as erro:
            messagebox.showerror("Renomear fornecedor", str(erro), parent=self.janela)
            return
        nome_final = str(resultado.get("nome") or novo_nome)
        self.var_busca.set(nome_final)
        self.var_nome.set(nome_final)
        self._carregar()
        self._atualizar_painel_principal()
        alterados = int(resultado.get("contas", 0))
        agenda = int(resultado.get("agenda", 0))
        fila = int(resultado.get("fila", 0))
        detalhe = f"{alterados} conta(s), {agenda} agenda(s) e {fila} item(ns) da fila atualizados."
        if resultado.get("mesclado"):
            detalhe += "\n\nJá existia esse nome; os dois cadastros foram unidos com segurança."
        messagebox.showinfo(
            "Fornecedor renomeado",
            f"Fornecedor alterado para:\n{nome_final}\n\n{detalhe}",
            parent=self.janela,
        )

    def _excluir_fornecedor(self) -> None:
        nome = self.var_nome.get().strip()
        if not nome:
            messagebox.showwarning(
                "Fornecedor", "Selecione um fornecedor para excluir.", parent=self.janela
            )
            return
        try:
            uso = self.servico.repositorio.resumo_uso_fornecedor(nome)
        except Exception as erro:
            messagebox.showerror("Fornecedor", str(erro), parent=self.janela)
            return
        total = int(uso.get("total", 0))
        if total:
            pergunta = (
                f"{nome} ainda aparece em {uso.get('contas', 0)} conta(s), "
                f"{uso.get('agenda', 0)} agenda(s) e {uso.get('fila', 0)} item(ns) da fila.\n\n"
                "Para não apagar o histórico financeiro, ele será apenas OCULTADO do cadastro "
                "e das listas para novos lançamentos.\n\nContinuar?"
            )
        else:
            pergunta = (
                f"Excluir definitivamente o fornecedor abaixo?\n\n{nome}\n\n"
                "Ele não está sendo usado em contas, agendas ou fila financeira."
            )
        if not messagebox.askyesno("Excluir fornecedor", pergunta, parent=self.janela):
            return
        try:
            resultado = self.servico.repositorio.excluir_fornecedor(nome)
        except Exception as erro:
            messagebox.showerror("Excluir fornecedor", str(erro), parent=self.janela)
            return
        self.var_nome.set("")
        self.var_cnpj.set("")
        self.var_busca.set("")
        self._carregar()
        self._atualizar_painel_principal()
        if resultado.get("acao") == "ocultado":
            mensagem = "Fornecedor ocultado. O histórico das contas foi preservado."
        else:
            mensagem = "Fornecedor excluído do cadastro."
        messagebox.showinfo("Fornecedor", mensagem, parent=self.janela)

    def _salvar(self) -> None:
        nome = self.var_nome.get().strip()
        if not nome:
            messagebox.showwarning("Fornecedor / CNPJ", "Selecione um fornecedor.", parent=self.janela)
            return
        try:
            cnpj = self.servico.repositorio.salvar_cnpj_fornecedor(nome, self.var_cnpj.get())
        except Exception as erro:
            messagebox.showerror("Fornecedor / CNPJ", str(erro), parent=self.janela)
            return
        self.var_cnpj.set("")
        self.var_status.set(f"CNPJ {self._formatar_cnpj(cnpj)} adicionado para {nome}.")
        self._carregar()


class JanelaOrganizarScans:
    """Fila visual para identificar um scan e vinculá-lo ao lançamento correto."""

    EXTENSOES = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

    def __init__(
        self, master, servico: ContasPagarServico, *, competencia_inicial: str = "", ao_vincular=None
    ):
        self.master = master
        self.servico = servico
        self.ao_vincular = ao_vincular
        self._map_scans: dict[str, Path] = {}
        self._map_contas: dict[str, object] = {}

        self.janela = Toplevel(master)
        self.janela.title("Organizar scans baixados")
        self.janela.transient(master.winfo_toplevel())
        self.janela.grab_set()
        dimensionar_janela(self.janela, 1120, 700, 900, 590, maximizar_em_tela_baixa=True)

        competencias = list(self.servico.opcoes_competencia(
            adicionais=self.servico.repositorio.listar_competencias()
        ))
        padrao = competencia_inicial if competencia_inicial in competencias else date.today().strftime("%m/%Y")
        self.var_competencia = StringVar(value=padrao)
        self.var_busca = StringVar(value="")
        self.var_mostrar_vinculadas = BooleanVar(value=False)
        self.var_status = StringVar(value="Selecione um scan, abra para conferir e procure o Nº Documento da conta.")
        self.var_qtd_scans = StringVar(value="0 scan(s) aguardando vínculo")
        self.var_qtd_contas = StringVar(value="0 conta(s)")
        self._montar(competencias)
        self._atualizar_tudo()

    def _montar(self, competencias: list[str]) -> None:
        principal = ttk.Frame(self.janela, padding=12, style="Page.TFrame")
        principal.pack(fill=BOTH, expand=True)

        cab = Frame(principal, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)
        cab.pack(fill=X, pady=(0, 8))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        Label(
            cab, text="🗂 Organizar scans baixados", bg=COR_CARD, fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"), padx=12, pady=7
        ).pack(anchor="w")
        Label(
            cab,
            text=(
                "Aqui você não precisa descobrir o arquivo pelo nome do Adobe. Abra o Scan 01, "
                "veja o número do documento, pesquise a conta e clique em Vincular."
            ),
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 9),
            padx=12, pady=3, justify="left", wraplength=1020
        ).pack(anchor="w")

        filtros = ttk.LabelFrame(principal, text="Competência e busca", padding=8, style="Card.TLabelframe")
        filtros.pack(fill=X, pady=(0, 8))
        ttk.Label(filtros, text="Competência:").pack(side=LEFT)
        combo = ttk.Combobox(
            filtros, textvariable=self.var_competencia, values=competencias, state="readonly", width=13
        )
        combo.pack(side=LEFT, padx=(7, 16))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._atualizar_tudo())
        ttk.Label(filtros, text="Buscar conta / Nº documento:").pack(side=LEFT)
        self.ent_busca = ttk.Entry(filtros, textvariable=self.var_busca, width=34)
        self.ent_busca.pack(side=LEFT, fill=X, expand=True, padx=(7, 10))
        self.ent_busca.bind("<KeyRelease>", lambda _e: self._carregar_contas())
        ttk.Checkbutton(
            filtros, text="Mostrar contas já com anexo", variable=self.var_mostrar_vinculadas,
            command=self._carregar_contas
        ).pack(side=LEFT)

        area = ttk.Frame(principal, style="Page.TFrame")
        area.pack(fill=BOTH, expand=True)
        area.columnconfigure(0, weight=5, uniform="orgscan")
        area.columnconfigure(1, weight=8, uniform="orgscan")
        area.rowconfigure(0, weight=1)

        scans = ttk.LabelFrame(area, text="Scans baixados", padding=8, style="Card.TLabelframe")
        scans.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        scans.rowconfigure(1, weight=1)
        scans.columnconfigure(0, weight=1)
        ttk.Label(scans, textvariable=self.var_qtd_scans).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.tabela_scans = ttk.Treeview(
            scans, columns=("scan", "tipo", "hora", "tamanho"), show="headings", selectmode="browse", height=14
        )
        for col, titulo, largura, ancora in (
            ("scan", "Scan", 95, "center"), ("tipo", "Tipo", 65, "center"),
            ("hora", "Baixado em", 125, "center"), ("tamanho", "Tamanho", 85, "e")
        ):
            self.tabela_scans.heading(col, text=titulo)
            self.tabela_scans.column(col, width=largura, anchor=ancora, stretch=(col == "scan"))
        self.tabela_scans.grid(row=1, column=0, sticky="nsew")
        scroll_s = ttk.Scrollbar(scans, orient="vertical", command=self.tabela_scans.yview)
        scroll_s.grid(row=1, column=1, sticky="ns")
        self.tabela_scans.configure(yscrollcommand=scroll_s.set)
        self.tabela_scans.bind("<Double-1>", lambda _e: self._abrir_scan())
        ttk.Button(
            scans, text="👁 Abrir scan selecionado", command=self._abrir_scan, style="Primary.TButton"
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        contas = ttk.LabelFrame(area, text="Contas da competência", padding=8, style="Card.TLabelframe")
        contas.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        contas.rowconfigure(1, weight=1)
        contas.columnconfigure(0, weight=1)
        ttk.Label(contas, textvariable=self.var_qtd_contas).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.tabela_contas = ttk.Treeview(
            contas, columns=("doc", "fornecedor", "venc", "valor", "empresa", "anexo"),
            show="headings", selectmode="browse", height=14
        )
        configs = (
            ("doc", "Nº Documento", 125, "w"),
            ("fornecedor", "Fornecedor", 190, "w"),
            ("venc", "Vencimento", 95, "center"),
            ("valor", "Valor", 95, "e"),
            ("empresa", "Empresa", 155, "w"),
            ("anexo", "Anexo", 65, "center"),
        )
        for col, titulo, largura, ancora in configs:
            self.tabela_contas.heading(col, text=titulo)
            self.tabela_contas.column(col, width=largura, anchor=ancora)
        self.tabela_contas.grid(row=1, column=0, sticky="nsew")
        scroll_c = ttk.Scrollbar(contas, orient="vertical", command=self.tabela_contas.yview)
        scroll_c.grid(row=1, column=1, sticky="ns")
        self.tabela_contas.configure(yscrollcommand=scroll_c.set)
        self.tabela_contas.bind("<Return>", lambda _e: self._vincular())

        acao = ttk.Frame(principal, style="Page.TFrame")
        acao.pack(fill=X, pady=(8, 0))
        Label(
            acao, textvariable=self.var_status, bg=COR_CARD, fg=COR_TEXTO,
            font=("Segoe UI", 9, "bold"), padx=9, pady=7, anchor="w",
            highlightthickness=1, highlightbackground=COR_BORDA
        ).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(acao, text="Atualizar", command=self._atualizar_tudo).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(acao, text="Fechar", command=self.janela.destroy).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(
            acao, text="🔗 Vincular scan à conta", command=self._vincular, style="Primary.TButton"
        ).pack(side=RIGHT, padx=(8, 0))

    def _arquivos_recebidos(self) -> list[Path]:
        try:
            pasta = self.servico.pasta_documentos_recebidos(self.var_competencia.get())
        except Exception:
            return []
        if not pasta.is_dir():
            return []
        arquivos = [
            item for item in pasta.iterdir()
            if item.is_file() and item.suffix.casefold() in self.EXTENSOES
        ]
        return sorted(arquivos, key=lambda p: (p.stat().st_mtime, p.name.casefold()))

    @staticmethod
    def _tam_br(tamanho: int) -> str:
        if tamanho >= 1024 * 1024:
            return f"{tamanho / (1024*1024):.1f} MB"
        return f"{max(1, tamanho // 1024)} KB"

    def _carregar_scans(self) -> None:
        for item in self.tabela_scans.get_children():
            self.tabela_scans.delete(item)
        self._map_scans.clear()
        arquivos = self._arquivos_recebidos()
        for indice, arquivo in enumerate(arquivos, 1):
            iid = f"scan_{indice}"
            self._map_scans[iid] = arquivo
            try:
                mod = datetime.fromtimestamp(arquivo.stat().st_mtime).strftime("%d/%m %H:%M")
                tam = self._tam_br(arquivo.stat().st_size)
            except OSError:
                mod, tam = "", ""
            self.tabela_scans.insert(
                "", END, iid=iid, values=(f"SCAN {indice:02d}", arquivo.suffix.upper().lstrip("."), mod, tam)
            )
        self.var_qtd_scans.set(f"{len(arquivos)} scan(s) aguardando vínculo")
        if arquivos:
            primeiro = "scan_1"
            self.tabela_scans.selection_set(primeiro)
            self.tabela_scans.focus(primeiro)

    def _carregar_contas(self) -> None:
        for item in self.tabela_contas.get_children():
            self.tabela_contas.delete(item)
        self._map_contas.clear()
        try:
            contas = list(self.servico.contas_competencia(self.var_competencia.get()))
        except Exception:
            contas = []
        termo = _normalizar_busca_combo(self.var_busca.get())
        mostrar = self.var_mostrar_vinculadas.get()
        exibidas = []
        for conta in contas:
            caminho = str(conta["caminho_documento"] or "").strip()
            tem_anexo = bool(caminho and Path(caminho).is_file())
            if tem_anexo and not mostrar:
                continue
            alvo = " ".join((
                str(conta["id"] or ""), str(conta["numero_documento"] or ""),
                str(conta["fornecedor"] or ""), str(conta["descricao"] or ""),
                str(conta["empresa"] or ""),
            ))
            if termo and termo not in _normalizar_busca_combo(alvo):
                continue
            exibidas.append((conta, tem_anexo))

        exibidas.sort(key=lambda x: (str(x[0]["numero_documento"] or "").casefold(), str(x[0]["fornecedor"] or "").casefold()))
        for conta, tem_anexo in exibidas:
            iid = str(conta["id"])
            self._map_contas[iid] = conta
            numero = str(conta["numero_documento"] or "").strip() or f"SEM DOC • ID {conta['id']}"
            self.tabela_contas.insert(
                "", END, iid=iid, values=(
                    numero, conta["fornecedor"], self.servico.data_br(str(conta["vencimento"] or "")),
                    self.servico.valor_br(conta["valor"]), conta["empresa"], "SIM" if tem_anexo else "NÃO"
                )
            )
        self.var_qtd_contas.set(f"{len(exibidas)} conta(s) disponível(is) para vínculo")
        if len(exibidas) == 1:
            iid = str(exibidas[0][0]["id"])
            self.tabela_contas.selection_set(iid)
            self.tabela_contas.focus(iid)

    def _atualizar_tudo(self) -> None:
        self._carregar_scans()
        self._carregar_contas()

    def _scan_selecionado(self) -> Path | None:
        selecao = self.tabela_scans.selection()
        return self._map_scans.get(selecao[0]) if selecao else None

    def _conta_selecionada(self):
        selecao = self.tabela_contas.selection()
        return self._map_contas.get(selecao[0]) if selecao else None

    def _abrir_scan(self) -> None:
        arquivo = self._scan_selecionado()
        if not arquivo:
            messagebox.showwarning("Organizar scans", "Selecione um scan primeiro.", parent=self.janela)
            return
        if not arquivo.is_file():
            messagebox.showwarning("Organizar scans", "Esse arquivo não existe mais. Clique em Atualizar.", parent=self.janela)
            return
        PainelContasPagar._abrir_caminho(str(arquivo))
        self.var_status.set("Scan aberto. Veja o Nº Documento e digite-o no campo de busca acima.")
        self.ent_busca.focus_set()
        self.ent_busca.selection_range(0, END)

    def _vincular(self) -> None:
        arquivo = self._scan_selecionado()
        conta = self._conta_selecionada()
        if not arquivo:
            messagebox.showwarning("Organizar scans", "Selecione o scan que deseja vincular.", parent=self.janela)
            return
        if not conta:
            messagebox.showwarning("Organizar scans", "Selecione a conta correta na lista da direita.", parent=self.janela)
            return

        atual = str(conta["caminho_documento"] or "").strip()
        if atual and Path(atual).is_file():
            if not messagebox.askyesno(
                "Trocar anexo",
                f"A conta Nº {conta['numero_documento'] or conta['id']} já possui anexo.\n\nDeseja substituir pelo scan selecionado?",
                parent=self.janela,
            ):
                return
        try:
            destino, arquivado = self.servico.vincular_scan_recebido(int(conta["id"]), arquivo)
        except Exception as erro:
            messagebox.showerror("Organizar scans", str(erro), parent=self.janela)
            return

        numero = str(conta["numero_documento"] or "").strip() or f"ID {conta['id']}"
        self.var_status.set(f"✅ Scan vinculado ao documento {numero}: {destino.name}")
        self.var_busca.set("")
        if callable(self.ao_vincular):
            try:
                self.ao_vincular()
            except Exception:
                pass
        self._carregar_scans()
        self._carregar_contas()
        if not arquivado and arquivo.exists():
            messagebox.showwarning(
                "Vínculo concluído",
                "O anexo foi vinculado corretamente, mas o arquivo original não pôde ser retirado da fila de recebidos.",
                parent=self.janela,
            )


class JanelaDownloadDocumentosAdobe:
    """Cola mensagens do WhatsApp, extrai links Adobe e baixa os documentos em lote."""

    def __init__(self, master, servico: ContasPagarServico, *, competencia_inicial: str = ""):
        self.master = master
        self.servico = servico
        self.resultado_lote = None
        self._baixando = False

        self.janela = Toplevel(master)
        self.janela.title("Baixar scans do WhatsApp / Adobe")
        self.janela.transient(master.winfo_toplevel())
        self.janela.grab_set()
        dimensionar_janela(self.janela, 950, 680, 800, 560, maximizar_em_tela_baixa=True)

        competencias = list(self.servico.opcoes_competencia(
            adicionais=self.servico.repositorio.listar_competencias()
        ))
        padrao = competencia_inicial if competencia_inicial in competencias else date.today().strftime("%m/%Y")
        self.var_competencia = StringVar(value=padrao)
        self.var_pasta_destino = StringVar(value=str(self.servico.pasta_download_scans_preferida(padrao)))
        self.var_links = StringVar(value="0 link(s) Adobe identificado(s)")
        self.var_status = StringVar(value="Cole abaixo a mensagem inteira que veio do WhatsApp.")
        self._montar(competencias)

    def _montar(self, competencias: list[str]) -> None:
        principal = ttk.Frame(self.janela, padding=12, style="Page.TFrame")
        principal.pack(fill=BOTH, expand=True)

        cab = Frame(principal, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)
        cab.pack(fill=X, pady=(0, 8))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        Label(
            cab, text="⬇ Baixar scans do WhatsApp", bg=COR_CARD, fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"), padx=12, pady=7
        ).pack(anchor="w")
        Label(
            cab,
            text=(
                "Cole a mensagem inteira com os links do Adobe Acrobat. O FiscalPro identifica "
                "os links, tenta baixar todos e separa os que exigirem abertura manual."
            ),
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 9),
            padx=12, pady=3, justify="left", wraplength=860
        ).pack(anchor="w")

        topo = ttk.LabelFrame(principal, text="Destino dos arquivos", padding=8, style="Card.TLabelframe")
        topo.pack(fill=X, pady=(0, 8))
        topo.columnconfigure(1, weight=1)
        ttk.Label(topo, text="Competência:").grid(row=0, column=0, sticky="w")
        self.combo_competencia = ttk.Combobox(
            topo, textvariable=self.var_competencia, values=competencias,
            state="readonly", width=13
        )
        self.combo_competencia.grid(row=0, column=1, sticky="w", padx=(7, 14), pady=(0, 6))

        ttk.Label(topo, text="Pasta para baixar:").grid(row=1, column=0, sticky="w")
        ttk.Entry(topo, textvariable=self.var_pasta_destino, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=(7, 7)
        )
        ttk.Button(topo, text="📂 Escolher pasta", command=self._escolher_pasta).grid(
            row=1, column=2, sticky="e", padx=(0, 7)
        )
        ttk.Button(topo, text="Usar pasta do FiscalPro", command=self._usar_pasta_interna).grid(
            row=1, column=3, sticky="e"
        )
        ttk.Label(
            topo, text="Você pode escolher Área de Trabalho, Documentos ou qualquer pasta fácil de identificar."
        ).grid(row=2, column=1, columnspan=3, sticky="w", padx=(7, 0), pady=(5, 0))

        entrada = ttk.LabelFrame(principal, text="Mensagem / links do WhatsApp", padding=8, style="Card.TLabelframe")
        entrada.pack(fill=X, pady=(0, 8))
        self.texto = Text(
            entrada, height=6, wrap="word", font=("Segoe UI", 9),
            relief="solid", borderwidth=1
        )
        self.texto.pack(fill=X, expand=False)
        self.texto.bind("<<Modified>>", self._texto_alterado)

        barra = ttk.Frame(entrada, style="Card.TFrame")
        barra.pack(fill=X, pady=(7, 0))
        ttk.Label(barra, textvariable=self.var_links).pack(side=LEFT)
        ttk.Button(barra, text="🔎 Identificar links", command=self._identificar).pack(side=RIGHT)
        self.botao_baixar = ttk.Button(
            barra, text="⬇ Baixar todos", command=self._baixar, style="Primary.TButton"
        )
        self.botao_baixar.pack(side=RIGHT, padx=(0, 7))

        resultado_frame = ttk.LabelFrame(principal, text="Resultado", padding=8, style="Card.TLabelframe")
        resultado_frame.pack(fill=BOTH, expand=True, pady=(0, 8))
        resultado_frame.rowconfigure(1, weight=1)
        resultado_frame.columnconfigure(0, weight=1)
        Label(
            resultado_frame, textvariable=self.var_status, bg=COR_CARD, fg=COR_TEXTO,
            font=("Segoe UI", 9, "bold"), anchor="w", justify="left"
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.tabela_resultado = ttk.Treeview(
            resultado_frame, columns=("n", "status", "link", "arquivo"),
            show="headings", height=6
        )
        self.tabela_resultado.heading("n", text="#")
        self.tabela_resultado.heading("status", text="Status")
        self.tabela_resultado.heading("link", text="Link")
        self.tabela_resultado.heading("arquivo", text="Arquivo / motivo")
        self.tabela_resultado.column("n", width=45, anchor="center", stretch=False)
        self.tabela_resultado.column("status", width=90, anchor="center", stretch=False)
        self.tabela_resultado.column("link", width=380, anchor="w")
        self.tabela_resultado.column("arquivo", width=330, anchor="w")
        self.tabela_resultado.grid(row=1, column=0, sticky="nsew")
        rolagem = ttk.Scrollbar(resultado_frame, orient="vertical", command=self.tabela_resultado.yview)
        rolagem.grid(row=1, column=1, sticky="ns")
        self.tabela_resultado.configure(yscrollcommand=rolagem.set)

        rodape = ttk.Frame(principal, style="Page.TFrame")
        rodape.pack(fill=X)
        ttk.Button(rodape, text="Fechar", command=self._fechar).pack(side=RIGHT)
        self.botao_abrir = ttk.Button(
            rodape, text="📂 Abrir pasta dos baixados", command=self._abrir_pasta, state="disabled"
        )
        self.botao_abrir.pack(side=RIGHT, padx=(0, 7))
        self.botao_pendentes = ttk.Button(
            rodape, text="🌐 Abrir pendentes", command=self._abrir_pendentes, state="disabled"
        )
        self.botao_pendentes.pack(side=RIGHT, padx=(0, 7))
        ttk.Button(
            rodape, text="🗂 Organizar e vincular", command=self._abrir_organizador, style="Accent.TButton"
        ).pack(side=LEFT)

    def _escolher_pasta(self) -> None:
        atual = self.var_pasta_destino.get().strip() or str(Path.home() / "Downloads")
        pasta = filedialog.askdirectory(
            title="Escolha onde salvar os scans baixados",
            initialdir=atual if Path(atual).exists() else str(Path.home()),
            parent=self.janela,
        )
        if not pasta:
            return
        try:
            destino = self.servico.salvar_pasta_download_scans(pasta)
            self.var_pasta_destino.set(str(destino))
            self.var_status.set(f"Pasta escolhida: {destino}")
        except Exception as erro:
            messagebox.showerror("Escolher pasta", str(erro), parent=self.janela)

    def _usar_pasta_interna(self) -> None:
        try:
            destino = self.servico.usar_pasta_interna_download_scans(self.var_competencia.get())
            self.var_pasta_destino.set(str(destino))
            self.var_status.set(f"Pasta interna selecionada: {destino}")
        except Exception as erro:
            messagebox.showerror("Pasta do FiscalPro", str(erro), parent=self.janela)

    def _fechar(self) -> None:
        if self._baixando:
            messagebox.showwarning(
                "Download em andamento", "Aguarde o download terminar antes de fechar.", parent=self.janela
            )
            return
        self.janela.destroy()

    def _texto_alterado(self, _evento=None) -> None:
        if self.texto.edit_modified():
            self.texto.edit_modified(False)
            self._identificar(limpar_resultado=False)

    def _texto_atual(self) -> str:
        return self.texto.get("1.0", END).strip()

    def _identificar(self, limpar_resultado: bool = True) -> tuple[str, ...]:
        links = self.servico.extrair_links_documentos_adobe(self._texto_atual())
        self.var_links.set(f"{len(links)} link(s) Adobe identificado(s)")
        if limpar_resultado and not self._baixando:
            for item in self.tabela_resultado.get_children():
                self.tabela_resultado.delete(item)
            self.var_status.set(
                "Pronto para baixar." if links else "Nenhum link do Adobe Acrobat foi encontrado."
            )
        return links

    def _baixar(self) -> None:
        if self._baixando:
            return
        links = self._identificar()
        if not links:
            messagebox.showwarning(
                "Baixar scans", "Cole uma mensagem contendo pelo menos um link do Adobe Acrobat.",
                parent=self.janela
            )
            return
        competencia = self.var_competencia.get()
        texto = self._texto_atual()
        self._baixando = True
        self.resultado_lote = None
        self.botao_baixar.configure(state="disabled")
        self.botao_abrir.configure(state="disabled")
        self.botao_pendentes.configure(state="disabled")
        self.var_status.set(f"Baixando 0 de {len(links)}...")
        for item in self.tabela_resultado.get_children():
            self.tabela_resultado.delete(item)

        def progresso(resultado, atual, total):
            self.janela.after(0, lambda r=resultado, a=atual, t=total: self._mostrar_progresso(r, a, t))

        def executar():
            try:
                resultado = self.servico.baixar_documentos_adobe(
                    texto, competencia=competencia,
                    pasta_destino=self.var_pasta_destino.get().strip(),
                    progresso=progresso
                )
                self.janela.after(0, lambda: self._concluir(resultado, None))
            except Exception as erro:
                self.janela.after(0, lambda e=erro: self._concluir(None, e))

        threading.Thread(target=executar, daemon=True).start()

    def _mostrar_progresso(self, resultado, atual: int, total: int) -> None:
        arquivo = resultado.caminho.name if resultado.caminho else resultado.mensagem
        self.tabela_resultado.insert(
            "", END, values=(resultado.indice, resultado.status, resultado.url, arquivo),
            tags=(resultado.status,)
        )
        self.var_status.set(f"Baixando {atual} de {total}... último: {resultado.status}")

    def _concluir(self, resultado, erro) -> None:
        self._baixando = False
        self.botao_baixar.configure(state="normal")
        if erro is not None:
            self.var_status.set("O download não pôde ser concluído.")
            messagebox.showerror("Baixar scans", str(erro), parent=self.janela)
            return

        self.resultado_lote = resultado
        self.botao_abrir.configure(state="normal")
        if resultado.manuais or resultado.erros:
            self.botao_pendentes.configure(state="normal")
        self.var_status.set(
            f"Concluído: ✅ {resultado.baixados} baixado(s) • "
            f"🌐 {resultado.manuais} manual(is) • ❌ {resultado.erros} erro(s)."
        )
        mensagem = (
            f"Links encontrados: {resultado.total_links}\n"
            f"Baixados automaticamente: {resultado.baixados}\n"
            f"Precisam abrir manualmente: {resultado.manuais}\n"
            f"Erros: {resultado.erros}\n\n"
            f"Pasta: {resultado.pasta}"
        )
        messagebox.showinfo("Download concluído", mensagem, parent=self.janela)

    def _abrir_pasta(self) -> None:
        try:
            if self.resultado_lote is not None:
                pasta = self.resultado_lote.pasta
            else:
                pasta = Path(self.var_pasta_destino.get().strip() or self.servico.pasta_documentos_recebidos(self.var_competencia.get()))
            PainelContasPagar._abrir_caminho(str(pasta))
        except Exception as erro:
            messagebox.showerror("Abrir pasta", str(erro), parent=self.janela)

    def _abrir_organizador(self) -> None:
        JanelaOrganizarScans(
            self.master, self.servico, competencia_inicial=self.var_competencia.get(),
            ao_vincular=getattr(self.master, "atualizar", None),
        )

    def _abrir_pendentes(self) -> None:
        if self.resultado_lote is None:
            return
        pendentes = [r for r in self.resultado_lote.resultados if r.status != "OK"]
        if not pendentes:
            messagebox.showinfo("Pendentes", "Não existem links pendentes.", parent=self.janela)
            return
        if len(pendentes) > 5 and not messagebox.askyesno(
            "Abrir links pendentes",
            f"Serão abertas {len(pendentes)} abas no navegador. Deseja continuar?",
            parent=self.janela
        ):
            return
        for item in pendentes:
            webbrowser.open(item.url, new=2)


class JanelaPacoteContabilidade:
    """Conferência e geração do pacote mensal de documentos para a contabilidade."""

    def __init__(self, master, servico: ContasPagarServico, *, competencia_inicial: str = ""):
        self.master = master
        self.servico = servico
        self.janela = Toplevel(master)
        self.janela.title("Pacote mensal para a Contabilidade")
        self.janela.transient(master.winfo_toplevel())
        self.janela.grab_set()
        dimensionar_janela(self.janela, 820, 650, 720, 560, maximizar_em_tela_baixa=False)

        competencias = list(self.servico.opcoes_competencia(
            adicionais=self.servico.repositorio.listar_competencias()
        ))
        padrao = competencia_inicial if competencia_inicial in competencias else date.today().strftime("%m/%Y")
        self.var_competencia = StringVar(value=padrao)
        self.empresas = tuple(self.servico.repositorio.listar_empresas())
        self.vars_empresas = {empresa: BooleanVar(value=True) for empresa in self.empresas}
        self.var_pasta = StringVar(value=str(Path.home() / "Documents"))
        self.var_resumo = StringVar(value="Clique em Conferir documentos.")
        self._montar(competencias)
        self._conferir()

    def _montar(self, competencias: list[str]) -> None:
        principal = ttk.Frame(self.janela, padding=12, style="Page.TFrame")
        principal.pack(fill=BOTH, expand=True)

        cab = Frame(principal, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)
        cab.pack(fill=X, pady=(0, 10))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        Label(cab, text="📦 Pacote mensal para a Contabilidade", bg=COR_CARD, fg=COR_TEXTO,
              font=("Segoe UI", 13, "bold"), padx=12, pady=8).pack(anchor="w")
        Label(cab, text="Reúne os PDFs/imagens anexados às contas e gera uma planilha de conferência.",
              bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 9), padx=12, pady=3).pack(anchor="w")

        periodo = ttk.LabelFrame(principal, text="Competência", padding=10, style="Card.TLabelframe")
        periodo.pack(fill=X, pady=(0, 8))
        ttk.Label(periodo, text="Mês/ano:").pack(side=LEFT)
        combo = ttk.Combobox(periodo, textvariable=self.var_competencia, values=competencias, state="readonly", width=13)
        combo.pack(side=LEFT, padx=(8, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._conferir())

        bloco = ttk.LabelFrame(principal, text="Empresas", padding=10, style="Card.TLabelframe")
        bloco.pack(fill=X, pady=(0, 8))
        for indice, empresa in enumerate(self.empresas):
            ttk.Checkbutton(bloco, text=empresa, variable=self.vars_empresas[empresa], command=self._conferir).grid(
                row=indice // 2, column=indice % 2, sticky="w", padx=(0, 25), pady=2
            )
        acoes = ttk.Frame(bloco)
        acoes.grid(row=(len(self.empresas)+1)//2, column=0, columnspan=2, sticky="w", pady=(6,0))
        ttk.Button(acoes, text="Marcar todas", command=lambda: self._marcar(True)).pack(side=LEFT)
        ttk.Button(acoes, text="Desmarcar todas", command=lambda: self._marcar(False)).pack(side=LEFT, padx=(6,0))

        conferencia = ttk.LabelFrame(principal, text="Conferência dos anexos", padding=12, style="Card.TLabelframe")
        conferencia.pack(fill=X, pady=(0, 8))
        Label(conferencia, textvariable=self.var_resumo, bg=COR_CARD, fg=COR_TEXTO,
              font=("Segoe UI", 10, "bold"), justify="left").pack(anchor="w")
        ttk.Button(conferencia, text="🔎 Conferir documentos", command=self._conferir).pack(anchor="e", pady=(8,0))

        destino = ttk.LabelFrame(principal, text="Destino", padding=10, style="Card.TLabelframe")
        destino.pack(fill=X, pady=(0, 8))
        destino.columnconfigure(0, weight=1)
        ttk.Entry(destino, textvariable=self.var_pasta, state="readonly").grid(row=0, column=0, sticky="ew")
        ttk.Button(destino, text="Selecionar pasta", command=self._selecionar_pasta).grid(row=0, column=1, padx=(8,0))

        aviso = Label(principal, text=(
            "O ZIP sempre inclui o relatório Excel. Se houver contas sem anexo, também será criado "
            "DOCUMENTOS_FALTANTES.txt para facilitar a conferência antes do envio."
        ), bg=COR_CARD, fg=COR_TEXTO_SUAVE, justify="left", padx=10, pady=8,
            highlightthickness=1, highlightbackground=COR_BORDA)
        aviso.pack(fill=X, pady=(0, 10))

        rodape = ttk.Frame(principal, style="Page.TFrame")
        rodape.pack(fill=X)
        ttk.Button(rodape, text="Cancelar", command=self.janela.destroy).pack(side=RIGHT)
        ttk.Button(rodape, text="📦 Gerar pacote", command=self._gerar, style="Primary.TButton").pack(side=RIGHT, padx=(0,8))

    def _marcar(self, valor: bool) -> None:
        for var in self.vars_empresas.values():
            var.set(valor)
        self._conferir()

    def _selecionadas(self) -> tuple[str, ...]:
        return tuple(e for e in self.empresas if self.vars_empresas[e].get())

    def _selecionar_pasta(self) -> None:
        pasta = filedialog.askdirectory(title="Pasta do pacote da contabilidade", initialdir=self.var_pasta.get(), parent=self.janela)
        if pasta:
            self.var_pasta.set(pasta)

    def _conferir(self) -> None:
        empresas = self._selecionadas()
        if not empresas:
            self.var_resumo.set("Nenhuma empresa selecionada.")
            return
        try:
            resumo = self.servico.resumo_documentos_competencia(
                self.var_competencia.get(), empresas=empresas
            )
        except Exception as erro:
            self.var_resumo.set(str(erro))
            return
        self.var_resumo.set(
            f"Contas na competência: {resumo.total_contas}\n"
            f"✅ Com documento: {resumo.com_documento}    "
            f"⚠️ Sem documento: {resumo.sem_documento}"
            + (f"    • caminhos inválidos: {resumo.documentos_invalidos}" if resumo.documentos_invalidos else "")
        )

    def _gerar(self) -> None:
        empresas = self._selecionadas()
        if not empresas:
            messagebox.showwarning("Pacote contabilidade", "Marque pelo menos uma empresa.", parent=self.janela)
            return
        try:
            resumo = self.servico.resumo_documentos_competencia(self.var_competencia.get(), empresas=empresas)
        except Exception as erro:
            messagebox.showerror("Pacote contabilidade", str(erro), parent=self.janela)
            return
        if resumo.sem_documento and not messagebox.askyesno(
            "Documentos faltando",
            f"Existem {resumo.sem_documento} conta(s) sem documento válido.\n\n"
            "Deseja gerar o pacote mesmo assim?",
            parent=self.janela,
        ):
            return
        try:
            resultado = self.servico.gerar_pacote_contabilidade(
                self.var_pasta.get(), competencia=self.var_competencia.get(), empresas=empresas
            )
        except Exception as erro:
            messagebox.showerror("Pacote contabilidade", str(erro), parent=self.janela)
            return
        mensagem = (
            f"Pacote criado com sucesso.\n\n"
            f"Contas: {resultado.total_contas}\n"
            f"Documentos incluídos: {resultado.documentos_incluidos}\n"
            f"Documentos faltantes: {resultado.documentos_faltantes}\n\n"
            f"{resultado.caminho_zip}"
        )
        if messagebox.askyesno("Pacote contabilidade", mensagem + "\n\nDeseja abrir a pasta?", parent=self.janela):
            PainelContasPagar._abrir_caminho(str(resultado.caminho_zip.parent))
        self.janela.destroy()


class JanelaRelatorioContasPagas:
    """Relatório mensal pela data efetiva da baixa."""

    def __init__(self, master, servico: ContasPagarServico, *, competencia_inicial: str = ""):
        self.master = master
        self.servico = servico
        self.janela = Toplevel(master)
        self.janela.title("Contas pagas do mês")
        self.janela.transient(master.winfo_toplevel())
        self.janela.grab_set()
        dimensionar_janela(self.janela, 780, 610, 720, 560, maximizar_em_tela_baixa=False)

        competencias = list(self.servico.opcoes_competencia(
            adicionais=self.servico.repositorio.listar_competencias()
        ))
        padrao = competencia_inicial if competencia_inicial in competencias else date.today().strftime("%m/%Y")
        self.var_competencia = StringVar(value=padrao)
        self.empresas_disponiveis = tuple(self.servico.repositorio.listar_empresas())
        self.vars_empresas = {
            empresa: BooleanVar(value=True) for empresa in self.empresas_disponiveis
        }
        self.var_pasta = StringVar(value=str(Path.home() / "Documents"))
        self.var_resumo = StringVar(value="Calculando...")
        self._montar(competencias)
        self._atualizar_resumo()

    def _montar(self, competencias: list[str]) -> None:
        principal = ttk.Frame(self.janela, padding=12, style="Page.TFrame")
        principal.pack(fill=BOTH, expand=True)

        cab = Frame(principal, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)
        cab.pack(fill=X, pady=(0, 9))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        Label(
            cab, text="💰 Relatório mensal de contas pagas", bg=COR_CARD, fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"), padx=12, pady=7,
        ).pack(anchor="w")
        Label(
            cab,
            text=(
                "O mês é definido pela DATA DA BAIXA. Assim, uma conta vencida em agosto mas "
                "paga em setembro aparece no relatório de setembro."
            ),
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 9),
            padx=12, pady=3, justify="left", wraplength=720,
        ).pack(anchor="w")

        periodo = ttk.LabelFrame(principal, text="Mês do pagamento", padding=10, style="Card.TLabelframe")
        periodo.pack(fill=X, pady=(0, 8))
        ttk.Label(periodo, text="Mês / ano:").pack(side=LEFT)
        combo = ttk.Combobox(
            periodo, textvariable=self.var_competencia, values=competencias,
            state="readonly", width=14,
        )
        combo.pack(side=LEFT, padx=(7, 14))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._atualizar_resumo())
        Label(
            periodo, textvariable=self.var_resumo, bg=COR_CARD, fg=COR_TEXTO,
            font=("Segoe UI", 9, "bold"), padx=8,
        ).pack(side=LEFT)

        bloco = ttk.LabelFrame(principal, text="Empresas", padding=10, style="Card.TLabelframe")
        bloco.pack(fill=X, pady=(0, 8))
        for indice, empresa in enumerate(self.empresas_disponiveis):
            linha = indice // 2
            coluna = indice % 2
            ttk.Checkbutton(
                bloco, text=empresa, variable=self.vars_empresas[empresa],
                command=self._atualizar_resumo,
            ).grid(row=linha, column=coluna, sticky="w", padx=(0, 28), pady=2)
        linha_acoes = (len(self.empresas_disponiveis) + 1) // 2
        acoes_emp = ttk.Frame(bloco)
        acoes_emp.grid(row=linha_acoes, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(acoes_emp, text="Marcar todas", command=lambda: self._marcar_empresas(True)).pack(side=LEFT)
        ttk.Button(acoes_emp, text="Desmarcar todas", command=lambda: self._marcar_empresas(False)).pack(side=LEFT, padx=(6, 0))

        destino = ttk.LabelFrame(principal, text="Onde salvar", padding=10, style="Card.TLabelframe")
        destino.pack(fill=X, pady=(0, 8))
        destino.columnconfigure(0, weight=1)
        ttk.Entry(destino, textvariable=self.var_pasta).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(destino, text="Escolher pasta", command=self._selecionar_pasta).grid(row=0, column=1)

        Label(
            principal,
            text=(
                "O Excel terá uma aba Resumo, uma aba Pagamentos e uma aba por empresa. "
                "Para a contabilidade, mostra primeiro Data de pagamento, Vencimento, Fornecedor, "
                "CNPJ do fornecedor, Nº Documento, Empresa e Valor."
            ),
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 9),
            justify="left", wraplength=730, padx=10, pady=9,
            highlightthickness=1, highlightbackground=COR_BORDA,
        ).pack(fill=X, pady=(0, 10))

        acoes = ttk.Frame(principal, style="Page.TFrame")
        acoes.pack(fill=X)
        ttk.Button(
            acoes, text="🏢 Cadastrar CNPJs", command=self._abrir_cadastro_cnpj
        ).pack(side=LEFT)
        ttk.Button(acoes, text="Cancelar", command=self.janela.destroy).pack(side=RIGHT)
        ttk.Button(
            acoes, text="Gerar Excel", command=self._gerar, style="Primary.TButton"
        ).pack(side=RIGHT, padx=(0, 8))

    def _marcar_empresas(self, valor: bool) -> None:
        for var in self.vars_empresas.values():
            var.set(bool(valor))
        self._atualizar_resumo()

    def _empresas_selecionadas(self) -> tuple[str, ...]:
        return tuple(
            empresa for empresa in self.empresas_disponiveis
            if self.vars_empresas[empresa].get()
        )

    def _atualizar_resumo(self) -> None:
        empresas = self._empresas_selecionadas()
        if not empresas:
            self.var_resumo.set("Nenhuma empresa selecionada")
            return
        try:
            resumo = self.servico.resumo_contas_pagas_mes(
                self.var_competencia.get(), empresas=empresas
            )
            faltantes = int(resumo.get("quantidade_fornecedores_sem_cnpj", 0) or 0)
            complemento = f" • ⚠ {faltantes} fornecedor(es) sem CNPJ" if faltantes else " • CNPJs OK"
            self.var_resumo.set(
                f"{resumo['quantidade']} pagamento(s) • {self.servico.valor_br(resumo['total'])}{complemento}"
            )
        except Exception as erro:
            self.var_resumo.set(str(erro))

    def _abrir_cadastro_cnpj(self) -> None:
        janela = JanelaFornecedoresCNPJ(self.janela, self.servico)
        self.janela.wait_window(janela.janela)
        self._atualizar_resumo()

    def _selecionar_pasta(self) -> None:
        pasta = filedialog.askdirectory(
            title="Escolha onde salvar o relatório",
            initialdir=self.var_pasta.get() or str(Path.home()),
            parent=self.janela,
        )
        if pasta:
            self.var_pasta.set(pasta)

    def _gerar(self) -> None:
        empresas = self._empresas_selecionadas()
        if not empresas:
            messagebox.showwarning(
                "Contas pagas do mês", "Marque pelo menos uma empresa.", parent=self.janela
            )
            return
        if not self.var_pasta.get().strip():
            messagebox.showwarning(
                "Contas pagas do mês", "Escolha a pasta onde o Excel será salvo.", parent=self.janela
            )
            return
        try:
            resumo_cnpj = self.servico.resumo_contas_pagas_mes(
                self.var_competencia.get(), empresas=empresas
            )
        except Exception as erro:
            messagebox.showerror("Contas pagas do mês", str(erro), parent=self.janela)
            return
        faltantes = tuple(resumo_cnpj.get("fornecedores_sem_cnpj", ()))
        if faltantes:
            amostra = "\n".join(f"• {nome}" for nome in faltantes[:8])
            restante = len(faltantes) - min(len(faltantes), 8)
            if restante:
                amostra += f"\n• ... e mais {restante}"
            if not messagebox.askyesno(
                "CNPJ de fornecedor faltando",
                f"Existem {len(faltantes)} fornecedor(es) sem CNPJ neste relatório:\n\n"
                f"{amostra}\n\nDeseja gerar o Excel mesmo assim?",
                parent=self.janela,
            ):
                return
        try:
            resultado = self.servico.gerar_relatorio_contas_pagas_mes(
                self.var_pasta.get(), competencia=self.var_competencia.get(), empresas=empresas
            )
        except Exception as erro:
            messagebox.showerror("Contas pagas do mês", str(erro), parent=self.janela)
            return

        totais = "\n".join(
            f"• {empresa}: {self.servico.valor_br(total)}"
            for empresa, total in resultado.totais_empresas
        )
        mensagem = (
            f"Relatório gerado com sucesso.\n\n"
            f"Pagamentos: {resultado.quantidade_contas}\n"
            f"Empresas com pagamento: {resultado.quantidade_empresas}\n\n"
            f"{totais}\n\n"
            f"TOTAL GERAL: {self.servico.valor_br(resultado.total_geral)}\n\n"
            f"{resultado.caminho}"
        )
        if messagebox.askyesno(
            "Contas pagas do mês", mensagem + "\n\nDeseja abrir a pasta?", parent=self.janela
        ):
            PainelContasPagar._abrir_caminho(str(resultado.caminho.parent))
        self.janela.destroy()


class JanelaRelatorioVencimentos:
    """Configuração dos relatórios de vencimentos da Sprint 16.2.2."""

    def __init__(self, master, servico: ContasPagarServico):
        self.master = master
        self.servico = servico
        inicio, fim = servico.periodo_proxima_semana()

        self.janela = Toplevel(master)
        self.janela.title("Relatório semanal de Contas a Pagar")
        self.janela.transient(master.winfo_toplevel())
        self.janela.grab_set()
        dimensionar_janela(
            self.janela, 820, 680, 740, 620, maximizar_em_tela_baixa=False
        )

        self.var_periodo = StringVar(value="Próxima semana")
        self.var_inicio = StringVar(value=inicio.strftime("%d/%m/%Y"))
        self.var_fim = StringVar(value=fim.strftime("%d/%m/%Y"))
        self.empresas_disponiveis = tuple(self.servico.repositorio.listar_empresas())
        self.vars_empresas = {
            empresa: BooleanVar(value=True) for empresa in self.empresas_disponiveis
        }
        self.var_organizacao = StringVar(value="Consolidado - um arquivo")
        self.var_pdf = BooleanVar(value=True)
        self.var_excel = BooleanVar(value=True)
        self.var_vencidas = BooleanVar(value=False)
        self.var_detalhado = BooleanVar(value=True)
        self.var_pasta = StringVar(value=str(Path.home() / "Documents"))
        self.var_resumo = StringVar(value="")
        self._montar()
        self._atualizar_periodo()

    def _montar(self) -> None:
        principal = ttk.Frame(self.janela, padding=12, style="Page.TFrame")
        principal.pack(fill=BOTH, expand=True)

        cabecalho = Frame(
            principal, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA
        )
        cabecalho.pack(fill=X, pady=(0, 10))
        Frame(cabecalho, bg=COR_DESTAQUE, height=3).pack(fill=X)
        Label(
            cabecalho,
            text="Relatório de vencimentos",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"),
            padx=12,
            pady=7,
        ).pack(anchor="w")
        Label(
            cabecalho,
            text=(
                "Selecione uma ou mais empresas e gere as contas da semana seguinte em um "
                "relatório consolidado ou em arquivos separados."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
            padx=12,
            pady=3,
        ).pack(anchor="w")

        periodo = ttk.LabelFrame(
            principal, text="Período", padding=10, style="Card.TLabelframe"
        )
        periodo.pack(fill=X, pady=(0, 8))
        periodo.columnconfigure(5, weight=1)
        ttk.Radiobutton(
            periodo,
            text="Próxima semana (sábado a sexta-feira)",
            variable=self.var_periodo,
            value="Próxima semana",
            command=self._atualizar_periodo,
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(
            periodo,
            text="Período personalizado",
            variable=self.var_periodo,
            value="Personalizado",
            command=self._atualizar_periodo,
        ).grid(row=0, column=3, columnspan=3, sticky="w", padx=(20, 0))

        ttk.Label(periodo, text="Data inicial:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.ent_inicio = ttk.Entry(periodo, textvariable=self.var_inicio, width=14)
        self.ent_inicio.grid(row=1, column=1, sticky="w", padx=(5, 18), pady=(8, 0))
        ttk.Label(periodo, text="Data final:").grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.ent_fim = ttk.Entry(periodo, textvariable=self.var_fim, width=14)
        self.ent_fim.grid(row=1, column=3, sticky="w", padx=(5, 18), pady=(8, 0))
        ttk.Label(periodo, textvariable=self.var_resumo, foreground=COR_TEXTO_SUAVE).grid(
            row=1, column=4, columnspan=2, sticky="w", pady=(8, 0)
        )

        opcoes = ttk.LabelFrame(
            principal, text="Empresas e organização", padding=10, style="Card.TLabelframe"
        )
        opcoes.pack(fill=X, pady=(0, 8))
        opcoes.columnconfigure(0, weight=1)
        opcoes.columnconfigure(1, weight=1)

        bloco_empresas = ttk.Frame(opcoes)
        bloco_empresas.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        ttk.Label(bloco_empresas, text="Empresas do relatório:").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        for indice, empresa in enumerate(self.empresas_disponiveis):
            linha = 1 + (indice // 2)
            coluna = indice % 2
            ttk.Checkbutton(
                bloco_empresas,
                text=empresa,
                variable=self.vars_empresas[empresa],
            ).grid(row=linha, column=coluna, sticky="w", padx=(0, 18), pady=2)

        acoes_empresas = ttk.Frame(bloco_empresas)
        acoes_empresas.grid(
            row=1 + ((len(self.empresas_disponiveis) + 1) // 2),
            column=0, columnspan=2, sticky="w", pady=(5, 0)
        )
        ttk.Button(
            acoes_empresas, text="Marcar todas", command=lambda: self._marcar_empresas(True)
        ).pack(side=LEFT)
        ttk.Button(
            acoes_empresas, text="Desmarcar todas", command=lambda: self._marcar_empresas(False)
        ).pack(side=LEFT, padx=(6, 0))

        bloco_organizacao = ttk.Frame(opcoes)
        bloco_organizacao.grid(row=0, column=1, sticky="new")
        ttk.Label(bloco_organizacao, text="Organização:").pack(anchor="w")
        ttk.Combobox(
            bloco_organizacao,
            textvariable=self.var_organizacao,
            values=(
                "Consolidado - um arquivo",
                "Separado - um arquivo por empresa",
            ),
            state="readonly",
            width=34,
        ).pack(fill=X, pady=(5, 0))
        ttk.Label(
            bloco_organizacao,
            text=(
                "Consolidado: somente as empresas marcadas no mesmo arquivo.\n"
                "Separado: um arquivo para cada empresa marcada."
            ),
            foreground=COR_TEXTO_SUAVE,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        conteudo = ttk.LabelFrame(
            principal, text="Conteúdo e formatos", padding=10, style="Card.TLabelframe"
        )
        conteudo.pack(fill=X, pady=(0, 8))
        ttk.Checkbutton(
            conteudo,
            text="Detalhar todas as contas",
            variable=self.var_detalhado,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            conteudo,
            text="Incluir contas vencidas anteriores ainda não pagas",
            variable=self.var_vencidas,
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Separator(conteudo, orient="vertical").grid(
            row=0, column=1, rowspan=2, sticky="ns", padx=20
        )
        ttk.Checkbutton(conteudo, text="Gerar PDF", variable=self.var_pdf).grid(
            row=0, column=2, sticky="w"
        )
        ttk.Checkbutton(conteudo, text="Gerar Excel", variable=self.var_excel).grid(
            row=1, column=2, sticky="w", pady=(5, 0)
        )

        destino = ttk.LabelFrame(
            principal, text="Pasta de destino", padding=10, style="Card.TLabelframe"
        )
        destino.pack(fill=X, pady=(0, 8))
        destino.columnconfigure(0, weight=1)
        ttk.Entry(destino, textvariable=self.var_pasta).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(destino, text="Selecionar pasta", command=self._selecionar_pasta).grid(
            row=0, column=1, sticky="ew"
        )

        aviso = Label(
            principal,
            text=(
                "O relatório considera somente contas sem data de pagamento. No modo separado, "
                "o FiscalPro também cria um Resumo Geral com o total de cada empresa e do grupo."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=700,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
        )
        aviso.pack(fill=X, pady=(0, 10))

        acoes = ttk.Frame(principal, style="Page.TFrame")
        acoes.pack(fill=X)
        ttk.Button(acoes, text="Cancelar", command=self.janela.destroy).pack(
            side=RIGHT
        )
        ttk.Button(
            acoes,
            text="Gerar relatórios",
            command=self._gerar,
            style="Primary.TButton",
        ).pack(side=RIGHT, padx=(0, 8))

    def _marcar_empresas(self, marcado: bool) -> None:
        for variavel in self.vars_empresas.values():
            variavel.set(bool(marcado))

    def _empresas_selecionadas(self) -> tuple[str, ...]:
        return tuple(
            empresa
            for empresa in self.empresas_disponiveis
            if self.vars_empresas[empresa].get()
        )

    def _atualizar_periodo(self) -> None:
        personalizado = self.var_periodo.get() == "Personalizado"
        estado = "normal" if personalizado else "disabled"
        self.ent_inicio.configure(state=estado)
        self.ent_fim.configure(state=estado)
        if not personalizado:
            inicio, fim = self.servico.periodo_proxima_semana()
            self.var_inicio.set(inicio.strftime("%d/%m/%Y"))
            self.var_fim.set(fim.strftime("%d/%m/%Y"))
        self.var_resumo.set(f"{self.var_inicio.get()} até {self.var_fim.get()}")

    def _selecionar_pasta(self) -> None:
        pasta = filedialog.askdirectory(
            title="Escolha a pasta dos relatórios",
            initialdir=self.var_pasta.get() or str(Path.home()),
            parent=self.janela,
        )
        if pasta:
            self.var_pasta.set(pasta)

    def _gerar(self) -> None:
        empresas = self._empresas_selecionadas()
        if not empresas:
            messagebox.showwarning(
                "Relatório semanal",
                "Marque pelo menos uma empresa para gerar o relatório.",
                parent=self.janela,
            )
            return
        separado = self.var_organizacao.get().startswith("Separado")
        try:
            resultado = self.servico.gerar_relatorio_vencimentos(
                self.var_pasta.get(),
                inicio=self.var_inicio.get(),
                fim=self.var_fim.get(),
                empresas=empresas,
                incluir_vencidas=self.var_vencidas.get(),
                detalhado=self.var_detalhado.get(),
                separado=separado,
                gerar_pdf=self.var_pdf.get(),
                gerar_excel=self.var_excel.get(),
            )
        except Exception as erro:
            messagebox.showerror("Relatório semanal", str(erro), parent=self.janela)
            return

        totais = "\n".join(
            f"• {empresa_nome}: {self.servico.valor_br(total)}"
            for empresa_nome, total in resultado.totais_empresas
        )
        mensagem = (
            f"Contas incluídas: {resultado.quantidade_contas}\n"
            f"Empresas: {resultado.quantidade_empresas}\n\n"
            f"{totais or 'Nenhuma conta encontrada no período.'}\n\n"
            f"TOTAL GERAL: {self.servico.valor_br(resultado.total_geral)}\n\n"
            f"Arquivos gerados: {len(resultado.arquivos)}"
        )
        if messagebox.askyesno(
            "Relatórios gerados",
            mensagem + "\n\nDeseja abrir a pasta de destino?",
            parent=self.janela,
        ):
            PainelContasPagar._abrir_caminho(str(Path(self.var_pasta.get())))
        self.janela.destroy()


class JanelaContaPagar:
    """Cadastro rápido de contas com fornecedores, categorias e datas assistidas."""

    def __init__(
        self,
        master,
        servico: ContasPagarServico,
        *,
        conta=None,
        conta_id: int | None = None,
        dados: dict[str, object] | None = None,
        fila_id: int | None = None,
        agenda_item_id: int | None = None,
        ao_salvar=None,
    ):
        self.master = master
        self.servico = servico
        self.conta_id = conta_id
        self.fila_id = fila_id
        self.agenda_item_id = agenda_item_id
        self.ao_salvar = ao_salvar
        self.fonte = dict(conta) if conta is not None else dict(dados or {})

        self.janela = Toplevel(master)
        self.janela.title("Editar conta" if conta_id else "Nova conta")
        self.janela.transient(master.winfo_toplevel())
        self.janela.grab_set()
        dimensionar_janela(
            self.janela, 780, 720, 700, 640, maximizar_em_tela_baixa=False
        )

        competencia_inicial = self.servico.competencia_br(
            str(self.fonte.get("competencia") or "")
        )
        if not competencia_inicial:
            competencia_inicial = date.today().strftime("%m/%Y")

        self.vars = {
            "empresa": StringVar(value=str(self.fonte.get("empresa") or "")),
            "fornecedor": StringVar(value=str(self.fonte.get("fornecedor") or "")),
            "fornecedor_cnpj": StringVar(
                value=JanelaFornecedoresCNPJ._formatar_cnpj(
                    self.fonte.get("fornecedor_cnpj") or ""
                )
            ),
            "descricao": StringVar(
                value=str(
                    self.fonte.get("descricao")
                    or self.fonte.get("tipo_documento")
                    or ""
                )
            ),
            "categoria": StringVar(
                value=str(self.fonte.get("categoria") or "OUTROS").strip().upper()
            ),
            "valor": StringVar(value=self._valor_inicial(self.fonte.get("valor"))),
            "vencimento": StringVar(value=self._data_inicial(self.fonte.get("vencimento"))),
            "data_pagamento": StringVar(
                value=self._data_inicial(self.fonte.get("data_pagamento"))
            ),
            "numero_documento": StringVar(
                value=str(self.fonte.get("numero_documento") or "")
            ),
            "competencia": StringVar(value=competencia_inicial),
            "caminho_documento": StringVar(
                value=str(self.fonte.get("caminho_documento") or "")
            ),
        }
        self.origem = str(
            self.fonte.get("origem") or ("ROBÔ FISCALPRO" if fila_id else "MANUAL")
        )
        self.robo_documento_id = self.fonte.get("robo_documento_id")
        self.fornecedores_todos: list[str] = []
        self.cnpjs_fornecedor: list[str] = []
        self._fornecedor_cnpj_nome = str(self.fonte.get("fornecedor") or "").strip()
        self.categorias_todas: list[str] = []
        self.detalhes_visiveis = True
        self.var_feedback_salvamento = StringVar(value="")
        self._montar()
        self._atualizar_fornecedores()
        self._atualizar_cnpjs_fornecedor()
        self._atualizar_categorias()
        self._atualizar_competencias()

        # 17.8.77: os detalhes fazem parte do fluxo normal do cadastro e
        # permanecem visíveis em contas novas e edições.
        self.detalhes_visiveis = True
        self.janela.bind("<Control-s>", lambda _e: self._salvar())
        # 17.8.48: Enter vira o comando principal do cadastro rápido.
        # O atalho é inteligente: enquanto faltar dado obrigatório ele leva
        # ao próximo campo; quando o cadastro estiver completo, salva a conta.
        self.janela.bind("<Return>", self._atalho_enter_conta, add="+")
        self.janela.bind("<KP_Enter>", self._atalho_enter_conta, add="+")
        self.janela.after_idle(self._focar_primeiro_campo)

    def _data_inicial(self, valor) -> str:
        if not valor:
            return ""
        if isinstance(valor, (datetime, date)):
            return valor.strftime("%d/%m/%Y")
        texto = str(valor)
        return self.servico.data_br(texto) if re_iso(texto) else texto

    def _valor_inicial(self, valor) -> str:
        if valor in (None, ""):
            return ""
        try:
            return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (TypeError, ValueError):
            return str(valor)

    def _montar(self) -> None:
        corpo = ttk.Frame(self.janela, padding=10)
        corpo.pack(fill=BOTH, expand=True)
        corpo.columnconfigure(0, weight=1)

        cabecalho = ttk.Frame(corpo)
        cabecalho.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(
            cabecalho,
            text="Cadastro rápido de conta",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            cabecalho,
            text=(
                "Preencha os dados da conta. Fornecedores ficam salvos automaticamente "
                "e os detalhes abaixo permanecem disponíveis no mesmo cadastro."
            ),
            foreground=COR_TEXTO_SUAVE,
        ).pack(anchor="w", pady=(2, 0))

        principais = ttk.LabelFrame(
            corpo, text="Dados principais", padding=8, style="Card.TLabelframe"
        )
        principais.grid(row=1, column=0, sticky="ew")
        principais.columnconfigure(1, weight=1)

        linha = 0
        ttk.Label(principais, text="Empresa:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self.cbo_empresa_conta = ttk.Combobox(
            principais,
            textvariable=self.vars["empresa"],
            values=self.servico.repositorio.listar_empresas(),
            state="readonly",
        )
        self.cbo_empresa_conta.grid(
            row=linha, column=1, columnspan=2, sticky="ew", pady=3
        )
        linha += 1

        ttk.Label(principais, text="Fornecedor / beneficiário:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self.cbo_fornecedor = ttk.Combobox(
            principais,
            textvariable=self.vars["fornecedor"],
            state="normal",
        )
        self.cbo_fornecedor.grid(
            row=linha, column=1, columnspan=2, sticky="ew", pady=3
        )
        self.cbo_fornecedor.configure(postcommand=self._atualizar_fornecedores)
        self.cbo_fornecedor.bind("<KeyRelease>", self._filtrar_fornecedores)
        self.cbo_fornecedor.bind("<<ComboboxSelected>>", self._fornecedor_selecionado)
        self.cbo_fornecedor.bind("<FocusOut>", self._fornecedor_selecionado)
        self.cbo_fornecedor.bind("<Escape>", lambda _e: self._esconder_sugestoes_fornecedor())
        linha += 1
        ttk.Label(
            principais,
            text=(
                "Digite o início do nome para ver somente os fornecedores correspondentes. "
                "Novos fornecedores ficam salvos automaticamente."
            ),
            foreground=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8),
        ).grid(row=linha, column=1, columnspan=2, sticky="w", pady=(0, 2))
        linha += 1

        ttk.Label(principais, text="CNPJ do fornecedor:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self.cbo_fornecedor_cnpj = ttk.Combobox(
            principais, textvariable=self.vars["fornecedor_cnpj"], state="normal"
        )
        self.cbo_fornecedor_cnpj.grid(
            row=linha, column=1, columnspan=2, sticky="ew", pady=3
        )
        self.cbo_fornecedor_cnpj.configure(postcommand=self._atualizar_cnpjs_fornecedor)
        self.cbo_fornecedor_cnpj.bind(
            "<<ComboboxSelected>>", lambda _e: self.cbo_fornecedor_cnpj.icursor(END)
        )
        linha += 1
        ttk.Label(
            principais,
            text=(
                "Um CNPJ é preenchido automaticamente; com vários, escolha o desta conta. "
                "Se digitar um novo CNPJ, ele fica salvo para esse fornecedor."
            ),
            foreground=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8),
        ).grid(row=linha, column=1, columnspan=2, sticky="w", pady=(0, 2))
        linha += 1

        ttk.Label(principais, text="Categoria:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self.cbo_categoria = ttk.Combobox(
            principais,
            textvariable=self.vars["categoria"],
            state="normal",
        )
        self.cbo_categoria.grid(row=linha, column=1, sticky="ew", pady=3)
        self.cbo_categoria.configure(postcommand=self._atualizar_categorias)
        self.cbo_categoria.bind("<KeyRelease>", self._filtrar_categorias)
        self.cbo_categoria.bind(
            "<<ComboboxSelected>>", lambda _e: self.cbo_categoria.icursor(END)
        )
        ttk.Button(
            principais,
            text="＋ Nova categoria",
            command=self._nova_categoria,
        ).grid(row=linha, column=2, sticky="ew", padx=(8, 0), pady=3)
        linha += 1

        ttk.Label(principais, text="Valor:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self.ent_valor = ttk.Entry(principais, textvariable=self.vars["valor"])
        self.ent_valor.grid(row=linha, column=1, columnspan=2, sticky="ew", pady=3)
        linha += 1

        ttk.Label(principais, text="Vencimento:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self.ent_vencimento = ttk.Entry(
            principais,
            textvariable=self.vars["vencimento"],
            state="readonly",
        )
        self.ent_vencimento.grid(row=linha, column=1, sticky="ew", pady=3)
        self.btn_vencimento = ttk.Button(
            principais,
            text="📅 Escolher data",
            command=lambda: self._abrir_calendario("vencimento"),
        )
        self.btn_vencimento.grid(row=linha, column=2, sticky="ew", padx=(8, 0), pady=3)
        linha += 1

        ttk.Label(principais, text="Competência:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self.cbo_competencia_conta = ttk.Combobox(
            principais,
            textvariable=self.vars["competencia"],
            state="readonly",
        )
        self.cbo_competencia_conta.grid(
            row=linha, column=1, columnspan=2, sticky="ew", pady=3
        )

        self.quadro_detalhes = ttk.LabelFrame(
            corpo, text="Detalhes da conta", padding=8, style="Card.TLabelframe"
        )
        self.quadro_detalhes.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        self.quadro_detalhes.columnconfigure(1, weight=1)
        corpo.rowconfigure(2, weight=1)

        linha = 0
        ttk.Label(self.quadro_detalhes, text="Descrição:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=2
        )
        ttk.Entry(
            self.quadro_detalhes, textvariable=self.vars["descricao"]
        ).grid(row=linha, column=1, columnspan=2, sticky="ew", pady=2)
        linha += 1

        ttk.Label(self.quadro_detalhes, text="Data da baixa:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=2
        )
        ttk.Entry(
            self.quadro_detalhes,
            textvariable=self.vars["data_pagamento"],
            state="readonly",
        ).grid(row=linha, column=1, sticky="ew", pady=2)
        ttk.Button(
            self.quadro_detalhes,
            text="📅 Escolher / limpar",
            command=lambda: self._abrir_calendario(
                "data_pagamento", permitir_limpar=True
            ),
        ).grid(row=linha, column=2, sticky="ew", padx=(8, 0), pady=2)
        linha += 1

        ttk.Label(self.quadro_detalhes, text="Número do documento:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=2
        )
        ttk.Entry(
            self.quadro_detalhes, textvariable=self.vars["numero_documento"]
        ).grid(row=linha, column=1, columnspan=2, sticky="ew", pady=2)
        linha += 1

        ttk.Label(self.quadro_detalhes, text="Documento anexado:").grid(
            row=linha, column=0, sticky="w", padx=(0, 10), pady=2
        )
        ttk.Entry(
            self.quadro_detalhes, textvariable=self.vars["caminho_documento"]
        ).grid(row=linha, column=1, sticky="ew", pady=2)
        ttk.Button(
            self.quadro_detalhes,
            text="Selecionar PDF / imagem",
            command=self._selecionar_arquivo,
        ).grid(row=linha, column=2, sticky="ew", padx=(8, 0), pady=2)
        linha += 1

        ttk.Label(self.quadro_detalhes, text="Observações:").grid(
            row=linha, column=0, sticky="nw", padx=(0, 10), pady=2
        )
        self.txt_observacoes = Text(self.quadro_detalhes, height=2, wrap="word")
        self.txt_observacoes.grid(
            row=linha, column=1, columnspan=2, sticky="nsew", pady=2
        )
        self.txt_observacoes.insert(
            END,
            str(self.fonte.get("observacoes") or self.fonte.get("motivo") or ""),
        )
        self.quadro_detalhes.rowconfigure(linha, weight=1)

        ttk.Label(
            corpo,
            textvariable=self.var_feedback_salvamento,
            foreground=COR_SUCESSO,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=3, column=0, sticky="w", pady=(5, 0))

        botoes = ttk.Frame(corpo)
        botoes.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        botoes.columnconfigure(0, weight=1)
        botoes.columnconfigure(1, weight=1)
        ttk.Button(botoes, text="Cancelar", command=self.janela.destroy).grid(
            row=0, column=0, sticky="ew", padx=(0, 5)
        )
        self.btn_salvar_conta = ttk.Button(
            botoes,
            text="Salvar conta  •  Enter",
            command=self._salvar,
            style="Primary.TButton",
        )
        self.btn_salvar_conta.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        ttk.Label(
            corpo,
            text="Atalho: Enter avança pelos dados obrigatórios e salva quando o cadastro estiver completo. Ctrl+S também salva.",
            foreground=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8),
        ).grid(row=5, column=0, sticky="w", pady=(4, 0))

    @staticmethod
    def _primeiro_obrigatorio_pendente(dados: dict[str, object]) -> str:
        """Retorna o primeiro campo mínimo ainda necessário para salvar."""

        for chave in ("empresa", "fornecedor", "valor", "vencimento"):
            if not str(dados.get(chave) or "").strip():
                return chave
        return ""

    def _focar_obrigatorio_pendente(self, chave: str) -> None:
        if chave == "empresa":
            self.cbo_empresa_conta.focus_set()
        elif chave == "fornecedor":
            self.cbo_fornecedor.focus_set()
        elif chave == "valor":
            self.ent_valor.focus_set()
        elif chave == "vencimento":
            # O calendário é o único modo de preencher o vencimento, então
            # abrir diretamente deixa o fluxo por teclado realmente rápido.
            self._abrir_calendario("vencimento")

    def _atalho_enter_conta(self, evento=None):
        """Enter avança pelos obrigatórios e salva a conta quando estiver pronta."""

        foco = self.janela.focus_get()
        if foco is self.txt_observacoes:
            # Em observações, Enter continua sendo quebra de linha.
            return None

        try:
            classe = foco.winfo_class() if foco is not None else ""
        except Exception:
            classe = ""

        # Preserve o comportamento natural dos demais botões (calendário,
        # cancelar, selecionar arquivo etc.). No botão Salvar, Enter salva.
        if classe in {"TButton", "Button"}:
            if foco is getattr(self, "btn_salvar_conta", None):
                self._salvar()
                return "break"
            return None

        dados = {chave: variavel.get() for chave, variavel in self.vars.items()}
        fornecedor = str(dados.get("fornecedor") or "").strip()
        if fornecedor and not str(dados.get("fornecedor_cnpj") or "").strip():
            try:
                cnpjs = self.servico.repositorio.listar_cnpjs_fornecedor(fornecedor)
            except Exception:
                cnpjs = []
            if len(cnpjs) > 1:
                self._atualizar_cnpjs_fornecedor()
                self.cbo_fornecedor_cnpj.focus_set()
                return "break"
        pendente = self._primeiro_obrigatorio_pendente(dados)
        if pendente:
            self._focar_obrigatorio_pendente(pendente)
            return "break"

        self._salvar()
        return "break"

    def _fonte_tem_detalhes(self) -> bool:
        return any(
            str(self.fonte.get(chave) or "").strip()
            for chave in (
                "descricao",
                "tipo_documento",
                "data_pagamento",
                "numero_documento",
                "caminho_documento",
                "observacoes",
                "motivo",
            )
        )

    def _alternar_detalhes(self, mostrar: bool | None = None) -> None:
        """Compatibilidade: desde 17.8.77 os detalhes permanecem sempre visíveis."""
        self.detalhes_visiveis = True
        self.quadro_detalhes.grid()
        self.janela.after_idle(self._ajustar_altura)

    def _ajustar_altura(self) -> None:
        self.janela.update_idletasks()
        largura = max(self.janela.winfo_width(), 700)
        altura = min(720, self.janela.winfo_screenheight() - 60)
        self.janela.geometry(f"{largura}x{altura}")

    def _focar_primeiro_campo(self) -> None:
        if not self.vars["empresa"].get():
            self.cbo_empresa_conta.focus_set()
        else:
            self.cbo_fornecedor.focus_set()

    @staticmethod
    def _evento_apenas_navegacao(evento) -> bool:
        return evento is not None and evento.keysym in _TECLAS_NAVEGACAO_COMBO

    def _mostrar_lista_filtrada(self, combo: ttk.Combobox, valores) -> None:
        """Abre a lista do combobox sem tirar o cursor do texto digitado."""

        valores = list(valores or ())
        try:
            if not valores:
                combo.tk.call("ttk::combobox::Unpost", str(combo))
                return
        except Exception:
            return

        def abrir() -> None:
            try:
                if not combo.winfo_exists() or combo.focus_get() != combo:
                    return
                combo.tk.call("ttk::combobox::Post", str(combo))
                combo.icursor(END)
            except Exception:
                try:
                    combo.event_generate("<Down>")
                    combo.icursor(END)
                except Exception:
                    pass

        self.janela.after_idle(abrir)

    def _atualizar_fornecedores(self) -> None:
        atual = self.vars["fornecedor"].get()
        self.fornecedores_todos = self.servico.repositorio.listar_fornecedores()
        valores = filtrar_opcoes_por_inicio(self.fornecedores_todos, atual)
        self.cbo_fornecedor.configure(values=valores)
        self.vars["fornecedor"].set(atual)

    def _fornecedor_selecionado(self, _evento=None) -> None:
        self._esconder_sugestoes_fornecedor()
        atual = self.vars["fornecedor"].get().strip()
        mudou = atual.casefold() != self._fornecedor_cnpj_nome.casefold()
        self._fornecedor_cnpj_nome = atual
        if mudou:
            self.vars["fornecedor_cnpj"].set("")
        self.cbo_fornecedor.icursor(END)
        self._atualizar_cnpjs_fornecedor()
        if len(self.cnpjs_fornecedor) > 1 and not self.vars["fornecedor_cnpj"].get().strip():
            self.janela.after_idle(self.cbo_fornecedor_cnpj.focus_set)

    def _atualizar_cnpjs_fornecedor(self) -> None:
        fornecedor = self.vars["fornecedor"].get().strip()
        atual = self.vars["fornecedor_cnpj"].get().strip()
        atuais_digitos = "".join(ch for ch in atual if ch.isdigit())
        try:
            cnpjs = self.servico.repositorio.listar_cnpjs_fornecedor(fornecedor)
        except Exception:
            cnpjs = []
        self.cnpjs_fornecedor = list(cnpjs)
        formatados = [JanelaFornecedoresCNPJ._formatar_cnpj(cnpj) for cnpj in cnpjs]
        self.cbo_fornecedor_cnpj.configure(values=formatados)
        if atuais_digitos and atuais_digitos in cnpjs:
            self.vars["fornecedor_cnpj"].set(
                JanelaFornecedoresCNPJ._formatar_cnpj(atuais_digitos)
            )
        elif len(cnpjs) == 1 and not atuais_digitos:
            self.vars["fornecedor_cnpj"].set(
                JanelaFornecedoresCNPJ._formatar_cnpj(cnpjs[0])
            )

    def _esconder_sugestoes_fornecedor(self) -> None:
        popup = getattr(self, "_popup_sugestoes_fornecedor", None)
        try:
            if popup is not None and popup.winfo_exists():
                popup.withdraw()
        except Exception:
            pass

    def _selecionar_sugestao_fornecedor(self, evento=None):
        lista = getattr(self, "_lista_sugestoes_fornecedor", None)
        if lista is None:
            return "break"
        try:
            selecao = lista.curselection()
            indice = selecao[0] if selecao else lista.nearest(evento.y)
            nome = str(lista.get(indice)).strip()
        except Exception:
            return "break"

        if nome:
            self.vars["fornecedor"].set(nome)
            self.cbo_fornecedor.icursor(END)
            self._esconder_sugestoes_fornecedor()
            self._fornecedor_selecionado()
            self.cbo_fornecedor.focus_set()
        return "break"

    def _mostrar_sugestoes_fornecedor(self, valores) -> None:
        """Mostra sugestões sem transferir o foco para a lista."""
        valores = list(valores or ())
        termo = self.vars["fornecedor"].get().strip()

        if not termo or not valores:
            self._esconder_sugestoes_fornecedor()
            return

        popup = getattr(self, "_popup_sugestoes_fornecedor", None)
        lista = getattr(self, "_lista_sugestoes_fornecedor", None)

        try:
            popup_valido = popup is not None and popup.winfo_exists()
        except Exception:
            popup_valido = False

        if not popup_valido:
            popup = Toplevel(self.janela)
            popup.overrideredirect(True)
            try:
                popup.transient(self.janela)
            except Exception:
                pass

            lista = Listbox(
                popup,
                activestyle="none",
                exportselection=False,
                font=("Segoe UI", 9),
                relief="solid",
                borderwidth=1,
                highlightthickness=0,
            )
            lista.pack(fill=BOTH, expand=True)
            lista.bind("<ButtonRelease-1>", self._selecionar_sugestao_fornecedor)

            self._popup_sugestoes_fornecedor = popup
            self._lista_sugestoes_fornecedor = lista

        lista.delete(0, END)
        for valor in valores[:12]:
            lista.insert(END, valor)

        altura_linhas = min(8, max(1, len(valores)))
        try:
            self.janela.update_idletasks()
            x = self.cbo_fornecedor.winfo_rootx()
            y = self.cbo_fornecedor.winfo_rooty() + self.cbo_fornecedor.winfo_height()
            largura = max(300, self.cbo_fornecedor.winfo_width())
            altura = 22 * altura_linhas + 4
            popup.geometry(f"{largura}x{altura}+{x}+{y}")
            popup.deiconify()
            popup.lift()
        except Exception:
            return

        # O ponto principal da correção: a lista aparece, mas o teclado
        # continua pertencendo ao campo Fornecedor.
        self.cbo_fornecedor.focus_set()
        self.cbo_fornecedor.icursor(END)

    def _filtrar_fornecedores(self, evento=None) -> None:
        if self._evento_apenas_navegacao(evento):
            return

        valores = filtrar_opcoes_por_inicio(
            self.fornecedores_todos, self.vars["fornecedor"].get()
        )
        self.cbo_fornecedor.configure(values=valores)
        self._mostrar_sugestoes_fornecedor(valores)

    def _atualizar_categorias(self) -> None:
        atual = self.vars["categoria"].get()
        self.categorias_todas = self.servico.repositorio.listar_categorias()
        valores = filtrar_opcoes_por_inicio(self.categorias_todas, atual)
        self.cbo_categoria.configure(values=valores)
        if atual:
            self.vars["categoria"].set(atual)
        elif self.categorias_todas:
            padrao = "OUTROS" if "OUTROS" in self.categorias_todas else self.categorias_todas[0]
            self.vars["categoria"].set(padrao)

    def _filtrar_categorias(self, evento=None) -> None:
        if self._evento_apenas_navegacao(evento):
            return
        valores = filtrar_opcoes_por_inicio(
            self.categorias_todas, self.vars["categoria"].get()
        )
        self.cbo_categoria.configure(values=valores)
        self._mostrar_lista_filtrada(self.cbo_categoria, valores)

    def _nova_categoria(self) -> None:
        nome = simpledialog.askstring(
            "Nova categoria",
            "Digite o nome da nova categoria:",
            parent=self.janela,
        )
        if nome is None:
            return
        try:
            categoria = self.servico.repositorio.salvar_categoria(nome)
        except Exception as erro:
            messagebox.showerror("Nova categoria", str(erro), parent=self.janela)
            return
        self._atualizar_categorias()
        self.vars["categoria"].set(categoria)

    def _atualizar_competencias(self, selecionar: str | None = None) -> None:
        adicionais: list[str] = list(self.servico.repositorio.listar_competencias())
        adicionais.append(self.vars["competencia"].get())
        vencimento = self.vars["vencimento"].get()
        try:
            data_vencimento = datetime.strptime(vencimento, "%d/%m/%Y")
            adicionais.append(data_vencimento.strftime("%m/%Y"))
        except ValueError:
            pass
        valores = self.servico.opcoes_competencia(adicionais=adicionais)
        self.cbo_competencia_conta.configure(values=valores)
        if selecionar:
            self.vars["competencia"].set(selecionar)
        elif self.vars["competencia"].get() not in valores:
            self.vars["competencia"].set(date.today().strftime("%m/%Y"))

    def _abrir_calendario(self, chave: str, permitir_limpar: bool = False) -> None:
        callback = self._ao_vencimento if chave == "vencimento" else None
        SeletorDataPopup(
            self.janela,
            self.vars[chave],
            titulo=(
                "Selecionar vencimento"
                if chave == "vencimento"
                else "Selecionar data do pagamento"
            ),
            permitir_limpar=permitir_limpar,
            ao_selecionar=callback,
        )

    def _ao_vencimento(self, texto: str) -> None:
        try:
            data_vencimento = datetime.strptime(texto, "%d/%m/%Y")
        except ValueError:
            return
        self._atualizar_competencias(data_vencimento.strftime("%m/%Y"))
        # Depois de escolher a data, o próximo Enter já pode salvar.
        self.janela.after_idle(self.cbo_competencia_conta.focus_set)

    def _selecionar_arquivo(self) -> None:
        arquivo = filedialog.askopenfilename(
            title="Vincular documento",
            filetypes=[
                ("PDF e imagens", "*.pdf *.jpg *.jpeg *.png *.webp"),
                ("PDF", "*.pdf"),
                ("Imagens", "*.jpg *.jpeg *.png *.webp"),
            ],
            parent=self.janela,
        )
        if arquivo:
            self.vars["caminho_documento"].set(arquivo)

    def _cadastro_manual_novo(self) -> bool:
        """Indica quando a janela deve continuar aberta após salvar."""

        return self.conta_id is None and self.fila_id is None and self.agenda_item_id is None

    def _preparar_proxima_conta(self, conta_id: int | None = None) -> None:
        """Limpa o formulário e mantém empresa/competência para o próximo lançamento."""

        empresa = self.vars["empresa"].get()
        competencia = self.vars["competencia"].get() or date.today().strftime("%m/%Y")

        for chave in (
            "fornecedor",
            "fornecedor_cnpj",
            "descricao",
            "valor",
            "vencimento",
            "data_pagamento",
            "numero_documento",
            "caminho_documento",
        ):
            self.vars[chave].set("")

        self.vars["empresa"].set(empresa)
        self.vars["categoria"].set("OUTROS")
        self.vars["competencia"].set(competencia)
        self.txt_observacoes.delete("1.0", END)

        self._fornecedor_cnpj_nome = ""
        self._atualizar_fornecedores()
        self._atualizar_cnpjs_fornecedor()
        self._atualizar_categorias()
        self._atualizar_competencias(selecionar=competencia)
        self._alternar_detalhes(False)

        identificador = f" (ID {conta_id})" if conta_id else ""
        self.var_feedback_salvamento.set(
            f"Conta salva com sucesso{identificador}. Cadastre a próxima."
        )
        self.janela.after_idle(self.cbo_fornecedor.focus_set)

    def _salvar(self) -> None:
        dados = {chave: variavel.get() for chave, variavel in self.vars.items()}
        dados.update(
            {
                "observacoes": self.txt_observacoes.get("1.0", END).strip(),
                "origem": self.origem,
                "robo_documento_id": self.robo_documento_id,
            }
        )
        try:
            conta_id, duplicados = self.servico.salvar_conta(
                dados, conta_id=self.conta_id
            )
            if duplicados:
                texto = "\n".join(
                    f"ID {item['id']} — {item['fornecedor']} — "
                    f"{self.servico.data_br(item['vencimento'])} — "
                    f"{self.servico.valor_br(item['valor'])}"
                    for item in duplicados[:5]
                )
                confirmar = messagebox.askyesno(
                    "Possível duplicidade",
                    "O FiscalPro encontrou lançamento semelhante:\n\n"
                    + texto
                    + "\n\nDeseja salvar mesmo assim?",
                    parent=self.janela,
                )
                if not confirmar:
                    return
                conta_id, _ = self.servico.salvar_conta(
                    dados, conta_id=self.conta_id, permitir_duplicidade=True
                )
        except Exception as erro:
            messagebox.showerror("Salvar conta", str(erro), parent=self.janela)
            return
        if self.fila_id and conta_id:
            self.servico.repositorio.atualizar_status_fila(
                self.fila_id, "IMPORTADO", f"Conta criada: {conta_id}"
            )
        if self.agenda_item_id and conta_id:
            self.servico.agenda.vincular_conta(self.agenda_item_id, int(conta_id))
        if self.ao_salvar:
            self.ao_salvar()

        if self._cadastro_manual_novo():
            self._preparar_proxima_conta(conta_id)
            return

        self.janela.destroy()


class JanelaAgendaFaturas:
    """Agenda mensal de contas recorrentes que precisam ser buscadas/baixadas."""

    def __init__(self, master, servico: ContasPagarServico, *, ao_atualizar=None):
        self.master = master
        self.servico = servico
        self.ao_atualizar = ao_atualizar
        self.janela = Toplevel(master)
        self.janela.title("Agenda Inteligente de Faturas")
        self.janela.transient(master.winfo_toplevel())
        dimensionar_janela(self.janela, 1280, 760, 980, 620)

        self.var_empresa = StringVar(value="Todas")
        self.var_competencia = StringVar(value=date.today().strftime("%m/%Y"))
        self.var_status = StringVar(value="Pendentes")
        self.var_concluidos = BooleanVar(value=False)
        self.vars_cards = {
            "baixar": StringVar(value="0"),
            "vencendo": StringVar(value="0"),
            "nao_lancadas": StringVar(value="0"),
            "concluidas": StringVar(value="0"),
        }
        self._montar()
        self.atualizar()

    def _montar(self) -> None:
        topo = Frame(self.janela, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)
        topo.pack(fill=X, padx=10, pady=(10, 6))
        Frame(topo, bg=COR_DESTAQUE, height=3).pack(fill=X)
        Label(
            topo, text="Agenda Inteligente de Faturas", bg=COR_CARD, fg=COR_TEXTO,
            font=("Segoe UI", 14, "bold"), padx=12, pady=6,
        ).pack(anchor="w")
        Label(
            topo,
            text=("Controle água, energia, internet, telefone e outras faturas recorrentes "
                  "antes de elas virarem lançamentos no Contas a Pagar."),
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 9), padx=12, pady=3,
        ).pack(anchor="w")

        cards = ttk.Frame(self.janela, padding=(10, 0, 10, 6), style="Page.TFrame")
        cards.pack(fill=X)
        for col in range(4):
            cards.columnconfigure(col, weight=1, uniform="agenda")
        self._card(cards, 0, "Faturas para baixar", self.vars_cards["baixar"], COR_ALERTA)
        self._card(cards, 1, "Vencendo em 7 dias", self.vars_cards["vencendo"], COR_ERRO)
        self._card(cards, 2, "Ainda não lançadas", self.vars_cards["nao_lancadas"], COR_DESTAQUE)
        self._card(cards, 3, "Concluídas no mês", self.vars_cards["concluidas"], COR_SUCESSO)

        filtros = ttk.LabelFrame(self.janela, text="Filtros", padding=8, style="Card.TLabelframe")
        filtros.pack(fill=X, padx=10, pady=(0, 6))
        ttk.Label(filtros, text="Empresa:").grid(row=0, column=0, sticky="w")
        self.cbo_empresa = ttk.Combobox(filtros, textvariable=self.var_empresa, state="readonly", width=25)
        self.cbo_empresa.grid(row=0, column=1, padx=(5, 14), sticky="w")
        self.cbo_empresa.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())

        ttk.Label(filtros, text="Competência:").grid(row=0, column=2, sticky="w")
        self.cbo_comp = ttk.Combobox(filtros, textvariable=self.var_competencia, state="readonly", width=12)
        self.cbo_comp.grid(row=0, column=3, padx=(5, 14), sticky="w")
        self.cbo_comp.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())

        ttk.Label(filtros, text="Situação:").grid(row=0, column=4, sticky="w")
        self.cbo_status = ttk.Combobox(
            filtros, textvariable=self.var_status,
            values=("Pendentes", "Todos", STATUS_AGUARDANDO, STATUS_BAIXADA, STATUS_LANCADA, STATUS_PAGA),
            state="readonly", width=20,
        )
        self.cbo_status.grid(row=0, column=5, padx=(5, 14), sticky="w")
        self.cbo_status.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())
        ttk.Button(filtros, text="Atualizar", command=self.atualizar).grid(row=0, column=6, sticky="ew")
        filtros.columnconfigure(7, weight=1)

        quadro = ttk.Frame(self.janela, padding=(10, 0, 10, 0))
        quadro.pack(fill=BOTH, expand=True)
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)
        colunas = ("id", "sinal", "competencia", "empresa", "fornecedor", "tipo", "prevista", "vencimento", "status", "conta")
        self.tabela = ttk.Treeview(quadro, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "id":"ID", "sinal":"Alerta", "competencia":"Competência", "empresa":"Empresa",
            "fornecedor":"Fornecedor", "tipo":"Fatura", "prevista":"Baixar a partir de",
            "vencimento":"Vencimento previsto", "status":"Etapa", "conta":"Conta ID",
        }
        larguras = {
            "id":50, "sinal":235, "competencia":90, "empresa":160, "fornecedor":210,
            "tipo":110, "prevista":110, "vencimento":120, "status":135, "conta":70,
        }
        for coluna in colunas:
            self.tabela.heading(coluna, text=titulos[coluna])
            self.tabela.column(coluna, width=larguras[coluna], minwidth=50, anchor="w")
        self.tabela.tag_configure("CRITICO", foreground=COR_ERRO)
        self.tabela.tag_configure("ALERTA", foreground="#B35A00")
        self.tabela.tag_configure("ATENCAO", foreground="#8A6D00")
        self.tabela.tag_configure("OK", foreground=COR_SUCESSO)
        self.tabela.tag_configure("CONCLUIDA", foreground=COR_TEXTO_SUAVE)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        by = ttk.Scrollbar(quadro, orient="vertical", command=self.tabela.yview)
        bx = ttk.Scrollbar(quadro, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=by.set, xscrollcommand=bx.set)
        by.grid(row=0, column=1, sticky="ns")
        bx.grid(row=1, column=0, sticky="ew")
        self.tabela.bind("<Double-1>", lambda _e: self._lancar_conta())
        self.tabela.bind("<<TreeviewSelect>>", lambda _e: self._atualizar_estado_botoes())

        botoes = ttk.Frame(self.janela, padding=10)
        botoes.pack(fill=X)
        for col in range(8):
            botoes.columnconfigure(col, weight=1)
        ttk.Button(botoes, text="＋ Novo lembrete", command=self._novo, style="Primary.TButton").grid(row=0, column=0, sticky="ew", padx=(0,3))
        ttk.Button(botoes, text="Editar lembrete", command=self._editar).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(botoes, text="✓ Fatura baixada", command=self._marcar_baixada, style="Accent.TButton").grid(row=0, column=2, sticky="ew", padx=3)
        self.btn_lancar_agenda = ttk.Button(
            botoes, text="Lançar no Contas a Pagar", command=self._lancar_conta,
            style="Primary.TButton", state="disabled",
        )
        self.btn_lancar_agenda.grid(row=0, column=3, sticky="ew", padx=3)
        ttk.Button(botoes, text="✓ Dar baixa hoje", command=self._dar_baixa_hoje, style="Accent.TButton").grid(row=0, column=4, sticky="ew", padx=3)
        ttk.Button(botoes, text="Reabrir aguardando", command=self._reabrir).grid(row=0, column=5, sticky="ew", padx=3)
        ttk.Button(botoes, text="Desativar lembrete", command=self._desativar, style="Danger.TButton").grid(row=0, column=6, sticky="ew", padx=3)
        ttk.Button(botoes, text="Fechar", command=self.janela.destroy).grid(row=0, column=7, sticky="ew", padx=(3,0))

    @staticmethod
    def _card(master, coluna, titulo, variavel, cor):
        quadro = Frame(master, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA, padx=8, pady=6)
        quadro.grid(row=0, column=coluna, sticky="nsew", padx=(0 if coluna == 0 else 4, 0))
        Label(quadro, text=titulo, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).pack()
        Label(quadro, textvariable=variavel, bg=COR_CARD, fg=cor, font=("Segoe UI", 14, "bold")).pack(pady=(2,0))

    def _filtros(self):
        empresa = "" if self.var_empresa.get() == "Todas" else self.var_empresa.get()
        comp = "" if self.var_competencia.get() == "Todas" else self.var_competencia.get()
        situacao = self.var_status.get()
        status = "" if situacao in {"Todos", "Pendentes"} else situacao
        incluir = situacao == "Todos" or status == STATUS_PAGA
        return empresa, comp, status, incluir

    def atualizar(self):
        empresas = ("Todas", *self.servico.repositorio.listar_empresas())
        self.cbo_empresa.configure(values=empresas)
        if self.var_empresa.get() not in empresas:
            self.var_empresa.set("Todas")

        atual = date.today().strftime("%Y-%m")
        proxima = self.servico.agenda._somar_meses(atual, 1)
        comps = ("Todas", self.servico.agenda.competencia_br(atual), self.servico.agenda.competencia_br(proxima))
        self.cbo_comp.configure(values=comps)
        if self.var_competencia.get() not in comps:
            self.var_competencia.set(self.servico.agenda.competencia_br(atual))

        empresa, comp, status, incluir = self._filtros()
        itens = self.servico.agenda.listar_itens(
            empresa=empresa, competencia=comp, status=status, incluir_concluidos=incluir
        )
        if self.var_status.get() == "Pendentes":
            itens = [i for i in itens if i["status"] != STATUS_PAGA]

        for item in self.tabela.get_children():
            self.tabela.delete(item)
        for linha in itens:
            sinal = str(linha["sinalizacao"])
            if sinal.startswith("🔴"):
                tag = "CRITICO"
            elif sinal.startswith("🟠"):
                tag = "ALERTA"
            elif sinal.startswith("🟡"):
                tag = "ATENCAO"
            elif sinal.startswith("✅"):
                tag = "CONCLUIDA"
            else:
                tag = "OK"
            self.tabela.insert(
                "", END, iid=str(linha["id"]),
                values=(
                    linha["id"], sinal, self.servico.agenda.competencia_br(str(linha["competencia"])),
                    linha["empresa"], linha["fornecedor"], linha["tipo_fatura"],
                    self.servico.data_br(str(linha["data_prevista"])),
                    self.servico.data_br(str(linha["vencimento_previsto"])),
                    linha["status"], linha["conta_id"] or "",
                ), tags=(tag,)
            )

        resumo = self.servico.agenda.resumo(empresa=empresa)
        self.vars_cards["baixar"].set(str(resumo["para_baixar"]))
        self.vars_cards["vencendo"].set(str(resumo["vencendo_7_dias"]))
        self.vars_cards["nao_lancadas"].set(str(resumo["nao_lancadas"]))
        self.vars_cards["concluidas"].set(str(resumo["concluidas_mes"]))
        self._atualizar_estado_botoes()
        if self.ao_atualizar:
            self.ao_atualizar()

    def _atualizar_estado_botoes(self) -> None:
        """Habilita o lançamento somente para fatura ainda sem conta vinculada."""
        habilitar_lancamento = False
        selecao = self.tabela.selection()
        if selecao:
            try:
                item = self.servico.agenda.obter_item(int(selecao[0]))
            except (TypeError, ValueError):
                item = None
            if item is not None:
                habilitar_lancamento = not bool(item["conta_id"])

        self.btn_lancar_agenda.configure(
            state="normal" if habilitar_lancamento else "disabled"
        )

    def _selecionado(self):
        selecao = self.tabela.selection()
        if not selecao:
            messagebox.showwarning("Agenda de Faturas", "Selecione um lembrete mensal.", parent=self.janela)
            return None
        return self.servico.agenda.obter_item(int(selecao[0]))

    def _novo(self):
        JanelaLembreteFatura(self.janela, self.servico, ao_salvar=self.atualizar)

    def _editar(self):
        item = self._selecionado()
        if not item:
            return
        lembrete = self.servico.agenda.obter_lembrete(int(item["lembrete_id"]))
        if lembrete:
            JanelaLembreteFatura(
                self.janela, self.servico, lembrete=lembrete,
                lembrete_id=int(item["lembrete_id"]), ao_salvar=self.atualizar,
            )

    def _marcar_baixada(self):
        item = self._selecionado()
        if not item:
            return
        if item["status"] in {STATUS_LANCADA, STATUS_PAGA}:
            messagebox.showwarning("Agenda de Faturas", "Essa fatura já foi lançada no Contas a Pagar.", parent=self.janela)
            return
        caminho = ""
        if messagebox.askyesno(
            "Fatura baixada", "Deseja vincular o arquivo da fatura agora?", parent=self.janela
        ):
            caminho = filedialog.askopenfilename(title="Selecionar fatura baixada", parent=self.janela)
        self.servico.agenda.marcar_fatura_baixada(int(item["id"]), caminho)
        self.atualizar()

    def _lancar_conta(self):
        item = self._selecionado()
        if not item:
            return
        if item["conta_id"]:
            messagebox.showinfo(
                "Agenda de Faturas",
                f"Essa fatura já está vinculada à conta ID {item['conta_id']}.",
                parent=self.janela,
            )
            return
        dados = self.servico.agenda.prefill_conta(int(item["id"]))
        JanelaContaPagar(
            self.janela, self.servico, dados=dados, agenda_item_id=int(item["id"]),
            ao_salvar=self.atualizar,
        )

    def _dar_baixa_hoje(self):
        item = self._selecionado()
        if not item:
            return
        if item["status"] == STATUS_PAGA:
            messagebox.showinfo(
                "Agenda de Faturas",
                "Essa fatura já está marcada como paga.",
                parent=self.janela,
            )
            return
        conta_id = int(item["conta_id"]) if item["conta_id"] else None
        if conta_id is None:
            candidatos = self.servico.agenda.localizar_contas_candidatas(int(item["id"]))
            if not candidatos:
                messagebox.showwarning(
                    "Agenda de Faturas",
                    "Essa fatura ainda não está vinculada ao Contas a Pagar.\n\n"
                    "O FiscalPro não encontrou um lançamento compatível.\n\n"
                    "Se a conta ainda não existir, use 'Lançar no Contas a Pagar'.",
                    parent=self.janela,
                )
                return

            if len(candidatos) == 1:
                conta_id = int(candidatos[0]["id"])
            else:
                linhas = []
                for candidato in candidatos[:8]:
                    valor = self.servico.valor_br(candidato["valor"])
                    venc = self.servico.data_br(str(candidato["vencimento"] or ""))
                    pago = " • PAGO" if str(candidato["status"] or "") == "PAGO" else ""
                    linhas.append(
                        f"ID {candidato['id']} — {candidato['fornecedor']} — {venc} — {valor}{pago}"
                    )
                escolha = simpledialog.askinteger(
                    "Vincular conta existente",
                    "Encontrei mais de uma conta compatível no Contas a Pagar.\n\n"
                    + "\n".join(linhas)
                    + "\n\nDigite o ID da conta correta:",
                    parent=self.janela,
                )
                ids_validos = {int(c["id"]) for c in candidatos}
                if escolha is None:
                    return
                if int(escolha) not in ids_validos:
                    messagebox.showwarning(
                        "Agenda de Faturas",
                        "O ID informado não está entre as contas compatíveis encontradas.",
                        parent=self.janela,
                    )
                    return
                conta_id = int(escolha)

            conta_encontrada = self.servico.repositorio.obter_conta(int(conta_id))
            if not conta_encontrada:
                messagebox.showwarning(
                    "Agenda de Faturas",
                    "A conta encontrada não está mais disponível no Contas a Pagar.",
                    parent=self.janela,
                )
                return
            if not messagebox.askyesno(
                "Vincular conta existente",
                f"Encontrei a conta ID {conta_id} já lançada para {conta_encontrada['fornecedor']}.\n"
                f"Vencimento: {self.servico.data_br(str(conta_encontrada['vencimento']))} • "
                f"Valor: {self.servico.valor_br(conta_encontrada['valor'])}.\n\n"
                "Deseja vincular esta conta à Agenda e continuar a baixa?",
                parent=self.janela,
            ):
                return
            self.servico.agenda.vincular_conta(int(item["id"]), int(conta_id))
            item = self.servico.agenda.obter_item(int(item["id"]))

        conta = self.servico.repositorio.obter_conta(int(conta_id))
        if not conta:
            messagebox.showwarning(
                "Agenda de Faturas",
                "A conta vinculada não foi encontrada no Contas a Pagar. Atualize ou refaça o vínculo.",
                parent=self.janela,
            )
            return
        if not messagebox.askyesno(
            "Dar baixa hoje",
            f"Marcar como paga hoje a conta ID {conta_id} — {item['fornecedor']}?",
            parent=self.janela,
        ):
            return
        try:
            self.servico.dar_baixa_conta(int(conta_id))
        except ValueError as erro:
            messagebox.showerror("Agenda de Faturas", str(erro), parent=self.janela)
            return
        self.atualizar()

    def _reabrir(self):
        item = self._selecionado()
        if not item:
            return
        if item["conta_id"]:
            messagebox.showwarning(
                "Agenda de Faturas",
                "A fatura está vinculada a uma conta. Exclua/reabra o lançamento antes de voltar para aguardando.",
                parent=self.janela,
            )
            return
        self.servico.agenda.marcar_aguardando(int(item["id"]))
        self.atualizar()

    def _desativar(self):
        item = self._selecionado()
        if not item:
            return
        if not messagebox.askyesno(
            "Desativar lembrete",
            f"Parar de gerar novas competências para {item['fornecedor']} — {item['tipo_fatura']}?\n\n"
            "O histórico já criado será preservado.", parent=self.janela,
        ):
            return
        self.servico.agenda.desativar_lembrete(int(item["lembrete_id"]))
        self.atualizar()


class JanelaLembreteFatura:
    """Cadastro de uma obrigação mensal recorrente da Agenda de Faturas."""

    CATEGORIA_POR_TIPO = {
        "ÁGUA": "ÁGUA",
        "ENERGIA": "ENERGIA",
        "INTERNET": "INTERNET E TELEFONIA",
        "TELEFONE": "INTERNET E TELEFONIA",
    }

    def __init__(self, master, servico: ContasPagarServico, *, lembrete=None, lembrete_id=None, ao_salvar=None):
        self.servico = servico
        self.lembrete_id = lembrete_id
        self.ao_salvar = ao_salvar
        fonte = dict(lembrete) if lembrete is not None else {}
        empresas = self.servico.repositorio.listar_empresas()
        empresa_inicial = str(fonte.get("empresa") or (empresas[0] if empresas else ""))
        self.vars = {
            "empresa": StringVar(value=empresa_inicial),
            "fornecedor": StringVar(value=str(fonte.get("fornecedor") or "")),
            "tipo_fatura": StringVar(value=str(fonte.get("tipo_fatura") or "ENERGIA")),
            "categoria": StringVar(value=str(fonte.get("categoria") or "ENERGIA")),
            "dia_disponibilidade": StringVar(value=str(fonte.get("dia_disponibilidade") or 1)),
            "dia_vencimento": StringVar(value=str(fonte.get("dia_vencimento") or 10)),
            "dias_alerta": StringVar(value=str(fonte.get("dias_alerta") if fonte.get("dias_alerta") is not None else 3)),
            "competencia_inicial": StringVar(value=self.servico.agenda.competencia_br(str(fonte.get("competencia_inicial") or date.today().strftime("%Y-%m")))),
        }
        self.var_recorrente = BooleanVar(value=bool(fonte.get("recorrente", 1)))
        self.janela = Toplevel(master)
        self.janela.title("Editar lembrete de fatura" if lembrete_id else "Novo lembrete de fatura")
        self.janela.transient(master.winfo_toplevel())
        self.janela.grab_set()
        dimensionar_janela(self.janela, 720, 590, 660, 520, maximizar_em_tela_baixa=False)
        self._montar(str(fonte.get("observacoes") or ""))

    def _montar(self, observacoes):
        corpo = ttk.Frame(self.janela, padding=14)
        corpo.pack(fill=BOTH, expand=True)
        corpo.columnconfigure(1, weight=1)
        ttk.Label(corpo, text="Lembrete mensal de fatura", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            corpo,
            text="Cadastre uma vez. O FiscalPro gera a obrigação mensal sem exigir valor antecipado.",
            foreground=COR_TEXTO_SUAVE,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2,10))

        linha = 2
        def rotulo(texto):
            nonlocal linha
            ttk.Label(corpo, text=texto).grid(row=linha, column=0, sticky="w", padx=(0,10), pady=5)

        rotulo("Empresa:")
        ttk.Combobox(corpo, textvariable=self.vars["empresa"], values=self.servico.repositorio.listar_empresas(), state="readonly").grid(row=linha, column=1, columnspan=2, sticky="ew", pady=5); linha += 1
        rotulo("Fornecedor:")
        ttk.Combobox(corpo, textvariable=self.vars["fornecedor"], values=self.servico.repositorio.listar_fornecedores(), state="normal").grid(row=linha, column=1, columnspan=2, sticky="ew", pady=5); linha += 1
        rotulo("Tipo de fatura:")
        combo_tipo = ttk.Combobox(corpo, textvariable=self.vars["tipo_fatura"], values=TIPOS_FATURA, state="readonly")
        combo_tipo.grid(row=linha, column=1, sticky="ew", pady=5)
        combo_tipo.bind("<<ComboboxSelected>>", lambda _e: self._ajustar_categoria())
        ttk.Entry(corpo, textvariable=self.vars["categoria"]).grid(row=linha, column=2, sticky="ew", padx=(8,0), pady=5); linha += 1
        rotulo("Disponível por volta do dia:")
        ttk.Entry(corpo, textvariable=self.vars["dia_disponibilidade"], width=8).grid(row=linha, column=1, sticky="w", pady=5)
        ttk.Label(corpo, text="(1 a 31)", foreground=COR_TEXTO_SUAVE).grid(row=linha, column=2, sticky="w", padx=(8,0)); linha += 1
        rotulo("Vencimento previsto — dia:")
        ttk.Entry(corpo, textvariable=self.vars["dia_vencimento"], width=8).grid(row=linha, column=1, sticky="w", pady=5)
        ttk.Label(corpo, text="A data real poderá ser ajustada ao lançar a conta.", foreground=COR_TEXTO_SUAVE).grid(row=linha, column=2, sticky="w", padx=(8,0)); linha += 1
        rotulo("Avisar com antecedência:")
        ttk.Entry(corpo, textvariable=self.vars["dias_alerta"], width=8).grid(row=linha, column=1, sticky="w", pady=5)
        ttk.Label(corpo, text="dias antes da data prevista para baixar", foreground=COR_TEXTO_SUAVE).grid(row=linha, column=2, sticky="w", padx=(8,0)); linha += 1
        rotulo("Começar na competência:")
        atual = date.today().strftime("%Y-%m")
        prox = self.servico.agenda._somar_meses(atual, 1)
        valores_comp = self.servico.opcoes_competencia(adicionais=(atual, prox))
        ttk.Combobox(corpo, textvariable=self.vars["competencia_inicial"], values=valores_comp, state="readonly").grid(row=linha, column=1, sticky="ew", pady=5)
        ttk.Checkbutton(corpo, text="Repetir todo mês", variable=self.var_recorrente).grid(row=linha, column=2, sticky="w", padx=(8,0)); linha += 1

        ttk.Label(corpo, text="Observações:").grid(row=linha, column=0, sticky="nw", padx=(0,10), pady=5)
        self.txt_obs = Text(corpo, height=5, wrap="word")
        self.txt_obs.grid(row=linha, column=1, columnspan=2, sticky="nsew", pady=5)
        self.txt_obs.insert(END, observacoes)
        corpo.rowconfigure(linha, weight=1); linha += 1

        botoes = ttk.Frame(corpo)
        botoes.grid(row=linha, column=0, columnspan=3, sticky="ew", pady=(10,0))
        botoes.columnconfigure(0, weight=1); botoes.columnconfigure(1, weight=1)
        ttk.Button(botoes, text="Cancelar", command=self.janela.destroy).grid(row=0, column=0, sticky="ew", padx=(0,5))
        ttk.Button(botoes, text="Salvar lembrete", command=self._salvar, style="Primary.TButton").grid(row=0, column=1, sticky="ew", padx=(5,0))

    def _ajustar_categoria(self):
        tipo = self.vars["tipo_fatura"].get()
        sugerida = self.CATEGORIA_POR_TIPO.get(tipo, "OUTROS")
        self.vars["categoria"].set(sugerida)

    def _salvar(self):
        dados = {chave: var.get() for chave, var in self.vars.items()}
        dados["recorrente"] = self.var_recorrente.get()
        dados["ativa"] = True
        dados["observacoes"] = self.txt_obs.get("1.0", END).strip()
        try:
            self.servico.agenda.salvar_lembrete(dados, lembrete_id=self.lembrete_id)
        except Exception as erro:
            messagebox.showerror("Agenda de Faturas", str(erro), parent=self.janela)
            return
        if self.ao_salvar:
            self.ao_salvar()
        self.janela.destroy()


class JanelaFilaFinanceira:
    def __init__(self, master, servico: ContasPagarServico, *, ao_importar=None):
        self.master = master
        self.servico = servico
        self.ao_importar = ao_importar
        self.janela = Toplevel(master)
        self.janela.title("Fila financeira do Robô FiscalPro")
        self.janela.transient(master.winfo_toplevel())
        dimensionar_janela(self.janela, 1180, 720, 900, 600)
        self.var_status = StringVar(value="Pendentes")
        self.var_resumo = StringVar(value="")
        self._montar()
        self.atualizar()

    def _montar(self) -> None:
        topo = ttk.Frame(self.janela, padding=10)
        topo.pack(fill=X)
        ttk.Label(
            topo,
            text="Documentos encontrados pelo robô",
            font=("Segoe UI", 12, "bold"),
        ).pack(side=LEFT)
        ttk.Button(
            topo,
            text="Sincronizar documentos",
            command=self._sincronizar,
            style="Accent.TButton",
        ).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(topo, text="Atualizar", command=self.atualizar).pack(side=RIGHT)

        filtros = ttk.Frame(self.janela, padding=(10, 0, 10, 8))
        filtros.pack(fill=X)
        ttk.Label(filtros, text="Mostrar:").pack(side=LEFT)
        combo = ttk.Combobox(
            filtros,
            textvariable=self.var_status,
            values=("Pendentes", "Todos", "NOVO", "REVISAR", "IMPORTADO", "DUPLICADO", "IGNORADO"),
            state="readonly",
            width=14,
        )
        combo.pack(side=LEFT, padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())
        ttk.Label(filtros, textvariable=self.var_resumo).pack(side=RIGHT)

        quadro = ttk.Frame(self.janela, padding=(10, 0, 10, 0))
        quadro.pack(fill=BOTH, expand=True)
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)
        colunas = (
            "id", "status", "empresa", "fornecedor", "tipo", "numero", "vencimento",
            "valor", "competencia", "motivo",
        )
        self.tabela = ttk.Treeview(quadro, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "id":"ID", "status":"Situação", "empresa":"Empresa", "fornecedor":"Fornecedor",
            "tipo":"Documento", "numero":"Número", "vencimento":"Vencimento",
            "valor":"Valor", "competencia":"Competência", "motivo":"Revisão",
        }
        larguras = {
            "id":55, "status":90, "empresa":170, "fornecedor":190, "tipo":120,
            "numero":100, "vencimento":95, "valor":105, "competencia":90, "motivo":260,
        }
        for coluna in colunas:
            self.tabela.heading(coluna, text=titulos[coluna])
            self.tabela.column(coluna, width=larguras[coluna], anchor="w")
        self.tabela.grid(row=0, column=0, sticky="nsew")
        by = ttk.Scrollbar(quadro, orient="vertical", command=self.tabela.yview)
        bx = ttk.Scrollbar(quadro, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=by.set, xscrollcommand=bx.set)
        by.grid(row=0, column=1, sticky="ns")
        bx.grid(row=1, column=0, sticky="ew")
        self.tabela.bind("<Double-1>", lambda _e: self._aprovar())

        botoes = ttk.Frame(self.janela, padding=10)
        botoes.pack(fill=X)
        for coluna in range(5):
            botoes.columnconfigure(coluna, weight=1)
        ttk.Button(
            botoes, text="Aprovar e lançar", command=self._aprovar, style="Primary.TButton"
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(botoes, text="Abrir documento", command=self._abrir_documento).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(botoes, text="Marcar duplicado", command=lambda: self._status("DUPLICADO")).grid(
            row=0, column=2, sticky="ew", padx=4
        )
        ttk.Button(botoes, text="Ignorar", command=lambda: self._status("IGNORADO")).grid(
            row=0, column=3, sticky="ew", padx=4
        )
        ttk.Button(botoes, text="Fechar", command=self.janela.destroy).grid(
            row=0, column=4, sticky="ew", padx=(4, 0)
        )

    def _statuses(self):
        atual = self.var_status.get()
        if atual == "Pendentes":
            return ("NOVO", "REVISAR")
        if atual == "Todos":
            return None
        return (atual,)

    def atualizar(self) -> None:
        linhas = self.servico.repositorio.listar_fila(self._statuses())
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        for linha in linhas:
            self.tabela.insert(
                "", END, iid=str(linha["id"]), values=(
                    linha["id"], linha["status"], linha["empresa"], linha["fornecedor"],
                    linha["tipo_documento"], linha["numero_documento"],
                    self.servico.data_br(linha["vencimento"]),
                    self.servico.valor_br(linha["valor"]) if linha["valor"] else "",
                    self.servico.competencia_br(linha["competencia"]), linha["motivo"],
                )
            )
        self.var_resumo.set(f"{len(linhas)} documento(s)")

    def _selecionado(self):
        selecao = self.tabela.selection()
        if not selecao:
            messagebox.showwarning("Fila do Robô", "Selecione um documento.", parent=self.janela)
            return None
        return self.servico.repositorio.obter_fila(int(selecao[0]))

    def _sincronizar(self) -> None:
        try:
            resultado = self.servico.sincronizar_fila_robo()
        except Exception as erro:
            messagebox.showerror("Sincronizar Robô", str(erro), parent=self.janela)
            return
        self.atualizar()
        messagebox.showinfo(
            "Fila sincronizada",
            f"Documentos analisados: {resultado['analisados']}\n"
            f"Prontos para conferir: {resultado['novos']}\n"
            f"Precisam de revisão: {resultado['revisar']}\n"
            f"Possíveis duplicados: {resultado['duplicados']}\n"
            f"Sem dados financeiros: {resultado['ignorados']}",
            parent=self.janela,
        )

    def _aprovar(self) -> None:
        linha = self._selecionado()
        if not linha:
            return
        if linha["status"] in {"IMPORTADO", "IGNORADO"}:
            messagebox.showwarning(
                "Fila do Robô", "Esse documento já foi finalizado na fila.", parent=self.janela
            )
            return
        prefill = dict(linha)
        prefill["origem"] = "ROBÔ FISCALPRO"
        prefill["robo_documento_id"] = linha["robo_documento_id"]
        JanelaContaPagar(
            self.janela,
            self.servico,
            dados=prefill,
            fila_id=int(linha["id"]),
            ao_salvar=self._depois_importar,
        )

    def _depois_importar(self) -> None:
        self.atualizar()
        if self.ao_importar:
            self.ao_importar()

    def _status(self, status: str) -> None:
        linha = self._selecionado()
        if not linha:
            return
        self.servico.repositorio.atualizar_status_fila(int(linha["id"]), status)
        self.atualizar()

    def _abrir_documento(self) -> None:
        linha = self._selecionado()
        if not linha:
            return
        caminho = str(linha["caminho_documento"] or "")
        if not caminho or not Path(caminho).exists():
            messagebox.showwarning("Documento", "Arquivo não encontrado.", parent=self.janela)
            return
        PainelContasPagar._abrir_caminho(caminho)


def re_iso(texto: str) -> bool:
    try:
        datetime.strptime(texto, "%Y-%m-%d")
        return True
    except ValueError:
        return False
