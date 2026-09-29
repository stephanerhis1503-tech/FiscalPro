from pathlib import Path

from src.core.app_info import VERSAO_APP

BASE = Path(__file__).resolve().parents[1]


def test_versao_17835_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split(".")) >= (17, 8, 35)


def test_alterar_cenario_descarta_resultado_antigo_e_limpa_tela():
    fonte = (BASE / "src/ui/janela_comparar_cenarios_tributarios.py").read_text(encoding="utf-8")
    assert "self.resultado = None" in fonte
    assert "self._resultado_completo = None" in fonte
    assert "Configuração alterada — compare novamente." in fonte
    assert "O resultado anterior foi limpo" in fonte
    assert "self._renderizar_destaques()" in fonte
    assert "self._renderizar_resultado()" in fonte


def test_resultado_desatualizado_nao_pode_ser_usado():
    fonte = (BASE / "src/ui/janela_comparar_cenarios_tributarios.py").read_text(encoding="utf-8")
    assert "self.btn_usar_a.configure(state=tk.DISABLED)" in fonte
    assert "self.btn_usar_b.configure(state=tk.DISABLED)" in fonte


def test_invalidacao_real_limpa_resultado_e_renderiza_estado_vazio():
    from src.ui.janela_comparar_cenarios_tributarios import JanelaCompararCenariosTributarios

    class Botao:
        def __init__(self):
            self.state = None
        def configure(self, **kwargs):
            self.state = kwargs.get("state")

    class Var:
        def __init__(self):
            self.valor = ""
        def set(self, valor):
            self.valor = valor

    class Dummy:
        pass

    d = Dummy()
    d.resultado = {"linhas": [object()]}
    d._resultado_completo = {"antigo": True}
    d.btn_usar_a = Botao()
    d.btn_usar_b = Botao()
    d.identificacao_var = Var()
    d.resumo_var = Var()
    d.destaques = 0
    d.tabela = 0
    d._renderizar_destaques = lambda: setattr(d, "destaques", d.destaques + 1)
    d._renderizar_resultado = lambda: setattr(d, "tabela", d.tabela + 1)

    JanelaCompararCenariosTributarios._marcar_comparacao_desatualizada(d)

    assert d.resultado is None
    assert d._resultado_completo is None
    assert d.btn_usar_a.state == "disabled"
    assert d.btn_usar_b.state == "disabled"
    assert "compare novamente" in d.identificacao_var.valor.lower()
    assert "resultado anterior foi limpo" in d.resumo_var.valor.lower()
    assert d.destaques == 1
    assert d.tabela == 1
