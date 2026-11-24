"""PR27: evidencia ST do XML nao cria conclusao tributaria nem altera banco."""
from types import SimpleNamespace
from openpyxl import load_workbook

from src.services.conferencia_st_xml_service import conferir_item_st_xml
from src.services.ficha_assistida_sped_service import FichaAssistidaSPEDService
from src.sped.auditor_tributario import ImportadorXMLNFe


CTX = {
    "ncm": "87141000", "operacao": "ENTRADA",
    "finalidade": "USO E CONSUMO", "uf_origem": "MG", "uf_destino": "MG",
}


def item(**kwargs):
    base = {
        "numero_item": "1", "codigo": "P1", "ncm": "87141000",
        "cest": "", "cfop": "5405", "cst_icms": "60",
        "valores_st_xml": {},
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def doc():
    return SimpleNamespace(arquivo_origem="nota.xml")


def test_xml_ausente_e_tag_ausente_nao_equivalem_a_zero():
    assert "AINDA NAO IMPORTADO" in conferir_item_st_xml(CTX)["st_xml_status"]
    assert "SEM XML CORRESPONDENTE" in conferir_item_st_xml(
        CTX, xml_importado=True
    )["st_xml_status"]
    assert "SEM TAG ST" in conferir_item_st_xml(
        CTX, doc(), item(), xml_importado=True
    )["st_xml_status"]
    assert "SEM VALOR" in conferir_item_st_xml(
        CTX, doc(), item(valores_st_xml={"vICMSST": "0.00"}), xml_importado=True
    )["st_xml_status"]


def test_st_destacada_retida_e_ambas_geram_situacoes_distintas():
    a = conferir_item_st_xml(
        CTX, doc(), item(valores_st_xml={"vICMSST": "12.30"}), xml_importado=True
    )
    b = conferir_item_st_xml(
        CTX, doc(), item(valores_st_xml={"vICMSSTRet": "8.00"}), xml_importado=True
    )
    c = conferir_item_st_xml(
        CTX, doc(), item(valores_st_xml={"vICMSST": "12.30", "vICMSSTRet": "8.00"}),
        xml_importado=True,
    )
    assert "ST DESTACADA" in a["st_xml_status"]
    assert "RETIDA ANTERIORMENTE" in b["st_xml_status"]
    assert c["st_xml_status"].startswith("REVISAR")
    assert "NAO DETERMINADA" in a["st_xml_responsabilidade"]


def test_xml_inconsistente_bloqueia_conclusao():
    a = conferir_item_st_xml(CTX, doc(), item(valores_st_xml={"vICMSST": "-1"}), xml_importado=True)
    b = conferir_item_st_xml(CTX, doc(), item(ncm="83011000"), xml_importado=True)
    c = conferir_item_st_xml(CTX, doc(), item(), vinculo_duvidoso=True, xml_importado=True)
    assert all(x["st_xml_status"].startswith("DIVERGENCIA") for x in (a, b, c))


def test_outros_contextos_nao_recebem_diagnostico_st_interno():
    assert conferir_item_st_xml({**CTX, "uf_origem": "SP"}, doc(), item(), xml_importado=True) == {}
    assert conferir_item_st_xml({**CTX, "finalidade": "REVENDA"}, doc(), item(), xml_importado=True) == {}


def test_leitura_xml_conserva_tags_st_em_vez_de_inferir_valor():
    chave = "31" + "2610" + "12345678000199" + "55" + "001" + "000000123" + "1" + "00000001" + "0"
    xml = f'''<nfeProc><NFe><infNFe Id="NFe{chave}">
      <ide><mod>55</mod><nNF>123</nNF><serie>1</serie></ide>
      <emit><CNPJ>12345678000199</CNPJ></emit>
      <dest><CNPJ>11809691000195</CNPJ></dest>
      <det nItem="1"><prod><cProd>P1</cProd><xProd>Uso</xProd>
      <NCM>87141000</NCM><CFOP>5405</CFOP><vProd>100.00</vProd></prod>
      <imposto><ICMS><ICMS60><orig>0</orig><CST>60</CST>
      <vBCSTRet>100.00</vBCSTRet><vICMSSTRet>15.25</vICMSSTRet>
      </ICMS60></ICMS></imposto></det></infNFe></NFe></nfeProc>'''
    documento = ImportadorXMLNFe()._interpretar_xml(xml.encode(), "exemplo.xml")
    assert documento is not None
    valores = documento.itens[0].valores_st_xml
    assert valores["vICMSSTRet"] == "15.25"
    assert valores["vBCSTRet"] == "100.00"
    assert "vICMSST" not in valores


def test_excel_mantem_item_por_nota_com_status(tmp_path):
    refs = []
    for n, valor in [(1, "12.30"), (2, "0")]:
        refs.append({
            **CTX, "descricao_sped": "PECA TESTE", "empresa": "EMPRESA TESTE",
            "regime": "LUCRO REAL", "codigo_produto": "P1",
            "data_operacao": "2026-10-12", "cfop_sped": "1556",
            "contribuinte": "SIM", "nota": str(n), "item": "1",
            "chave": str(n) * 44,
            **conferir_item_st_xml(
                CTX, doc(), item(valores_st_xml={"vICMSST": valor}),
                xml_importado=True,
            ),
        })
    propostas = FichaAssistidaSPEDService.preparar(
        SimpleNamespace(referencias_fiscais=refs)
    )
    assert len(propostas) == 1
    assert len(propostas[0].evidencias_xml_st) == 2
    arquivo = FichaAssistidaSPEDService.exportar(propostas, tmp_path / "triagem.xlsx")
    wb = load_workbook(arquivo, read_only=True)
    assert wb.sheetnames == [
        "Propostas para revisao", "Triagem ST condicional", "Conferencia ST XML"
    ]
    resumo = wb.worksheets[0]
    assert resumo["AG1"].value == "Conferencia documental ST no XML"
    detalhes = wb["Conferencia ST XML"]
    assert detalhes.max_row == 3
    assert detalhes["M2"].value != detalhes["M3"].value
    assert detalhes["X2"].value == "12.30"
    assert detalhes["X3"].value == "0"


def test_cfop_5929_vinculado_a_cupom_nao_acusa_falta_de_st():
    from src.services.ficha_assistida_sped_service import _conclusao_st_xml
    sem_tags = conferir_item_st_xml(
        CTX, doc(), item(cfop="5929"), xml_importado=True
    )
    assert sem_tags["st_xml_status"].startswith("INFORMATIVO - CFOP 5929")
    assert "cupom" in sem_tags["st_xml_acao"].lower()
    assert _conclusao_st_xml(sem_tags["st_xml_status"])[0] == "6 - INFORMATIVO"


def test_cfop_5929_preserva_st_retida_sem_gerar_alerta():
    r = conferir_item_st_xml(
        CTX, doc(), item(cfop="5929", valores_st_xml={"vICMSSTRet": "33.09"}),
        xml_importado=True,
    )
    assert r["st_xml_status"].startswith("INFORMATIVO - CFOP 5929")
    assert r["st_xml_vICMSSTRet"] == "33.09"
    assert "novo recolhimento" in r["st_xml_acao"].lower()


def test_cfop_5929_nao_oculta_divergencia_ncm_nem_st_destacada():
    ncm = conferir_item_st_xml(
        CTX, doc(), item(cfop="5929", ncm="83011000"), xml_importado=True
    )
    destaque = conferir_item_st_xml(
        CTX, doc(), item(cfop="5929", valores_st_xml={"vICMSST": "10.00"}),
        xml_importado=True,
    )
    assert ncm["st_xml_status"].startswith("DIVERGENCIA")
    assert destaque["st_xml_status"].startswith("REVISAR")
