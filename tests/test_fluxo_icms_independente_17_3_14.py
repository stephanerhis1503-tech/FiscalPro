from collections import namedtuple

from src.sped.exclusor_icms_creditos_piscofins import ExclusorICMSCreditosPISCOFINS


def test_pendencia_preexistente_nao_e_tratada_como_erro_novo():
    A = namedtuple('A', 'registro campo categoria mensagem numero_linha')
    antes = [A('C170', 'CFOP', 'PGE', 'CFOP inválido.', 100)]
    depois = [A('C170', 'CFOP', 'PGE', 'CFOP inválido.', 98)]
    assert ExclusorICMSCreditosPISCOFINS._erros_novos(antes, depois) == []


def test_aumento_de_pendencia_continua_bloqueavel():
    A = namedtuple('A', 'registro campo categoria mensagem numero_linha')
    antes = [A('M105', 'VL_BC_PIS_NC', 'PGE', 'Base inválida.', 10)]
    depois = [
        A('M105', 'VL_BC_PIS_NC', 'PGE', 'Base inválida.', 10),
        A('M105', 'VL_BC_PIS_NC', 'PGE', 'Base inválida.', 11),
    ]
    novos = ExclusorICMSCreditosPISCOFINS._erros_novos(antes, depois)
    assert len(novos) == 1
