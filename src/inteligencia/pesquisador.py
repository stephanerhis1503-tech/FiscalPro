from src.inteligencia.fontes.catalogo_fontes import CatalogoFontes


class Pesquisador:

    def buscar(self, consulta):

        print("=" * 60)
        print("PESQUISADOR FISCALPRO AI")
        print("=" * 60)

        print(f"NCM: {consulta.ncm}")
        print()

        for fonte in CatalogoFontes.listar():

            print(f"🔎 {fonte.__class__.__name__}")

            resultado = fonte.pesquisar(consulta)

            if resultado:

                print("✅ Informação localizada.")

                return resultado

        print()

        print("⚠ Nenhuma fonte retornou resultado.")

        return None