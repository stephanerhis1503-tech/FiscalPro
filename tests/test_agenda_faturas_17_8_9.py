from datetime import date

from src.financeiro.agenda_faturas import (
    STATUS_AGUARDANDO,
    STATUS_BAIXADA,
    STATUS_LANCADA,
    STATUS_PAGA,
)
from src.financeiro.repositorio import ContasPagarRepositorio
from src.financeiro.servico import ContasPagarServico


def criar_servico(tmp_path):
    repo = ContasPagarRepositorio(tmp_path / "contas_pagar.db")
    return ContasPagarServico(repo)


def lembrete_base(**extras):
    dados = {
        "empresa": "Mega Motos Trilha",
        "fornecedor": "CEMIG",
        "tipo_fatura": "ENERGIA",
        "categoria": "ENERGIA",
        "dia_disponibilidade": 5,
        "dia_vencimento": 15,
        "dias_alerta": 3,
        "competencia_inicial": "08/2026",
        "recorrente": True,
        "ativa": True,
        "observacoes": "Baixar no portal da concessionária.",
    }
    dados.update(extras)
    return dados


def test_cria_tabelas_sem_apagar_contas_existentes(tmp_path):
    servico = criar_servico(tmp_path)
    conta_id, duplicados = servico.salvar_conta({
        "empresa": "Mega Motos Trilha",
        "fornecedor": "Fornecedor teste",
        "categoria": "OUTROS",
        "valor": "100,00",
        "vencimento": "20/08/2026",
        "competencia": "08/2026",
    })
    assert conta_id and not duplicados
    assert servico.repositorio.obter_conta(conta_id)["valor"] == 100.0
    with servico.repositorio._conectar() as con:
        tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "agenda_faturas" in tabelas
    assert "agenda_faturas_itens" in tabelas
    assert "contas_pagar" in tabelas


def test_lembrete_recorrente_gera_mes_atual_e_proximo_sem_duplicar(tmp_path):
    servico = criar_servico(tmp_path)
    lembrete_id = servico.agenda.salvar_lembrete(lembrete_base())
    assert lembrete_id > 0
    servico.agenda.gerar_competencias(referencia=date(2026, 8, 13), meses_futuros=1)
    servico.agenda.gerar_competencias(referencia=date(2026, 8, 13), meses_futuros=1)
    with servico.repositorio._conectar() as con:
        itens = con.execute(
            "SELECT competencia FROM agenda_faturas_itens WHERE lembrete_id=? ORDER BY competencia",
            (lembrete_id,),
        ).fetchall()
    assert [r["competencia"] for r in itens] == ["2026-08", "2026-09"]


def test_dia_31_e_ajustado_ao_ultimo_dia_do_mes(tmp_path):
    servico = criar_servico(tmp_path)
    servico.agenda.salvar_lembrete(lembrete_base(
        dia_disponibilidade=31,
        dia_vencimento=31,
        competencia_inicial="02/2027",
        recorrente=False,
    ))
    itens = servico.agenda.listar_itens(competencia="02/2027", incluir_concluidos=True)
    assert len(itens) == 1
    assert itens[0]["data_prevista"] == "2027-02-28"
    assert itens[0]["vencimento_previsto"] == "2027-02-28"


def test_sinalizacao_muda_conforme_data_e_status(tmp_path):
    servico = criar_servico(tmp_path)
    item = {
        "status": STATUS_AGUARDANDO,
        "data_prevista": "2026-08-10",
        "vencimento_previsto": "2026-08-20",
        "dias_alerta": 3,
    }
    assert servico.agenda.sinalizacao(item, hoje=date(2026, 8, 7))[0].startswith("🟡")
    assert servico.agenda.sinalizacao(item, hoje=date(2026, 8, 10))[0].startswith("🟠")
    assert servico.agenda.sinalizacao(item, hoje=date(2026, 8, 19))[0].startswith("🔴")
    item["status"] = STATUS_PAGA
    assert servico.agenda.sinalizacao(item, hoje=date(2026, 8, 19))[0].startswith("✅")


