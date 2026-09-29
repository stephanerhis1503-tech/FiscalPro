from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.ui.painel_contas_pagar import JanelaContaPagar


def _texto(caminho: str) -> str:
    return Path(caminho).read_text(encoding="utf-8")


def test_campos_obrigatorios_do_enter_conta():
    assert JanelaContaPagar._primeiro_obrigatorio_pendente({}) == "empresa"
    assert JanelaContaPagar._primeiro_obrigatorio_pendente({"empresa": "Mega Motos Trilha"}) == "fornecedor"
    assert JanelaContaPagar._primeiro_obrigatorio_pendente({
        "empresa": "Mega Motos Trilha", "fornecedor": "Fornecedor X"
    }) == "valor"
    assert JanelaContaPagar._primeiro_obrigatorio_pendente({
        "empresa": "Mega Motos Trilha", "fornecedor": "Fornecedor X", "valor": "10,00"
    }) == "vencimento"
    assert JanelaContaPagar._primeiro_obrigatorio_pendente({
        "empresa": "Mega Motos Trilha", "fornecedor": "Fornecedor X", "valor": "10,00", "vencimento": "21/08/2026"
    }) == ""


def test_contas_pagar_tem_enter_e_preserva_observacoes():
    fonte = _texto("src/ui/painel_contas_pagar.py")
    assert 'self.janela.bind("<Return>", self._atalho_enter_conta' in fonte
    assert 'self.janela.bind("<KP_Enter>", self._atalho_enter_conta' in fonte
    assert 'if foco is self.txt_observacoes:' in fonte
    assert 'Salvar conta  •  Enter' in fonte


def test_consultas_principais_aceitam_enter_e_teclado_numerico():
    ficha = _texto("src/ui/janela_ficha_tributaria.py")
    principal = _texto("src/ui/janela_principal.py")
    consulta = _texto("src/ui/janela_consulta_ncm.py")
    comparador = _texto("src/ui/janela_comparar_cenarios_tributarios.py")

    assert 'self.entry_pesquisa.bind("<Return>"' in ficha
    assert 'self.entry_pesquisa.bind("<KP_Enter>"' in ficha
    assert 'entrada.bind("<Return>"' in principal
    assert 'entrada.bind("<KP_Enter>"' in principal
    assert 'self.ncm.bind("<Return>"' in consulta
    assert 'self.ncm.bind("<KP_Enter>"' in consulta
    assert 'self.entry_ncm.bind("<Return>"' in comparador
    assert 'self.entry_ncm.bind("<KP_Enter>"' in comparador


def test_versao_17848():
    fonte = _texto("src/core/app_info.py")
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 48)
