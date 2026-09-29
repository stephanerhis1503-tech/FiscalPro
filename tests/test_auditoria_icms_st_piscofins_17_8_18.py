from pathlib import Path

from src.services.auditoria_icms_st_piscofins_service import (
    STATUS_REVISAR_ICMS,
    STATUS_OK,
    STATUS_SEM_CREDITO,
    STATUS_SEM_CREDITO_ZERO,
)


def test_status_icms_proprio_e_ok_no_escopo_st():
    assert STATUS_REVISAR_ICMS.startswith("OK — ST FORA")


def test_ui_nao_conta_icms_proprio_como_pendencia_st():
    texto = Path("src/ui/janela_auditoria_icms_st_piscofins.py").read_text(encoding="utf-8")
    assert 'self.var_filtro = tk.StringVar(value="Pendências ST")' in texto
    assert 'Pendências ST: {pendencias_st}' in texto
    trecho = texto.split('if filtro == "Pendências ST"', 1)[1].split('if filtro == "OK — ST fora"', 1)[0]
    assert "STATUS_REVISAR_ICMS" in trecho
    assert '"OK ST + revisar ICMS próprio"' in texto


def test_resumo_tem_ok_icms_st_total():
    texto = Path("src/services/auditoria_icms_st_piscofins_service.py").read_text(encoding="utf-8")
    assert '"ok_icms_st": por_status.get(STATUS_OK, 0) + por_status.get(STATUS_REVISAR_ICMS, 0)' in texto
    assert '"ok_revisar_icms": por_status.get(STATUS_REVISAR_ICMS, 0)' in texto


def test_versao_17_8_18():
    from src.core.app_info import VERSAO_APP
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 18)
