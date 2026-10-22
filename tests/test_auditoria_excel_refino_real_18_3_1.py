from pathlib import Path

from src.services.ncm_validador_semantico_service import NCMValidadorSemanticoService


def test_plural_fusiveis_retorna_raiz_fusivel():
    assert NCMValidadorSemanticoService._raiz_token("FUSIVEIS") == "FUSIVEL"


def test_modelo_com_numero_adiciona_dominio_motocicleta():
    tokens = NCMValidadorSemanticoService._tokens(
        "PROTETOR CORRENTE BROS160 XRE300 TORK",
        produto=True,
    )
    assert "MOTOCICLETA" in tokens


def test_capacete_65061000_tem_migracao_vigente_2026_no_fluxo():
    fonte = Path("src/services/auditoria_cadastros_excel_service.py").read_text(encoding="utf-8")
    assert 'ncm_atual == "65061000"' in fonte
    assert 'ncm="65061090"' in fonte
    assert 'data_ref > "2026-02-01"' in fonte
    assert "Resolução Gecex 812/2025" in fonte
