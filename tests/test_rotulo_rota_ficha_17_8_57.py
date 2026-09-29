from pathlib import Path

from src.core.app_info import VERSAO_APP


def test_versao_17857():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 57)


def test_rotulo_interestadual_usa_ufs_selecionadas_na_tela():
    fonte = Path("src/ui/janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert "uf_origem_exibicao" in fonte
    assert "uf_destino_exibicao" in fonte
    assert 'f"ICMS interestadual {uf_origem_exibicao}→{uf_destino_exibicao}"' in fonte
    assert "self.uf_origem_var.get()" in fonte
    assert "self.uf_destino_var.get()" in fonte


def test_rotulo_da_rota_nao_depende_da_uf_retornada_pelo_motor_st():
    fonte = Path("src/ui/janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert 'f"ICMS interestadual {self._contexto().get(\'uf_origem\') or \'-\'}→{uf_icms}"' not in fonte
