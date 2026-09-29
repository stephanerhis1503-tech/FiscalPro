from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_uf_service import ICMSUFService


def test_versao_17_8_61():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 61)


def test_rn_contextual_mantem_fonte_anexo_005():
    resultado = ICMSUFService.analisar(
        "87141000",
        contexto={"uf_origem": "MG", "uf_destino": "RN", "data_operacao": "2026-08-24"},
    )
    st = ConsultaOficialService.st_contextual({"icms_uf": resultado})
    assert st["fonte_nome"] == "SEFAZ/RN — RICMS/RN, Anexo 005"
    assert st["regra_aplicada"] == "ANTECIPAÇÃO ICMS/RN — ANEXO 005"


def test_ficha_considera_nao_informada_como_fonte_ausente():
    fonte = Path("src/ui/janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert 'fonte_regra_exibicao in {"Não informado", "Não informada", "Não localizada"}' in fonte
    assert 'fonte_regra_exibicao = str(st_oficial.get("fonte_nome") or "").strip()' in fonte
