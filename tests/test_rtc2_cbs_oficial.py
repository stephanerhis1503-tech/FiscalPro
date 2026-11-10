"""RTC 2 - respostas oficiais incrementais e seguranca do cliente CBS."""

import json
from decimal import Decimal

import pytest

from src.services.cbs_apuracao_oficial_service import ServicoCBSOficial, ResultadoOficial
from src.services.cbs_apuracao_api_client import ClienteCBSReceita, ErroConsultaCBS

EMPRESA = "12345678000199"
FILIAL = "12345678000270"
OUTRA_RAIZ = "99999999000100"
CHAVE = "31261112345678000199550010000000011000000012"


def debito(chave=CHAVE, apurado=9.0, atualizado="2026-11-10T12:00:00Z", saldo=4.0):
    return {
        "origem": 0,
        "documento": 55,
        "chave": chave,
        "emissao": "2026-11-10T10:00:00Z",
        "registro": "2026-11-10T10:01:00Z",
        "atualizacao": atualizado,
        "cbs": {
            "apurado": apurado,
            "extinto": apurado - saldo,
            "saldoDevedor": saldo,
        },
    }


def credito(chave=CHAVE, apurado=9.0, apropriado=5.0):
    return {
        "origem": 0,
        "documento": 55,
        "chave": chave,
        "emissao": "2026-11-10T10:00:00Z",
        "registro": "2026-11-10T10:01:00Z",
        "atualizacao": "2026-11-10T12:00:00Z",
        "cbs": {
            "apurado": apurado,
            "apropriacao": {
                "aApropriar": apurado - apropriado,
                "apropriado": apropriado,
                "utilizacao": {"naoUtilizado": {"saldoCredor": apropriado}},
            },
        },
    }


def payload(tipo, registros, ni="12345678", ticket="abc.001"):
    return {
        "tiqueteSolicitacao": ticket,
        "ni": ni,
        "niConsumidor": "12345678000199",
        "geradoEm": "2026-11-10T13:00:00Z",
        "apuracao": [{"pa": "11/2026", tipo: registros}],
    }


@pytest.fixture
def servico(tmp_path):
    return ServicoCBSOficial(tmp_path / "rtc2.sqlite3")


def test_debito_importacao_json_documentado(servico):
    retorno = servico.importar(json.dumps(payload("debitos", [debito()])).encode(), "debitos", EMPRESA)
    assert retorno.novos == 1
    assert retorno.periodos == ("2026-11",)
    assert servico.importar(payload("debitos", [debito()]), "debitos", EMPRESA).duplicado
    assert len(servico.historico(EMPRESA)) == 1


def test_credito_apropriado_nao_confundido_com_potencial(servico):
    retorno = servico.importar(payload("creditos", [credito()]), "creditos", EMPRESA)
    assert retorno.novos == 1
    com_chave = servico.filtrar_conciliacao(
        [{
            "direcao": "ENTRADA", "numero_nf": "1", "chave_nfe": CHAVE,
            "valor_cbs": "9.00",
        }],
        [{
            "origem": 0, "modelo": 55, "chave": CHAVE,
            "apurado": "9.00", "apropriado": "5.00", "a_apropriar": "4.00",
            "saldo_devedor": "0.00",
        }],
        "creditos",
    )
    assert com_chave[0]["status"] == "CONFERE"
    assert com_chave[0]["apropriado_oficial"] == "5.00"
    assert com_chave[0]["a_apropriar_oficial"] == "4.00"


def test_consulta_por_raiz_rejeita_ni_incorreto(servico):
    with pytest.raises(ValueError, match="CNPJ basico"):
        servico.importar(payload("debitos", [debito()], ni="99999999"), "debitos", EMPRESA)
    assert not servico.historico(EMPRESA)


def test_arquivo_oficial_incremental_vazio_nao_prova_falta_de_debito(servico):
    resultado = servico.importar(
        {"ni": "12345678", "geradoEm": "2026-11-10T13:00:00Z", "apuracao": []},
        "debitos", EMPRESA,
    )
    assert resultado.novos == 0
    local = [{"direcao": "SAIDA", "numero_nf": "123", "chave_nfe": CHAVE, "valor_cbs": "9.00"}]
    linhas = servico.filtrar_conciliacao(local, [], "debitos")
    assert linhas[0]["status"] == "SEM_DADO_NESTE_RETORNO"


def test_versao_atualizada_substitui_saldo_sem_somar_debito(servico):
    assert servico.importar(payload("debitos", [debito()]), "debitos", EMPRESA).novos == 1
    revisado = payload("debitos", [debito(atualizado="2026-11-11T11:00:00Z", saldo=2.0)])
    resultado = servico.importar(revisado, "debitos", EMPRESA)
    assert resultado.atualizados == 1
    with servico._conectar() as con:
        linhas = con.execute(
            "SELECT saldo_devedor FROM cbs_oficial_registros WHERE cnpj_base='12345678'"
        ).fetchall()
    assert [x[0] for x in linhas] == ["2.00"]


