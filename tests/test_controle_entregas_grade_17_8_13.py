from pathlib import Path

from src.entregas.repositorio import EntregasRepositorio
from src.entregas.servico import EntregasServico


def servico_tmp(tmp_path: Path) -> EntregasServico:
    return EntregasServico(EntregasRepositorio(tmp_path / "controle_entregas.db"))


def test_sincroniza_somente_empresas_atuais_e_preserva_antiga_inativa(tmp_path):
    servico = servico_tmp(tmp_path)
    antiga_id = servico.repositorio.salvar_empresa("Empresa Antiga", regime="LUCRO REAL")
    servico.sincronizar_estrutura_atual()

    ativas = servico.repositorio.listar_empresas()
    assert {e["nome"] for e in ativas} == {
        "Mega Motos Trilha", "Mega T.O. E-commerce", "Mega Mix E-commerce",
        "Mega Motos Comércio", "Mega Serviços", "Mega Serviços Profissionais"
    }
    mega = servico.repositorio.obter_empresa_por_nome("Mega Motos Comércio")
    assert mega["regime"] == "LUCRO PRESUMIDO"

    todas = servico.repositorio.listar_empresas(incluir_inativas=True)
    antiga = next(e for e in todas if e["id"] == antiga_id)
    assert antiga["ativa"] == 0


def test_modelo_inicial_presumido_segue_planilha_sem_creditos(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    mega = servico.repositorio.obter_empresa_por_nome("Mega Motos Comércio")
    empresa_id = int(mega["id"])

    for obrigacao in ("CRÉDITO ICMS", "CRÉDITO PIS", "CRÉDITO COFINS"):
        modelo = servico.repositorio.obter_modelo_por_empresa_tipo(
            empresa_id, obrigacao, incluir_inativo=True
        )
        assert modelo is not None
        assert modelo["ativo"] == 0

    assert servico.repositorio.obter_modelo_por_empresa_tipo(
        empresa_id, "ICMS", incluir_inativo=False
    )["dia_prazo"] == 8
    assert servico.repositorio.obter_modelo_por_empresa_tipo(
        empresa_id, "ISS", incluir_inativo=False
    )["dia_prazo"] == 20
    assert servico.repositorio.obter_modelo_por_empresa_tipo(
        empresa_id, "PIS", incluir_inativo=False
    )["dia_prazo"] == 25
    assert servico.repositorio.obter_modelo_por_empresa_tipo(
        empresa_id, "COFINS", incluir_inativo=False
    )["dia_prazo"] == 25


def test_grade_mensal_tem_empresas_regime_colunas_e_nao_aplica(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    grade = servico.grade_competencia("08/2026")

    assert len(grade) == 6
    mega = next(l for l in grade if l["empresa"]["nome"] == "Mega Motos Comércio")
    assert mega["empresa"]["regime"] == "LUCRO PRESUMIDO"
    assert set(mega["celulas"]) == set(servico.OBRIGACOES_NOMES)
    assert mega["celulas"]["CRÉDITO PIS"]["status"] == "NÃO SE APLICA"
    assert mega["celulas"]["ICMS"]["status"] == "PENDENTE"


def test_geracao_respeita_prazos_e_nao_cria_creditos_presumido(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    servico.gerar_competencia("08/2026", "Mega Motos Comércio")
    mega = servico.repositorio.obter_empresa_por_nome("Mega Motos Comércio")
    eid = int(mega["id"])

    icms = servico.repositorio.obter_entrega_por_chave(eid, "2026-08", "ICMS")
    iss = servico.repositorio.obter_entrega_por_chave(eid, "2026-08", "ISS")
    pis = servico.repositorio.obter_entrega_por_chave(eid, "2026-08", "PIS")
    credito_pis = servico.repositorio.obter_entrega_por_chave(eid, "2026-08", "CRÉDITO PIS")

    assert icms["prazo"] == "2026-09-08"
    assert iss["prazo"] == "2026-09-20"
    assert pis["prazo"] == "2026-09-25"
    assert credito_pis is None


def test_detalhe_guarda_valor_protocolo_andamento_e_observacao(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    servico.gerar_competencia("08/2026", "Mega Motos Comércio")
    mega = servico.repositorio.obter_empresa_por_nome("Mega Motos Comércio")
    eid = int(mega["id"])
    item = servico.repositorio.obter_entrega_por_chave(eid, "2026-08", "ICMS")

    servico.salvar_entrega(
        {
            "empresa": "Mega Motos Comércio",
            "competencia": "08/2026",
            "tipo_arquivo": "ICMS",
            "prazo": "08/09/2026",
            "status": "EM ANDAMENTO",
            "valor": "1.234,56",
            "protocolo": "PROTO-123",
            "observacoes": "Conferir antes de transmitir",
        },
        entrega_id=int(item["id"]),
    )
    atualizado = servico.repositorio.obter_entrega(int(item["id"]))
    assert atualizado["status"] == "EM ANDAMENTO"
    assert atualizado["valor"] == 1234.56
    assert atualizado["protocolo"] == "PROTO-123"

    servico.repositorio.salvar_observacao_competencia(
        eid, "2026-08", "Parcelamento conferir no dia 15"
    )
    assert servico.repositorio.obter_observacao_competencia(
        eid, "2026-08"
    ) == "Parcelamento conferir no dia 15"



def test_sincronizacao_mantem_regimes_canonicos_das_empresas_atuais(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    trilha = servico.repositorio.obter_empresa_por_nome("Mega Motos Trilha")
    servico.repositorio.atualizar_regime_empresa(int(trilha["id"]), "LUCRO PRESUMIDO")
    servico.sincronizar_estrutura_atual()
    trilha = servico.repositorio.obter_empresa_por_nome("Mega Motos Trilha")
    assert trilha["regime"] == "LUCRO REAL"

def test_interface_tem_grade_mensal_e_nao_reintroduz_lista_antiga():
    texto = Path("src/ui/painel_entregas.py").read_text(encoding="utf-8")
    assert "Controle Mensal de Entregas" in texto
    assert "Configurar empresas / obrigações" in texto
    assert "OBSERVAÇÕES" in texto
    assert "Gerar / atualizar competência" in texto
    assert "Checklist de entregas" not in texto
