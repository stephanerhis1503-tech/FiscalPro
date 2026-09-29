from pathlib import Path

from src.core.app_info import VERSAO_APP

BASE = Path(__file__).resolve().parents[1]


def test_versao_17834_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split(".")) >= (17, 8, 34)


def test_comparador_tem_cards_de_destaque_e_uso_de_cenario():
    fonte = (BASE / "src/ui/janela_comparar_cenarios_tributarios.py").read_text(encoding="utf-8")
    assert "Destaques da comparação" in fonte
    assert "USAR ESTE CENÁRIO" in fonte
    assert "def _renderizar_destaques" in fonte
    assert "MUDOU" in fonte
    assert "CENÁRIOS EQUIVALENTES" in fonte


def test_uso_de_cenario_abre_ficha_com_contexto_completo():
    fonte = (BASE / "src/ui/janela_comparar_cenarios_tributarios.py").read_text(encoding="utf-8")
    assert 'cenario = self.resultado["cenario_a" if lado == "A" else "cenario_b"]' in fonte
    assert 'contexto=dict(cenario.get("contexto") or {})' in fonte
    assert 'ncm=str(cenario.get("ncm") or "")' in fonte


def test_alteracao_de_contexto_bloqueia_uso_ate_nova_comparacao():
    fonte = (BASE / "src/ui/janela_comparar_cenarios_tributarios.py").read_text(encoding="utf-8")
    assert "def _marcar_comparacao_desatualizada" in fonte
    assert "self.btn_usar_a.configure(state=tk.DISABLED)" in fonte
    assert "self.btn_usar_b.configure(state=tk.DISABLED)" in fonte
    assert "Compare novamente antes de usar" in fonte
