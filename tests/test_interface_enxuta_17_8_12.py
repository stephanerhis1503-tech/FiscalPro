from pathlib import Path

from src.core.app_info import VERSAO_APP


def _fonte_principal():
    return Path("src/ui/janela_principal.py").read_text(encoding="utf-8")


def test_17812_remove_robo_fiscal_da_navegacao_e_carregamento():
    fonte = _fonte_principal()
    bloco_abas = fonte.split("def criar_abas", 1)[1].split("def _cabecalho_pagina", 1)[0]
    assert "aba_robo" not in bloco_abas
    assert 'text="  Robô Fiscal  "' not in bloco_abas
    assert "criar_painel_robo" not in fonte
    assert "painel_robo_email" not in fonte
    assert "PainelRoboEmail" not in fonte


def test_17812_remove_atalhos_antigos_da_aba_sped():
    fonte = _fonte_principal()
    bloco = fonte.split("def criar_botoes", 1)[1].split("def criar_resultado", 1)[0]
    assert 'text="Abrir SPED"' not in bloco
    assert 'text="Corrigir SPED"' not in bloco
    assert 'text="SPED Inteligente"' in bloco
    assert 'text="Selecionar XML"' not in bloco
    assert 'text="XML → Planilha ST"' in bloco
    assert 'text="Consulta tributária"' in bloco
    assert 'text="Ficha inteligente"' in bloco
    assert "range(4)" in bloco


def test_17812_contas_pagar_sem_fila_robo_visivel():
    fonte = Path("src/ui/painel_contas_pagar.py").read_text(encoding="utf-8")
    bloco = fonte.split("def _montar", 1)[1].split("def _montar_cards", 1)[0]
    assert 'text="Fila do Robô"' not in bloco
    assert "Agenda Inteligente de Faturas" in bloco
    assert "range(5)" in bloco


def test_17812_backup_preserva_legado_sem_apresentar_robo_como_ativo():
    fonte = Path("src/ui/janela_backup.py").read_text(encoding="utf-8")
    assert "documentos fiscais arquivados" in fonte
    assert "dados históricos dos módulos desativados" in fonte


def test_17812_relatorios_nao_cita_robo_fiscal_ativo():
    fonte = _fonte_principal()
    bloco = fonte.split("def criar_painel_relatorios", 1)[1].split("def criar_painel_financeiro", 1)[0]
    assert "Robô Fiscal" not in bloco
    assert "SPED Inteligente" in bloco


def test_versao_cumulativa_apos_17_8_12():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 12)
