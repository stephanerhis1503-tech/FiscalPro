from pathlib import Path

import pytest

from src.financeiro.servico import ContasPagarServico


class RepositorioFake:
    def __init__(self):
        self.chamadas = []
        self._dados = {
            "Empresa A": [{"empresa": "Empresa A", "vencimento": "2026-08-20", "valor": 10.0}],
            "Empresa B": [{"empresa": "Empresa B", "vencimento": "2026-08-21", "valor": 20.0}],
            "Empresa C": [{"empresa": "Empresa C", "vencimento": "2026-08-22", "valor": 30.0}],
        }

    def listar_empresas(self):
        return list(self._dados)

    def atualizar_status_em_lote(self, _hoje):
        return None

    def listar_contas_periodo(self, inicio, fim, *, empresa="", incluir_vencidas=False):
        self.chamadas.append((inicio, fim, empresa, incluir_vencidas))
        if empresa:
            return list(self._dados[empresa])
        return [conta for contas in self._dados.values() for conta in contas]


def _servico_fake():
    servico = object.__new__(ContasPagarServico)
    servico.repositorio = RepositorioFake()
    servico.agenda = None
    return servico


def test_relatorio_filtra_multiplas_empresas_sem_incluir_as_demais():
    servico = _servico_fake()
    contas = servico.contas_para_relatorio(
        "20/08/2026",
        "25/08/2026",
        empresas=("Empresa A", "Empresa C"),
    )
    assert [conta["empresa"] for conta in contas] == ["Empresa A", "Empresa C"]
    assert [chamada[2] for chamada in servico.repositorio.chamadas] == ["Empresa A", "Empresa C"]


def test_relatorio_rejeita_empresa_nao_cadastrada():
    servico = _servico_fake()
    with pytest.raises(ValueError, match="Empresa não cadastrada"):
        servico.contas_para_relatorio(
            "20/08/2026",
            "25/08/2026",
            empresas=("Empresa inexistente",),
        )


def test_interface_tem_selecao_por_checkbox_e_botoes_de_marcacao():
    fonte = Path("src/ui/painel_contas_pagar.py").read_text(encoding="utf-8")
    trecho = fonte.split("class JanelaRelatorioVencimentos:", 1)[1].split("class JanelaContaPagar:", 1)[0]
    assert "self.vars_empresas" in trecho
    assert "ttk.Checkbutton" in trecho
    assert 'text="Marcar todas"' in trecho
    assert 'text="Desmarcar todas"' in trecho
    assert "empresas=empresas" in trecho
    assert "Marque pelo menos uma empresa" in trecho


def test_versao_17_8_21():
    fonte = Path("src/core/app_info.py").read_text(encoding="utf-8")
    
    import re
    m = re.search(r'VERSAO_APP\s*=\s*"(\d+)\.(\d+)\.(\d+)"', fonte)
    assert m and tuple(map(int, m.groups())) >= (17, 8, 21)
