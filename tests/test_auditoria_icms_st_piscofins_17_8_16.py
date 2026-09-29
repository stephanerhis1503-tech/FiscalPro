from decimal import Decimal
from pathlib import Path
import tempfile
import zipfile

from src.services.auditoria_icms_st_piscofins_service import (
    AuditoriaICMSSTPISCOFINSService,
    STATUS_OK,
    STATUS_POSSIVEL_ST,
    STATUS_REVISAR_CST,
    STATUS_REVISAR_ICMS,
    STATUS_SEM_CREDITO,
    STATUS_SEM_CREDITO_ZERO,
)


def _xml(chave: str, itens: list[dict]) -> str:
    dets = []
    for idx, i in enumerate(itens, 1):
        pis = i.get("pis", "01")
        base_xml = i.get("base_xml", "100.00")
        if Decimal(str(base_xml)) > 0:
            bloco_pis = f"<PIS><PISAliq><CST>{pis}</CST><vBC>{base_xml}</vBC><pPIS>1.65</pPIS><vPIS>1.65</vPIS></PISAliq></PIS>"
            bloco_cof = f"<COFINS><COFINSAliq><CST>{pis}</CST><vBC>{base_xml}</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS>"
        else:
            bloco_pis = f"<PIS><PISNT><CST>{pis}</CST></PISNT></PIS>"
            bloco_cof = f"<COFINS><COFINSNT><CST>{pis}</CST></COFINSNT></COFINS>"
        dets.append(f'''<det nItem="{idx}"><prod><cProd>{i.get('code', f'P{idx}')}</cProd><xProd>Produto {idx}</xProd><NCM>87141000</NCM><CFOP>5403</CFOP><qCom>1.0000</qCom><vProd>{i.get('vitem','150.00')}</vProd></prod><imposto><ICMS><ICMS10><orig>0</orig><CST>10</CST><vICMS>{i.get('vicms','10.00')}</vICMS><vICMSST>{i.get('vst','20.00')}</vICMSST></ICMS10></ICMS>{bloco_pis}{bloco_cof}</imposto></det>''')
    return f'''<?xml version="1.0" encoding="utf-8"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe{chave}"><ide><serie>1</serie><nNF>123</nNF><dhEmi>2026-07-10T10:00:00-03:00</dhEmi></ide><emit><CNPJ>00000000000100</CNPJ><xNome>Fornecedor Teste</xNome><CRT>3</CRT></emit>{''.join(dets)}</infNFe></NFe></nfeProc>'''


def _c170(num, base, cst="50", code=None, vitem="150,00"):
    code = code or f"P{num}"
    campos = ["", "C170", str(num), code, f"Produto {num}", "1", "UN", vitem, "0", "0", "060", "1403", "10"]
    campos += [""] * 12
    campos += [cst, str(base).replace(".", ","), "1,65", "", "", "1,65", cst, str(base).replace(".", ","), "7,6", "", "", "7,60", "40020", ""]
    return "|".join(campos)


def test_classifica_cinco_cenarios_sem_alterar_arquivos():
    chave = "31260700000000000100550010000001231000000123"
    itens_xml = [
        {"base_xml": "100.00", "vicms": "10.00", "vst": "20.00"},
        {"base_xml": "100.00", "vicms": "10.00", "vst": "20.00"},
        {"base_xml": "100.00", "vicms": "10.00", "vst": "20.00"},
        {"base_xml": "0.00", "pis": "04", "vicms": "10.00", "vst": "20.00"},
        {"base_xml": "100.00", "vicms": "10.00", "vst": "20.00"},
    ]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        zpath = td / "xmls.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("nfe.xml", _xml(chave, itens_xml))
        sped = td / "sped.txt"
        linhas = [
            f"|C100|0|1|FORN|55|00|001|123|{chave}|10072026|10072026|750|0|0|0|750|0|0|0|0|0|0|0|0|0|0|0|0|",
            _c170(1, "100.00"),          # OK
            _c170(2, "0.00", "73"),    # sem crédito
            _c170(3, "110.00"),         # diferença = ICMS próprio
            _c170(4, "150.00"),         # XML sem base, SPED com crédito
            _c170(5, "120.00"),         # diferença = ST
        ]
        sped.write_text("\n".join(linhas) + "\n", encoding="latin-1")
        original = sped.read_bytes()
        resultado = AuditoriaICMSSTPISCOFINSService.auditar(str(sped), str(zpath))
        assert [i.status for i in resultado.itens] == [
            STATUS_OK,
            STATUS_SEM_CREDITO,
            STATUS_REVISAR_ICMS,
            STATUS_SEM_CREDITO_ZERO,
            STATUS_POSSIVEL_ST,
        ]
        assert sped.read_bytes() == original


