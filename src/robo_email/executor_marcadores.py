"""Executor contínuo do classificador de marcadores do Gmail."""

from __future__ import annotations

import argparse
import time
from datetime import datetime

from .config import ConfiguracaoRoboEmail
from .servico import RoboEmailService


def _log(texto: str) -> None:
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{agora}] {texto}", flush=True)


def executar_uma_vez() -> int:
    configuracao = ConfiguracaoRoboEmail.carregar()
    servico = RoboEmailService(configuracao, log=_log)
    resultado = servico.classificar_marcadores()
    _log(
        "Classificação concluída: "
        f"{resultado.marcadores_aplicados} marcador(es) aplicado(s), "
        f"{resultado.mensagens_sem_classificacao} sem classificação segura, "
        f"{resultado.erros} erro(s)."
    )
    return 1 if resultado.erros else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classifica e-mails do Robô FiscalPro com marcadores do Gmail."
    )
    parser.add_argument(
        "--intervalo",
        type=int,
        default=60,
        help="Segundos entre verificações no modo contínuo (padrão: 60).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa uma única verificação e encerra.",
    )
    args = parser.parse_args()

    if args.once:
        return executar_uma_vez()

    intervalo = max(30, int(args.intervalo))
    _log(
        "Classificador de marcadores iniciado. "
        f"Nova verificação a cada {intervalo} segundos. "
        "Feche esta janela para parar."
    )
    while True:
        try:
            executar_uma_vez()
        except KeyboardInterrupt:
            _log("Classificador encerrado pela usuária.")
            return 0
        except Exception as erro:
            _log(f"ERRO: {erro}")
        time.sleep(intervalo)


if __name__ == "__main__":
    raise SystemExit(main())
