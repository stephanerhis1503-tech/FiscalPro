from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

from src.backup.service import ServicoBackup


def _criar_banco(caminho: Path, valor: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(caminho) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS marcador(valor TEXT)")
        conn.execute("DELETE FROM marcador")
        conn.execute("INSERT INTO marcador(valor) VALUES (?)", (valor,))
        conn.commit()


def _ler_banco(caminho: Path) -> str:
    with sqlite3.connect(caminho) as conn:
        return str(conn.execute("SELECT valor FROM marcador").fetchone()[0])


def test_backup_inclui_toda_pasta_dados_e_restaura_modulos(tmp_path: Path) -> None:
    raiz = tmp_path / "FiscalProDados"
    backups = tmp_path / "backups_externos"

    fiscal = raiz / "fiscalpro.db"
    financeiro = raiz / "dados" / "financeiro" / "contas_pagar.db"
    entregas = raiz / "dados" / "entregas" / "controle_entregas.db"
    futuro = raiz / "dados" / "modulo_futuro" / "dados.db"
    tributacao = raiz / "dados" / "tributacao.db"

    for banco, valor in (
        (fiscal, "fiscal-original"),
        (financeiro, "financeiro-original"),
        (entregas, "entregas-original"),
        (futuro, "futuro-original"),
        (tributacao, "tributacao-original"),
    ):
        _criar_banco(banco, valor)

    config_robo = raiz / "dados" / "robo_email" / "config.json"
    config_robo.parent.mkdir(parents=True, exist_ok=True)
    config_robo.write_text(json.dumps({"teste": "original"}), encoding="utf-8")

    preferencias = raiz / "dados" / "seguranca" / "preferencias_login.json"
    preferencias.parent.mkdir(parents=True, exist_ok=True)
    preferencias.write_text('{"lembrar": true}', encoding="utf-8")

    base_oficial = raiz / "dados" / "bases_oficiais" / "base.json.gz"
    base_oficial.parent.mkdir(parents=True, exist_ok=True)
    base_oficial.write_bytes(b"base-oficial")

    servico = ServicoBackup(raiz_dados=raiz, pasta_backups=backups)
    resultado = servico.criar_backup(tipo="manual", incluir_documentos=False)

    with zipfile.ZipFile(resultado.caminho, "r") as pacote:
        nomes = set(pacote.namelist())

    esperados = {
        "dados_app/fiscalpro.db",
        "dados_app/dados/financeiro/contas_pagar.db",
        "dados_app/dados/entregas/controle_entregas.db",
        "dados_app/dados/modulo_futuro/dados.db",
        "dados_app/dados/tributacao.db",
        "dados_app/dados/robo_email/config.json",
        "dados_app/dados/seguranca/preferencias_login.json",
        "dados_app/dados/bases_oficiais/base.json.gz",
    }
    assert esperados <= nomes

    # Altera os dados depois do backup e comprova a restauração completa.
    for banco in (fiscal, financeiro, entregas, futuro, tributacao):
        _criar_banco(banco, "alterado")
    config_robo.write_text('{"teste": "alterado"}', encoding="utf-8")
    preferencias.write_text('{"lembrar": false}', encoding="utf-8")
    base_oficial.write_bytes(b"alterada")

    restaurado = servico.restaurar_backup(
        resultado.caminho,
        criar_backup_seguranca=False,
    )

    assert restaurado["arquivos_restaurados"] >= len(esperados)
    assert _ler_banco(fiscal) == "fiscal-original"
    assert _ler_banco(financeiro) == "financeiro-original"
    assert _ler_banco(entregas) == "entregas-original"
    assert _ler_banco(futuro) == "futuro-original"
    assert _ler_banco(tributacao) == "tributacao-original"
    assert json.loads(config_robo.read_text(encoding="utf-8"))["teste"] == "original"
    assert json.loads(preferencias.read_text(encoding="utf-8"))["lembrar"] is True
    assert base_oficial.read_bytes() == b"base-oficial"


def test_backup_nao_empacota_wal_shm_tmp_lock(tmp_path: Path) -> None:
    raiz = tmp_path / "FiscalProDados"
    dados = raiz / "dados" / "financeiro"
    dados.mkdir(parents=True, exist_ok=True)
    (raiz / "fiscalpro.db").write_bytes(b"nao-sqlite")
    (dados / "arquivo.txt").write_text("ok", encoding="utf-8")
    for nome in ("contas_pagar.db-wal", "contas_pagar.db-shm", "teste.tmp", "teste.lock"):
        (dados / nome).write_text("temporario", encoding="utf-8")

    servico = ServicoBackup(raiz_dados=raiz, pasta_backups=tmp_path / "backups")
    resultado = servico.criar_backup(tipo="manual")
    with zipfile.ZipFile(resultado.caminho, "r") as pacote:
        nomes = set(pacote.namelist())

    assert "dados_app/dados/financeiro/arquivo.txt" in nomes
    assert all(not nome.endswith(("-wal", "-shm", ".tmp", ".lock")) for nome in nomes)
