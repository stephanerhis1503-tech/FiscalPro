"""Cadastro central de empresas do FiscalPro — versão 18.2.18."""

from __future__ import annotations

from tkinter import BOTH, END, LEFT, RIGHT, X, Frame, Label, StringVar, BooleanVar, Toplevel
from tkinter import messagebox, ttk

from src.services.cadastro_empresas_service import CadastroEmpresasService

from .estilos import (
    COR_BORDA,
    COR_CARD,
    COR_DESTAQUE,
    COR_FUNDO,
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
    def _formatar_cnpj(valor: object) -> str:
        digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
        if len(digitos) != 14:
            return digitos or "—"
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"

    def _montar(self) -> None:
        cab = Frame(self, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)
        cab.pack(fill=X, padx=10, pady=(7, 6))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        miolo = Frame(cab, bg=COR_CARD, padx=12, pady=8)
        miolo.pack(fill=X)
        Label(
            miolo,
            text="Cadastro Central de Empresas",
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        Label(
            miolo,
            text=(
                "Cadastre a empresa uma única vez. Nome, CNPJ e regime passam a alimentar "
                "Tributação, Controle de Entregas, Contas a Pagar e a identidade usada em NF-e/NFS-e. "
                "Certificado A1, NSU e documentos continuam guardados somente no módulo fiscal."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
            justify=LEFT,
            wraplength=1120,
        ).pack(anchor="w", pady=(3, 0))

        acoes = ttk.LabelFrame(self, text="Empresas", padding=8, style="Card.TLabelframe")
        acoes.pack(fill=X, padx=10, pady=(0, 6))
        acoes.columnconfigure(1, weight=1)
        ttk.Label(acoes, text="Buscar:").grid(row=0, column=0, sticky="w")
        ent = ttk.Entry(acoes, textvariable=self.var_busca)
        ent.grid(row=0, column=1, sticky="ew", padx=(6, 10))
        ent.bind("<Return>", lambda _e: self.atualizar())
        ttk.Checkbutton(
            acoes,
            text="Mostrar inativas",
            variable=self.var_inativas,
            command=self.atualizar,
        ).grid(row=0, column=2, sticky="w", padx=(0, 10))
        ttk.Button(acoes, text="Pesquisar", command=self.atualizar).grid(row=0, column=3, padx=(0, 6))
        ttk.Button(acoes, text="＋ Nova empresa", command=self._nova, style="Primary.TButton").grid(row=0, column=4, padx=3)
        ttk.Button(acoes, text="Editar", command=self._editar).grid(row=0, column=5, padx=3)
        ttk.Button(acoes, text="Ativar / Desativar", command=self._alternar_ativa).grid(row=0, column=6, padx=(3, 0))

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
        colunas = ("id", "nome", "cnpj", "regime", "status")
        self.tabela = ttk.Treeview(caixa, columns=colunas, show="headings", selectmode="browse", height=18)
        titulos = {"id": "ID", "nome": "Nome / Razão social", "cnpj": "CNPJ", "regime": "Regime tributário", "status": "Situação"}
        larguras = {"id": 55, "nome": 330, "cnpj": 180, "regime": 190, "status": 100}
        for c in colunas:
            self.tabela.heading(c, text=titulos[c])
            self.tabela.column(c, width=larguras[c], anchor="center" if c in {"id", "status"} else "w")
        self.tabela.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(caixa, orient="vertical", command=self.tabela.yview)
        sy.grid(row=0, column=1, sticky="ns")
        self.tabela.configure(yscrollcommand=sy.set)
        self.tabela.bind("<Double-1>", lambda _e: self._editar())
        self.tabela.tag_configure("inativa", foreground=COR_TEXTO_SUAVE)

    def atualizar(self) -> None:
        termo = self.var_busca.get().strip().casefold()
        empresas = self.servico.listar(incluir_inativas=True)
        total = len(empresas)
        ativas = sum(1 for e in empresas if int(e.get("ativa") or 0))
        self.var_resumo.set(f"{ativas} empresa(s) ativa(s) • {total} cadastrada(s) • cadastro único do FiscalPro")
        self.tabela.delete(*self.tabela.get_children())
        for empresa in empresas:
            ativa = bool(int(empresa.get("ativa") or 0))
            if not ativa and not self.var_inativas.get():
                continue
            texto_busca = f"{empresa.get('nome','')} {empresa.get('cnpj','')} {empresa.get('regime','')}".casefold()
            if termo and termo not in texto_busca:
                continue
            iid = str(empresa["id"])
            self.tabela.insert(
                "",
                END,
                iid=iid,
                values=(
                    empresa["id"],
                    empresa.get("nome") or "",
                    self._formatar_cnpj(empresa.get("cnpj")),
                    empresa.get("regime") or "A DEFINIR",
                    "ATIVA" if ativa else "INATIVA",
                ),
                tags=(() if ativa else ("inativa",)),
            )

    def _selecionada(self):
        sel = self.tabela.selection()
        if not sel:
            messagebox.showwarning("Cadastro de Empresas", "Selecione uma empresa.", parent=self.winfo_toplevel())
            return None
        return self.servico.obter(int(sel[0]))

    def _nova(self) -> None:
        JanelaEmpresaCentral(self, self.servico, ao_salvar=self._apos_alterar)

    def _editar(self) -> None:
        empresa = self._selecionada()
        if empresa:
            JanelaEmpresaCentral(self, self.servico, empresa=empresa, ao_salvar=self._apos_alterar)

    def _alternar_ativa(self) -> None:
        empresa = self._selecionada()
        if not empresa:
            return
        ativa = bool(int(empresa.get("ativa") or 0))
        acao = "desativar" if ativa else "reativar"
        if not messagebox.askyesno(
            "Cadastro de Empresas",
            f"Deseja {acao} a empresa\n\n{empresa.get('nome')}?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            if ativa:
                self.servico.desativar(int(empresa["id"]))
            else:
                self.servico.reativar(int(empresa["id"]))
        except Exception as exc:
            messagebox.showerror("Cadastro de Empresas", str(exc), parent=self.winfo_toplevel())
            return
        self._apos_alterar()

    def _sincronizar(self) -> None:
        self.servico.migrar_dados_legados()
        self.servico.sincronizar_integracoes()
        self.atualizar()
        if self.ao_alterar:
            self.ao_alterar()
        messagebox.showinfo(
            "Cadastro de Empresas",
            "Integrações atualizadas. O cadastro central foi reaplicado aos módulos do FiscalPro.",
            parent=self.winfo_toplevel(),
        )

    def _apos_alterar(self) -> None:
        self.atualizar()
        if self.ao_alterar:
            self.ao_alterar()


class JanelaEmpresaCentral(Toplevel):
    def __init__(self, master, servico: CadastroEmpresasService, empresa=None, ao_salvar=None):
        super().__init__(master)
        self.servico = servico
        self.empresa = empresa
        self.ao_salvar = ao_salvar
        self.title("Editar empresa" if empresa else "Nova empresa")
        self.geometry("590x300")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()

        self.var_nome = StringVar(value=str(empresa.get("nome") or "") if empresa else "")
        self.var_cnpj = StringVar(value=PainelEmpresas._formatar_cnpj(empresa.get("cnpj")) if empresa else "")
        self.var_regime = StringVar(value=str(empresa.get("regime") or "A DEFINIR") if empresa else "A DEFINIR")
        self._montar()

    def _montar(self) -> None:
        corpo = ttk.Frame(self, padding=18, style="Page.TFrame")
        corpo.pack(fill=BOTH, expand=True)
        corpo.columnconfigure(1, weight=1)

        ttk.Label(corpo, text="Nome / Razão social").grid(row=0, column=0, sticky="w", pady=8)
        self.ent_nome = ttk.Entry(corpo, textvariable=self.var_nome)
        self.ent_nome.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=8)

        ttk.Label(corpo, text="CNPJ").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(corpo, textvariable=self.var_cnpj).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=8)

        ttk.Label(corpo, text="Regime tributário").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Combobox(
            corpo,
            textvariable=self.var_regime,
            values=self.servico.REGIMES,
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=8)

        if self.empresa:
            nomes_base = {nome.casefold() for nome, _ in self.servico.EMPRESAS_BASE}
            if str(self.empresa.get("nome") or "").casefold() in nomes_base:
                self.ent_nome.configure(state="readonly")
                ttk.Label(
                    corpo,
                    text="Empresa-base: o nome é protegido; CNPJ e regime podem ser atualizados.",
                    style="CardSubtitle.TLabel",
                ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 6))

        botoes = ttk.Frame(corpo, style="Page.TFrame")
        botoes.grid(row=4, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side=LEFT, padx=(0, 6))
        ttk.Button(botoes, text="Salvar empresa", command=self._salvar, style="Primary.TButton").pack(side=LEFT)

        self.bind("<Return>", lambda _e: self._salvar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.ent_nome.focus_set()

    def _salvar(self) -> None:
        try:
            if self.empresa:
                self.servico.editar(
                    int(self.empresa["id"]),
                    self.var_nome.get(),
                    self.var_cnpj.get(),
                    self.var_regime.get(),
                )
            else:
                self.servico.cadastrar(self.var_nome.get(), self.var_cnpj.get(), self.var_regime.get())
        except Exception as exc:
            messagebox.showerror("Cadastro de Empresas", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Cadastro de Empresas",
            "Empresa atualizada com sucesso." if self.empresa else "Empresa cadastrada com sucesso.",
            parent=self,
        )
        if self.ao_salvar:
            self.ao_salvar()
        self.destroy()
