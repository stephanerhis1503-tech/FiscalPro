import sqlite3

from src.core.caminhos import BANCO_FISCAL

DB = BANCO_FISCAL


class Banco:

    @staticmethod
    def conectar():
        DB.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        return conn
