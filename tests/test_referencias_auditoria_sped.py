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
