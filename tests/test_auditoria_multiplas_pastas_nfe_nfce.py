"""Regressoes importacao incremental NF-e (55) e NFC-e (65)."""
from pathlib import Path
from xml.sax.saxutils import escape

from src.sped.auditor_tributario import ImportadorXMLNFe


def _xml(modelo, numero, chave):
    assert len(chave) == 44
    return (
        f'<nfeProc><NFe><infNFe Id="NFe{chave}">'
        f'<ide><mod>{modelo}</mod><nNF>{numero}</nNF><serie>1</serie></ide>'
        '<emit><CNPJ>11809691000195</CNPJ></emit>'
        '<dest><CNPJ>12345678000100</CNPJ></dest>'
        '<det nItem="1"><prod><cProd>P1</cProd><xProd>PECA</xProd>'
        '<NCM>87141000</NCM><CFOP>5102</CFOP><vProd>10.00</vProd>'
        '</prod></det><total><ICMSTot><vNF>10.00</vNF></ICMSTot></total>'
        '</infNFe></NFe></nfeProc>'
    )


def _chave(modelo, numero):
    # Chave com AAMM e modelo nas posicoes 21-22.
    chave = "31" + "2610" + "11809691000195" + modelo + "001" + f"{numero:09d}" + "1" + "00000001" + "0"
    assert len(chave) == 44
    return chave


def test_duas_pastas_acumulam_nfe_e_nfce(tmp_path):
    a, b = tmp_path / "nfe", tmp_path / "nfce"
    a.mkdir()
    b.mkdir()
    chave55, chave65 = _chave("55", 101), _chave("65", 202)
    (a / "nfe.xml").write_text(_xml("55", 101, chave55), encoding="utf-8")
    (b / "nfce.xml").write_text(_xml("65", 202, chave65), encoding="utf-8")
    imp = ImportadorXMLNFe()
    primeiro = imp.importar([a])
    assert primeiro.total_nfe_validas == 1
    assert primeiro.total_nfce_validas == 0
    ambos = imp.importar([b], anterior=primeiro)
    assert ambos.total_fontes == 2
    assert ambos.total_nfe_validas == 1
    assert ambos.total_nfce_validas == 1
    assert chave55 in ambos.documentos
    assert chave65 not in ambos.documentos
    assert chave65 in ambos.documentos_nfce
    assert chave55 not in ambos.documentos_nfce


def test_reselecionar_mesma_pasta_nao_duplica_contagem(tmp_path):
    pasta = tmp_path / "lote"
    pasta.mkdir()
    chave = _chave("55", 100)
    (pasta / "a.xml").write_text(_xml("55", 100, chave), encoding="utf-8")
    imp = ImportadorXMLNFe()
    r = imp.importar([pasta])
    r = imp.importar([pasta], anterior=r)
    assert r.total_fontes == 1
    assert r.total_nfe_validas == 1
    assert r.total_duplicadas == 0


def test_chaves_repetidas_em_pastas_diferentes_contam_uma_vez(tmp_path):
    chave = _chave("55", 123)
    a, b = tmp_path / "um", tmp_path / "dois"
    a.mkdir()
    b.mkdir()
    (a / "nota.xml").write_text(_xml("55", 123, chave), encoding="utf-8")
    (b / "nota.xml").write_text(_xml("55", 123, chave), encoding="utf-8")
    imp = ImportadorXMLNFe()
    r = imp.importar([a])
    r = imp.importar([b], anterior=r)
    assert r.total_fontes == 2
    assert r.total_nfe_validas == 1
    assert r.total_duplicadas == 1


def test_lote_novo_sem_anterior_recomeca_zerado(tmp_path):
    chave = _chave("65", 124)
    arquivo = tmp_path / "cupom.xml"
    arquivo.write_text(_xml("65", 124, chave), encoding="utf-8")
    imp = ImportadorXMLNFe()
    r = imp.importar([arquivo])
    novo = imp.importar([])
    assert r.total_nfce_validas == 1
    assert novo.total_nfce_validas == 0
    assert novo.total_fontes == 0
