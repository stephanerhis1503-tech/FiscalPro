from __future__ import annotations

from pathlib import Path

import src.ui.painel_manifestacao_nfe as painel_mod
from src.ui.painel_manifestacao_nfe import PainelManifestacaoNFe


class VarFake:
    def __init__(self, valor=""):
        self.valor = valor

    def get(self):
        return self.valor

    def set(self, valor):
        self.valor = valor


class ServicoLocalFake:
    def __init__(self, xml_por_chave):
        self.xml_por_chave = dict(xml_por_chave)
        self.chamadas = []

    def obter_xml_completo(self, empresa_id, chave):
        self.chamadas.append((empresa_id, chave))
        return self.xml_por_chave.get(chave, "")


def _painel_sem_tk(tmp_path: Path):
    painel = object.__new__(PainelManifestacaoNFe)
    painel.var_pasta_xml = VarFake(str(tmp_path))
    painel.var_status = VarFake("")
    painel._empresa_selecionada = lambda: {"id": 7, "nome": "MEGA MOTOS TRILHA", "cnpj": "11111111000191"}
    return painel


def test_destino_xml_organiza_por_empresa_ano_mes(tmp_path):
    painel = _painel_sem_tk(tmp_path)
    reg = {
        "chave": "31260911111111000191550010000000011000000011",
        "emitente_nome": "PARANA FERRAGENS LTDA (IND)",
        "data_emissao": "2026-09-23T09:13:00-03:00",
    }
    destino = painel._destino_xml_nota(painel._empresa_selecionada(), reg)
    assert destino.parent == tmp_path / "MEGA MOTOS TRILHA" / "2026" / "09"
    assert destino.suffix == ".xml"
    assert reg["chave"] in destino.name
    assert "PARANA FERRAGENS" in destino.name


def test_download_manual_salva_somente_xml_completo_sem_sincronizar(tmp_path, monkeypatch):
    painel = _painel_sem_tk(tmp_path)
    chave_ok = "31260911111111000191550010000000011000000011"
    chave_resumo = "31260911111111000191550010000000021000000022"
    painel.servico = ServicoLocalFake({chave_ok: "<nfeProc><NFe/></nfeProc>"})
    monkeypatch.setattr(painel_mod.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(painel_mod.messagebox, "showwarning", lambda *args, **kwargs: None)

    painel._exportar_xmls_locais([
        {
            "chave": chave_ok,
            "emitente_nome": "FORNECEDOR TESTE",
            "data_emissao": "2026-09-23T10:00:00-03:00",
            "tem_xml_completo": 1,
        },
        {
            "chave": chave_resumo,
            "emitente_nome": "OUTRO FORNECEDOR",
            "data_emissao": "2026-09-23T10:00:00-03:00",
            "tem_xml_completo": 0,
        },
    ])

    arquivos = list(tmp_path.rglob("*.xml"))
    assert len(arquivos) == 1
    assert chave_ok in arquivos[0].name
    assert arquivos[0].read_text(encoding="utf-8") == "<nfeProc><NFe/></nfeProc>"
    assert painel.servico.chamadas == [(7, chave_ok)]
    assert "XMLs salvos: 1" in painel.var_status.get()
    assert "indisponíveis: 1" in painel.var_status.get()
