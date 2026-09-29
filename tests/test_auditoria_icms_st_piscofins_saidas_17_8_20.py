from pathlib import Path
import tempfile
import zipfile

from src.services.auditoria_icms_st_piscofins_saidas_service import (
    AuditoriaICMSSTPISCOFINSSaidasService,
    STATUS_ALIQUOTA_ZERO,
    STATUS_CORRIGIR_ST,
    STATUS_SEM_ST_XML,
    STATUS_XML_NAO_LOCALIZADO,
)


def _c100(modelo: str, numero: str, chave: str) -> str:
    return f"|C100|1|0|CLI|{modelo}|00|001|{numero}|{chave}|01072026|01072026|100|0|0|0|100|9|0|0|0|0|0||||1,65|7,60|0|0|"


def _c170(item: int, cst: str = "01", base: str = "100,00", valor: str = "100,00") -> str:
    campos = [
        "", "C170", str(item), f"P{item}", f"Produto {item}", "1", "UN", valor, "0", "0", "060", "5405",
        "", "", "", "", "", "", "", "", "", "", "", "", "", cst, base, "1,65", "", "", "1,65",
        cst, base, "7,60", "", "", "7,60", "61075", ""
    ]
    return "|".join(campos)


def _c175(cst: str = "01", base: str = "100,00", valor: str = "100,00") -> str:
    return f"|C175|5405|{valor}|0|{cst}|{base}|1,65|||1,65|{cst}|{base}|7,60|||7,60|61075||"


def _xml(chave: str, modelo: str, numero: str, itens: list[dict]) -> bytes:
    dets = []
    for i, x in enumerate(itens, start=1):
        cst = x.get("cst", "01")
        base = x.get("base", "100.00")
        st = x.get("st", "0.00")
        valor = x.get("valor", "100.00")
        codigo = x.get("codigo", f"P{i}")
        if cst in {"04", "06", "07"}:
            pis = f"<PIS><PISNT><CST>{cst}</CST></PISNT></PIS>"
            cof = f"<COFINS><COFINSNT><CST>{cst}</CST></COFINSNT></COFINS>"
        else:
            pis = f"<PIS><PISAliq><CST>{cst}</CST><vBC>{base}</vBC><pPIS>1.65</pPIS><vPIS>1.65</vPIS></PISAliq></PIS>"
            cof = f"<COFINS><COFINSAliq><CST>{cst}</CST><vBC>{base}</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS>"
        dets.append(
            f'''<det nItem="{i}"><prod><cProd>{codigo}</cProd><xProd>Produto {i}</xProd><CFOP>5405</CFOP><vProd>{valor}</vProd></prod>
            <imposto><ICMS><ICMS60><orig>0</orig><CST>60</CST><vBCSTRet>100.00</vBCSTRet><vICMSSTRet>{st}</vICMSSTRet></ICMS60></ICMS>{pis}{cof}</imposto></det>'''
        )
    texto = f'''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe{chave}"><ide><mod>{modelo}</mod><nNF>{numero}</nNF><tpNF>1</tpNF></ide>{''.join(dets)}</infNFe></NFe>
<protNFe><infProt><cStat>100</cStat></infProt></protNFe></nfeProc>'''
    return texto.encode("utf-8")


def _zip_xml(path: Path, nome: str, conteudo: bytes) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(nome, conteudo)


def test_xml_com_st_destacado_e_base_cheia_vira_correcao_sem_alterar_sped():
    chave = "31260700000000000100550010000000011000000001"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sped = td / "sped.txt"
        sped.write_text(_c100("55", "1", chave) + "\n" + _c170(1) + "\n", encoding="latin-1")
        antes = sped.read_bytes()
        pacote = td / "saida.zip"
        _zip_xml(pacote, f"Autorizados/{chave}-procNFe.xml", _xml(chave, "55", "1", [{"st": "10.00"}]))
        resultado = AuditoriaICMSSTPISCOFINSSaidasService.auditar_com_xml(str(sped), str(pacote))
        assert sped.read_bytes() == antes
        item = resultado.registros[0]
        assert item.status == STATUS_CORRIGIR_ST
        assert item.valor_st_xml == 10
        assert item.base_pis_sugerida == 90
        assert item.valor_pis_sugerido == item.valor_pis_sugerido.__class__("1.49")
        assert item.base_cofins_sugerida == 90
        assert item.valor_cofins_sugerido == item.valor_cofins_sugerido.__class__("6.84")


def test_xml_sem_valor_st_nao_gera_correcao_automatica():
    chave = "31260700000000000100550010000000021000000002"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sped = td / "sped.txt"
        sped.write_text(_c100("55", "2", chave) + "\n" + _c170(1) + "\n", encoding="latin-1")
        pacote = td / "saida.zip"
        _zip_xml(pacote, f"Autorizados/{chave}-procNFe.xml", _xml(chave, "55", "2", [{"st": "0.00"}]))
        item = AuditoriaICMSSTPISCOFINSSaidasService.auditar_com_xml(str(sped), str(pacote)).registros[0]
        assert item.status == STATUS_SEM_ST_XML
        assert item.base_pis_sugerida == 0


def test_c175_agrega_itens_do_xml_por_classe_tributaria():
    chave = "31260700000000000100650010000000031000000003"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sped = td / "sped.txt"
        sped.write_text(_c100("65", "3", chave) + "\n" + _c175(base="100,00", valor="100,00") + "\n", encoding="latin-1")
        pacote = td / "saida.zip"
        _zip_xml(
            pacote,
            f"Autorizados/{chave}-procNFe.xml",
            _xml(chave, "65", "3", [
                {"valor": "40.00", "base": "40.00", "st": "0.00", "codigo": "A"},
                {"valor": "60.00", "base": "60.00", "st": "0.00", "codigo": "B"},
            ]),
        )
        item = AuditoriaICMSSTPISCOFINSSaidasService.auditar_com_xml(str(sped), str(pacote)).registros[0]
        assert item.registro == "C175"
        assert item.status == STATUS_SEM_ST_XML
        assert item.base_pis_xml == 100
        assert item.valor_operacao_xml == 100


def test_aliquota_zero_continua_sem_impacto_mesmo_se_cst_xml_for_07():
    chave = "31260700000000000100550010000000041000000004"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sped = td / "sped.txt"
        sped.write_text(_c100("55", "4", chave) + "\n" + _c170(1, cst="04", base="0") + "\n", encoding="latin-1")
        pacote = td / "saida.zip"
        _zip_xml(pacote, f"Autorizados/{chave}-procNFe.xml", _xml(chave, "55", "4", [{"cst": "07", "base": "0", "st": "5.00"}]))
        item = AuditoriaICMSSTPISCOFINSSaidasService.auditar_com_xml(str(sped), str(pacote)).registros[0]
        assert item.status == STATUS_ALIQUOTA_ZERO


def test_documento_tributado_sem_xml_fica_para_revisao():
    chave = "31260700000000000100550010000000051000000005"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sped = td / "sped.txt"
        sped.write_text(_c100("55", "5", chave) + "\n" + _c170(1) + "\n", encoding="latin-1")
        pacote = td / "saida.zip"
        with zipfile.ZipFile(pacote, "w"):
            pass
        item = AuditoriaICMSSTPISCOFINSSaidasService.auditar_com_xml(str(sped), str(pacote)).registros[0]
        assert item.status == STATUS_XML_NAO_LOCALIZADO


def test_versao_17_8_20():
    from src.core.app_info import VERSAO_APP
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 20)
