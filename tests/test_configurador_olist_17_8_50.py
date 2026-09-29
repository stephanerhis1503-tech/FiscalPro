from pathlib import Path
from types import SimpleNamespace

from src.core.app_info import VERSAO_APP
from src.services.configurador_olist_service import ConfiguradorOlistService
from src.services.decisao_operacao_tributaria_service import (
    ComponenteDecisao,
    DecisaoOperacaoTributaria,
)
from src.services.robo_tributario_service import ResultadoRoboTributario


BASE = Path(__file__).resolve().parents[1]


def _componente(valor, status="CONFIRMADO", motivo="ok", confianca=100.0):
    return ComponenteDecisao(valor, status, confianca, motivo)


def _decisao():
    return DecisaoOperacaoTributaria(
        status="CONFIRMADO",
        confiabilidade=100.0,
        cfop=_componente("6102"),
        icms=_componente("CST 000"),
        pis=_componente("CST 01"),
        cofins=_componente("CST 01"),
        destaque_icms=_componente("SIM"),
        icms_st=_componente("NÃO APLICÁVEL"),
        difal=_componente("APLICÁVEL"),
    )


def _instalar_motores_fake(monkeypatch, *, destinatario=False, difal_confirmado=True):
    def robo_fake(consulta):
        ficha = SimpleNamespace(
            aliquota_pis=0.65,
            aliquota_cofins=3.0,
            ipi=0.0,
            cst_ipi="53",
        )
        return ResultadoRoboTributario(
            consulta=consulta,
            ficha=ficha,
            status="CONSISTENTE" if difal_confirmado else "REVISAR",
            confiabilidade=100.0 if difal_confirmado else 70.0,
            diagnosticos=[],
            alertas=[],
            decisao_operacao=_decisao(),
            relatorio="",
        )

    def icms_fake(ncm, contexto=None, descricao=""):
        return {
            "aliquota_operacao": 7.0,
            "aliquota_operacao_confirmada": True,
            "aliquota_operacao_status": "CONFIRMADA — REGRA INTERESTADUAL DE 7%",
            "aliquota_interna_destino": 20.5,
            "aliquota_interna_confirmada": True,
            "fcp": 0.0,
            "fcp_confirmado": True,
            "st_status": "NÃO APLICÁVEL",
            "st_decisao_confirmada": True,
            "cest": "",
            "mva_aplicada": None,
            "mva_tipo": "",
            "exige_revisao": False,
            "confiabilidade_aliquota": 100.0,
            "confiabilidade_fcp": 100.0,
            "confiabilidade_st": 100.0,
        }

    def difal_fake(ncm, contexto=None, descricao=""):
        return {
            "aplicavel": True,
            "confirmado": difal_confirmado,
            "status": "CONFIRMADO" if difal_confirmado else "REVISÃO NECESSÁRIA",
            "motivo": "Venda interestadual a consumidor final.",
            "responsavel": (
                "DESTINATÁRIO — CONTRIBUINTE DO ICMS"
                if destinatario
                else "REMETENTE/PRESTADOR — DESTINATÁRIO NÃO CONTRIBUINTE"
            ),
            "aliquota_interestadual": 7.0,
            "aliquota_interestadual_confirmada": True,
            "aliquota_interestadual_status": "CONFIRMADA",
            "aliquota_interna_destino": 20.5,
            "aliquota_interna_confirmada": difal_confirmado,
            "aliquota_interna_status": "CONFIRMADA" if difal_confirmado else "REVISAR",
            "diferencial_percentual": 13.5,
            "aliquota_fcp": 0.0,
            "fcp_confirmado": True,
            "fcp_status": "NÃO APLICÁVEL",
            "valor_operacao": 100.0,
            "valor_difal": 13.5,
            "valor_fcp": 0.0,
            "confiabilidade": 100.0 if difal_confirmado else 70.0,
        }

    monkeypatch.setattr(
        "src.services.configurador_olist_service.RoboTributarioService.analisar",
        robo_fake,
    )
    monkeypatch.setattr(
        "src.services.configurador_olist_service.ICMSUFService.analisar",
        icms_fake,
    )
    monkeypatch.setattr(
        "src.services.configurador_olist_service.DIFALFCPNacionalService.analisar",
        difal_fake,
    )


