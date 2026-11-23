"""Regressao do diagnostico de cobertura da Ficha Tributaria."""
from src.sped.auditor_tributario import AuditorTributarioSPED
from src.sped import auditor_tributario as modulo


def test_diagnostico_conta_regras_sem_alterar_banco(monkeypatch):
    class Conexao:
        def __init__(self):
            self.executadas = []
        def execute(self, sql):
            self.executadas.append(sql)
            if "tributacao_atual" in sql:
                return self
            return self
        def fetchone(self):
            if "tributacao_atual" in self.executadas[-1]:
                return (0,)
            return (3,)
        def close(self):
            pass
    conexao = Conexao()
    monkeypatch.setattr(modulo.Banco, "conectar", lambda: conexao)
    r = AuditorTributarioSPED._diagnosticar_cadastro_regras()
    assert r == {"tributacao_atual": 0, "tributacao_base_ativa": 3}
    assert all(sql.startswith("SELECT") for sql in conexao.executadas)


def test_falha_no_diagnostico_nao_vira_cobertura_confirmada(monkeypatch):
    def falhar():
        raise RuntimeError("Banco indisponivel")
    monkeypatch.setattr(modulo.Banco, "conectar", falhar)
    assert AuditorTributarioSPED._diagnosticar_cadastro_regras() == {}
