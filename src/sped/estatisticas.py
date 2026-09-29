from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .indice import IndiceSPED


def _eh_data_sped(valor: str) -> bool:
    valor = (valor or "").strip()
    if len(valor) != 8 or not valor.isdigit():
        return False
    try:
        datetime.strptime(valor, "%d%m%Y")
        return True
    except ValueError:
        return False


def _formatar_data_sped(valor: str) -> str:
    valor = (valor or "").strip()
    if _eh_data_sped(valor):
        return datetime.strptime(valor, "%d%m%Y").strftime("%d/%m/%Y")
    return valor or "-"


@dataclass(slots=True)
class EstatisticasSPED:
    empresa: str = "-"
    cnpj: str = "-"
    periodo: str = "-"
    layout: str = "-"
    finalidade: str = "-"
    tipo_sped: str = "-"
    total_linhas: int = 0
    total_registros_validos: int = 0
    contagens: dict[str, int] = field(default_factory=dict)

    @property
    def produtos(self) -> int:
        return self.contagens.get("0200", 0)

    @property
    def participantes(self) -> int:
        return self.contagens.get("0150", 0)

    @property
    def documentos(self) -> int:
        return self.contagens.get("C100", 0)

    @property
    def itens(self) -> int:
        return self.contagens.get("C170", 0)

    @property
    def ctes(self) -> int:
        return self.contagens.get("D100", 0)


class CalculadorEstatisticasSPED:
    """Extrai identificação e contagens respeitando o leiaute de cada EFD."""

    REGISTROS_FORTES_FISCAL = {
        "E100", "E110", "E111", "E112", "E113", "E115", "E116",
        "H001", "H005", "H010", "K001", "K200",
    }
    REGISTROS_FORTES_CONTRIBUICOES = {
        "0110", "0111", "A001", "A010", "F001", "M001", "M100",
        "M200", "M400", "M500", "M600", "P001",
    }

    def calcular(self, linhas: list[str], indice: IndiceSPED) -> EstatisticasSPED:
        contagens = indice.contagens()
        estatisticas = EstatisticasSPED(
            total_linhas=len(linhas),
            total_registros_validos=sum(contagens.values()),
            contagens=contagens,
        )

        refs_0000 = indice.referencias("0000")
        if not refs_0000:
            return estatisticas

        campos = linhas[refs_0000[0].indice_lista].rstrip("\r\n").split("|")
        estatisticas.layout = self._campo(campos, 2)
        tipo = self._identificar_tipo(campos, contagens)
        estatisticas.tipo_sped = tipo

        if tipo == "EFD Contribuições":
            # |0000|COD_VER|TIPO_ESCRIT|IND_SIT_ESP|NUM_REC_ANTERIOR|
            # DT_INI|DT_FIN|NOME|CNPJ|UF|COD_MUN|SUFRAMA|IND_NAT_PJ|IND_ATIV|
            estatisticas.finalidade = self._campo(campos, 3)
            inicio = _formatar_data_sped(self._campo(campos, 6, ""))
            fim = _formatar_data_sped(self._campo(campos, 7, ""))
            estatisticas.empresa = self._campo(campos, 8)
            estatisticas.cnpj = self._campo(campos, 9)
        else:
            # EFD ICMS/IPI (Fiscal):
            # |0000|COD_VER|COD_FIN|DT_INI|DT_FIN|NOME|CNPJ|CPF|UF|IE|COD_MUN|...
            estatisticas.finalidade = self._campo(campos, 3)
            inicio = _formatar_data_sped(self._campo(campos, 4, ""))
            fim = _formatar_data_sped(self._campo(campos, 5, ""))
            estatisticas.empresa = self._campo(campos, 6)
            estatisticas.cnpj = self._campo(campos, 7)

        if inicio == "-" and fim == "-":
            estatisticas.periodo = "-"
        elif inicio == fim:
            estatisticas.periodo = inicio
        else:
            estatisticas.periodo = f"{inicio} até {fim}"

        return estatisticas

    def _identificar_tipo(self, campos: list[str], contagens: dict[str, int]) -> str:
        # A posição das datas no 0000 é a forma mais segura de distinguir
        # os dois arquivos suportados nesta fase.
        if _eh_data_sped(self._campo(campos, 4, "")) and _eh_data_sped(self._campo(campos, 5, "")):
            return "EFD ICMS/IPI (Fiscal)"
        if _eh_data_sped(self._campo(campos, 6, "")) and _eh_data_sped(self._campo(campos, 7, "")):
            return "EFD Contribuições"

        # Fallback para arquivos incompletos ou cabeçalhos fora do padrão.
        pontos_fiscal = sum(contagens.get(codigo, 0) for codigo in self.REGISTROS_FORTES_FISCAL)
        pontos_contrib = sum(contagens.get(codigo, 0) for codigo in self.REGISTROS_FORTES_CONTRIBUICOES)
        if pontos_contrib > pontos_fiscal:
            return "EFD Contribuições"
        if pontos_fiscal > 0:
            return "EFD ICMS/IPI (Fiscal)"
        return "SPED não identificado"

    @staticmethod
    def _campo(campos: list[str], indice: int, padrao: str = "-") -> str:
        if indice < len(campos):
            valor = campos[indice].strip()
            return valor or padrao
        return padrao
