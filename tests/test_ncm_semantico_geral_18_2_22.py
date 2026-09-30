from src.services.ncm_validador_semantico_service import (
    CandidatoNCMSemantico,
    NCMValidadorSemanticoService,
    ResultadoValidacaoNCMSemantica,
)
from src.services.auditoria_cadastros_excel_service import (
    AuditoriaCadastrosExcelService,
    STATUS_REVISAR,
)
from src.services.analise_tributaria_lote_service import ItemBrutoLote, ResultadoItemLote


CATALOGO = [
    {
        "ncm": "33059000",
        "descricao": "Outras",
        "descricao_completa": "Preparações para utilização nos cabelos - Outras preparações capilares",
    },
    {
        "ncm": "68138110",
        "descricao": "Pastilhas",
        "descricao_completa": (
            "Guarnições para freios, embreagens ou quaisquer órgãos de fricção - "
            "Guarnições para freios - Pastilhas"
        ),
    },
    {
        "ncm": "90261029",
        "descricao": "Outros",
        "descricao_completa": (
            "Instrumentos e aparelhos para medida ou controle da vazão ou do nível "
            "dos líquidos - Para medida ou controle do nível dos líquidos - Outros"
        ),
    },
    {
        "ncm": "85114000",
        "descricao": "Motores de arranque, mesmo funcionando como geradores",
        "descricao_completa": (
            "Aparelhos e dispositivos elétricos de ignição ou de arranque para motores - "
            "Motores de arranque, mesmo funcionando como geradores"
        ),
    },
    {
        "ncm": "87141000",
        "descricao": "De motocicletas, incluindo os ciclomotores",
        "descricao_completa": (
            "Partes e acessórios dos veículos das posições 87.11 a 87.13 - "
            "De motocicletas, incluindo os ciclomotores"
        ),
    },
]


def validar(descricao: str, ncm: str):
    return NCMValidadorSemanticoService._validar_com_catalogo_teste(
        descricao, ncm, CATALOGO
    )


def test_pastilha_freio_nao_aceita_preparacao_capilar():
    resultado = validar(
        "PASTILHA FREIO TITAN/FAN160 18/BROS160 25/PCX160 CBS (MAXX)",
        "33059000",
    )
    assert resultado.status == "INCOMPATIVEL"
    assert resultado.candidato_principal is not None
    assert resultado.candidato_principal.ncm == "68138110"
    assert resultado.compatibilidade_atual < resultado.candidato_principal.pontuacao


def test_boia_tanque_procura_nivel_de_liquido_no_catalogo_oficial():
    resultado = validar(
        "BOIA TANQUE BROS160 18/21 EDD (MAGNETRON)",
        "33059000",
    )
    assert resultado.status == "INCOMPATIVEL"
    assert resultado.candidato_principal is not None
    assert resultado.candidato_principal.ncm == "90261029"


def test_motor_partida_correto_nao_cria_falso_alerta():
    resultado = validar("MOTOR PARTIDA TITAN 160", "85114000")
    assert resultado.status == "COMPATIVEL"
    assert resultado.ncm_atual == "85114000"


def test_capa_banco_errada_nao_e_tratada_como_capilar():
    resultado = validar("CAPA BANCO SPORT PROTECAO DIVINA (ZAMP)", "33059000")
    assert resultado.status in {"REVISAR", "INCOMPATIVEL"}
    assert resultado.status != "COMPATIVEL"


def test_sanfona_bengala_87141000_nao_vira_falso_erro():
    resultado = validar("SANFONA BENG. 24D VERM (CIRCUIT)", "87141000")
    assert resultado.status == "COMPATIVEL"
    assert resultado.ncm_atual == "87141000"


