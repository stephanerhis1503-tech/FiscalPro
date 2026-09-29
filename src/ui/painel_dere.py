"""Painel DeRE — pré-validador estrutural e de XSD.

FiscalPro 18.2.3.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import webbrowser
from tkinter import BOTH, END, LEFT, RIGHT, X, Frame, Label, StringVar, Text
from tkinter import filedialog, messagebox, ttk

from src.dere.service import FONTE_TECNICA, URL_OFICIAL_DERE, ResultadoDeRE, ServicoDeRE
from src.ui.estilos import (
    COR_ALERTA,
    COR_BORDA,
    COR_CARD,
    COR_DESTAQUE,
    COR_ERRO,
    COR_PRIMARIA,
    COR_SUCESSO,
    COR_TEXTO,
    COR_TEXTO_SUAVE,
)


class PainelDeRE(ttk.Frame):
    """Central local para preparar e validar XMLs da DeRE."""

    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.servico = ServicoDeRE()
        self.arquivos_xml: list[Path] = []
        self.pacote_xsd: Path | None = None
        self.resultados: list[ResultadoDeRE] = []
        self.var_xsd = StringVar(value="Nenhum pacote XSD selecionado")
        self.var_status = StringVar(value="Selecione XMLs da DeRE para iniciar.")
        self.var_motor_xsd = StringVar(value=self.servico.disponibilidade_xsd().mensagem)
        self._montar()

    def _montar(self) -> None:
        cabecalho = Frame(
            self,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
        )
        cabecalho.pack(fill=X, padx=10, pady=(7, 6))
        Frame(cabecalho, bg=COR_DESTAQUE, height=3).pack(fill=X)
        conteudo = Frame(cabecalho, bg=COR_CARD, padx=12, pady=8)
        conteudo.pack(fill=X)
        Label(
            conteudo,
            text="DeRE — Pré-validador",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        Label(
            conteudo,
            text=(
                "Analise XMLs da Declaração de Regimes Específicos antes do envio. "
                "O FiscalPro identifica D-1001, D-1011, D-1101, D-1106 e D-1199, confere "
                "versão, limites estruturais e, quando você informar o pacote oficial, valida também pelo XSD."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
            justify=LEFT,
            wraplength=1100,
        ).pack(anchor="w", pady=(2, 0))
        Label(
            conteudo,
            text=FONTE_TECNICA,
            bg=COR_CARD,
            fg=COR_PRIMARIA,
            font=("Segoe UI", 8, "bold"),
            justify=LEFT,
        ).pack(anchor="w", pady=(5, 0))

        acoes = ttk.LabelFrame(
            self, text="Arquivos e validação", padding=8, style="Card.TLabelframe"
        )
        acoes.pack(fill=X, padx=10, pady=(0, 6))
        for coluna in range(6):
            acoes.columnconfigure(coluna, weight=1)

        ttk.Button(
            acoes,
            text="Selecionar XMLs",
            command=self._selecionar_xmls,
            style="Primary.TButton",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(
            acoes,
            text="Pasta de XMLs",
            command=self._selecionar_pasta_xmls,
        ).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(
            acoes,
            text="Pacote XSD (.zip)",
            command=self._selecionar_zip_xsd,
        ).grid(row=0, column=2, sticky="ew", padx=3)
        ttk.Button(
            acoes,
            text="Pasta XSD",
            command=self._selecionar_pasta_xsd,
        ).grid(row=0, column=3, sticky="ew", padx=3)
        ttk.Button(
            acoes,
            text="VALIDAR",
            command=self._validar,
            style="Accent.TButton",
        ).grid(row=0, column=4, sticky="ew", padx=3)
        ttk.Button(
            acoes,
            text="Limpar",
            command=self._limpar,
        ).grid(row=0, column=5, sticky="ew", padx=(3, 0))

        info = Frame(acoes, bg=COR_CARD)
        info.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        Label(
            info,
            text="XSD:",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 8, "bold"),
        ).pack(side=LEFT)
        Label(
            info,
            textvariable=self.var_xsd,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8),
        ).pack(side=LEFT, padx=(5, 15))
        Label(
            info,
            textvariable=self.var_motor_xsd,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8),
        ).pack(side=LEFT)
        ttk.Button(
            info,
            text="Documentação oficial",
            command=lambda: webbrowser.open(URL_OFICIAL_DERE),
            style="Secondary.TButton",
        ).pack(side=RIGHT)

        resumo = Frame(
            self,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=12,
            pady=7,
        )
        resumo.pack(fill=X, padx=10, pady=(0, 6))
        Label(
            resumo,
            textvariable=self.var_status,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 9, "bold"),
        ).pack(side=LEFT)
        ttk.Button(
            resumo,
            text="Exportar relatório Excel",
            command=self._exportar_excel,
            style="Secondary.TButton",
        ).pack(side=RIGHT)

        quadro = ttk.LabelFrame(
            self, text="Resultado da pré-validação", padding=6, style="Card.TLabelframe"
        )
        quadro.pack(fill=BOTH, expand=True, padx=10, pady=(0, 6))
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)

        colunas = (
            "status",
            "arquivo",
            "evento",
            "versao",
            "grupo",
            "quantidade",
            "limite",
            "xsd",
            "cnpj",
            "periodo",
        )
        self.grade = ttk.Treeview(quadro, columns=colunas, show="headings", height=12)
        titulos = {
            "status": "Status",
            "arquivo": "Arquivo",
            "evento": "Evento",
            "versao": "Versão",
            "grupo": "Grupo",
            "quantidade": "Qtd.",
            "limite": "Limite",
            "xsd": "XSD",
            "cnpj": "CNPJ raiz",
            "periodo": "Período",
        }
        larguras = {
            "status": 78,
            "arquivo": 220,
            "evento": 225,
            "versao": 90,
            "grupo": 92,
            "quantidade": 70,
            "limite": 82,
            "xsd": 100,
            "cnpj": 100,
            "periodo": 100,
        }
        for coluna in colunas:
            self.grade.heading(coluna, text=titulos[coluna])
            self.grade.column(
                coluna,
                width=larguras[coluna],
                minwidth=65,
                anchor="w" if coluna in {"arquivo", "evento"} else "center",
                stretch=coluna in {"arquivo", "evento"},
            )

        barra_y = ttk.Scrollbar(quadro, orient="vertical", command=self.grade.yview)
        barra_x = ttk.Scrollbar(quadro, orient="horizontal", command=self.grade.xview)
        self.grade.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        self.grade.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        self.grade.bind("<<TreeviewSelect>>", self._mostrar_detalhes)
        self.grade.tag_configure("OK", foreground=COR_SUCESSO)
        self.grade.tag_configure("REVISAR", foreground=COR_ALERTA)
        self.grade.tag_configure("ERRO", foreground=COR_ERRO)

        detalhes = ttk.LabelFrame(
            self, text="Detalhes técnicos", padding=6, style="Card.TLabelframe"
        )
        detalhes.pack(fill=X, padx=10, pady=(0, 9))
        self.txt_detalhes = Text(
            detalhes,
            height=5,
            wrap="word",
            font=("Consolas", 9),
            padx=7,
            pady=5,
        )
        self.txt_detalhes.pack(fill=X)
        self.txt_detalhes.insert(
            END,
            "D-1001: Informações do Contribuinte (XSD v1.0.1).\n"
            "D-1011: até 150.000 infoConta (XSD v1.0.3).\n"
            "D-1101: até 90.000 infoConta (XSD v1.0.1).\n"
            "D-1106: até 100 infoAplic e até 500 detAtivo por infoAplic (XSD v1.0.0).\n"
            "D-1199: Fechamento Mensal (XSD v0.0.2 no pacote completo v1.2.0).\n"
            "A transmissão não faz parte desta versão; este módulo é de pré-validação local.",
        )
        self.txt_detalhes.configure(state="disabled")

    def _selecionar_xmls(self) -> None:
        caminhos = filedialog.askopenfilenames(
            parent=self,
            title="Selecione XMLs da DeRE",
            filetypes=(("Arquivos XML", "*.xml"), ("Todos os arquivos", "*.*")),
        )
        if caminhos:
            self.arquivos_xml = [Path(c) for c in caminhos]
            self.var_status.set(f"{len(self.arquivos_xml)} XML(s) selecionado(s). Clique em VALIDAR.")

    def _selecionar_pasta_xmls(self) -> None:
        pasta = filedialog.askdirectory(parent=self, title="Selecione a pasta com XMLs da DeRE")
        if not pasta:
            return
        self.arquivos_xml = sorted(Path(pasta).rglob("*.xml"))
        self.var_status.set(f"{len(self.arquivos_xml)} XML(s) localizado(s) na pasta.")

    def _selecionar_zip_xsd(self) -> None:
        caminho = filedialog.askopenfilename(
            parent=self,
            title="Selecione o ZIP oficial de XSDs da DeRE",
            filetypes=(("Pacote ZIP", "*.zip"), ("Todos os arquivos", "*.*")),
        )
        if caminho:
            self.pacote_xsd = Path(caminho)
            self.var_xsd.set(self.pacote_xsd.name)

    def _selecionar_pasta_xsd(self) -> None:
        pasta = filedialog.askdirectory(parent=self, title="Selecione a pasta dos XSDs da DeRE")
        if pasta:
            self.pacote_xsd = Path(pasta)
            self.var_xsd.set(str(self.pacote_xsd))

    def _validar(self) -> None:
        if not self.arquivos_xml:
            messagebox.showwarning(
                "FiscalPro — DeRE",
                "Selecione pelo menos um XML da DeRE.",
                parent=self,
            )
            return
        self.var_status.set("Validando arquivos...")
        self.update_idletasks()
        self.resultados = self.servico.analisar_varios(self.arquivos_xml, self.pacote_xsd)
        self._preencher_grade()

        total = len(self.resultados)
        erros = sum(1 for r in self.resultados if r.status_geral == "ERRO")
        revisar = sum(1 for r in self.resultados if r.status_geral == "REVISAR")
        ok = total - erros - revisar
        xsd = "com XSD" if self.pacote_xsd else "sem XSD"
        self.var_status.set(
            f"{total} arquivo(s) • {ok} OK • {revisar} revisar • {erros} erro(s) • validação {xsd}."
        )

    @staticmethod
    def _fmt_numero(valor: int | None) -> str:
        if valor is None:
            return "-"
        return f"{valor:,}".replace(",", ".")

    def _preencher_grade(self) -> None:
        for item in self.grade.get_children():
            self.grade.delete(item)
        for indice, resultado in enumerate(self.resultados):
            evento = (
                f"{resultado.codigo_evento} — {resultado.nome_evento}"
                if resultado.codigo_evento
                else "Não identificado"
            )
            self.grade.insert(
                "",
                END,
                iid=str(indice),
                values=(
                    resultado.status_geral,
                    Path(resultado.arquivo).name,
                    evento,
                    resultado.versao_namespace or "-",
                    resultado.grupo_contagem or "-",
                    self._fmt_numero(resultado.quantidade_grupo) if resultado.grupo_contagem else "-",
                    self._fmt_numero(resultado.limite_grupo),
                    resultado.status_xsd,
                    resultado.cnpj_raiz or "-",
                    resultado.periodo or "-",
                ),
                tags=(resultado.status_geral,),
            )
        if self.resultados:
            self.grade.selection_set("0")
            self.grade.focus("0")
            self._mostrar_detalhes()

    def _mostrar_detalhes(self, _evento=None) -> None:
        selecao = self.grade.selection()
        if not selecao:
            return
        try:
            resultado = self.resultados[int(selecao[0])]
        except (ValueError, IndexError):
            return
        linhas = [
            f"Arquivo: {resultado.arquivo}",
            f"Evento: {resultado.codigo_evento or '-'} {resultado.nome_evento}",
            f"Namespace: {resultado.namespace or '-'}",
            f"Versão detectada / esperada: {resultado.versao_namespace or '-'} / {resultado.versao_esperada or '-'}",
            f"Categoria: {resultado.categoria_evento or '-'}",
            f"Grupo monitorado: {resultado.grupo_contagem or '-'} | quantidade: "
            f"{self._fmt_numero(resultado.quantidade_grupo) if resultado.grupo_contagem else '-'} / "
            f"{self._fmt_numero(resultado.limite_grupo)}",
            f"XML: {resultado.status_xml} | versão: {resultado.status_versao} | capacidade: {resultado.status_capacidade} | XSD: {resultado.status_xsd}",
            f"Detalhe: {resultado.detalhes or '-'}",
        ]
        self.txt_detalhes.configure(state="normal")
        self.txt_detalhes.delete("1.0", END)
        self.txt_detalhes.insert(END, "\n".join(linhas))
        self.txt_detalhes.configure(state="disabled")

    def _exportar_excel(self) -> None:
        if not self.resultados:
            messagebox.showwarning(
                "FiscalPro — DeRE",
                "Valide os XMLs antes de exportar o relatório.",
                parent=self,
            )
            return
        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar relatório DeRE",
            defaultextension=".xlsx",
            initialfile=f"FiscalPro_DeRE_{datetime.now():%Y%m%d_%H%M}.xlsx",
            filetypes=(("Planilha Excel", "*.xlsx"),),
        )
        if not destino:
            return
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font

            wb = Workbook()
            ws = wb.active
            ws.title = "Pré-Validação DeRE"
            cabecalhos = [
                "Status",
                "Arquivo",
                "Evento",
                "Descrição",
                "Namespace",
                "Versão detectada",
                "Versão esperada",
                "Categoria",
                "Grupo monitorado",
                "Quantidade",
                "Limite",
                "Status XML",
                "Status versão",
                "Status capacidade",
                "Status XSD",
                "CNPJ raiz",
                "Período",
                "Detalhes",
            ]
            ws.append(cabecalhos)
            for celula in ws[1]:
                celula.font = Font(bold=True)
            for r in self.resultados:
                ws.append(
                    [
                        r.status_geral,
                        r.arquivo,
                        r.codigo_evento,
                        r.nome_evento,
                        r.namespace,
                        r.versao_namespace,
                        r.versao_esperada,
                        r.categoria_evento,
                        r.grupo_contagem,
                        r.quantidade_grupo if r.grupo_contagem else "",
                        r.limite_grupo if r.limite_grupo is not None else "",
                        r.status_xml,
                        r.status_versao,
                        r.status_capacidade,
                        r.status_xsd,
                        r.cnpj_raiz,
                        r.periodo,
                        r.detalhes,
                    ]
                )
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            larguras = {
                "A": 12, "B": 42, "C": 12, "D": 34, "E": 52, "F": 16,
                "G": 16, "H": 20, "I": 18, "J": 14, "K": 14, "L": 14,
                "M": 16, "N": 20, "O": 18, "P": 16, "Q": 14, "R": 80,
            }
            for coluna, largura in larguras.items():
                ws.column_dimensions[coluna].width = largura
            wb.save(destino)
            messagebox.showinfo(
                "FiscalPro — DeRE",
                f"Relatório salvo em:\n{destino}",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror(
                "FiscalPro — DeRE",
                f"Não foi possível exportar o relatório:\n{exc}",
                parent=self,
            )

    def _limpar(self) -> None:
        self.arquivos_xml = []
        self.resultados = []
        for item in self.grade.get_children():
            self.grade.delete(item)
        self.var_status.set("Selecione XMLs da DeRE para iniciar.")
        self.txt_detalhes.configure(state="normal")
        self.txt_detalhes.delete("1.0", END)
        self.txt_detalhes.insert(
            END,
            "D-1001: Informações do Contribuinte (XSD v1.0.1).\n"
            "D-1011: até 150.000 infoConta (XSD v1.0.3).\n"
            "D-1101: até 90.000 infoConta (XSD v1.0.1).\n"
            "D-1106: até 100 infoAplic e até 500 detAtivo por infoAplic (XSD v1.0.0).\n"
            "D-1199: Fechamento Mensal (XSD v0.0.2; requer pacote XSD v1.2.0 completo).",
        )
        self.txt_detalhes.configure(state="disabled")
