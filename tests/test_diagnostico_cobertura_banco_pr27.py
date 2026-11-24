"""O diagnostico da copia PR27 e somente explicativo, sem tocar bancos."""
from types import SimpleNamespace

from src.services.diagnostico_cobertura_banco_pr27_service import aviso_banco_isolado_pr27


def _r(*, inconclusiva=True, atual=0, produto=0):
    return SimpleNamespace(
        auditoria_tributaria_inconclusiva=inconclusiva,
        regras_operacionais_banco={
            "tributacao_atual": atual,
            "tributacao_base_ativa": produto,
        },
    )


def test_aviso_apenas_na_copia_pr27_sem_regras():
    resposta = aviso_banco_isolado_pr27(
        _r(), r"C:\Users\Teste\AppData\Local\FiscalPro_TESTE_FICHA_PR27"
    )
    assert "0 regras por operacao" in resposta
    assert "primeira execucao" in resposta
    assert "NAO comprova" in resposta


def test_aviso_nao_inferir_regras_no_banco_original():
    original = r"C:\Users\Teste\AppData\Local\FiscalPro"
    assert aviso_banco_isolado_pr27(_r(), original) == ""
    assert aviso_banco_isolado_pr27(_r(inconclusiva=False), "FiscalPro_TESTE_FICHA_PR27") == ""


def test_aviso_contextual_sem_homologar_ou_copiar():
    resposta = aviso_banco_isolado_pr27(
        _r(atual=2, produto=5), "FiscalPro_TESTE_FICHA_PR27"
    )
    assert "2 regras por operacao" in resposta
    assert "5 cadastros ativos" in resposta
    assert "nao" in resposta.lower()
