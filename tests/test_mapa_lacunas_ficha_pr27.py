"""Regressao do mapa de lacunas: sem registrar ou aplicar regra tributaria."""
from src.services.ficha_assistida_sped_service import PropostaFichaAssistida
from src.services.mapa_lacunas_ficha_service import consolidar_lacunas


def _p(ncm, codigo, finalidade, cfop, itens, st=""):
    return PropostaFichaAssistida(
        identificador=1, ncm=ncm, codigo_produto=codigo,
        descricao=f"PRODUTO {codigo}", empresa="MEGA MOTOS TRILHA",
        regime="LUCRO REAL", operacao="ENTRADA", finalidade=finalidade,
        uf_origem="MG", uf_destino="MG", contribuinte="CONTRIBUINTE",
        itens=itens, cfops_sped={cfop},
        st_status={st} if st else set(),
    )


def test_distingue_ncm_de_contextos_sem_inventar_regras():
    props = [
        _p("87141000", "P1", "REVENDA", "1403", 3),
        _p("87141000", "P2", "REVENDA", "2403", 2),
        _p("87141000", "P3", "USO E CONSUMO", "1556", 1),
        _p("65061090", "P4", "REVENDA", "2403", 2,
           "CONDICIONAL - CONFIRMAR FINALIDADE AUTOMOTIVA"),
        _p("32141010", "P5", "", "1949", 1),
    ]
    ncms, contextos = consolidar_lacunas(props)
    assert len(ncms) == 3
    assert len(contextos) == 5
    assert sum(x["itens"] for x in ncms) == 9
    principal = next(x for x in ncms if x["ncm"] == "87141000")
    assert principal["itens"] == 6
    assert principal["prioridade"] == "2 - FINALIDADES DIFERENTES"
    assert principal["ids_aprovados"] == 0
    assert next(x for x in ncms if x["ncm"] == "32141010")["prioridade"] == "1 - FINALIDADE INDEFINIDA"
    assert next(x for x in ncms if x["ncm"] == "65061090")["st_condicional"] == 1
    assert all(x["validacao"] == "PENDENTE - SEM HOMOLOGACAO AUTOMATICA" for x in contextos)


def test_mesma_mercadoria_cfops_distintos_geram_contextos_distintos():
    props = [
        _p("85365090", "A", "REVENDA", "1403", 1),
        _p("85365090", "A", "REVENDA", "2403", 1),
    ]
    ncms, contextos = consolidar_lacunas(props)
    assert len(ncms) == 1
    assert len(contextos) == 2
    assert {v["cfop"] for v in contextos} == {"1403", "2403"}
    assert all(v["ids_aprovados"] == 0 for v in contextos)


def test_alíquota_condicional_de_mva_nao_se_confunde_com_alerta_st():
    props = [
        _p("87141000", "A", "REVENDA", "2403", 1,
           "ICMS-ST/MG CONFIRMADO - MVA AJUSTADA COM ALIQUOTA INTERNA CONDICIONAL"),
    ]
    ncms, contextos = consolidar_lacunas(props)
    assert ncms[0]["st_condicional"] == 0
    assert contextos[0]["st_condicional"] == 0
