"""Homologacao automatizada da Ficha contra C170, em SQLite 100% isolado.

Dados sinteticos, sem empresa real nem valores fiscais homologados.
Executado com pytest/tmp_path no runner; nenhum banco do usuario e aberto.
"""
from pathlib import Path

import pytest

from src.banco import conexao
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository
from src.services import referencias_auditoria_sped_service as refs
from src.sped.auditor_tributario import AuditorTributarioSPED
from src.sped.corretor_tributario_assistido import CorretorTributarioAssistido


NOME_TESTE = "EMPRESA LABORATORIO LTDA"
NCM_TESTE = "87141000"
CHAVE_TESTE = "3" * 44


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    """Desvia TODAS as conexoes da Ficha/Auditoria para um DB temporario."""
    caminho_real = Path(conexao.DB)
    caminho_teste = tmp_path / "fiscalpro_teste_isolado.db"
    assert caminho_teste != caminho_real
    monkeypatch.setattr(conexao, "DB", caminho_teste)

    # O que se testa e a leitura da regra operacional, nao a disponibilidade
    # dos catalogos oficiais no runner. Nao consultar nem escrever bases reais.
    monkeypatch.setattr(
        refs.ReferenciasAuditoriaSPEDService,
        "consultar_item",
        lambda self, ncm, descricao, contexto, ex_tipi="": {
            "ncm_status": "CONSULTA SINTETICA",
            "falha_tecnica": False,
            "restricao_uso": "NAO USAR COMO FUNDAMENTO FISCAL",
        },
    )
    FichaTributariaRepository.preparar_banco()
    # A base por produto e criada normalmente pelo bootstrap geral do app;
    # criar seu esquema minimo SOMENTE no DB de teste temporario.
    conn = conexao.Banco.conectar()
    conn.execute("""
        CREATE TABLE tributacao_base (
            id INTEGER PRIMARY KEY, empresa TEXT, codigo_produto TEXT,
            descricao_produto TEXT, ncm TEXT, cest TEXT, cfop TEXT,
            cst_icms TEXT, icms REAL, icms_st TEXT, fcp REAL,
            cst_pis TEXT, aliquota_pis REAL,
            cst_cofins TEXT, aliquota_cofins REAL,
            cst_ipi TEXT, ipi REAL, ibs REAL, cbs REAL,
            classificacao TEXT, beneficio TEXT, fonte TEXT,
            confiabilidade INTEGER, ultima_validacao TEXT,
            observacoes TEXT, atualizado_em TEXT, ativo INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()
    assert caminho_teste.is_file()
    assert conexao.DB == caminho_teste
    yield caminho_teste, tmp_path
    assert conexao.DB == caminho_teste
    # Testes nunca escrevem o caminho do banco de producao.
    assert caminho_teste != caminho_real


def sped_ficticio(cfop="2102"):
    itens = [
        "", "C170", "1", "PROD1", "PECA FICTICIA", "1", "UN",
        "100", "0", "0", "00", cfop,
    ] + ["0"] * 27
    return [
        f"|0000|019|0|01102026|31102026|{NOME_TESTE}|12345678000199||MG|",
        "|0150|FORN|FORNECEDOR||||123456|3550308|",
        f"|0200|PROD1|PECA FICTICIA|||UN|00|{NCM_TESTE}|||||",
        f"|C100|0|1|FORN|55|00|1|101|{CHAVE_TESTE}|15102026|15102026|100|",
        "|".join(itens) + "|",
    ]


def regra_ficticia(**alteracoes):
    regra = {
        "ncm": NCM_TESTE,
        "empresa": NOME_TESTE,
        "uf_origem": "SP",
        "uf_destino": "MG",
        "regime": "LUCRO REAL",
        "operacao": "ENTRADA",
        "finalidade": "REVENDA",
        "contribuinte": "CONTRIBUINTE",
        "vigencia_inicio": "01/09/2026",
        "vigencia_fim": "31/10/2026",
        "status": "VIGENTE",
        "cfop": "2102",
        "cst_icms": "00",
        "fonte": "TESTE AUTOMATIZADO SINTETICO - SEM VALIDADE TRIBUTARIA",
        "confiabilidade": 90,
    }
    regra.update(alteracoes)
    return regra


def executar(linhas):
    return AuditorTributarioSPED().auditar(
        linhas,
        "EFD ICMS/IPI (Fiscal)",
        NOME_TESTE,
        {
            "empresa": NOME_TESTE,
            "regime": "LUCRO REAL",
            "finalidade": "REVENDA",
            "contribuinte": "CONTRIBUINTE",
        },
    )


def test_c170_regra_ficticia_aparece_so_apos_cadastro(ambiente):
    caminho_banco, pasta = ambiente
    linhas = sped_ficticio()
    arquivo_original = pasta / "sped_original_ficticio.txt"
    arquivo_original.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    antes = arquivo_original.read_bytes()

    vazio = executar(linhas)
    assert vazio.total_itens == 1
    assert vazio.itens_com_regra == 0
    assert vazio.itens_sem_regra == 1
    assert vazio.cobertura_regras == 0

    registro_id = FichaTributariaRepository.salvar_tributacao_atual(
        regra_ficticia(),
        encerrar_anterior=False,
    )
    assert registro_id > 0
    assert caminho_banco.exists()

    auditado = executar(linhas)
    assert auditado.total_itens == 1
    assert auditado.itens_com_regra == 1
    assert auditado.itens_sem_regra == 0
    assert auditado.cobertura_regras == 100.0
    assert not auditado.auditoria_tributaria_inconclusiva
    assert not any(
        a.campo == "Regra tributária" and a.atual == "Não encontrada"
        for a in auditado.apontamentos
    )
    assert arquivo_original.read_bytes() == antes
    assert linhas == sped_ficticio()


@pytest.mark.parametrize(
    "alteracoes",
    [
        {"regime": "LUCRO PRESUMIDO"},
        {"operacao": "SAÍDA"},
        {"uf_origem": "RJ"},
        {"uf_destino": "SP"},
        {"empresa": "OUTRA EMPRESA LABORATORIO LTDA"},
        {"vigencia_inicio": "01/11/2026"},
        {"vigencia_fim": "30/09/2026", "vigencia_inicio": "01/09/2026"},
        {"status": "RASCUNHO"},
    ],
    ids=[
        "regime_incompativel", "operacao_incompativel", "origem_incompativel",
        "destino_incompativel", "empresa_incompativel", "vigencia_futura",
        "vigencia_encerrada", "rascunho_nao_aplicavel",
    ],
)
def test_regra_incompativel_nao_gera_conformidade(ambiente, alteracoes):
    FichaTributariaRepository.salvar_tributacao_atual(
        regra_ficticia(**alteracoes), encerrar_anterior=False,
    )
    resultado = executar(sped_ficticio())
    assert resultado.itens_com_regra == 0
    assert resultado.itens_sem_regra == 1
    assert resultado.auditoria_tributaria_inconclusiva
    assert resultado.cobertura_regras == 0


def test_divergencia_sintetica_so_gera_proposta_desmarcada(ambiente):
    FichaTributariaRepository.salvar_tributacao_atual(
        regra_ficticia(), encerrar_anterior=False,
    )
    linhas = sped_ficticio(cfop="2101")
    copia = list(linhas)
    auditoria = executar(linhas)
    assert auditoria.itens_com_regra == 1
    assert any(
        a.origem == "FICHA TRIBUTÁRIA" and a.campo == "CFOP"
        and a.nivel == "ERRO"
        for a in auditoria.apontamentos
    )
    preparadas = CorretorTributarioAssistido().preparar(linhas, auditoria)
    assert preparadas.propostas
    assert preparadas.selecionadas == []
    assert all(not proposta.selecionada for proposta in preparadas.propostas)
    assert linhas == copia
    # Nenhuma chamada a aplicar() e feita no teste.
