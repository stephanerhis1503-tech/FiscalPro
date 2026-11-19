"""Conferencia de cobertura: somente NF-e 55 com C170 integra denominador."""
from src.sped.auditor_tributario import (
    AuditorTributarioSPED,
    DocumentoXMLNFe,
    ResultadoImportacaoXMLNFe,
)


def _nota(chave: str, modelo="55", numero="1", tem_c170=True) -> list[str]:
    # Layout C100: IND_OPER, IND_EMIT, COD_PART, COD_MOD, COD_SIT, SER, NUM_DOC, CHV_NFE
    c100 = f"|C100|0|1|FORN|{modelo}|00|1|{numero}|{chave}|01102026|01102026|100|"
    return [c100] + (
        ["|C170|1|P1|PECAS|1|UN|100|0|0|000|2102|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|"]
        if tem_c170 else []
    )


def test_c100_sem_c170_nao_aumenta_documentos_faltantes(monkeypatch):
    monkeypatch.setattr(
        AuditorTributarioSPED, "_carregar_regras_lote",
        staticmethod(lambda ncms: ({}, {}, set())),
    )
    k1 = "3" * 44
    k2 = "4" * 44
    k3 = "5" * 44
    linhas = [
        "|0000|019|0|01012026|31122026|TESTE|11809691000195|MG|",
        "|0150|FORN|FORNECEDOR|1058|12345678000100|",
        "|0200|P1|PRODUTO|UN|00|87141000|",
        *_nota(k1, tem_c170=True),
        *_nota(k2, numero="2", tem_c170=False),
        *_nota(k3, numero="3", tem_c170=False),
    ]
    imp = ResultadoImportacaoXMLNFe(
        documentos={k1: DocumentoXMLNFe(
            chave=k1, numero="1", serie="1", emitente_cnpj="12345678000100",
            destinatario_cnpj="11809691000195", arquivo_origem="exemplo.xml"
        )},
        total_nfe_validas=1,
    )
    r = AuditorTributarioSPED().auditar(
        linhas, "EFD ICMS/IPI (Fiscal)", "TESTE",
        {"regime": "LUCRO REAL"}, imp
    )
    assert r.notas_sped_chaves_unicas == 3
    assert r.notas_sped_chaves_coincidentes == 1
    assert r.notas_c170_chaves_unicas == 1
    assert r.notas_c170_chaves_coincidentes == 1
    assert "Todas as 1 NF-e modelo 55 com C170" in r.diagnostico_xml
    assert r.c170_notas_entrada == 1
    assert r.c170_notas_entrada_com_xml == 1
    assert r.c170_notas_saida == 0
    assert r.xml_importados_c100_sem_c170 == 0
    assert len(r.documentos_c170) == 1
    assert r.documentos_c170[0]["situacao"] == "LOCALIZADO"
    assert len(r.documentos_xml_importados) == 1
    assert r.documentos_xml_importados[0]["situacao"] == "CORRESPONDE A C170"

