from __future__ import annotations

from pathlib import Path

import pytest

from src.sped.auditor_difal import AuditorDIFALSPED
from src.sped.auditor_tributario import ImportadorXMLNFe


CHAVE = "31260812345678000190550010000012341000012345"


def _xml(difal="6.00", fcp="2.00", ind_final="1", ind_ie="9") -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{CHAVE}" versao="4.00">
      <ide><cUF>31</cUF><natOp>VENDA</natOp><mod>55</mod><serie>1</serie><nNF>1234</nNF><idDest>2</idDest><indFinal>{ind_final}</indFinal></ide>
      <emit><CNPJ>12345678000190</CNPJ><enderEmit><UF>MG</UF></enderEmit></emit>
      <dest><CPF>12345678909</CPF><enderDest><UF>SP</UF></enderDest><indIEDest>{ind_ie}</indIEDest></dest>
      <det nItem="1">
        <prod><cProd>P1</cProd><xProd>PECA</xProd><NCM>85122011</NCM><CFOP>6108</CFOP><uCom>UN</uCom><qCom>1</qCom><vUnCom>100.00</vUnCom><vProd>100.00</vProd></prod>
        <imposto>
          <ICMS><ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>100.00</vBC><pICMS>12.00</pICMS><vICMS>12.00</vICMS></ICMS00></ICMS>
          <ICMSUFDest><vBCUFDest>100.00</vBCUFDest><vBCFCPUFDest>100.00</vBCFCPUFDest><pFCPUFDest>2.00</pFCPUFDest><pICMSUFDest>18.00</pICMSUFDest><pICMSInter>12.00</pICMSInter><pICMSInterPart>100.00</pICMSInterPart><vFCPUFDest>{fcp}</vFCPUFDest><vICMSUFDest>{difal}</vICMSUFDest><vICMSUFRemet>0.00</vICMSUFRemet></ICMSUFDest>
          <PIS><PISAliq><CST>01</CST><vBC>100.00</vBC><pPIS>1.65</pPIS><vPIS>1.65</vPIS></PISAliq></PIS>
          <COFINS><COFINSAliq><CST>01</CST><vBC>100.00</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS>
        </imposto>
      </det>
      <total><ICMSTot><vNF>100.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
</nfeProc>'''.encode()


def _sped(c101: str | None = "|C101|2,00|6,00|0,00|") -> list[str]:
    linhas = [
        "|0000|020|0|01082026|31082026|EMPRESA TESTE|12345678000190||MG|123|3106200|||B|1|\n",
        "|0150|CLI|CLIENTE|1058||12345678909||3550308||RUA A|1|||\n",
        f"|C100|1|0|CLI|55|00|1|1234|{CHAVE}|01082026|01082026|100,00|0|0,00|0,00|100,00|0|0,00|0,00|0,00|100,00|12,00|0,00|0,00|0,00|1,65|7,60|0,00|0,00|\n",
        "|C190|000|6108|12,00|100,00|100,00|12,00|0,00|0,00|0,00|0,00||\n",
    ]
    if c101:
        linhas.insert(3, c101 + "\n")
    return linhas


def _importacao(tmp_path: Path, xml: bytes | None = None):
    arquivo = tmp_path / "nfe.xml"
    arquivo.write_bytes(xml or _xml())
    return ImportadorXMLNFe().importar([arquivo])


def test_importador_extrai_contexto_e_icmsufdest(tmp_path):
    imp = _importacao(tmp_path)
    doc = imp.documentos[CHAVE]
    assert doc.uf_emitente == "MG"
    assert doc.uf_destinatario == "SP"
    assert doc.id_destino == "2"
    assert doc.consumidor_final is True
    assert doc.indicador_ie_dest == "9"
    assert doc.destinatario_contribuinte is False
    assert doc.itens[0].tem_icms_uf_dest is True
    assert doc.itens[0].base_difal == 100.0
    assert doc.itens[0].valor_icms_destino == 6.0
    assert doc.itens[0].valor_fcp_destino == 2.0


def test_c101_igual_xml_fica_ok(tmp_path):
    r = AuditorDIFALSPED().auditar(
        _sped(), "EFD ICMS/IPI (Fiscal)", "EMPRESA", "08/2026", _importacao(tmp_path)
    )
    assert r.total_final_nao_contribuinte_confirmado == 1
    assert r.total_com_c101 == 1
    assert r.erros == 0
    assert r.ok == 1
    assert float(r.valor_difal_xml) == 6.0
    assert float(r.valor_fcp_xml) == 2.0


def test_xml_confirmado_sem_c101_e_erro(tmp_path):
    r = AuditorDIFALSPED().auditar(
        _sped(None), "EFD ICMS/IPI (Fiscal)", importacao_xml=_importacao(tmp_path)
    )
    assert r.total_sem_c101_quando_confirmado == 1
    assert r.erros == 1
    assert r.apontamentos[0].nivel == "ERRO"
    assert "não possui registro C101" in r.apontamentos[0].mensagem


def test_c101_divergente_do_xml_e_erro(tmp_path):
    r = AuditorDIFALSPED().auditar(
        _sped("|C101|0,00|3,00|0,00|"), "EFD ICMS/IPI (Fiscal)", importacao_xml=_importacao(tmp_path)
    )
    assert r.erros == 1
    assert "divergem" in r.apontamentos[0].mensagem


def test_sem_xml_cfop_6108_e_revisao_nao_correcao():
    r = AuditorDIFALSPED().auditar(_sped(None), "EFD ICMS/IPI (Fiscal)")
    assert r.total_candidatos_sem_xml == 1
    assert r.erros == 0
    assert r.avisos == 1
    assert r.apontamentos[0].nivel == "REVISAR"


def test_nao_aplica_em_efd_contribuicoes():
    with pytest.raises(RuntimeError, match="somente na EFD ICMS/IPI"):
        AuditorDIFALSPED().auditar(_sped(), "EFD Contribuições")
