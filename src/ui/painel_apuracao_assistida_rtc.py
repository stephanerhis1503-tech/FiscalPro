"""RTC 1 - painel de conferencia local dos XMLs IBS/CBS (sem API e sem recolhimento)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tkinter import BOTH, END, LEFT, X, StringVar, ttk
from tkinter import filedialog, messagebox

from src.services.apuracao_assistida_local_service import ServicoApuracaoLocalRTC
from src.services.empresas_regimes_service import EmpresasRegimesService


class PainelApuracaoAssistidaRTC(ttk.Frame):
    FILTROS_TIPO = ("Todas", "Somente entradas", "Somente saídas", "Somente revisar")

    MESES = (
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    )

    @classmethod
    def _competencia_selecionada(cls, mes: str, ano: str) -> str:
        """Converte os seletores de mes e ano ao formato usado pelo banco."""
        if mes not in cls.MESES:
            raise ValueError("Selecione um mês válido.")
        ano = str(ano or "").strip()
        if not (len(ano) == 4 and ano.isascii() and ano.isdigit() and 2000 <= int(ano) <= 2100):
            raise ValueError("Selecione um ano válido.")
        return ServicoApuracaoLocalRTC.validar_competencia(
            f"{ano}-{cls.MESES.index(mes) + 1:02d}"
        )

    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.servico = ServicoApuracaoLocalRTC()
        self.empresas: dict[str, dict] = {}
        self.var_empresa = StringVar()
        hoje = date.today()
        self.var_mes = StringVar(value=self.MESES[hoje.month - 1])
        self.var_ano = StringVar(value=str(hoje.year))
        self.var_status = StringVar(value="Selecione uma empresa e a competencia.")
        self.var_totais = StringVar(value="Nenhum documento carregado.")
        self.var_tipo_lista = StringVar(value="Todas")
        self.var_busca_nf = StringVar()
        self.var_exibidos = StringVar(value="Nenhuma nota carregada.")
        self.documentos: list[dict] = []
        self._montar()
        self._carregar_empresas()

    def _montar(self):
        cab = ttk.LabelFrame(self, text="RTC 1 | Base local da Apuracao Assistida", padding=10)
        cab.pack(fill=X, padx=10, pady=(8, 6))
        ttk.Label(
            cab,
            text=(
                "Conferencia preliminar dos XMLs. Nao consulta a Receita, "
                "nao reconhece creditos e nao confirma recolhimentos."
            ),
            wraplength=1000,
        ).pack(anchor="w", pady=(0, 8))

        filtros = ttk.Frame(cab)
        filtros.pack(fill=X)
        ttk.Label(filtros, text="Empresa / CNPJ").pack(side=LEFT)
        self.combo_empresas = ttk.Combobox(
            filtros, textvariable=self.var_empresa, state="readonly", width=52
        )
        self.combo_empresas.pack(side=LEFT, padx=(6, 14))
        ttk.Label(filtros, text="Competência").pack(side=LEFT)
        self.combo_mes = ttk.Combobox(
            filtros, textvariable=self.var_mes, state="readonly",
            values=self.MESES, width=12,
        )
        self.combo_mes.pack(side=LEFT, padx=(6, 4))
        self.combo_ano = ttk.Combobox(
            filtros, textvariable=self.var_ano, state="readonly",
            values=tuple(str(ano) for ano in range(date.today().year + 5, 2019, -1)),
            width=7,
        )
        self.combo_ano.pack(side=LEFT, padx=(0, 8))
        ttk.Button(filtros, text="Atualizar empresas", command=self._atualizar_empresas_com_aviso).pack(
            side=LEFT
        )

        botoes = ttk.Frame(cab)
        botoes.pack(fill=X, pady=(10, 0))
        ttk.Button(
            botoes, text="Importar XML / ZIP", command=self._importar_arquivos
        ).pack(side=LEFT, padx=(0, 5))
        ttk.Button(
            botoes, text="Importar pasta", command=self._importar_pasta
        ).pack(side=LEFT, padx=(0, 5))
        ttk.Button(
            botoes, text="Consultar base local", command=self._consultar
        ).pack(side=LEFT)
        ttk.Label(cab, textvariable=self.var_status, wraplength=1020).pack(
            anchor="w", pady=(8, 0)
        )

        resumo = ttk.LabelFrame(self, text="Totais extraidos dos XMLs - NAO oficiais", padding=8)
        resumo.pack(fill=X, padx=10, pady=5)
        ttk.Label(resumo, textvariable=self.var_totais, wraplength=1000).pack(anchor="w")

        corpo = ttk.LabelFrame(self, text="Notas fiscais importadas", padding=6)
        corpo.pack(fill=BOTH, expand=True, padx=10, pady=(4, 8))
        barra_filtros = ttk.Frame(corpo)
        barra_filtros.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(barra_filtros, text="Mostrar:").pack(side=LEFT, padx=(0, 5))
        self.combo_tipo_lista = ttk.Combobox(
            barra_filtros, textvariable=self.var_tipo_lista,
            values=self.FILTROS_TIPO, width=20, state="readonly",
        )
        self.combo_tipo_lista.pack(side=LEFT, padx=(0, 12))
        self.combo_tipo_lista.bind("<<ComboboxSelected>>", lambda _evento: self._atualizar_grade())
        ttk.Label(barra_filtros, text="Buscar NF ou chave:").pack(side=LEFT, padx=(0, 5))
        campo_busca = ttk.Entry(barra_filtros, textvariable=self.var_busca_nf, width=25)
        campo_busca.pack(side=LEFT, padx=(0, 5))
        campo_busca.bind("<Return>", lambda _evento: self._atualizar_grade())
        ttk.Button(barra_filtros, text="Filtrar", command=self._atualizar_grade).pack(
            side=LEFT, padx=(0, 10)
        )
        ttk.Label(barra_filtros, textvariable=self.var_exibidos).pack(side=LEFT)
        nomes = ("tipo", "nf", "emissao", "chave", "ibs", "cbs", "conferencia", "credito", "protocolo")
        titulos = (
            "Tipo", "NF", "Emissao", "Chave NF-e", "IBS XML", "CBS XML",
            "Conferencia", "Credito", "Protocolo"
        )
        self.tabela = ttk.Treeview(corpo, columns=nomes, show="headings")
        for n, titulo in zip(nomes, titulos):
            self.tabela.heading(n, text=titulo)
            self.tabela.column(
                n, width=360 if n == "chave" else 165 if n in {"conferencia", "credito", "protocolo"} else 90,
                minwidth=65, anchor="w" if n in {"chave", "credito", "protocolo"} else "center",
            )
        sy = ttk.Scrollbar(corpo, orient="vertical", command=self.tabela.yview)
        sx = ttk.Scrollbar(corpo, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        corpo.rowconfigure(1, weight=1)
        corpo.columnconfigure(0, weight=1)
        self.tabela.grid(row=1, column=0, sticky="nsew")
        sy.grid(row=1, column=1, sticky="ns")
        sx.grid(row=2, column=0, sticky="ew")

    @staticmethod
    def _opcoes_empresas(cadastros):
        """Exibe PJs mesmo sem CNPJ; nunca permite importar por um identificador vazio."""
        opcoes = {}
        for cadastro in cadastros:
            if str(cadastro.get("tipo_pessoa") or "PJ").upper() == "PF":
                continue
            if not int(cadastro.get("ativa", 1) or 0):
                continue
            nome = str(cadastro.get("nome") or "").strip()
            if not nome:
                continue
            cnpj = "".join(x for x in str(cadastro.get("cnpj") or "") if x.isdigit())
            identificador = cnpj if len(cnpj) == 14 else "CNPJ pendente"
            rotulo = f"{nome} | {identificador}"
            opcoes[rotulo] = cadastro
        return opcoes

    def _carregar_empresas(self):
        selecionada = self.var_empresa.get()
        cadastros = EmpresasRegimesService.listar_cadastros()
        self.empresas = self._opcoes_empresas(cadastros)
        self.combo_empresas.configure(values=tuple(self.empresas))
        if selecionada in self.empresas:
            self.var_empresa.set(selecionada)
        elif self.empresas:
            self.var_empresa.set(next(iter(self.empresas)))
        else:
            self.var_empresa.set("")
            self.var_status.set(
                "Nenhuma pessoa juridica ativa encontrada no Cadastro Central. "
                "Confira a aba Empresas e clique em Atualizar empresas."
            )
            return
        pendentes = sum(
            1 for empresa in self.empresas.values()
            if len("".join(c for c in str(empresa.get("cnpj") or "") if c.isdigit())) != 14
        )
        if pendentes:
            self.var_status.set(
                f"{pendentes} empresa(s) sem CNPJ. Para importar XMLs, abra a aba Empresas, "
                "selecione a empresa, clique em Editar e informe o CNPJ. "
                "Depois retorne aqui e clique em Atualizar empresas."
            )
        else:
            self.var_status.set(f"{len(self.empresas)} empresa(s) carregada(s) do Cadastro Central.")

    def _atualizar_empresas_com_aviso(self):
        """Garante retorno visivel ao clicar em Atualizar empresas."""
        try:
            self._carregar_empresas()
        except Exception as exc:
            self.var_status.set("Falha ao consultar Cadastro Central.")
            messagebox.showerror(
                "RTC | Empresas",
                "Nao foi possivel ler o Cadastro Central. "
                f"Detalhes: {exc}",
                parent=self,
            )
            return

        total = len(self.empresas)
        if not total:
            messagebox.showwarning(
                "RTC | Nenhuma empresa localizada",
                "O FiscalPro desta execucao nao localizou empresas ativas no "
                "Cadastro Central. Abra a aba Empresas e confira se os cadastros "
                "aparecem la. Se aparecem no FiscalPro instalado, mas nao nesta "
                "versao aberta pelo Python, os programas podem estar utilizando "
                "pastas de dados diferentes. Nao crie cadastros duplicados.",
                parent=self,
            )
            return

        pendentes = sum(
            1 for cadastro in self.empresas.values()
            if len("".join(c for c in str(cadastro.get("cnpj") or "") if c.isdigit())) != 14
        )
        messagebox.showinfo(
            "RTC | Empresas atualizadas",
            f"{total} empresa(s) encontrada(s) no Cadastro Central. "
            f"{pendentes} com CNPJ pendente.\n\n"
            "Abra a lista Empresa / CNPJ para selecionar. "
            "A importacao de XML permanece bloqueada para empresas sem CNPJ.",
            parent=self,
        )

    def _filtros(self):
        empresa = self.empresas.get(self.var_empresa.get())
        if not empresa:
            raise ValueError("Selecione uma empresa valida no Cadastro Central.")
        cnpj = "".join(x for x in str(empresa.get("cnpj") or "") if x.isdigit())
        if len(cnpj) != 14:
            raise ValueError(
                "Esta empresa ainda nao tem CNPJ cadastrado. Abra a aba Empresas, "
                "selecione a empresa, clique em Editar, salve o CNPJ e depois "
                "clique em Atualizar empresas na aba RTC. "
                "A importacao foi bloqueada para nao misturar dados de empresas."
            )
        competencia = self._competencia_selecionada(self.var_mes.get(), self.var_ano.get())
        return cnpj, competencia

    def _importar_arquivos(self):
        arquivos = filedialog.askopenfilenames(
            parent=self, title="XMLs ou ZIPs de NF-e",
            filetypes=(("XML ou ZIP", "*.xml *.zip"), ("Todos", "*.*")),
        )
        if arquivos:
            self._importar(list(arquivos))

    def _importar_pasta(self):
        pasta = filedialog.askdirectory(parent=self, title="Pasta com XMLs")
        if pasta:
            self._importar([pasta])

    def _importar(self, caminhos):
        try:
            cnpj, competencia = self._filtros()
            resultado = self.servico.importar(caminhos, cnpj, competencia)
            self._consultar()
        except (ValueError, OSError) as exc:
            messagebox.showerror("RTC 1", str(exc), parent=self)
            return
        texto = (
            f"{resultado.lidos} lidos | {resultado.importados} novos | "
            f"{resultado.duplicados} duplicados | {resultado.atualizados} complementados | "
            f"{resultado.conflitos} conflitos | "
            f"{resultado.ignorados} ignorados."
        )
        self.var_status.set(texto)
        if resultado.avisos:
            messagebox.showwarning(
                "Importacao RTC 1", texto + "\n\n" + "\n".join(resultado.avisos),
                parent=self,
            )

    @classmethod
    def _filtrar_documentos(cls, documentos: list[dict], tipo: str, busca: str = "") -> list[dict]:
        """Filtro apenas visual; nao altera registros nem totais da competencia."""
        if tipo not in cls.FILTROS_TIPO:
            raise ValueError("Filtro de visualizacao invalido.")
        termo = str(busca or "").strip().casefold()
        retorno: list[dict] = []
        for doc in documentos:
            direcao = str(doc.get("direcao") or "").upper()
            conferencia = str(doc.get("status_conferencia") or "").upper()
            if tipo == "Somente entradas" and direcao != "ENTRADA":
                continue
            if tipo == "Somente saídas" and direcao != "SAIDA":
                continue
            if tipo == "Somente revisar" and conferencia != "REVISAR":
                continue
            if termo and not any(
                termo in str(doc.get(chave) or "").casefold()
                for chave in ("numero_nf", "chave_nfe")
            ):
                continue
            retorno.append(doc)
        return retorno

    def _atualizar_grade(self):
        documentos = self._filtrar_documentos(
            self.documentos, self.var_tipo_lista.get(), self.var_busca_nf.get()
        )
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        for doc in documentos:
            self.tabela.insert(
                "", END, values=(
                    doc["direcao"], doc["numero_nf"], doc["emissao"],
                    doc["chave_nfe"], doc["valor_ibs"], doc["valor_cbs"],
                    doc["status_conferencia"], doc["status_credito"],
                    doc["status_protocolo"],
                )
            )
        self.var_exibidos.set(
            f"Exibindo {len(documentos)} de {len(self.documentos)} nota(s)"
        )

    def _consultar(self):
        try:
            cnpj, competencia = self._filtros()
            linhas = self.servico.listar(cnpj, competencia)
            totais = self.servico.resumo(cnpj, competencia)
        except (ValueError, OSError) as exc:
            messagebox.showerror("RTC 1", str(exc), parent=self)
            return
        self.documentos = linhas
        self._atualizar_grade()
        self.var_totais.set(
            f"{totais['documentos']} notas ({totais['saidas']} saidas; "
            f"{totais['entradas']} entradas; {totais['revisar']} revisar).  "
            f"Debitos em XMLs: IBS R$ {totais['ibs_debito_xml']} | "
            f"CBS R$ {totais['cbs_debito_xml']}.  "
            f"Creditos apenas potenciais em XMLs: IBS R$ "
            f"{totais['ibs_credito_potencial']} | "
            f"CBS R$ {totais['cbs_credito_potencial']}."
        )
        self.var_status.set(
            "Base local consultada. Valores nao representam apuracao oficial."
        )
