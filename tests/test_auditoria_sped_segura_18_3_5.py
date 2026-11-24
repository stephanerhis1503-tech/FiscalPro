"""Regressoes de seguranca da Auditoria Tributaria do SPED Inteligente."""
from pathlib import Path
from types import SimpleNamespace

from src.sped.auditor_tributario import (
    AuditorTributarioSPED,
    DocumentoXMLNFe,
    ItemXMLNFe,
    ResultadoAuditoriaTributaria,
)
from src.sped.corretor_tributario_assistido import CorretorTributarioAssistido


def _item_xml(**trocas):
    campos = dict(
        numero_item="1", codigo="FORN-001", descricao="PECA",
        ncm="83011000", cest="", cfop="6102", cst_icms="00",
        aliquota_icms=12, cst_pis="01", aliquota_pis=1.65,
        cst_cofins="01", aliquota_cofins=7.6, cst_ipi="50", aliquota_ipi=5,
    )
    campos.update(trocas)
    return ItemXMLNFe(**campos)


def _documento(itens):
    return DocumentoXMLNFe(
        chave="1" * 44, numero="1", serie="1", emitente_cnpj="1" * 14,
        destinatario_cnpj="2" * 14, arquivo_origem="teste.xml",
        itens=itens,
    )


def _item_sped():
    return SimpleNamespace(
        numero_item="1", codigo="INTERNO-10", ncm="83011000", cest="",
        cfop="2102", cst_icms="90", aliquota_icms=0,
        cst_pis="50", aliquota_pis=1.65, cst_cofins="50",
        aliquota_cofins=7.6, cst_ipi="49", aliquota_ipi=0,
        descricao_0200="CADEADO", descricao_complementar="",
    )


def _nota():
    return {"numero": "1", "chave": "1" * 44, "ind_oper": "0"}


def test_xml_mesmo_numero_mas_codigo_interno_distinto_sem_erro():
    d = _documento([_item_xml()])
    assert d.localizar_item("1", "INTERNO-10") is not None


def test_xml_numero_nao_localizado_nao_faz_fallback_por_codigo():
    d = _documento([_item_xml()])
    assert d.localizar_item("9", "FORN-001") is None


def test_entrada_nao_confronta_cst_cfop_alq_emitente_com_escrituracao():
    r = ResultadoAuditoriaTributaria()
    AuditorTributarioSPED()._comparar_xml(
        r, 5, _nota(), _item_sped(), _item_xml(), entrada=True,
    )
    assert r.apontamentos == []


def test_entrada_ncm_divergente_e_aviso_sem_correcao():
    r = ResultadoAuditoriaTributaria()
    AuditorTributarioSPED()._comparar_xml(
        r, 5, _nota(), _item_sped(), _item_xml(ncm="83014000"), entrada=True,
    )
    assert len(r.apontamentos) == 1
    assert r.apontamentos[0].nivel == "AVISO"
    assert r.apontamentos[0].campo == "NCM"
    correcoes = CorretorTributarioAssistido().preparar(
        ["|0000|", "|C170|1|INTERNO-10|"], r,
    )
    assert not correcoes.propostas


def test_saida_diferenca_documental_gera_erro():
    r = ResultadoAuditoriaTributaria()
    AuditorTributarioSPED()._comparar_xml(
        r, 5, _nota(), _item_sped(), _item_xml(), entrada=False,
    )
    assert any(a.nivel == "ERRO" and a.campo == "CFOP" for a in r.apontamentos)


def test_filtro_xml_e_limpeza_do_sped_no_codigo_ui():
    codigo = Path("src/ui/janela_sped_inteligente.py").read_text(encoding="utf-8")
    assert 'if filtro == "XML NF-e":\n                origem = "XML NF-e"' in codigo
    assert 'self.importacao_nfe_xml = None' in codigo
    motor = Path("src/sped/motor_sped.py").read_text(encoding="utf-8")
    trecho = motor.split("    def abrir(", 1)[1].split("    def verificar_apuracao_bloco_m(", 1)[0]
    assert 'self.importacao_xml_nfe = None' in trecho
