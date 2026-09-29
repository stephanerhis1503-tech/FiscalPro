import sqlite3
from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository


BASE = Path(__file__).resolve().parents[1]


def test_versao_17832_ou_superior():
    assert tuple(int(x) for x in VERSAO_APP.split('.')) >= (17, 8, 32)


def test_saneia_duplicidade_normalizada_e_preserva_cenario_distinto(monkeypatch, tmp_path):
    import src.banco.conexao as conexao

    db = tmp_path / 'fiscalpro_17832.db'
    conn = sqlite3.connect(db)
    conn.execute('CREATE TABLE ncm (ncm TEXT PRIMARY KEY, descricao TEXT)')
    conn.execute("INSERT INTO ncm(ncm, descricao) VALUES ('87141000', 'De motocicletas')")
    conn.execute(
        '''
        CREATE TABLE ficha_consultas_recentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ncm TEXT NOT NULL,
            descricao TEXT DEFAULT '',
            empresa TEXT NOT NULL DEFAULT '',
            regime TEXT DEFAULT '',
            operacao TEXT DEFAULT '',
            uf_origem TEXT DEFAULT '',
            uf_destino TEXT DEFAULT '',
            consultado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    # Mesmo cenário com diferenças apenas de caixa/espaços: deve virar um só.
    conn.execute(
        "INSERT INTO ficha_consultas_recentes(ncm, descricao, empresa, regime, operacao, uf_origem, uf_destino, consultado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ('87141000', 'Antiga', 'Mega Motos Comércio', 'Lucro Presumido', 'Saída', 'mg', 'MG', '2026-08-20 10:00:00'),
    )
    conn.execute(
        "INSERT INTO ficha_consultas_recentes(ncm, descricao, empresa, regime, operacao, uf_origem, uf_destino, consultado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ('87141000', 'Mais recente', '  mega motos comércio  ', 'LUCRO PRESUMIDO', 'SAÍDA', 'MG', 'mg', '2026-08-20 11:00:00'),
    )
    # Mesmo NCM, mas cenário realmente diferente: deve permanecer.
    conn.execute(
        "INSERT INTO ficha_consultas_recentes(ncm, descricao, empresa, regime, operacao, uf_origem, uf_destino, consultado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ('87141000', 'PA para MG', 'Mega Motos Comércio', 'LUCRO PRESUMIDO', 'SAÍDA', 'PA', 'MG', '2026-08-20 12:00:00'),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(conexao, 'DB', db)
    FichaTributariaRepository.preparar_banco()

    recentes = FichaTributariaRepository.listar_consultas_recentes(limite=20)
    encontrados = [item for item in recentes if item['ncm'] == '87141000']
    assert len(encontrados) == 2
    assert {(item['uf_origem'].strip().upper(), item['uf_destino'].strip().upper()) for item in encontrados} == {('MG', 'MG'), ('PA', 'MG')}

    # Repetir MG→MG com variação de caixa/espaço atualiza o topo, sem duplicar.
    FichaTributariaRepository.registrar_consulta_recente(
        ncm='87141000',
        descricao='Atualizada 17.8.32',
        empresa='MEGA MOTOS COMÉRCIO',
        regime='lucro presumido',
        operacao=' saída ',
        uf_origem=' mg ',
        uf_destino='MG',
    )
    recentes = FichaTributariaRepository.listar_consultas_recentes(limite=20)
    encontrados = [item for item in recentes if item['ncm'] == '87141000']
    assert len(encontrados) == 2
    mg_mg = [item for item in encontrados if item['uf_origem'].strip().upper() == 'MG'][0]
    assert mg_mg['descricao'] == 'Atualizada 17.8.32'


def test_central_diferencia_cenarios_distintos_no_rotulo_recente():
    fonte = (BASE / 'src/ui/janela_principal.py').read_text(encoding='utf-8')
    assert 'uf_origem' in fonte
    assert 'uf_destino' in fonte
    assert '→' in fonte
    assert 'contexto = f"{empresa} • {uf_origem}→{uf_destino}"' in fonte
