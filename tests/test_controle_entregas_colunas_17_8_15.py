from pathlib import Path

from src.entregas.repositorio import EntregasRepositorio
from src.entregas.servico import EntregasServico


def servico_tmp(tmp_path: Path) -> EntregasServico:
    return EntregasServico(EntregasRepositorio(tmp_path / "controle_entregas.db"))


def test_17815_remove_colunas_pedidas_da_grade_e_configuracao(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    nomes = [nome for nome, _rotulo, _monetario in servico.OBRIGACOES_PADRAO]
    for removida in ("DOCUMENTOS", "ESCRITURAÇÃO", "DAPI", "DIF. ALÍQUOTA", "REINF"):
        assert removida not in nomes
    for mantida in ("RECEITA MENSAL", "ICMS", "SPED FISCAL", "GNRE", "ISS", "EFD CONTRIBUIÇÕES", "PIS", "COFINS", "PARCELAMENTO"):
        assert mantida in nomes


def test_17815_grade_nao_expoe_colunas_removidas(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    grade = servico.grade_competencia("08/2026")
    assert grade
    for linha in grade:
        for removida in servico.OBRIGACOES_REMOVIDAS_DA_GRADE:
            assert removida not in linha["celulas"]


def test_17815_historico_de_coluna_removida_nao_e_apagado(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    empresa = servico.repositorio.obter_empresa_por_nome("Mega Motos Trilha")
    empresa_id = int(empresa["id"])
    # Simula dado legado anterior à remoção visual.
    modelo_id = servico.repositorio.salvar_modelo(
        empresa_id=empresa_id, tipo_arquivo="DAPI", dia_prazo=9, meses_apos_competencia=1
    )
    assert modelo_id
    servico.sincronizar_estrutura_atual()
    legado = servico.repositorio.obter_modelo_por_empresa_tipo(empresa_id, "DAPI", incluir_inativo=True)
    assert legado is not None
    assert "DAPI" not in [n for n, _r, _m in servico.OBRIGACOES_PADRAO]


def test_17815_exportacao_grade_usa_somente_colunas_atuais(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    destino = tmp_path / "grade.csv"
    servico.exportar_grade_csv(destino, "08/2026")
    cabecalho = destino.read_text(encoding="utf-8-sig").splitlines()[0]
    for removida in ("DOC.", "ESCRITURAÇÃO", "DAPI", "DIF. ALÍQUOTA", "REINF"):
        assert removida not in cabecalho
    assert "SPED FISCAL" in cabecalho
    assert "EFD CONTRIB." in cabecalho
