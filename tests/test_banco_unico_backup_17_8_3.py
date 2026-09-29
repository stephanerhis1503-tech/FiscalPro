from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from src.backup.service import BackupInvalidoError, ServicoBackup
from src.core import caminhos


def _criar_contas(caminho: Path, quantidade: int) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(caminho) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contas_pagar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL DEFAULT 'A VENCER',
                criado_em TEXT NOT NULL DEFAULT '',
                atualizado_em TEXT NOT NULL DEFAULT '',
                data_pagamento TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("DELETE FROM contas_pagar")
        for indice in range(quantidade):
            conn.execute(
                "INSERT INTO contas_pagar(status, criado_em, atualizado_em, data_pagamento) "
                "VALUES ('A VENCER', ?, ?, '')",
                (
                    f"2026-08-11T10:{indice:02d}:00",
                    f"2026-08-11T10:{indice:02d}:30",
                ),
            )
        conn.commit()


def _contar(caminho: Path, tabela: str = "contas_pagar") -> int:
    with sqlite3.connect(caminho) as conn:
        return int(conn.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0])


def _criar_entregas(caminho: Path, quantidade: int) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(caminho) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entregas_arquivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                atualizado_em TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("DELETE FROM entregas_arquivos")
        for indice in range(quantidade):
            conn.execute(
                "INSERT INTO entregas_arquivos(atualizado_em) VALUES (?)",
                (f"2026-08-11T11:{indice:02d}:00",),
            )
        conn.commit()


def test_migracao_recupera_financeiro_vazio_e_entregas(monkeypatch, tmp_path: Path) -> None:
    atual = tmp_path / "AppData" / "FiscalPro"
    legado = tmp_path / "FiscalPro_17_8_0"

    banco_atual = atual / "dados" / "financeiro" / "contas_pagar.db"
    banco_legado = legado / "dados" / "financeiro" / "contas_pagar.db"
    entregas_legado = legado / "dados" / "entregas" / "controle_entregas.db"

    _criar_contas(banco_atual, 0)
    _criar_contas(banco_legado, 7)
    _criar_entregas(entregas_legado, 2)

    monkeypatch.setattr(caminhos, "RAIZ_DADOS", atual)
    monkeypatch.setattr(caminhos, "PASTA_DADOS_INTERNOS", atual / "dados")
    monkeypatch.setattr(caminhos, "PASTA_SEGURANCA", atual / "dados" / "seguranca")
    monkeypatch.setattr(caminhos, "PASTA_ROBO_EMAIL", atual / "dados" / "robo_email")
    monkeypatch.setattr(caminhos, "PASTA_FINANCEIRO", atual / "dados" / "financeiro")
    monkeypatch.setattr(caminhos, "PASTA_ENTREGAS", atual / "dados" / "entregas")
    monkeypatch.setattr(caminhos, "BANCO_FISCAL", atual / "fiscalpro.db")
    monkeypatch.setattr(caminhos, "BANCO_TRIBUTACAO", atual / "dados" / "tributacao.db")
    monkeypatch.setattr(caminhos, "BANCO_FINANCEIRO", banco_atual)
    monkeypatch.setattr(
        caminhos,
        "BANCO_ENTREGAS",
        atual / "dados" / "entregas" / "controle_entregas.db",
    )
    monkeypatch.setattr(caminhos, "esta_empacotado", lambda: True)
    monkeypatch.setattr(caminhos, "_pastas_legacy", lambda: [legado])

    migrados = caminhos.migrar_dados_legacy()

    assert _contar(banco_atual) == 7
    assert _contar(caminhos.BANCO_ENTREGAS, "entregas_arquivos") == 2
    assert any("Contas a Pagar recuperadas" in item for item in migrados)
    assert list(banco_atual.parent.glob("contas_pagar.db.ANTES_MIGRACAO_17_8_3_*.bak"))


def test_backup_registra_quantidade_e_integridade_contas(tmp_path: Path) -> None:
    raiz = tmp_path / "dados_app"
    banco = raiz / "dados" / "financeiro" / "contas_pagar.db"
    _criar_contas(banco, 5)

    servico = ServicoBackup(raiz_dados=raiz, pasta_backups=tmp_path / "backups")
    resultado = servico.criar_backup(tipo="manual")

    assert resultado.contas_pagar == 5
    with zipfile.ZipFile(resultado.caminho, "r") as pacote:
        manifesto = json.loads(pacote.read("manifesto.json").decode("utf-8"))

    resumo = manifesto["modulos"]["contas_pagar"]
    assert resumo["registros"] == 5
    assert resumo["integridade_sqlite"] == "ok"
    assert resumo["caminho"] == "dados/financeiro/contas_pagar.db"


def test_restauracao_bloqueia_backup_vazio_sobre_base_com_contas(tmp_path: Path) -> None:
    raiz_atual = tmp_path / "atual"
    banco_atual = raiz_atual / "dados" / "financeiro" / "contas_pagar.db"
    _criar_contas(banco_atual, 4)

    raiz_vazia = tmp_path / "vazia"
    banco_vazio = raiz_vazia / "dados" / "financeiro" / "contas_pagar.db"
    _criar_contas(banco_vazio, 0)

    backup_vazio = ServicoBackup(
        raiz_dados=raiz_vazia,
        pasta_backups=tmp_path / "backups_vazios",
    ).criar_backup(tipo="manual")

    servico_atual = ServicoBackup(
        raiz_dados=raiz_atual,
        pasta_backups=tmp_path / "backups_atuais",
    )

    with pytest.raises(BackupInvalidoError, match="Restauração bloqueada"):
        servico_atual.restaurar_backup(
            backup_vazio.caminho,
            criar_backup_seguranca=False,
        )

    assert _contar(banco_atual) == 4


def test_validacao_backup_antigo_descobre_banco_financeiro_sem_resumo(tmp_path: Path) -> None:
    raiz = tmp_path / "antigo"
    banco = raiz / "dados" / "financeiro" / "contas_pagar.db"
    _criar_contas(banco, 3)

    servico = ServicoBackup(raiz_dados=raiz, pasta_backups=tmp_path / "backups")
    resultado = servico.criar_backup(tipo="manual")

    # Simula o formato 17.8.2 removendo apenas o novo bloco de resumo; os hashes
    # dos arquivos de dados continuam válidos porque o manifesto não é hasheado.
    refeito = tmp_path / "backup_17_8_2_simulado.zip"
    with zipfile.ZipFile(resultado.caminho, "r") as origem, zipfile.ZipFile(
        refeito, "w", compression=zipfile.ZIP_DEFLATED
    ) as destino:
        for nome in origem.namelist():
            if nome == "manifesto.json":
                manifesto = json.loads(origem.read(nome).decode("utf-8"))
                manifesto.pop("modulos", None)
                destino.writestr(nome, json.dumps(manifesto, ensure_ascii=False, indent=2))
            else:
                destino.writestr(nome, origem.read(nome))

    manifesto_validado = servico.validar_backup(refeito)
    assert manifesto_validado["modulos"]["contas_pagar"]["registros"] == 3
