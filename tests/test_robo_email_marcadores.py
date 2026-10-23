from datetime import datetime
from pathlib import Path

from src.robo_email.config import ConfiguracaoRoboEmail
from src.robo_email.gmail_client import MensagemGmail
from src.robo_email.servico import RoboEmailService


class ClienteFake:
    def __init__(self, mensagens):
        self.mensagens = {m.id: m for m in mensagens}
        self.aplicados = []

    def listar_ids(self, consulta, limite):
        return [{"id": mid} for mid in list(self.mensagens)[:limite]]

    def listar_rotulos(self):
        return [
            {"id": "TRILHA", "name": "MEGA MOTOS TRILHA"},
            {"id": "COMERCIO", "name": "MEGA MOTOS COMERCIO"},
            {"id": "MIX", "name": "MEGA MIX E-COMERCE"},
            {"id": "TO", "name": "MEGA TO E-COMERCE"},
            {"id": "SERVICOS", "name": "MEGA MOTOS SERVIÇOS"},
            {"id": "PROF", "name": "MEGA SERVIÇOS PROFISSIONAL"},
        ]

    def obter_mensagem(self, mensagem_id):
        return self.mensagens[mensagem_id]

    def aplicar_rotulo(self, mensagem_id, rotulo_id):
        self.aplicados.append((mensagem_id, rotulo_id))


def _mensagem(mid, destinatarios, assunto="", snippet="", labels=None):
    return MensagemGmail(
        id=mid,
        thread_id=f"t-{mid}",
        remetente="fornecedor@example.com",
        destinatarios=destinatarios,
        assunto=assunto,
        data=datetime(2026, 10, 22, 8, 0),
        snippet=snippet,
        corpo_texto="",
        corpo_html="",
        anexos=[],
        label_ids=list(labels or []),
    )


def _config(tmp_path):
    cred = tmp_path / "cred.json"
    cred.write_text("{}", encoding="utf-8")
    return ConfiguracaoRoboEmail(
        caminho_credenciais=str(cred),
        pasta_destino=str(tmp_path / "docs"),
        dias_retroativos=30,
        limite_mensagens=100,
    )


def test_classificador_aplica_marcador_por_alias_sem_baixar_anexo(tmp_path):
    cliente = ClienteFake([
        _mensagem(
            "1",
            "grupomegamotos.fiscal+megamix@gmail.com",
            "Documento fiscal",
        )
    ])
    resultado = RoboEmailService(_config(tmp_path), cliente=cliente).classificar_marcadores()

    assert cliente.aplicados == [("1", "MIX")]
    assert resultado.marcadores_aplicados == 1
    assert resultado.arquivos_baixados == 0
    assert resultado.links_baixados == 0


def test_classificador_nao_repete_marcador_existente(tmp_path):
    cliente = ClienteFake([
        _mensagem(
            "1",
            "grupomegamotos.fiscal+megatrilha@gmail.com",
            labels=["TRILHA"],
        )
    ])
    resultado = RoboEmailService(_config(tmp_path), cliente=cliente).classificar_marcadores()

    assert cliente.aplicados == []
    assert resultado.mensagens_ja_processadas == 1


def test_classificador_deixa_ambiguo_sem_marcador(tmp_path):
    cliente = ClienteFake([
        _mensagem(
            "1",
            "grupomegamotos.fiscal@gmail.com",
            assunto="Documento disponível",
        )
    ])
    resultado = RoboEmailService(_config(tmp_path), cliente=cliente).classificar_marcadores()

    assert cliente.aplicados == []
    assert resultado.mensagens_sem_classificacao == 1
