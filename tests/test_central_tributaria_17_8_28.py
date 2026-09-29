from pathlib import Path

from src.core.app_info import VERSAO_APP


BASE = Path(__file__).resolve().parents[1] / "src" / "ui"


def test_versao_17828_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split(".")) >= (17, 8, 28)


def test_aba_tributacao_virou_central_inteligente():
    fonte = (BASE / "janela_principal.py").read_text(encoding="utf-8")
    assert "Central Tributária Inteligente" in fonte
    assert "Consulta rápida" in fonte
    assert '"CONSULTAR"' in fonte
    assert '"AUDITAR"' in fonte
    assert '"CALCULAR"' in fonte
    assert "Semáforo tributário" in fonte
    assert "EmpresasRegimesService" in fonte


def test_consulta_rapida_abre_ficha_com_contexto():
    fonte = (BASE / "janela_principal.py").read_text(encoding="utf-8")
    bloco = fonte.split("def abrir_ficha_tributaria_rapida", 1)[1].split("def abrir_calculo_icms_st_direto", 1)[0]
    assert '"empresa": empresa_contexto' in bloco
    assert '"regime": regime' in bloco
    assert '"operacao": self.trib_operacao_var.get().strip()' in bloco
    assert '"uf_origem": self.trib_uf_origem_var.get().strip()' in bloco
    assert '"uf_destino": self.trib_uf_destino_var.get().strip()' in bloco
    assert "JanelaFichaTributaria(self.janela, contexto=contexto, ncm=termo)" in bloco


def test_ficha_prioriza_cards_e_preserva_detalhes_tecnicos():
    fonte = (BASE / "janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert "Resumo da análise" in fonte
    assert "Detalhes técnicos" in fonte
    assert '"PIS / COFINS"' in fonte
    assert '"ICMS-ST"' in fonte
    assert '"ICMS / CFOP"' in fonte
    assert '"IPI"' in fonte
    assert '"SEGURANÇA"' in fonte
    assert "O que revisar antes de aplicar" in fonte
    # Estrutura antiga continua disponível para auditoria detalhada.
    assert "self.tree_resultado = ttk.Treeview" in fonte
    assert "self.texto_explicacao = tk.Text" in fonte


def test_cards_usam_resultado_dos_motores_existentes():
    fonte = (BASE / "janela_ficha_tributaria.py").read_text(encoding="utf-8")
    bloco = fonte.split("# Resumo visual da Central Tributária", 1)[1].split("linhas = [", 1)[0]
    assert "piscofins_exibicao" in bloco
    assert "st_confirmado" in bloco
    assert "icms_exibicao" in bloco
    assert "cfop_exibicao" in bloco
    assert "ipi_exibicao" in bloco
    assert "indicador_geral.resultado" in bloco
