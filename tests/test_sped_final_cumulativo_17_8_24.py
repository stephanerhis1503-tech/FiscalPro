from pathlib import Path
import tempfile
import zipfile

from src.services.auditoria_icms_st_piscofins_saidas_service import (
    AuditoriaICMSSTPISCOFINSSaidasService,
)


def test_nome_final_remove_sufixos_intermediarios_das_etapas():
    svc = AuditoriaICMSSTPISCOFINSSaidasService
    assert svc.sugerir_nome_sped_final("SPED CONT 07-2026.txt") == "SPED CONT 07-2026_FINAL_CORRIGIDO.txt"
    assert svc.sugerir_nome_sped_final("SPED CONT 07-2026_ICMS_ST_ENTRADAS_CORRIGIDO.txt") == "SPED CONT 07-2026_FINAL_CORRIGIDO.txt"
    assert svc.sugerir_nome_sped_final("SPED CONT 07-2026_ICMS_ST_SAIDAS_CORRIGIDO.txt") == "SPED CONT 07-2026_FINAL_CORRIGIDO.txt"
    assert svc.sugerir_nome_sped_final("SPED CONT 07-2026_FINAL_CORRIGIDO_PVA.txt") == "SPED CONT 07-2026_FINAL_CORRIGIDO.txt"


def test_nome_final_preserva_identidade_de_outro_arquivo_corrigido():
    svc = AuditoriaICMSSTPISCOFINSSaidasService
    assert svc.sugerir_nome_sped_final("SPED_CONT_OUTRA_CORRECAO.txt") == "SPED_CONT_OUTRA_CORRECAO_FINAL_CORRIGIDO.txt"


def test_ui_expoe_sped_final_cumulativo():
    fonte = Path("src/ui/janela_auditoria_icms_st_piscofins_saidas.py").read_text(encoding="utf-8")
    assert "Gerar SPED FINAL corrigido" in fonte
    assert "Selecionar SPED base" in fonte
    assert "sugerir_nome_sped_final" in fonte
    assert "correções da Etapa 1" in fonte


def test_log_identifica_base_cumulativa_e_sped_final():
    fonte = Path("src/services/auditoria_icms_st_piscofins_saidas_service.py").read_text(encoding="utf-8")
    assert "SPED base cumulativo" in fonte
    assert "SPED FINAL corrigido" in fonte
    assert "Correções já existentes no SPED base: preservadas" in fonte


def test_versao_17_8_24():
    from src.core.app_info import VERSAO_APP
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 24)
