from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FichaTributaria:

    # Identificação
    ncm: str
    descricao: str = ""
    cest: str = ""

    # Tributação Atual
    uf: str = ""
    regime: str = ""
    operacao: str = ""

    pis_cst: str = ""
    cofins_cst: str = ""

    aliquota_pis: float = 0.0
    aliquota_cofins: float = 0.0

    icms: float = 0.0
    icms_st: str = ""
    fcp: float = 0.0
    ipi: float = 0.0

    # Reforma Tributária
    cclasstrib: str = ""
    ccredpres: str = ""
    cst_ibs: str = ""
    cst_cbs: str = ""

    aliquota_ibs: float = 0.0
    aliquota_cbs: float = 0.0

    imposto_seletivo: str = ""

    # Inteligência
    fontes: List[str] = field(default_factory=list)

    base_legal: List[str] = field(default_factory=list)

    confiabilidade: float = 0.0

    status: str = "LOCAL"

    observacoes: Optional[str] = None