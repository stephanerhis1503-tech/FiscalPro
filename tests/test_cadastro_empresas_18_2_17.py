from pathlib import Path

from src.entregas.repositorio import EntregasRepositorio
from src.entregas.servico import EntregasServico
from src.core.app_info import VERSAO_APP


def servico_tmp(tmp_path: Path) -> EntregasServico:
    return EntregasServico(EntregasRepositorio(tmp_path / "controle_entregas.db"))


def test_versao_18_2_17_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split(".")) >= (18, 2, 17)


def test_nova_empresa_manual_permanece_ativa_apos_sincronizacao(tmp_path):
    servico = servico_tmp(tmp_path)
    servico.sincronizar_estrutura_atual()
    empresa_id = servico.cadastrar_empresa(
        "Empresa Teste Ltda",
        "12.345.678/0001-90",
        "LUCRO REAL",
    )

    empresa = servico.repositorio.obter_empresa_por_id(empresa_id)
    assert empresa is not None
    assert empresa["ativa"] == 1
    assert empresa["manual"] == 1
    assert empresa["cnpj"] == "12345678000190"

    servico.sincronizar_estrutura_atual()
    empresa = servico.repositorio.obter_empresa_por_id(empresa_id)
    assert empresa is not None
    assert empresa["ativa"] == 1


def test_nova_empresa_recebe_grade_padrao(tmp_path):
    servico = servico_tmp(tmp_path)
    empresa_id = servico.cadastrar_empresa(
        "Empresa Presumida Ltda",
        "98.765.432/0001-10",
        "LUCRO PRESUMIDO",
    )

    icms = servico.repositorio.obter_modelo_por_empresa_tipo(
        empresa_id, "ICMS", incluir_inativo=True
    )
    credito_pis = servico.repositorio.obter_modelo_por_empresa_tipo(
        empresa_id, "CRÉDITO PIS", incluir_inativo=True
    )
    assert icms is not None and icms["ativo"] == 1
    assert credito_pis is not None and credito_pis["ativo"] == 0


def test_editar_empresa_manual_preserva_id_e_historico(tmp_path):
    servico = servico_tmp(tmp_path)
    empresa_id = servico.cadastrar_empresa(
        "Empresa Antiga Ltda",
        "11.222.333/0001-44",
        "SIMPLES NACIONAL",
    )
    servico.editar_empresa(
        empresa_id,
        "Empresa Nova Ltda",
        "11.222.333/0001-44",
        "LUCRO REAL",
    )
    empresa = servico.repositorio.obter_empresa_por_id(empresa_id)
    assert empresa is not None
    assert empresa["nome"] == "Empresa Nova Ltda"
    assert empresa["regime"] == "LUCRO REAL"
    assert empresa["manual"] == 1


def test_tela_tem_botoes_de_cadastro():
    texto = Path("src/ui/painel_entregas.py").read_text(encoding="utf-8")
    assert "+ Nova empresa" in texto
    assert "Editar empresa" in texto
    assert "JanelaCadastroEmpresa" in texto
