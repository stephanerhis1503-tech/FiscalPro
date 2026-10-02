"""Painel de Distribuição DF-e e Manifestação do Destinatário da NF-e."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Frame, Label, StringVar, Entry, Text, Toplevel
from tkinter import filedialog, messagebox, simpledialog, ttk

from src.nfe.assinatura import DESCRICOES_EVENTO
from src.nfe.cliente import ErroNFe, UF_CODIGOS
from src.nfe.servico import ServicoManifestacaoNFe

from .estilos import COR_BORDA, COR_CARD, COR_DESTAQUE, COR_FUNDO, COR_PRIMARIA, COR_TEXTO, COR_TEXTO_SUAVE, FONTE_NORMAL


EVENTOS_UI = (
    ("210210", "Ciência da Operação"),
    ("210200", "Confirmação da Operação"),
    ("210220", "Desconhecimento da Operação"),
    ("210240", "Operação não Realizada"),
)


class PainelManifestacaoNFe(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.servico = ServicoManifestacaoNFe()
        self.empresas: list[dict] = []
        self.registros: list[dict] = []
        self._ocupado = False
        self._bloqueio_after_id = None
        self._montar()
        self._carregar_empresas()

    @staticmethod
    def _cnpj_formatado(valor: str) -> str:
        d = "".join(ch for ch in str(valor or "") if ch.isdigit())
        if len(d) == 14:
            return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
        return d

    @staticmethod
    def _data_curta(valor: str) -> str:
        texto = str(valor or "").strip()
        if not texto:
            return ""
        try:
            return datetime.fromisoformat(texto.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            try:
                return datetime.fromisoformat(texto[:10]).strftime("%d/%m/%Y")
            except ValueError:
                return texto[:19]

    @staticmethod
    def _moeda(valor) -> str:
        try:
            numero = float(valor or 0)
        except (TypeError, ValueError):
            numero = 0.0
        return f"R$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _card(self, master):
        return Frame(master, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)

    def _montar(self):
        cab = self._card(self)
        cab.pack(fill=X, padx=10, pady=(7, 6))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        miolo = Frame(cab, bg=COR_CARD, padx=12, pady=8)
        miolo.pack(fill=X)
        Label(miolo, text="NF-e • Manifestação do Destinatário", bg=COR_CARD, fg=COR_TEXTO,
              font=("Segoe UI", 13, "bold")).pack(anchor="w")
        Label(
            miolo,
            text=("Consulte uma NF-e pela chave sem disputar a sequência de NSU com outro sistema e registre "
                  "Ciência, Confirmação, Desconhecimento ou Operação não Realizada. A senha do A1 não é gravada."),
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=FONTE_NORMAL, justify=LEFT,
        ).pack(anchor="w", pady=(2, 0))

        config = self._card(self)
        config.pack(fill=X, padx=10, pady=(0, 6))
        linha = Frame(config, bg=COR_CARD, padx=10, pady=8)
        linha.pack(fill=X)

        self.var_empresa = StringVar()
        self.var_uf = StringVar(value="MG")
        self.var_senha = StringVar()
        self.var_busca = StringVar()
        self.var_chave_consulta = StringVar()
        self.var_filtro_manifestacao = StringVar(value="TODAS")
        self.var_status = StringVar(value="Selecione uma empresa do Cadastro Central com certificado A1 configurado na aba NFS-e Nacional.")
        self.var_pasta_xml = StringVar(
            value=str(Path.home() / "Documents" / "FiscalPro" / "XML NF-e")
        )

        box_emp = Frame(linha, bg=COR_CARD)
        box_emp.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        Label(box_emp, text="Empresa / certificado A1", bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).pack(anchor="w")
        self.combo_empresa = ttk.Combobox(box_emp, textvariable=self.var_empresa, state="readonly")
        self.combo_empresa.pack(fill=X)
        self.combo_empresa.bind("<<ComboboxSelected>>", self._empresa_alterada)

        box_uf = Frame(linha, bg=COR_CARD)
        box_uf.grid(row=0, column=1, sticky="ew", padx=(0, 7))
        Label(box_uf, text="UF", bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).pack(anchor="w")
        self.combo_uf = ttk.Combobox(box_uf, textvariable=self.var_uf, values=tuple(UF_CODIGOS), state="readonly", width=6)
        self.combo_uf.pack(fill=X)

        box_senha = Frame(linha, bg=COR_CARD)
        box_senha.grid(row=0, column=2, sticky="ew", padx=(0, 7))
        Label(box_senha, text="Senha do A1 (não será salva)", bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).pack(anchor="w")
        Entry(box_senha, textvariable=self.var_senha, show="•", relief="solid", bd=1).pack(fill=X, ipady=3)

        acoes = Frame(linha, bg=COR_CARD)
        acoes.grid(row=0, column=3, sticky="sew")
        self.btn_sincronizar = ttk.Button(
            acoes, text="Sincronizar por NSU", command=self._sincronizar, style="Secondary.TButton"
        )
        self.btn_sincronizar.pack(fill=X)
        linha.columnconfigure(0, weight=5)
        linha.columnconfigure(1, weight=1)
        linha.columnconfigure(2, weight=3)
        linha.columnconfigure(3, weight=2)

        consulta_chave = Frame(config, bg=COR_CARD, padx=10)
        consulta_chave.pack(fill=X, pady=(0, 7))
        Label(
            consulta_chave,
            text="Chave da NF-e (44 dígitos) • consulta pontual, não avança o ultNSU",
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8),
        ).pack(anchor="w")
        linha_chave = Frame(consulta_chave, bg=COR_CARD)
        linha_chave.pack(fill=X, pady=(2, 0))
        self.ent_chave_consulta = ttk.Entry(linha_chave, textvariable=self.var_chave_consulta)
        self.ent_chave_consulta.pack(side=LEFT, fill=X, expand=True, padx=(0, 7))
        self.ent_chave_consulta.bind("<Return>", lambda _e: self._consultar_por_chave())
        self.btn_consultar_chave = ttk.Button(
            linha_chave, text="Consultar / baixar pela chave",
            command=self._consultar_por_chave, style="Accent.TButton",
        )
        self.btn_consultar_chave.pack(side=RIGHT)

        status = Frame(config, bg=COR_CARD, padx=10)
        status.pack(fill=X, pady=(0, 8))
        Label(status, textvariable=self.var_status, bg=COR_CARD, fg=COR_TEXTO_SUAVE,
              font=("Segoe UI", 8), justify=LEFT).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(status, text="Atualizar empresas", command=self._carregar_empresas,
                   style="Secondary.TButton").pack(side=RIGHT)
        self.btn_diagnostico = ttk.Button(
            status, text="Diagnóstico", command=self._mostrar_diagnostico,
            style="Secondary.TButton"
        )
        self.btn_diagnostico.pack(side=RIGHT, padx=(0, 6))

        filtros = self._card(self)
        filtros.pack(fill=X, padx=10, pady=(0, 6))
        fl = Frame(filtros, bg=COR_CARD, padx=10, pady=7)
        fl.pack(fill=X)
        Label(fl, text="Buscar", bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w")
        Label(fl, text="Manifestação", bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).grid(row=0, column=1, sticky="w")
        ent_busca = ttk.Entry(fl, textvariable=self.var_busca)
        ent_busca.grid(row=1, column=0, sticky="ew", padx=(0, 7))
        ent_busca.bind("<Return>", lambda _e: self._consultar_local())
        self.combo_filtro = ttk.Combobox(
            fl, textvariable=self.var_filtro_manifestacao,
            values=("TODAS", "SEM MANIFESTAÇÃO", "CIÊNCIA", "CONFIRMADA", "DESCONHECIDA", "NÃO REALIZADA"),
            state="readonly", width=20,
        )
        self.combo_filtro.grid(row=1, column=1, sticky="ew", padx=(0, 7))
        self.combo_filtro.bind("<<ComboboxSelected>>", lambda _e: self._consultar_local())
        ttk.Button(fl, text="Consultar", command=self._consultar_local, style="Primary.TButton").grid(row=1, column=2, sticky="ew")
        fl.columnconfigure(0, weight=4)
        fl.columnconfigure(1, weight=2)

        # Ações compactas: ficam visíveis sem consumir a área da grade/XML.
        acoes_card = self._card(self)
        acoes_card.pack(fill=X, padx=10, pady=(0, 6))
        ac = Frame(acoes_card, bg=COR_CARD, padx=8, pady=5)
        ac.pack(fill=X)

        self.var_detalhe = StringVar(value="Selecione uma NF-e para manifestar ou baixar XML.")
        Label(
            ac, textvariable=self.var_detalhe, bg=COR_CARD, fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8), justify=LEFT,
        ).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 4))

        self.btn_ciencia = ttk.Button(ac, text="Ciência", command=lambda: self._manifestar("210210"), style="Secondary.TButton")
        self.btn_confirmar = ttk.Button(ac, text="Confirmar Operação", command=lambda: self._manifestar("210200"), style="Primary.TButton")
        self.btn_desconhecer = ttk.Button(ac, text="Desconhecer", command=lambda: self._manifestar("210220"), style="Secondary.TButton")
        self.btn_nao_realizada = ttk.Button(ac, text="Operação não Realizada", command=lambda: self._manifestar("210240"), style="Secondary.TButton")
        self.btn_ciencia.grid(row=1, column=0, sticky="ew", padx=(0, 3))
        self.btn_confirmar.grid(row=1, column=1, sticky="ew", padx=3)
        self.btn_desconhecer.grid(row=1, column=2, sticky="ew", padx=3)
        self.btn_nao_realizada.grid(row=1, column=3, sticky="ew", padx=(3, 0))

        self.ent_pasta_xml = ttk.Entry(ac, textvariable=self.var_pasta_xml, state="readonly")
        self.ent_pasta_xml.grid(row=2, column=0, sticky="ew", padx=(0, 3), pady=(5, 0))
        self.btn_pasta_xml = ttk.Button(ac, text="Escolher pasta", command=self._escolher_pasta_xml, style="Secondary.TButton")
        self.btn_pasta_xml.grid(row=2, column=1, sticky="ew", padx=3, pady=(5, 0))
        self.btn_xml = ttk.Button(ac, text="Baixar XML selecionado(s)", command=self._salvar_xml, style="Primary.TButton")
        self.btn_xml.grid(row=2, column=2, sticky="ew", padx=3, pady=(5, 0))
        self.btn_xml_todos = ttk.Button(ac, text="Baixar todos completos", command=self._salvar_todos_xml, style="Secondary.TButton")
        self.btn_xml_todos.grid(row=2, column=3, sticky="ew", padx=(3, 0), pady=(5, 0))
        ac.columnconfigure(0, weight=3)
        ac.columnconfigure(1, weight=1)
        ac.columnconfigure(2, weight=2)
        ac.columnconfigure(3, weight=2)

        # Área principal: prioridade visual para a grade de NF-e.
        area_dividida = ttk.Frame(self, style="Page.TFrame")
        area_dividida.pack(fill=BOTH, expand=True, padx=10, pady=(0, 6))
        area_dividida.columnconfigure(0, weight=1)
        area_dividida.rowconfigure(0, weight=5, minsize=220)
        area_dividida.rowconfigure(1, weight=2, minsize=90)

        card_tabela = self._card(area_dividida)
        card_tabela.grid(row=0, column=0, sticky="nsew", pady=(0, 4))
        corpo = ttk.Frame(card_tabela, style="Page.TFrame")
        corpo.pack(fill=BOTH, expand=True, padx=1, pady=1)
        colunas = ("emissao", "emitente", "cnpj", "valor", "situacao", "manifestacao", "prazo", "xml")
        self.tabela = ttk.Treeview(corpo, columns=colunas, show="headings", selectmode="extended", height=12)
        cabecalhos = {
            "emissao": "Emissão", "emitente": "Emitente", "cnpj": "CNPJ", "valor": "Valor NF-e",
            "situacao": "Situação", "manifestacao": "Manifestação", "prazo": "Prazo final", "xml": "XML",
        }
        larguras = {"emissao": 120, "emitente": 245, "cnpj": 125, "valor": 105, "situacao": 85,
                    "manifestacao": 135, "prazo": 95, "xml": 75}
        for col in colunas:
            self.tabela.heading(col, text=cabecalhos[col])
            self.tabela.column(col, width=larguras[col], minwidth=60, anchor="w" if col in {"emitente", "manifestacao"} else "center")
        sy = ttk.Scrollbar(corpo, orient="vertical", command=self.tabela.yview)
        sx = ttk.Scrollbar(corpo, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        corpo.rowconfigure(0, weight=1)
        corpo.columnconfigure(0, weight=1)
        self.tabela.bind("<<TreeviewSelect>>", self._selecionar_nota)

        card_xml = self._card(area_dividida)
        card_xml.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        xml_prev = Frame(card_xml, bg=COR_CARD, padx=8, pady=5)
        xml_prev.pack(fill=BOTH, expand=True)
        topo_xml = Frame(xml_prev, bg=COR_CARD)
        topo_xml.pack(fill=X, pady=(0, 4))
        Label(
            topo_xml, text="XML da NF-e selecionada", bg=COR_CARD, fg=COR_TEXTO,
            font=("Segoe UI", 9, "bold")
        ).pack(side=LEFT)
        self.var_xml_preview_info = StringVar(
            value="Selecione uma NF-e com XML completo para visualizar abaixo."
        )
        Label(
            topo_xml, textvariable=self.var_xml_preview_info, bg=COR_CARD,
            fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8), justify=LEFT
        ).pack(side=LEFT, fill=X, expand=True, padx=(12, 0))

        area_xml = Frame(xml_prev, bg=COR_CARD)
        area_xml.pack(fill=BOTH, expand=True)
        self.txt_xml_preview = Text(
            area_xml, wrap="none", relief="solid", bd=1, height=4, font=("Consolas", 8)
        )
        sy_xml = ttk.Scrollbar(area_xml, orient="vertical", command=self.txt_xml_preview.yview)
        sx_xml = ttk.Scrollbar(area_xml, orient="horizontal", command=self.txt_xml_preview.xview)
        self.txt_xml_preview.configure(yscrollcommand=sy_xml.set, xscrollcommand=sx_xml.set)
        self.txt_xml_preview.grid(row=0, column=0, sticky="nsew")
        sy_xml.grid(row=0, column=1, sticky="ns")
        sx_xml.grid(row=1, column=0, sticky="ew")
        area_xml.rowconfigure(0, weight=1)
        area_xml.columnconfigure(0, weight=1)
        self.txt_xml_preview.insert("1.0", "Selecione uma NF-e para visualizar o XML aqui.")
        self.txt_xml_preview.configure(state="disabled")

    def _empresa_selecionada(self) -> dict | None:
        idx = self.combo_empresa.current()
        if 0 <= idx < len(self.empresas):
            return self.empresas[idx]
        return None

    def _registro_selecionado(self) -> dict | None:
        selecao = self.tabela.selection()
        if not selecao:
            return None
        try:
            return self.registros[int(selecao[0])]
        except (ValueError, IndexError):
            return None

    def _registros_selecionados(self) -> list[dict]:
        registros: list[dict] = []
        for iid in self.tabela.selection():
            try:
                registros.append(self.registros[int(iid)])
            except (ValueError, IndexError):
                continue
        return registros

    def _carregar_empresas(self):
        atual_cnpj = (self._empresa_selecionada() or {}).get("cnpj", "")
        self.empresas = self.servico.listar_empresas()
        valores = [f"{e.get('nome','')} • {self._cnpj_formatado(e.get('cnpj',''))} • {e.get('ambiente','PRODUCAO')}" for e in self.empresas]
        self.combo_empresa.configure(values=valores)
        if not self.empresas:
            self.var_empresa.set("")
            self.var_status.set("Nenhuma empresa com CNPJ disponível. Complete o Cadastro Central e configure o certificado A1 na aba NFS-e Nacional.")
            self._limpar_tabela()
            return
        indice = 0
        if atual_cnpj:
            for i, empresa in enumerate(self.empresas):
                if empresa.get("cnpj") == atual_cnpj:
                    indice = i
                    break
        self.combo_empresa.current(indice)
        self._empresa_alterada()

    def _empresa_alterada(self, _evt=None):
        empresa = self._empresa_selecionada()
        if not empresa:
            return
        config = self.servico.obter_config(empresa.get("cnpj", ""), empresa.get("ambiente", "PRODUCAO"))
        self.var_uf.set(config.get("uf_autor") or "MG")
        cert = Path(empresa.get("certificado_path") or "")
        cert_txt = cert.name if cert.name else "não informado"
        cstat = str(config.get("ultimo_cstat") or "").strip()
        retorno = f" • Último retorno: {cstat}" if cstat else ""
        self.var_status.set(
            f"Ambiente: {empresa.get('ambiente','PRODUCAO')} • Certificado: {cert_txt} • "
            f"NSU: {int(config.get('ultimo_nsu') or 0):015d} / {int(config.get('max_nsu') or 0):015d}"
            f"{retorno}"
        )
        self._consultar_local()
        self._atualizar_bloqueio_ui()

    def _definir_preview_xml(self, conteudo: str, info: str = ""):
        if hasattr(self, "txt_xml_preview"):
            self.txt_xml_preview.configure(state="normal")
            self.txt_xml_preview.delete("1.0", END)
            self.txt_xml_preview.insert("1.0", conteudo or "")
            self.txt_xml_preview.configure(state="disabled")
        if hasattr(self, "var_xml_preview_info"):
            self.var_xml_preview_info.set(info or "")

    def _atualizar_preview_xml(self, reg: dict | None):
        if not reg:
            self._definir_preview_xml(
                "Selecione uma NF-e para visualizar o XML aqui.",
                "Selecione uma NF-e com XML completo para visualizar o conteúdo abaixo.",
            )
            return
        if not reg.get("tem_xml_completo"):
            self._definir_preview_xml(
                "XML completo ainda não está disponível para esta NF-e.\n\n"
                "Situação comum: a SEFAZ disponibilizou apenas o resumo do DF-e.\n"
                "Após a manifestação, consulte novamente esta mesma chave para tentar obter o XML completo.",
                f"NF-e {str(reg.get('chave') or '')} disponível apenas como resumo.",
            )
            return
        empresa = self._empresa_selecionada() or {}
        empresa_id = int(empresa.get("id") or 0)
        chave = str(reg.get("chave") or "")
        xml = self.servico.obter_xml_completo(empresa_id, chave) if empresa_id and chave else ""
        emitente = str(reg.get("emitente") or "")
        if not xml:
            self._definir_preview_xml(
                "O FiscalPro não encontrou o XML completo salvo localmente para esta NF-e.",
                f"NF-e {chave} sem XML local carregado.",
            )
            return
        self._definir_preview_xml(
            xml,
            f"Visualizando XML local de {emitente or 'NF-e selecionada'} • Chave: {chave}",
        )

    def _limpar_tabela(self):
        self.registros = []
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        self.var_detalhe.set("Selecione uma NF-e para manifestar ou baixar XML.")
        self._atualizar_preview_xml(None)

    def _consultar_local(self):
        empresa = self._empresa_selecionada()
        self._limpar_tabela()
        if not empresa:
            return
        self.registros = self.servico.listar_notas(
            empresa["id"], self.var_busca.get(), self.var_filtro_manifestacao.get()
        )
        for i, reg in enumerate(self.registros):
            situacao = str(reg.get("situacao_nfe") or "")
            situacao_txt = {"1": "Autorizada", "2": "Denegada", "3": "Cancelada", "100": "Autorizada", "101": "Cancelada"}.get(situacao, situacao or "—")
            self.tabela.insert(
                "", END, iid=str(i), values=(
                    self._data_curta(reg.get("data_emissao")),
                    reg.get("emitente_nome") or "—",
                    self._cnpj_formatado(reg.get("emitente_doc")),
                    self._moeda(reg.get("valor_nf")),
                    situacao_txt,
                    reg.get("manifestacao") or "SEM MANIFESTAÇÃO",
                    self._data_curta(reg.get("prazo_final"))[:10],
                    "Completo" if reg.get("tem_xml_completo") else "Resumo",
                ),
            )
        self.var_status.set(self.var_status.get().split(" • Notas:")[0] + f" • Notas: {len(self.registros)}")

    def _selecionar_nota(self, _evt=None):
        selecionados = self._registros_selecionados()
        if not selecionados:
            self.var_detalhe.set("Selecione uma NF-e para manifestar ou baixar XML.")
            self._atualizar_preview_xml(None)
            return
        if len(selecionados) > 1:
            completos = sum(1 for reg in selecionados if reg.get("tem_xml_completo"))
            self.var_detalhe.set(
                f"{len(selecionados)} NF-e selecionadas • {completos} com XML completo disponível para download local."
            )
            self._definir_preview_xml(
                "Visualização de XML disponível somente quando uma única NF-e estiver selecionada.",
                f"{len(selecionados)} NF-e selecionadas.",
            )
            return
        reg = selecionados[0]
        chave = str(reg.get("chave") or "")
        protocolo = str(reg.get("protocolo_manifestacao") or "")
        texto = f"Chave: {chave} • Manifestação atual: {reg.get('manifestacao') or 'SEM MANIFESTAÇÃO'}"
        if protocolo:
            texto += f" • Protocolo: {protocolo}"
        self.var_detalhe.set(texto)
        self._atualizar_preview_xml(reg)

    def _cancelar_timer_bloqueio(self):
        if self._bloqueio_after_id is not None:
            try:
                self.after_cancel(self._bloqueio_after_id)
            except Exception:
                pass
            self._bloqueio_after_id = None

    @staticmethod
    def _tempo_restante_texto(segundos: int) -> str:
        segundos = max(0, int(segundos or 0))
        horas, resto = divmod(segundos, 3600)
        minutos, seg = divmod(resto, 60)
        if horas:
            return f"{horas}h {minutos:02d}min"
        if minutos:
            return f"{minutos}min {seg:02d}s"
        return f"{seg}s"

    def _atualizar_bloqueio_ui(self, agendar: bool = True):
        if agendar:
            self._cancelar_timer_bloqueio()
        empresa = self._empresa_selecionada()
        if not empresa:
            return
        status = self.servico.status_sincronizacao(empresa["id"])
        if status.get("bloqueado"):
            cstat = str(status.get("ultimo_cstat") or "")
            bloqueio_656 = cstat.startswith("656")
            try:
                self.btn_sincronizar.configure(state="disabled")
                self.btn_consultar_chave.configure(
                    state="disabled" if bloqueio_656 else ("disabled" if self._ocupado else "normal")
                )
            except Exception:
                pass
            detalhe = f" • cStat {cstat}" if cstat else ""
            complemento_chave = (
                " • Por segurança, consulta por chave também bloqueada"
                if bloqueio_656
                else " • Consulta por chave disponível"
            )
            self.var_status.set(
                f"Consulta DF-e protegida até {status.get('bloqueado_ate_formatado')} "
                f"• faltam {self._tempo_restante_texto(status.get('segundos_restantes', 0))}"
                f"{detalhe} • NSU {int(status.get('ultimo_nsu') or 0):015d} / {int(status.get('max_nsu') or 0):015d}"
                f" • Notas: {len(self.registros)}{complemento_chave}"
            )
            if agendar:
                self._bloqueio_after_id = self.after(15000, self._atualizar_bloqueio_ui)
            return

        if not self._ocupado:
            try:
                self.btn_sincronizar.configure(state="normal")
                self.btn_consultar_chave.configure(state="normal")
            except Exception:
                pass
        if str(self.var_status.get()).startswith("Consulta DF-e protegida"):
            self.var_status.set(
                f"Consulta DF-e liberada • NSU {int(status.get('ultimo_nsu') or 0):015d} / "
                f"{int(status.get('max_nsu') or 0):015d} • Notas: {len(self.registros)}"
            )

    def _definir_ocupado(self, ocupado: bool, mensagem: str = ""):
        self._ocupado = ocupado
        estado = "disabled" if ocupado else "normal"
        for botao in (
            self.btn_sincronizar, self.btn_diagnostico, self.btn_ciencia, self.btn_confirmar,
            self.btn_desconhecer, self.btn_nao_realizada, self.btn_xml, self.btn_xml_todos,
            self.btn_pasta_xml, self.btn_consultar_chave,
        ):
            try:
                botao.configure(state=estado)
            except Exception:
                pass
        if not ocupado:
            self._atualizar_bloqueio_ui()
        if mensagem:
            self.var_status.set(mensagem)

    def _executar_thread(self, funcao, ao_concluir):
        if self._ocupado:
            return
        self._definir_ocupado(True)

        def trabalho():
            try:
                resultado = funcao()
            except Exception as exc:  # erro é exibido na thread da UI
                self.after(0, lambda e=exc: self._erro(e))
                return
            self.after(0, lambda r=resultado: ao_concluir(r))

        threading.Thread(target=trabalho, daemon=True).start()

    def _erro(self, exc: Exception):
        self._definir_ocupado(False)
        mensagem = str(exc) or exc.__class__.__name__
        self.var_status.set(mensagem)
        messagebox.showerror("NF-e / Manifestação", mensagem, parent=self)

    def _mostrar_diagnostico(self):
        empresa = self._empresa_selecionada()
        if not empresa:
            messagebox.showwarning(
                "NF-e / Manifestação",
                "Selecione uma empresa para gerar o diagnóstico.",
                parent=self,
            )
            return
        try:
            dados = self.servico.diagnostico(int(empresa["id"]))
        except Exception as exc:
            messagebox.showerror(
                "Diagnóstico da Manifestação",
                str(exc) or exc.__class__.__name__,
                parent=self,
            )
            return

        texto = str(dados.get("texto") or "")
        janela = Toplevel(self)
        janela.title("Diagnóstico • NF-e / Manifestação")
        janela.geometry("760x520")
        janela.minsize(650, 420)
        janela.transient(self.winfo_toplevel())

        corpo = ttk.Frame(janela, padding=12)
        corpo.pack(fill=BOTH, expand=True)
        ttk.Label(
            corpo,
            text="Diagnóstico da Distribuição DF-e",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            corpo,
            text="Leitura local do FiscalPro — esta tela não consome uma nova consulta à SEFAZ.",
        ).pack(anchor="w", pady=(2, 8))

        area = Frame(corpo)
        area.pack(fill=BOTH, expand=True)
        txt = Text(area, wrap="word", font=("Consolas", 9), relief="solid", bd=1)
        barra = ttk.Scrollbar(area, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=barra.set)
        txt.pack(side=LEFT, fill=BOTH, expand=True)
        barra.pack(side=RIGHT, fill=Y)
        txt.insert("1.0", texto)
        txt.configure(state="disabled")

        botoes = ttk.Frame(corpo)
        botoes.pack(fill=X, pady=(10, 0))

        def copiar():
            janela.clipboard_clear()
            janela.clipboard_append(texto)
            janela.update()
            self.var_status.set("Diagnóstico copiado para a área de transferência.")

        ttk.Button(botoes, text="Copiar diagnóstico", command=copiar).pack(side=LEFT)
        ttk.Button(botoes, text="Fechar", command=janela.destroy).pack(side=RIGHT)

    def _consultar_por_chave(self):
        empresa = self._empresa_selecionada()
        if not empresa:
            messagebox.showwarning("NF-e / Manifestação", "Selecione uma empresa.", parent=self)
            return
        senha = self.var_senha.get()
        if not senha:
            messagebox.showwarning("NF-e / Manifestação", "Digite a senha do certificado A1.", parent=self)
            return
        chave = "".join(ch for ch in self.var_chave_consulta.get() if ch.isdigit())
        if len(chave) != 44:
            messagebox.showwarning(
                "Consulta por chave",
                "Informe uma chave de NF-e válida com 44 dígitos.",
                parent=self,
            )
            return
        self.var_chave_consulta.set(chave)
        uf = self.var_uf.get()
        self.servico.salvar_uf(empresa["cnpj"], empresa.get("ambiente", "PRODUCAO"), uf)
        self.var_status.set(f"Consultando a chave {chave} sem alterar o ultNSU…")
        self._executar_thread(
            lambda: self.servico.consultar_por_chave(empresa["id"], senha, uf, chave),
            self._consulta_chave_concluida,
        )

    def _consulta_chave_concluida(self, resultado: dict):
        self._definir_ocupado(False)
        chave = str(resultado.get("chave") or "")
        self._consultar_local()

        registro = next((r for r in self.registros if str(r.get("chave") or "") == chave), None)
        if registro:
            try:
                indice = self.registros.index(registro)
                self.tabela.selection_set(str(indice))
                self.tabela.focus(str(indice))
                self.tabela.see(str(indice))
                self._selecionar_nota()
            except Exception:
                pass

        cstat = str(resultado.get("cstat") or "")
        motivo = str(resultado.get("motivo") or "")
        if registro and registro.get("tem_xml_completo"):
            empresa = self._empresa_selecionada() or {}
            xml = self.servico.obter_xml_completo(int(empresa.get("id") or 0), chave)
            if xml:
                try:
                    destino = self._destino_xml_nota(empresa, registro)
                    destino.write_text(xml, encoding="utf-8")
                    self.var_status.set(
                        f"Consulta por chave concluída • cStat {cstat} • XML completo salvo em {destino}"
                    )
                    messagebox.showinfo(
                        "NF-e localizada",
                        f"NF-e localizada e XML completo salvo.\n\n{destino}",
                        parent=self,
                    )
                    return
                except OSError as exc:
                    self.var_status.set(f"NF-e localizada, mas houve erro ao salvar o XML: {exc}")

        if registro:
            self.var_status.set(
                f"Consulta por chave concluída • cStat {cstat} • NF-e disponível como resumo"
            )
            messagebox.showinfo(
                "NF-e localizada",
                "A NF-e foi localizada, mas a SEFAZ ainda disponibilizou somente o resumo.\n\n"
                "Você pode fazer a manifestação e depois consultar a mesma chave novamente para tentar obter o XML completo.",
                parent=self,
            )
            return

        detalhe = "\n".join(str(x) for x in (resultado.get("detalhes") or []) if str(x).strip())
        self.var_status.set(f"Consulta por chave • cStat {cstat}: {motivo}")
        messagebox.showinfo(
            "Consulta por chave",
            f"Retorno: cStat {cstat or '—'}\n{motivo or 'Sem motivo informado.'}"
            + (f"\n\n{detalhe}" if detalhe else ""),
            parent=self,
        )

    def _sincronizar(self):
        empresa = self._empresa_selecionada()
        if not empresa:
            messagebox.showwarning("NF-e / Manifestação", "Selecione uma empresa.", parent=self)
            return
        if not messagebox.askyesno(
            "Sincronização por NSU",
            "Este modo avança a sequência de NSU e deve ser usado somente quando nenhum outro sistema "
            "(como Digisat) consulta a Distribuição DF-e deste CNPJ.\n\n"
            "Se o Digisat consulta este CNPJ, use 'Consultar / baixar pela chave'.\n\n"
            "Deseja continuar com a sincronização por NSU?",
            parent=self,
        ):
            return
        status = self.servico.status_sincronizacao(empresa["id"])
        if status.get("bloqueado"):
            self._atualizar_bloqueio_ui()
            messagebox.showinfo(
                "Consulta protegida",
                "Para evitar novo cStat 656, este CNPJ só poderá consultar a Distribuição DF-e novamente após "
                f"{status.get('bloqueado_ate_formatado')}.\n\n"
                "O botão será liberado automaticamente depois desse horário.",
                parent=self,
            )
            return
        senha = self.var_senha.get()
        uf = self.var_uf.get()
        if not senha:
            messagebox.showwarning("NF-e / Manifestação", "Digite a senha do certificado A1.", parent=self)
            return

        def progresso(texto):
            self.after(0, lambda t=texto: self.var_status.set(t))

        self.servico.salvar_uf(empresa["cnpj"], empresa.get("ambiente", "PRODUCAO"), uf)
        self._executar_thread(
            lambda: self.servico.sincronizar(empresa["id"], senha, uf, progresso=progresso),
            self._sincronizacao_concluida,
        )

    def _sincronizacao_concluida(self, resultado: dict):
        self._definir_ocupado(False)
        self._consultar_local()
        proxima = str(resultado.get("bloqueado_ate_formatado") or "")
        complemento = f" • Próxima consulta após {proxima}" if proxima else ""
        self.var_status.set(
            f"Sincronização concluída • {resultado.get('processados', 0)} documento(s) processado(s) • "
            f"NSU {int(resultado.get('ultimo_nsu') or 0):015d} / {int(resultado.get('max_nsu') or 0):015d}"
            f"{complemento}"
        )
        self._atualizar_bloqueio_ui()

    def _manifestar(self, tp_evento: str):
        empresa = self._empresa_selecionada()
        selecionados = self._registros_selecionados()
        if not empresa or not selecionados:
            messagebox.showwarning("NF-e / Manifestação", "Selecione uma NF-e.", parent=self)
            return
        if len(selecionados) != 1:
            messagebox.showwarning(
                "NF-e / Manifestação",
                "Para manifestar, selecione somente uma NF-e por vez. A seleção múltipla é usada para baixar XMLs.",
                parent=self,
            )
            return
        reg = selecionados[0]
        senha = self.var_senha.get()
        if not senha:
            messagebox.showwarning("NF-e / Manifestação", "Digite a senha do certificado A1.", parent=self)
            return

        justificativa = ""
        if tp_evento == "210240":
            justificativa = simpledialog.askstring(
                "Operação não Realizada",
                "Informe a justificativa (15 a 255 caracteres):",
                parent=self,
            ) or ""
            if not justificativa:
                return
            if not 15 <= len(justificativa.strip()) <= 255:
                messagebox.showwarning("NF-e / Manifestação", "A justificativa deve ter entre 15 e 255 caracteres.", parent=self)
                return

        descricao = DESCRICOES_EVENTO[tp_evento]
        aviso = (
            f"Você vai registrar '{descricao}' para a NF-e abaixo:\n\n"
            f"Emitente: {reg.get('emitente_nome') or '—'}\n"
            f"Chave: {reg.get('chave')}\n\n"
            "O evento será transmitido ao Ambiente Nacional da NF-e. Deseja continuar?"
        )
        if not messagebox.askyesno("Confirmar manifestação", aviso, parent=self):
            return

        self._executar_thread(
            lambda: self.servico.manifestar(
                empresa["id"], senha, reg["chave"], tp_evento, justificativa.strip()
            ),
            lambda retorno: self._manifestacao_concluida(descricao, retorno),
        )

    def _manifestacao_concluida(self, descricao: str, retorno: dict):
        self._definir_ocupado(False)
        self._consultar_local()
        cstat = str(retorno.get("cstat") or "")
        motivo = str(retorno.get("motivo") or "")
        protocolo = str(retorno.get("protocolo") or "")
        if cstat in {"135", "136"}:
            self.var_status.set(f"{descricao} registrada • cStat {cstat} • Protocolo {protocolo or '—'}")
            messagebox.showinfo(
                "Manifestação registrada",
                f"Evento: {descricao}\ncStat: {cstat}\n{motivo}\nProtocolo: {protocolo or '—'}",
                parent=self,
            )
        else:
            self.var_status.set(f"Manifestação retornou cStat {cstat}: {motivo}")
            messagebox.showwarning(
                "Retorno da manifestação",
                f"O Ambiente Nacional retornou cStat {cstat or '—'}:\n{motivo or 'Sem motivo informado.'}",
                parent=self,
            )

    def _escolher_pasta_xml(self):
        atual = Path(self.var_pasta_xml.get() or (Path.home() / "Documents"))
        inicial = atual if atual.exists() else Path.home() / "Documents"
        destino = filedialog.askdirectory(
            parent=self,
            title="Escolher pasta para os XMLs da NF-e",
            initialdir=str(inicial),
        )
        if destino:
            self.var_pasta_xml.set(destino)
            self.var_status.set(f"Pasta dos XMLs: {destino}")

    @staticmethod
    def _nome_seguro(valor: object, limite: int = 60) -> str:
        texto = " ".join(str(valor or "").strip().split())
        permitidos = []
        for ch in texto:
            if ch.isalnum() or ch in {" ", "-", "_", "."}:
                permitidos.append(ch)
            else:
                permitidos.append("_")
        nome = "".join(permitidos).strip(" ._-")
        while "__" in nome:
            nome = nome.replace("__", "_")
        return (nome or "SEM_NOME")[:limite].rstrip(" .")

    @staticmethod
    def _ano_mes_nota(reg: dict) -> tuple[str, str]:
        texto = str(reg.get("data_emissao") or "").strip()
        if texto:
            try:
                data = datetime.fromisoformat(texto.replace("Z", "+00:00"))
                return f"{data.year:04d}", f"{data.month:02d}"
            except ValueError:
                try:
                    data = datetime.fromisoformat(texto[:10])
                    return f"{data.year:04d}", f"{data.month:02d}"
                except ValueError:
                    pass
        agora = datetime.now()
        return f"{agora.year:04d}", f"{agora.month:02d}"

    def _destino_xml_nota(self, empresa: dict, reg: dict) -> Path:
        base = Path(self.var_pasta_xml.get().strip() or (Path.home() / "Documents" / "FiscalPro" / "XML NF-e"))
        empresa_nome = self._nome_seguro(empresa.get("nome") or empresa.get("cnpj") or "EMPRESA", 70)
        ano, mes = self._ano_mes_nota(reg)
        pasta = base / empresa_nome / ano / mes
        pasta.mkdir(parents=True, exist_ok=True)

        chave = "".join(ch for ch in str(reg.get("chave") or "") if ch.isdigit()) or self._nome_seguro(reg.get("chave"), 50)
        emitente = self._nome_seguro(reg.get("emitente_nome") or "EMITENTE", 40)
        return pasta / f"NFe_{chave}_{emitente}.xml"

    def _exportar_xmls_locais(self, registros: list[dict]):
        empresa = self._empresa_selecionada()
        if not empresa:
            messagebox.showwarning("NF-e / Manifestação", "Selecione uma empresa.", parent=self)
            return
        if not registros:
            messagebox.showwarning("NF-e / Manifestação", "Selecione pelo menos uma NF-e.", parent=self)
            return

        salvos: list[Path] = []
        indisponiveis: list[dict] = []
        erros: list[str] = []

        for reg in registros:
            if not reg.get("tem_xml_completo"):
                indisponiveis.append(reg)
                continue
            chave = str(reg.get("chave") or "")
            xml = self.servico.obter_xml_completo(empresa["id"], chave)
            if not xml:
                indisponiveis.append(reg)
                continue
            try:
                destino = self._destino_xml_nota(empresa, reg)
                destino.write_text(xml, encoding="utf-8")
                salvos.append(destino)
            except OSError as exc:
                erros.append(f"{chave}: {exc}")

        resumo = [f"XMLs salvos: {len(salvos)}"]
        if indisponiveis:
            resumo.append(f"Somente resumo / indisponíveis: {len(indisponiveis)}")
        if erros:
            resumo.append(f"Erros ao gravar: {len(erros)}")

        base = self.var_pasta_xml.get().strip()
        self.var_status.set(" • ".join(resumo) + (f" • Pasta: {base}" if salvos else ""))

        mensagem = "\n".join(resumo)
        if salvos:
            mensagem += f"\n\nPasta base:\n{base}\n\nOs arquivos foram organizados por Empresa / Ano / Mês."
        if indisponiveis:
            mensagem += (
                "\n\nAs NF-e marcadas como 'Resumo' não foram consultadas novamente. "
                "Use 'Consultar / baixar pela chave' para consultar pontualmente sem avançar o ultNSU."
            )
        if erros:
            mensagem += "\n\nPrimeiro erro: " + erros[0]

        if salvos:
            messagebox.showinfo("Download de XML concluído", mensagem, parent=self)
        else:
            messagebox.showinfo("Nenhum XML completo salvo", mensagem, parent=self)

    def _salvar_xml(self):
        selecionados = self._registros_selecionados()
        if not selecionados:
            messagebox.showwarning(
                "NF-e / Manifestação",
                "Selecione uma ou mais NF-e na tabela. Use Ctrl+clique para selecionar várias.",
                parent=self,
            )
            return
        self._exportar_xmls_locais(selecionados)

    def _salvar_todos_xml(self):
        if not self.registros:
            messagebox.showinfo("NF-e / Manifestação", "Não há NF-e exibidas para baixar.", parent=self)
            return
        completos = [reg for reg in self.registros if reg.get("tem_xml_completo")]
        if not completos:
            messagebox.showinfo(
                "NF-e / Manifestação",
                "Nenhuma das NF-e exibidas possui XML completo armazenado no FiscalPro neste momento.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Baixar XMLs completos",
            f"Salvar {len(completos)} XML(s) completo(s) que já estão armazenados no FiscalPro?\n\n"
            "Esta ação é local e não fará nova consulta à SEFAZ.",
            parent=self,
        ):
            return
        self._exportar_xmls_locais(completos)

