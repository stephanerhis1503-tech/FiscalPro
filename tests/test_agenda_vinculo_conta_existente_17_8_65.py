from datetime import date
from pathlib import Path

from src.financeiro.agenda_faturas import STATUS_BAIXADA, STATUS_PAGA
from src.financeiro.repositorio import ContasPagarRepositorio
from src.financeiro.servico import ContasPagarServico


def _servico(tmp_path: Path) -> ContasPagarServico:
    return ContasPagarServico(ContasPagarRepositorio(tmp_path / "financeiro.db"))


def _criar_item_sem_vinculo(servico: ContasPagarServico, fornecedor: str = "CEMIG"):
    empresa = servico.repositorio.listar_empresas()[0]
    lembrete_id = servico.agenda.salvar_lembrete({
        "empresa": empresa,
        "fornecedor": fornecedor,
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
    item = servico.agenda.obter_item(int(item["id"]))
    assert item["status"] == STATUS_BAIXADA
    assert item["conta_id"] is None
    return item, empresa


def _criar_conta_manual(servico: ContasPagarServico, empresa: str, fornecedor: str, *, vencimento="25/08/2026"):
    conta_id, duplicados = servico.salvar_conta({
        "empresa": empresa,
        "fornecedor": fornecedor,
        "descricao": "Conta de energia agosto",
        "categoria": "ENERGIA",
        "valor": "250,00",
        "vencimento": vencimento,
        "competencia": "08/2026",
        "origem": "MANUAL",
    })
    assert not duplicados
    return conta_id


def test_localiza_conta_manual_da_mesma_empresa_fornecedor_e_competencia(tmp_path):
    servico = _servico(tmp_path)
    item, empresa = _criar_item_sem_vinculo(servico)
    conta_id = _criar_conta_manual(servico, empresa, "Cemig")

    candidatos = servico.agenda.localizar_contas_candidatas(int(item["id"]))

    assert [int(c["id"]) for c in candidatos] == [conta_id]
    assert candidatos[0]["score_vinculo"] >= 100


def test_nao_oferece_fornecedor_diferente_como_vinculo_automatico(tmp_path):
    servico = _servico(tmp_path)
    item, empresa = _criar_item_sem_vinculo(servico)
    _criar_conta_manual(servico, empresa, "COPASA")

    assert servico.agenda.localizar_contas_candidatas(int(item["id"])) == []


def test_vinculo_de_conta_preexistente_permite_baixa_e_sincroniza_agenda(tmp_path):
    servico = _servico(tmp_path)
    item, empresa = _criar_item_sem_vinculo(servico)
    conta_id = _criar_conta_manual(servico, empresa, "CEMIG")

    servico.agenda.vincular_conta(int(item["id"]), conta_id)
    servico.dar_baixa_conta(conta_id, "24/08/2026")

    conta = servico.repositorio.obter_conta(conta_id)
    item_final = servico.agenda.obter_item(int(item["id"]))
    assert conta["status"] == "PAGO"
    assert conta["data_pagamento"] == "2026-08-24"
    assert item_final["conta_id"] == conta_id
    assert item_final["status"] == STATUS_PAGA


def test_interface_tenta_reaproveitar_lancamento_existente_antes_de_pedir_novo():
    fonte = Path("src/ui/painel_contas_pagar.py").read_text(encoding="utf-8")
    assert "localizar_contas_candidatas" in fonte
    assert "Vincular conta existente" in fonte
    assert "O FiscalPro não encontrou um lançamento compatível" in fonte
