"""RTC 2: consulta controlada e conciliacao da CBS oficial vs. XML local.

A interface nao armazena token, nao apropria credito e nao confirma apuracao.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tkinter import BOTH, END, LEFT, X, StringVar, ttk, Entry
from tkinter import filedialog, messagebox
import threading

from src.services.cbs_apuracao_oficial_service import ServicoCBSOficial
from src.services.cbs_apuracao_api_client import ClienteCBSReceita
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.ui.painel_apuracao_assistida_rtc import PainelApuracaoAssistidaRTC


class PainelCBSOficial(ttk.Frame):
    TIPOS = {"Débitos": "debitos", "Créditos": "creditos"}

    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.servico = ServicoCBSOficial()
        self.empresas: dict[str, dict] = {}
        self.var_empresa = StringVar()
        self.var_tipo = StringVar(value="Débitos")
        self.var_mes = StringVar(value=PainelApuracaoAssistidaRTC.MESES[date.today().month - 1])
        self.var_ano = StringVar(value=str(date.today().year))
        self.var_token = StringVar()
        self.var_tiquete = StringVar()
        self.var_status = StringVar(value="Sem consulta oficial importada. Valores nao sao apuracao definitiva.")
        self.var_aviso = StringVar(value="Retornos oficiais sao incrementais; ausencia de nota nao prova ausencia na Receita.")
        self._em_rede = False
        self._montar()
        self._carregar_empresas()

    def _montar(self):
        filtros = ttk.LabelFrame(self, text="CBS oficial | Integracao em modo consulta", padding=8)
        filtros.pack(fill=X, padx=9, pady=(8, 5))
        ttk.Label(
            filtros, text=(
                "Importe JSON recebido da Receita ou consulte com token OAuth2 temporario. "
                "Nao transmite apuracao, nao paga impostos e nao credita automaticamente."
            ), wraplength=1060,
        ).pack(anchor="w")
        linha = ttk.Frame(filtros)
        linha.pack(fill=X, pady=(8, 0))
        ttk.Label(linha, text="Empresa").pack(side=LEFT, padx=(0, 5))
        self.combo_empresa = ttk.Combobox(
            linha, textvariable=self.var_empresa, state="readonly", width=45
        )
        self.combo_empresa.pack(side=LEFT, padx=(0, 7))
        ttk.Label(linha, text="Mês").pack(side=LEFT)
        ttk.Combobox(
            linha, textvariable=self.var_mes, state="readonly",
            values=PainelApuracaoAssistidaRTC.MESES, width=12,
        ).pack(side=LEFT, padx=(4, 6))
        ttk.Label(linha, text="Ano").pack(side=LEFT)
        ttk.Combobox(
            linha, textvariable=self.var_ano, state="readonly",
            values=tuple(str(n) for n in range(date.today().year + 5, 2019, -1)),
            width=6,
        ).pack(side=LEFT, padx=(4, 7))
        ttk.Label(linha, text="Retorno").pack(side=LEFT)
        ttk.Combobox(
            linha, textvariable=self.var_tipo, state="readonly",
            values=tuple(self.TIPOS), width=10,
        ).pack(side=LEFT, padx=(4, 6))
        ttk.Button(linha, text="Atualizar empresas", command=self._carregar_empresas).pack(side=LEFT)

        acoes = ttk.Frame(filtros)
        acoes.pack(fill=X, pady=(8, 0))
        ttk.Button(
            acoes, text="Importar JSON oficial", command=self._importar_json
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            acoes, text="Comparar com XMLs locais", command=self._comparar
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            acoes, text="Histórico dos retornos", command=self._historico
        ).pack(side=LEFT)
        ttk.Label(filtros, textvariable=self.var_status, wraplength=1050).pack(
            anchor="w", pady=(8, 2)
        )
        ttk.Label(filtros, textvariable=self.var_aviso, wraplength=1050).pack(anchor="w")

        api = ttk.LabelFrame(self, text="Consulta API Receita | Requer autorizacao e token temporario", padding=8)
        api.pack(fill=X, padx=9, pady=(0, 5))
        linha_api = ttk.Frame(api)
        linha_api.pack(fill=X)
        ttk.Label(linha_api, text="Token OAuth2 (não é salvo)").pack(side=LEFT, padx=(0, 5))
        self.token_entry = Entry(linha_api, textvariable=self.var_token, show="*", width=38)
        self.token_entry.pack(side=LEFT, padx=(0, 6))
        ttk.Label(linha_api, text="Tíquete").pack(side=LEFT)
        ttk.Entry(linha_api, textvariable=self.var_tiquete, width=34).pack(
            side=LEFT, padx=(4, 6)
        )
        linha_botoes = ttk.Frame(api)
        linha_botoes.pack(fill=X, pady=(6, 0))
        self.btn_solicitar = ttk.Button(
            linha_botoes, text="Solicitar consulta oficial", command=self._solicitar
        )
        self.btn_solicitar.pack(side=LEFT, padx=(0, 5))
        self.btn_situacao = ttk.Button(
            linha_botoes, text="Verificar tíquete", command=self._situacao
        )
        self.btn_situacao.pack(side=LEFT, padx=(0, 5))
        self.btn_baixar = ttk.Button(
            linha_botoes, text="Baixar e importar retorno", command=self._baixar
        )
        self.btn_baixar.pack(side=LEFT)
        ttk.Label(
            api, text=(
                "Sem token? Use 'Importar JSON oficial'. Cada nova solicitacao "
                "consome uma das 4 chamadas diarias permitidas por API."
            ),
            wraplength=1040,
        ).pack(anchor="w", pady=(5, 0))

        area = ttk.LabelFrame(self, text="Conciliacao documental da CBS (amostra incremental)", padding=6)
        area.pack(fill=BOTH, expand=True, padx=9, pady=(0, 8))
        cols = ("nf", "tipo", "xml", "oficial", "saldo", "apropriado", "pendente", "status", "chave")
        labels = (
            "NF", "Operação", "CBS XML", "CBS oficial", "Saldo devedor",
            "Crédito apropriado", "A apropriar", "Resultado", "Chave"
        )
        self.tabela = ttk.Treeview(area, columns=cols, show="headings")
        for coluna, label in zip(cols, labels):
            self.tabela.heading(coluna, text=label)
            self.tabela.column(coluna, width=130 if coluna != "chave" else 350)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        barra_v = ttk.Scrollbar(area, orient="vertical", command=self.tabela.yview)
        barra_h = ttk.Scrollbar(area, orient="horizontal", command=self.tabela.xview)
        barra_v.grid(row=0, column=1, sticky="ns")
        barra_h.grid(row=1, column=0, sticky="ew")
        self.tabela.configure(yscrollcommand=barra_v.set, xscrollcommand=barra_h.set)

    def _carregar_empresas(self):
        selecionada = self.var_empresa.get()
        self.empresas = PainelApuracaoAssistidaRTC._opcoes_empresas(
            EmpresasRegimesService.listar_cadastros()
        )
        self.combo_empresa.configure(values=tuple(self.empresas))
        self.var_empresa.set(
            selecionada if selecionada in self.empresas
            else next(iter(self.empresas), "")
        )

    def _filtros(self):
        empresa = self.empresas.get(self.var_empresa.get())
        if not empresa:
            raise ValueError("Selecione uma empresa no Cadastro Central.")
        cnpj = self.servico.cnpj_base(str(empresa.get("cnpj") or ""))
        # Guardamos os 14 digitos para comparar apenas XMLs deste estabelecimento.
        cnpj_completo = "".join(c for c in str(empresa["cnpj"]) if c.isdigit())
        pa = PainelApuracaoAssistidaRTC._competencia_selecionada(
            self.var_mes.get(), self.var_ano.get(),
        )
        tipo = self.TIPOS[self.var_tipo.get()]
        return cnpj_completo, cnpj, pa, tipo

    def _importar_json(self):
        try:
            cnpj, base, _, tipo = self._filtros()
        except ValueError as exc:
            messagebox.showerror("CBS oficial", str(exc), parent=self)
            return
        caminho = filedialog.askopenfilename(
            parent=self, title="Selecione JSON oficial da Apuracao CBS",
            filetypes=(("Arquivo JSON", "*.json"), ("Todos", "*.*")),
        )
        if not caminho:
            return
        try:
            arquivo = Path(caminho)
            if arquivo.stat().st_size > 40 * 1024 * 1024:
                raise ValueError("JSON maior que 40 MB.")
            resultado = self.servico.importar(arquivo.read_bytes(), tipo, cnpj)
        except (ValueError, OSError) as exc:
            messagebox.showerror("CBS oficial", str(exc), parent=self)
            return
        if resultado.duplicado:
            resumo = "Retorno oficial ja importado; nao houve duplicacao."
        else:
            resumo = (
                f"Retorno {tipo}, raiz {base}: {resultado.novos} novo(s), "
                f"{resultado.atualizados} atualizado(s); periodos: "
                f"{', '.join(resultado.periodos) or 'nenhum'}."
            )
        self.var_status.set(resumo)
        self._comparar()

    def _comparar(self):
        try:
            cnpj, base, comp, tipo = self._filtros()
            resultado = self.servico.conciliar(cnpj, comp, tipo)
        except (ValueError, OSError) as exc:
            messagebox.showerror("CBS oficial", str(exc), parent=self)
            return
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        estatisticas = {}
        for doc in resultado:
            estatisticas[doc["status"]] = estatisticas.get(doc["status"], 0) + 1
            self.tabela.insert("", END, values=(
                doc["nf"], doc["tipo"], doc["cbs_xml"], doc["cbs_oficial"],
                doc["saldo_oficial"], doc["apropriado_oficial"],
                doc["a_apropriar_oficial"], doc["status"], doc["chave"],
            ))
        contagem = ", ".join(f"{k}: {v}" for k, v in estatisticas.items())
        self.var_aviso.set(
            f"{len(resultado)} XML(s) da operacao selecionada. "
            f"{contagem}. A consulta por raiz {base} devolve atualizacoes "
            "incrementais; notas ausentes NAO significam que a Receita as desconhece."
        )

    def _historico(self):
        try:
            cnpj, _, _, tipo = self._filtros()
            docs = self.servico.historico(cnpj, tipo)
        except ValueError as exc:
            messagebox.showerror("CBS oficial", str(exc), parent=self)
            return
        if not docs:
            messagebox.showinfo("CBS", "Nenhum retorno oficial deste tipo foi importado.", parent=self)
            return
        texto = "\n".join(
            f"{x['importado_em']} | {x['registros_recebidos']} registro(s) | "
            f"{x['registros_novos']} novos" for x in docs[:15]
        )
        messagebox.showinfo("Histórico CBS oficial", texto, parent=self)

    def _cliente(self):
        return ClienteCBSReceita(self.var_token.get(), self.servico)

    def _executar_online(self, acao, ao_concluir):
        if self._em_rede:
            messagebox.showwarning("CBS", "Ja existe uma consulta em andamento.", parent=self)
            return
        self._em_rede = True
        self.var_status.set("Consultando a Receita (somente leitura)...")
        for botao in (self.btn_solicitar, self.btn_situacao, self.btn_baixar):
            botao.configure(state="disabled")

        def tarefa():
            try:
                resposta = acao()
            except Exception as exc:
                mensagem = str(exc)
                self.after(0, lambda: terminar(None, mensagem))
            else:
                self.after(0, lambda: terminar(resposta, None))

        def terminar(resultado, erro):
            self._em_rede = False
            for botao in (self.btn_solicitar, self.btn_situacao, self.btn_baixar):
                botao.configure(state="normal")
            # Nunca exibir token ou URL assinada em mensagens.
            if erro:
                self.var_status.set("Consulta nao concluida.")
                messagebox.showerror("CBS oficial", erro, parent=self)
            else:
                ao_concluir(resultado)

        threading.Thread(target=tarefa, daemon=True).start()

    def _solicitar(self):
        try:
            cnpj, _, _, tipo = self._filtros()
            cliente = self._cliente()
            if not messagebox.askyesno(
                "Confirmar consulta", f"Solicitar nova consulta de {tipo} "
                "a Receita? O limite oficial e de 4 solicitacoes diarias "
                "por API. O FiscalPro nao paga ou declara impostos.",
                parent=self,
            ):
                return
        except ValueError as exc:
            messagebox.showerror("CBS", str(exc), parent=self)
            return
        def concluir(ticket):
            self.var_tiquete.set(ticket)
            self.var_status.set("Solicitacao aceita. Use Verificar tiquete antes do download.")
            self.var_token.set("")
        self._executar_online(lambda: cliente.solicitar(cnpj, tipo), concluir)

    def _situacao(self):
        try:
            cliente = self._cliente()
            ticket = self.var_tiquete.get().strip()
        except ValueError as exc:
            messagebox.showerror("CBS", str(exc), parent=self)
            return
        def concluir(situacao):
            self.var_status.set(f"Situacao oficial do tiquete: {situacao}")
            self.var_token.set("")
        self._executar_online(lambda: cliente.situacao(ticket), concluir)

    def _baixar(self):
        try:
            cnpj, _, _, tipo = self._filtros()
            cliente = self._cliente()
            ticket = self.var_tiquete.get().strip()
        except ValueError as exc:
            messagebox.showerror("CBS", str(exc), parent=self)
            return
        def concluir(resultado):
            self.var_token.set("")
            self.var_status.set(
                f"JSON oficial recebido: {resultado.novos} novo(s), "
                f"{resultado.atualizados} atualizados; retorno duplicado: {resultado.duplicado}."
            )
            self._comparar()
        self._executar_online(lambda: cliente.baixar_e_importar(cnpj, tipo, ticket), concluir)
