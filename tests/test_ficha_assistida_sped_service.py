"""Ficha Assistida: geracao sem escrita, aprovacao individual e seguranca."""
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from src.services import ficha_assistida_sped_service as modulo


def _ref(produto="A", **kwargs):
    dado = {
        "ncm": "87141000", "codigo_produto": produto,
        "descricao_sped": "PECA DE TESTE",
        "empresa": "EMPRESA TESTE", "regime": "LUCRO REAL",
        "operacao": "ENTRADA", "finalidade": "REVENDA",
        "uf_origem": "SP", "uf_destino": "MG", "contribuinte": "CONTRIBUINTE",
        "data_operacao": "2026-10-15", "chave": "3" * 44, "nota": "101",
        "cfop_sped": "2102", "pis_status": "REVISAR",
        "st_status": "CONDICIONAL", "ncm_fonte": "FONTE TESTE",
        "falha_tecnica": False,
    }
    dado.update(kwargs)
    return dado


def _proposta():
    return modulo.FichaAssistidaSPEDService.preparar(
        SimpleNamespace(referencias_fiscais=[_ref()])
    )[0]


def _campos(**kw):
    v = {
        "vigencia_inicio": "2026-10-01", "vigencia_fim": "2026-10-31",
        "fonte": "NORMA DE TESTE COM ARTIGO CONFERIDO",
        "cfop": "2102",
    }
    v.update(kw)
    return v


def test_preparar_agrega_contexto_e_nao_acessa_banco(monkeypatch):
    def proibido(*_a, **_k):
        raise AssertionError("consulta ou gravacao do banco nao autorizada")
    monkeypatch.setattr(modulo.FichaTributariaRepository, "preparar_banco", proibido)
    monkeypatch.setattr(modulo.FichaTributariaRepository, "salvar_tributacao_atual", proibido)
    refs = [_ref(), _ref(chave="4"*44, data_operacao="2026-10-22"), _ref(produto="B")]
    propostas = modulo.FichaAssistidaSPEDService.preparar(
        SimpleNamespace(referencias_fiscais=refs)
    )
    assert len(propostas) == 2
    assert sum(p.itens for p in propostas) == 3
    assert all(p.regra_id is None for p in propostas)
    assert all(p.produtos_no_ncm == 2 for p in propostas)
    assert any(p.primeira_data == "2026-10-15" and p.ultima_data == "2026-10-22" for p in propostas)


@pytest.mark.parametrize(
    "campos,rev,escopo",
    [
        (_campos(), False, True),
        (_campos(), True, False),
        (_campos(fonte=""), True, True),
        (_campos(cfop=""), True, True),
        (_campos(vigencia_inicio="2026-10-20"), True, True),
        (_campos(icms_st="SIM"), True, True),
    ],
)
def test_bloqueio_sem_confirmacao_ou_fundamento(monkeypatch, campos, rev, escopo):
    monkeypatch.setattr(
        modulo.FichaTributariaRepository,
        "salvar_tributacao_atual",
        lambda *_a, **_k: pytest.fail("Gravacao nao autorizada"),
    )
    with pytest.raises(ValueError):
        modulo.FichaAssistidaSPEDService.aprovar(
            _proposta(), campos,
            confirmar_revisao=rev, confirmar_abrangencia_ncm=escopo,
        )


def test_aprovacao_grava_uma_regra_com_campos_explicitamente_informados(monkeypatch):
    gravadas = []
    def salvar(dados, **kwargs):
        gravadas.append((dados, kwargs))
        return 42
    monkeypatch.setattr(
        modulo.FichaTributariaRepository, "salvar_tributacao_atual", salvar
    )
    p = _proposta()
    id_regra = modulo.FichaAssistidaSPEDService.aprovar(
        p, _campos(),
        confirmar_revisao=True, confirmar_abrangencia_ncm=True,
    )
    assert id_regra == 42
    assert p.regra_id == 42
    assert len(gravadas) == 1
    regra, opcoes = gravadas[0]
    assert regra["ncm"] == p.ncm
    assert regra["operacao"] == "ENTRADA"
    assert regra["regime"] == "LUCRO REAL"
    assert regra["cfop"] == "2102"
    assert "icms_st" not in regra
    assert "aliquota_pis" not in regra
    assert "[FISCALPRO_ASSISTIDA_CAMPOS:cfop]" in regra["observacoes"]
    assert opcoes["encerrar_anterior"] is False
    with pytest.raises(ValueError, match="ja foi salva"):
        modulo.FichaAssistidaSPEDService.aprovar(
            p, _campos(), confirmar_revisao=True,
            confirmar_abrangencia_ncm=True,
        )


