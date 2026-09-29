from src.services.empresas_regimes_service import EmpresasRegimesService


def test_regime_mega_motos_comercio_resolve_para_presumido():
    assert EmpresasRegimesService.resolver_regime("Mega Motos Comércio", "") == "LUCRO PRESUMIDO"


def test_ficha_interface_contem_calculo_local_de_empresa_especifica():
    # Regressão do bug 17.8.29: _criar_interface usava empresa_especifica
    # sem defini-la no próprio escopo e a janela parava de montar no campo Regime.
    import inspect
    from src.ui.janela_ficha_tributaria import JanelaFichaTributaria

    fonte = inspect.getsource(JanelaFichaTributaria._criar_interface)
    assert 'empresa_especifica = empresa_atual not in {"", "Todas as empresas"}' in fonte
