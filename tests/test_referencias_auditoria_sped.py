"""Regressoes da camada referencial: nao cria regras ou creditos."""
from src.services import referencias_auditoria_sped_service as modulo


def _ctx():
    return {
        "empresa": "EMPRESA TESTE", "regime": "LUCRO REAL",
        "operacao": "ENTRADA", "finalidade": "REVENDA",
        "uf_origem": "SP", "uf_destino": "MG",
        "data_operacao": "2026-10-01",
    }


def test_consultas_contextuais_cacheadas_e_sem_escrever_banco(monkeypatch):
    chamadas = {"ncm": 0, "tipi": 0, "pis": 0, "icms": 0}
    def ncm(codigo):
        chamadas["ncm"] += 1
        return {"status": "ATIVO", "descricao": "CADEADO", "fonte_codigo": "NCM_OFICIAL"}
    def tipi(codigo):
        chamadas["tipi"] += 1
        return [{"ncm": codigo}]
    def pis(codigo, *, contexto, descricao, ex_tipi):
        chamadas["pis"] += 1
        assert contexto["operacao"] == "ENTRADA"
        return {"status": "REVISAR OPERACAO", "confirmado": False}
    def icms(codigo, *, contexto, descricao):
        chamadas["icms"] += 1
        assert contexto["uf_destino"] == "MG"
        return {"status": "SEM ST", "st_decisao_confirmada": True,
                "st_status": "NAO APLICAVEL", "cest": ""}
    monkeypatch.setattr(modulo.BaseOficialRepository, "buscar_ncm_oficial", ncm)
    monkeypatch.setattr(modulo.BaseOficialRepository, "buscar_tipi", tipi)
    monkeypatch.setattr(modulo.PISCOFINSNacionalService, "analisar", pis)
    monkeypatch.setattr(modulo.ICMSMGLoteIntegracaoService, "analisar", icms)
    service = modulo.ReferenciasAuditoriaSPEDService()
    a = service.consultar_item("83011000", "CADEADO", _ctx())
    b = service.consultar_item("83011000", "CADEADO", _ctx())
    assert a == b
    assert chamadas == {"ncm": 1, "tipi": 1, "pis": 1, "icms": 1}
    assert a["ncm_status"] == "ATIVO"
    assert a["pis_confirmado"] is False
    assert a["st_decisao_confirmada"] is True
    assert "credito" in a["restricao_uso"].lower()


def test_falha_da_base_nao_fabrica_regra(monkeypatch):
    def erro(*args, **kwargs):
        raise RuntimeError("Sem base instalada")
    monkeypatch.setattr(modulo.BaseOficialRepository, "buscar_ncm_oficial", erro)
    monkeypatch.setattr(modulo.PISCOFINSNacionalService, "analisar", erro)
    monkeypatch.setattr(modulo.ICMSMGLoteIntegracaoService, "analisar", erro)
    r = modulo.ReferenciasAuditoriaSPEDService().consultar_item(
        "87141000", "PECAS", _ctx()
    )
    assert r["falha_tecnica"]
    assert r["pis_confirmado"] is False
    assert r["st_decisao_confirmada"] is False
    assert "FALHA" in r["ncm_status"]


def test_sem_data_nao_invoca_pis_nem_icms(monkeypatch):
    def proibido(*args, **kwargs):
        raise AssertionError("consulta sem data nao autorizada")
    monkeypatch.setattr(modulo.PISCOFINSNacionalService, "analisar", proibido)
    monkeypatch.setattr(modulo.ICMSMGLoteIntegracaoService, "analisar", proibido)
    monkeypatch.setattr(modulo.BaseOficialRepository, "buscar_ncm_oficial", lambda _ncm: None)
    monkeypatch.setattr(modulo.BaseOficialRepository, "buscar_tipi", lambda _ncm: [])
    contexto = _ctx()
    contexto["data_operacao"] = ""
    r = modulo.ReferenciasAuditoriaSPEDService().consultar_item(
        "87141000", "PECAS", contexto
    )
    assert "INFORME" in r["pis_status"]
    assert "INFORME" in r["st_status"]


