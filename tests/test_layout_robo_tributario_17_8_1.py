from types import SimpleNamespace

import src.ui.janela_principal as jp


class _FakeWidget:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def pack(self, *args, **kwargs):
        return None

    def grid(self, *args, **kwargs):
        return None

    def columnconfigure(self, *args, **kwargs):
        return None

    def rowconfigure(self, *args, **kwargs):
        return None

    def configure(self, *args, **kwargs):
        return None

    config = configure

    def create_window(self, *args, **kwargs):
        return 1

    def bind(self, *args, **kwargs):
        return None

    def bind_all(self, *args, **kwargs):
        return None

    def unbind_all(self, *args, **kwargs):
        return None

    def bbox(self, *args, **kwargs):
        return (0, 0, 0, 0)

    def itemconfigure(self, *args, **kwargs):
        return None

    def yview(self, *args, **kwargs):
        return None

    def yview_scroll(self, *args, **kwargs):
        return None

    def set(self, *args, **kwargs):
        return None


def test_robo_tributario_permanece_na_central_tributaria_apos_reorganizacao():
    from pathlib import Path

    fonte = Path("src/ui/janela_principal.py").read_text(encoding="utf-8")
    bloco = fonte.split("def criar_painel_tributacao", 1)[1].split("def criar_painel_correcoes", 1)[0]
    assert "Central Tributária Inteligente" in bloco
    assert '"CONSULTAR"' in bloco
    assert '("Robô Tributário", self.abrir_robo_tributario, "Secondary.TButton")' in bloco
    assert '"AUDITAR"' in bloco
    assert '("Auditoria de cadastro por XML", self.abrir_auditoria_cadastros_xml, "Secondary.TButton")' in bloco

def test_acao_do_robo_continua_abrindo_a_janela(monkeypatch):
    recebido = []

    class _JanelaFake:
        def __init__(self, parent):
            recebido.append(parent)

    monkeypatch.setattr(jp, "JanelaRoboTributario", _JanelaFake)
    obj = jp.JanelaPrincipal.__new__(jp.JanelaPrincipal)
    obj.janela = object()

    obj.abrir_robo_tributario()

    assert recebido == [obj.janela]
