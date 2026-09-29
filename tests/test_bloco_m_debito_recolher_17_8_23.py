from src.sped.reapurador_bloco_m import ReapuradorBlocoM
from src.sped.pre_validador import PreValidadorPVA


def _c170(base_pis: str, valor_pis: str, base_cofins: str, valor_cofins: str) -> str:
    campos = [
        "C170", "1", "P1", "Produto", "1", "UN", "100,00", "0", "0", "060", "5405",
        "", "", "", "", "", "", "", "", "", "", "", "", "", "01", base_pis,
        "1,65", "", "", valor_pis, "01", base_cofins, "7,60", "", "", valor_cofins, "61075", "",
    ]
    return "|" + "|".join(campos) + "|\n"


def _bloco(base_pis="100,00", vp="1,65", base_cofins="100,00", vc="7,60"):
    return [
        _c170(base_pis, vp, base_cofins, vc),
        "|M200|1,65|0|0|1,65|0|0|1,65|0|0|0|0|1,65|\n",
        "|M205|08|691201|1,65|\n",
        "|M210|01|100,00|100,00|0|0|100,00|1,65|0||1,65|0|0|0|0|1,65|\n",
        "|M600|7,60|0|0|7,60|0|0|7,60|0|0|0|0|7,60|\n",
        "|M605|08|585601|7,60|\n",
        "|M610|01|100,00|100,00|0|0|100,00|7,60|0||7,60|0|0|0|0|7,60|\n",
    ]


def test_reapurador_sincroniza_m205_e_m605_com_m200_m600():
    antes = _bloco()
    depois = list(antes)
    depois[0] = _c170("90,00", "1,49", "90,00", "6,84")

    resultado = ReapuradorBlocoM().sincronizar(antes, depois, "EFD Contribuições")
    assert resultado.avisos == []

    por_codigo = {}
    for linha in resultado.linhas:
        codigo = linha.split("|")[1]
        por_codigo[codigo] = linha

    assert por_codigo["M200"].split("|")[8] == "1,49"  # VL_CONT_NC_REC
    assert por_codigo["M205"].split("|")[4] == "1,49"  # VL_DEBITO
    assert por_codigo["M600"].split("|")[8] == "6,84"
    assert por_codigo["M605"].split("|")[4] == "6,84"


def test_pre_validador_detecta_m205_m605_dessincronizados():
    linhas = _bloco()
    # Pais já reduzidos, filhos ainda no valor antigo: exatamente o cenário visto no PGE.
    linhas[1] = "|M200|1,49|0|0|1,49|0|0|1,49|0|0|0|0|1,49|\n"
    linhas[4] = "|M600|6,84|0|0|6,84|0|0|6,84|0|0|0|0|6,84|\n"
    resultado = PreValidadorPVA().validar(linhas, "EFD Contribuições")
    erros = [e for e in resultado.erros if e.categoria == "Débito a recolher Bloco M"]
    assert len(erros) == 2
    assert {e.registro for e in erros} == {"M205", "M605"}


def test_pre_validador_aprova_m205_m605_sincronizados():
    antes = _bloco()
    depois = list(antes)
    depois[0] = _c170("90,00", "1,49", "90,00", "6,84")
    sincronizado = ReapuradorBlocoM().sincronizar(antes, depois, "EFD Contribuições")
    resultado = PreValidadorPVA().validar(sincronizado.linhas, "EFD Contribuições")
    erros = [e for e in resultado.erros if e.categoria == "Débito a recolher Bloco M"]
    assert erros == []


def test_versao_17_8_23():
    from src.core.app_info import VERSAO_APP
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 23)
