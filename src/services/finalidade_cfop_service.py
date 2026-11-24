"""Classificação conservadora da finalidade declarada no CFOP do C170.

A natureza fiscal inferida do CFOP é uma indicação documental, NÃO uma
homologação tributária, tampouco prova de crédito ou de ICMS-ST.
CFOP não reconhecido permanece sem finalidade e exige revisão.
"""

from __future__ import annotations

from dataclasses import dataclass


CFOP_USO_CONSUMO = frozenset({"1407", "2407", "1556", "2556", "1653", "2653"})
CFOP_REVENDA = frozenset({"1102", "2102", "1403", "2403"})
CFOP_OUTROS = frozenset({"1910", "2910", "1949", "2949"})


@dataclass(frozen=True)
class ClassificacaoFinalidadeCFOP:
    cfop: str
    finalidade: str
    status: str
    motivo: str

    @property
    def inconclusiva(self) -> bool:
        return self.status != "INDICIO_CFOP"


def classificar_finalidade_entrada(cfop: str) -> ClassificacaoFinalidadeCFOP:
    codigo = "".join(caractere for caractere in str(cfop or "") if caractere.isdigit())
    if len(codigo) != 4 or codigo[0] not in "12":
        return ClassificacaoFinalidadeCFOP(
            codigo, "", "REVISAR",
            "CFOP ausente, inválido ou incompatível com entrada; não assumir revenda.",
        )
    if codigo in CFOP_USO_CONSUMO:
        return ClassificacaoFinalidadeCFOP(
            codigo, "USO E CONSUMO", "INDICIO_CFOP",
            "O CFOP indica aquisição para uso/consumo; não presumir direito a crédito.",
        )
    if codigo in CFOP_REVENDA:
        return ClassificacaoFinalidadeCFOP(
            codigo, "REVENDA", "INDICIO_CFOP",
            "O CFOP indica aquisição para comercialização; enquadramento ainda exige conferência.",
        )
    if codigo in CFOP_OUTROS:
        return ClassificacaoFinalidadeCFOP(
            codigo, "", "REVISAR",
            "CFOP de outras entradas ou operação específica; requer classificação manual.",
        )
    return ClassificacaoFinalidadeCFOP(
        codigo, "", "REVISAR",
        "CFOP de entrada sem mapeamento seguro; não reutilizar a finalidade padrão.",
    )
