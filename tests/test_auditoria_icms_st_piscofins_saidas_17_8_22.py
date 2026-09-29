from pathlib import Path
import tempfile
import zipfile

import pytest

from src.services.auditoria_icms_st_piscofins_saidas_service import (
    AuditoriaICMSSTPISCOFINSSaidasService,
    STATUS_CORRIGIR_ST,
)


def _c100(numero: str, chave: str) -> str:
    return (
        f"|C100|1|0|CLI|55|00|001|{numero}|{chave}|01072026|01072026|100|0|0|0|100|9|0|0|0|0|0||||1,65|7,60|0|0|"
    )


def _c170() -> str:
    campos = [
        "", "C170", "1", "P1", "Produto 1", "1", "UN", "100,00", "0", "0", "060", "5405",
        "", "", "", "", "", "", "", "", "", "", "", "", "", "01", "100,00", "1,65", "", "", "1,65",
        "01", "100,00", "7,60", "", "", "7,60", "61075", ""
    ]
    return "|".join(campos)


def _xml(chave: str) -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe{chave}"><ide><mod>55</mod><nNF>1</nNF><tpNF>1</tpNF></ide>
<det nItem="1"><prod><cProd>P1</cProd><xProd>Produto 1</xProd><CFOP>5405</CFOP><vProd>100.00</vProd></prod>
<imposto><ICMS><ICMS60><orig>0</orig><CST>60</CST><vBCSTRet>100.00</vBCSTRet><vICMSSTRet>10.00</vICMSSTRet></ICMS60></ICMS>
<PIS><PISAliq><CST>01</CST><vBC>100.00</vBC><pPIS>1.65</pPIS><vPIS>1.65</vPIS></PISAliq></PIS>
<COFINS><COFINSAliq><CST>01</CST><vBC>100.00</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS></imposto></det>
</infNFe></NFe><protNFe><infProt><cStat>100</cStat></infProt></protNFe></nfeProc>'''.encode("utf-8")


def _linhas_sped(chave: str) -> str:
    # Os registros M reproduzem uma apuração simples, suficiente para validar
    # a propagação determinística do delta das saídas corrigidas.
    return "\n".join([
        "|0000|006|0|01072026|31072026|EMPRESA TESTE|00000000000000|MG|000000000|||A|1|",
        "|0110|1|1|1||",
        _c100("1", chave),
        _c170(),
        "|M200|1,65|0|0|1,65|0|0|1,65|0|0|0|0|1,65|",
        "|M210|01|100,00|100,00|0|0|100,00|1,65|0||1,65|0|0|0|0|1,65|",
        "|M600|7,60|0|0|7,60|0|0|7,60|0|0|0|0|7,60|",
        "|M610|01|100,00|100,00|0|0|100,00|7,60|0||7,60|0|0|0|0|7,60|",
        "",
    ])


def _preparar(td: Path):
    chave = "31260700000000000100550010000000011000000001"
    sped = td / "sped.txt"
    sped.write_text(_linhas_sped(chave), encoding="latin-1")
    pacote = td / "xml.zip"
    with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"Autorizados/{chave}-procNFe.xml", _xml(chave))
    auditoria = AuditoriaICMSSTPISCOFINSSaidasService.auditar_com_xml(str(sped), str(pacote))
    return sped, pacote, auditoria


def test_aplicar_correcao_gera_novo_sped_preserva_original_e_reaudita_ok():
    with tempfile.TemporaryDirectory() as nome:
        td = Path(nome)
        sped, pacote, auditoria = _preparar(td)
        assert auditoria.resumo()["corrigir"] == 1
        antes = sped.read_bytes()
        saida = td / "corrigido.txt"

        resultado = AuditoriaICMSSTPISCOFINSSaidasService.aplicar_correcoes(
            str(sped), str(pacote), auditoria, str(saida)
        )

        assert sped.read_bytes() == antes
        assert saida.exists()
        assert resultado.itens_corrigidos == 1
        assert resultado.st_excluido == 10
        assert resultado.novos_erros_pre_pva == 0
        assert resultado.corrigir_apos == 0
        assert resultado.revisar_apos == 0
        assert resultado.ok_st_fora_apos == 1
        assert resultado.caminho_log.exists()

        linhas = saida.read_text(encoding="latin-1").splitlines()
        c170 = next(x for x in linhas if x.startswith("|C170|"))
        campos = c170.split("|")
        assert campos[26] == "90,00"  # VL_BC_PIS
        assert campos[30] == "1,49"   # VL_PIS
        assert campos[32] == "90,00"  # VL_BC_COFINS
        assert campos[36] == "6,84"   # VL_COFINS

        m210 = next(x for x in linhas if x.startswith("|M210|"))
        m610 = next(x for x in linhas if x.startswith("|M610|"))
        assert "|90,00|" in m210
        assert "|90,00|" in m610


def test_correcao_nao_pode_sobrescrever_sped_original():
    with tempfile.TemporaryDirectory() as nome:
        td = Path(nome)
        sped, pacote, auditoria = _preparar(td)
        with pytest.raises(ValueError, match="não pode ser sobrescrito"):
            AuditoriaICMSSTPISCOFINSSaidasService.aplicar_correcoes(
                str(sped), str(pacote), auditoria, str(sped)
            )


def test_correcao_bloqueia_enquanto_houver_revisao():
    with tempfile.TemporaryDirectory() as nome:
        td = Path(nome)
        sped, pacote, auditoria = _preparar(td)
        item = auditoria.registros[0]
        from dataclasses import replace
        from src.services.auditoria_icms_st_piscofins_saidas_service import (
            ResultadoPreAuditoriaSaidas,
            STATUS_XML_NAO_LOCALIZADO,
        )
        pendente = replace(item, status=STATUS_XML_NAO_LOCALIZADO)
        audit_pendente = ResultadoPreAuditoriaSaidas(
            registros=[item, pendente],
            documentos_saida=1,
            documentos_cfop_5405=1,
            outras_operacoes={},
            documentos_xml_autorizados=1,
            arquivos_xml_lidos=1,
            auditoria_com_xml=True,
        )
        with pytest.raises(ValueError, match="para revisar"):
            AuditoriaICMSSTPISCOFINSSaidasService.aplicar_correcoes(
                str(sped), str(pacote), audit_pendente, str(td / "corrigido.txt")
            )


def test_candidato_precisa_ser_c170_com_vinculo_alto():
    with tempfile.TemporaryDirectory() as nome:
        td = Path(nome)
        sped, pacote, auditoria = _preparar(td)
        from dataclasses import replace
        from src.services.auditoria_icms_st_piscofins_saidas_service import ResultadoPreAuditoriaSaidas
        item = next(x for x in auditoria.registros if x.status == STATUS_CORRIGIR_ST)
        inseguro = replace(item, confianca_vinculo="MÉDIA")
        audit_insegura = ResultadoPreAuditoriaSaidas(
            registros=[inseguro],
            documentos_saida=1,
            documentos_cfop_5405=1,
            outras_operacoes={},
            documentos_xml_autorizados=1,
            arquivos_xml_lidos=1,
            auditoria_com_xml=True,
        )
        with pytest.raises(ValueError, match="confiança ALTA"):
            AuditoriaICMSSTPISCOFINSSaidasService.aplicar_correcoes(
                str(sped), str(pacote), audit_insegura, str(td / "corrigido.txt")
            )


def test_versao_17_8_22():
    from src.core.app_info import VERSAO_APP
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 22)
