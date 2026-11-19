"""Auditoria sem regras nao pode declarar conformidade total."""
from src.sped.auditor_tributario import ResultadoAuditoriaTributaria


def test_zero_regras_nao_equivale_a_cem_porcento_conforme():
    a = ResultadoAuditoriaTributaria(
        total_itens=1341, itens_sem_regra=1341, avisos=380,
        diagnostico_regras="Nenhuma regra localizada.",
    )
    assert a.auditoria_tributaria_inconclusiva
    assert a.cobertura_regras == 0
    assert a.conformidade_exibicao.startswith("NAO AVALIAVEL")
    assert a.conformidade != 100.0 or a.auditoria_tributaria_inconclusiva


def test_cobertura_parcial_continua_visivel():
    a = ResultadoAuditoriaTributaria(
        total_itens=100, itens_com_regra=40, itens_sem_regra=60
    )
    assert a.cobertura_regras == 40.0
    assert not a.auditoria_tributaria_inconclusiva
    assert "cobertura de regras: 40.00%" in a.conformidade_exibicao


def test_sem_itens_nao_marca_conformidade_integral():
    a = ResultadoAuditoriaTributaria()
    assert a.auditoria_tributaria_inconclusiva
    assert a.cobertura_regras == 0.0
    assert a.conformidade == 0.0
