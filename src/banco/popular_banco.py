from src.repositorios.ncm_repository import NCMRepository

print("Populando banco...")

# ==========================
# NCM
# ==========================

NCMRepository.inserir(
    "84821010",
    "ROLAMENTO DE ESFERAS",
    "01.001.00"
)

# ==========================
# TRIBUTAÇÃO ATUAL
# ==========================

NCMRepository.inserir_tributacao_atual(
    "84821010",
    "MG",
    "Lucro Real",
    "Venda",
    "01",
    "01",
    1.65,
    7.60,
    18,
    "SIM",
    2,
    0
)

# ==========================
# REFORMA TRIBUTÁRIA
# ==========================

NCMRepository.inserir_reforma(
    "84821010",
    "1001",
    "000",
    "00",
    "00",
    17.5,
    8.8,
    "NÃO"
)

# Outros NCMs de exemplo
NCMRepository.inserir(
    "85122011",
    "FAROL PARA MOTOCICLETA",
    ""
)

NCMRepository.inserir(
    "40169300",
    "GUARNIÇÃO TAMPA CABEÇOTE",
    ""
)

print("Concluído.")