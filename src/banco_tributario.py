import sqlite3
import os

CAMINHO_DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "dados",
    "tributacao.db"
)


def criar_banco():

    os.makedirs(os.path.dirname(CAMINHO_DB), exist_ok=True)

    conn = sqlite3.connect(CAMINHO_DB)
    cursor = conn.cursor()

    # ==========================
    # TABELA NCM
    # ==========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ncm (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            codigo TEXT UNIQUE NOT NULL,
            descricao TEXT NOT NULL,

            cest TEXT,

            cst_icms TEXT,
            aliquota_icms REAL,

            possui_st INTEGER DEFAULT 0,
            mva REAL,
            fcp REAL,

            cst_pis TEXT,
            aliquota_pis REAL,

            cst_cofins TEXT,
            aliquota_cofins REAL,

            credito_piscofins INTEGER DEFAULT 0,

            aliquota_ipi REAL,

            cfop_entrada TEXT,
            cfop_saida TEXT,

            base_legal_icms TEXT,
            base_legal_pis TEXT,
            base_legal_cofins TEXT,

            observacoes TEXT,

            ultima_atualizacao TEXT
        )
    """)

    # ==========================
    # BASE LEGAL
    # ==========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS base_legal (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tipo TEXT,
            numero TEXT,
            artigo TEXT,
            descricao TEXT,
            vigencia TEXT
        )
    """)

    # ==========================
    # EMPRESAS
    # ==========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresa (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            nome TEXT,
            uf TEXT,
            regime TEXT,
            atividade TEXT,
            crt TEXT,

            usa_credito_pis INTEGER DEFAULT 1,
            usa_credito_cofins INTEGER DEFAULT 1,

            beneficio_fiscal TEXT
        )
    """)

    # ==========================
    # REGRAS TRIBUTÁRIAS
    # ==========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regra_tributaria (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            ncm_codigo TEXT NOT NULL,

            uf TEXT NOT NULL,

            regime TEXT NOT NULL,

            atividade TEXT NOT NULL,

            operacao TEXT NOT NULL,

            cst_icms TEXT,
            aliquota_icms REAL,

            possui_st INTEGER DEFAULT 0,
            mva REAL,
            fcp REAL,

            cst_pis TEXT,
            aliquota_pis REAL,

            cst_cofins TEXT,
            aliquota_cofins REAL,

            credito_piscofins INTEGER DEFAULT 0,

            cfop_entrada TEXT,
            cfop_saida TEXT,

            base_legal TEXT,

            observacoes TEXT,

            FOREIGN KEY (ncm_codigo)
                REFERENCES ncm(codigo)

        )
    """)

    conn.commit()
    conn.close()

    print("Banco Tributário criado com sucesso!")


if __name__ == "__main__":
    criar_banco()