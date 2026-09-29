from datetime import date
from pathlib import Path

from src.entregas.repositorio import EntregasRepositorio
from src.entregas.servico import EntregasServico


def criar_servico(tmp_path: Path) -> EntregasServico:
    return EntregasServico(EntregasRepositorio(tmp_path / "entregas.db"))


def test_cadastra_empresas_sem_duplicar_nome(tmp_path):
    servico = criar_servico(tmp_path)
    primeiro = servico.repositorio.salvar_empresa("Empresa A", "123")
    segundo = servico.repositorio.salvar_empresa("empresa a", "456")
    assert primeiro == segundo
    empresas = servico.repositorio.listar_empresas()
    assert len(empresas) == 1
    assert empresas[0]["cnpj"] == "456"


def test_modelo_mensal_e_geracao_da_competencia(tmp_path):
    servico = criar_servico(tmp_path)
    empresa_id = servico.repositorio.salvar_empresa("Empresa A")
    servico.repositorio.salvar_modelo(
        empresa_id=empresa_id,
        tipo_arquivo="SPED Fiscal",
        dia_prazo=20,
        destinatario="Contabilidade",
    )
    assert servico.gerar_competencia("08/2026") == 1
    itens = servico.repositorio.listar_entregas(competencia="2026-08")
    assert len(itens) == 1
    assert itens[0]["tipo_arquivo"] == "SPED Fiscal"
    assert itens[0]["prazo"] == "2026-09-20"
    assert itens[0]["destinatario"] == "Contabilidade"


def test_gerar_competencia_e_idempotente(tmp_path):
    servico = criar_servico(tmp_path)
    empresa_id = servico.repositorio.salvar_empresa("Empresa A")
    servico.repositorio.salvar_modelo(
        empresa_id=empresa_id, tipo_arquivo="XML", dia_prazo=10
    )
    assert servico.gerar_competencia("08/2026") == 1
    assert servico.gerar_competencia("08/2026") == 0
    assert len(servico.repositorio.listar_entregas()) == 1


def test_dia_31_ajusta_para_fim_do_mes(tmp_path):
    servico = criar_servico(tmp_path)
    empresa_id = servico.repositorio.salvar_empresa("Empresa A")
    servico.repositorio.salvar_modelo(
        empresa_id=empresa_id, tipo_arquivo="Fechamento", dia_prazo=31
    )
    servico.gerar_competencia("02/2026")
    item = servico.repositorio.listar_entregas()[0]
    assert item["prazo"] == "2026-03-31"


def test_status_atrasado_pendente_e_entregue(tmp_path):
    servico = criar_servico(tmp_path)
    servico.repositorio.salvar_empresa("Empresa A")
    a = servico.salvar_entrega(
        {
            "empresa": "Empresa A", "competencia": "07/2026", "tipo_arquivo": "A",
            "prazo": "10/07/2026", "status": "PENDENTE",
        }
    )
    b = servico.salvar_entrega(
        {
            "empresa": "Empresa A", "competencia": "08/2026", "tipo_arquivo": "B",
            "prazo": "20/08/2026", "status": "PENDENTE",
        }
    )
    servico.atualizar_status(date(2026, 8, 10))
    assert servico.repositorio.obter_entrega(a)["status"] == "ATRASADO"
    assert servico.repositorio.obter_entrega(b)["status"] == "PENDENTE"
    servico.repositorio.marcar_entregue(b, "2026-08-10")
    assert servico.repositorio.obter_entrega(b)["status"] == "ENTREGUE"


def test_nao_se_aplica_e_preservado_na_atualizacao(tmp_path):
    servico = criar_servico(tmp_path)
    servico.repositorio.salvar_empresa("Empresa A")
    entrega_id = servico.salvar_entrega(
        {
            "empresa": "Empresa A", "competencia": "01/2026", "tipo_arquivo": "Sem movimento",
            "prazo": "05/01/2026", "status": "PENDENTE",
        }
    )
    servico.repositorio.marcar_nao_aplica(entrega_id)
    servico.atualizar_status(date(2026, 8, 10))
    assert servico.repositorio.obter_entrega(entrega_id)["status"] == "NÃO SE APLICA"


def test_resumo_por_competencia(tmp_path):
    servico = criar_servico(tmp_path)
    servico.repositorio.salvar_empresa("Empresa A")
    ids = []
    for tipo, prazo in (("A", "01/08/2026"), ("B", "20/08/2026"), ("C", "25/08/2026")):
        ids.append(
            servico.salvar_entrega(
                {
                    "empresa": "Empresa A", "competencia": "08/2026",
                    "tipo_arquivo": tipo, "prazo": prazo, "status": "PENDENTE",
                }
            )
        )
    servico.atualizar_status(date(2026, 8, 10))
    servico.repositorio.marcar_entregue(ids[1], "2026-08-10")
    resumo = servico.repositorio.resumo(competencia="2026-08")
    assert resumo == {
        "total": 3, "entregues": 1, "pendentes": 1, "atrasados": 1, "nao_aplica": 0
    }


def test_exporta_relatorio_csv(tmp_path):
    servico = criar_servico(tmp_path)
    servico.repositorio.salvar_empresa("Empresa A")
    servico.salvar_entrega(
        {
            "empresa": "Empresa A", "competencia": "08/2026", "tipo_arquivo": "SPED Contribuições",
            "prazo": "15/08/2026", "destinatario": "Contabilidade", "status": "PENDENTE",
        }
    )
    destino = servico.exportar_csv(tmp_path / "relatorio.csv", competencia="2026-08")
    texto = destino.read_text(encoding="utf-8-sig")
    assert "Empresa A" in texto
    assert "SPED Contribuições" in texto
    assert "Contabilidade" in texto


def test_prazo_pode_ser_no_mes_da_competencia(tmp_path):
    servico = criar_servico(tmp_path)
    empresa_id = servico.repositorio.salvar_empresa("Empresa A")
    servico.repositorio.salvar_modelo(
        empresa_id=empresa_id, tipo_arquivo="Obrigação no mês", dia_prazo=31,
        meses_apos_competencia=0,
    )
    servico.gerar_competencia("02/2026")
    item = servico.repositorio.listar_entregas()[0]
    assert item["prazo"] == "2026-02-28"
