"""RTC 2: consulta controlada e conciliacao da CBS oficial vs. XML local.

A interface nao armazena token, nao apropria credito e nao confirma apuracao.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tkinter import BOTH, END, LEFT, X, StringVar, Toplevel, ttk, Entry
from tkinter import filedialog, messagebox
import threading
from time import monotonic

from src.services.cbs_apuracao_oficial_service import ServicoCBSOficial
from src.services.cbs_apuracao_api_client import ClienteCBSReceita
from src.services.receita_integra_auth import AutenticadorReceitaIntegra
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
        self.var_client_id = StringVar()
        self.var_client_secret = StringVar()
        self._access_token: str | None = None
        self._token_valido_ate = 0.0
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
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            acoes, text="Ver competências oficiais", command=self._ver_competencias
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            acoes, text="Ver documentos oficiais", command=self._ver_documentos_oficiais
        ).pack(side=LEFT)
        ttk.Label(filtros, textvariable=self.var_status, wraplength=1050).pack(
            anchor="w", pady=(8, 2)
        )
        ttk.Label(filtros, textvariable=self.var_aviso, wraplength=1050).pack(anchor="w")

        api = ttk.LabelFrame(self, text="Consulta API Receita | Credenciais e token automatico", padding=8)
        api.pack(fill=X, padx=9, pady=(0, 5))
        linha_api = ttk.Frame(api)
        linha_api.pack(fill=X)
        ttk.Label(linha_api, text="Client ID").pack(side=LEFT, padx=(0, 5))
        self.id_entry = Entry(linha_api, textvariable=self.var_client_id, width=26)
        self.id_entry.pack(side=LEFT, padx=(0, 8))
        ttk.Label(linha_api, text="Client Secret").pack(side=LEFT)
        self.secret_entry = Entry(linha_api, textvariable=self.var_client_secret, show="*", width=28)
        self.secret_entry.pack(side=LEFT, padx=(4, 8))
        self.btn_autenticar = ttk.Button(
            linha_api, text="Autenticar", command=self._autenticar
        )
        self.btn_autenticar.pack(side=LEFT, padx=(0, 8))
        linha_ticket = ttk.Frame(api)
        linha_ticket.pack(fill=X, pady=(6, 0))
        ttk.Label(linha_ticket, text="Tíquete").pack(side=LEFT, padx=(0, 5))
        ttk.Entry(linha_ticket, textvariable=self.var_tiquete, width=40).pack(
            side=LEFT, padx=(0, 6)
        )
        ttk.Button(
            linha_ticket, text="Recuperar último tíquete",
            command=self._recuperar_tiquete,
        ).pack(side=LEFT, padx=(0, 6))
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
                "Credenciais sao usadas somente para gerar token temporario em memoria; "
                "os campos sao limpos apos a autenticacao. Cada nova solicitacao "
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
        periodos = self.servico.resumo_competencias(cnpj, tipo)
        atual = next((p for p in periodos if p["competencia"] == comp), None)
        num_oficiais = atual["registros"] if atual else 0
        num_comparaveis = atual["candidatos_xml"] if atual else 0
        self.var_aviso.set(
            f"{len(resultado)} XML(s) da operacao selecionada; "
            f"{num_oficiais} registro(s) oficiais armazenados em {comp} "
            f"({num_comparaveis} potencialmente comparaveis por chave). "
            f"{contagem}. A consulta por raiz {base} devolve atualizacoes "
            "incrementais; notas ausentes NAO significam que a Receita as desconhece."
        )

    def _ver_competencias(self):
        """Mostra a distribuicao dos dados ja importados, sem consulta online."""
        try:
            cnpj, _, _, tipo = self._filtros()
            periodos = self.servico.resumo_competencias(cnpj, tipo)
        except (ValueError, OSError) as exc:
            messagebox.showerror("CBS | Competencias", str(exc), parent=self)
            return
        if not periodos:
            messagebox.showinfo(
                "CBS | Competencias",
                "Ainda nao existem registros oficiais armazenados para esse "
                "tipo de retorno e essa raiz de CNPJ.",
                parent=self,
            )
            return
        linhas = [
            f"{p['competencia']}: {p['registros']} registro(s), "
            f"{p['candidatos_xml']} candidato(s) a confronto por chave"
            for p in periodos
        ]
        messagebox.showinfo(
            "CBS | Competencias dos registros oficiais",
            "Distribuicao dos retornos incrementais ja importados:\n\n"
            + "\n".join(linhas)
            + "\n\nAs contagens nao comprovam que o mes esteja completo.",
            parent=self,
        )

    def _ver_documentos_oficiais(self):
        """Exibe dados ja importados da Receita mesmo sem XML local equivalente."""
        try:
            cnpj, raiz, competencia, tipo = self._filtros()
            registros = self.servico.listar_registros_oficiais(
                cnpj, competencia, tipo,
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("CBS | Documentos oficiais", str(exc), parent=self)
            return
        if not registros:
            messagebox.showinfo(
                "CBS | Documentos oficiais",
                f"Nenhum registro oficial armazenado para {competencia}, "
                f"tipo {tipo}, raiz {raiz}. Isso nao prova ausencia de dados "
                "na Receita: as consultas sao incrementais.",
                parent=self,
            )
            return
        janela = self.winfo_toplevel()
        popup = Toplevel(janela)
        popup.title(f"CBS oficial | {competencia} | {tipo} | raiz {raiz}")
        popup.geometry("1140x540")
        popup.minsize(780, 320)
        caixa = ttk.Frame(popup, padding=10)
        caixa.pack(fill=BOTH, expand=True)
        ttk.Label(
            caixa,
            text=(
                f"{len(registros)} registro(s) oficiais armazenados para "
                f"{competencia}. Limite de 5.000 por visualizacao. "
                "A consulta e por raiz CNPJ; dados podem incluir filiais. "
                "Retorno incremental, NAO apuracao mensal completa."
            ),
            wraplength=1100,
        ).pack(anchor="w", pady=(0, 8))
        grade_frame = ttk.Frame(caixa)
        grade_frame.pack(fill=BOTH, expand=True)
        colunas = (
            "chave", "origem", "modelo", "emissao", "cbs",
            "extinto", "saldo", "apropriado", "a_apropriar",
        )
        titulos = (
            "Chave do documento", "Origem", "Modelo", "Emissao",
            "CBS apurada", "CBS extinta", "Saldo devedor",
            "Credito apropriado", "A apropriar",
        )
        grade = ttk.Treeview(
            grade_frame, columns=colunas, show="headings", selectmode="browse",
        )
        for coluna, titulo in zip(colunas, titulos):
            grade.heading(coluna, text=titulo)
            grade.column(coluna, width=335 if coluna == "chave" else 132, anchor="w")
        for item in registros:
            grade.insert(
                "", END, values=(
                    item["chave"], item["origem"], item["modelo"],
                    item["emissao"], item["apurado"], item["extinto"],
                    item["saldo_devedor"], item["apropriado"], item["a_apropriar"],
                ),
            )
        sb_v = ttk.Scrollbar(grade_frame, orient="vertical", command=grade.yview)
        sb_h = ttk.Scrollbar(grade_frame, orient="horizontal", command=grade.xview)
        grade.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        grade_frame.rowconfigure(0, weight=1)
        grade_frame.columnconfigure(0, weight=1)
        grade.grid(row=0, column=0, sticky="nsew")
        sb_v.grid(row=0, column=1, sticky="ns")
        sb_h.grid(row=1, column=0, sticky="ew")

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
        if not self._access_token or monotonic() >= self._token_valido_ate:
            self._access_token = None
            self._token_valido_ate = 0.0
            raise ValueError("Token ausente ou expirado. Informe Client ID e Client Secret "
                             "e clique em Autenticar novamente.")
        return ClienteCBSReceita(self._access_token, self.servico)

    def _autenticar(self):
        if self._em_rede:
            messagebox.showwarning("CBS", "Ja existe uma requisicao em andamento.", parent=self)
            return
        if self._access_token and monotonic() < self._token_valido_ate:
            self.var_status.set(
                "Token de acesso ainda valido nesta sessao. Nao e necessario "
                "autenticar novamente. Utilize o tiquete ja salvo."
            )
            return
        client_id = self.var_client_id.get()
        client_secret = self.var_client_secret.get()
        # Secrets sao retirados dos campos antes do envio. Nada e persistido.
        self.var_client_id.set("")
        self.var_client_secret.set("")
        def solicitar_token():
            return AutenticadorReceitaIntegra().obter_token(client_id, client_secret)
        def concluir(resultado):
            self._access_token = resultado.valor
            self._token_valido_ate = monotonic() + max(0, resultado.expira_em_segundos - 120)
            self.var_status.set(
                "Autenticacao aceita pela Receita. Token temporario em memoria. "
                "Agora e possivel solicitar consultas de CBS."
            )
        self._executar_online(solicitar_token, concluir)

    def _executar_online(self, acao, ao_concluir):
        if self._em_rede:
            messagebox.showwarning("CBS", "Ja existe uma consulta em andamento.", parent=self)
            return
        self._em_rede = True
        self.var_status.set("Consultando a Receita (somente leitura)...")
        for botao in (self.btn_autenticar, self.btn_solicitar, self.btn_situacao, self.btn_baixar):
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
            for botao in (self.btn_autenticar, self.btn_solicitar, self.btn_situacao, self.btn_baixar):
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
        self._executar_online(lambda: cliente.solicitar(cnpj, tipo), concluir)

    def _recuperar_tiquete(self):
        try:
            cnpj, _, _, tipo = self._filtros()
            registro = self.servico.recuperar_ultimo_tiquete(cnpj, tipo)
        except (ValueError, OSError) as exc:
            messagebox.showerror("CBS oficial", str(exc), parent=self)
            return
        if registro is None:
            self.var_status.set(
                "Nenhuma solicitacao pendente ou concluida foi encontrada "
                "para esta empresa e este tipo de retorno."
            )
            messagebox.showinfo(
                "CBS oficial", "Nao foi localizado tiquete reutilizavel no banco local. "
                "Confira a empresa e o tipo de retorno. Nao faca outra consulta "
                "antes de verificar a origem do registro.",
                parent=self,
            )
            return
        self.var_tiquete.set(registro["ticket"])
        self.var_status.set(
            "Tiquete recuperado do banco local. "
            f"Situacao registrada: {registro['situacao']}. "
            "Use Verificar tiquete para confirmar a situacao atual na Receita."
        )

    def _situacao(self):
        try:
            cliente = self._cliente()
            ticket = self.var_tiquete.get().strip()
        except ValueError as exc:
            messagebox.showerror("CBS", str(exc), parent=self)
            return
        def concluir(situacao):
            self.var_status.set(f"Situacao oficial do tiquete: {situacao}")
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
            self.var_status.set(
                f"JSON oficial recebido: {resultado.novos} novo(s), "
                f"{resultado.atualizados} atualizados; retorno duplicado: {resultado.duplicado}."
            )
            self._comparar()
        self._executar_online(lambda: cliente.baixar_e_importar(cnpj, tipo, ticket), concluir)
