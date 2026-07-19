from src.repositorios.ncm_repository import NCMRepository


print("Populando banco...")

NCMRepository.inserir(
    "84821010",
    "ROLAMENTO DE ESFERAS",
    "01.001.00"
)

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