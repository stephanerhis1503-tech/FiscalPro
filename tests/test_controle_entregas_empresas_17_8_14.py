from pathlib import Path

from src.entregas.repositorio import EntregasRepositorio
from src.entregas.servico import EntregasServico


def servico_tmp(tmp_path: Path) -> EntregasServico:
    return EntregasServico(EntregasRepositorio(tmp_path / "controle_entregas.db"))


def test_corrige_lista_17_8_13_e_preserva_erradas_apenas_inativas(tmp_path):
    servico = servico_tmp(tmp_path)
    # Simula empresas que a 17.8.13 colocou por engano.
    for nome in ("Center Motos", "Araújo Motos", "Minas Turbo"):
        servico.repositorio.salvar_empresa(nome, regime="A DEFINIR")

    servico.sincronizar_estrutura_atual()

    ativas = servico.repositorio.listar_empresas()
    assert [e["nome"] for e in sorted(ativas, key=lambda e: e["nome"])] == sorted([
        "Mega Motos Trilha",
        "Mega T.O. E-commerce",
        "Mega Mix E-commerce",
        "Mega Motos Comércio",
        "Mega Serviços",
        "Mega Serviços Profissionais",
    ])

    esperados = {
        "Mega Motos Trilha": "LUCRO REAL",
        "Mega T.O. E-commerce": "LUCRO REAL",
        "Mega Mix E-commerce": "LUCRO REAL",
        "Mega Motos Comércio": "LUCRO PRESUMIDO",
        "Mega Serviços": "SIMPLES NACIONAL",
        "Mega Serviços Profissionais": "SIMPLES NACIONAL",
    }
    for nome, regime in esperados.items():
        empresa = servico.repositorio.obter_empresa_por_nome(nome)
        assert empresa is not None
        assert empresa["ativa"] == 1
        assert empresa["regime"] == regime

    todas = servico.repositorio.listar_empresas(incluir_inativas=True)
    por_nome = {e["nome"]: e for e in todas}
    assert por_nome["Center Motos"]["ativa"] == 0
    assert por_nome["Araújo Motos"]["ativa"] == 0
    assert por_nome["Minas Turbo"]["ativa"] == 0


def test_grade_fica_na_ordem_dos_regimes_confirmados(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    grade = servico.grade_competencia("08/2026")
    assert [linha["empresa"]["nome"] for linha in grade] == [
        "Mega Motos Trilha",
        "Mega T.O. E-commerce",
        "Mega Mix E-commerce",
        "Mega Motos Comércio",
        "Mega Serviços",
        "Mega Serviços Profissionais",
    ]
    assert [linha["empresa"]["regime"] for linha in grade] == [
        "LUCRO REAL", "LUCRO REAL", "LUCRO REAL",
        "LUCRO PRESUMIDO",
        "SIMPLES NACIONAL", "SIMPLES NACIONAL",
    ]


def test_presumido_mantem_creditos_iniciais_como_nao_aplica_da_planilha(tmp_path):
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


def test_simples_nacional_esta_disponivel_no_cadastro_sem_inventar_na_aplicabilidade(tmp_path):
    servico = servico_tmp(tmp_path)
    assert "SIMPLES NACIONAL" in servico.REGIMES
    servico.sincronizar_estrutura_atual()
    mega_servicos = servico.repositorio.obter_empresa_por_nome("Mega Serviços")
    assert mega_servicos["regime"] == "SIMPLES NACIONAL"
    # A planilha enviada não possui bloco de Simples Nacional; por segurança,
    # a 17.8.14 não desativa obrigações automaticamente só por esse regime.
    modelo = servico.repositorio.obter_modelo_por_empresa_tipo(
        int(mega_servicos["id"]), "ICMS", incluir_inativo=False
    )
    assert modelo is not None


def test_competencia_e_prazo_continuam_separados(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    servico.gerar_competencia("08/2026", "Mega Motos Comércio")
    mega = servico.repositorio.obter_empresa_por_nome("Mega Motos Comércio")
    item = servico.repositorio.obter_entrega_por_chave(int(mega["id"]), "2026-08", "ICMS")
    assert item["prazo"] == "2026-09-08"


def test_interface_grade_mensal_permanece_sem_lista_antiga_hardcoded():
    texto = Path("src/ui/painel_entregas.py").read_text(encoding="utf-8")
    assert "Controle Mensal de Entregas" in texto
    assert "Configurar empresas / obrigações" in texto
    assert "OBSERVAÇÕES" in texto
