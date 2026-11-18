"""PDF RTC: resumo fiel ao motor do Excel, pendencias e anexo opcional."""
from copy import deepcopy
from pathlib import Path

import pytest
from pypdf import PdfReader

from src.services.rtc_relatorio_lote_2027_pdf_service import (
    ServicoRelatorioLoteRTC2027PDF,
)
from tests.test_rtc_destinacao_efd import CHAVE_A, CHAVE_B, criar_efd

CNPJ = "11809691000195"
COMPETENCIA = "2026-10"


def item(n, cfop, direcao="SAIDA", *, alerta=False, chave=None, numero="1"):
    return {
        "numero_nf": str(n),
        "numero_item": numero,
        "chave_nfe": chave or f"{n:044d}",
        "descricao": "Produto & servico <teste> do estoque",
        "direcao": direcao, "cfop": cfop, "cst_ibscbs": "000",
        "cclass_trib": "000001", "base_ibs_cbs": "1000.00",
        "status_auditoria": "REVISAR" if alerta else "OK",
        "motivos": "Sem grupo IBS/CBS" if alerta else "",
        "emissao": "2026-10-01", "ncm": "87141000",
    }


class LocalFalso:
    def __init__(self, itens):
        self.itens = itens
    def listar_itens(self, _cnpj, _comp, *, limite=None):
        assert limite is None
        return deepcopy(self.itens)
    def contar_itens(self, _cnpj, _comp):
        return len(self.itens)


@pytest.fixture
def servico():
    return ServicoRelatorioLoteRTC2027PDF(
        LocalFalso([
            item(101, "5102"),
            item(102, "5405"),
            item(103, "1102", "ENTRADA", alerta=True,
                 chave=CHAVE_A, numero="1"),
            item(104, "5152"),
            item(105, "5405", alerta=True),
            item(106, "1102", "ENTRADA", chave=CHAVE_B, numero="1"),
        ])
    )


def extrair(pdf: Path):
    leitor = PdfReader(str(pdf))
    return leitor, "\n".join(p.extract_text() or "" for p in leitor.pages)


def test_pdf_resumido_gera_sem_credito_ou_cbs_tcu(servico, tmp_path):
    arq = servico.gerar(
        CNPJ, COMPETENCIA, tmp_path / "relatorio.pdf",
        regime="Lucro Real", empresa="Mega Motos Trilha",
        permitir_venda_icms_st=True,
    )
    assert arq.exists() and arq.stat().st_size > 1500
    leitor, texto = extrair(arq)
    assert leitor.metadata.title == (
        "FiscalPro - Auditoria IBS/CBS em lote - Simulacao 2027"
    )
    assert "Mega Motos Trilha" in texto
    assert "RELATORIO DEMONSTRATIVO" in texto
    assert "SEM EFEITO FISCAL" in texto
    assert "CBS 2027" in texto
    assert "NAO SIMULADA" in texto
    assert "1. Alertas originais dos XMLs" in texto
    assert "2. Outras operacoes a revisar" in texto
    assert "Sem grupo IBS/CBS" in texto
    assert "Produto & servico <teste>" in texto
    assert "As demais 3 linhas" in " ".join(texto.split())
    assert "3. Demais itens - anexo completo" not in texto
    assert "R$ 1,00" in texto  # 2 itens x 0,50 no IBS UF
    assert len(leitor.pages) >= 2


def test_pdf_cenario_tcu_apenas_com_optin_e_cruzamento_efd(servico, tmp_path):
    efd = criar_efd(tmp_path)
    arq = servico.gerar(
        CNPJ, COMPETENCIA, tmp_path / "cruzamento.pdf",
        regime="Lucro Real", arquivo_sped_fiscal=efd,
        permitir_venda_icms_st=True, usar_cenario_tcu=True,
    )
    _, texto = extrair(arq)
    assert "SIM - NAO OFICIAL" in texto
    assert "CBS TCU 11,2%" in texto
    assert "sped_fiscal.txt" in texto
    assert "Uso e consumo (CFOP EFD)" in texto
    assert "1556" in texto
    assert "CHAVE + ITEM" not in texto  # pdf exibe a classificacao


def test_pdf_completo_inclui_outros_itens_sem_duplicar(servico, tmp_path):
    arq = servico.gerar(
        CNPJ, COMPETENCIA, tmp_path / "completo.pdf",
        regime="Lucro Real", incluir_todos_itens=True,
        permitir_venda_icms_st=True,
    )
    _, texto = extrair(arq)
    assert "3. Demais itens - anexo completo" in texto
    assert "2. Outras operacoes a revisar" in texto
    assert "1. Alertas originais dos XMLs" in texto
    assert "101" in texto and "102" in texto
    assert "105" in texto
    assert "As demais 3 linhas" not in texto


def test_pdf_somente_vendas_sem_alerta_nao_quebra(tmp_path):
    servico = ServicoRelatorioLoteRTC2027PDF(
        LocalFalso([item(111, "5102"), item(112, "6102")])
    )
    arquivo = servico.gerar(
        CNPJ, COMPETENCIA, tmp_path / "vazio_revisoes.pdf",
        regime="Lucro Presumido",
    )
    _, texto = extrair(arquivo)
    assert texto.count("Nenhum item nesta categoria") == 2
    assert "2" in texto
    assert "NAO SIMULADA" in texto


def test_pdf_extensao_errada_e_opcao_nao_booleana(servico, tmp_path):
    with pytest.raises(ValueError, match="extensao"):
        servico.gerar(CNPJ, COMPETENCIA, tmp_path / "nao.pdf.xlsx", regime="Lucro Real")
    with pytest.raises(ValueError, match="PDF completo"):
        servico.gerar(
            CNPJ, COMPETENCIA, tmp_path / "a.pdf",
            regime="Lucro Real", incluir_todos_itens="sim",
        )


def test_pdf_falha_nao_sobrescreve_documento_preexistente(servico, tmp_path, monkeypatch):
    from reportlab.platypus import SimpleDocTemplate
    destino = tmp_path / "antigo.pdf"
    destino.write_bytes(b"ORIGINAL")
    def quebrar(self, *a, **kw):
        raise OSError("Falha simulada ao construir PDF")
    monkeypatch.setattr(SimpleDocTemplate, "build", quebrar)
    with pytest.raises(OSError, match="Falha simulada"):
        servico.gerar(CNPJ, COMPETENCIA, destino, regime="Lucro Real")
    assert destino.read_bytes() == b"ORIGINAL"
    assert not (tmp_path / "antigo.gerando.pdf").exists()
