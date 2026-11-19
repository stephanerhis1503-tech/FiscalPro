"""Garante limpeza da navegacao principal sem remover ferramentas fiscais."""
import ast
from pathlib import Path

CAMINHO = Path("src/ui/janela_principal.py")


def test_abas_operacionais_sem_obsoletas():
    texto = CAMINHO.read_text(encoding="utf-8")
    arvore = ast.parse(texto)
    classe = next(n for n in arvore.body if isinstance(n, ast.ClassDef) and n.name == "JanelaPrincipal")
    metodo = next(n for n in classe.body if isinstance(n, ast.FunctionDef) and n.name == "criar_abas")
    chamadas = [
        n for n in ast.walk(metodo)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "add" and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "notebook"
    ]
    alvos = [n.args[0].attr for n in chamadas if n.args and isinstance(n.args[0], ast.Attribute)]
    assert alvos == ["aba_sped", "aba_empresas", "aba_tributacao", "aba_dere", "aba_financeiro", "aba_nfse"]


def test_auditorias_st_permanecem_disponiveis_em_tributacao():
    texto = CAMINHO.read_text(encoding="utf-8")
    arvore = ast.parse(texto)
    classe = next(n for n in arvore.body if isinstance(n, ast.ClassDef) and n.name == "JanelaPrincipal")
    metodo = next(n for n in classe.body if isinstance(n, ast.FunctionDef) and n.name == "criar_painel_tributacao")
    nomes = {n.attr for n in ast.walk(metodo) if isinstance(n, ast.Attribute)}
    assert {"abrir_auditoria_icms_st_piscofins", "abrir_auditoria_icms_st_piscofins_saidas"} <= nomes


def test_codigo_antigo_mantem_modulo_servico_intacto():
    # Remocao na interface nao exclui o servico ou seu historico no banco.
    assert Path("src/ui/painel_entregas.py").exists()
    assert Path("src/ui/painel_contas_pagar.py").exists()
    assert Path("src/ui/painel_documentos_fiscais.py").exists()
