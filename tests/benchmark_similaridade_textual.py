"""Medicao reproduzivel da busca NCM; nao mede a auditoria completa.

Execute: python -m tests.benchmark_similaridade_textual
O pacote oficial e lido localmente; nenhum banco ou arquivo do usuario e escrito.
"""

from dataclasses import asdict
from difflib import SequenceMatcher
import json
from statistics import median
from time import perf_counter

from src.services import ncm_validador_semantico_service as modulo
from src.services.base_ncm_nacional_service import BaseNCMNacionalService
from src.services.similaridade_textual_service import (
    _similaridade_em_cache, similaridade_textual,
)


DESCRICOES = (
    "PASTILHA FREIO TITAN FAN160", "TAMPA VALVULA BUTYL ALUM AZ 20PC",
    "REGUL.RETIF. CBX 200 STRADA 94-02", "SENS.INCL. CG 150 TITAN ESD 11-15",
    "SUPORTE DE FAROL FACTOR", "CHAVE TIC TAC", "CORRENTE COMANDO YBR125",
    "FILTRO AR MOTOR FAZER250", "ADESIVO DECORATIVO MOTO",
    "RETENTOR BENGALA YBR125", "CAPACETE MOTO", "MANOPLA BORRACHA",
    "PARAFUSO ARRUELA", "PECA GENERICA",
)


def medir() -> dict:
    motor = modulo.NCMValidadorSemanticoService
    estado = (motor._cache_chave, motor._registros, motor._por_ncm, motor._por_token)
    funcao_original = modulo.similaridade_textual
    catalogo = BaseNCMNacionalService._ler_payload()["ncm"]
    motor._instalar_catalogo_em_memoria(catalogo, ("BENCHMARK", len(catalogo)))
    tempos = {"antes": [], "depois": []}
    resultados = {}
    funcoes = {
        "antes": lambda a, b: SequenceMatcher(None, a, b).ratio(),
        "depois": similaridade_textual,
    }
    try:
        # Alterna a ordem e inclui aquecimento do cache dentro de cada medicao.
        for rodada in range(7):
            ordem = ("antes", "depois") if rodada % 2 == 0 else ("depois", "antes")
            for modo in ordem:
                modulo.similaridade_textual = funcoes[modo]
                _similaridade_em_cache.cache_clear()
                inicio = perf_counter()
                saidas = []
                for _ in range(20):
                    for descricao in DESCRICOES:
                        tokens = motor._tokens(descricao, produto=True)
                        candidatos = motor._candidatos(tokens)
                        saidas.append([asdict(c) for c in candidatos])
                tempos[modo].append(perf_counter() - inicio)
                if "antes" in resultados:
                    assert saidas == resultados["antes"], "Resultado NCM divergente"
                resultados[modo] = saidas
        anterior, novo = median(tempos["antes"]), median(tempos["depois"])
        return {
            "escopo": "Busca e pontuacao NCM em memoria, com descricoes repetidas; nao e auditoria completa",
            "catalogo_registros": len(catalogo),
            "consultas_por_rodada": len(DESCRICOES) * 20,
            "rodadas_por_modo": 7,
            "resultados_identicos": resultados["antes"] == resultados["depois"],
            "segundos_mediana_antes": anterior,
            "segundos_mediana_depois": novo,
            "reducao_percentual": 100 * (anterior - novo) / anterior,
            "tempos_segundos": tempos,
        }
    finally:
        modulo.similaridade_textual = funcao_original
        motor._cache_chave, motor._registros, motor._por_ncm, motor._por_token = estado
        _similaridade_em_cache.cache_clear()


if __name__ == "__main__":
    print(json.dumps(medir(), indent=2))
