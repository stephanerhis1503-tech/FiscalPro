from src.services.cobertura_tributaria_service import CoberturaTributariaService


def test_resumo_bases_instaladas_tem_ncm_tipi_e_st_mg():
    r = CoberturaTributariaService.resumo_bases()
    assert r["ncm_oficial"] >= 11000
    assert r["tipi_oficial"] >= 10000
    assert r["st_mg_registros"] >= 200
    assert r["st_mg_ncm"] > 0
    assert len(r["st_mg_segmentos"]) >= 3


def test_mapa_cobre_as_27_ufs_sem_dizer_que_regra_geral_e_cobertura_local():
    linhas = CoberturaTributariaService.mapa_ufs()
    assert len(linhas) == 27
    por_uf = {x["uf"]: x for x in linhas}
    assert por_uf["MG"]["nivel"] == 3
    for uf in ("SP", "ES", "BA", "RJ", "PA", "GO", "PR", "MS"):
        assert por_uf[uf]["nivel"] == 2
    assert "Autopeças + pneumáticos" in por_uf["PA"]["st"]
    for uf in ("RS",):
        assert por_uf[uf]["nivel"] == 2
        assert "Pneumáticos detalhados" in por_uf[uf]["st"]
        assert "01/11/2024" in por_uf[uf]["st"]


def test_diagnostico_nao_confunde_ausencia_de_base_com_ausencia_de_tributo():
    d = CoberturaTributariaService.diagnostico()
    assert "Ausência de regra local" in d["aviso"]
    assert d["totais"]["ampliada"] == 1
    assert d["totais"]["parcial"] == 25
    assert d["totais"]["geral"] == 1
