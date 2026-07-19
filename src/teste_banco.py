import sqlite3
import os

CAMINHO = os.path.join(
    os.path.dirname(__file__),
    "..",
    "dados",
    "tributacao.db"
)

conn = sqlite3.connect(CAMINHO)

cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")

print("\nTABELAS ENCONTRADAS:\n")

for tabela in cursor.fetchall():
    print(tabela[0])

conn.close()