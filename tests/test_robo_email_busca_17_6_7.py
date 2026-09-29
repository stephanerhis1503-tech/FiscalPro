from pathlib import Path
import json

from src.robo_email.config import ConfiguracaoRoboEmail
from src.robo_email.servico import RoboEmailService


def test_consulta_padrao_busca_caixa_entrada_e_lidos(tmp_path):
    cfg = ConfiguracaoRoboEmail(
        caminho_credenciais=str(tmp_path / 'cred.json'),
        pasta_destino=str(tmp_path / 'docs'),
        dias_retroativos=30,
        somente_nao_lidos=False,
    )
    consulta = RoboEmailService(cfg)._montar_consulta()
    assert 'in:inbox' in consulta
    assert 'newer_than:30d' in consulta
    assert 'is:unread' not in consulta


def test_consulta_opcional_somente_nao_lidos(tmp_path):
    cfg = ConfiguracaoRoboEmail(
        caminho_credenciais=str(tmp_path / 'cred.json'),
        pasta_destino=str(tmp_path / 'docs'),
        dias_retroativos=7,
        somente_nao_lidos=True,
    )
    consulta = RoboEmailService(cfg)._montar_consulta()
    assert 'in:inbox' in consulta
    assert 'is:unread' in consulta


def test_padrao_novo_nao_restringe_nao_lidos():
    cfg = ConfiguracaoRoboEmail()
    assert cfg.somente_nao_lidos is False
    assert cfg.revisao_busca == 2
