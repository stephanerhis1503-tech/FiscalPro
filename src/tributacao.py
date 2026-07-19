import sqlite3
import os


CAMINHO_DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "dados",
    "tributacao.db"
)


class BancoTributario:

    def __init__(self):
        self.conn = sqlite3.connect(CAMINHO_DB)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    # ============================
    # CONSULTAS
    # ============================

    def listar_ncm(self):

        self.cursor.execute("""
            SELECT codigo, descricao
            FROM ncm
            ORDER BY codigo
        """)

        return self.cursor.fetchall()

    def consultar_ncm(self, codigo):

        self.cursor.execute("""
            SELECT *
            FROM ncm
            WHERE codigo = ?
        """, (codigo,))

        resultado = self.cursor.fetchone()

        if resultado:
            return dict(resultado)

        return None

    def pesquisar_descricao(self, texto):

        self.cursor.execute("""
            SELECT codigo, descricao
            FROM ncm
            WHERE descricao LIKE ?
            ORDER BY descricao
        """, (f"%{texto}%",))

        return self.cursor.fetchall()

    def existe_ncm(self, codigo):

        self.cursor.execute("""
            SELECT id
            FROM ncm
            WHERE codigo = ?
        """, (codigo,))

        return self.cursor.fetchone() is not None

    def fechar(self):
        self.conn.close()