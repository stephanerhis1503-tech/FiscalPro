import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DB = BASE_DIR / "fiscalpro.db"


class Banco:

    @staticmethod
    def conectar():
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        return conn