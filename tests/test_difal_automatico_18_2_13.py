from src.simulador.tabela_difal import aliquota_interna_destino
from src.sped.auditor_difal import AuditorDIFALSPED
from src.sped.auditor_tributario import DocumentoXMLNFe, ItemXMLNFe, ResultadoImportacaoXMLNFe


def _sped_ba() -> list[str]:
    chave = "31260812345678000190550010000012341000012345"
    return [
        "|0000|020|0|01082026|31082026|EMPRESA TESTE|12345678000190||MG|123|3106200|||B|1|\n",
        "|0150|CLI|CLIENTE|1058||12345678909||2927408||RUA A|1|||\n",
        f"|C100|1|0|CLI|55|00|1|1234|{chave}|01082026|01082026|100,00|0|0,00|0,00|100,00|0|0,00|0,00|0,00|100,00|4,00|0,00|0,00|0,00|1,65|7,60|0,00|0,00|\n",
        "|C190|000|6108|4,00|100,00|100,00|4,00|0,00|0,00|0,00|0,00||\n",
    ]


def test_bahia_historico_modal():
    assert aliquota_interna_destino("BA", "01082026") == 20.5
    assert aliquota_interna_destino("BA", "07022024") == 20.5
    assert aliquota_interna_destino("BA", "06022024") == 19
    assert aliquota_interna_destino("BA", "21032023") == 18


def test_xml_bahia_19_mostra_20_5_e_recalcula_devido():
    chave = "31260812345678000190550010000012341000012345"
    item = ItemXMLNFe(
        numero_item="1", codigo="A", descricao="PECA", ncm="00000000", cest="", cfop="6108",
        cst_icms="00", aliquota_icms=4.0, cst_pis="", aliquota_pis=0.0, cst_cofins="",
        aliquota_cofins=0.0, cst_ipi="", aliquota_ipi=0.0, valor_produto=100.0,
        tem_icms_uf_dest=True, base_difal=100.0, base_fcp_difal=100.0, aliquota_fcp_destino=0.0,
        aliquota_icms_destino=19.0, aliquota_icms_interestadual=4.0, percentual_partilha_destino=100.0,
        valor_fcp_destino=0.0, valor_icms_destino=15.0, valor_icms_remetente=0.0,
    )
    doc = DocumentoXMLNFe(
        chave=chave, numero="1234", serie="1", emitente_cnpj="12345678000190",
        destinatario_cnpj="12345678909", arquivo_origem="teste.xml", itens=[item],
        uf_emitente="MG", uf_destinatario="BA", id_destino="2", consumidor_final=True,
        indicador_ie_dest="9", destinatario_contribuinte=False, valor_nota=100.0,
    )
    imp = ResultadoImportacaoXMLNFe(documentos={chave: doc}, total_nfe_validas=1)
    r = AuditorDIFALSPED().auditar(_sped_ba(), "EFD ICMS/IPI (Fiscal)", importacao_xml=imp)
    a = r.apontamentos[0]
    assert float(a.aliquota_interna) == 20.5
    assert float(a.difal_xml) == 15.0
    assert float(a.difal_devido) == 16.5
    assert a.nivel == "REVISAR"
    assert "pICMSUFDest XML=19" in a.evidencia
    assert "20.5" in a.evidencia
