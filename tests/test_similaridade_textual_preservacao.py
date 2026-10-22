"""Otimiza somente texto: os resultados anteriores permanecem identicos."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from difflib import SequenceMatcher

import pytest

from src.services import ncm_validador_semantico_service as modulo_ncm
from src.services import similaridade_textual_service as texto
from src.services.base_ncm_nacional_service import BaseNCMNacionalService


PARES = [
    ("", ""), ("", "MOTOR"), ("MOTOR", ""),
    ("MOTOR", "MOTOR"), ("MOTOR", "MOTORES DE ARRANQUE"),
    ("TIDE", "DIET"), ("DIET", "TIDE"),
    ("PASTILHA FREIO", "PASTILHAS GUARNICOES FREIOS"),
    ("FIO", "FIACAO CONDUTORES"),
    ("INTER", "INTERRUPTORES"),
    ("FAROL", "SUPORTE FAROL"),
    ("\u00e7\u00e3\u00e9", "cae"),
    ("a b", "a  b"), ("a", "A"),
    ("a" * 300 + "b", "a" * 300 + "c"),
    ("M" * 4100, "MOTOR"),
]
CASOS = [
    ("PASTILHA FREIO TITAN FAN160", "68138110"),
    ("PASTILHA FREIO TITAN FAN160", "33059000"),
    ("TAMPA VALVULA BUTYL ALUM AZ 20PC", "76169900"),
    ("REGUL.RETIF. CBX 200 STRADA 94-02", "85118020"),
    ("SENS.INCL. CG 150 TITAN ESD 11-15", "85364100"),
    ("SUPORTE DE FAROL FACTOR", "85129000"),
    ("CHAVE TIC TAC", "85365090"),
    ("CORRENTE COMANDO YBR125", "73151100"),
    ("FILTRO AR MOTOR FAZER250", "84219999"),
    ("ADESIVO DECORATIVO MOTO", "39199090"),
    ("RETENTOR BENGALA YBR125", "40169300"),
    ("CAPACETE MOTO", "65061090"),
    ("MANOPLA BORRACHA", "40169990"),
    ("PARAFUSO ARRUELA", "73181500"),
    ("PECA GENERICA", "00000000"),
    ("", "85365090"),
]


def _sem_cache(produto, oficial):
    return SequenceMatcher(None, produto, oficial).ratio()


@pytest.fixture(autouse=True)
def cache_limpo():
    texto._similaridade_em_cache.cache_clear()
    yield
    texto._similaridade_em_cache.cache_clear()


@pytest.mark.parametrize("produto,oficial", PARES)
def test_proporcao_exatamente_igual_ao_algoritmo_anterior(produto, oficial):
    esperado = _sem_cache(produto, oficial)
    assert texto.similaridade_textual(produto, oficial) == esperado
    assert texto.similaridade_textual(produto, oficial) == esperado


def test_repeticao_reutiliza_calculo():
    texto.similaridade_textual("FREIO", "FREIOS")
    texto.similaridade_textual("FREIO", "FREIOS")
    estado = texto._similaridade_em_cache.cache_info()
    assert estado.misses == 1
    assert estado.hits == 1


def test_ordem_dos_textos_nao_e_trocada():
    ida = texto.similaridade_textual("TIDE", "DIET")
    volta = texto.similaridade_textual("DIET", "TIDE")
    assert ida == _sem_cache("TIDE", "DIET")
    assert volta == _sem_cache("DIET", "TIDE")
    assert ida != volta
    assert texto._similaridade_em_cache.cache_info().misses == 2


def test_alteracao_em_qualquer_texto_cria_nova_chave():
    pares = [("FREIO", "FREIOS"), ("FREIO", "FREIOS MOTOR"),
             ("FREIO MOTOR", "FREIOS")]
    for par in pares:
        assert texto.similaridade_textual(*par) == _sem_cache(*par)
    assert texto._similaridade_em_cache.cache_info().misses == len(pares)


def test_texto_longo_nao_e_retido():
    par = ("M" * (texto._MAX_CARACTERES + 1), "MOTOR")
    assert texto.similaridade_textual(*par) == _sem_cache(*par)
    assert texto._similaridade_em_cache.cache_info().currsize == 0


def test_cache_tem_limite_e_descarte_nao_altera_resposta():
    for indice in range(texto._MAX_ENTRADAS + 1):
        texto.similaridade_textual(str(indice), "MOTOR")
    assert texto._similaridade_em_cache.cache_info().currsize == texto._MAX_ENTRADAS
    assert texto.similaridade_textual("0", "MOTOR") == _sem_cache("0", "MOTOR")


def test_consultas_simultaneas_mantem_os_resultados():
    pares = PARES[:12] * 10
    with ThreadPoolExecutor(max_workers=4) as executor:
        resultados = list(executor.map(lambda par: texto.similaridade_textual(*par), pares))
    assert resultados == [_sem_cache(*par) for par in pares]


@pytest.fixture(scope="module")
def catalogo_oficial_em_memoria():
    # Le somente o pacote versionado. Nao consulta rede nem o banco do usuario.
    motor = modulo_ncm.NCMValidadorSemanticoService
    estado = (motor._cache_chave, motor._registros, motor._por_ncm, motor._por_token)
    catalogo = BaseNCMNacionalService._ler_payload()["ncm"]
    motor._instalar_catalogo_em_memoria(catalogo, ("PRESERVACAO", len(catalogo)))
    try:
        yield motor
    finally:
        motor._cache_chave, motor._registros, motor._por_ncm, motor._por_token = estado


@pytest.mark.parametrize("descricao,ncm", CASOS)
def test_resultados_completos_ncm_iguais_com_e_sem_cache(
    descricao, ncm, catalogo_oficial_em_memoria, monkeypatch
):
    motor = catalogo_oficial_em_memoria
    monkeypatch.setattr(motor, "_garantir_indice", classmethod(lambda cls: None))
    with monkeypatch.context() as original:
        original.setattr(modulo_ncm, "similaridade_textual", _sem_cache)
        esperado = asdict(motor.validar(descricao, ncm))
        busca = motor.pesquisar_descricao(descricao, limite=10)
    for _ in range(2):
        assert asdict(motor.validar(descricao, ncm)) == esperado
        assert motor.pesquisar_descricao(descricao, limite=10) == busca
