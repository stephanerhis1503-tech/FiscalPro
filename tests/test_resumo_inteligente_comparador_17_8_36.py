from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.comparador_cenarios_tributarios_service import ComparadorCenariosTributariosService

BASE = Path(__file__).resolve().parents[1]


def contexto(empresa, ufo="PA", ufd="MG"):
    return {
        "empresa": empresa,
        "operacao": "SAÍDA",
        "uf_origem": ufo,
        "uf_destino": ufd,
        "finalidade": "REVENDA",
    }


def test_versao_17836_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split(".")) >= (17, 8, 36)


def test_resumo_nao_elege_vencedor_e_distingue_aliquota_nominal_de_carga_efetiva():
    r = ComparadorCenariosTributariosService.comparar(
        "87141000",
        contexto("Mega Motos Comércio"),
        contexto("Mega Motos Trilha"),
    )
    resumo = r["resumo_inteligente"]
    texto = " ".join(resumo["itens"] + [resumo["conclusao"]]).lower()
    assert resumo["badge"] == "SEM VENCEDOR AUTOMÁTICO"
    assert "alíquotas nominais menores" in texto
    assert "não significa" in texto and "carga efetiva" in texto
    assert "não existe vencedor automático" in texto


def test_monofasico_igual_nao_vira_falsa_vantagem_por_regime():
    r = ComparadorCenariosTributariosService.comparar(
        "40114000",
        contexto("Mega Motos Comércio", "MG", "MG"),
        contexto("Mega Motos Trilha", "MG", "MG"),
    )
    resumo = " ".join(r["resumo_inteligente"]["itens"]).lower()
    assert "pis/cofins: sem diferença" in resumo
    assert "alíquotas nominais menores" not in resumo


def test_rota_diferente_resume_icms_e_cfop_sem_chamar_de_melhor():
    r = ComparadorCenariosTributariosService.comparar(
        "87141000",
        contexto("Mega Motos Comércio", "MG", "MG"),
        contexto("Mega Motos Comércio", "PA", "MG"),
    )
    texto = " ".join(r["resumo_inteligente"]["itens"] + [r["resumo_inteligente"]["conclusao"]]).lower()
    assert "icms próprio: as alíquotas nominais mudam" in texto
    assert "cfop:" in texto
    assert "melhor opção" not in texto


def test_interface_exibe_resumo_inteligente_e_selo_sem_vencedor():
    fonte = (BASE / "src/ui/janela_comparar_cenarios_tributarios.py").read_text(encoding="utf-8")
    assert "Resumo inteligente da comparação" in fonte
    assert "SEM VENCEDOR AUTOMÁTICO" in fonte
    assert "def _renderizar_resumo_inteligente" in fonte
    assert "self._renderizar_resumo_inteligente()" in fonte
