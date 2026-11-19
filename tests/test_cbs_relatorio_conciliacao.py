"""Regressao: conferencia CBS no Excel e PDF, sem acesso a API."""
from pathlib import Path

from openpyxl import load_workbook

from src.services.apuracao_assistida_local_service import ServicoApuracaoLocalRTC
from src.services.cbs_apuracao_oficial_service import ServicoCBSOficial
from src.services.cbs_relatorio_conciliacao_service import ServicoRelatorioConciliacaoCBS


CNPJ = "12345678000199"
CHAVE = "31261112345678000199550010000000011000000012"


def _preparar(tmp_path):
    servico = ServicoCBSOficial(tmp_path / "dados.db")
    local = ServicoApuracaoLocalRTC(servico.banco)
    with local._conectar() as con, con:
        for chave, direcao, nf, valor in [
            (CHAVE, "ENTRADA", "12", "17.19"),
            ("31261112345678000199550010000000021000000013",
             "SAIDA", "13", "10.00"),
        ]:
            con.execute(
                "INSERT INTO rtc_documentos_xml "
                "(cnpj_empresa,competencia,chave_nfe,numero_nf,emissao,"
                "cnpj_emitente,cnpj_destinatario,direcao,"
                "valor_cbs,status_conferencia,status_protocolo,status_credito,"
                "arquivo_origem,hash_xml) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (CNPJ, "2026-11", chave, nf, "2026-11-18",
                 CNPJ, CNPJ, direcao, valor, "OK", "OK",
                 "POTENCIAL", "teste.xml", chave),
            )
    retorno = {
        "ni": "12345678",
        "geradoEm": "2026-11-18T12:00:00Z",
        "apuracao": [{
            "pa": "11/2026",
            "creditos": [{
                "origem": 0, "documento": 55, "chave": CHAVE,
                "emissao": "2026-11-18T10:00:00Z",
                "registro": "2026-11-18T10:00:00Z",
                "atualizacao": "2026-11-18T12:00:00Z",
                "cbs": {"apurado": 17.19,
                        "apropriacao": {"apropriado": 0,
                                       "aApropriar": 17.19}},
            }],
        }],
    }
    servico.importar(retorno, "creditos", CNPJ)
    return ServicoRelatorioConciliacaoCBS(servico)


def test_excel_cbs_distingue_apropriado_de_a_apropriar(tmp_path):
    gerador = _preparar(tmp_path)
    arquivo = gerador.gerar(CNPJ, "2026-11", tmp_path / "cbs.xlsx", "Empresa Teste")
    wb = load_workbook(arquivo)
    assert wb.sheetnames == ["Resumo", "Debitos", "Creditos", "Pendencias"]
    assert wb["Creditos"]["G10"].value == 0
    assert wb["Creditos"]["H10"].value == 17.19
    assert wb["Creditos"]["I10"].value == "CONFERE"
    assert wb["Debitos"]["I10"].value == "SEM_DADO_NESTE_RETORNO"
    assert wb["Debitos"]["E10"].value is None
    assert wb["Pendencias"]["I10"].value == "SEM_DADO_NESTE_RETORNO"
    assert "incrementais" in wb["Resumo"]["A5"].value


def test_pdf_cbs_produz_documento(tmp_path):
    gerador = _preparar(tmp_path)
    arquivo = gerador.gerar(CNPJ, "2026-11", tmp_path / "cbs.pdf", "Empresa Teste")
    assert Path(arquivo).read_bytes().startswith(b"%PDF")
    assert arquivo.stat().st_size > 1000


def test_arquivo_sem_dados_nao_e_criado(tmp_path):
    gerador = ServicoRelatorioConciliacaoCBS(ServicoCBSOficial(tmp_path / "vazio.db"))
    try:
        gerador.gerar(CNPJ, "2026-11", tmp_path / "vazio.xlsx")
    except ValueError as exc:
        assert "Nao ha XMLs" in str(exc)
    else:
        raise AssertionError("Deveria bloquear exportacao vazia")
    assert not (tmp_path / "vazio.xlsx").exists()

def test_pdf_valores_no_padrao_brasileiro():
    from src.services.cbs_relatorio_conciliacao_service import _formatar_valor_pdf
    assert _formatar_valor_pdf(2908.01) == "2.908,01"
    assert _formatar_valor_pdf(0) == "0,00"
    assert _formatar_valor_pdf(None) == "-"



def test_triagem_valores_positivos_zeros_e_divergencias():
    from src.services.cbs_relatorio_conciliacao_service import _triagem_pendencia
    assert _triagem_pendencia({"status": "SEM_DADO_NESTE_RETORNO", "cbs_xml": "8.40"}) == "SEM_RETORNO_CBS_POSITIVA"
    assert _triagem_pendencia({"status": "SEM_DADO_NESTE_RETORNO", "cbs_xml": "0.00"}) == "SEM_RETORNO_CBS_ZERO"
    assert _triagem_pendencia({"status": "SEM_DADO_NESTE_RETORNO", "cbs_xml": ""}) == "SEM_RETORNO_VALOR_INDISPONIVEL"
    assert _triagem_pendencia({"status": "DIFERENCA_REVISAR", "cbs_xml": "2.00"}) == "REVISAR_DIVERGENCIA"
    assert _triagem_pendencia({"status": "MULTIPLOS_OFICIAIS_REVISAR", "cbs_xml": "2.00"}) == "REVISAR_MULTIPLOS"
    assert _triagem_pendencia({"status": "CONFERE", "cbs_xml": "0.00"}) == "CONFERE"


def test_triagem_excel_preserva_quatro_abas_e_pendencias(tmp_path):
    gerador = _preparar(tmp_path)
    caminho = gerador.gerar(CNPJ, "2026-11", tmp_path / "triagem.xlsx")
    wb = load_workbook(caminho)
    assert wb.sheetnames == ["Resumo", "Debitos", "Creditos", "Pendencias"]
    assert wb["Pendencias"]["I10"].value == "SEM_DADO_NESTE_RETORNO"
    assert wb["Pendencias"]["J10"].value == "SEM_RETORNO_CBS_POSITIVA"
    assert wb["Resumo"]["B19"].value == 1
    assert wb["Resumo"]["B20"].value == 0
    assert wb["Resumo"]["B23"].value == 0


def test_triagem_pdf_documenta_incompletude(tmp_path):
    gerador = _preparar(tmp_path)
    pdf = gerador.gerar(CNPJ, "2026-11", tmp_path / "triagem.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")
    assert pdf.stat().st_size > 1000
