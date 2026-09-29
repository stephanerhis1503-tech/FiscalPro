from src.sped.auditor_difal import AuditorDIFALSPED
from src.sped.auditor_tributario import DocumentoXMLNFe, ItemXMLNFe, ResultadoImportacaoXMLNFe


def _sped_6102_cpf() -> list[str]:
    chave = "31260812345678000190550010000012341000012345"
    return [
        "|0000|020|0|01082026|31082026|EMPRESA TESTE|12345678000190||MG|123|3106200|||B|1|\n",
        "|0150|CLI|CLIENTE CPF|1058||12345678909||2927408||RUA A|1|||\n",
        f"|C100|1|0|CLI|55|00|1|1234|{chave}|01082026|01082026|100,00|0|0,00|0,00|100,00|0|0,00|0,00|0,00|100,00|4,00|0,00|0,00|0,00|1,65|7,60|0,00|0,00|\n",
        "|C190|000|6102|4,00|100,00|100,00|4,00|0,00|0,00|0,00|0,00||\n",
    ]


def _xml_6102_sem_icmsufdest():
    chave = "31260812345678000190550010000012341000012345"
    item = ItemXMLNFe(
        numero_item="1", codigo="A", descricao="PECA", ncm="00000000", cest="", cfop="6102",
        cst_icms="00", aliquota_icms=4.0, cst_pis="", aliquota_pis=0.0, cst_cofins="",
        aliquota_cofins=0.0, cst_ipi="", aliquota_ipi=0.0, valor_produto=100.0,
        tem_icms_uf_dest=False, base_difal=0.0, base_fcp_difal=0.0, aliquota_fcp_destino=0.0,
        aliquota_icms_destino=0.0, aliquota_icms_interestadual=0.0, percentual_partilha_destino=0.0,
        valor_fcp_destino=0.0, valor_icms_destino=0.0, valor_icms_remetente=0.0,
    )
    return DocumentoXMLNFe(
        chave=chave, numero="1234", serie="1", emitente_cnpj="12345678000190",
        destinatario_cnpj="12345678909", arquivo_origem="teste.xml", itens=[item],
        uf_emitente="MG", uf_destinatario="BA", id_destino="2", consumidor_final=True,
        indicador_ie_dest="9", destinatario_contribuinte=False, valor_nota=100.0,
    )


def test_cfop_6102_xml_confirma_cpf_final_calcula_mesmo_sem_icmsufdest():
    doc = _xml_6102_sem_icmsufdest()
    imp = ResultadoImportacaoXMLNFe(documentos={doc.chave: doc}, total_nfe_validas=1)
    r = AuditorDIFALSPED().auditar(_sped_6102_cpf(), "EFD ICMS/IPI (Fiscal)", importacao_xml=imp)
    assert r.apontamentos
    a = r.apontamentos[0]
    assert float(a.base_calculo) == 100.0
    assert float(a.aliquota_interna) == 20.5
    assert float(a.aliquota_interestadual) == 4.0
    assert float(a.difal_devido) == 16.5
    assert a.calculo_estimado is True
    assert "CFOP 6102" in a.evidencia
    assert "cálculo reconstruído pelo SPED" in a.origem_calculo


def test_sem_xml_cpf_sem_ie_cfop_6102_tambem_calcula_e_marca_revisao():
    r = AuditorDIFALSPED().auditar(_sped_6102_cpf(), "EFD ICMS/IPI (Fiscal)", importacao_xml=None)
    assert r.apontamentos
    a = r.apontamentos[0]
    assert float(a.base_calculo) == 100.0
    assert float(a.aliquota_interna) == 20.5
    assert float(a.aliquota_interestadual) == 4.0
    assert float(a.difal_devido) == 16.5
    assert a.nivel == "REVISAR"
    assert "CPF sem IE" in a.evidencia
    assert "CFOP 6102" in a.evidencia
