from src.inteligencia.ficha_tributaria import FichaTributaria
from src.inteligencia.resultado_pesquisa import ResultadoPesquisa


class DecisorTributario:

    def decidir(self, resultados: list[ResultadoPesquisa]) -> FichaTributaria | None:

        if not resultados:
            return None

        # Nesta primeira versão utiliza o primeiro resultado válido.
        for resultado in resultados:

            if resultado.sucesso:
                return self._montar_ficha(resultado)

        return None

    def _montar_ficha(self, resultado: ResultadoPesquisa):

        ficha = FichaTributaria(
            ncm=resultado.dados.get("ncm", ""),
            descricao=resultado.dados.get("descricao", ""),
            cest=resultado.dados.get("cest", ""),
            status="PESQUISA"
        )

        ficha.fontes.append(resultado.fonte)

        return ficha