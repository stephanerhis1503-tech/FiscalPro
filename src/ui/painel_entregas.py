"""Controle de Entregas — Hotfix 17.8.15.

Grade mensal inspirada na planilha de controle fornecida pela usuária: uma
linha por empresa e uma coluna por obrigação. A competência continua separada
do vencimento real de cada obrigação.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import BOTH, END, LEFT, X, Frame, Label, StringVar, Text, Toplevel
from tkinter import filedialog, messagebox, simpledialog, ttk

from src.entregas import EntregasServico
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


PRAZO_APOS_COMPETENCIA = {
    "Mesmo mês": 0,
    "Mês seguinte": 1,
    "2 meses depois": 2,
}
PRAZO_APOS_COMPETENCIA_INV = {valor: rotulo for rotulo, valor in PRAZO_APOS_COMPETENCIA.items()}


def _rotulo_prazo_competencia(meses: object) -> str:
    try:
        quantidade = int(meses)
    except (TypeError, ValueError):
        quantidade = 1
    return PRAZO_APOS_COMPETENCIA_INV.get(
        quantidade, f"{quantidade} meses depois" if quantidade != 1 else "Mês seguinte"
    )


class PainelEntregas(ttk.Frame):
    """Painel mensal em formato de grade, semelhante à planilha de referência."""

    def __init__(self, master, servico: EntregasServico | None = None):
        super().__init__(master, style="Page.TFrame")
        self.servico = servico or EntregasServico()
        self.servico.sincronizar_estrutura_atual()
        hoje = date.today()
        self.var_competencia = StringVar(value=f"{hoje.month:02d}/{hoje.year}")
        self.var_orientacao = StringVar(value="")
        self.var_resumo = {
            "pendentes": StringVar(value="0"),
            "andamento": StringVar(value="0"),
            "entregues": StringVar(value="0"),
            "atrasados": StringVar(value="0"),
            "nao_aplica": StringVar(value="0"),
        }
        self._criar_interface()
        self.atualizar()

    def _criar_interface(self) -> None:
        cabecalho = Frame(
            self, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA,
            padx=14, pady=9,
        )
        cabecalho.pack(fill=X, padx=10, pady=(8, 6))
        Label(
            cabecalho, text="Controle Mensal de Entregas", bg=COR_CARD,
            fg=COR_TEXTO, font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        Label(
            cabecalho,
            text=(
                "Grade por empresa e obrigação, inspirada na sua planilha. "
                "Clique em uma célula para informar status, valor, prazo, protocolo ou comprovante."
            ),
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 9), justify=LEFT,
        ).pack(anchor="w", pady=(2, 0))
        Label(
            cabecalho, textvariable=self.var_orientacao, bg=COR_CARD,
            fg=COR_PRIMARIA, font=("Segoe UI", 9, "bold"), justify=LEFT,
        ).pack(anchor="w", pady=(5, 0))

        barra = ttk.LabelFrame(self, text="Competência e ações", padding=8, style="Card.TLabelframe")
        barra.pack(fill=X, padx=10, pady=(0, 6))
        barra.columnconfigure(1, weight=1)
        ttk.Label(barra, text="Competência", style="CardSubtitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )
        self.cbo_competencia = ttk.Combobox(
            barra, textvariable=self.var_competencia,
            values=self.servico.opcoes_competencia(), width=12,
        )
        self.cbo_competencia.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.cbo_competencia.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())

        botoes = ttk.Frame(barra, style="Card.TFrame")
        botoes.grid(row=1, column=1, sticky="ew")
        for coluna in range(4):
            botoes.columnconfigure(coluna, weight=1)
        ttk.Button(
            botoes, text="Gerar / atualizar competência", command=self._gerar_competencia,
            style="Primary.TButton",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(botoes, text="Atualizar", command=self.atualizar).grid(
            row=0, column=1, sticky="ew", padx=3
        )
        ttk.Button(
            botoes, text="Configurar empresas / obrigações", command=self._configurar,
            style="Accent.TButton",
        ).grid(row=0, column=2, sticky="ew", padx=3)
        ttk.Button(botoes, text="Exportar grade CSV", command=self._exportar).grid(
            row=0, column=3, sticky="ew", padx=(3, 0)
        )

        cards = ttk.Frame(self, style="Page.TFrame")
        cards.pack(fill=X, padx=10, pady=(0, 6))
        for coluna in range(5):
            cards.columnconfigure(coluna, weight=1, uniform="entregas")
        self._card(cards, 0, "Pendentes", self.var_resumo["pendentes"], COR_PRIMARIA)
        self._card(cards, 1, "Em andamento", self.var_resumo["andamento"], COR_ALERTA)
        self._card(cards, 2, "Entregues", self.var_resumo["entregues"], COR_SUCESSO)
        self._card(cards, 3, "Atrasados", self.var_resumo["atrasados"], COR_ERRO)
        self._card(cards, 4, "Não se aplica", self.var_resumo["nao_aplica"], COR_TEXTO_SUAVE)

        legenda = ttk.Frame(self, style="Page.TFrame")
        legenda.pack(fill=X, padx=12, pady=(0, 5))
        ttk.Label(
            legenda,
            text="⬜ Pendente   🟡 Em andamento   ✅ Entregue   🔴 Atrasado   ➖ Não se aplica",
            style="CardSubtitle.TLabel",
        ).pack(side=LEFT)

        quadro = ttk.LabelFrame(self, text="Checklist mensal", padding=6, style="Card.TLabelframe")
        quadro.pack(fill=BOTH, expand=True, padx=10, pady=(0, 8))
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            quadro, bg=COR_CARD, highlightthickness=0, borderwidth=0,
        )
        self.barra_x = ttk.Scrollbar(quadro, orient="horizontal", command=self.canvas.xview)
        self.barra_y = ttk.Scrollbar(quadro, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(
            xscrollcommand=self.barra_x.set, yscrollcommand=self.barra_y.set
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.barra_y.grid(row=0, column=1, sticky="ns")
        self.barra_x.grid(row=1, column=0, sticky="ew")

        self.grade = Frame(self.canvas, bg=COR_CARD)
        self._grade_window = self.canvas.create_window((0, 0), window=self.grade, anchor="nw")
        self.grade.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind("<Configure>", self._ajustar_canvas)

    @staticmethod
    def _card(master, coluna: int, titulo: str, variavel: StringVar, cor: str) -> None:
        quadro = Frame(
            master, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA,
            padx=10, pady=8,
        )
        quadro.grid(row=0, column=coluna, sticky="nsew", padx=(0 if coluna == 0 else 4, 0))
        Frame(quadro, bg=cor, height=3).pack(fill=X, pady=(0, 5))
        Label(
            quadro, text=titulo, bg=COR_CARD, fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8),
        ).pack()
        Label(
            quadro, textvariable=variavel, bg=COR_CARD, fg=cor,
            font=("Segoe UI", 13, "bold"),
        ).pack(pady=(2, 0))

    def _ajustar_canvas(self, evento) -> None:
        # Mantém a grade ocupando toda a largura quando ela for menor que a tela,
        # sem impedir a rolagem horizontal quando houver muitas colunas.
        requerido = self.grade.winfo_reqwidth()
        self.canvas.itemconfigure(self._grade_window, width=max(evento.width, requerido))

    def _competencia_iso(self) -> str | None:
        try:
            return self.servico.competencia_iso(self.var_competencia.get())
        except Exception as erro:
            messagebox.showerror("Controle de Entregas", str(erro), parent=self)
            return None

    def atualizar(self) -> None:
        competencia = self._competencia_iso()
        if not competencia:
            return
        grade = self.servico.grade_competencia(competencia)
        self.var_orientacao.set(
            f"{len(grade)} empresa(s) atual(is) • competência {self.servico.competencia_br(competencia)}. "
            "Empresas antigas permanecem preservadas apenas no histórico do banco."
        )
        resumo = {chave: 0 for chave in self.var_resumo}
        for linha in grade:
            for celula in linha["celulas"].values():
                status = str(celula["status"])
                if status == "EM ANDAMENTO":
                    resumo["andamento"] += 1
                elif status == "ENTREGUE":
                    resumo["entregues"] += 1
                elif status == "ATRASADO":
                    resumo["atrasados"] += 1
                elif status == "NÃO SE APLICA":
                    resumo["nao_aplica"] += 1
                else:
                    resumo["pendentes"] += 1
        for chave, variavel in self.var_resumo.items():
            variavel.set(str(resumo[chave]))
        self._montar_grade(grade, competencia)

    def _montar_grade(self, linhas: list[dict[str, object]], competencia: str) -> None:
        for filho in self.grade.winfo_children():
            filho.destroy()

        cabecalhos = ["EMPRESA", "REGIME"] + [
            rotulo for _nome, rotulo, _monetario in self.servico.OBRIGACOES_PADRAO
        ] + ["OBSERVAÇÕES"]
        for coluna, texto in enumerate(cabecalhos):
            lbl = Label(
                self.grade, text=texto, bg=COR_PRIMARIA, fg="white",
                font=("Segoe UI", 8, "bold"), relief="solid", bd=1,
                padx=7, pady=7, justify="center", wraplength=130,
            )
            lbl.grid(row=0, column=coluna, sticky="nsew")
            self.grade.grid_columnconfigure(coluna, minsize=145 if coluna >= 2 else 155)

        for linha_idx, linha in enumerate(linhas, start=1):
            empresa = linha["empresa"]
            empresa_id = int(empresa["id"])
            Label(
                self.grade, text=str(empresa["nome"]), bg=COR_CARD, fg=COR_TEXTO,
                font=("Segoe UI", 9, "bold"), relief="solid", bd=1,
                padx=7, pady=11, anchor="w",
            ).grid(row=linha_idx, column=0, sticky="nsew")
            Label(
                self.grade, text=str(empresa["regime"] or "A DEFINIR"), bg="#F7F8FA",
                fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8, "bold"), relief="solid", bd=1,
                padx=6, pady=11, justify="center",
            ).grid(row=linha_idx, column=1, sticky="nsew")

            for deslocamento, (obrigacao, _rotulo, monetario) in enumerate(
                self.servico.OBRIGACOES_PADRAO, start=2
            ):
                celula = linha["celulas"][obrigacao]
                texto, fundo, frente = self._aparencia_celula(celula, monetario)
                botao = tk.Button(
                    self.grade, text=texto, command=lambda eid=empresa_id, ob=obrigacao, c=celula: self._abrir_celula(eid, ob, c),
                    bg=fundo, fg=frente, activebackground=fundo, activeforeground=frente,
                    font=("Segoe UI", 8, "bold"), relief="solid", bd=1,
                    padx=5, pady=8, cursor="hand2", wraplength=125,
                )
                botao.grid(row=linha_idx, column=deslocamento, sticky="nsew")

            obs = str(linha["observacoes"] or "").strip()
            texto_obs = obs if obs else "Adicionar"
            if len(texto_obs) > 36:
                texto_obs = texto_obs[:33] + "..."
            tk.Button(
                self.grade, text=texto_obs,
                command=lambda eid=empresa_id, nome=str(empresa["nome"]): self._editar_observacao(eid, nome, competencia),
                bg="#F7F8FA", fg=COR_TEXTO, activebackground="#F7F8FA",
                font=("Segoe UI", 8), relief="solid", bd=1, padx=5, pady=8,
                cursor="hand2", wraplength=140,
            ).grid(
                row=linha_idx, column=len(cabecalhos) - 1, sticky="nsew"
            )

        self.grade.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _aparencia_celula(self, celula: dict[str, object], monetario: bool):
        status = str(celula["status"])
        entrega = celula["entrega"]
        mapa = {
            "PENDENTE": ("⬜ Pendente", "#EEF4FF", COR_PRIMARIA),
            "EM ANDAMENTO": ("🟡 Andamento", "#FFF4CC", "#8A6200"),
            "ENTREGUE": ("✅ Entregue", "#E7F5EC", COR_SUCESSO),
            "ATRASADO": ("🔴 Atrasado", "#FDECEC", COR_ERRO),
            "NÃO SE APLICA": ("➖ N/A", "#F0F1F3", COR_TEXTO_SUAVE),
        }
        texto, fundo, frente = mapa.get(status, mapa["PENDENTE"])
        if monetario and entrega is not None and float(entrega["valor"] or 0):
            texto += "\n" + self.servico.valor_br(entrega["valor"])
        elif entrega is not None and str(entrega["data_entrega"] or "") and status == "ENTREGUE":
            texto += "\n" + self.servico.data_br(entrega["data_entrega"])
        return texto, fundo, frente

    def _abrir_celula(self, empresa_id: int, obrigacao: str, celula: dict[str, object]) -> None:
        if not bool(celula["aplicavel"]):
            messagebox.showinfo(
                "Não se aplica",
                f"{obrigacao} está marcado como NÃO SE APLICA para esta empresa.\n\n"
                "Use “Configurar empresas / obrigações” para ativar essa obrigação mensalmente.",
                parent=self,
            )
            return
        entrega = celula["entrega"]
        if entrega is None:
            entrega = self.servico.garantir_entrega(
                empresa_id, self.var_competencia.get(), obrigacao
            )
        if entrega is None:
            return
        JanelaEntrega(self, self.servico, entrega=entrega, ao_salvar=self.atualizar, fixo=True)

    def _gerar_competencia(self) -> None:
        competencia = self._competencia_iso()
        if not competencia:
            return
        try:
            quantidade = self.servico.gerar_competencia(competencia)
        except Exception as erro:
            messagebox.showerror("Gerar competência", str(erro), parent=self)
            return
        self.atualizar()
        messagebox.showinfo(
            "Gerar competência",
            f"Competência {self.servico.competencia_br(competencia)} processada.\n"
            f"{quantidade} novo(s) item(ns) incluído(s). Itens já entregues foram preservados.",
            parent=self,
        )

    def _editar_observacao(self, empresa_id: int, empresa: str, competencia: str) -> None:
        JanelaObservacaoCompetencia(
            self, self.servico, empresa_id, empresa, competencia, ao_salvar=self.atualizar
        )

    def _configurar(self) -> None:
        JanelaConfiguracaoEntregas(self, self.servico, ao_fechar=self.atualizar)

    def _exportar(self) -> None:
        competencia = self._competencia_iso()
        if not competencia:
            return
        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar grade mensal",
            defaultextension=".csv",
            filetypes=[("Arquivo CSV", "*.csv")],
            initialfile=f"Controle_Entregas_{self.servico.competencia_br(competencia).replace('/', '-')}.csv",
        )
        if not destino:
            return
        try:
            caminho = self.servico.exportar_grade_csv(destino, competencia)
        except Exception as erro:
            messagebox.showerror("Exportar grade", str(erro), parent=self)
            return
        messagebox.showinfo("Exportar grade", f"Arquivo gerado:\n{caminho}", parent=self)


class JanelaEntrega(Toplevel):
    def __init__(
        self, master, servico: EntregasServico, entrega=None, ao_salvar=None, fixo: bool = False
    ):
        super().__init__(master)
        self.servico = servico
        self.entrega = entrega
        self.ao_salvar = ao_salvar
        self.fixo = fixo
        self.title("Detalhes da obrigação")
        self.geometry("760x590")
        self.minsize(680, 540)
        self.transient(master.winfo_toplevel())
        self.grab_set()

        hoje = date.today()
        self.var_empresa = StringVar(value=str(entrega["empresa"]) if entrega else "")
        self.var_competencia = StringVar(
            value=self.servico.competencia_br(entrega["competencia"])
            if entrega else f"{hoje.month:02d}/{hoje.year}"
        )
        self.var_tipo = StringVar(value=str(entrega["tipo_arquivo"]) if entrega else "")
        self.var_prazo = StringVar(value=self.servico.data_br(entrega["prazo"]) if entrega else "")
        self.var_entrega = StringVar(value=self.servico.data_br(entrega["data_entrega"]) if entrega else "")
        self.var_status = StringVar(value=str(entrega["status"]) if entrega else "PENDENTE")
        self.var_valor = StringVar(
            value=self.servico.valor_br(entrega["valor"]).replace("R$ ", "")
            if entrega and float(entrega["valor"] or 0) else ""
        )
        self.var_protocolo = StringVar(value=str(entrega["protocolo"] or "") if entrega else "")
        self.var_caminho = StringVar(value=str(entrega["caminho_arquivo"] or "") if entrega else "")
        self._criar()

    def _criar(self) -> None:
        corpo = ttk.Frame(self, padding=14, style="Page.TFrame")
        corpo.pack(fill=BOTH, expand=True)
        corpo.columnconfigure(1, weight=1)

        campos_fixos = (
            ("Empresa", self.var_empresa),
            ("Competência", self.var_competencia),
            ("Obrigação", self.var_tipo),
        )
        for linha, (titulo, var) in enumerate(campos_fixos):
            ttk.Label(corpo, text=titulo).grid(row=linha, column=0, sticky="w", pady=5)
            estado = "readonly" if self.fixo else "normal"
            ttk.Entry(corpo, textvariable=var, state=estado).grid(
                row=linha, column=1, sticky="ew", pady=5
            )

        dados = ttk.LabelFrame(corpo, text="Situação da competência", padding=8)
        dados.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 5))
        for i in range(3):
            dados.columnconfigure(i, weight=1)
        ttk.Label(dados, text="Status").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            dados, textvariable=self.var_status,
            values=self.servico.STATUS, state="readonly",
        ).grid(row=1, column=0, sticky="ew", padx=(0, 6))
        ttk.Label(dados, text="Prazo (DD/MM/AAAA)").grid(row=0, column=1, sticky="w")
        ttk.Entry(dados, textvariable=self.var_prazo).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Label(dados, text="Entregue em").grid(row=0, column=2, sticky="w")
        ttk.Entry(dados, textvariable=self.var_entrega).grid(row=1, column=2, sticky="ew", padx=(6, 0))

        financeiro = ttk.Frame(corpo, style="Page.TFrame")
        financeiro.grid(row=4, column=0, columnspan=2, sticky="ew", pady=5)
        financeiro.columnconfigure(1, weight=1)
        financeiro.columnconfigure(3, weight=2)
        ttk.Label(financeiro, text="Valor").grid(row=0, column=0, sticky="w")
        ttk.Entry(financeiro, textvariable=self.var_valor, width=18).grid(
            row=0, column=1, sticky="ew", padx=(6, 14)
        )
        ttk.Label(financeiro, text="Protocolo / referência").grid(row=0, column=2, sticky="w")
        ttk.Entry(financeiro, textvariable=self.var_protocolo).grid(
            row=0, column=3, sticky="ew", padx=(6, 0)
        )

        ttk.Label(corpo, text="Comprovante / arquivo").grid(row=5, column=0, sticky="w", pady=5)
        arquivo = ttk.Frame(corpo, style="Page.TFrame")
        arquivo.grid(row=5, column=1, sticky="ew", pady=5)
        arquivo.columnconfigure(0, weight=1)
        ttk.Entry(arquivo, textvariable=self.var_caminho).grid(row=0, column=0, sticky="ew")
        ttk.Button(arquivo, text="Procurar...", command=self._procurar).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(arquivo, text="Abrir", command=self._abrir).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(corpo, text="Observações").grid(row=6, column=0, sticky="nw", pady=5)
        self.txt_obs = Text(corpo, height=9, wrap="word", padx=6, pady=5)
        self.txt_obs.grid(row=6, column=1, sticky="nsew", pady=5)
        corpo.rowconfigure(6, weight=1)
        if self.entrega:
            self.txt_obs.insert("1.0", str(self.entrega["observacoes"] or ""))

        ttk.Label(
            corpo,
            text="O valor é apenas informativo para o controle mensal; não altera apurações tributárias.",
            style="CardSubtitle.TLabel",
        ).grid(row=7, column=1, sticky="w", pady=(0, 4))

        botoes = ttk.Frame(corpo, style="Page.TFrame")
        botoes.grid(row=8, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side=LEFT, padx=(0, 6))
        ttk.Button(botoes, text="Salvar", command=self._salvar, style="Primary.TButton").pack(side=LEFT)

    def _procurar(self) -> None:
        caminho = filedialog.askopenfilename(parent=self, title="Selecione o comprovante")
        if caminho:
            self.var_caminho.set(caminho)

    def _abrir(self) -> None:
        caminho = self.var_caminho.get().strip()
        if not caminho:
            return
        alvo = Path(caminho)
        if not alvo.exists():
            messagebox.showwarning("Abrir arquivo", f"Arquivo não localizado:\n{caminho}", parent=self)
            return
        try:
            if os.name == "nt":
                os.startfile(str(alvo))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(alvo)])
            else:
                subprocess.Popen(["xdg-open", str(alvo)])
        except Exception as erro:
            messagebox.showerror("Abrir arquivo", str(erro), parent=self)

    def _salvar(self) -> None:
        dados = {
            "empresa": self.var_empresa.get(),
            "competencia": self.var_competencia.get(),
            "tipo_arquivo": self.var_tipo.get(),
            "prazo": self.var_prazo.get(),
            "data_entrega": self.var_entrega.get(),
            "status": self.var_status.get(),
            "valor": self.var_valor.get(),
            "protocolo": self.var_protocolo.get(),
            "caminho_arquivo": self.var_caminho.get(),
            "observacoes": self.txt_obs.get("1.0", END).strip(),
            "destinatario": str(self.entrega["destinatario"] or "") if self.entrega else "",
        }
        try:
            self.servico.salvar_entrega(
                dados, entrega_id=int(self.entrega["id"]) if self.entrega else None
            )
        except Exception as erro:
            messagebox.showerror("Salvar obrigação", str(erro), parent=self)
            return
        if self.ao_salvar:
            self.ao_salvar()
        self.destroy()


class JanelaObservacaoCompetencia(Toplevel):
    def __init__(self, master, servico, empresa_id: int, empresa: str, competencia: str, ao_salvar=None):
        super().__init__(master)
        self.servico = servico
        self.empresa_id = empresa_id
        self.competencia = competencia
        self.ao_salvar = ao_salvar
        self.title("Observações da competência")
        self.geometry("620x330")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        corpo = ttk.Frame(self, padding=14, style="Page.TFrame")
        corpo.pack(fill=BOTH, expand=True)
        ttk.Label(
            corpo,
            text=f"{empresa} • {servico.competencia_br(competencia)}",
            style="CardTitle.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        self.txt = Text(corpo, height=12, wrap="word", padx=7, pady=6)
        self.txt.pack(fill=BOTH, expand=True)
        self.txt.insert(
            "1.0", servico.repositorio.obter_observacao_competencia(empresa_id, competencia)
        )
        botoes = ttk.Frame(corpo, style="Page.TFrame")
        botoes.pack(fill=X, pady=(10, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side=LEFT)
        ttk.Button(
            botoes, text="Salvar observação", command=self._salvar, style="Primary.TButton"
        ).pack(side="right")

    def _salvar(self):
        self.servico.repositorio.salvar_observacao_competencia(
            self.empresa_id, self.competencia, self.txt.get("1.0", END).strip()
        )
        if self.ao_salvar:
            self.ao_salvar()
        self.destroy()


class JanelaConfiguracaoEntregas(Toplevel):
    """Configura empresas, regime e aplicabilidade das colunas da grade mensal."""

    def __init__(self, master, servico: EntregasServico, ao_fechar=None):
        super().__init__(master)
        self.servico = servico
        self.ao_fechar = ao_fechar
        self.title("Empresas e obrigações do Controle de Entregas")
        self.geometry("980x620")
        self.minsize(900, 550)
        self.transient(master.winfo_toplevel())
        self.grab_set()
        empresas = self.servico.repositorio.listar_empresas()
        primeiro = str(empresas[0]["nome"]) if empresas else ""
        self.var_empresa = StringVar(value=primeiro)
        self.var_regime = StringVar(value="A DEFINIR")
        self._criar()
        self.atualizar()

    def _criar(self) -> None:
        corpo = ttk.Frame(self, padding=12, style="Page.TFrame")
        corpo.pack(fill=BOTH, expand=True)
        topo = ttk.LabelFrame(corpo, text="Empresa atual", padding=8, style="Card.TLabelframe")
        topo.pack(fill=X, pady=(0, 8))
        topo.columnconfigure(1, weight=1)
        topo.columnconfigure(3, weight=1)
        ttk.Label(topo, text="Empresa").grid(row=0, column=0, sticky="w")
        self.cbo_empresa = ttk.Combobox(topo, textvariable=self.var_empresa, state="readonly")
        self.cbo_empresa.grid(row=0, column=1, sticky="ew", padx=(6, 14))
        self.cbo_empresa.bind("<<ComboboxSelected>>", lambda _e: self.atualizar_modelos())
        ttk.Label(topo, text="Regime").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            topo, textvariable=self.var_regime, values=self.servico.REGIMES, state="readonly"
        ).grid(row=0, column=3, sticky="ew", padx=(6, 8))
        ttk.Button(topo, text="Salvar regime", command=self._salvar_regime).grid(row=0, column=4)
        botoes_empresa = ttk.Frame(topo, style="Card.TFrame")
        botoes_empresa.grid(row=1, column=0, columnspan=5, sticky="w", pady=(8, 0))
        ttk.Button(
            botoes_empresa,
            text="+ Nova empresa",
            command=self._nova_empresa,
            style="Accent.TButton",
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            botoes_empresa,
            text="Editar empresa",
            command=self._editar_empresa,
        ).pack(side=LEFT)

        ttk.Label(
            corpo,
            text=(
                "Cadastre novas empresas aqui; elas permanecem salvas nas próximas versões e também ficam "
                "disponíveis nas listas dos módulos tributários. Empresas antigas desativadas continuam no histórico. "
                "Use 'N/A' para obrigações que não se aplicam permanentemente à empresa."
            ),
            style="CardSubtitle.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        quadro = ttk.LabelFrame(corpo, text="Obrigações da grade", padding=7, style="Card.TLabelframe")
        quadro.pack(fill=BOTH, expand=True)
        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)
        self.tabela = ttk.Treeview(
            quadro, columns=("obrigacao", "aplica", "dia", "apos"), show="headings", height=16
        )
        titulos = {
            "obrigacao": "Obrigação",
            "aplica": "Aplica?",
            "dia": "Dia do prazo",
            "apos": "Prazo após competência",
        }
        larguras = {"obrigacao": 310, "aplica": 90, "dia": 100, "apos": 190}
        for coluna in ("obrigacao", "aplica", "dia", "apos"):
            self.tabela.heading(coluna, text=titulos[coluna])
            self.tabela.column(
                coluna, width=larguras[coluna],
                anchor="center" if coluna != "obrigacao" else "w",
            )
        self.tabela.grid(row=0, column=0, sticky="nsew")
        barra_y = ttk.Scrollbar(quadro, orient="vertical", command=self.tabela.yview)
        barra_y.grid(row=0, column=1, sticky="ns")
        self.tabela.configure(yscrollcommand=barra_y.set)
        self.tabela.bind("<Double-1>", lambda _e: self._editar_prazo())

        acoes = ttk.Frame(corpo, style="Page.TFrame")
        acoes.pack(fill=X, pady=(8, 0))
        ttk.Button(
            acoes, text="Alternar Aplica / N/A", command=self._alternar,
            style="Accent.TButton",
        ).pack(side=LEFT, padx=(0, 5))
        ttk.Button(acoes, text="Editar prazo", command=self._editar_prazo).pack(side=LEFT, padx=5)
        ttk.Button(acoes, text="Fechar", command=self._fechar).pack(side="right")

    def atualizar(self) -> None:
        empresas = self.servico.repositorio.listar_empresas()
        nomes = tuple(str(e["nome"]) for e in empresas)
        self.cbo_empresa.configure(values=nomes)
        if self.var_empresa.get() not in nomes and nomes:
            self.var_empresa.set(nomes[0])
        self.atualizar_modelos()

    def atualizar_modelos(self) -> None:
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        empresa = self.servico.repositorio.obter_empresa_por_nome(self.var_empresa.get())
        if not empresa:
            return
        self.var_regime.set(str(empresa["regime"] or "A DEFINIR"))
        empresa_id = int(empresa["id"])
        for obrigacao, rotulo, _monetario in self.servico.OBRIGACOES_PADRAO:
            modelo = self.servico.repositorio.obter_modelo_por_empresa_tipo(
                empresa_id, obrigacao, incluir_inativo=True
            )
            ativo = bool(modelo is not None and int(modelo["ativo"] or 0))
            dia = int(modelo["dia_prazo"] or 0) if modelo else 0
            apos = int(modelo["meses_apos_competencia"] or 1) if modelo else 1
            self.tabela.insert(
                "", END, iid=obrigacao,
                values=(rotulo, "SIM" if ativo else "N/A", dia if dia else "—", _rotulo_prazo_competencia(apos)),
            )

    def _selecionados(self):
        selecao = self.tabela.selection()
        if not selecao:
            messagebox.showwarning("Obrigações", "Selecione uma obrigação.", parent=self)
            return None, None
        empresa = self.servico.repositorio.obter_empresa_por_nome(self.var_empresa.get())
        return empresa, str(selecao[0])

    def _salvar_regime(self) -> None:
        empresa = self.servico.repositorio.obter_empresa_por_nome(self.var_empresa.get())
        if not empresa:
            return
        self.servico.repositorio.atualizar_regime_empresa(int(empresa["id"]), self.var_regime.get())
        self.atualizar_modelos()

    def _nova_empresa(self) -> None:
        JanelaCadastroEmpresa(
            self,
            self.servico,
            ao_salvar=self._apos_salvar_empresa,
        )

    def _editar_empresa(self) -> None:
        empresa = self.servico.repositorio.obter_empresa_por_nome(self.var_empresa.get())
        if not empresa:
            messagebox.showwarning("Empresa", "Selecione uma empresa.", parent=self)
            return
        JanelaCadastroEmpresa(
            self,
            self.servico,
            empresa=empresa,
            ao_salvar=self._apos_salvar_empresa,
        )

    def _apos_salvar_empresa(self, nome: str) -> None:
        self.var_empresa.set(nome)
        self.atualizar()

    def _alternar(self) -> None:
        empresa, obrigacao = self._selecionados()
        if not empresa:
            return
        modelo = self.servico.repositorio.obter_modelo_por_empresa_tipo(
            int(empresa["id"]), obrigacao, incluir_inativo=True
        )
        if modelo is not None and int(modelo["ativo"] or 0):
            self.servico.repositorio.excluir_modelo(int(modelo["id"]))
        else:
            dia = int(modelo["dia_prazo"] or 0) if modelo else self.servico.PRAZOS_INICIAIS.get(obrigacao, (0, 1))[0]
            apos = int(modelo["meses_apos_competencia"] or 1) if modelo else self.servico.PRAZOS_INICIAIS.get(obrigacao, (0, 1))[1]
            self.servico.repositorio.salvar_modelo(
                empresa_id=int(empresa["id"]), tipo_arquivo=obrigacao,
                dia_prazo=dia, meses_apos_competencia=apos,
                modelo_id=int(modelo["id"]) if modelo else None,
            )
        self.atualizar_modelos()

    def _editar_prazo(self) -> None:
        empresa, obrigacao = self._selecionados()
        if not empresa:
            return
        modelo = self.servico.repositorio.obter_modelo_por_empresa_tipo(
            int(empresa["id"]), obrigacao, incluir_inativo=True
        )
        dia_atual = int(modelo["dia_prazo"] or 0) if modelo else 0
        apos_atual = int(modelo["meses_apos_competencia"] or 1) if modelo else 1
        dia = simpledialog.askinteger(
            "Dia do prazo", "Dia do vencimento (0 = sem prazo fixo):",
            parent=self, minvalue=0, maxvalue=31, initialvalue=dia_atual,
        )
        if dia is None:
            return
        meses = simpledialog.askinteger(
            "Prazo após competência",
            "Quantos meses após a competência?\n0 = mesmo mês | 1 = mês seguinte | 2 = dois meses depois",
            parent=self, minvalue=0, maxvalue=12, initialvalue=apos_atual,
        )
        if meses is None:
            return
        estava_ativo = bool(modelo is None or int(modelo["ativo"] or 0))
        modelo_id = self.servico.repositorio.salvar_modelo(
            empresa_id=int(empresa["id"]), tipo_arquivo=obrigacao,
            dia_prazo=dia, meses_apos_competencia=meses,
            modelo_id=int(modelo["id"]) if modelo else None,
        )
        if not estava_ativo:
            self.servico.repositorio.excluir_modelo(modelo_id)
        self.atualizar_modelos()

    def _fechar(self) -> None:
        if self.ao_fechar:
            self.ao_fechar()
        self.destroy()


class JanelaCadastroEmpresa(Toplevel):
    """Inclui ou edita uma empresa persistente do FiscalPro."""

    def __init__(self, master, servico: EntregasServico, empresa=None, ao_salvar=None):
        super().__init__(master)
        self.servico = servico
        self.empresa = empresa
        self.ao_salvar = ao_salvar
        self.title("Editar empresa" if empresa is not None else "Nova empresa")
        self.geometry("560x280")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()

        self.var_nome = StringVar(value=str(empresa["nome"]) if empresa is not None else "")
        self.var_cnpj = StringVar(value=self._formatar_cnpj(empresa["cnpj"]) if empresa is not None else "")
        self.var_regime = StringVar(
            value=str(empresa["regime"] or "A DEFINIR") if empresa is not None else "A DEFINIR"
        )
        self._criar()

    @staticmethod
    def _formatar_cnpj(valor: object) -> str:
        digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
        if len(digitos) != 14:
            return digitos
        return (
            f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/"
            f"{digitos[8:12]}-{digitos[12:]}"
        )

    def _criar(self) -> None:
        corpo = ttk.Frame(self, padding=16, style="Page.TFrame")
        corpo.pack(fill=BOTH, expand=True)
        corpo.columnconfigure(1, weight=1)

        ttk.Label(corpo, text="Nome / Razão social").grid(row=0, column=0, sticky="w", pady=7)
        self.ent_nome = ttk.Entry(corpo, textvariable=self.var_nome)
        self.ent_nome.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=7)

        ttk.Label(corpo, text="CNPJ").grid(row=1, column=0, sticky="w", pady=7)
        ttk.Entry(corpo, textvariable=self.var_cnpj).grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=7
        )

        ttk.Label(corpo, text="Regime tributário").grid(row=2, column=0, sticky="w", pady=7)
        ttk.Combobox(
            corpo,
            textvariable=self.var_regime,
            values=self.servico.REGIMES,
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=7)

        if self.empresa is not None:
            nomes_fixos = {nome.casefold() for nome, _regime in self.servico.EMPRESAS_ATUAIS}
            if str(self.empresa["nome"]).casefold() in nomes_fixos:
                self.ent_nome.configure(state="readonly")
                ttk.Label(
                    corpo,
                    text="Empresa-base: o nome é protegido; CNPJ e regime podem ser ajustados.",
                    style="CardSubtitle.TLabel",
                ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 4))

        botoes = ttk.Frame(corpo, style="Page.TFrame")
        botoes.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            botoes,
            text="Salvar empresa",
            command=self._salvar,
            style="Primary.TButton",
        ).pack(side=LEFT)

        self.bind("<Return>", lambda _e: self._salvar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.ent_nome.focus_set()

    def _salvar(self) -> None:
        nome = self.var_nome.get().strip()
        try:
            if self.empresa is None:
                self.servico.cadastrar_empresa(nome, self.var_cnpj.get(), self.var_regime.get())
            else:
                self.servico.editar_empresa(
                    int(self.empresa["id"]),
                    nome,
                    self.var_cnpj.get(),
                    self.var_regime.get(),
                )
        except Exception as erro:
            messagebox.showerror("Empresa", str(erro), parent=self)
            return

        nome_final = nome
        if self.empresa is not None:
            atualizado = self.servico.repositorio.obter_empresa_por_id(int(self.empresa["id"]))
            if atualizado is not None:
                nome_final = str(atualizado["nome"])
        messagebox.showinfo(
            "Empresa",
            "Empresa cadastrada com sucesso." if self.empresa is None else "Empresa atualizada com sucesso.",
            parent=self,
        )
        if self.ao_salvar:
            self.ao_salvar(nome_final)
        self.destroy()
