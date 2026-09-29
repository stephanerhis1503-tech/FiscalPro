from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.comparador_cenarios_tributarios_service import (
    ComparadorCenariosTributariosService,
)

BASE = Path(__file__).resolve().parents[1]


def contexto(empresa, origem="MG", destino="MG"):
    return {
        "empresa": empresa,
        "operacao": "SAÍDA",
        "uf_origem": origem,
        "uf_destino": destino,
        "finalidade": "REVENDA",
    }


def linha(resultado, chave):
    return next(item for item in resultado["linhas"] if item.chave == chave)


def test_versao_17833_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split(".")) >= (17, 8, 33)


def test_comparador_usa_mesmos_motores_e_diferencia_presumido_de_real():
    resultado = ComparadorCenariosTributariosService.comparar(
        "87141000",
        contexto("Mega Motos Comércio"),
        contexto("Mega Motos Trilha"),
    )
    regime = linha(resultado, "regime")
    pisco = linha(resultado, "piscofins")
    assert regime.diferente is True
    assert "LUCRO PRESUMIDO" in regime.valor_a
    assert "LUCRO REAL" in regime.valor_b
    assert pisco.diferente is True
    assert "PIS 0,65%" in pisco.valor_a and "COFINS 3,00%" in pisco.valor_a
    assert "PIS 1,65%" in pisco.valor_b and "COFINS 7,60%" in pisco.valor_b
    assert linha(resultado, "icms_st").diferente is False


def test_monofasico_prevalece_nos_dois_regimes():
    resultado = ComparadorCenariosTributariosService.comparar(
        "40114000",
        contexto("Mega Motos Comércio"),
        contexto("Mega Motos Trilha"),
    )
    pisco = linha(resultado, "piscofins")
    assert pisco.diferente is False
    assert "MONOFÁSICO" in pisco.valor_a.upper()
    assert "PIS 0,00%" in pisco.valor_a
    assert "COFINS 0,00%" in pisco.valor_a


def test_comparacao_de_rota_destaca_icms_e_cfop():
    resultado = ComparadorCenariosTributariosService.comparar(
        "87141000",
        contexto("Mega Motos Comércio", "MG", "MG"),
        contexto("Mega Motos Comércio", "PA", "MG"),
    )
    icms = linha(resultado, "icms")
    cfop = linha(resultado, "cfop")
    assert icms.diferente is True
    assert "18,00%" in icms.valor_a
    assert "12,00%" in icms.valor_b
    assert cfop.diferente is True
    assert "5405" in cfop.valor_a
    assert "6403" in cfop.valor_b


def test_central_expoe_botao_comparar_cenarios():
    fonte = (BASE / "src/ui/janela_principal.py").read_text(encoding="utf-8")
    assert "Comparar cenários" in fonte
    assert "JanelaCompararCenariosTributarios" in fonte
    assert "def abrir_comparador_tributario" in fonte
    fonte_janela = (BASE / "src/ui/janela_comparar_cenarios_tributarios.py").read_text(encoding="utf-8")
    assert "Mostrar somente diferenças" in fonte_janela
    assert "USAR ESTE CENÁRIO" in fonte_janela
    assert "_abrir_ficha" in fonte_janela