def test_uso_consumo_interno_separa_st_mercadoria_de_recolhimento(monkeypatch):
    """Motor pode enquadrar mercadoria, mas isso nao prova imposto devido."""
    monkeypatch.setattr(
        modulo.BaseOficialRepository, "buscar_ncm_oficial",
        lambda codigo: {"status": "ATIVO", "fonte_codigo": "CATALOGO TESTE"},
    )
    monkeypatch.setattr(
        modulo.BaseOficialRepository, "buscar_tipi", lambda codigo: []
    )
    monkeypatch.setattr(
        modulo.PISCOFINSNacionalService, "analisar",
        lambda *_a, **_kw: {"status": "REVISAR OPERAÇÃO", "confirmado": False},
    )
    monkeypatch.setattr(
        modulo.ICMSMGLoteIntegracaoService, "analisar",
        lambda *_a, **_kw: {
            "st_status": "ICMS-ST/MG CONFIRMADO — MVA ORIGINAL APLICADA",
            "st_decisao_confirmada": True,
            "aliquota_operacao_confirmada": True, "cest": "0107600",
        },
    )
    ctx = _ctx()
    ctx.update({"finalidade": "USO E CONSUMO", "uf_origem": "MG"})
    r = modulo.ReferenciasAuditoriaSPEDService().consultar_item(
        "87141000", "TESTE USO CONSUMO", ctx,
    )
    assert "MVA ORIGINAL APLICADA" in r["st_enquadramento_mercadoria_status"]
    assert "REVISAR ST NA NOTA" in r["st_status"]
    assert r["st_decisao_confirmada"] is False
    assert "NAO CONCLUIDO" in r["st_recolhimento_status"]
    assert "ENTRADA INTERNA" in r["st_difal_status"]
    assert "VEDADO CREDITO" in r["icms_credito_status"]
    assert "MG->MG" in r["restricao_uso"]


def test_uso_consumo_interno_nao_aplica_bloqueio_de_st_difal_interestadual(monkeypatch):
    monkeypatch.setattr(modulo.BaseOficialRepository, "buscar_ncm_oficial", lambda _n: None)
    monkeypatch.setattr(modulo.BaseOficialRepository, "buscar_tipi", lambda _n: [])
    monkeypatch.setattr(modulo.PISCOFINSNacionalService, "analisar", lambda *_a, **_kw: {})
    monkeypatch.setattr(modulo.ICMSMGLoteIntegracaoService, "analisar", lambda *_a, **_kw: {
        "st_status": "ICMS-ST/MG APLICÁVEL — RESPONSABILIDADE A REVISAR",
        "st_decisao_confirmada": False,
    })
    ctx = _ctx()
    ctx["finalidade"] = "USO E CONSUMO"
    r = modulo.ReferenciasAuditoriaSPEDService().consultar_item(
        "87141000", "TESTE", ctx
    )
    assert "st_difal_status" not in r
    assert "enquadramento_mercadoria_status" not in r


def test_uso_consumo_interno_gera_colunas_especificas_no_excel(tmp_path):
    from types import SimpleNamespace
    from openpyxl import load_workbook
    from src.services.ficha_assistida_sped_service import FichaAssistidaSPEDService

    r = {
        "ncm": "87141000", "codigo_produto": "PROD-TESTE",
        "descricao_sped": "MATERIAL DE USO", "empresa": "EMPRESA TESTE",
        "regime": "LUCRO REAL", "operacao": "ENTRADA",
        "finalidade": "USO E CONSUMO", "finalidade_informada": "REVENDA",
        "finalidade_status": "INDICIO_CFOP", "uf_origem": "MG", "uf_destino": "MG",
        "contribuinte": "CONTRIBUINTE", "data_operacao": "2026-10-12",
        "cfop_sped": "1556", "st_status": "REVISAR ST NA NOTA",
        "st_enquadramento_mercadoria_status": "ST ORIGINAL DO MOTOR",
        "st_recolhimento_status": "NAO CONCLUIDO",
        "st_difal_status": "NAO SE APLICA ENTRADA INTERNA",
        "icms_credito_status": "VEDADO CREDITO - REGRA GERAL",
    }
    propostas = FichaAssistidaSPEDService.preparar(
        SimpleNamespace(referencias_fiscais=[r])
    )
    ws = load_workbook(
        FichaAssistidaSPEDService.exportar(propostas, tmp_path / "teste_st.xlsx"),
        read_only=True,
    ).active
    assert ws["H2"].value == "USO E CONSUMO"
    assert ws["R2"].value == "REVISAR ST NA NOTA"
    assert ws["AC2"].value == "ST ORIGINAL DO MOTOR"
    assert ws["AD2"].value == "NAO CONCLUIDO"
    assert ws["AE2"].value == "NAO SE APLICA ENTRADA INTERNA"
    assert ws["AF2"].value == "VEDADO CREDITO - REGRA GERAL"
