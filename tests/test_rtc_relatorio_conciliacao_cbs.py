"""Relatorio RTC: exportacao so de leitura e conciliacao na mesma base local."""
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from src.services.apuracao_assistida_local_service import ServicoApuracaoLocalRTC
from src.services.rtc_relatorio_conciliacao_cbs import ServicoRelatorioConciliacaoCBS


EMPRESA = "11809691000195"
CLIENTE = "12345678000199"
CHAVES = (
    "31261111809691000195550010001231541000000001",
    "31261111809691000195550010001231551000000002",
    "31261111809691000195550010001231561000000003",
)


def xml_teste(numero: int, chave: str, valor_cbs: str):
    return f"""<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
    <NFe><infNFe Id="NFe{chave}" versao="4.00">
        <ide><nNF>{numero}</nNF><dhEmi>2026-11-03T08:00:00-03:00</dhEmi></ide>
        <emit><CNPJ>{EMPRESA}</CNPJ><CRT>3</CRT></emit>
        <dest><CNPJ>{CLIENTE}</CNPJ></dest>
        <det nItem="1"><prod>
          <cProd>A{numero}</cProd><xProd>Produto {numero}</xProd>
          <NCM>87141000</NCM><CFOP>5102</CFOP></prod>
          <imposto><IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib>
          <gIBSCBS><vBC>100.00</vBC>
          <gIBSUF><pIBSUF>0.1</pIBSUF><vIBSUF>0.10</vIBSUF></gIBSUF>
          <gIBSMun><pIBSMun>0</pIBSMun><vIBSMun>0.00</vIBSMun></gIBSMun>
          <vIBS>0.10</vIBS><gCBS><pCBS>0.9</pCBS><vCBS>{valor_cbs}</vCBS></gCBS>
          </gIBSCBS></IBSCBS></imposto>
        </det>
        <total><IBSCBSTot><vBCIBSCBS>100.00</vBCIBSCBS>
          <gIBS><vIBS>0.10</vIBS></gIBS>
          <gCBS><vCBS>{valor_cbs}</vCBS></gCBS>
        </IBSCBSTot></total>
    </infNFe></NFe>
    <protNFe><infProt><chNFe>{chave}</chNFe><cStat>100</cStat></infProt></protNFe>
    </nfeProc>""".encode("utf-8")


class OficialFalso:
    def __init__(self, banco):
        self.banco = banco

    def conciliar(self, cnpj, competencia, tipo):
        assert (cnpj, competencia, tipo) == (EMPRESA, "2026-11", "debitos")
        return [
            {
                "chave": CHAVES[0], "nf": "123154", "tipo": "SAIDA",
                "cbs_xml": "0.90", "cbs_oficial": "0.90",
                "saldo_oficial": "0.90", "apropriado_oficial": "",
                "a_apropriar_oficial": "", "status": "CONFERE",
            },
            {
                "chave": CHAVES[1], "nf": "123155", "tipo": "SAIDA",
                "cbs_xml": "0.90", "cbs_oficial": "0.80",
                "saldo_oficial": "0.80", "apropriado_oficial": "",
                "a_apropriar_oficial": "", "status": "DIFERENCA_REVISAR",
            },
            {
                "chave": CHAVES[2], "nf": "123156", "tipo": "SAIDA",
                "cbs_xml": "0.90", "cbs_oficial": "",
                "saldo_oficial": "", "apropriado_oficial": "",
                "a_apropriar_oficial": "", "status": "SEM_DADO_NESTE_RETORNO",
            },
        ]

    def resumo_competencias(self, cnpj, tipo):
        return [{
            "competencia": "2026-11", "registros": 2, "candidatos_xml": 2
        }]


@pytest.fixture
def relatorio(tmp_path):
    banco = tmp_path / "teste_rtc.db"
    svc = ServicoApuracaoLocalRTC(banco)
    for numero, chave in enumerate(CHAVES, start=123154):
        arquivo = tmp_path / f"{numero}.xml"
        arquivo.write_bytes(xml_teste(numero, chave, "0.90"))
        assert svc.importar([arquivo], EMPRESA, "2026-11").importados == 1
    return ServicoRelatorioConciliacaoCBS(OficialFalso(banco))


def test_reconcilia_todos_sem_limite_da_grade_e_sem_registro_falso(relatorio):
    dados = relatorio.preparar(EMPRESA, "2026-11", "debitos", "Mega Motos Trilha")
    assert dados["resumo"]["xmls"] == 3
    assert dados["resumo"]["oficiais"] == 2
    assert dados["resumo"]["comparaveis"] == 2
    assert dados["resumo"]["conferem"] == 1
    assert dados["resumo"]["diferencas"] == 1
    assert dados["resumo"]["sem_retorno"] == 1
    assert dados["linhas"][0]["diferenca"] == Decimal("0.00")
    assert dados["linhas"][1]["diferenca"] == Decimal("0.10")
    assert dados["linhas"][2]["diferenca"] is None
    assert "receita" in dados["linhas"][2]["observacao"].lower()


def test_excel_gerado_com_abas_revisar_e_sem_retorno(relatorio, tmp_path):
    arquivo = relatorio.gerar_excel(
        EMPRESA, "2026-11", "debitos", tmp_path / "conciliacao.xlsx", "Mega"
    )
    wb = load_workbook(arquivo)
    assert wb.sheetnames == ["Resumo", "Conciliacao", "Revisar", "Sem retorno"]
    assert wb["Resumo"]["B11"].value == 3
    aba = wb["Conciliacao"]
    assert [aba[f"K{n}"].value for n in (7, 8, 9)] == [
        "CONFERE", "DIFERENCA_REVISAR", "SEM_DADO_NESTE_RETORNO"
    ]
    assert aba["E8"].value == pytest.approx(0.9)
    assert aba["F8"].value == pytest.approx(0.8)
    assert aba["G8"].value == "=IF(OR(E8=\"\",F8=\"\"),\"\",ROUND(E8-F8,2))"
    assert aba["F9"].value is None
    assert wb["Revisar"]["B7"].value == "123155"
    assert wb["Sem retorno"]["B7"].value == "123156"
    assert aba["D7"].value == CHAVES[0]


def test_pdf_capa_e_anexo_por_documento(relatorio, tmp_path):
    destino = relatorio.gerar_pdf(
        EMPRESA, "2026-11", "debitos", tmp_path / "conciliacao.pdf",
        "Mega Motos Trilha",
    )
    paginas = PdfReader(destino).pages
    assert len(paginas) == 2
    capa = paginas[0].extract_text()
    assert "FiscalPro" in capa
    assert "Resumo executivo" in capa
    assert "1" in capa
    anexo = paginas[1].extract_text()
    for nf in ("123154", "123155", "123156"):
        assert nf in anexo
    assert "SEM RETORNO" in anexo
    assert "DIFERENCA" in anexo


def test_nao_aceita_extensao_incorreta_ou_competencia_sem_xml(relatorio, tmp_path):
    with pytest.raises(ValueError, match="formato"):
        relatorio.gerar_pdf(
            EMPRESA, "2026-11", "debitos", tmp_path / "errado.xlsx",
        )
    with pytest.raises(ValueError, match="Nao ha XMLs"):
        relatorio.gerar_excel(
            EMPRESA, "2026-10", "debitos", tmp_path / "vazio.xlsx",
        )
