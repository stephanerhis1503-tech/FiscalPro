from __future__ import annotations

from pathlib import Path
from typing import Iterable


class ErroLeituraSPED(RuntimeError):
    """Erro ocorrido durante a leitura de um arquivo SPED."""


class LeitorSPEDUnificado:
    """Lê arquivos SPED preservando cada linha exatamente como foi encontrada."""

    ENCODINGS = ("utf-8-sig", "latin-1", "cp1252")

    def ler(self, caminho: str | Path) -> tuple[list[str], str]:
        arquivo = Path(caminho)
        if not arquivo.exists():
            raise FileNotFoundError(f"Arquivo SPED não encontrado: {arquivo}")
        if not arquivo.is_file():
            raise ErroLeituraSPED(f"O caminho informado não é um arquivo: {arquivo}")

        ultimo_erro: Exception | None = None
        for encoding in self.ENCODINGS:
            try:
                with arquivo.open("r", encoding=encoding, newline="") as stream:
                    return stream.readlines(), encoding
            except UnicodeDecodeError as erro:
                ultimo_erro = erro

        raise ErroLeituraSPED(
            f"Não foi possível identificar a codificação do arquivo {arquivo.name}."
        ) from ultimo_erro

    @staticmethod
    def iterar_registros(linhas: Iterable[str]):
        for numero_linha, linha in enumerate(linhas, start=1):
            texto = linha.rstrip("\r\n")
            if not texto.startswith("|"):
                continue
            campos = texto.split("|")
            if len(campos) < 3 or not campos[1]:
                continue
            yield numero_linha, campos[1].upper(), campos
