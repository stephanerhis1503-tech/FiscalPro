"""Cobertura inicial do RTC 1 - armazenamento local e importacao conservadora."""

from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.services.apuracao_assistida_local_service import ServicoApuracaoLocalRTC


EMPRESA = "12345678000199"
FORNECEDOR = "99887766000155"
CHAVE = "31261112345678000199550010000000011000000012"


def xml_nfe(*, emitente=EMPRESA, destinatario=FORNECEDOR, chave=CHAVE,
            emissao="2026-11-10", cbs="9.00", protocolo=True):
    retorno = f"""
    <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
      <NFe><infNFe Id="NFe{chave}" versao="4.00">
        <ide><nNF>1</nNF><dhEmi>{emissao}T10:00:00-03:00</dhEmi></ide>
        <emit><CNPJ>{emitente}</CNPJ><CRT>3</CRT></emit>
        <dest><CNPJ>{destinatario}</CNPJ></dest>
        <det nItem="1"><prod><cProd>A</cProd><xProd>Produto A</xProd>
        <NCM>87141000</NCM><CFOP>5102</CFOP></prod>
          <imposto><IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib>
          <gIBSCBS><vBC>100.00</vBC><gIBSUF><pIBSUF>0.1</pIBSUF>
          <vIBSUF>0.10</vIBSUF></gIBSUF>
          <gIBSMun><pIBSMun>0</pIBSMun><vIBSMun>0.00</vIBSMun></gIBSMun>
          <vIBS>0.10</vIBS><gCBS><pCBS>0.9</pCBS><vCBS>{cbs}</vCBS>
          </gCBS></gIBSCBS></IBSCBS></imposto>
        </det>
        <total><IBSCBSTot><vBCIBSCBS>100.00</vBCIBSCBS>
          <gIBS><vIBS>0.10</vIBS></gIBS>
          <gCBS><vCBS>{cbs}</vCBS></gCBS>
        </IBSCBSTot></total>
      </infNFe></NFe>
    """
    if protocolo:
        retorno += f"<protNFe><infProt><chNFe>{chave}</chNFe><cStat>100</cStat></infProt></protNFe>"
    return (retorno + "</nfeProc>").encode("utf-8")


@pytest.fixture
def servico(tmp_path):
    return ServicoApuracaoLocalRTC(tmp_path / "rtc.db")


def test_importa_saida_e_evita_duplicacao(servico, tmp_path):
    arquivo = tmp_path / "nfe.xml"
    arquivo.write_bytes(xml_nfe())
    primeira = servico.importar([arquivo], EMPRESA, "2026-11")
    segunda = servico.importar([arquivo], EMPRESA, "2026-11")
    assert primeira.importados == 1
    assert segunda.duplicados == 1
    docs = servico.listar(EMPRESA, "2026-11")
    assert len(docs) == 1
    assert docs[0]["direcao"] == "SAIDA"
    assert docs[0]["status_credito"] == "NAO_APLICAVEL"
    resumo = servico.resumo(EMPRESA, "2026-11")
    assert resumo["cbs_debito_xml"] == Decimal("9.00")


def test_compra_e_apenas_credito_potencial(servico, tmp_path):
    arquivo = tmp_path / "compra.xml"
    arquivo.write_bytes(xml_nfe(emitente=FORNECEDOR, destinatario=EMPRESA))
    resultado = servico.importar([arquivo], EMPRESA, "2026-11")
    assert resultado.importados == 1
    assert servico.listar(EMPRESA, "2026-11")[0]["status_credito"] == "POTENCIAL_NAO_APROPRIADO"
    assert servico.resumo(EMPRESA, "2026-11")["cbs_credito_potencial"] == Decimal("9.00")
    assert servico.resumo(EMPRESA, "2026-11")["cbs_debito_xml"] == 0


def test_competencia_divergente_nao_entra(servico, tmp_path):
    arquivo = tmp_path / "nfe.xml"
    arquivo.write_bytes(xml_nfe())
    resultado = servico.importar([arquivo], EMPRESA, "2026-10")
    assert resultado.importados == 0
    assert resultado.ignorados == 1


def test_cnpj_estranho_nao_entra(servico, tmp_path):
    arquivo = tmp_path / "nfe.xml"
    arquivo.write_bytes(xml_nfe())
    resultado = servico.importar([arquivo], "11111111000111", "2026-11")
    assert resultado.ignorados == 1
    assert servico.listar("11111111000111", "2026-11") == []


def test_conflito_de_chave_nao_sobrescreve(servico, tmp_path):
    arquivo = tmp_path / "nfe.xml"
    arquivo.write_bytes(xml_nfe())
    assert servico.importar([arquivo], EMPRESA, "2026-11").importados == 1
    arquivo.write_bytes(xml_nfe(cbs="8.00"))
    resultado = servico.importar([arquivo], EMPRESA, "2026-11")
    assert resultado.conflitos == 1
    assert servico.listar(EMPRESA, "2026-11")[0]["valor_cbs"] == "9.00"


def test_zip_e_xml_sem_protocolo_ficam_para_revisar(servico, tmp_path):
    pacote = tmp_path / "nfs.zip"
    with ZipFile(pacote, "w") as arquivo:
        arquivo.writestr("nfe.xml", xml_nfe(protocolo=False))
    assert servico.importar([pacote], EMPRESA, "2026-11").importados == 1
    doc = servico.listar(EMPRESA, "2026-11")[0]
    assert doc["status_conferencia"] == "REVISAR"
    assert doc["status_protocolo"] == "SEM_PROTOCOLO"


