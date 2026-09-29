"""Tela da Correção Tributária Assistida em Lote — Sprint 17.3.0."""

from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List

from src.services.analise_tributaria_lote_service import ResultadoAnaliseLote
from src.services.correcao_tributaria_lote_service import (
    CorrecaoTributariaLoteService,
    PropostaCorrecaoLote,
    ResultadoAplicacaoCorrecaoLote,
    ResultadoPreparacaoCorrecaoLote,
)
from src.ui.layout_responsivo import dimensionar_janela


class JanelaCorrecaoTributariaLote(tk.Toplevel):
    """Permite confirmar item a item as correções seguras encontradas no SPED."""

    def __init__(self, master, analise: ResultadoAnaliseLote):
        super().__init__(master)
        self.title("FiscalPro — Correção tributária assistida em lote")
        dimensionar_janela(self, 1240, 760, 920, 560)
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        self.service = CorrecaoTributariaLoteService()
        self.preparacao: ResultadoPreparacaoCorrecaoLote = self.service.preparar(analise)
        self.propostas_visiveis: List[PropostaCorrecaoLote] = []
        self._processando = False
        self._fila: queue.Queue = queue.Queue()

        self.var_resumo = tk.StringVar()
        self.var_status = tk.StringVar(value="Confira o antes e depois e mantenha marcadas apenas as correções desejadas.")
        self.var_filtro = tk.StringVar(value="Todas")

        self._montar()
        self._atualizar_resumo()
        self._preencher()
        if not self.preparacao.propostas:
            self.after(100, self._avisar_sem_propostas)

    def _montar(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        cabecalho = ttk.Frame(self, padding=(14, 12, 14, 7))
        cabecalho.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            cabecalho,
            text="Correção Tributária Assistida em Lote",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            cabecalho,
            text=(
                "Somente divergências confirmadas de arquivos SPED diretos são propostas. "
                "XMLs permanecem somente para leitura. O FiscalPro sempre gera uma nova cópia."
            ),
            wraplength=1120,
        ).pack(anchor="w", pady=(3, 0))

        barra = ttk.Frame(self, padding=(14, 0, 14, 7))
        barra.grid(row=1, column=0, sticky="ew")
        ttk.Label(barra, textvariable=self.var_resumo, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(barra, text="Filtro:").pack(side=tk.RIGHT, padx=(8, 4))
        filtro = ttk.Combobox(
            barra,
            textvariable=self.var_filtro,
            state="readonly",
            width=16,
            values=("Todas", "Marcadas", "Desmarcadas", "Conflitos"),
        )
        filtro.pack(side=tk.RIGHT)
        filtro.bind("<<ComboboxSelected>>", lambda _e: self._preencher())

        area = ttk.Frame(self, padding=(14, 0, 14, 7))
        area.grid(row=2, column=0, sticky="nsew")
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)

        colunas = (
            "marcar", "arquivo", "linha", "registro", "campo", "antes",
            "depois", "seguranca", "produto",
        )
        self.tabela = ttk.Treeview(area, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "marcar": "Aplicar", "arquivo": "SPED", "linha": "Linha",
            "registro": "Registro", "campo": "Campo", "antes": "Antes",
            "depois": "Depois", "seguranca": "Segurança", "produto": "Produto / NCM",
        }
        larguras = {
            "marcar": 65, "arquivo": 175, "linha": 65, "registro": 75,
            "campo": 135, "antes": 100, "depois": 100, "seguranca": 90,
            "produto": 275,
        }
        for coluna in colunas:
            self.tabela.heading(coluna, text=titulos[coluna])
            self.tabela.column(
                coluna,
                width=larguras[coluna],
                minwidth=55,
                anchor="center" if coluna not in {"arquivo", "campo", "produto"} else "w",
            )
        yscroll = ttk.Scrollbar(area, orient="vertical", command=self.tabela.yview)
        xscroll = ttk.Scrollbar(area, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tabela.tag_configure("conflito", foreground="#9b1c1c")
        self.tabela.bind("<Double-1>", self._alternar_selecionada)
        self.tabela.bind("<space>", self._alternar_selecionada)
        self.tabela.bind("<Return>", self._mostrar_detalhes)

        rodape = ttk.Frame(self, padding=(14, 4, 14, 12))
        rodape.grid(row=3, column=0, sticky="ew")
        ttk.Label(rodape, textvariable=self.var_status, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(rodape, text="Marcar todas", command=self._marcar_todas).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(rodape, text="Desmarcar todas", command=self._desmarcar_todas).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(rodape, text="Ver detalhes", command=self._mostrar_detalhes).pack(side=tk.LEFT, padx=(6, 0))
        self.btn_aplicar = ttk.Button(rodape, text="Gerar cópias corrigidas", command=self._aplicar)
        self.btn_aplicar.pack(side=tk.LEFT, padx=(12, 0))
        ttk.Button(rodape, text="Fechar", command=self._fechar).pack(side=tk.LEFT, padx=(6, 0))

    def _atualizar_resumo(self) -> None:
        self.var_resumo.set(
            f"Propostas: {self.preparacao.total}  •  Marcadas: {self.preparacao.total_selecionadas}  •  "
            f"SPEDs: {self.preparacao.arquivos_sped}  •  XML somente leitura: "
            f"{self.preparacao.itens_xml_somente_leitura}  •  Conflitos: {len(self.preparacao.conflitos)}"
        )
        self.btn_aplicar.configure(
            state="normal" if self.preparacao.total_selecionadas and not self._processando else "disabled"
        )

    def _preencher(self) -> None:
        for iid in self.tabela.get_children():
            self.tabela.delete(iid)
        filtro = self.var_filtro.get()
        propostas = self.preparacao.propostas
        if filtro == "Marcadas":
            propostas = [p for p in propostas if p.selecionada]
        elif filtro == "Desmarcadas":
            propostas = [p for p in propostas if not p.selecionada and not p.conflito]
        elif filtro == "Conflitos":
            propostas = [p for p in propostas if p.conflito]
        self.propostas_visiveis = propostas
        for indice, proposta in enumerate(propostas):
            marcador = "⚠" if proposta.conflito else ("☑" if proposta.selecionada else "☐")
            produto = f"{proposta.codigo or '-'} — NCM {proposta.ncm or '-'}"
            self.tabela.insert(
                "", "end", iid=str(indice), tags=("conflito",) if proposta.conflito else (),
                values=(
                    marcador, Path(proposta.caminho_origem).name, proposta.numero_linha,
                    proposta.registro, proposta.campo, proposta.valor_atual or "-",
                    proposta.valor_sugerido or "-", f"{proposta.confiabilidade:.0f}%", produto,
                ),
            )

    def _proposta_selecionada(self) -> PropostaCorrecaoLote | None:
        selecao = self.tabela.selection()
        if not selecao:
            return None
        try:
            return self.propostas_visiveis[int(selecao[0])]
        except (IndexError, ValueError):
            return None

    def _alternar_selecionada(self, _evento=None) -> None:
        proposta = self._proposta_selecionada()
        if proposta is None:
            return
        if proposta.conflito:
            messagebox.showwarning(
                "FiscalPro", "Esta proposta possui conflito e não pode ser marcada.", parent=self,
            )
            return
        proposta.selecionada = not proposta.selecionada
        self._atualizar_resumo()
        self._preencher()

    def _marcar_todas(self) -> None:
        for proposta in self.preparacao.propostas:
            proposta.selecionada = proposta.aplicavel
        self._atualizar_resumo()
        self._preencher()

    def _desmarcar_todas(self) -> None:
        for proposta in self.preparacao.propostas:
            proposta.selecionada = False
        self._atualizar_resumo()
        self._preencher()

    def _mostrar_detalhes(self, _evento=None) -> None:
        proposta = self._proposta_selecionada()
        if proposta is None:
            messagebox.showinfo("FiscalPro", "Selecione uma proposta.", parent=self)
            return
        texto = (
            f"Arquivo: {proposta.caminho_origem}\n"
            f"Linha/registro: {proposta.numero_linha} / {proposta.registro}\n"
            f"Documento/item: {proposta.documento or '-'} / {proposta.numero_item or '-'}\n"
            f"Produto: {proposta.codigo or '-'} — NCM {proposta.ncm or '-'}\n\n"
            f"Campo: {proposta.campo}\n"
            f"Antes: {proposta.valor_atual or '-'}\n"
            f"Depois: {proposta.valor_sugerido or '-'}\n"
            f"Segurança: {proposta.confiabilidade:.2f}%\n\n"
            f"Origem: {proposta.origem_regra or '-'}\n"
            f"Fundamento: {proposta.fundamento or '-'}\n"
            f"Justificativa: {proposta.justificativa or '-'}"
        )
        messagebox.showinfo("Detalhes da correção", texto, parent=self)

    def _aplicar(self) -> None:
        if self._processando:
            return
        quantidade = self.preparacao.total_selecionadas
        if not quantidade:
            messagebox.showwarning("FiscalPro", "Marque ao menos uma proposta.", parent=self)
            return
        pasta = filedialog.askdirectory(
            title="Escolha a pasta para as cópias corrigidas e relatórios", parent=self,
        )
        if not pasta:
            return
        confirmar = messagebox.askyesno(
            "FiscalPro",
            f"Gerar novas cópias com {quantidade} correção(ões) marcada(s)?\n\n"
            "Os arquivos originais não serão alterados. O Bloco M deverá ser recalculado "
            "no PVA quando houver mudanças de PIS/Cofins.",
            parent=self,
        )
        if not confirmar:
            return
        self._processando = True
        self.btn_aplicar.configure(state="disabled")
        self.var_status.set("Gerando cópias, recalculando dependências e executando o Pré-Validador...")

        def executar() -> None:
            try:
                valor = self.service.aplicar(self.preparacao, pasta)
                self._fila.put(("ok", valor))
            except Exception as erro:  # pragma: no cover - proteção da interface.
                self._fila.put(("erro", erro))

        threading.Thread(target=executar, daemon=True).start()
        self.after(100, self._verificar_fila)

    def _verificar_fila(self) -> None:
        try:
            tipo, valor = self._fila.get_nowait()
        except queue.Empty:
            if self._processando and self.winfo_exists():
                self.after(100, self._verificar_fila)
            return
        self._processando = False
        self._atualizar_resumo()
        if tipo == "erro":
            self.var_status.set("Não foi possível gerar as cópias corrigidas.")
            messagebox.showerror("FiscalPro", str(valor), parent=self)
            return
        self._concluido(valor)

    def _concluido(self, resultado: ResultadoAplicacaoCorrecaoLote) -> None:
        self.var_status.set(
            f"Concluído: {resultado.total_arquivos} arquivo(s) e {resultado.total_alteracoes} alteração(ões)."
        )
        caminhos = "\n".join(f"• {item.caminho_saida}" for item in resultado.arquivos)
        aviso_bloco_m = any(item.requer_reapuracao_bloco_m for item in resultado.arquivos)
        texto = (
            f"Correção concluída com sucesso.\n\n{caminhos}\n\n"
            f"Relatório Excel:\n{resultado.caminho_relatorio_excel}"
        )
        if aviso_bloco_m:
            texto += "\n\nAtenção: recalcule o Bloco M e valide cada cópia no PVA oficial."
        messagebox.showinfo("FiscalPro", texto, parent=self)

    def _avisar_sem_propostas(self) -> None:
        avisos = "\n".join(f"• {item}" for item in self.preparacao.avisos[:8])
        messagebox.showinfo(
            "FiscalPro",
            "Nenhuma correção automática segura foi preparada.\n\n" + (avisos or "Revise a análise em lote."),
            parent=self,
        )

    def _fechar(self) -> None:
        if self._processando:
            if not messagebox.askyesno(
                "FiscalPro", "A geração ainda está em andamento. Deseja fechar a tela?", parent=self,
            ):
                return
        self.destroy()


__all__ = ["JanelaCorrecaoTributariaLote"]