def test_resposta_antiga_nao_sobrescreve_atualizada(servico):
    mais_novo = payload("debitos", [debito(atualizado="2026-11-12T12:00:00Z", saldo=2.0)])
    mais_antigo = payload("debitos", [debito(atualizado="2026-11-10T12:00:00Z", saldo=4.0)])
    assert servico.importar(mais_novo, "debitos", EMPRESA).novos == 1
    assert servico.importar(mais_antigo, "debitos", EMPRESA).ignorados_antigos == 1


def test_filiares_compartilham_raiz_mas_xml_estritamente_separado(servico):
    assert servico.cnpj_base(EMPRESA) == servico.cnpj_base(FILIAL)
    assert servico.cnpj_base(OUTRA_RAIZ) != servico.cnpj_base(EMPRESA)


def test_conciliacao_nao_duplicar_registros_oficiais_mesma_chave(servico):
    local = [{"direcao": "SAIDA", "numero_nf": "1", "chave_nfe": CHAVE, "valor_cbs": "9.00"}]
    oficial = [
        {"origem": 0, "modelo": 55, "chave": CHAVE, "apurado": "9.00", "saldo_devedor": "1.00"},
        {"origem": 0, "modelo": 55, "chave": CHAVE, "apurado": "9.00", "saldo_devedor": "0.00"},
    ]
    assert servico.filtrar_conciliacao(local, oficial, "debitos")[0]["status"] == "MULTIPLOS_OFICIAIS_REVISAR"


def test_tipo_e_json_invalidos_nao_alteram_banco(servico):
    with pytest.raises(ValueError):
        servico.importar(payload("debitos", [debito()]), "creditos", EMPRESA)
    with pytest.raises(ValueError):
        servico.importar(b'{"ni":', "debitos", EMPRESA)
    assert servico.historico(EMPRESA) == []


def test_abertura_cliente_usa_cnpj_base_e_sem_webhook(servico):
    cliente = ClienteCBSReceita("token-de-teste", servico)
    requisicoes = []
    cliente._json = lambda metodo, url, corpo=None: (
        requisicoes.append((metodo, url, corpo)) or
        {"tiqueteSolicitacao": "abc.001"}
    )
    ticket = cliente.solicitar(EMPRESA, "debitos")
    assert ticket == "abc.001"
    assert requisicoes == [
        ("POST", "https://api.receitafederal.gov.br/apuracao-cbs/v2/debitos/12345678", {"urlRetorno": ""})
    ]
    assert len(servico.listar_tiquetes(EMPRESA)) == 1
    with pytest.raises(ErroConsultaCBS, match="pendente"):
        cliente.solicitar(FILIAL, "debitos")


def test_situacao_sem_credencial_em_log(servico):
    cliente = ClienteCBSReceita("token-teste", servico)
    servico.registrar_tiquete(EMPRESA, "debitos", "abc.001")
    cliente._json = lambda *_args, **_kw: {"situacao": "CONCLUIDA"}
    assert cliente.situacao("abc.001") == "CONCLUIDA"
    assert servico.listar_tiquetes(EMPRESA)[0]["situacao"] == "CONCLUIDA"


def test_token_exige_valor():
    with pytest.raises(ValueError):
        ClienteCBSReceita("")


def test_oauth_receita_gera_token_com_basic_e_sem_persistencia():
    from base64 import b64encode
    from src.services.receita_integra_auth import AutenticadorReceitaIntegra, TOKEN_URL

    chamadas = []
    class Resposta:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, _size):
            return b'{"access_token":"abc.jwt.token","expires_in":3600,"token_type":"bearer"}'

    class Abertura:
        def open(self, req, timeout):
            chamadas.append((req, timeout))
            return Resposta()

    token = AutenticadorReceitaIntegra(Abertura()).obter_token("cliente-teste", "segredo-ficticio")
    assert token.valor == "abc.jwt.token"
    assert token.expira_em_segundos == 3600
    req, timeout = chamadas[0]
    assert req.full_url == TOKEN_URL
    assert req.get_method() == "POST"
    assert req.data == b"grant_type=client_credentials"
    esperado = b64encode(b"cliente-teste:segredo-ficticio").decode("ascii")
    assert req.get_header("Authorization") == "Basic " + esperado
    assert timeout == 30


def test_oauth_receita_nao_retorna_segredo_em_erro_http():
    from io import BytesIO
    from urllib.error import HTTPError
    from src.services.receita_integra_auth import AutenticadorReceitaIntegra, ErroAutenticacaoReceita

    class Abertura:
        def open(self, req, timeout):
            raise HTTPError(req.full_url, 401, "Unauthorized", {}, BytesIO(b"secret-vazado"))

    with pytest.raises(ErroAutenticacaoReceita) as exc:
        AutenticadorReceitaIntegra(Abertura()).obter_token("id-ficticio", "segredo-ficticio")
    assert "segredo-ficticio" not in str(exc.value)
    assert "secret-vazado" not in str(exc.value)


