from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository


BASE = Path(__file__).resolve().parents[1]


def test_versao_17831_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split('.')) >= (17, 8, 31)


def test_central_exibe_acesso_rapido_recentes_e_favoritos():
    fonte = (BASE / 'src/ui/janela_principal.py').read_text(encoding='utf-8')
    assert 'Acesso rápido' in fonte
    assert 'ÚLTIMAS CONSULTAS' in fonte
    assert 'FAVORITOS' in fonte
    assert 'listar_consultas_recentes' in fonte
    assert 'listar_favoritos' in fonte


def test_ficha_simplificada_exibe_botao_favoritar():
    from src.ui.janela_ficha_tributaria import JanelaFichaTributaria
    assert hasattr(JanelaFichaTributaria, 'alternar_favorito')
    assert hasattr(JanelaFichaTributaria, '_atualizar_botao_favorito')
    fonte = (BASE / 'src/ui/janela_ficha_tributaria.py').read_text(encoding='utf-8')
    bloco = fonte.split('def _criar_interface(self) -> None:', 2)[-1]
    assert '☆ Favoritar NCM' in bloco
    assert 'command=self.alternar_favorito' in bloco


def test_registro_consulta_recente_preserva_contexto_e_nao_duplica():
    ncm = '40114000'
    FichaTributariaRepository.registrar_consulta_recente(
        ncm=ncm,
        descricao='Pneu moto teste 17.8.31',
        empresa='Mega Motos Comércio',
        regime='LUCRO PRESUMIDO',
        operacao='SAÍDA',
        uf_origem='MG',
        uf_destino='MG',
    )
    FichaTributariaRepository.registrar_consulta_recente(
        ncm=ncm,
        descricao='Pneu moto teste 17.8.31',
        empresa='Mega Motos Comércio',
        regime='LUCRO PRESUMIDO',
        operacao='SAÍDA',
        uf_origem='MG',
        uf_destino='MG',
    )
    recentes = FichaTributariaRepository.listar_consultas_recentes(limite=20)
    encontrados = [
        item for item in recentes
        if item['ncm'] == ncm
        and item['empresa'] == 'Mega Motos Comércio'
        and item['regime'] == 'LUCRO PRESUMIDO'
        and item['operacao'] == 'SAÍDA'
        and item['uf_origem'] == 'MG'
        and item['uf_destino'] == 'MG'
    ]
    assert len(encontrados) == 1
    assert encontrados[0]['descricao'] == 'Pneu moto teste 17.8.31'
