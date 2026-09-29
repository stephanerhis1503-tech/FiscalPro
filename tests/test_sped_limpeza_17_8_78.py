"""Regressões da limpeza técnica do SPED na 17.8.78."""

from pathlib import Path

from src.core.app_info import VERSAO_APP


def _principal() -> str:
    return Path("src/ui/janela_principal.py").read_text(encoding="utf-8")


def test_versao_minima_17_8_78() -> None:
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 78)


def test_janela_principal_nao_importa_pipeline_sped_legado() -> None:
    fonte = _principal()
    assert "from src.leitor_sped import LeitorSPED" not in fonte
    assert "from src.motor_correcao import MotorCorrecao" not in fonte
    assert "from src.analisador import AnalisadorSPED" not in fonte
    assert "from src.formatador import FormatadorAuditoria" not in fonte


def test_janela_principal_nao_expoe_metodos_legados() -> None:
    fonte = _principal()
    assert "def abrir_sped(self):" not in fonte
    assert "def corrigir_sped(self):" not in fonte
    assert "def selecionar_xml(self):" not in fonte
    assert "self.linhas_sped" not in fonte
    assert "self.arquivo_sped" not in fonte
    assert "self.pasta_xml" not in fonte


def test_sped_inteligente_permanece_caminho_operacional() -> None:
    fonte = _principal()
    assert 'text="SPED Inteligente"' in fonte
    assert "command=self.abrir_sped_inteligente" in fonte
    assert "JanelaSPEDInteligente(self.janela)" in fonte
    assert 'text="XML → Planilha ST"' in fonte
    assert "command=self.abrir_xml_icms_st" in fonte
