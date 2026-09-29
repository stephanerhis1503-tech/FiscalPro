from pathlib import Path


def test_auditoria_excel_permanece_destacada_na_central_tributaria():
    fonte = Path("src/ui/janela_principal.py").read_text(encoding="utf-8")
    bloco = fonte.split("def criar_painel_tributacao", 1)[1].split("def criar_painel_correcoes", 1)[0]
    assert "Central Tributária Inteligente" in bloco
    assert '"AUDITAR"' in bloco
    assert '"Auditoria de cadastro por Excel"' in bloco
    assert "self.abrir_auditoria_cadastros_excel" in bloco

def test_aba_tributacao_tem_rolagem_vertical():
    fonte = Path("src/ui/janela_principal.py").read_text(encoding="utf-8")
    bloco = fonte.split("def criar_painel_tributacao", 1)[1].split("def criar_painel_correcoes", 1)[0]
    assert "Canvas(" in bloco
    assert 'orient="vertical"' in bloco
    assert "canvas.yview" in bloco


def test_versao_17_8_10_ou_superior():
    import re
    fonte = Path("src/core/app_info.py").read_text(encoding="utf-8")
    m = re.search(r'VERSAO_APP = "(\d+)\.(\d+)\.(\d+)"', fonte)
    assert m
    assert tuple(map(int, m.groups())) >= (17, 8, 10)