def test_aceita_pasta_de_xmls():
    chave = "31260700000000000100550010000004561000000456"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "nfe.xml").write_text(_xml(chave, [{"base_xml": "100.00"}]), encoding="utf-8")
        sped = td / "sped.txt"
        sped.write_text(
            f"|C100|0|1|FORN|55|00|001|456|{chave}|10072026|10072026|150|0|0|0|150|0|0|0|0|0|0|0|0|0|0|0|0|\n"
            + _c170(1, "100.00") + "\n",
            encoding="latin-1",
        )
        resultado = AuditoriaICMSSTPISCOFINSService.auditar(str(sped), str(td))
        assert resultado.resumo()["itens_st"] == 1
        assert resultado.resumo()["ok"] == 1


def test_modulo_fica_em_correcoes_e_correcao_permanece_bloqueada():
    principal = Path("src/ui/janela_principal.py").read_text(encoding="utf-8")
    janela = Path("src/ui/janela_auditoria_icms_st_piscofins.py").read_text(encoding="utf-8")
    bloco = principal.split("def criar_painel_correcoes", 1)[1].split("def criar_painel_relatorios", 1)[0]
    assert "Exclusão ICMS-ST da base PIS/COFINS — Etapa 1" in bloco
    assert "abrir_auditoria_icms_st_piscofins" in principal
    assert 'text="Aplicar correções no SPED", state="disabled"' in janela
    assert "não corrige nem sobrescreve o SPED" in janela


def test_versao_17_8_18_cumulativa():
    from src.core.app_info import VERSAO_APP
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 18)


def test_base_zero_com_cst_nao_reconhecido_continua_em_revisao():
    chave = "31260700000000000100550010000007891000000789"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        zpath = td / "xmls.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("nfe.xml", _xml(chave, [{"base_xml": "0.00", "pis": "07", "vicms": "10.00", "vst": "20.00"}]))
        sped = td / "sped.txt"
        sped.write_text(
            f"|C100|0|1|FORN|55|00|001|789|{chave}|10072026|10072026|150|0|0|0|150|0|0|0|0|0|0|0|0|0|0|0|0|\n"
            + _c170(1, "150.00") + "\n",
            encoding="latin-1",
        )
        resultado = AuditoriaICMSSTPISCOFINSService.auditar(str(sped), str(zpath))
        assert resultado.itens[0].status == STATUS_REVISAR_CST


def test_resumo_soma_aliquota_zero_como_sem_credito():
    chave = "31260700000000000100550010000009991000000999"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        zpath = td / "xmls.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("nfe.xml", _xml(chave, [{"base_xml": "0.00", "pis": "04", "vicms": "10.00", "vst": "20.00"}]))
        sped = td / "sped.txt"
        sped.write_text(
            f"|C100|0|1|FORN|55|00|001|999|{chave}|10072026|10072026|150|0|0|0|150|0|0|0|0|0|0|0|0|0|0|0|0|\n"
            + _c170(1, "150.00") + "\n",
            encoding="latin-1",
        )
        resultado = AuditoriaICMSSTPISCOFINSService.auditar(str(sped), str(zpath))
        resumo = resultado.resumo()
        assert resultado.itens[0].status == STATUS_SEM_CREDITO_ZERO
        assert resumo["sem_credito"] == 1
        assert resumo["sem_credito_aliquota_zero"] == 1
        assert resumo["revisar_cst"] == 0
        assert resumo["itens_com_credito"] == 0
