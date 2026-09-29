import sqlite3

from src.core.caminhos import BANCO_FISCAL

DB = BANCO_FISCAL


def criar_banco():

    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)

    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ncm (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        ncm TEXT NOT NULL UNIQUE,

        descricao TEXT,

        cest TEXT,

        ex_tipi TEXT,

        status TEXT DEFAULT 'ATIVO',

        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tributacao_atual (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        ncm TEXT,

        uf TEXT,

        regime TEXT,

        operacao TEXT,

        pis_cst TEXT,

        cofins_cst TEXT,

        aliquota_pis REAL,

        aliquota_cofins REAL,

        icms REAL,

        icms_st TEXT,

        fcp REAL,

        ipi REAL,

        beneficio TEXT,

        vigencia_inicio DATE,

        vigencia_fim DATE

    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tributacao_reforma (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        ncm TEXT,

        cclasstrib TEXT,

        ccredpres TEXT,

        cst_ibs TEXT,

        cst_cbs TEXT,

        aliquota_ibs REAL,

        aliquota_cbs REAL,

        imposto_seletivo TEXT,

        vigencia_inicio DATE,

        vigencia_fim DATE

    )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    criar_banco()