def test_exportar_planilha_nao_sugere_tributacao_e_escapa_formulas(tmp_path):
    p = _proposta()
    p.descricao = "=HYPERLINK(\"https://invalido.test\",\"abrir\")"
    destino = modulo.FichaAssistidaSPEDService.exportar([p], tmp_path / "triagem.xlsx")
    wb = load_workbook(destino)
    ws = wb["Propostas para revisao"]
    assert ws["A2"].value == "PENDENTE DE REVISAO"
    assert ws["D2"].data_type != "f"
    assert ws["D2"].value.startswith("'=")
    assert ws["P2"].value == "2102"
    assert "NAO aprovado" in ws["P1"].value
    assert "CST" not in " ".join(str(c.value) for c in ws[1])


def test_cfop_uso_consumo_bloqueia_finalidade_padrao(monkeypatch):
    p = modulo.FichaAssistidaSPEDService.preparar(
        SimpleNamespace(referencias_fiscais=[
            _ref(cfop_sped="1556", codigo_produto="HIGIENE", descricao_sped="PAPEL HIGIENICO"),
        ])
    )[0]
    assert p.requer_revisao_finalidade
    assert "USO E CONSUMO" in p.aviso_finalidade
    monkeypatch.setattr(
        modulo.FichaTributariaRepository,
        "salvar_tributacao_atual",
        lambda *_a, **_k: pytest.fail("Aprovacao incorreta"),
    )
    with pytest.raises(ValueError, match="finalidade"):
        modulo.FichaAssistidaSPEDService.aprovar(
            p, _campos(), confirmar_revisao=True, confirmar_abrangencia_ncm=True,
        )
    with pytest.raises(ValueError, match="indica USO E CONSUMO"):
        modulo.FichaAssistidaSPEDService.aprovar(
            p, _campos(finalidade_revisada="REVENDA"),
            confirmar_revisao=True, confirmar_abrangencia_ncm=True,
        )


def test_uso_consumo_revisado_salva_finalidade_explicita(monkeypatch):
    p = modulo.FichaAssistidaSPEDService.preparar(
        SimpleNamespace(referencias_fiscais=[
            _ref(cfop_sped="1407", codigo_produto="LAVAGEM"),
        ])
    )[0]
    aprovados = []
    monkeypatch.setattr(
        modulo.FichaTributariaRepository,
        "salvar_tributacao_atual",
        lambda dados, **_k: aprovados.append(dados) or 19,
    )
    modulo.FichaAssistidaSPEDService.aprovar(
        p, _campos(finalidade_revisada="USO E CONSUMO"),
        confirmar_revisao=True, confirmar_abrangencia_ncm=True,
    )
    assert aprovados[0]["finalidade"] == "USO E CONSUMO"
    assert "CFOP observado: 1407" in aprovados[0]["observacoes"]


def test_outras_entradas_exige_justificativa():
    p = modulo.FichaAssistidaSPEDService.preparar(
        SimpleNamespace(referencias_fiscais=[
            _ref(cfop_sped="1949"),
        ])
    )[0]
    assert p.requer_revisao_finalidade
    with pytest.raises(ValueError, match="justificativa"):
        modulo.FichaAssistidaSPEDService.aprovar(
            p, _campos(finalidade_revisada="OUTRA"),
            confirmar_revisao=True, confirmar_abrangencia_ncm=True,
        )


def test_cfops_distintos_mesmo_produto_geram_propostas_separadas():
    refs = [
        _ref(cfop_sped="1403", data_operacao="2026-10-01"),
        _ref(cfop_sped="1949", data_operacao="2026-10-03"),
    ]
    propostas = modulo.FichaAssistidaSPEDService.preparar(
        SimpleNamespace(referencias_fiscais=refs)
    )
    assert len(propostas) == 2
    assert {tuple(p.cfops_sped) for p in propostas} == {("1403",), ("1949",)}


def test_contexto_sem_data_nao_permite_aprovacao():
    p = _proposta()
    p.primeira_data = ""
    with pytest.raises(ValueError, match="datas"):
        modulo.FichaAssistidaSPEDService.aprovar(
            p, _campos(), confirmar_revisao=True,
            confirmar_abrangencia_ncm=True,
        )
