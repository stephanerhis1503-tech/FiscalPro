"""Cadastro central de empresas e pessoas do FiscalPro — versão 18.2.20."""

from __future__ import annotations

from tkinter import BOTH, END, LEFT, RIGHT, X, Frame, Label, StringVar, BooleanVar, Toplevel
from tkinter import messagebox, ttk

from src.services.cadastro_empresas_service import CadastroEmpresasService

from .estilos import (
    COR_BORDA,
    COR_CARD,
    COR_DESTAQUE,
    COR_TEXTO,
    COR_TEXTO_SUAVE,
)


class PainelEmpresas(ttk.Frame):
    def __init__(self, master, ao_alterar=None):
        super().__init__(master, style="Page.TFrame")
        self.ao_alterar = ao_alterar
        self.servico = CadastroEmpresasService()
        self.var_busca = StringVar(value="")
        self.var_inativas = BooleanVar(value=False)
        self.var_resumo = StringVar(value="")
        self._montar()
        self.atualizar()
        self.servico.sincronizar_integracoes()

    @staticmethod
    def _formatar_documento(valor: object) -> str:
        digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
        if len(digitos) == 11:
            return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
        if len(digitos) == 14:
            return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
        return digitos or "—"

    @staticmethod
    def _rotulo_tipo(tipo: object) -> str:
        return "Pessoa Física" if str(tipo or "PJ").upper() == "PF" else "Pessoa Jurídica"

    def _montar(self) -> None:
        cab = Frame(self, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)
        cab.pack(fill=X, padx=10, pady=(7, 6))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        miolo = Frame(cab, bg=COR_CARD, padx=12, pady=8)
        miolo.pack(fill=X)
        Label(
            miolo,
            text="Cadastro Central de Empresas e Pessoas",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        Label(
            miolo,
            text=(
                "Cadastre cada empresa ou pessoa uma única vez. Pessoas jurídicas alimentam Tributação, "
                "Controle de Entregas, Contas a Pagar e NF-e/NFS-e. Pessoas físicas ficam disponíveis para "
                "uso administrativo, como contas pessoais dos sócios."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
            justify=LEFT,
            wraplength=1120,
        ).pack(anchor="w", pady=(3, 0))

        acoes = ttk.LabelFrame(self, text="Cadastros", padding=8, style="Card.TLabelframe")
        acoes.pack(fill=X, padx=10, pady=(0, 6))
        acoes.columnconfigure(1, weight=1)
        ttk.Label(acoes, text="Buscar:").grid(row=0, column=0, sticky="w")
        ent = ttk.Entry(acoes, textvariable=self.var_busca)
        ent.grid(row=0, column=1, sticky="ew", padx=(6, 10))
        ent.bind("<Return>", lambda _e: self.atualizar())
        ttk.Checkbutton(
            acoes,
            text="Mostrar inativos",
            variable=self.var_inativas,
            command=self.atualizar,
        ).grid(row=0, column=2, sticky="w", padx=(0, 10))
        ttk.Button(acoes, text="Pesquisar", command=self.atualizar).grid(row=0, column=3, padx=(0, 6))
        ttk.Button(acoes, text="＋ Novo cadastro", command=self._nova, style="Primary.TButton").grid(row=0, column=4, padx=3)
        ttk.Button(acoes, text="Editar", command=self._editar).grid(row=0, column=5, padx=3)
        ttk.Button(acoes, text="Excluir", command=self._excluir).grid(row=0, column=6, padx=3)
        ttk.Button(acoes, text="Ativar / Desativar", command=self._alternar_ativa).grid(row=0, column=7, padx=(3, 0))

        info = Frame(self, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)
        info.pack(fill=X, padx=10, pady=(0, 6))
        Label(
            info,
            textvariable=self.var_resumo,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
        ).pack(side=LEFT)
        ttk.Button(info, text="Atualizar integrações", command=self._sincronizar).pack(side=RIGHT, padx=8, pady=4)

        caixa = ttk.LabelFrame(self, text="Cadastro", padding=7, style="Card.TLabelframe")
        caixa.pack(fill=BOTH, expand=True, padx=10, pady=(0, 8))
        caixa.rowconfigure(0, weight=1)
        caixa.columnconfigure(0, weight=1)
        colunas = ("id", "tipo", "nome", "documento", "regime", "status")
        self.tabela = ttk.Treeview(caixa, columns=colunas, show="headings", selectmode="browse", height=18)
        titulos = {
            "id": "ID",
            "tipo": "Tipo",
            "nome": "Nome / Razão social",
            "documento": "CPF / CNPJ",
            "regime": "Regime tributário",
            "status": "Situação",
        }
        larguras = {"id": 50, "tipo": 120, "nome": 300, "documento": 170, "regime": 175, "status": 90}
        for c in colunas:
            self.tabela.heading(c, text=titulos[c])
            self.tabela.column(c, width=larguras[c], anchor="center" if c in {"id", "tipo", "status"} else "w")
        self.tabela.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(caixa, orient="vertical", command=self.tabela.yview)
        sy.grid(row=0, column=1, sticky="ns")
        self.tabela.configure(yscrollcommand=sy.set)
        self.tabela.bind("<Double-1>", lambda _e: self._editar())
        self.tabela.tag_configure("inativa", foreground=COR_TEXTO_SUAVE)

    def atualizar(self) -> None:
        termo = self.var_busca.get().strip().casefold()
        cadastros = self.servico.listar(incluir_inativas=True)
        total = len(cadastros)
        ativos = sum(1 for e in cadastros if int(e.get("ativa") or 0))
        pfs = sum(1 for e in cadastros if str(e.get("tipo_pessoa") or "PJ").upper() == "PF")
        self.var_resumo.set(
            f"{ativos} cadastro(s) ativo(s) • {total} cadastrado(s) • {pfs} pessoa(s) física(s)"
        )
        self.tabela.delete(*self.tabela.get_children())
        for cadastro in cadastros:
            ativa = bool(int(cadastro.get("ativa") or 0))
            if not ativa and not self.var_inativas.get():
                continue
            tipo = str(cadastro.get("tipo_pessoa") or "PJ").upper()
            texto_busca = (
                f"{cadastro.get('nome','')} {cadastro.get('cnpj','')} "
                f"{cadastro.get('regime','')} {tipo} {self._rotulo_tipo(tipo)}"
            ).casefold()
            if termo and termo not in texto_busca:
                continue
            iid = str(cadastro["id"])
            self.tabela.insert(
                "",
                END,
                iid=iid,
                values=(
                    cadastro["id"],
                    "PF" if tipo == "PF" else "PJ",
                    cadastro.get("nome") or "",
                    self._formatar_documento(cadastro.get("cnpj")),
                    cadastro.get("regime") or ("NÃO SE APLICA" if tipo == "PF" else "A DEFINIR"),
                    "ATIVO" if ativa else "INATIVO",
                ),
                tags=(() if ativa else ("inativa",)),
            )

    def _selecionada(self):
        sel = self.tabela.selection()
        if not sel:
            messagebox.showwarning("Cadastro Central", "Selecione um cadastro.", parent=self.winfo_toplevel())
            return None
        return self.servico.obter(int(sel[0]))

    def _nova(self) -> None:
        JanelaEmpresaCentral(self, self.servico, ao_salvar=self._apos_alterar)

    def _editar(self) -> None:
        cadastro = self._selecionada()
        if cadastro:
            JanelaEmpresaCentral(self, self.servico, empresa=cadastro, ao_salvar=self._apos_alterar)

    def _excluir(self) -> None:
        cadastro = self._selecionada()
        if not cadastro:
            return
        documento = self._formatar_documento(cadastro.get("cnpj"))
        if not messagebox.askyesno(
            "Excluir cadastro",
            (
                "Deseja excluir permanentemente este cadastro?\n\n"
                f"{cadastro.get('nome')}\n{documento}\n\n"
                "Cadastros com entregas históricas vinculadas serão protegidos e não serão apagados."
            ),
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self.servico.excluir(int(cadastro["id"]))
        except Exception as exc:
            messagebox.showerror("Excluir cadastro", str(exc), parent=self.winfo_toplevel())
            return
        self._apos_alterar()
        messagebox.showinfo("Excluir cadastro", "Cadastro excluído com sucesso.", parent=self.winfo_toplevel())

    def _alternar_ativa(self) -> None:
        cadastro = self._selecionada()
        if not cadastro:
            return
        ativa = bool(int(cadastro.get("ativa") or 0))
        acao = "desativar" if ativa else "reativar"
        if not messagebox.askyesno(
            "Cadastro Central",
            f"Deseja {acao} o cadastro\n\n{cadastro.get('nome')}?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            if ativa:
                self.servico.desativar(int(cadastro["id"]))
            else:
                self.servico.reativar(int(cadastro["id"]))
        except Exception as exc:
            messagebox.showerror("Cadastro Central", str(exc), parent=self.winfo_toplevel())
            return
        self._apos_alterar()

    def _sincronizar(self) -> None:
        self.servico.migrar_dados_legados()
        self.servico.sincronizar_integracoes()
        self.atualizar()
        if self.ao_alterar:
            self.ao_alterar()
        messagebox.showinfo(
            "Cadastro Central",
            "Integrações atualizadas. O cadastro central foi reaplicado aos módulos do FiscalPro.",
            parent=self.winfo_toplevel(),
        )

    def _apos_alterar(self) -> None:
        self.atualizar()
        if self.ao_alterar:
            self.ao_alterar()


class JanelaEmpresaCentral(Toplevel):
    TIPOS = ("Pessoa Jurídica", "Pessoa Física")

    def __init__(self, master, servico: CadastroEmpresasService, empresa=None, ao_salvar=None):
        super().__init__(master)
        self.servico = servico
        self.empresa = empresa
        self.ao_salvar = ao_salvar
        self.title("Editar cadastro" if empresa else "Novo cadastro")
        self.geometry("640x360")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()

        tipo_codigo = str(empresa.get("tipo_pessoa") or "PJ").upper() if empresa else "PJ"
        self.var_tipo = StringVar(value="Pessoa Física" if tipo_codigo == "PF" else "Pessoa Jurídica")
        self.var_nome = StringVar(value=str(empresa.get("nome") or "") if empresa else "")
        self.var_documento = StringVar(
            value=PainelEmpresas._formatar_documento(empresa.get("cnpj")) if empresa else ""
        )
        self.var_regime = StringVar(
            value=(
                "NÃO SE APLICA"
                if tipo_codigo == "PF"
                else str(empresa.get("regime") or "A DEFINIR") if empresa else "A DEFINIR"
            )
        )
        self.var_rotulo_documento = StringVar(value="CPF" if tipo_codigo == "PF" else "CNPJ")
        self._montar()
        self._atualizar_tipo()

    def _codigo_tipo(self) -> str:
        return "PF" if self.var_tipo.get() == "Pessoa Física" else "PJ"

    def _montar(self) -> None:
        corpo = ttk.Frame(self, padding=18, style="Page.TFrame")
        corpo.pack(fill=BOTH, expand=True)
        corpo.columnconfigure(1, weight=1)

        ttk.Label(corpo, text="Tipo de cadastro").grid(row=0, column=0, sticky="w", pady=8)
        self.cmb_tipo = ttk.Combobox(
            corpo,
            textvariable=self.var_tipo,
            values=self.TIPOS,
            state="readonly",
        )
        self.cmb_tipo.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=8)
        self.cmb_tipo.bind("<<ComboboxSelected>>", lambda _e: self._atualizar_tipo())
        if self.empresa:
            self.cmb_tipo.configure(state="disabled")

        ttk.Label(corpo, text="Nome / Razão social").grid(row=1, column=0, sticky="w", pady=8)
        self.ent_nome = ttk.Entry(corpo, textvariable=self.var_nome)
        self.ent_nome.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=8)

        ttk.Label(corpo, textvariable=self.var_rotulo_documento).grid(row=2, column=0, sticky="w", pady=8)
        ttk.Entry(corpo, textvariable=self.var_documento).grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=8)

        ttk.Label(corpo, text="Regime tributário").grid(row=3, column=0, sticky="w", pady=8)
        self.cmb_regime = ttk.Combobox(
            corpo,
            textvariable=self.var_regime,
            values=self.servico.REGIMES,
            state="readonly",
        )
        self.cmb_regime.grid(row=3, column=1, sticky="ew", padx=(12, 0), pady=8)

        if self.empresa and not int(self.empresa.get("manual") or 0):
            self.ent_nome.configure(state="readonly")
            ttk.Label(
                corpo,
                text="Empresa-base: o nome é protegido; CNPJ e regime podem ser atualizados.",
                style="CardSubtitle.TLabel",
            ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 6))

        botoes = ttk.Frame(corpo, style="Page.TFrame")
        botoes.grid(row=5, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side=LEFT, padx=(0, 6))
        ttk.Button(botoes, text="Salvar cadastro", command=self._salvar, style="Primary.TButton").pack(side=LEFT)

        self.bind("<Return>", lambda _e: self._salvar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.ent_nome.focus_set()

    def _atualizar_tipo(self) -> None:
        if self._codigo_tipo() == "PF":
            self.var_rotulo_documento.set("CPF")
            self.var_regime.set("NÃO SE APLICA")
            self.cmb_regime.configure(state="disabled")
        else:
            self.var_rotulo_documento.set("CNPJ")
            if self.var_regime.get() == "NÃO SE APLICA":
                self.var_regime.set("A DEFINIR")
            self.cmb_regime.configure(state="readonly")

    def _salvar(self) -> None:
        try:
            tipo = self._codigo_tipo()
            if self.empresa:
                self.servico.editar(
                    int(self.empresa["id"]),
                    self.var_nome.get(),
                    self.var_documento.get(),
                    self.var_regime.get(),
                    tipo,
                )
            else:
                self.servico.cadastrar(
                    self.var_nome.get(),
                    self.var_documento.get(),
                    self.var_regime.get(),
                    tipo,
                )
        except Exception as exc:
            messagebox.showerror("Cadastro Central", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Cadastro Central",
            "Cadastro atualizado com sucesso." if self.empresa else "Cadastro realizado com sucesso.",
            parent=self,
        )
        if self.ao_salvar:
            self.ao_salvar()
        self.destroy()
