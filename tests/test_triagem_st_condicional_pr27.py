"""Triagem ST de contexto, sem escrita fiscal, com regressao na exportacao PR27."""
from openpyxl import load_workbook

from src.services.ficha_assistida_sped_service import FichaAssistidaSPEDService, PropostaFichaAssistida
from src.services.triagem_st_condicional_service import (
    REFERENCIA, DIVERGENCIA, DOCUMENTAL, triagem_st_condicional,
)


def _p(ncm, desc, codigo="A", cfop="2403", status="CONDICIONAL"):
    return PropostaFichaAssistida(
        identificador=1, ncm=ncm, descricao=desc, codigo_produto=codigo,
        empresa="TRILHA", regime="LUCRO REAL", operacao="ENTRADA",
        finalidade="REVENDA", uf_origem="MG", uf_destino="MG",
        contribuinte="SIM", primeira_data="2026-10-01",
        ultima_data="2026-10-01", itens=1, documentos={"1"},
        st_status={status}, cfops_sped={cfop},
    )


def test_sem_condicional_nao_recebe_alerta():
    assert triagem_st_condicional(_p("65061090", "CAPACETE", status="CONFIRMADO")) == ("", "", "")


def test_grupos_de_revisao_nao_atribuem_tributacao():
    amostras = [
        (_p("65061090", "CAPACETE JOY"), REFERENCIA),
        (_p("39199090", "ADESIVO HONDA"), DIVERGENCIA),
        (_p("32141010", "SILICONE UNIFORT"), DIVERGENCIA),
        (_p("84879000", "RETENTOR BENGALA"), DIVERGENCIA),
        (_p("90328925", "SENSOR TPS MAGNETRON", codigo="90224680"), DIVERGENCIA),
        (_p("65070000", "MECANISMO VISEIRA"), DOCUMENTAL),
        (_p("73151900", "EMENDA DE CORRENTE"), DOCUMENTAL),
        (_p("85444200", "CABO BATERIA"), DOCUMENTAL),
        (_p("90328989", "SENSOR INCLINACAO"), DOCUMENTAL),
        (_p("90328990", "CDI BROS"), DOCUMENTAL),
    ]
    for proposta, esperado in amostras:
        grupo, motivo, acao = triagem_st_condicional(proposta)
        assert grupo == esperado, proposta.descricao
        assert motivo and acao
        assert "APROVADA" not in acao
        assert "ST A RECOLHER" not in acao


def test_exportar_triagem_preserva_planilha_original_e_nao_grava_banco(tmp_path, monkeypatch):
    from src.services import ficha_assistida_sped_service as modulo

    def bloquear(*args, **kwargs):
        raise AssertionError("A triagem nao deve consultar nem gravar banco")

    monkeypatch.setattr(modulo.FichaTributariaRepository, "salvar_tributacao_atual", bloquear)
    monkeypatch.setattr(modulo.FichaTributariaRepository, "preparar_banco", bloquear)

    props = [
        _p("65061090", "CAPACETE"),
        _p("39199090", "ADESIVO TAMPA FILTRO HONDA"),
        _p("32141010", "SILICONE UNIFORT", cfop="1102"),
        _p("73151900", "EMENDA DE CORRENTE"),
        _p("87141000", "PECA FORA DO LOTE", status="CONFIRMADO"),
    ]
    arq = FichaAssistidaSPEDService.exportar(props, tmp_path / "triagem.xlsx")
    wb = load_workbook(arq, read_only=True)
    assert "Propostas para revisao" in wb.sheetnames
    assert "Triagem ST condicional" in wb.sheetnames
    assert "Conferencia ST XML" in wb.sheetnames

    antiga = wb["Propostas para revisao"]
    assert antiga["A2"].value == "PENDENTE DE REVISAO"
    assert antiga["AI2"].value == REFERENCIA
    assert "CAPACETE" in antiga["D2"].value
    assert "PENDENTE" in wb["Triagem ST condicional"]["L2"].value
    triagem = wb["Triagem ST condicional"]
    assert triagem.max_row == 5
    assert triagem["I2"].value == REFERENCIA
    assert triagem["I3"].value == DIVERGENCIA
    assert triagem["I4"].value == DIVERGENCIA
    assert triagem["I5"].value == DOCUMENTAL
    assert "ST A RECOLHER" not in (triagem["K2"].value or "")
    assert antiga["AI3"].value == DIVERGENCIA
