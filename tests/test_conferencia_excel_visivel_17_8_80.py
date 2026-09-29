"""Regressões da interface da Conferência Excel na 17.8.80."""

from pathlib import Path

from src.core.app_info import VERSAO_APP


def _fonte() -> str:
    return Path("src/ui/janela_sped_inteligente.py").read_text(encoding="utf-8")


def test_versao_minima_17_8_80() -> None:
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 80)


def test_conferencia_excel_tem_fluxo_completo_na_propria_aba() -> None:
    fonte = _fonte()
    assert "self.btn_importar_excel_conf = ttk.Button" in fonte
    assert 'text="📂 Selecionar Excel"' in fonte
    assert "self.btn_validar_excel_conf = ttk.Button" in fonte
    assert 'text="✅ Validar planilha"' in fonte
    assert "self.btn_conferir_excel_conf = ttk.Button" in fonte
    assert 'text="🔎 Conferir alterações"' in fonte
    assert "self.btn_relatorio_conferencia_excel = ttk.Button" in fonte
    assert 'text="💾 Gerar relatório"' in fonte


def test_fluxo_conferencia_excel_sincroniza_estados() -> None:
    fonte = _fonte()
    assert "def _sincronizar_fluxo_conferencia_excel(self):" in fonte
    assert 'state="normal" if self.caminho_excel is not None else "disabled"' in fonte
    assert 'state="normal" if self.validacao_excel is not None else "disabled"' in fonte
    assert 'state="normal" if self.conferencia_excel_executada else "disabled"' in fonte


def test_selecao_e_validacao_permanecem_na_conferencia_excel() -> None:
    fonte = _fonte()
    assert fonte.count("self.abas.select(self.aba_conferencia_excel)") >= 3
    assert "self.conferencia_excel_executada = False" in fonte
    assert "self.conferencia_excel_executada = True" in fonte
