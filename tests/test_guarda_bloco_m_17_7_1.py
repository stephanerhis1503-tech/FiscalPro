from __future__ import annotations

from src.sped.validador_apuracao_bloco_m import ValidadorApuracaoBlocoM


def linha(campos: list[str]) -> str:
    return "|" + "|".join(campos) + "|"


def c170_credito(base_pis="100,00", base_cofins="100,00") -> str:
    campos = ["C170"] + [""] * 35
    campos[1] = "1"
    campos[2] = "ITEM1"
    campos[10] = "1102"
    campos[24] = "50"
    campos[25] = base_pis
    campos[26] = "1,6500"
    campos[29] = "1,65" if base_pis != "0,00" else "0,00"
    campos[30] = "50"
    campos[31] = base_cofins
    campos[32] = "7,6000"
    campos[35] = "7,60" if base_cofins != "0,00" else "0,00"
    return linha(campos)


def test_sped_fiscal_nao_e_bloqueado():
    r = ValidadorApuracaoBlocoM().validar([c170_credito()], "EFD ICMS/IPI (Fiscal)")
    assert not r.aplicavel
    assert not r.bloqueado


def test_creditos_sem_bloco_m_bloqueiam_excel():
    r = ValidadorApuracaoBlocoM().validar(
        [linha(["M001", "0"]), c170_credito()],
        "EFD Contribuições",
    )
    assert r.bloqueado
    assert r.creditos_pis == 1
    assert r.creditos_cofins == 1
    assert any("nenhum M100" in motivo for motivo in r.motivos)
    assert any("nenhum M500" in motivo for motivo in r.motivos)
    assert "Gerar Apurações" in r.mensagem_bloqueio()


def test_bloco_m_com_pais_e_filhos_permite_excel():
    linhas = [
        linha(["M001", "0"]),
        c170_credito(),
        linha(["M100", "101", "0", "100,00", "1,6500"]),
        linha(["M105", "02", "50", "100,00", "0,00", "100,00", "100,00"]),
        linha(["M500", "101", "0", "100,00", "7,6000"]),
        linha(["M505", "02", "50", "100,00", "0,00", "100,00", "100,00"]),
    ]
    r = ValidadorApuracaoBlocoM().validar(linhas, "EFD Contribuições")
    assert not r.bloqueado
    assert r.apurado_para_excel


def test_sem_credito_nao_exige_m100_m500():
    c170 = ["C170"] + [""] * 35
    c170[24] = "04"
    c170[25] = "0,00"
    c170[29] = "0,00"
    c170[30] = "04"
    c170[31] = "0,00"
    c170[35] = "0,00"
    r = ValidadorApuracaoBlocoM().validar(
        [linha(["M001", "0"]), linha(c170)],
        "EFD Contribuições",
    )
    assert not r.bloqueado


def test_m001_sem_movimento_com_documentos_tributarios_bloqueia():
    r = ValidadorApuracaoBlocoM().validar(
        [linha(["M001", "1"]), c170_credito()],
        "EFD Contribuições",
    )
    assert r.bloqueado
    assert any("IND_MOV=1" in motivo for motivo in r.motivos)


def test_m100_sem_m105_e_m500_sem_m505_bloqueia():
    r = ValidadorApuracaoBlocoM().validar(
        [
            linha(["M001", "0"]),
            c170_credito(),
            linha(["M100", "101", "0", "100,00", "1,6500"]),
            linha(["M500", "101", "0", "100,00", "7,6000"]),
        ],
        "EFD Contribuições",
    )
    assert r.bloqueado
    assert any("nenhum M105" in motivo for motivo in r.motivos)
    assert any("nenhum M505" in motivo for motivo in r.motivos)
