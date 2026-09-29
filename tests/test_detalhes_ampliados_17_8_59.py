from pathlib import Path

from src.core.app_info import VERSAO_APP


BASE = Path(__file__).resolve().parents[1] / "src" / "ui"


def test_versao_17859_ativa():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 59)


def test_ficha_tem_detalhes_tecnicos_ampliados():
    fonte = (BASE / "janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert "class _JanelaDetalhesTecnicosAmpliados" in fonte
    assert 'text="⛶ Ampliar detalhes"' in fonte
    assert "abrir_detalhes_tecnicos_ampliados" in fonte
    assert 'orient=tk.HORIZONTAL' in fonte
    assert 'orient=tk.VERTICAL' in fonte
    assert 'orient=tk.HORIZONTAL, command=tree.xview' in fonte
    assert 'self.state("zoomed")' in fonte


def test_duplo_clique_tambem_abre_visualizacao_ampla():
    fonte = (BASE / "janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert 'self.tree_resultado.bind("<Double-1>"' in fonte
    assert 'self.texto_explicacao.bind("<Double-1>"' in fonte
