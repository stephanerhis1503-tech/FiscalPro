"""Janela simples de backup e restauração do FiscalPro."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, Frame, Label, StringVar, Toplevel
from tkinter import filedialog, messagebox, ttk

from src.backup.service import BackupInvalidoError, ServicoBackup
from src.core.caminhos import PASTA_BACKUPS

from .estilos import (
    COR_BORDA,
    COR_CARD,
    COR_DESTAQUE,
    COR_PRIMARIA,
    COR_TEXTO,
    COR_TEXTO_SUAVE,
    FONTE_NORMAL,
    configurar_tema,
)
from .recursos import aplicar_icone
from .layout_responsivo import dimensionar_janela, vincular_wraplength


class JanelaBackup:
    def __init__(self, master, ao_restaurar=None):
        self.master = master
        self.ao_restaurar = ao_restaurar
        self.servico = ServicoBackup()
        self.servico.preparar()

        self.janela = Toplevel(master)
        self.janela.title("Backup e restauração — FiscalPro")
        self.janela.transient(master)
        self.janela.grab_set()
        configurar_tema(self.janela)
        aplicar_icone(self.janela)
        dimensionar_janela(self.janela, 860, 680, 660, 500, maximizar_em_tela_baixa=False)

        self.incluir_documentos = BooleanVar(value=True)
        self.status = StringVar(value="Pronto para proteger seus dados.")
        self.criar_interface()
        self.atualizar_lista()

    def criar_interface(self):
        topo = Frame(self.janela, bg=COR_PRIMARIA, height=88)
        topo.pack(fill=X)
        topo.pack_propagate(False)

        Label(
            topo,
            text="Backup e restauração",
            bg=COR_PRIMARIA,
            fg="white",
            font=("Segoe UI", 19, "bold"),
        ).pack(anchor="w", padx=24, pady=(16, 0))
        Label(
            topo,
            text="Proteja todos os dados do FiscalPro e, se quiser, os documentos fiscais arquivados.",
            bg=COR_PRIMARIA,
            fg="#DCEAF5",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=24, pady=(3, 12))

        corpo = ttk.Frame(self.janela, style="Page.TFrame", padding=18)
        corpo.pack(fill=BOTH, expand=True)

        card = Frame(
            corpo,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=18,
            pady=16,
        )
        card.pack(fill=X)

        Label(
            card,
            text="Criar uma cópia de segurança",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        Label(
            card,
            text=(
                "O backup sempre inclui os bancos e dados internos do FiscalPro: "
                "Contas a Pagar, Controle de Entregas, tributação, login, "
                "configurações e dados históricos dos módulos desativados."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=FONTE_NORMAL,
            wraplength=670,
            justify=LEFT,
        ).pack(anchor="w", pady=(6, 10))

        ttk.Checkbutton(
            card,
            text="Incluir também os documentos fiscais arquivados",
            variable=self.incluir_documentos,
        ).pack(anchor="w", pady=(0, 12))

        botoes = Frame(card, bg=COR_CARD)
        botoes.pack(fill=X)
        ttk.Button(
            botoes,
            text="Criar backup agora",
            command=self.criar_backup,
            style="Primary.TButton",
        ).pack(side=LEFT, padx=(0, 8))
        ttk.Button(
            botoes,
            text="Restaurar um backup",
            command=self.restaurar_backup,
            style="Secondary.TButton",
        ).pack(side=LEFT, padx=8)
        ttk.Button(
            botoes,
            text="Abrir pasta de backups",
            command=self.abrir_pasta,
            style="Secondary.TButton",
        ).pack(side=LEFT, padx=8)

        Label(
            corpo,
            text="Backups recentes",
            bg=self.janela.cget("bg"),
            fg=COR_TEXTO,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(18, 7))

        quadro_lista = ttk.Frame(corpo, style="Card.TFrame")
        quadro_lista.pack(fill=BOTH, expand=True)
        quadro_lista.rowconfigure(0, weight=1)
        quadro_lista.columnconfigure(0, weight=1)

        self.lista = ttk.Treeview(
            quadro_lista,
            columns=("tipo", "data", "tamanho"),
            show="tree headings",
            height=8,
        )
        self.lista.heading("#0", text="Arquivo")
        self.lista.heading("tipo", text="Tipo")
        self.lista.heading("data", text="Data")
        self.lista.heading("tamanho", text="Tamanho")
        self.lista.column("#0", width=340, anchor="w")
        self.lista.column("tipo", width=100, anchor="center")
        self.lista.column("data", width=145, anchor="center")
        self.lista.column("tamanho", width=95, anchor="e")
        barra = ttk.Scrollbar(quadro_lista, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.lista.bind("<Double-1>", self._restaurar_selecionado)

        rodape = Frame(self.janela, bg=COR_CARD, height=38)
        rodape.pack(fill=X, side="bottom")
        rodape.pack_propagate(False)
        Label(
            rodape,
            textvariable=self.status,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
        ).pack(side=LEFT, padx=18)
        ttk.Button(
            rodape,
            text="Fechar",
            command=self.janela.destroy,
            style="Link.TButton",
        ).pack(side=RIGHT, padx=12, pady=3)

    def criar_backup(self):
        incluir = bool(self.incluir_documentos.get())
        texto = "Criando backup completo..." if incluir else "Criando backup..."
        self._definir_status(texto)
        self._habilitar_interface(False)
        try:
            resultado = self.servico.criar_backup(
                tipo="manual",
                incluir_documentos=incluir,
            )
            self.atualizar_lista()
            self._definir_status(f"Backup criado: {resultado.caminho.name}")
            contas = (
                f"\nContas a Pagar protegidas: {resultado.contas_pagar:,}".replace(",", ".")
                if resultado.contas_pagar is not None
                else ""
            )
            messagebox.showinfo(
                "FiscalPro",
                (
                    "Backup criado com sucesso!\n\n"
                    f"Arquivo: {resultado.caminho.name}\n"
                    f"Itens protegidos: {resultado.quantidade_arquivos}"
                    f"{contas}\n"
                    f"Pasta: {resultado.caminho.parent}"
                ),
                parent=self.janela,
            )
        except Exception as erro:
            self._definir_status("Não foi possível criar o backup.")
            messagebox.showerror("FiscalPro", str(erro), parent=self.janela)
        finally:
            self._habilitar_interface(True)

    def restaurar_backup(self, caminho: str | Path | None = None):
        if caminho is None:
            selecionado = filedialog.askopenfilename(
                title="Selecione o backup do FiscalPro",
                initialdir=str(PASTA_BACKUPS),
                filetypes=[("Backup do FiscalPro", "*.zip")],
                parent=self.janela,
            )
            if not selecionado:
                return
            caminho = selecionado

        arquivo = Path(caminho)
        try:
            manifesto = self.servico.validar_backup(arquivo)
        except BackupInvalidoError as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self.janela)
            return

        data = str(manifesto.get("criado_em", ""))
        versao = str(manifesto.get("versao_aplicativo", ""))
        resumo_contas = None
        modulos = manifesto.get("modulos")
        if isinstance(modulos, dict) and isinstance(modulos.get("contas_pagar"), dict):
            resumo_contas = modulos["contas_pagar"]
        texto_contas = ""
        if resumo_contas is not None:
            quantidade = int(resumo_contas.get("registros", 0))
            integridade = str(resumo_contas.get("integridade_sqlite", "")) or "não informada"
            quantidade_txt = f"{quantidade:,}".replace(",", ".")
            texto_contas = (
                f"Contas a Pagar no backup: {quantidade_txt}\n"
                f"Integridade do banco: {integridade}\n"
            )
        confirmar = messagebox.askyesno(
            "Restaurar backup",
            (
                "O FiscalPro criará uma cópia de segurança do estado atual antes de restaurar.\n\n"
                f"Backup: {arquivo.name}\n"
                f"Versão: {versao}\n"
                f"Criado em: {data}\n"
                f"{texto_contas}\n"
                "Deseja continuar?"
            ),
            parent=self.janela,
        )
        if not confirmar:
            return

        self._habilitar_interface(False)
        self._definir_status("Validando e restaurando o backup...")
        try:
            resultado = self.servico.restaurar_backup(arquivo)
            self._definir_status("Backup restaurado com sucesso.")
            messagebox.showinfo(
                "FiscalPro",
                (
                    "Restauração concluída com sucesso!\n\n"
                    f"Arquivos restaurados: {resultado['arquivos_restaurados']}\n"
                    "O FiscalPro voltará para a tela de login para recarregar os dados."
                ),
                parent=self.janela,
            )
            self.janela.destroy()
            if callable(self.ao_restaurar):
                self.ao_restaurar()
        except Exception as erro:
            self._definir_status("Não foi possível restaurar o backup.")
            messagebox.showerror(
                "FiscalPro",
                (
                    f"A restauração não foi concluída.\n\n{erro}\n\n"
                    "Quando criada, a cópia de segurança anterior permanece na pasta de backups."
                ),
                parent=self.janela,
            )
        finally:
            if self.janela.winfo_exists():
                self._habilitar_interface(True)

    def atualizar_lista(self):
        for item in self.lista.get_children():
            self.lista.delete(item)

        for arquivo in self.servico.listar_backups(20):
            pasta = arquivo.parent.name.casefold()
            tipo = {
                "manuais": "Manual",
                "automaticos": "Automático",
                "seguranca": "Segurança",
            }.get(pasta, "Backup")
            data = datetime.fromtimestamp(arquivo.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            tamanho = self._formatar_tamanho(arquivo.stat().st_size)
            self.lista.insert(
                "",
                END,
                iid=str(arquivo),
                text=arquivo.name,
                values=(tipo, data, tamanho),
            )

    def abrir_pasta(self):
        self.servico.preparar()
        caminho = str(self.servico.pasta_backups)
        try:
            if os.name == "nt":
                os.startfile(caminho)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", caminho])
            else:
                subprocess.Popen(["xdg-open", caminho])
        except OSError as erro:
            messagebox.showerror("FiscalPro", str(erro), parent=self.janela)

    def _restaurar_selecionado(self, _evento=None):
        selecao = self.lista.selection()
        if selecao:
            self.restaurar_backup(selecao[0])

    def _definir_status(self, texto: str):
        self.status.set(texto)
        self.janela.update_idletasks()

    def _habilitar_interface(self, habilitar: bool):
        estado = "normal" if habilitar else "disabled"
        for filho in self.janela.winfo_children():
            self._alterar_estado_recursivo(filho, estado)

    @classmethod
    def _alterar_estado_recursivo(cls, widget, estado: str):
        try:
            if isinstance(widget, (ttk.Button, ttk.Checkbutton)):
                widget.configure(state=estado)
        except Exception:
            pass
        for filho in widget.winfo_children():
            cls._alterar_estado_recursivo(filho, estado)

    @staticmethod
    def _formatar_tamanho(tamanho: int) -> str:
        valor = float(tamanho)
        for unidade in ("B", "KB", "MB", "GB"):
            if valor < 1024 or unidade == "GB":
                return f"{valor:.1f} {unidade}" if unidade != "B" else f"{int(valor)} B"
            valor /= 1024
        return f"{valor:.1f} GB"
