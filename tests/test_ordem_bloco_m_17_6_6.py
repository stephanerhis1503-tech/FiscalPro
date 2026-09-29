from src.sped.reapurador_bloco_m import ReapuradorBlocoM


def _c170(aliq_pis='0,0000', vl_pis='0,00', aliq_cofins='0,0000', vl_cofins='0,00'):
    campos = [''] * 36
    campos[0] = 'C170'
    campos[1] = '1'
    campos[2] = 'ITEM1'
    campos[6] = '100,00'
    campos[10] = '6102'
    campos[24] = '01'
    campos[25] = '100,00'
    campos[26] = aliq_pis
    campos[29] = vl_pis
    campos[30] = '01'
    campos[31] = '100,00'
    campos[32] = aliq_cofins
    campos[35] = vl_cofins
    return '|' + '|'.join(campos) + '|\n'


def test_m600_m610_criados_antes_de_m800_m810():
    antes = [
        _c170(),
        '|M001|0|\n',
        '|M200|10,00|0,00|0,00|10,00|0,00|0,00|10,00|0,00|0,00|0,00|0,00|10,00|\n',
        '|M210|01|606,06|606,06|0|0|606,06|1,6500|||10,00|0|0|0|0|10,00|\n',
        '|M800|04|100,00|1||\n',
        '|M810|999|100,00|1||\n',
        '|M990|6|\n',
    ]
    depois = list(antes)
    depois[0] = _c170('1,6500', '1,65', '7,6000', '7,60')

    r = ReapuradorBlocoM().sincronizar(antes, depois, 'EFD Contribuições')
    codigos = [linha.split('|')[1] for linha in r.linhas if linha.startswith('|M')]

    assert codigos.index('M600') < codigos.index('M610') < codigos.index('M800') < codigos.index('M810') < codigos.index('M990')


def test_pre_validador_aponta_m600_m610_depois_de_m800():
    from src.sped.pre_validador import PreValidadorPVA

    linhas = [
        '|0000|006|0|||01072026|31072026|EMPRESA|00000000000000|MG|||00|1|',
        '|M001|0|',
        '|M800|04|100,00|1||',
        '|M810|999|100,00|1||',
        '|M600|10,00|0,00|0,00|10,00|0,00|0,00|10,00|0,00|0,00|0,00|0,00|10,00|',
        '|M610|01|100,00|100,00|0|0|100,00|7,6000|||7,60|0|0|0|0|7,60|',
        '|M990|6|',
        '|9999|8|',
    ]
    r = PreValidadorPVA().validar(linhas, 'EFD Contribuições')
    encontrados = [e for e in r.erros if e.categoria == 'Hierarquia Bloco M' and e.registro in {'M600', 'M610'}]
    assert len(encontrados) == 2
