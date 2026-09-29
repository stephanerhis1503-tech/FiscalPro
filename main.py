"""Ponto de entrada do FiscalPro.

Sprint 16.2.1 — relatório semanal do Contas a Pagar.
"""

from src.core.caminhos import preparar_ambiente

# Precisa ocorrer antes dos módulos que calculam caminhos de banco/configuração.
preparar_ambiente()

from src.auth.service import ServicoAutenticacao
from src.backup.service import ServicoBackup
from src.core.logger import logger
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository
from src.ui.janela_login import JanelaLogin
from src.ui.janela_principal import JanelaPrincipal


def main() -> None:
    # Proteção diária: cria no máximo um backup automático por dia, sem copiar
    # os documentos externos do Robô Fiscal para manter a operação leve.
    try:
        ServicoBackup().criar_backup_automatico_se_necessario()
    except Exception:
        logger.exception("Não foi possível criar o backup automático diário.")

    # Estruturas complementares da ficha tributária. A operação é segura e
    # repetível, sem substituir o banco fiscal do usuário.
    FichaTributariaRepository.preparar_banco()

    autenticacao = ServicoAutenticacao()
    autenticacao.preparar()

    while True:
        sessao = JanelaLogin(autenticacao).executar()
        if sessao is None:
            break

        acao = JanelaPrincipal(sessao=sessao, servico_autenticacao=autenticacao).executar()
        if acao not in {"logout", "reiniciar"}:
            break


if __name__ == "__main__":
    main()