def _campo(resultado, nome):
    return next(c for c in resultado.campos_olist if c.campo == nome)


def test_versao_17850_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split(".")) >= (17, 8, 50)


def test_produto_para_nao_contribuinte_gera_configuracao_difal_olist(monkeypatch):
    _instalar_motores_fake(monkeypatch, destinatario=False, difal_confirmado=True)
    resultado = ConfiguradorOlistService.analisar(
        ncm="87141000",
        descricao_produto="Peça para motocicleta",
        empresa="Empresa Nova",
        regime="Lucro Presumido",
        uf_origem="MG",
        uf_destino="BA",
        destinatario_contribuinte=False,
        consumidor_final=True,
        valor_operacao="100,00",
    )
    assert resultado.consulta.regime == "LUCRO PRESUMIDO"
    assert _campo(resultado, "Natureza de operação sugerida").valor.startswith("Venda interestadual")
    assert _campo(resultado, "CFOP").valor == "6102"
    assert _campo(resultado, "ICMS DIFAL para não contribuinte").valor == "SIM"
    assert _campo(resultado, "Alíquota interestadual").valor == "7,00%"
    assert _campo(resultado, "Alíquota interna da UF destino").valor == "20,50%"
    assert _campo(resultado, "Valor DIFAL esperado").valor == "R$ 13,50"
    assert "Configurações > Notas Fiscais > ICMS DIFAL para não contribuinte" in resultado.relatorio


def test_empresa_nova_pode_ser_digitada_sem_cadastro_previo(monkeypatch):
    _instalar_motores_fake(monkeypatch)
    resultado = ConfiguradorOlistService.analisar(
        ncm="87141000",
        descricao_produto="Peça para motocicleta",
        empresa="Minha Nova Empresa Ltda",
        regime="Simples Nacional",
        uf_origem="MG",
        uf_destino="ES",
        destinatario_contribuinte=False,
    )
    assert resultado.consulta.empresa == "Minha Nova Empresa Ltda"
    assert resultado.consulta.regime == "SIMPLES NACIONAL"


def test_contribuinte_nao_ativa_campo_especifico_de_difal_nao_contribuinte(monkeypatch):
    _instalar_motores_fake(monkeypatch, destinatario=True)
    resultado = ConfiguradorOlistService.analisar(
        ncm="87141000",
        descricao_produto="Peça para motocicleta",
        empresa="Empresa Nova",
        regime="Lucro Real",
        uf_origem="MG",
        uf_destino="BA",
        destinatario_contribuinte=True,
    )
    assert _campo(resultado, "ICMS DIFAL para não contribuinte").valor == "NÃO"
    assert "DESTINATÁRIO — CONTRIBUINTE" in _campo(resultado, "Responsável pelo DIFAL").valor


def test_resultado_nao_se_declara_pronto_quando_difal_exige_revisao(monkeypatch):
    _instalar_motores_fake(monkeypatch, destinatario=False, difal_confirmado=False)
    resultado = ConfiguradorOlistService.analisar(
        ncm="87141000",
        descricao_produto="Peça para motocicleta",
        empresa="Empresa Nova",
        regime="Lucro Real",
        uf_origem="MG",
        uf_destino="BA",
        destinatario_contribuinte=False,
    )
    assert resultado.status == "REVISAR"
    assert resultado.pronto_para_configurar is False
    assert _campo(resultado, "Alíquota interna da UF destino").status == "REVISAR"


def test_central_tributaria_expoe_configurador_olist():
    fonte = (BASE / "src/ui/janela_principal.py").read_text(encoding="utf-8")
    assert "JanelaConfiguradorOlist" in fonte
    assert "Configurar venda no Olist" in fonte
    assert "def abrir_configurador_olist" in fonte


def test_tela_olist_prioriza_produto_e_busca_catalogo_ncm():
    fonte = (BASE / "src/ui/janela_configurador_olist.py").read_text(encoding="utf-8")
    assert "Produto / descrição" in fonte
    assert "Buscar NCM no catálogo" in fonte
    assert "Empresa nova / não cadastrada" in fonte
    assert "GERAR CONFIGURAÇÃO OLIST" in fonte
    assert "Configuração Olist" in fonte
