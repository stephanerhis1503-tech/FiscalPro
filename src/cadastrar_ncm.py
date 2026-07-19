import sqlite3
import os
from datetime import datetime

CAMINHO_DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "dados",
    "tributacao.db"
)

conn = sqlite3.connect(CAMINHO_DB)
cursor = conn.cursor()

dados = (
    "87141000",                        # código
    "Partes e acessórios de motocicletas",
    "",                                # CEST
    "000",                             # CST ICMS
    18.0,                              # Alíquota ICMS
    0,                                 # Possui ST
    None,                              # MVA
    None,                              # FCP
    "50",                              # CST PIS
    1.65,                              # Alíquota PIS
    "50",                              # CST COFINS
    7.60,                              # Alíquota COFINS
    1,                                 # Gera crédito
    0.0,                               # IPI
    "2102",                            # CFOP Entrada
    "5102",                            # CFOP Saída
    "",                                # Base Legal ICMS
    "Lei 10.637/2002",                 # Base Legal PIS
    "Lei 10.833/2003",                 # Base Legal COFINS
    "Cadastro inicial FiscalPro",
    datetime.now().strftime("%d/%m/%Y")
)

cursor.execute("""
INSERT OR REPLACE INTO ncm (

codigo,
descricao,
cest,

cst_icms,
aliquota_icms,
possui_st,
mva,
fcp,

cst_pis,
aliquota_pis,

cst_cofins,
aliquota_cofins,

credito_piscofins,

aliquota_ipi,

cfop_entrada,
cfop_saida,

base_legal_icms,
base_legal_pis,
base_legal_cofins,

observacoes,

ultima_atualizacao

)

VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", dados)

conn.commit()
conn.close()

print("Cadastro realizado com sucesso!")