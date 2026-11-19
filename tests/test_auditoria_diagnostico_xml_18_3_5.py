"""Diagnostico XML quando nenhuma chave do SPED cruza com os documentos importados."""
from src.sped.auditor_tributario import AuditorTributarioSPED, ResultadoImportacaoXMLNFe


def _linhas():
    # Arquivo SPED minimo sintético com nota C100 e item C170; sem depender da base real.
    return [
        "|0000|019|0|01012026|31122026|TESTE|11809691000195|MG|",
        "|0150|FORN|FORNECEDOR|1058|12345678000100|",
        "|0200|P1|PRODUTO TESTE|UN|00|87141000|",
        "|C100|0|1|FORN|55|00|1|100|31102611809691000195550010000001001000000001|01012026|01012026|100|0|0|0|100|0|0|0|0|0|0|0|0|0|",
        "|C170|1|P1|PRODUTO TESTE|1|UN|100|0|0|000|2102|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|",
    ]


def test_sem_xml_importado_distingue_de_importacao_vazia(monkeypatch):
    from src.sped import auditor_tributario as modulo
    monkeypatch.setattr(
        modulo.AuditorTributarioSPED, "_carregar_regras_lote",
        staticmethod(lambda ncms: ({}, {}, set())),
    )
    s = AuditorTributarioSPED().auditar(
        _linhas(), "EFD ICMS/IPI (Fiscal)", "TESTE", {"regime": "LUCRO REAL"}
    )
    assert not s.xml_importado
    assert "Nenhum XML de NF-e foi importado" in s.diagnostico_xml
    assert s.xml_validos_importados == 0

    vazio = ResultadoImportacaoXMLNFe(total_ignoradas=2, total_erros=1)
    t = AuditorTributarioSPED().auditar(
        _linhas(), "EFD ICMS/IPI (Fiscal)", "TESTE",
        {"regime": "LUCRO REAL"}, vazio
    )
    assert t.xml_importado
    assert "Importacao sem NF-e valida" in t.diagnostico_xml
    assert "erros de leitura: 1" in t.diagnostico_xml