def test_fluxo_baixada_lancada_paga_e_reaberta(tmp_path):
    servico = criar_servico(tmp_path)
    servico.agenda.salvar_lembrete(lembrete_base())
    servico.agenda.gerar_competencias(referencia=date(2026, 8, 13), meses_futuros=0)
    item = servico.agenda.listar_itens(competencia="08/2026")[0]

    servico.agenda.marcar_fatura_baixada(int(item["id"]), "C:/faturas/cemig.pdf")
    item = servico.agenda.obter_item(int(item["id"]))
    assert item["status"] == STATUS_BAIXADA
    assert item["caminho_documento"] == "C:/faturas/cemig.pdf"

    prefill = servico.agenda.prefill_conta(int(item["id"]))
    prefill["valor"] = "350,90"
    conta_id, duplicados = servico.salvar_conta(prefill)
    assert conta_id and not duplicados
    servico.agenda.vincular_conta(int(item["id"]), conta_id)
    item = servico.agenda.obter_item(int(item["id"]))
    assert item["status"] == STATUS_LANCADA
    assert item["conta_id"] == conta_id

    conta = dict(servico.repositorio.obter_conta(conta_id))
    conta["data_pagamento"] = "2026-08-14"
    servico.salvar_conta(conta, conta_id=conta_id, permitir_duplicidade=True)
    assert servico.agenda.obter_item(int(item["id"]))["status"] == STATUS_PAGA

    conta = dict(servico.repositorio.obter_conta(conta_id))
    conta["data_pagamento"] = ""
    servico.salvar_conta(conta, conta_id=conta_id, permitir_duplicidade=True)
    assert servico.agenda.obter_item(int(item["id"]))["status"] == STATUS_LANCADA


def test_excluir_conta_devolve_fatura_para_fluxo_da_agenda(tmp_path):
    servico = criar_servico(tmp_path)
    servico.agenda.salvar_lembrete(lembrete_base())
    servico.agenda.gerar_competencias(referencia=date(2026, 8, 13), meses_futuros=0)
    item = servico.agenda.listar_itens(competencia="08/2026")[0]
    servico.agenda.marcar_fatura_baixada(int(item["id"]), "C:/faturas/cemig.pdf")
    prefill = servico.agenda.prefill_conta(int(item["id"]))
    prefill["valor"] = "100,00"
    conta_id, _ = servico.salvar_conta(prefill)
    servico.agenda.vincular_conta(int(item["id"]), conta_id)

    servico.repositorio.excluir_conta(conta_id)
    item = servico.agenda.obter_item(int(item["id"]))
    assert item["conta_id"] is None
    assert item["status"] == STATUS_BAIXADA


def test_resumo_da_agenda_sinaliza_pendencias(tmp_path):
    servico = criar_servico(tmp_path)
    servico.agenda.salvar_lembrete(lembrete_base(
        dia_disponibilidade=10,
        dia_vencimento=15,
        dias_alerta=3,
    ))
    servico.agenda.gerar_competencias(referencia=date(2026, 8, 13), meses_futuros=0)
    resumo = servico.agenda.resumo(referencia=date(2026, 8, 13))
    assert resumo["para_baixar"] >= 1
    assert resumo["nao_lancadas"] >= 1
    assert resumo["vencendo_7_dias"] >= 1


def test_edicao_do_lembrete_atualiza_datas_abertas(tmp_path):
    servico = criar_servico(tmp_path)
    lembrete_id = servico.agenda.salvar_lembrete(lembrete_base())
    servico.agenda.gerar_competencias(referencia=date(2026, 8, 13), meses_futuros=0)
    item = servico.agenda.listar_itens(competencia="08/2026")[0]
    assert item["vencimento_previsto"] == "2026-08-15"

    servico.agenda.salvar_lembrete(
        lembrete_base(dia_disponibilidade=8, dia_vencimento=20),
        lembrete_id=lembrete_id,
    )
    item = servico.agenda.obter_item(int(item["id"]))
    assert item["data_prevista"] == "2026-08-08"
    assert item["vencimento_previsto"] == "2026-08-20"
