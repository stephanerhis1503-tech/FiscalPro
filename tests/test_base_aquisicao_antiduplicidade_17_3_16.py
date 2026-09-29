from decimal import Decimal

from src.sped.exclusor_icms_creditos_piscofins import ExclusorICMSCreditosPISCOFINS
from src.sped.estatisticas import CalculadorEstatisticasSPED
from src.sped.indice import IndiceSPED


def linha(campos):
    return "|" + "|".join(campos) + "|\n"


def c100(chave):
    c=["C100"]+[""]*28
    c[1]="0"; c[2]="1"; c[4]="55"; c[5]="00"; c[7]="10"; c[8]=chave
    return c


def c170(base_pis, base_icms="100,00", icms="18,00"):
    c=["C170"]+[""]*35
    c[1]="1"; c[2]="ITEM1"; c[4]="1,00"; c[5]="UN"; c[6]="100,00"
    c[9]="000"; c[10]="2102"; c[12]=base_icms; c[13]="18,00"; c[14]=icms
    c[24]="50"; c[25]=base_pis; c[26]="1,6500"; c[29]="0,00"
    c[30]="50"; c[31]=base_pis; c[32]="7,6000"; c[35]="0,00"
    return c


def contrib(base):
    chave="31260712345678000190550010000000101234567890"
    return [
        linha(["0000","006","0","","","01072026","31072026","EMPRESA TESTE","12345678000190","MG","3100000","","00","2"]),
        linha(["0001","0"]), linha(["0110","1","1","1",""]),
        linha(c100(chave)), linha(c170(base)), linha(["9999","6"]),
    ]


def fiscal(base_pis, base_icms="100,00"):
    chave="31260712345678000190550010000000101234567890"
    return "".join([
        linha(["0000","020","0","01072026","31072026","EMPRESA TESTE","12345678000190","","MG","123","3100000","","","B","1"]),
        linha(c100(chave)), linha(c170(base_pis, base_icms=base_icms)), linha(["9999","4"]),
    ])


def estat(linhas):
    return CalculadorEstatisticasSPED().calcular(linhas, IndiceSPED().construir(linhas))


def test_fiscal_ja_liquido_nao_desconta_icms_de_novo(tmp_path):
    linhas=contrib("82,00")
    e=estat(linhas)
    arq=tmp_path/"fiscal.txt"
    arq.write_text(fiscal("82,00"), encoding="utf-8")
    a=ExclusorICMSCreditosPISCOFINS().analisar(linhas,e.tipo_sped,e.cnpj,e.periodo,arq)
    assert a.itens_alterar == 0
    assert len(a.itens_ja_excluidos) == 1
    assert a.total_icms_excluir == Decimal("0.00")
    assert not a.inconsistencias


def test_base_bruta_com_frete_preserva_frete_e_exclui_so_icms(tmp_path):
    # VL_ITEM=100, mas VL_BC_ICMS=101 por parcela acessória/frete rateado.
    # A base líquida correta é 101 - 18 = 83, e não 100 - 18 = 82.
    linhas=contrib("101,00")
    # ajusta a BC ICMS do C170 das contribuições apenas para refletir o exemplo
    partes=linhas[4].split('|'); partes[13]="101,00"; linhas[4]='|'.join(partes)
    e=estat(linhas)
    arq=tmp_path/"fiscal.txt"
    arq.write_text(fiscal("101,00", base_icms="101,00"), encoding="utf-8")
    a=ExclusorICMSCreditosPISCOFINS().analisar(linhas,e.tipo_sped,e.cnpj,e.periodo,arq)
    assert a.itens_alterar == 1
    assert a.itens_aptos[0].base_pis_nova == Decimal("83.00")
    assert a.itens_aptos[0].base_cofins_nova == Decimal("83.00")
    assert a.total_icms_excluir == Decimal("18.00")