def test_ncm_em_revisao_nao_manda_corrigir_tributacao_derivada():
    validacao = ResultadoValidacaoNCMSemantica(
        status="REVISAR",
        ncm_atual="33059000",
        compatibilidade_atual=0.0,
        descricao_oficial_atual="Outras preparações capilares",
        candidato_principal=CandidatoNCMSemantico(
            ncm="87141000",
            descricao_oficial="Partes e acessórios de motocicletas",
            pontuacao=48.0,
        ),
        candidatos=(
            CandidatoNCMSemantico(
                ncm="87141000",
                descricao_oficial="Partes e acessórios de motocicletas",
                pontuacao=48.0,
            ),
        ),
        motivo="NCM atual sem compatibilidade suficiente com a descrição.",
    )
    bruto = ItemBrutoLote(
        fonte_tipo="EXCEL",
        arquivo="cadastro.xlsx",
        codigo="3840",
        descricao="CAPA BANCO SPORT PROTECAO DIVINA (ZAMP)",
        ncm="33059000",
        cest_atual="2002200",
        cfop="5405",
        cst_icms_atual="060",
        aliquota_icms_atual=25.0,
        mva_st_atual=34.55,
        aliquota_fcp_st_atual=2.0,
        cst_pis_atual="01",
        aliquota_pis_atual=1.65,
        cst_cofins_atual="01",
        aliquota_cofins_atual=7.60,
        cst_ipi_atual="53",
        aliquota_ipi_atual=14.30,
    )
    analise = ResultadoItemLote(
        fonte_tipo="EXCEL",
        arquivo="cadastro.xlsx",
        documento="",
        chave="",
        numero_item="",
        codigo="3840",
        descricao=bruto.descricao,
        ncm="33059000",
        ncm_oficial="33059000",
        cfop="5405",
        uf_origem="MG",
        uf_destino="MG",
        data_operacao="2026-09-30",
        status="DIVERGÊNCIA",
        confiabilidade=45.0,
        confirmado=False,
        exige_revisao=True,
        divergencias=["Alíquota FCP-ST: atual 2.00% ≠ esperado 0.00%."],
        cst_pis_atual="01",
        aliquota_pis_atual=1.65,
        cst_pis_esperado="01",
        aliquota_pis_esperada=1.65,
        cst_cofins_atual="01",
        aliquota_cofins_atual=7.60,
        cst_cofins_esperado="01",
        aliquota_cofins_esperada=7.60,
        cst_icms_atual="060",
        aliquota_icms_atual=25.0,
        aliquota_icms_esperada=25.0,
        cest_atual="2002200",
        cest_esperado="2002200",
        aliquota_fcp_st_atual=2.0,
        fcp_esperado=0.0,
        cst_ipi_atual="53",
        aliquota_ipi_atual=14.30,
        aliquota_ipi_referencia=14.30,
    )
    item = AuditoriaCadastrosExcelService._converter(
        bruto,
        analise,
        linha_excel=2,
        originais={
            "ncm_original": "33059000",
            "validacao_semantica_geral": validacao,
            "candidatos_ncm": [],
            "cst_icms": "060",
            "cfop": "5405",
            "icms_desonerado": "NÃO",
            "icms_st_indicador": "REVISAR",
            "aliq_icms": 25.0,
            "mva_st": 34.55,
            "aliq_fem": 2.0,
        },
        contexto={
            "regime": "Lucro Real",
            "operacao": "Venda",
            "finalidade": "Revenda",
            "uf_origem": "MG",
            "uf_destino": "MG",
        },
    )

    assert item.status == STATUS_REVISAR
    assert item.divergencias == []
    assert "NCM atual" in item.problema
    assert "FCP-ST" in item.problema


def test_motor_nao_embute_tabela_fixa_peca_para_ncm():
    # A camada de linguagem pode conter sinônimos/conceitos, mas não pode
    # carregar NCMs diretamente. A classificação deve vir do catálogo.
    texto_grupos = repr(NCMValidadorSemanticoService._GRUPOS_SEMANTICOS)
    assert "68138110" not in texto_grupos
    assert "90261029" not in texto_grupos
    assert "87141000" not in texto_grupos
