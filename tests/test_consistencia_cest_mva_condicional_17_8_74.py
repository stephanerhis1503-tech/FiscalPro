"""Regressões da consistência visual do ICMS-ST condicional 17.8.74."""

from __future__ import annotations

import ast
from pathlib import Path

from src.services.icms_st_mg_service import ICMSSTMGService


RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO_UI = RAIZ / "src" / "ui" / "janela_ficha_tributaria.py"


def test_motor_continua_sugerindo_sem_confirmar() -> None:
    r = ICMSSTMGService.analisar("85444200", {"uf_origem": "MG", "uf_destino": "MG"}, "")
    assert r["confirmado"] is False
    assert r["decisao_st"] == "CONDICIONAL"
    assert r["cest_sugerido"] == "01.999.00"
    assert r["mva_sugerida"] == 71.78
    assert r.get("mva_original") is None
    assert r.get("mva_aplicada") is None


def test_ficha_distingue_sugestao_de_valor_confirmado() -> None:
    fonte = ARQUIVO_UI.read_text(encoding="utf-8")
    ast.parse(fonte)
    assert 'st_somente_sugerido = st_condicional and not st_encontrado' in fonte
    assert 'cest_exibicao = f"{self._formatar_cest_exibicao(cest_sugerido)} (possível)"' in fonte
    assert 'f"CEST possível {uf_icms}"' in fonte
    assert 'Não confirmada • possível' in fonte
    assert 'Não calculada — confirmar finalidade' in fonte
    assert 'A MVA possível não é aplicada ao cálculo' in fonte
