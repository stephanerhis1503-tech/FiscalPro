"""Tela de login e primeiro acesso do FiscalPro.

Sprint 15.3 — Identidade visual completa.
"""

from __future__ import annotations

from tkinter import BOTH, LEFT, RIGHT, X, BooleanVar, Frame, Label, StringVar, Tk, Toplevel
from tkinter import messagebox, ttk

from src.auth.models import SessaoUsuario
from src.auth.preferences import PreferenciasLogin
from src.auth.service import ServicoAutenticacao
from src.core.app_info import VERSAO_APP

from .estilos import (
    COR_BORDA,
    COR_CARD,
    COR_DESTAQUE,
    COR_FUNDO,
    COR_PRIMARIA,
    COR_SECUNDARIA,
    COR_TEXTO,
    COR_TEXTO_CLARO,
    COR_TEXTO_SUAVE,
    configurar_tema,
)
from .recursos import aplicar_icone, carregar_imagem


def _centralizar(janela, largura: int, altura: int) -> None:
    janela.update_idletasks()
    tela_largura = janela.winfo_screenwidth()
    tela_altura = janela.winfo_screenheight()
    x = max(0, (tela_largura - largura) // 2)
    y = max(0, (tela_altura - altura) // 2)
    janela.geometry(f"{largura}x{altura}+{x}+{y}")


class JanelaLogin:
    def __init__(
        self,
        servico: ServicoAutenticacao | None = None,
        preferencias: PreferenciasLogin | None = None,
    ):
        self.servico = servico or ServicoAutenticacao()
        self.preferencias = preferencias or PreferenciasLogin()
        self.servico.preparar()

        self.janela = Tk()
        self.janela.title("FiscalPro | Acesso")
        self.janela.resizable(False, False)
        configurar_tema(self.janela)
        aplicar_icone(self.janela)
        _centralizar(self.janela, 980, 680)
        self.janela.protocol("WM_DELETE_WINDOW", self._fechar)

        self.sessao: SessaoUsuario | None = None
        self.modo = "cadastro" if not self.servico.possui_usuario() else "login"
        self.var_mensagem = StringVar(value="")
        self.var_mostrar_senha = BooleanVar(value=False)
        self.var_lembrar = BooleanVar(value=bool(self.preferencias.carregar_usuario()))

        self.area_formulario: Frame | None = None
        self.entries_senha: list[ttk.Entry] = []
        self.criar_interface()

    def criar_interface(self) -> None:
        externo = Frame(self.janela, bg=COR_FUNDO)
        externo.pack(fill=BOTH, expand=True)

        painel_marca = Frame(externo, bg=COR_PRIMARIA, width=390)
        painel_marca.pack(side=LEFT, fill="y")
        painel_marca.pack_propagate(False)

        marca = Frame(painel_marca, bg=COR_PRIMARIA)
        marca.pack(fill=X, padx=42, pady=(62, 0))

        self.logo_login = carregar_imagem(self.janela, "fiscalpro_mark_96.png")
        if self.logo_login is not None:
            Label(marca, image=self.logo_login, bg=COR_PRIMARIA, bd=0).pack(anchor="w")
        else:
            Label(
                marca,
                text="FP",
                bg=COR_DESTAQUE,
                fg="white",
                font=("Segoe UI", 22, "bold"),
                width=3,
                height=2,
                bd=0,
            ).pack(anchor="w")

        Label(
            marca,
            text="FiscalPro",
            bg=COR_PRIMARIA,
            fg="white",
            font=("Segoe UI", 31, "bold"),
        ).pack(anchor="w", pady=(22, 0))
        Label(
            marca,
            text="Assistente Fiscal Inteligente",
            bg=COR_PRIMARIA,
            fg="#DCEAF5",
            font=("Segoe UI", 13),
        ).pack(anchor="w", pady=(2, 0))

        Label(
            marca,
            text=(
                "Segurança para acessar suas consultas,\n"
                "documentos, SPED e automações em um\n"
                "único ambiente."
            ),
            bg=COR_PRIMARIA,
            fg="#EAF3F9",
            justify=LEFT,
            font=("Segoe UI", 11),
            pady=34,
        ).pack(anchor="w")

        recursos = [
            "● Senha protegida e criptografada",
            "● Bloqueio temporário após tentativas",
            "● Banco de acesso separado do banco fiscal",
        ]
        for texto in recursos:
            Label(
                marca,
                text=texto,
                bg=COR_PRIMARIA,
                fg="#CDE2F1",
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=5)

        Label(
            painel_marca,
            text=f"FiscalPro {VERSAO_APP} • Stephane Rhis + ChatGPT",
            bg=COR_SECUNDARIA,
            fg="#DCEAF5",
            font=("Segoe UI", 9),
            padx=42,
            pady=13,
        ).pack(side="bottom", fill=X)

        painel_form = Frame(externo, bg=COR_FUNDO)
        painel_form.pack(side=RIGHT, fill=BOTH, expand=True)

        self.area_formulario = Frame(
            painel_form,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=38,
            pady=30,
        )
        self.area_formulario.pack(fill=BOTH, expand=False, padx=50, pady=42)

        self._montar_modo_atual()

    def _limpar_formulario(self) -> None:
        assert self.area_formulario is not None
        for filho in self.area_formulario.winfo_children():
            filho.destroy()
        self.entries_senha.clear()
        self.var_mensagem.set("")
        self.var_mostrar_senha.set(False)

    def _titulo(self, titulo: str, subtitulo: str) -> None:
        assert self.area_formulario is not None
        Label(
            self.area_formulario,
            text=titulo,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        Label(
            self.area_formulario,
            text=subtitulo,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 10),
            wraplength=430,
            justify=LEFT,
        ).pack(anchor="w", pady=(4, 20))

    def _campo(self, rotulo: str, variavel: StringVar, *, senha: bool = False) -> ttk.Entry:
        assert self.area_formulario is not None
        Label(
            self.area_formulario,
            text=rotulo,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(8, 5))
        entrada = ttk.Entry(self.area_formulario, textvariable=variavel, font=("Segoe UI", 11))
        entrada.pack(fill=X, ipady=3)
        if senha:
            entrada.configure(show="•")
            self.entries_senha.append(entrada)
        return entrada

    def _mensagem(self) -> None:
        assert self.area_formulario is not None
        Label(
            self.area_formulario,
            textvariable=self.var_mensagem,
            bg=COR_CARD,
            fg="#B43240",
            font=("Segoe UI", 9),
            wraplength=430,
            justify=LEFT,
        ).pack(anchor="w", pady=(9, 0))

    def _alternar_senha(self) -> None:
        mostrar = bool(self.var_mostrar_senha.get())
        for entrada in self.entries_senha:
            entrada.configure(show="" if mostrar else "•")

    def _montar_modo_atual(self) -> None:
        self._limpar_formulario()
        if self.modo == "cadastro":
            self._montar_cadastro()
        elif self.modo == "recuperacao":
            self._montar_recuperacao()
        else:
            self._montar_login()

    def _montar_login(self) -> None:
        assert self.area_formulario is not None
        self._titulo("Bem-vinda de volta", "Entre com o usuário e a senha cadastrados no FiscalPro.")

        self.var_usuario = StringVar(value=self.preferencias.carregar_usuario())
        self.var_senha = StringVar()
        entrada_usuario = self._campo("Usuário", self.var_usuario)
        entrada_senha = self._campo("Senha", self.var_senha, senha=True)

        opcoes = Frame(self.area_formulario, bg=COR_CARD)
        opcoes.pack(fill=X, pady=(12, 2))
        ttk.Checkbutton(
            opcoes,
            text="Lembrar usuário",
            variable=self.var_lembrar,
            style="Card.TCheckbutton",
        ).pack(side=LEFT)
        ttk.Checkbutton(
            opcoes,
            text="Mostrar senha",
            variable=self.var_mostrar_senha,
            command=self._alternar_senha,
            style="Card.TCheckbutton",
        ).pack(side=RIGHT)

        self._mensagem()
        ttk.Button(
            self.area_formulario,
            text="Entrar no FiscalPro",
            command=self._entrar,
            style="Primary.TButton",
        ).pack(fill=X, pady=(18, 8))
        ttk.Button(
            self.area_formulario,
            text="Esqueci minha senha",
            command=lambda: self._trocar_modo("recuperacao"),
            style="Link.TButton",
        ).pack(anchor="center")

        entrada_usuario.bind("<Return>", lambda _e: entrada_senha.focus_set())
        entrada_senha.bind("<Return>", lambda _e: self._entrar())
        (entrada_senha if self.var_usuario.get() else entrada_usuario).focus_set()

    def _montar_cadastro(self) -> None:
        assert self.area_formulario is not None
        self._titulo(
            "Crie o primeiro acesso",
            "Esta configuração é feita uma única vez. O usuário criado será o administrador do FiscalPro.",
        )
        self.var_nome = StringVar(value="Stephane Rhis")
        self.var_usuario = StringVar(value="stephane")
        self.var_senha = StringVar()
        self.var_confirmacao = StringVar()

        entrada_nome = self._campo("Nome do responsável", self.var_nome)
        entrada_usuario = self._campo("Usuário", self.var_usuario)
        entrada_senha = self._campo("Senha (mínimo de 8 caracteres)", self.var_senha, senha=True)
        entrada_confirma = self._campo("Confirmar senha", self.var_confirmacao, senha=True)

        ttk.Checkbutton(
            self.area_formulario,
            text="Mostrar senhas",
            variable=self.var_mostrar_senha,
            command=self._alternar_senha,
            style="Card.TCheckbutton",
        ).pack(anchor="w", pady=(10, 0))
        self._mensagem()
        ttk.Button(
            self.area_formulario,
            text="Criar acesso e entrar",
            command=self._criar_acesso,
            style="Accent.TButton",
        ).pack(fill=X, pady=(17, 0))

        entrada_nome.bind("<Return>", lambda _e: entrada_usuario.focus_set())
        entrada_usuario.bind("<Return>", lambda _e: entrada_senha.focus_set())
        entrada_senha.bind("<Return>", lambda _e: entrada_confirma.focus_set())
        entrada_confirma.bind("<Return>", lambda _e: self._criar_acesso())
        entrada_nome.focus_set()

    def _montar_recuperacao(self) -> None:
        assert self.area_formulario is not None
        self._titulo(
            "Redefinir senha",
            "Use o código de recuperação entregue na criação do primeiro acesso.",
        )
        self.var_usuario = StringVar(value=self.preferencias.carregar_usuario())
        self.var_codigo = StringVar()
        self.var_senha = StringVar()
        self.var_confirmacao = StringVar()

        entrada_usuario = self._campo("Usuário", self.var_usuario)
        entrada_codigo = self._campo("Código de recuperação", self.var_codigo)
        entrada_senha = self._campo("Nova senha", self.var_senha, senha=True)
        entrada_confirma = self._campo("Confirmar nova senha", self.var_confirmacao, senha=True)

        ttk.Checkbutton(
            self.area_formulario,
            text="Mostrar senhas",
            variable=self.var_mostrar_senha,
            command=self._alternar_senha,
            style="Card.TCheckbutton",
        ).pack(anchor="w", pady=(10, 0))
        self._mensagem()
        ttk.Button(
            self.area_formulario,
            text="Redefinir senha",
            command=self._redefinir_senha,
            style="Primary.TButton",
        ).pack(fill=X, pady=(16, 7))
        ttk.Button(
            self.area_formulario,
            text="Voltar para o login",
            command=lambda: self._trocar_modo("login"),
            style="Link.TButton",
        ).pack(anchor="center")

        entrada_usuario.bind("<Return>", lambda _e: entrada_codigo.focus_set())
        entrada_codigo.bind("<Return>", lambda _e: entrada_senha.focus_set())
        entrada_senha.bind("<Return>", lambda _e: entrada_confirma.focus_set())
        entrada_confirma.bind("<Return>", lambda _e: self._redefinir_senha())
        (entrada_codigo if self.var_usuario.get() else entrada_usuario).focus_set()

    def _trocar_modo(self, modo: str) -> None:
        self.modo = modo
        self._montar_modo_atual()

    def _entrar(self) -> None:
        resultado = self.servico.autenticar(self.var_usuario.get(), self.var_senha.get())
        if not resultado.sucesso:
            self.var_mensagem.set(resultado.mensagem)
            return

        self.preferencias.salvar_usuario(self.var_usuario.get(), self.var_lembrar.get())
        self.sessao = resultado.sessao
        self.janela.destroy()

    def _criar_acesso(self) -> None:
        resultado, codigo = self.servico.criar_primeiro_acesso(
            nome=self.var_nome.get(),
            usuario=self.var_usuario.get(),
            senha=self.var_senha.get(),
            confirmacao=self.var_confirmacao.get(),
        )
        if not resultado.sucesso or resultado.sessao is None or not codigo:
            self.var_mensagem.set(resultado.mensagem)
            return

        self.preferencias.salvar_usuario(self.var_usuario.get(), True)
        self._mostrar_codigo_recuperacao(codigo, primeiro_acesso=True)
        self.sessao = resultado.sessao
        self.janela.destroy()

    def _redefinir_senha(self) -> None:
        resultado, novo_codigo = self.servico.redefinir_com_recuperacao(
            usuario=self.var_usuario.get(),
            codigo=self.var_codigo.get(),
            nova_senha=self.var_senha.get(),
            confirmacao=self.var_confirmacao.get(),
        )
        if not resultado.sucesso or not novo_codigo:
            self.var_mensagem.set(resultado.mensagem)
            return

        self._mostrar_codigo_recuperacao(novo_codigo, primeiro_acesso=False)
        messagebox.showinfo("FiscalPro", "Senha redefinida. Entre com a nova senha.", parent=self.janela)
        self._trocar_modo("login")

    def _mostrar_codigo_recuperacao(self, codigo: str, *, primeiro_acesso: bool) -> None:
        janela = Toplevel(self.janela)
        janela.title("FiscalPro | Código de recuperação")
        janela.resizable(False, False)
        janela.transient(self.janela)
        janela.grab_set()
        janela.configure(bg=COR_FUNDO)
        aplicar_icone(janela)
        _centralizar(janela, 520, 330)

        card = Frame(
            janela,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=28,
            pady=26,
        )
        card.pack(fill=BOTH, expand=True, padx=24, pady=24)

        titulo = "Primeiro acesso criado" if primeiro_acesso else "Novo código de recuperação"
        Label(card, text=titulo, bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 16, "bold")).pack()
        Label(
            card,
            text=(
                "Guarde este código em local seguro. Ele permite redefinir a senha e é exibido somente agora."
            ),
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            wraplength=420,
            justify="center",
            font=("Segoe UI", 10),
        ).pack(pady=(8, 20))

        var_codigo = StringVar(value=codigo)
        entrada = ttk.Entry(card, textvariable=var_codigo, justify="center", font=("Consolas", 17, "bold"))
        entrada.pack(fill=X, ipady=7)
        entrada.state(["readonly"])

        def copiar() -> None:
            janela.clipboard_clear()
            janela.clipboard_append(codigo)
            lbl_copiado.config(text="Código copiado.")

        ttk.Button(card, text="Copiar código", command=copiar, style="Secondary.TButton").pack(pady=(14, 4))
        lbl_copiado = Label(card, text="", bg=COR_CARD, fg="#2E7D32", font=("Segoe UI", 9))
        lbl_copiado.pack()
        ttk.Button(card, text="Já guardei o código", command=janela.destroy, style="Primary.TButton").pack(
            fill=X, pady=(10, 0)
        )
        janela.wait_window()

    def _fechar(self) -> None:
        self.sessao = None
        self.janela.destroy()

    def executar(self) -> SessaoUsuario | None:
        self.janela.mainloop()
        return self.sessao


class JanelaAlterarSenha:
    def __init__(
        self,
        master,
        servico: ServicoAutenticacao,
        sessao: SessaoUsuario,
    ):
        self.servico = servico
        self.sessao = sessao
        self.janela = Toplevel(master)
        self.janela.title("FiscalPro | Alterar senha")
        self.janela.resizable(False, False)
        self.janela.transient(master)
        self.janela.grab_set()
        self.janela.configure(bg=COR_FUNDO)
        aplicar_icone(self.janela)
        _centralizar(self.janela, 470, 460)

        self.var_atual = StringVar()
        self.var_nova = StringVar()
        self.var_confirmacao = StringVar()
        self.var_mostrar = BooleanVar(value=False)
        self.var_mensagem = StringVar(value="")
        self.entries: list[ttk.Entry] = []
        self._montar()

    def _montar(self) -> None:
        card = Frame(
            self.janela,
            bg=COR_CARD,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=30,
            pady=28,
        )
        card.pack(fill=BOTH, expand=True, padx=28, pady=28)
        Label(card, text="Alterar senha", bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 18, "bold")).pack(
            anchor="w"
        )
        Label(
            card,
            text=f"Usuário: {self.sessao.usuario}",
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 16))

        for rotulo, variavel in (
            ("Senha atual", self.var_atual),
            ("Nova senha", self.var_nova),
            ("Confirmar nova senha", self.var_confirmacao),
        ):
            Label(card, text=rotulo, bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 9, "bold")).pack(
                anchor="w", pady=(8, 5)
            )
            entrada = ttk.Entry(card, textvariable=variavel, show="•", font=("Segoe UI", 11))
            entrada.pack(fill=X, ipady=3)
            self.entries.append(entrada)

        ttk.Checkbutton(
            card,
            text="Mostrar senhas",
            variable=self.var_mostrar,
            command=self._alternar,
            style="Card.TCheckbutton",
        ).pack(anchor="w", pady=(10, 0))
        Label(
            card,
            textvariable=self.var_mensagem,
            bg=COR_CARD,
            fg="#B43240",
            font=("Segoe UI", 9),
            wraplength=380,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Button(card, text="Salvar nova senha", command=self._salvar, style="Primary.TButton").pack(
            fill=X, pady=(17, 0)
        )
        self.entries[0].focus_set()
        self.entries[-1].bind("<Return>", lambda _e: self._salvar())

    def _alternar(self) -> None:
        for entrada in self.entries:
            entrada.configure(show="" if self.var_mostrar.get() else "•")

    def _salvar(self) -> None:
        resultado = self.servico.alterar_senha(
            sessao=self.sessao,
            senha_atual=self.var_atual.get(),
            nova_senha=self.var_nova.get(),
            confirmacao=self.var_confirmacao.get(),
        )
        if not resultado.sucesso:
            self.var_mensagem.set(resultado.mensagem)
            return
        messagebox.showinfo("FiscalPro", resultado.mensagem, parent=self.janela)
        self.janela.destroy()
