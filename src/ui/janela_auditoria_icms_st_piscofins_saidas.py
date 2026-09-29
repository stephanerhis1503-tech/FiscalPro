"""Tela da Etapa 2 — auditoria das saídas com ST já recolhido."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from src.services.auditoria_icms_st_piscofins_saidas_service import (
    AuditoriaICMSSTPISCOFINSSaidasService,
    ResultadoPreAuditoriaSaidas,
    STATUS_ALIQUOTA_ZERO,
    STATUS_CANDIDATO_XML,
    STATUS_REVISAR_BASE,
    STATUS_CORRIGIR_ST,
    STATUS_OK_ST_FORA,
    STATUS_SEM_ST_XML,
    STATUS_XML_NAO_LOCALIZADO,
    STATUS_VINCULO_XML,
    STATUS_COMPOSICAO_BASE,
)
from .layout_responsivo import dimensionar_janela


class JanelaAuditoriaICMSSTPISCOFINSSaidas(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Exclusão ICMS-ST da Base PIS/COFINS — Etapa 2")
        dimensionar_janela(self, 1500, 900, 1120, 680)
        self.transient(parent)

        self.arquivo_sped = ""
        self.fonte_xml = ""
        self.resultado: Optional[ResultadoPreAuditoriaSaidas] = None
        self._processando = False
        self._fila: queue.Queue = queue.Queue()
        self._registros_visiveis = []

        self.var_sped = tk.StringVar(value="Nenhum SPED selecionado.")
        self.var_xml = tk.StringVar(value="Nenhum ZIP/XML de saída selecionado.")
        self.var_status = tk.StringVar(value="Selecione o SPED e os XMLs de saída. Nenhum arquivo será alterado.")
        self.var_resumo = tk.StringVar(value="Registros 5405: 0  •  Corrigir: 0  •  Sem valor ST XML: 0  •  Alíquota zero: 0  •  Revisar: 0")
        self.var_filtro = tk.StringVar(value="Correção identificada")
        self.var_busca = tk.StringVar(value="")
        self.var_correcao = tk.StringVar(value="Correção bloqueada até a auditoria com XML ficar sem pendências.")
        self._montar()

    def _montar(self) -> None:
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        cab = ttk.Frame(self, padding=(14, 12, 14, 6))
        cab.grid(row=0, column=0, sticky="ew")
        ttk.Label(cab, text="Etapa 2 — Saídas com ST já recolhido", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            cab,
            text=(
                "Cruza o SPED Contribuições com os XMLs autorizados de saída. O SPED selecionado pode ser o original ou um arquivo já corrigido pela Etapa 1. Para CFOP 5405, o FiscalPro usa o valor de ICMS-ST retido "
                "informado no XML (vICMSSTRet), verifica se ele ainda está na base de PIS/COFINS e sugere a nova base. "
                "Quando não houver pendências de vínculo/base, a correção segura gera um único SPED FINAL, preservando todas as correções já existentes no arquivo base."
            ),
            wraplength=1400,
        ).pack(anchor="w", pady=(3, 0))

        fonte = ttk.LabelFrame(self, text="1. Arquivos da auditoria", padding=10)
        fonte.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 7))
        fonte.grid_columnconfigure(2, weight=1)
        ttk.Button(fonte, text="Selecionar SPED base", command=self._selecionar_sped).grid(row=0, column=0, sticky="ew")
        ttk.Label(fonte, textvariable=self.var_sped, anchor="w").grid(row=0, column=1, columnspan=2, sticky="ew", padx=(10, 0))
        ttk.Button(fonte, text="Selecionar ZIP/XML", command=self._selecionar_xml).grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(fonte, text="Selecionar pasta XML", command=self._selecionar_pasta_xml).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(fonte, textvariable=self.var_xml, anchor="w").grid(row=1, column=2, sticky="ew", padx=(10, 0), pady=(6, 0))

        acoes = ttk.Frame(self, padding=(14, 0, 14, 7))
        acoes.grid(row=2, column=0, sticky="ew")
        self.btn_auditar = ttk.Button(acoes, text="Auditar saídas + XML", command=self._auditar_xml)
        self.btn_auditar.pack(side=tk.LEFT)
        ttk.Button(acoes, text="Pré-auditar só SPED", command=self._pre_auditar).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(acoes, text="Limpar", command=self._limpar).pack(side=tk.LEFT, padx=(8, 0))
        self.btn_aplicar = ttk.Button(
            acoes, text="Gerar SPED FINAL corrigido", command=self._aplicar_correcoes, state="disabled"
        )
        self.btn_aplicar.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            acoes,
            textvariable=self.var_correcao,
            foreground="#8A5A00",
        ).pack(side=tk.LEFT, padx=(12, 0))

        filtros = ttk.Frame(self, padding=(14, 0, 14, 7))
        filtros.grid(row=3, column=0, sticky="ew")
        ttk.Label(filtros, textvariable=self.var_resumo, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(filtros, text="Busca:").pack(side=tk.RIGHT, padx=(10, 4))
        busca = ttk.Entry(filtros, textvariable=self.var_busca, width=24)
        busca.pack(side=tk.RIGHT)
        busca.bind("<KeyRelease>", lambda _e: self._preencher())
        ttk.Label(filtros, text="Filtro:").pack(side=tk.RIGHT, padx=(10, 4))
        combo = ttk.Combobox(
            filtros,
            textvariable=self.var_filtro,
            state="readonly",
            width=27,
            values=(
                "Correção identificada",
                "Sem valor ST no XML",
                "Alíquota zero",
                "OK — ST já fora",
                "Revisar vínculo/base",
                "Com base tributada (pré)",
                "NF-e itens (C170)",
                "NFC-e analítico (C175)",
                "Todos CFOP 5405",
            ),
        )
        combo.pack(side=tk.RIGHT)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._preencher())

        area = ttk.Frame(self)
        area.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 7))
        area.grid_rowconfigure(1, weight=1)
        area.grid_columnconfigure(0, weight=1)
        ttk.Label(area, textvariable=self.var_status, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 4))

        quadro = ttk.Frame(area)
        quadro.grid(row=1, column=0, sticky="nsew")
        quadro.grid_rowconfigure(0, weight=1)
        quadro.grid_columnconfigure(0, weight=1)

        colunas = (
            "status", "modelo", "nf", "registro", "item", "codigo", "descricao", "cfop",
            "cst_pis", "base_pis", "st_xml", "base_pis_nova", "cst_cof", "base_cof", "base_cof_nova", "linha",
        )
        self.tabela = ttk.Treeview(quadro, columns=colunas, show="headings", selectmode="browse")
        titulos = {
            "status": "Status", "modelo": "Modelo", "nf": "NF", "registro": "Registro", "item": "Item",
            "codigo": "Código", "descricao": "Descrição", "cfop": "CFOP", "cst_pis": "CST PIS", "base_pis": "Base PIS",
            "st_xml": "ICMS-ST XML", "base_pis_nova": "Base PIS sugerida", "cst_cof": "CST COFINS", "base_cof": "Base COFINS",
            "base_cof_nova": "Base COFINS sugerida", "linha": "Linha SPED",
        }
        larguras = {
            "status": 330, "modelo": 65, "nf": 85, "registro": 72, "item": 52, "codigo": 110, "descricao": 250,
            "cfop": 65, "cst_pis": 70, "base_pis": 95, "st_xml": 100, "base_pis_nova": 125, "cst_cof": 85,
            "base_cof": 105, "base_cof_nova": 135, "linha": 80,
        }
        for coluna in colunas:
            self.tabela.heading(coluna, text=titulos[coluna])
            self.tabela.column(coluna, width=larguras[coluna], minwidth=50, anchor="w", stretch=coluna in {"status", "descricao"})
        for coluna in ("modelo", "nf", "registro", "item", "cfop", "cst_pis", "base_pis", "st_xml", "base_pis_nova", "cst_cof", "base_cof", "base_cof_nova", "linha"):
            self.tabela.column(coluna, anchor="center")
        y = ttk.Scrollbar(quadro, orient="vertical", command=self.tabela.yview)
        x = ttk.Scrollbar(quadro, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        self.tabela.bind("<Double-1>", self._detalhes)
        self.tabela.tag_configure(STATUS_CORRIGIR_ST, background="#FDE9E7")
        self.tabela.tag_configure(STATUS_OK_ST_FORA, background="#E9F6EC")
        self.tabela.tag_configure(STATUS_SEM_ST_XML, background="#FFF4D6")
        self.tabela.tag_configure(STATUS_ALIQUOTA_ZERO, background="#EDF3F8")
        self.tabela.tag_configure(STATUS_XML_NAO_LOCALIZADO, background="#FDE9E7")
        self.tabela.tag_configure(STATUS_VINCULO_XML, background="#FDE9E7")
        self.tabela.tag_configure(STATUS_COMPOSICAO_BASE, background="#FDE9E7")
        self.tabela.tag_configure(STATUS_REVISAR_BASE, background="#FDE9E7")
        self.tabela.tag_configure(STATUS_CANDIDATO_XML, background="#FFF4D6")

        rodape = ttk.Frame(self, padding=(14, 0, 14, 10))
        rodape.grid(row=5, column=0, sticky="ew")
        ttk.Label(
            rodape,
            text=(
                "C175 é analítico: o FiscalPro soma os itens CFOP 5405 do XML por classe tributária e confere a base do registro. "
                "XML sem vICMSSTRet positivo não gera correção automática."
            ),
        ).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

    def _selecionar_sped(self) -> None:
        arquivo = filedialog.askopenfilename(parent=self, title="Selecione o SPED Contribuições", filetypes=(("SPED TXT", "*.txt"), ("Todos", "*.*")))
        if arquivo:
            self.arquivo_sped = arquivo
            self.var_sped.set(Path(arquivo).name)

    def _selecionar_xml(self) -> None:
        arquivo = filedialog.askopenfilename(parent=self, title="Selecione o ZIP/XML de saídas", filetypes=(("ZIP/XML", "*.zip *.xml"), ("ZIP", "*.zip"), ("XML", "*.xml"), ("Todos", "*.*")))
        if arquivo:
            self.fonte_xml = arquivo
            self.var_xml.set(Path(arquivo).name)

    def _selecionar_pasta_xml(self) -> None:
        pasta = filedialog.askdirectory(parent=self, title="Selecione a pasta dos XMLs de saída")
        if pasta:
            self.fonte_xml = pasta
            self.var_xml.set(pasta)

    def _pre_auditar(self) -> None:
        if not self.arquivo_sped:
            messagebox.showwarning("FiscalPro", "Selecione o SPED Contribuições primeiro.", parent=self)
            return
        self._iniciar_processamento(False)

    def _auditar_xml(self) -> None:
        if not self.arquivo_sped:
            messagebox.showwarning("FiscalPro", "Selecione o SPED Contribuições primeiro.", parent=self)
            return
        if not self.fonte_xml:
            messagebox.showwarning("FiscalPro", "Selecione o ZIP/XML ou a pasta dos XMLs de saída.", parent=self)
            return
        self._iniciar_processamento(True)

    def _iniciar_processamento(self, com_xml: bool) -> None:
        if self._processando:
            return
        self._processando = True
        self.btn_auditar.configure(state="disabled")
        self.btn_aplicar.configure(state="disabled")
        self.var_status.set("Iniciando auditoria... Nenhum arquivo será alterado.")
        sped = self.arquivo_sped
        xml = self.fonte_xml

        def progresso(texto: str) -> None:
            self._fila.put(("progresso", texto))

        def executar() -> None:
            try:
                if com_xml:
                    resultado = AuditoriaICMSSTPISCOFINSSaidasService.auditar_com_xml(sped, xml, progresso=progresso)
                else:
                    resultado = AuditoriaICMSSTPISCOFINSSaidasService.pre_auditar(sped, progresso=progresso)
                self._fila.put(("ok", resultado))
            except Exception as erro:
                self._fila.put(("erro", erro))

        threading.Thread(target=executar, daemon=True).start()
        self.after(100, self._verificar_fila)

    def _verificar_fila(self) -> None:
        final = False
        while True:
            try:
                tipo, valor = self._fila.get_nowait()
            except queue.Empty:
                break
            if tipo == "progresso":
                self.var_status.set(str(valor))
            elif tipo == "erro":
                final = True
                self._processando = False
                self.btn_auditar.configure(state="normal")
                self._atualizar_estado_correcao()
                self.var_status.set("Falha na auditoria.")
                messagebox.showerror("FiscalPro", str(valor), parent=self)
            elif tipo == "correcao_erro":
                final = True
                self._processando = False
                self.btn_auditar.configure(state="normal")
                self._atualizar_estado_correcao()
                self.var_status.set("A correção não foi gerada.")
                messagebox.showerror("FiscalPro", str(valor), parent=self)
            elif tipo == "correcao_ok":
                final = True
                self._processando = False
                self.btn_auditar.configure(state="normal")
                self._atualizar_estado_correcao()
                self.var_status.set(
                    f"SPED FINAL gerado: {valor.caminho_saida.name}  •  "
                    f"{valor.itens_corrigidos} item(ns)  •  novos erros Pré-PVA: {valor.novos_erros_pre_pva}."
                )
                aviso = ""
                if valor.avisos:
                    aviso = "\n\nAvisos técnicos:\n- " + "\n- ".join(valor.avisos)
                messagebox.showinfo(
                    "FiscalPro — SPED FINAL concluído",
                    f"SPED FINAL cumulativo gerado com sucesso.\n\n"
                    f"Itens corrigidos: {valor.itens_corrigidos}\n"
                    f"ICMS-ST excluído das bases: {self._moeda(valor.st_excluido)}\n"
                    f"Redução de PIS: {self._moeda(valor.reducao_pis)}\n"
                    f"Redução de COFINS: {self._moeda(valor.reducao_cofins)}\n"
                    f"C100 retotalizados: {valor.documentos_retotalizados}\n"
                    f"Alterações no Bloco M: {valor.alteracoes_bloco_m}\n"
                    f"Pré-PVA: {valor.erros_pre_pva_antes} erro(s) antes, "
                    f"{valor.erros_pre_pva_depois} depois, 0 novo(s).\n"
                    f"Reauditoria: corrigir {valor.corrigir_apos}, revisar {valor.revisar_apos}.\n\n"
                    f"SPED FINAL: {valor.caminho_saida}\n"
                    f"Log: {valor.caminho_log}" + aviso,
                    parent=self,
                )
            elif tipo == "ok":
                final = True
                self._processando = False
                self.btn_auditar.configure(state="normal")
                self.resultado = valor
                resumo = valor.resumo()
                if resumo["auditoria_com_xml"]:
                    self.var_resumo.set(
                        f"Registros 5405: {resumo['registros_5405']}  •  Corrigir: {resumo['corrigir']}  •  "
                        f"Sem valor ST XML: {resumo['sem_st_xml']}  •  Alíquota zero: {resumo['aliquota_zero']}  •  Revisar: {resumo['revisar_xml']}"
                    )
                    self.var_status.set(
                        f"XMLs autorizados: {resumo['documentos_xml_autorizados']}  •  "
                        f"ST destacado nos registros a corrigir: {self._moeda(resumo['st_corrigir'])}  •  "
                        f"Redução estimada PIS: {self._moeda(resumo['reducao_pis'])}  •  COFINS: {self._moeda(resumo['reducao_cofins'])}. "
                        "Nenhum arquivo foi alterado."
                    )
                    self.var_filtro.set("Correção identificada")
                else:
                    self.var_resumo.set(
                        f"Saídas: {resumo['documentos_saida']}  •  Docs CFOP 5405: {resumo['documentos_cfop_5405']}  •  "
                        f"Registros 5405: {resumo['registros_5405']}  •  Com base tributada: {resumo['candidatos_xml']}  •  "
                        f"Alíquota zero: {resumo['aliquota_zero']}"
                    )
                    self.var_status.set(
                        f"Pré-auditoria concluída: {resumo['c170']} C170 e {resumo['c175']} C175. "
                        f"Base PIS candidata: {self._moeda(resumo['base_pis_candidata'])}. Nenhum arquivo foi alterado."
                    )
                    self.var_filtro.set("Com base tributada (pré)")
                self._atualizar_estado_correcao()
                self._preencher()
        if self._processando and not final and self.winfo_exists():
            self.after(100, self._verificar_fila)

    def _atualizar_estado_correcao(self) -> None:
        if self._processando:
            self.btn_aplicar.configure(state="disabled")
            return
        if self.resultado is None or not self.resultado.auditoria_com_xml:
            self.btn_aplicar.configure(state="disabled")
            self.var_correcao.set("Correção bloqueada até a auditoria com XML ficar sem pendências.")
            return
        resumo = self.resultado.resumo()
        if resumo["revisar_xml"]:
            self.btn_aplicar.configure(state="disabled")
            self.var_correcao.set(
                f"Correção bloqueada: ainda há {resumo['revisar_xml']} registro(s) para revisar."
            )
            return
        if not resumo["corrigir"]:
            self.btn_aplicar.configure(state="disabled")
            self.var_correcao.set("Nenhuma correção de ICMS-ST foi identificada para aplicar.")
            return
        inseguros = [
            x for x in self.resultado.registros
            if x.status == STATUS_CORRIGIR_ST and (x.registro != "C170" or x.confianca_vinculo != "ALTA")
        ]
        if inseguros:
            self.btn_aplicar.configure(state="disabled")
            self.var_correcao.set(
                f"Correção bloqueada: {len(inseguros)} item(ns) não têm vínculo C170 de confiança ALTA."
            )
            return
        self.btn_aplicar.configure(state="normal")
        self.var_correcao.set(
            f"Auditoria validada: {resumo['corrigir']} item(ns) podem ser incorporados ao SPED FINAL."
        )

    def _aplicar_correcoes(self) -> None:
        if self._processando or self.resultado is None:
            return
        resumo = self.resultado.resumo()
        if not self.resultado.auditoria_com_xml or resumo["revisar_xml"] or not resumo["corrigir"]:
            self._atualizar_estado_correcao()
            messagebox.showwarning(
                "FiscalPro",
                "A correção só é liberada depois da auditoria com XML, sem pendências, e com itens confirmados.",
                parent=self,
            )
            return
        nome = AuditoriaICMSSTPISCOFINSSaidasService.sugerir_nome_sped_final(self.arquivo_sped)
        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar SPED FINAL corrigido",
            defaultextension=".txt",
            initialfile=nome,
            filetypes=(("SPED TXT", "*.txt"), ("Todos", "*.*")),
        )
        if not destino:
            return
        confirmar = messagebox.askyesno(
            "FiscalPro — Confirmar correção",
            f"O FiscalPro vai gerar um único SPED FINAL e preservar o arquivo base selecionado.\n"
            f"Se esse arquivo base já tiver correções da Etapa 1 ou de outra etapa anterior, elas serão mantidas.\n\n"
            f"Itens confirmados: {resumo['corrigir']}\n"
            f"ICMS-ST a retirar das bases: {self._moeda(resumo['st_corrigir'])}\n"
            f"Redução estimada PIS: {self._moeda(resumo['reducao_pis'])}\n"
            f"Redução estimada COFINS: {self._moeda(resumo['reducao_cofins'])}\n\n"
            "Também serão retotalizados os C100 afetados, sincronizado o Bloco M pelo delta e executado o Pré-PVA comparativo. "
            "Se surgir erro novo, o arquivo não será gerado.\n\nContinuar?",
            parent=self,
        )
        if not confirmar:
            return

        self._processando = True
        self.btn_auditar.configure(state="disabled")
        self.btn_aplicar.configure(state="disabled")
        self.var_status.set("Preparando o SPED FINAL cumulativo...")
        sped = self.arquivo_sped
        xml = self.fonte_xml
        resultado = self.resultado

        def progresso(texto: str) -> None:
            self._fila.put(("progresso", texto))

        def executar() -> None:
            try:
                correcao = AuditoriaICMSSTPISCOFINSSaidasService.aplicar_correcoes(
                    sped, xml, resultado, destino, progresso=progresso
                )
                self._fila.put(("correcao_ok", correcao))
            except Exception as erro:
                self._fila.put(("correcao_erro", erro))

        threading.Thread(target=executar, daemon=True).start()
        self.after(100, self._verificar_fila)

    def _preencher(self) -> None:
        for iid in self.tabela.get_children():
            self.tabela.delete(iid)
        if self.resultado is None:
            self._registros_visiveis = []
            return
        filtro = self.var_filtro.get()
        busca = self.var_busca.get().strip().upper()
        visiveis = []
        revisar_status = {STATUS_XML_NAO_LOCALIZADO, STATUS_VINCULO_XML, STATUS_COMPOSICAO_BASE, STATUS_REVISAR_BASE}
        for item in self.resultado.registros:
            if filtro == "Correção identificada" and item.status != STATUS_CORRIGIR_ST:
                continue
            if filtro == "Sem valor ST no XML" and item.status != STATUS_SEM_ST_XML:
                continue
            if filtro == "Alíquota zero" and item.status != STATUS_ALIQUOTA_ZERO:
                continue
            if filtro == "OK — ST já fora" and item.status != STATUS_OK_ST_FORA:
                continue
            if filtro == "Revisar vínculo/base" and item.status not in revisar_status:
                continue
            if filtro == "Com base tributada (pré)" and item.status != STATUS_CANDIDATO_XML:
                continue
            if filtro == "NF-e itens (C170)" and item.registro != "C170":
                continue
            if filtro == "NFC-e analítico (C175)" and item.registro != "C175":
                continue
            if busca and busca not in " ".join((item.numero_documento, item.chave_nfe, item.participante, item.codigo_item, item.descricao, item.cfop)).upper():
                continue
            visiveis.append(item)
        self._registros_visiveis = visiveis
        for indice, item in enumerate(visiveis):
            pis_nova = self._numero(item.base_pis_sugerida) if item.status == STATUS_CORRIGIR_ST else "-"
            cof_nova = self._numero(item.base_cofins_sugerida) if item.status == STATUS_CORRIGIR_ST else "-"
            self.tabela.insert(
                "", "end", iid=str(indice), tags=(item.status,),
                values=(
                    item.status, item.modelo, item.numero_documento, item.registro, item.item or "-", item.codigo_item or "-",
                    item.descricao, item.cfop, item.cst_pis, self._numero(item.base_pis), self._numero(item.valor_st_xml), pis_nova,
                    item.cst_cofins, self._numero(item.base_cofins), cof_nova, item.linha_sped,
                ),
            )

    def _detalhes(self, _evento=None) -> None:
        selecionado = self.tabela.selection()
        if not selecionado:
            return
        item = self._registros_visiveis[int(selecionado[0])]
        texto = (
            f"Status: {item.status}\nAção: {item.acao}\n\n"
            f"Documento: modelo {item.modelo}  NF {item.numero_documento}\nChave: {item.chave_nfe or '-'}\n"
            f"Data: {item.data or '-'}  Participante: {item.participante or '-'}\n"
            f"Registro/Linha: {item.registro} / {item.linha_sped}\n"
            f"Item/Código: {item.item or '-'} / {item.codigo_item or '-'}\nDescrição: {item.descricao}\n\n"
            f"CFOP: {item.cfop}  CST ICMS: {item.cst_icms or '-'}\nValor operação SPED: {self._moeda(item.valor_operacao)}\n"
            f"Valor operação XML: {self._moeda(item.valor_operacao_xml)}\nICMS-ST retido no XML: {self._moeda(item.valor_st_xml)}\n"
            f"Vínculo XML: {item.confianca_vinculo or '-'}\n\n"
            f"PIS — CST {item.cst_pis} | Base SPED {self._moeda(item.base_pis)} | Base XML {self._moeda(item.base_pis_xml)} | "
            f"Alíquota {self._numero(item.aliquota_pis)}% | Valor atual {self._moeda(item.valor_pis)}\n"
            f"COFINS — CST {item.cst_cofins} | Base SPED {self._moeda(item.base_cofins)} | Base XML {self._moeda(item.base_cofins_xml)} | "
            f"Alíquota {self._numero(item.aliquota_cofins)}% | Valor atual {self._moeda(item.valor_cofins)}"
        )
        if item.status == STATUS_CORRIGIR_ST:
            texto += (
                f"\n\nSUGESTÃO (não aplicada):\n"
                f"Base PIS: {self._moeda(item.base_pis_sugerida)} | PIS: {self._moeda(item.valor_pis_sugerido)}\n"
                f"Base COFINS: {self._moeda(item.base_cofins_sugerida)} | COFINS: {self._moeda(item.valor_cofins_sugerido)}"
            )
        if item.origem_xml:
            texto += f"\n\nXML: {item.origem_xml}"
        messagebox.showinfo("Detalhes — Etapa 2", texto, parent=self)

    def _limpar(self) -> None:
        self.resultado = None
        self._registros_visiveis = []
        self.var_resumo.set("Registros 5405: 0  •  Corrigir: 0  •  Sem valor ST XML: 0  •  Alíquota zero: 0  •  Revisar: 0")
        self.var_status.set("Selecione o SPED e os XMLs de saída. Nenhum arquivo será alterado.")
        self._atualizar_estado_correcao()
        self._preencher()

    @staticmethod
    def _numero(valor: Decimal) -> str:
        return f"{valor:.2f}".replace(".", ",")

    @staticmethod
    def _moeda(valor: Decimal) -> str:
        bruto = f"{valor:,.2f}"
        return "R$ " + bruto.replace(",", "X").replace(".", ",").replace("X", ".")
