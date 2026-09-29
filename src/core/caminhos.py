"""Caminhos de execução, dados e recursos do FiscalPro.

Na execução pelo código-fonte, os bancos continuam na pasta atual do projeto.
No executável instalado, dados do usuário ficam em ``%LOCALAPPDATA%\\FiscalPro``
e não são misturados aos arquivos internos gerados pelo PyInstaller.

Hotfix 17.8.3: todos os módulos passam a compartilhar os caminhos persistentes
centralizados neste arquivo. A migração também recupera bancos financeiros e de
entregas de instalações antigas/versionadas, sem sobrescrever uma base atual
que já contenha registros.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

NOME_PASTA_DADOS = "FiscalPro"


def esta_empacotado() -> bool:
    return bool(getattr(sys, "frozen", False))


def pasta_codigo() -> Path:
    """Pasta dos arquivos empacotados ou raiz do projeto em desenvolvimento."""

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass).resolve()
    return Path(__file__).resolve().parents[2]


def pasta_executavel() -> Path:
    if esta_empacotado():
        return Path(sys.executable).resolve().parent
    return pasta_codigo()


def pasta_dados() -> Path:
    """Raiz gravável dos dados persistentes do usuário."""

    sobrescrita = os.environ.get("FISCALPRO_DATA_DIR", "").strip()
    if sobrescrita:
        return Path(sobrescrita).expanduser().resolve()

    if not esta_empacotado():
        # Preserva integralmente o comportamento das versões já aprovadas.
        return pasta_codigo()

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / NOME_PASTA_DADOS

    return Path.home() / ".local" / "share" / NOME_PASTA_DADOS


def pasta_recursos() -> Path:
    return pasta_codigo()


RAIZ_DADOS = pasta_dados()
PASTA_DADOS_INTERNOS = RAIZ_DADOS / "dados"
PASTA_SEGURANCA = PASTA_DADOS_INTERNOS / "seguranca"
PASTA_ROBO_EMAIL = PASTA_DADOS_INTERNOS / "robo_email"
PASTA_FINANCEIRO = PASTA_DADOS_INTERNOS / "financeiro"
PASTA_ENTREGAS = PASTA_DADOS_INTERNOS / "entregas"
PASTA_LOGS = RAIZ_DADOS / "logs"
PASTA_BACKUPS = RAIZ_DADOS / "backups"
BANCO_FISCAL = RAIZ_DADOS / "fiscalpro.db"
BANCO_TRIBUTACAO = PASTA_DADOS_INTERNOS / "tributacao.db"
BANCO_FINANCEIRO = PASTA_FINANCEIRO / "contas_pagar.db"
BANCO_ENTREGAS = PASTA_ENTREGAS / "controle_entregas.db"


def _eh_banco_sqlite(caminho: Path) -> bool:
    try:
        with caminho.open("rb") as arquivo:
            return arquivo.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _copiar_banco_sqlite(origem: Path, destino: Path) -> None:
    """Cria snapshot consistente de um SQLite, incluindo páginas ainda no WAL."""

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.name + ".migrando")
    temporario.unlink(missing_ok=True)
    fonte: sqlite3.Connection | None = None
    alvo: sqlite3.Connection | None = None
    try:
        uri = origem.resolve().as_uri() + "?mode=ro"
        fonte = sqlite3.connect(uri, uri=True, timeout=30, cached_statements=0)
        alvo = sqlite3.connect(temporario, timeout=30, cached_statements=0)
        fonte.backup(alvo, pages=256, sleep=0.02)
        alvo.commit()
        alvo.close()
        alvo = None
        fonte.close()
        fonte = None
        os.replace(temporario, destino)
    finally:
        if alvo is not None:
            alvo.close()
        if fonte is not None:
            fonte.close()
        temporario.unlink(missing_ok=True)


def _arquivo_transitorio(arquivo: Path) -> bool:
    nome = arquivo.name.casefold()
    return nome.endswith(("-wal", "-shm", ".tmp", ".lock", ".migrando"))


def _copiar_arquivo_se_ausente(origem: Path, destino: Path) -> bool:
    if destino.exists() or not origem.is_file() or _arquivo_transitorio(origem):
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    if origem.suffix.casefold() == ".db" and _eh_banco_sqlite(origem):
        try:
            _copiar_banco_sqlite(origem, destino)
            return True
        except sqlite3.Error:
            # Compatibilidade com bases que não aceitem snapshot por alguma
            # particularidade antiga. A cópia simples continua sendo a última
            # alternativa, sem remover a origem.
            pass
    shutil.copy2(origem, destino)
    return True


def _copiar_pasta_se_ausente(origem: Path, destino: Path) -> int:
    if not origem.is_dir():
        return 0
    copiados = 0
    for arquivo in origem.rglob("*"):
        if not arquivo.is_file() or _arquivo_transitorio(arquivo):
            continue
        relativo = arquivo.relative_to(origem)
        alvo = destino / relativo
        if _copiar_arquivo_se_ausente(arquivo, alvo):
            copiados += 1
    return copiados


def _mtime_seguro(caminho: Path) -> float:
    try:
        return caminho.stat().st_mtime
    except OSError:
        return 0.0


def _pastas_legacy() -> list[Path]:
    """Localiza instalações antigas, inclusive pastas versionadas ``FiscalPro_*``."""

    candidatas: list[Path] = []

    informada = os.environ.get("FISCALPRO_LEGACY_DIR", "").strip()
    if informada:
        candidatas.append(Path(informada).expanduser())

    if os.name == "nt":
        unidade = Path(os.environ.get("SystemDrive", "C:") + "\\")
        try:
            pastas_raiz = [p for p in unidade.glob("FiscalPro*") if p.is_dir()]
            pastas_raiz.sort(key=_mtime_seguro, reverse=True)
            candidatas.extend(pastas_raiz)
        except OSError:
            candidatas.append(unidade / "FiscalPro")

        # Algumas instalações de desenvolvimento foram mantidas no Desktop/OneDrive.
        candidatas.extend(
            (
                Path.home() / "OneDrive" / "Desktop" / "FiscalPro" / "FiscalPro",
                Path.home() / "OneDrive" / "Desktop" / "FiscalPro",
            )
        )

    candidatas.extend((Path.home() / "FiscalPro", Path.cwd()))

    unicas: list[Path] = []
    try:
        destino_resolvido = RAIZ_DADOS.resolve()
    except OSError:
        destino_resolvido = RAIZ_DADOS

    for pasta in candidatas:
        try:
            resolvida = pasta.resolve()
        except OSError:
            continue
        if resolvida == destino_resolvido or resolvida in unicas:
            continue
        unicas.append(resolvida)
    return unicas


def _resumo_tabela_sqlite(
    caminho: Path,
    tabela: str,
    coluna_atualizacao: str = "atualizado_em",
) -> tuple[int, str] | None:
    if not caminho.is_file() or not _eh_banco_sqlite(caminho):
        return None
    conexao: sqlite3.Connection | None = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10, cached_statements=0)
        existe = conexao.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (tabela,),
        ).fetchone()
        if not existe:
            return None
        quantidade = int(conexao.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0])
        colunas = {
            str(linha[1])
            for linha in conexao.execute(f'PRAGMA table_info("{tabela}")').fetchall()
        }
        ultimo = ""
        if coluna_atualizacao in colunas:
            ultimo = str(
                conexao.execute(
                    f'SELECT COALESCE(MAX("{coluna_atualizacao}"), \'\') FROM "{tabela}"'
                ).fetchone()[0]
                or ""
            )
        return quantidade, ultimo
    except sqlite3.Error:
        return None
    finally:
        if conexao is not None:
            conexao.close()


def contar_contas_pagar(caminho: str | Path = BANCO_FINANCEIRO) -> int | None:
    resumo = _resumo_tabela_sqlite(Path(caminho), "contas_pagar")
    return resumo[0] if resumo is not None else None


def localizar_melhor_banco_financeiro_legacy() -> tuple[Path, int] | None:
    """Retorna a base antiga com dados financeiros mais recentes conhecida."""

    candidatos: list[tuple[tuple[str, float, int], Path, int]] = []
    for pasta in _pastas_legacy():
        banco = pasta / "dados" / "financeiro" / "contas_pagar.db"
        resumo = _resumo_tabela_sqlite(banco, "contas_pagar")
        if resumo is None or resumo[0] <= 0:
            continue
        quantidade, ultimo = resumo
        candidatos.append(((ultimo, _mtime_seguro(banco), quantidade), banco, quantidade))

    if not candidatos:
        return None
    _, banco, quantidade = max(candidatos, key=lambda item: item[0])
    return banco, quantidade


def _localizar_melhor_banco_legacy(
    relativo: Path,
    tabela: str,
) -> tuple[Path, int] | None:
    candidatos: list[tuple[tuple[str, float, int], Path, int]] = []
    for pasta in _pastas_legacy():
        banco = pasta / relativo
        resumo = _resumo_tabela_sqlite(banco, tabela)
        if resumo is None or resumo[0] <= 0:
            continue
        quantidade, ultimo = resumo
        candidatos.append(((ultimo, _mtime_seguro(banco), quantidade), banco, quantidade))
    if not candidatos:
        return None
    _, banco, quantidade = max(candidatos, key=lambda item: item[0])
    return banco, quantidade


def _backup_antes_migracao(destino: Path) -> Path | None:
    if not destino.is_file():
        return None
    sufixo = datetime.now().strftime("%Y%m%d_%H%M%S")
    copia = destino.with_name(f"{destino.name}.ANTES_MIGRACAO_17_8_3_{sufixo}.bak")
    shutil.copy2(destino, copia)
    return copia


def _recuperar_banco_se_vazio(
    destino: Path,
    relativo_legacy: Path,
    tabela: str,
) -> tuple[Path, int] | None:
    atual = _resumo_tabela_sqlite(destino, tabela)
    if atual is not None and atual[0] > 0:
        return None

    encontrado = _localizar_melhor_banco_legacy(relativo_legacy, tabela)
    if encontrado is None:
        return None
    origem, quantidade = encontrado

    if destino.is_file():
        _backup_antes_migracao(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if _eh_banco_sqlite(origem):
        _copiar_banco_sqlite(origem, destino)
    else:
        shutil.copy2(origem, destino)

    conferido = _resumo_tabela_sqlite(destino, tabela)
    if conferido is None or conferido[0] != quantidade:
        raise RuntimeError(f"Falha ao migrar o banco {destino.name} com segurança.")
    return origem, quantidade


def migrar_dados_legacy() -> list[str]:
    """Migra dados persistentes de instalações anteriores para o AppData.

    A partir do Hotfix 17.8.3, toda a pasta ``dados`` é considerada, incluindo
    Contas a Pagar e Controle de Entregas. Bancos SQLite são copiados por
    snapshot para incorporar alterações existentes no WAL. Se uma instalação
    anterior deixou um ``contas_pagar.db`` vazio no AppData, ele só é substituído
    quando uma base antiga com registros reais é encontrada; antes disso é
    preservada uma cópia ``ANTES_MIGRACAO``.
    """

    if not esta_empacotado():
        return []

    migrados: list[str] = []
    for antiga in _pastas_legacy():
        if not antiga.is_dir():
            continue

        if _copiar_arquivo_se_ausente(antiga / "fiscalpro.db", BANCO_FISCAL):
            migrados.append("banco fiscal")

        quantidade = _copiar_pasta_se_ausente(
            antiga / "dados", PASTA_DADOS_INTERNOS
        )
        if quantidade:
            migrados.append(f"dados internos ({quantidade} arquivo(s))")

    recuperado = _recuperar_banco_se_vazio(
        BANCO_FINANCEIRO,
        Path("dados") / "financeiro" / "contas_pagar.db",
        "contas_pagar",
    )
    if recuperado is not None:
        _, quantidade = recuperado
        migrados.append(f"Contas a Pagar recuperadas ({quantidade} registro(s))")

    recuperado_entregas = _recuperar_banco_se_vazio(
        BANCO_ENTREGAS,
        Path("dados") / "entregas" / "controle_entregas.db",
        "entregas_arquivos",
    )
    if recuperado_entregas is not None:
        _, quantidade = recuperado_entregas
        migrados.append(f"Controle de Entregas recuperado ({quantidade} registro(s))")

    return migrados


def instalar_bases_iniciais() -> list[str]:
    """Instala bases limpas quando não houver dados anteriores para migrar."""

    templates = pasta_recursos() / "templates"
    instaladas: list[str] = []
    if _copiar_arquivo_se_ausente(
        templates / "fiscalpro_base.db", BANCO_FISCAL
    ):
        instaladas.append("base fiscal inicial")
    if _copiar_arquivo_se_ausente(
        templates / "tributacao_base.db", BANCO_TRIBUTACAO
    ):
        instaladas.append("base tributária inicial")
    return instaladas


def preparar_ambiente() -> dict[str, list[str]]:
    """Cria a estrutura gravável e prepara a migração da versão em código."""

    for pasta in (
        RAIZ_DADOS,
        PASTA_DADOS_INTERNOS,
        PASTA_SEGURANCA,
        PASTA_ROBO_EMAIL,
        PASTA_FINANCEIRO,
        PASTA_ENTREGAS,
        PASTA_LOGS,
        PASTA_BACKUPS,
    ):
        pasta.mkdir(parents=True, exist_ok=True)

    migrados = migrar_dados_legacy()
    instaladas = instalar_bases_iniciais()

    # Mantém caminhos relativos previsíveis para componentes antigos.
    try:
        os.chdir(pasta_executavel())
    except OSError:
        pass

    return {"migrados": migrados, "instaladas": instaladas}
