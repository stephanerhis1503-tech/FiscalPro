from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.entregas.servico import EntregasServico
from src.inteligencia.consulta_tributaria import ConsultaTributaria
from src.services.analise_tributaria_lote_service import AnaliseTributariaLoteService
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.services.piscofins_nacional_service import PISCOFINSNacionalService
from src.services.robo_tributario_service import RoboTributarioService


def contexto(empresa: str, regime: str = "Lucro Real") -> dict:
    return {
        "empresa": empresa,
        "regime": regime,
        "operacao": "Venda",
        "finalidade": "Revenda",
        "data_operacao": "2026-08-20",
    }


def test_versao_17826_ou_superior():
    partes = tuple(int(x) for x in VERSAO_APP.split("."))
    assert partes >= (17, 8, 26)


def test_fonte_unica_empresas_regimes():
    esperado = {
        "Mega Motos Trilha": "LUCRO REAL",
        "Mega T.O. E-commerce": "LUCRO REAL",
        "Mega Mix E-commerce": "LUCRO REAL",
        "Mega Motos Comércio": "LUCRO PRESUMIDO",
        "Mega Serviços": "SIMPLES NACIONAL",
        "Mega Serviços Profissionais": "SIMPLES NACIONAL",
    }
    obtido = {p.nome: p.regime for p in EmpresasRegimesService.listar_perfis()}
    assert obtido == esperado
    assert dict(EntregasServico.EMPRESAS_ATUAIS) == esperado


def test_mega_comercio_prevalece_sobre_regime_incorreto():
    ctx = EmpresasRegimesService.aplicar_contexto(
        {"empresa": "Mega Motos Comércio", "regime": "Lucro Real"}
    )
    assert ctx["regime"] == "LUCRO PRESUMIDO"
    assert ctx["regime_origem"] == "EMPRESA"


def test_piscofins_padrao_comercio_presumido():
    # NCM fora do mapeamento monofásico específico: deve cair no padrão cumulativo.
    resultado = PISCOFINSNacionalService.analisar(
        "73181500", contexto=contexto("Mega Motos Comércio", "Lucro Real")
    )
    assert resultado["confirmado"] is False
    assert resultado["regime_apuracao"] == "Cumulativo"
    assert resultado["sugestao_cst_pis"] == "01"
    assert resultado["sugestao_aliquota_pis"] == 0.65
    assert resultado["sugestao_cst_cofins"] == "01"
    assert resultado["sugestao_aliquota_cofins"] == 3.0


def test_piscofins_padrao_trilha_real():
    resultado = PISCOFINSNacionalService.analisar(
        "73181500", contexto=contexto("Mega Motos Trilha", "Lucro Presumido")
    )
    assert resultado["confirmado"] is False
    assert resultado["regime_apuracao"] == "Não cumulativo"
    assert resultado["sugestao_aliquota_pis"] == 1.65
    assert resultado["sugestao_aliquota_cofins"] == 7.6


def test_monofasico_prevalece_sobre_padrao_do_regime():
    for empresa in ("Mega Motos Comércio", "Mega Motos Trilha"):
        resultado = PISCOFINSNacionalService.analisar(
            "40114000", contexto=contexto(empresa)
        )
        assert resultado["confirmado"] is True
        assert resultado["cst_pis"] == "04"
        assert resultado["aliquota_pis"] == 0.0
        assert resultado["cst_cofins"] == "04"
        assert resultado["aliquota_cofins"] == 0.0
        assert "MONOFÁSICO" in resultado["status"]


def test_robo_corrige_regime_pela_empresa_antes_de_analisar():
    consulta = ConsultaTributaria(
        ncm="73181500",
        uf_origem="MG",
        uf_destino="MG",
        regime="Lucro Real",
        operacao="Venda",
        consumidor_final=False,
        empresa="Mega Motos Comércio",
    )
    RoboTributarioService._aplicar_empresa_regime(consulta)
    assert consulta.regime == "LUCRO PRESUMIDO"


def test_lote_resolve_regime_pela_empresa():
    ctx = AnaliseTributariaLoteService._normalizar_contexto(
        {"empresa": "Mega Motos Comércio", "regime": "Lucro Real"}
    )
    assert ctx["empresa"] == "Mega Motos Comércio"
    assert ctx["regime"] == "LUCRO PRESUMIDO"


def test_telas_tributarias_usam_fonte_central():
    base = Path(__file__).resolve().parents[1] / "src" / "ui"
    arquivos = (
        "janela_ficha_tributaria.py",
        "janela_consulta_ncm.py",
        "janela_piscofins_nacional.py",
        "janela_robo_tributario.py",
        "janela_simulador_tributario.py",
        "janela_analise_lote.py",
        "janela_auditoria_cadastros_excel.py",
        "janela_auditoria_cadastros_xml.py",
    )
    for nome in arquivos:
        texto = (base / nome).read_text(encoding="utf-8")
        assert "EmpresasRegimesService" in texto, nome
