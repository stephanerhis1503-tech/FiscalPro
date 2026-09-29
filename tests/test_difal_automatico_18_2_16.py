from src.sped.auditor_difal import AuditorDIFALSPED
from src.sped.auditor_tributario import DocumentoXMLNFe, ItemXMLNFe, ResultadoImportacaoXMLNFe

CHAVE = "31250712345678000190550010000012341000012345"


def _base_sped(c190: list[str], c101: str = "|C101|0,00|16,50|0,00|\n") -> list[str]:
    linhas = [
        "|0000|020|0|01072025|31072025|EMPRESA TESTE|12345678000190||MG|123|3106200|||B|1|\n",
        "|0150|CLI|CLIENTE CPF|1058||12345678909||2927408||RUA A|1|||\n",
        f"|C100|1|0|CLI|55|00|1|1234|{CHAVE}|01072025|01072025|200,00|0|0,00|0,00|200,00|0|0,00|0,00|0,00|200,00|7,00|0,00|0,00|0,00|1,65|7,60|0,00|0,00|\n",
    ]
    linhas.extend(c190)
    if c101:
        linhas.append(c101)
    return linhas


def _xml(p_inter: float = 4.0, valor_difal: float = 16.5) -> DocumentoXMLNFe:
    item = ItemXMLNFe(
        numero_item="1", codigo="A", descricao="PECA", ncm="00000000", cest="", cfop="6108",
        cst_icms="00", aliquota_icms=7.0, cst_pis="", aliquota_pis=0.0,
        cst_cofins="", aliquota_cofins=0.0, cst_ipi="", aliquota_ipi=0.0,
        valor_produto=100.0, tem_icms_uf_dest=True, base_difal=100.0, base_fcp_difal=100.0,
        aliquota_fcp_destino=0.0, aliquota_icms_destino=20.5,
        aliquota_icms_interestadual=p_inter, percentual_partilha_destino=100.0,
        valor_fcp_destino=0.0, valor_icms_destino=valor_difal, valor_icms_remetente=0.0,
    )
    return DocumentoXMLNFe(
        chave=CHAVE, numero="1234", serie="1", emitente_cnpj="12345678000190",
        destinatario_cnpj="12345678909", arquivo_origem="teste.xml", itens=[item],
        uf_emitente="MG", uf_destinatario="BA", id_destino="2", consumidor_final=True,
        indicador_ie_dest="9", destinatario_contribuinte=False, valor_nota=100.0,
    )


def test_xml_4_sped_cst_nacional_7_marca_divergencia_sem_substituir_cenario():
    sped = _base_sped([
        "|C190|000|6108|7,00|100,00|100,00|7,00|0,00|0,00|0,00|0,00||\n",
    ])
    doc = _xml(4.0, 16.5)
    imp = ResultadoImportacaoXMLNFe(documentos={doc.chave: doc}, total_nfe_validas=1)
    r = AuditorDIFALSPED().auditar(sped, "EFD ICMS/IPI (Fiscal)", importacao_xml=imp)
    a = r.apontamentos[0]
    assert a.nivel == "REVISAR"
    assert a.divergencia_origem is True
    assert a.aliquota_interestadual_xml_texto == "4%"
    assert a.aliquota_interestadual_sped_texto == "7%"
    assert float(a.difal_devido) == 16.5
    assert float(a.difal_sped_origem) == 13.5
    assert r.total_divergencias_origem == 1
    assert "ORIGEM DIVERGENTE" in a.evidencia


def test_origens_mistas_sem_xml_calcula_cada_segmento_e_soma():
    sped = _base_sped([
        "|C190|000|6108|7,00|100,00|100,00|7,00|0,00|0,00|0,00|0,00||\n",
        "|C190|100|6108|4,00|100,00|100,00|4,00|0,00|0,00|0,00|0,00||\n",
    ], c101="")
    r = AuditorDIFALSPED().auditar(sped, "EFD ICMS/IPI (Fiscal)", importacao_xml=None)
    a = r.apontamentos[0]
    assert a.nivel == "REVISAR"
    assert a.aliquota_interestadual_sped_texto == "4% / 7%"
    assert float(a.difal_devido) == 30.0  # 100×(20,5-7)% + 100×(20,5-4)%
    assert r.total_origem_mista_sped == 1
    assert "CST 000" in a.detalhe_origem_sped
    assert "CST 100" in a.detalhe_origem_sped


def test_xml_e_sped_mesma_aliquota_nao_cria_divergencia_origem():
    sped = _base_sped([
        "|C190|000|6108|7,00|100,00|100,00|7,00|0,00|0,00|0,00|0,00||\n",
    ], c101="|C101|0,00|13,50|0,00|\n")
    doc = _xml(7.0, 13.5)
    imp = ResultadoImportacaoXMLNFe(documentos={doc.chave: doc}, total_nfe_validas=1)
    r = AuditorDIFALSPED().auditar(sped, "EFD ICMS/IPI (Fiscal)", importacao_xml=imp)
    a = r.apontamentos[0]
    assert a.divergencia_origem is False
    assert a.aliquota_interestadual_xml_texto == "7%"
    assert a.aliquota_interestadual_sped_texto == "7%"
    assert r.total_divergencias_origem == 0
