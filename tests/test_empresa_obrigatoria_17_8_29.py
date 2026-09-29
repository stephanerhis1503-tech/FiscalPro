from pathlib import Path

from src.core.app_info import VERSAO_APP

BASE = Path(__file__).resolve().parents[1] / "src" / "ui"


def test_versao_minima_17829():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 29)


def test_ficha_nao_assume_lucro_real_com_todas_empresas():
    fonte = (BASE / "janela_ficha_tributaria.py").read_text(encoding="utf-8")
    init = fonte.split("class JanelaFichaTributaria", 1)[1].split("def _criar_card_resumo", 1)[0]
    assert 'empresa_especifica = empresa_inicial not in {"", "Todas as empresas"}' in init
    assert 'value=regime_inicial if empresa_especifica else "SELECIONE UMA EMPRESA"' in init
    assert 'state="readonly" if empresa_especifica else "disabled"' in fonte
    assert 'else "Selecione uma empresa para definir o regime e calcular PIS/COFINS."' in init


def test_ficha_bloqueia_analise_sem_empresa_especifica():
    fonte = (BASE / "janela_ficha_tributaria.py").read_text(encoding="utf-8")
    bloco = fonte.split("def analisar(self)", 1)[1].split("def _preencher_resultado", 1)[0]
    assert 'empresa_selecionada in {"", "Todas as empresas"}' in bloco
    assert "Selecione uma empresa antes de analisar" in bloco
    assert "self.combo_empresa.focus_set()" in bloco


def test_todas_empresas_limpa_e_bloqueia_regime():
    fonte = (BASE / "janela_ficha_tributaria.py").read_text(encoding="utf-8")
    bloco = fonte.split("def _empresa_alterada", 1)[1].split("def _mesclar_empresas", 1)[0]
    assert 'self.regime_var.set("SELECIONE UMA EMPRESA")' in bloco
    assert 'self.combo_regime.configure(state="disabled")' in bloco
    assert "Selecione uma empresa para definir o regime e calcular PIS/COFINS." in bloco


def test_empresa_conhecida_reaplica_regime_automatico():
    fonte = (BASE / "janela_ficha_tributaria.py").read_text(encoding="utf-8")
    bloco = fonte.split("def _empresa_alterada", 1)[1].split("def _mesclar_empresas", 1)[0]
    assert "EmpresasRegimesService.obter_perfil(empresa)" in bloco
    assert "self.regime_var.set(perfil.regime)" in bloco
    assert 'self.combo_regime.configure(state="readonly")' in bloco


def test_consulta_rapida_tambem_bloqueia_todas_empresas():
    fonte = (BASE / "janela_principal.py").read_text(encoding="utf-8")
    bloco = fonte.split("def abrir_ficha_tributaria_rapida", 1)[1].split("def abrir_calculo_icms_st_direto", 1)[0]
    assert 'empresa in {"", "Todas as empresas"}' in bloco
    assert "Selecione uma empresa antes de analisar" in bloco
    assert "return" in bloco
    assert "JanelaFichaTributaria(self.janela, contexto=contexto, ncm=termo)" in bloco
