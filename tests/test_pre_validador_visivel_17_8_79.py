"""Regressões da interface do Pré-Validador PVA na 17.8.79."""

from pathlib import Path

from src.core.app_info import VERSAO_APP


def _fonte() -> str:
    return Path("src/ui/janela_sped_inteligente.py").read_text(encoding="utf-8")


def test_versao_minima_17_8_79() -> None:
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 79)


def test_pre_pva_tem_validacao_dentro_da_propria_aba() -> None:
    fonte = _fonte()
    assert "self.btn_validar_pva_aba = ttk.Button" in fonte
    assert 'text="✅ Validar antes do PVA"' in fonte
    assert "command=self.validar_antes_pva" in fonte


def test_pre_pva_tem_relatorio_dentro_da_propria_aba() -> None:
    fonte = _fonte()
    assert "self.btn_relatorio_pva_aba = ttk.Button" in fonte
    assert 'text="💾 Salvar relatório"' in fonte
    assert "command=self.salvar_relatorio_pva" in fonte


def test_estados_dos_atalhos_pva_sao_sincronizados() -> None:
    fonte = _fonte()
    assert 'self.btn_validar_pva_aba.configure(state="normal")' in fonte
    assert 'self.btn_validar_pva_aba.configure(state="disabled")' in fonte
    assert 'self.btn_relatorio_pva_aba.configure(state="normal")' in fonte
    assert 'self.btn_relatorio_pva_aba.configure(state="disabled")' in fonte
