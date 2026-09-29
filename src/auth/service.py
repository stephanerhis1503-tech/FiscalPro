"""Regras de autenticação e recuperação do FiscalPro."""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import ResultadoAutenticacao, SessaoUsuario
from .repository import RepositorioUsuarios
from .security import (
    ITERACOES_PADRAO,
    comparar_hash,
    derivar_hash,
    gerar_codigo_recuperacao,
    gerar_sal,
    normalizar_codigo_recuperacao,
)

MAX_TENTATIVAS = 5
SEGUNDOS_BLOQUEIO = 30


class ServicoAutenticacao:
    def __init__(self, repositorio: RepositorioUsuarios | None = None):
        self.repositorio = repositorio or RepositorioUsuarios()

    def preparar(self) -> None:
        self.repositorio.preparar()

    def possui_usuario(self) -> bool:
        return self.repositorio.possui_usuario()

    @staticmethod
    def _normalizar_usuario(usuario: str) -> str:
        return " ".join((usuario or "").strip().lower().split())

    @staticmethod
    def _validar_nome_usuario(nome: str, usuario: str) -> str | None:
        if len((nome or "").strip()) < 2:
            return "Informe o nome do responsável pelo acesso."
        if len((usuario or "").strip()) < 3:
            return "O usuário precisa ter pelo menos 3 caracteres."
        if any(ch.isspace() for ch in (usuario or "").strip()):
            return "O usuário não pode conter espaços."
        return None

    @staticmethod
    def _validar_senha(senha: str, confirmacao: str | None = None) -> str | None:
        if len(senha or "") < 8:
            return "A senha precisa ter pelo menos 8 caracteres."
        if confirmacao is not None and senha != confirmacao:
            return "A confirmação da senha não confere."
        return None

    def criar_primeiro_acesso(
        self,
        *,
        nome: str,
        usuario: str,
        senha: str,
        confirmacao: str,
    ) -> tuple[ResultadoAutenticacao, str | None]:
        self.preparar()
        if self.possui_usuario():
            return ResultadoAutenticacao(False, "O primeiro acesso já foi configurado."), None

        erro = self._validar_nome_usuario(nome, usuario) or self._validar_senha(senha, confirmacao)
        if erro:
            return ResultadoAutenticacao(False, erro), None

        usuario_norm = self._normalizar_usuario(usuario)
        senha_salt = gerar_sal()
        recovery_salt = gerar_sal()
        codigo = gerar_codigo_recuperacao()
        codigo_norm = normalizar_codigo_recuperacao(codigo)

        try:
            usuario_id = self.repositorio.criar_administrador(
                nome=nome.strip(),
                usuario=usuario_norm,
                senha_hash=derivar_hash(senha, senha_salt, ITERACOES_PADRAO),
                senha_salt=senha_salt,
                iteracoes=ITERACOES_PADRAO,
                recovery_hash=derivar_hash(codigo_norm, recovery_salt, ITERACOES_PADRAO),
                recovery_salt=recovery_salt,
            )
        except Exception as erro_db:
            return ResultadoAutenticacao(False, f"Não foi possível criar o acesso: {erro_db}"), None

        sessao = SessaoUsuario(usuario_id, nome.strip(), usuario_norm, "ADMINISTRADOR")
        self.repositorio.registrar_sucesso(usuario_id)
        return ResultadoAutenticacao(True, "Acesso criado com sucesso.", sessao), codigo

    def autenticar(self, usuario: str, senha: str) -> ResultadoAutenticacao:
        self.preparar()
        usuario_norm = self._normalizar_usuario(usuario)
        if not usuario_norm or not senha:
            return ResultadoAutenticacao(False, "Informe o usuário e a senha.")

        linha = self.repositorio.buscar_por_usuario(usuario_norm)
        if linha is None or not int(linha["ativo"]):
            return ResultadoAutenticacao(False, "Usuário ou senha incorretos.")

        agora = datetime.now()
        bloqueado_ate_txt = linha["bloqueado_ate"]
        if bloqueado_ate_txt:
            try:
                bloqueado_ate = datetime.fromisoformat(str(bloqueado_ate_txt))
            except ValueError:
                bloqueado_ate = agora
            if bloqueado_ate > agora:
                restante = max(1, int((bloqueado_ate - agora).total_seconds()))
                return ResultadoAutenticacao(
                    False,
                    f"Acesso temporariamente bloqueado. Aguarde {restante} segundos.",
                    segundos_bloqueio=restante,
                )

        senha_ok = comparar_hash(
            senha,
            bytes(linha["senha_salt"]),
            bytes(linha["senha_hash"]),
            int(linha["iteracoes"]),
        )
        if not senha_ok:
            tentativas = int(linha["tentativas"] or 0) + 1
            bloqueado_ate: str | None = None
            mensagem = "Usuário ou senha incorretos."
            if tentativas >= MAX_TENTATIVAS:
                bloqueio = agora + timedelta(seconds=SEGUNDOS_BLOQUEIO)
                bloqueado_ate = bloqueio.isoformat(timespec="seconds")
                tentativas = 0
                mensagem = f"Muitas tentativas. Acesso bloqueado por {SEGUNDOS_BLOQUEIO} segundos."
            self.repositorio.registrar_falha(int(linha["id"]), tentativas, bloqueado_ate)
            return ResultadoAutenticacao(False, mensagem)

        usuario_id = int(linha["id"])
        self.repositorio.registrar_sucesso(usuario_id)
        sessao = SessaoUsuario(
            usuario_id,
            str(linha["nome"]),
            str(linha["usuario"]),
            str(linha["perfil"]),
        )
        return ResultadoAutenticacao(True, "Acesso autorizado.", sessao)

    def alterar_senha(
        self,
        *,
        sessao: SessaoUsuario,
        senha_atual: str,
        nova_senha: str,
        confirmacao: str,
    ) -> ResultadoAutenticacao:
        erro = self._validar_senha(nova_senha, confirmacao)
        if erro:
            return ResultadoAutenticacao(False, erro)
        if senha_atual == nova_senha:
            return ResultadoAutenticacao(False, "A nova senha precisa ser diferente da atual.")

        atual = self.autenticar(sessao.usuario, senha_atual)
        if not atual.sucesso:
            return ResultadoAutenticacao(False, "A senha atual está incorreta.")

        sal = gerar_sal()
        self.repositorio.atualizar_senha(
            sessao.id,
            senha_hash=derivar_hash(nova_senha, sal, ITERACOES_PADRAO),
            senha_salt=sal,
            iteracoes=ITERACOES_PADRAO,
        )
        return ResultadoAutenticacao(True, "Senha alterada com sucesso.", sessao)

    def redefinir_com_recuperacao(
        self,
        *,
        usuario: str,
        codigo: str,
        nova_senha: str,
        confirmacao: str,
    ) -> tuple[ResultadoAutenticacao, str | None]:
        erro = self._validar_senha(nova_senha, confirmacao)
        if erro:
            return ResultadoAutenticacao(False, erro), None

        linha = self.repositorio.buscar_por_usuario(self._normalizar_usuario(usuario))
        if linha is None or not int(linha["ativo"]):
            return ResultadoAutenticacao(False, "Usuário ou código de recuperação inválido."), None

        codigo_norm = normalizar_codigo_recuperacao(codigo)
        if not codigo_norm or not comparar_hash(
            codigo_norm,
            bytes(linha["recovery_salt"]),
            bytes(linha["recovery_hash"]),
            int(linha["iteracoes"]),
        ):
            return ResultadoAutenticacao(False, "Usuário ou código de recuperação inválido."), None

        senha_salt = gerar_sal()
        recovery_salt = gerar_sal()
        novo_codigo = gerar_codigo_recuperacao()
        self.repositorio.atualizar_senha(
            int(linha["id"]),
            senha_hash=derivar_hash(nova_senha, senha_salt, ITERACOES_PADRAO),
            senha_salt=senha_salt,
            iteracoes=ITERACOES_PADRAO,
            recovery_hash=derivar_hash(
                normalizar_codigo_recuperacao(novo_codigo),
                recovery_salt,
                ITERACOES_PADRAO,
            ),
            recovery_salt=recovery_salt,
        )
        return ResultadoAutenticacao(True, "Senha redefinida com sucesso."), novo_codigo