def test_oauth_receita_rejeita_token_sem_validade():
    from src.services.receita_integra_auth import AutenticadorReceitaIntegra, ErroAutenticacaoReceita

    class Resposta:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, _size):
            return b'{"access_token":"token-teste","token_type":"bearer"}'
    class Abertura:
        def open(self, req, timeout):
            return Resposta()

    with pytest.raises(ErroAutenticacaoReceita):
        AutenticadorReceitaIntegra(Abertura()).obter_token("id", "secret")


def test_oauth_receita_nao_aceita_client_id_vazio():
    from src.services.receita_integra_auth import AutenticadorReceitaIntegra
    with pytest.raises(ValueError):
        AutenticadorReceitaIntegra().obter_token("", "secret")


def test_retorno_ni_consumidor_diferente_mas_ni_empresa_correto(servico):
    resposta = payload("debitos", [debito()])
    resposta["niConsumidor"] = "99999999000100"
    assert servico.importar(resposta, "debitos", EMPRESA).novos == 1


def test_retorno_ni_incorreto_informa_ambas_raizes_sem_importar(servico):
    resposta = payload("debitos", [debito()], ni="99999999")
    with pytest.raises(ValueError, match="empresa selecionada = 12345678") as exc:
        servico.importar(resposta, "debitos", EMPRESA)
    assert "retorno oficial (campo ni) = 99999999" in str(exc.value)
    assert servico.historico(EMPRESA) == []


def test_retorno_tiquete_diferente_bloqueia_antes_de_importar(servico):
    resposta = payload("debitos", [debito()], ticket="outro-ticket")
    with pytest.raises(ValueError, match="tiquete"):
        servico.importar(resposta, "debitos", EMPRESA, ticket="ticket-original")
    assert servico.historico(EMPRESA) == []


def test_retorno_sem_ni_valido_bloqueia_importacao(servico):
    resposta = payload("debitos", [debito()])
    resposta["ni"] = "12345678000199"
    with pytest.raises(ValueError, match="Campo ni"):
        servico.importar(resposta, "debitos", EMPRESA)
    assert servico.historico(EMPRESA) == []


@pytest.mark.parametrize(
    "status,esperado",
    [
        (400, "HTTP 400"),
        (401, "HTTP 401"),
        (403, "HTTP 403"),
    ],
)
def test_autenticacao_distingue_codigo_e_nao_revela_segredo(status, esperado):
    from io import BytesIO
    from urllib.error import HTTPError
    from src.services.receita_integra_auth import AutenticadorReceitaIntegra, ErroAutenticacaoReceita

    class Abertura:
        def open(self, req, timeout):
            raise HTTPError(req.full_url, status, "Denied", {}, BytesIO(b"secret-do-retorno"))

    with pytest.raises(ErroAutenticacaoReceita) as erro:
        AutenticadorReceitaIntegra(Abertura()).obter_token("id-ficticio", "segredo-ficticio")
    assert esperado in str(erro.value)
    assert "segredo-ficticio" not in str(erro.value)
    assert "secret-do-retorno" not in str(erro.value)



def test_recupera_tiquete_concluido_sem_nova_solicitacao(servico):
    servico.registrar_tiquete(EMPRESA, "debitos", "ticket-concluido")
    servico.atualizar_tiquete("ticket-concluido", "CONCLUIDA")
    recuperado = servico.recuperar_ultimo_tiquete(EMPRESA, "debitos")
    assert recuperado["ticket"] == "ticket-concluido"
    assert recuperado["situacao"] == "CONCLUIDA"
    assert servico.consultas_hoje(EMPRESA, "debitos") <= 1


def test_recuperacao_respeita_raiz_e_tipo(servico):
    servico.registrar_tiquete(EMPRESA, "debitos", "ticket-debito")
    servico.registrar_tiquete(EMPRESA, "creditos", "ticket-credito")
    servico.registrar_tiquete(OUTRA_RAIZ, "debitos", "ticket-outro")
    assert servico.recuperar_ultimo_tiquete(EMPRESA, "debitos")["ticket"] == "ticket-debito"
    assert servico.recuperar_ultimo_tiquete(EMPRESA, "creditos")["ticket"] == "ticket-credito"
    assert servico.recuperar_ultimo_tiquete(OUTRA_RAIZ, "debitos")["ticket"] == "ticket-outro"


def test_recupera_ultimo_tiquete_sem_repetir_ja_importado(servico):
    servico.registrar_tiquete(EMPRESA, "debitos", "ticket-pendente")
    servico.registrar_tiquete(EMPRESA, "debitos", "ticket-importado")
    servico.atualizar_tiquete("ticket-importado", "IMPORTADA")
    assert servico.recuperar_ultimo_tiquete(EMPRESA, "debitos")["ticket"] == "ticket-pendente"
    servico.atualizar_tiquete("ticket-pendente", "EXPIRADA")
    assert servico.recuperar_ultimo_tiquete(EMPRESA, "debitos") is None
