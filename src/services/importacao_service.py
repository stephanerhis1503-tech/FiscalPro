from pathlib import Path

from src.importadores.importador_ncm import ImportadorNCM


class ImportacaoService:

    def __init__(self):

        self.resultado = {
            "ncm": None,
            "digisat": None,
            "historico": None
        }

    # ==========================================================
    # IMPORTAÇÃO DA TABELA NCM
    # ==========================================================

    def importar_ncm(self, arquivo):

        print()

        print("=" * 70)
        print("IMPORTANDO TABELA OFICIAL NCM")
        print("=" * 70)

        importador = ImportadorNCM()

        importador.importar(Path(arquivo))

        self.resultado["ncm"] = {

            "inseridos": importador.inseridos,
            "atualizados": importador.atualizados,
            "sem_alteracao": importador.sem_alteracao,
            "erros": importador.erros

        }

        return self.resultado["ncm"]

    # ==========================================================
    # IMPORTAÇÃO COMPLETA
    # ==========================================================

    def atualizar_base(self, arquivo_ncm):

        self.importar_ncm(arquivo_ncm)

        # Futuramente:
        #
        # self.importar_digisat(...)
        # self.importar_legislacao(...)
        # self.atualizar_regras(...)
        # self.recalcular_indices(...)

        self.exibir_resumo()

    # ==========================================================
    # RESUMO
    # ==========================================================

    def exibir_resumo(self):

        print()

        print("=" * 70)
        print("RESUMO DA IMPORTAÇÃO")
        print("=" * 70)

        if self.resultado["ncm"]:

            dados = self.resultado["ncm"]

            print()

            print("Tabela Oficial NCM")

            print(f"  Inseridos......: {dados['inseridos']}")
            print(f"  Atualizados....: {dados['atualizados']}")
            print(f"  Sem alteração..: {dados['sem_alteracao']}")
            print(f"  Erros..........: {dados['erros']}")

        print()

        print("=" * 70)