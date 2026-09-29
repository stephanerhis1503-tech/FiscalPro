from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.comparador_cenarios_tributarios_service import ComparadorCenariosTributariosService

BASE = Path(__file__).resolve().parents[1]


def contexto(empresa):
    return {
        "empresa": empresa,
        "operacao": "SAÍDA",
        "uf_origem": "PA",
        "uf_destino": "MG",
        "finalidade": "REVENDA",
    }


def test_versao_17837_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split(".")) >= (17, 8, 37)


def test_mini_cards_sao_apenas_apresentacao_e_resumo_do_motor_permanece_igual():
    r = ComparadorCenariosTributariosService.comparar(
        "87141000", contexto("Mega Motos Comércio"), contexto("Mega Motos Trilha")
    )
    resumo = r["resumo_inteligente"]
    assert resumo["badge"] == "SEM VENCEDOR AUTOMÁTICO"
    texto = " ".join(resumo["itens"] + [resumo["conclusao"]]).lower()
    assert "pis/cofins" in texto
    assert "icms próprio" in texto
    assert "icms-st" in texto
    assert "não existe vencedor automático" in texto


def test_interface_exibe_os_cinco_mini_cards_do_resumo():
    fonte = (BASE / "src/ui/janela_comparar_cenarios_tributarios.py").read_text(encoding="utf-8")
    assert "def _criar_mini_card_resumo" in fonte
    assert 'titulo="PIS / COFINS"' in fonte
    assert 'titulo="ICMS"' in fonte
    assert 'titulo="ICMS-ST"' in fonte
    assert 'titulo="Pendências e segurança"' in fonte
    assert 'titulo="Conclusão"' in fonte
    assert "SEM VENCEDOR AUTOMÁTICO" in fonte


def test_comparacao_monofasica_continua_sem_falsa_vantagem():
    r = ComparadorCenariosTributariosService.comparar(
        "40114000", contexto("Mega Motos Comércio"), contexto("Mega Motos Trilha")
    )
    texto = " ".join(r["resumo_inteligente"]["itens"]).lower()
    assert "pis/cofins: sem diferença" in texto
    assert "alíquotas nominais menores" not in texto
