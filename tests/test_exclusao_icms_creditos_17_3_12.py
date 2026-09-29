from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.sped.exclusor_icms_creditos_piscofins import ExclusorICMSCreditosPISCOFINS
from src.sped.estatisticas import CalculadorEstatisticasSPED
from src.sped.indice import IndiceSPED


def linha(campos: list[str]) -> str:
    return "|" + "|".join(campos) + "|\n"


def c100(chave: str, cnpj_num: str = "123") -> list[str]:
    # Índices usados: IND_OPER=1, IND_EMIT=2, NUM_DOC=7, CHV_NFE=8,
    # totais PIS/COFINS=25/26.
    campos = ["C100"] + [""] * 28
    campos[1] = "0"
    campos[2] = "1"
    campos[4] = "55"
    campos[5] = "00"
    campos[7] = "10"
    campos[8] = chave
    campos[25] = "1,65"
    campos[26] = "7,60"
    return campos


def c170(base: str = "100,00", cod_item: str = "ITEM1", icms: str = "18,00") -> list[str]:
    campos = ["C170"] + [""] * 35
    campos[1] = "1"
    campos[2] = cod_item
    campos[4] = "1,00"
    campos[5] = "UN"
    campos[6] = "100,00"
    campos[9] = "000"
    campos[10] = "2102"
    campos[12] = "100,00"
    campos[13] = "18,00"
    campos[14] = icms
    campos[24] = "50"
    campos[25] = base
    campos[26] = "1,6500"
    campos[29] = "1,65" if base == "100,00" else "1,35"
    campos[30] = "50"
    campos[31] = base
    campos[32] = "7,6000"
    campos[35] = "7,60" if base == "100,00" else "6,23"
    return campos


def contrib_lines(base: str = "100,00", cod_item: str = "ITEM1") -> list[str]:
    chave = "31260712345678000190550010000000101234567890"
    return [
        linha(["0000", "006", "0", "", "", "01072026", "31072026", "EMPRESA TESTE", "12345678000190", "MG", "3100000", "", "00", "2"]),
        linha(["0001", "0"]),
        linha(["0110", "1", "1", "1", ""]),
        linha(c100(chave)),
        linha(c170(base=base, cod_item=cod_item)),
        linha(["M001", "0"]),
        linha(["M100", "101", "0", "100,00", "1,6500", "", "", "1,65", "0,00", "0,00", "0,00", "1,65", "0", "1,65", "0,00"]),
        linha(["M105", "02", "50", "100,00", "0,00", "100,00", "100,00", "", "", ""]),
        linha(["M200", "2,00", "1,65", "0,00", "0,35", "0,00", "0,00", "0,35", "0,00", "0,00", "0,00", "0,00", "0,35"]),
        linha(["M500", "101", "0", "100,00", "7,6000", "", "", "7,60", "0,00", "0,00", "0,00", "7,60", "0", "7,60", "0,00"]),
        linha(["M505", "02", "50", "100,00", "0,00", "100,00", "100,00", "", "", ""]),
        linha(["M600", "8,00", "7,60", "0,00", "0,40", "0,00", "0,00", "0,40", "0,00", "0,00", "0,00", "0,00", "0,40"]),
        linha(["M990", "8"]),
        linha(["9999", "14"]),
    ]


def fiscal_text(cnpj: str = "12345678000190", cod_item: str = "ITEM1") -> str:
    chave = "31260712345678000190550010000000101234567890"
    return "".join([
        linha(["0000", "020", "0", "01072026", "31072026", "EMPRESA TESTE", cnpj, "", "MG", "123", "3100000", "", "", "B", "1"]),
        linha(c100(chave)),
        linha(c170(base="100,00", cod_item=cod_item, icms="18,00")),
        linha(["9999", "4"]),
    ])


def estat(linhas: list[str]):
    return CalculadorEstatisticasSPED().calcular(linhas, IndiceSPED().construir(linhas))


class ValidadorVazio:
    def validar(self, *_args, **_kwargs):
        return SimpleNamespace(erros=[], avisos=[])


def test_exclui_icms_e_recalcula_documento_e_bloco_m(tmp_path):
    linhas = contrib_lines()
    e = estat(linhas)
    fiscal = tmp_path / "fiscal.txt"
    fiscal.write_text(fiscal_text(), encoding="utf-8")

    exclusor = ExclusorICMSCreditosPISCOFINS()
    exclusor.pre_validador = ValidadorVazio()
    analise = exclusor.analisar(linhas, e.tipo_sped, e.cnpj, e.periodo, fiscal)

    assert analise.pode_gerar
    assert analise.documentos_aptos == 1
    assert analise.itens_alterar == 1
    assert analise.total_icms_excluir == Decimal("18.00")

    saida = tmp_path / "contrib_corrigido.txt"
    resultado = exclusor.gerar(linhas, "utf-8", e.tipo_sped, analise, saida)
    novas = saida.read_text(encoding="utf-8").splitlines()

    assert "|C170|1|ITEM1||1,00|UN|100,00" in novas[4]
    assert "|50|82,00|1,6500|||1,35|50|82,00|7,6000|||6,23|" in novas[4]
    assert "|M100|101|0|82,00|1,6500|||1,35|0,00|0,00|0,00|1,35|0|1,35|0,00|" in novas[6]
    assert "|M105|02|50|82,00|0,00|82,00|82,00|" in novas[7]
    assert "|M200|2,00|1,35|0,00|0,65|0,00|0,00|0,65|" in novas[8]
    assert "|M500|101|0|82,00|7,6000|||6,23|0,00|0,00|0,00|6,23|0|6,23|0,00|" in novas[9]
    assert "|M505|02|50|82,00|0,00|82,00|82,00|" in novas[10]
    assert "|M600|8,00|6,23|0,00|1,77|0,00|0,00|1,77|" in novas[11]
    assert resultado.reducao_pis == Decimal("0.30")
    assert resultado.reducao_cofins == Decimal("1.37")


def test_nao_exclui_icms_duas_vezes(tmp_path):
    linhas = contrib_lines(base="82,00")
    e = estat(linhas)
    fiscal = tmp_path / "fiscal.txt"
    fiscal.write_text(fiscal_text(), encoding="utf-8")

    analise = ExclusorICMSCreditosPISCOFINS().analisar(
        linhas, e.tipo_sped, e.cnpj, e.periodo, fiscal
    )
    assert not analise.itens_aptos
    assert len(analise.itens_ja_excluidos) == 1
    assert not analise.inconsistencias


def test_bloqueia_cnpj_ou_competencia_diferente(tmp_path):
    linhas = contrib_lines()
    e = estat(linhas)
    fiscal = tmp_path / "fiscal.txt"
    fiscal.write_text(fiscal_text(cnpj="99999999000199"), encoding="utf-8")

    with pytest.raises(RuntimeError, match="CNPJ"):
        ExclusorICMSCreditosPISCOFINS().analisar(
            linhas, e.tipo_sped, e.cnpj, e.periodo, fiscal
        )


def test_bloqueia_item_sem_correspondencia_exata(tmp_path):
    linhas = contrib_lines(cod_item="OUTRO")
    e = estat(linhas)
    fiscal = tmp_path / "fiscal.txt"
    fiscal.write_text(fiscal_text(cod_item="ITEM1"), encoding="utf-8")

    analise = ExclusorICMSCreditosPISCOFINS().analisar(
        linhas, e.tipo_sped, e.cnpj, e.periodo, fiscal
    )
    assert not analise.pode_gerar
    assert analise.inconsistencias
    assert "correspondência única" in analise.inconsistencias[0]
