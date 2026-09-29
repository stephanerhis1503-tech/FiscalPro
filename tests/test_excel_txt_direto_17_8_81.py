"""Regressões do fluxo Excel -> TXT direto da 17.8.81."""

from pathlib import Path
from types import SimpleNamespace

from src.core.app_info import VERSAO_APP
from src.ui.janela_sped_inteligente import JanelaSPEDInteligente


def _fonte() -> str:
    return Path("src/ui/janela_sped_inteligente.py").read_text(encoding="utf-8")


def test_versao_minima_17_8_81() -> None:
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 81)


def test_aba_excel_txt_tem_fluxo_visivel_e_geracao_direta() -> None:
    fonte = _fonte()
    assert 'text="Fluxo Excel → TXT"' in fonte
    assert 'text="📂 Selecionar Excel"' in fonte
    assert 'text="✅ Validar planilha"' in fonte
    assert 'text="📝 Gerar SPED TXT agora"' in fonte
    assert "command=self.gerar_sped_txt_direto" in fonte
    assert 'text="🔎 Conferir alterações"' in fonte


def test_destino_padrao_nao_substitui_existente(tmp_path: Path) -> None:
    excel = tmp_path / "SPED_TESTE_ORGANIZADO.xlsx"
    excel.write_bytes(b"teste")
    janela = object.__new__(JanelaSPEDInteligente)
    janela.caminho_excel = str(excel)

    primeiro = Path(janela._destino_txt_padrao())
    assert primeiro.name == "SPED_TESTE_CONVERTIDO.txt"
    primeiro.write_text("ja existe", encoding="utf-8")

    segundo = Path(janela._destino_txt_padrao())
    assert segundo.name == "SPED_TESTE_CONVERTIDO_2.txt"


def test_sincronizacao_libera_geracao_so_apos_validacao_ok() -> None:
    class Botao:
        def __init__(self):
            self.state = None
        def configure(self, **kwargs):
            if "state" in kwargs:
                self.state = kwargs["state"]

    class Rotulo:
        def config(self, **kwargs):
            pass

    janela = object.__new__(JanelaSPEDInteligente)
    janela.caminho_excel = "teste.xlsx"
    janela.validacao_excel = SimpleNamespace(valido=False)
    janela.btn_validar_excel_aba = Botao()
    janela.btn_gerar_txt_aba = Botao()
    janela.btn_conferir_excel_aba = Botao()
    janela.lbl_destino_txt = Rotulo()
    janela._destino_txt_padrao = lambda: "teste_CONVERTIDO.txt"

    janela._sincronizar_fluxo_excel_txt()
    assert janela.btn_validar_excel_aba.state == "normal"
    assert janela.btn_gerar_txt_aba.state == "disabled"
    assert janela.btn_conferir_excel_aba.state == "normal"

    janela.validacao_excel = SimpleNamespace(valido=True)
    janela._sincronizar_fluxo_excel_txt()
    assert janela.btn_gerar_txt_aba.state == "normal"
