from pathlib import Path
import tempfile

from src.services.auditoria_icms_st_piscofins_saidas_service import (
    AuditoriaICMSSTPISCOFINSSaidasService,
    STATUS_ALIQUOTA_ZERO,
    STATUS_CANDIDATO_XML,
)


def _c100(modelo: str, numero: str, chave: str, part: str = "CLI") -> str:
    return f"|C100|1|0|{part}|{modelo}|00|001|{numero}|{chave}|01072026|01072026|100|0|0|0|100|9|0|0|0|0|0||||1,65|7,60|0|0|"


def _c170(item: int, cfop: str = "5405", cst: str = "01", base: str = "100,00") -> str:
    campos = [
        "", "C170", str(item), f"P{item}", f"Produto {item}", "1", "UN", "100,00", "0", "0", "060", cfop,
        "", "", "", "", "", "", "", "", "", "", "", "", "", cst, base, "1,65", "", "", "1,65",
        cst, base, "7,60", "", "", "7,60", "61075", ""
    ]
    return "|".join(campos)


def _c175(cfop: str = "5405", cst: str = "01", base: str = "100,00") -> str:
    # |C175|CFOP|VL_OPR|VL_DESC|CST_PIS|VL_BC_PIS|ALIQ_PIS|...|VL_PIS|CST_COFINS|VL_BC_COFINS|ALIQ_COFINS|...|VL_COFINS|COD_CTA|INFO_COMPL|
    return f"|C175|{cfop}|100,00|0|{cst}|{base}|1,65|||1,65|{cst}|{base}|7,60|||7,60|61075||"


def test_pre_auditoria_separa_cfop_5405_e_aliquota_zero_sem_alterar_sped():
    chave1 = "31260700000000000100550010000000011000000001"
    chave2 = "31260700000000000100650010000000021000000002"
    with tempfile.TemporaryDirectory() as td:
        sped = Path(td) / "sped.txt"
        linhas = [
            "|0150|CLI|Cliente Teste|1058|00000000000100||||||||||",
            _c100("55", "1", chave1),
            _c170(1, "5405", "01", "100,00"),
            _c170(2, "5102", "01", "50,00"),
            _c100("65", "2", chave2, ""),
            _c175("5405", "04", "0"),
            _c175("5405", "01", "30,00"),
        ]
        sped.write_text("\n".join(linhas) + "\n", encoding="latin-1")
        antes = sped.read_bytes()
        resultado = AuditoriaICMSSTPISCOFINSSaidasService.pre_auditar(str(sped))
        assert sped.read_bytes() == antes
        assert len(resultado.registros) == 3
        assert [r.status for r in resultado.registros].count(STATUS_CANDIDATO_XML) == 2
        assert [r.status for r in resultado.registros].count(STATUS_ALIQUOTA_ZERO) == 1
        resumo = resultado.resumo()
        assert resumo["documentos_saida"] == 2
        assert resumo["documentos_cfop_5405"] == 2
        assert resumo["c170"] == 1
        assert resumo["c175"] == 2
        assert resumo["candidatos_xml"] == 2
        assert resumo["aliquota_zero"] == 1
        assert resultado.outras_operacoes["5102"] == 1


def test_c175_e_identificado_como_registro_analitico_sem_item():
    chave = "31260700000000000100650010000000101000000010"
    with tempfile.TemporaryDirectory() as td:
        sped = Path(td) / "sped.txt"
        sped.write_text(_c100("65", "10", chave, "") + "\n" + _c175() + "\n", encoding="latin-1")
        resultado = AuditoriaICMSSTPISCOFINSSaidasService.pre_auditar(str(sped))
        item = resultado.registros[0]
        assert item.registro == "C175"
        assert item.item == ""
        assert "analítico" in item.descricao


def test_etapa_2_fica_em_correcoes_e_botao_inicia_bloqueado():
    principal = Path("src/ui/janela_principal.py").read_text(encoding="utf-8")
    janela = Path("src/ui/janela_auditoria_icms_st_piscofins_saidas.py").read_text(encoding="utf-8")
    bloco = principal.split("def criar_painel_correcoes", 1)[1].split("def criar_painel_relatorios", 1)[0]
    assert "Exclusão ICMS-ST da base PIS/COFINS — Etapa 2" in bloco
    assert "abrir_auditoria_icms_st_piscofins_saidas" in principal
    assert "self.btn_aplicar = ttk.Button" in janela
    assert 'state="disabled"' in janela
    assert "_atualizar_estado_correcao" in janela
    assert "revisar_xml" in janela


def test_versao_17_8_19():
    from src.core.app_info import VERSAO_APP
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 20)