@pytest.mark.parametrize("competencia", ["2026-00", "2026-13", "11/2026", "", "2026-11 OR 1=1"])
def test_competencia_invalida(servico, competencia):
    with pytest.raises(ValueError):
        servico.listar(EMPRESA, competencia)


def test_nao_importa_documento_estranho(servico, tmp_path):
    arquivo = tmp_path / "evento.xml"
    arquivo.write_text("<procEventoNFe><evento/></procEventoNFe>", encoding="utf-8")
    assert servico.importar([arquivo], EMPRESA, "2026-11").ignorados == 1


def test_opcoes_empresas_mostram_cnpj_pendente_sem_liberar_pf():
    from src.ui.painel_apuracao_assistida_rtc import PainelApuracaoAssistidaRTC
    cadastros = [
        {"nome": "Mega Motos Trilha", "cnpj": "", "tipo_pessoa": "PJ", "ativa": 1},
        {"nome": "Mega Mix", "cnpj": "12345678000199", "tipo_pessoa": "PJ", "ativa": 1},
        {"nome": "Socio", "cnpj": "12345678901", "tipo_pessoa": "PF", "ativa": 1},
        {"nome": "Antiga", "cnpj": "", "tipo_pessoa": "PJ", "ativa": 0},
    ]
    opcoes = PainelApuracaoAssistidaRTC._opcoes_empresas(cadastros)
    assert len(opcoes) == 2
    assert "Mega Motos Trilha | CNPJ pendente" in opcoes
    assert "Mega Mix | 12345678000199" in opcoes


def test_complementa_protocolo_sem_duplicar_e_preserva_rastro(servico, tmp_path):
    import sqlite3
    arquivo = tmp_path / "nfe.xml"
    arquivo.write_bytes(xml_nfe(protocolo=False))
    assert servico.importar([arquivo], EMPRESA, "2026-11").importados == 1
    arquivo.write_bytes(xml_nfe(protocolo=True))
    retorno = servico.importar([arquivo], EMPRESA, "2026-11")
    assert retorno.atualizados == 1
    assert retorno.importados == 0
    assert retorno.conflitos == 0
    docs = servico.listar(EMPRESA, "2026-11")
    assert len(docs) == 1
    assert docs[0]["status_protocolo"] == "PROTOCOLO_100_150_XML"
    assert docs[0]["valor_cbs"] == "9.00"
    with sqlite3.connect(servico.banco) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM rtc_documentos_atualizacoes"
        ).fetchone()[0] == 1
    assert servico.importar([arquivo], EMPRESA, "2026-11").duplicados == 1


def test_protocolo_nao_atualiza_se_valor_diverge(servico, tmp_path):
    arquivo = tmp_path / "nfe.xml"
    arquivo.write_bytes(xml_nfe(protocolo=False))
    assert servico.importar([arquivo], EMPRESA, "2026-11").importados == 1
    arquivo.write_bytes(xml_nfe(protocolo=True, cbs="8.00"))
    retorno = servico.importar([arquivo], EMPRESA, "2026-11")
    assert retorno.conflitos == 1
    assert retorno.atualizados == 0
    doc = servico.listar(EMPRESA, "2026-11")[0]
    assert doc["status_protocolo"] == "SEM_PROTOCOLO"
    assert doc["valor_cbs"] == "9.00"


@pytest.mark.parametrize(
    "mes, ano, esperado",
    [
        ("Janeiro", "2026", "2026-01"),
        ("Outubro", "2026", "2026-10"),
        ("Dezembro", "2027", "2027-12"),
    ],
)
def test_competencia_por_seletores_mes_ano(mes, ano, esperado):
    from src.ui.painel_apuracao_assistida_rtc import PainelApuracaoAssistidaRTC
    assert PainelApuracaoAssistidaRTC._competencia_selecionada(mes, ano) == esperado


@pytest.mark.parametrize(
    "mes, ano",
    [
        ("", "2026"),
        ("Mês desconhecido", "2026"),
        ("Outubro", ""),
        ("Outubro", "20x6"),
        ("Outubro", "1999"),
    ],
)
def test_seletores_rejeitam_competencia_invalida(mes, ano):
    from src.ui.painel_apuracao_assistida_rtc import PainelApuracaoAssistidaRTC
    with pytest.raises(ValueError):
        PainelApuracaoAssistidaRTC._competencia_selecionada(mes, ano)


def test_filtro_visual_entrada_saida_revisar_e_busca():
    from src.ui.painel_apuracao_assistida_rtc import PainelApuracaoAssistidaRTC
    docs = [
        {"direcao": "SAIDA", "numero_nf": "121301", "chave_nfe": "31A", "status_conferencia": "CONFERIDO_XML"},
        {"direcao": "ENTRADA", "numero_nf": "9876", "chave_nfe": "31B", "status_conferencia": "REVISAR"},
        {"direcao": "SAIDA", "numero_nf": "121302", "chave_nfe": "31C", "status_conferencia": "REVISAR"},
    ]
    filtrar = PainelApuracaoAssistidaRTC._filtrar_documentos
    assert len(filtrar(docs, "Todas")) == 3
    assert [d["numero_nf"] for d in filtrar(docs, "Somente entradas")] == ["9876"]
    assert len(filtrar(docs, "Somente saídas")) == 2
    assert len(filtrar(docs, "Somente revisar")) == 2
    assert [d["numero_nf"] for d in filtrar(docs, "Todas", "12130")] == ["121301", "121302"]
    assert [d["numero_nf"] for d in filtrar(docs, "Somente entradas", "31B")] == ["9876"]
    with pytest.raises(ValueError):
        filtrar(docs, "tipo desconhecido")
