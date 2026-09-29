"""Regressões de layout da Ficha Inteligente 17.8.71."""

from __future__ import annotations

import ast
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO_UI = RAIZ / "src" / "ui" / "janela_ficha_tributaria.py"


def _fonte() -> str:
    return ARQUIVO_UI.read_text(encoding="utf-8")


def test_interface_compila_e_preserva_recursos_tributarios() -> None:
    fonte = _fonte()
    ast.parse(fonte)
    assert 'text="Finalidade para ICMS-ST"' in fonte
    assert 'text="⛶ Ampliar detalhes"' in fonte
    assert "NCM sem enquadramento nominal: ICMS-ST condicional." in fonte


def test_formulario_nao_recria_linha_vertical_de_orientacao() -> None:
    fonte = _fonte()
    assert ").grid(row=7, column=0, columnspan=4" not in fonte
    assert "wraplength=1050" not in fonte


def test_tela_baixa_prioriza_cartoes_sem_ocultar_valores() -> None:
    fonte = _fonte()
    assert "tela_baixa = self.winfo_screenheight() <= 820" in fonte
    assert "if not tela_baixa:" in fonte
    assert "valor.pack(fill=tk.X" in fonte
    for titulo in ("PIS / COFINS", "ICMS-ST", "ICMS / CFOP", "IPI", "SEGURANÇA"):
        assert titulo in fonte
