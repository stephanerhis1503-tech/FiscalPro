from src.services.ncm_validador_semantico_service import NCMValidadorSemanticoService


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


def test_motor_nao_embute_tabela_fixa_peca_para_ncm():
    # A camada de linguagem pode conter sinônimos/conceitos, mas não pode
    # carregar NCMs diretamente. A classificação deve vir do catálogo.
    texto_grupos = repr(NCMValidadorSemanticoService._GRUPOS_SEMANTICOS)
    assert "68138110" not in texto_grupos
    assert "90261029" not in texto_grupos
    assert "87141000" not in texto_grupos
