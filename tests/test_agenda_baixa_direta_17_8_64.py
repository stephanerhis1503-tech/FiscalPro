from datetime import date
from pathlib import Path

from src.financeiro.agenda_faturas import STATUS_LANCADA, STATUS_PAGA
from src.financeiro.repositorio import ContasPagarRepositorio
from src.financeiro.servico import ContasPagarServico


def _servico(tmp_path: Path) -> ContasPagarServico:
    return ContasPagarServico(ContasPagarRepositorio(tmp_path / "financeiro.db"))


def _criar_item_lancado(servico: ContasPagarServico):
    empresa = servico.repositorio.listar_empresas()[0]
    lembrete_id = servico.agenda.salvar_lembrete({
        "empresa": empresa,
        "fornecedor": "CEMIG",
        "tipo_fatura": "ENERGIA",
        "categoria": "ENERGIA",
        "dia_disponibilidade": 5,
        "dia_vencimento": 25,
        "dias_alerta": 3,
        "competencia_inicial": "08/2026",
        "recorrente": False,
        "ativa": True,
    })
    servico.agenda.gerar_competencias(referencia=date(2026, 8, 24), meses_futuros=0)
    item = servico.agenda.listar_itens(competencia="08/2026", incluir_concluidos=True)[0]
    servico.agenda.marcar_fatura_baixada(int(item["id"]))
    dados = servico.agenda.prefill_conta(int(item["id"]))
    dados["valor"] = "250,00"
    conta_id, _ = servico.salvar_conta(dados)
    servico.agenda.vincular_conta(int(item["id"]), conta_id)
    item = servico.agenda.obter_item(int(item["id"]))
    assert item["status"] == STATUS_LANCADA
    return item, conta_id


def test_baixa_direta_marca_conta_e_agenda_como_pagas(tmp_path):
    servico = _servico(tmp_path)
    item, conta_id = _criar_item_lancado(servico)

    servico.dar_baixa_conta(conta_id, "24/08/2026")

    conta = servico.repositorio.obter_conta(conta_id)
    assert conta["data_pagamento"] == "2026-08-24"
    assert conta["status"] == "PAGO"
    item = servico.agenda.obter_item(int(item["id"]))
    assert item["status"] == STATUS_PAGA


def test_baixa_direta_preserva_data_original_se_conta_ja_estiver_paga(tmp_path):
    servico = _servico(tmp_path)
    _, conta_id = _criar_item_lancado(servico)

    servico.dar_baixa_conta(conta_id, "22/08/2026")
    servico.dar_baixa_conta(conta_id, "24/08/2026")

    conta = servico.repositorio.obter_conta(conta_id)
    assert conta["data_pagamento"] == "2026-08-22"
    assert conta["status"] == "PAGO"


def test_agenda_expoe_botao_dar_baixa_hoje_e_protege_fatura_sem_vinculo():
    fonte = Path("src/ui/painel_contas_pagar.py").read_text(encoding="utf-8")
    assert 'text="✓ Dar baixa hoje"' in fonte
    assert 'command=self._dar_baixa_hoje' in fonte
    assert 'Essa fatura ainda não está vinculada ao Contas a Pagar.' in fonte
    assert 'self.servico.dar_baixa_conta(int(conta_id))' in fonte
