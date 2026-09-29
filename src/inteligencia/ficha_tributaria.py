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
    cfop: str = ""
    cst_icms: str = ""
    cst_ipi: str = ""

    pis_cst: str = ""
    cofins_cst: str = ""

    aliquota_pis: float = 0.0
    aliquota_cofins: float = 0.0

    icms: float = 0.0
    icms_st: str = ""
    fcp: float = 0.0
    ipi: float = 0.0


    # Motor Nacional de PIS/COFINS — Sprint 16.5
    piscofins_status: str = ""
    piscofins_enquadramento: str = ""
    piscofins_confirmado: bool = False
    piscofins_exige_revisao: bool = True
    piscofins_fundamento: str = ""
    piscofins_fonte: str = ""
    piscofins_tabela_efd: str = ""
    piscofins_observacoes: str = ""
    piscofins_confiabilidade: float = 0.0
    piscofins_sugestao_cst_pis: str = ""
    piscofins_sugestao_aliquota_pis: float = 0.0
    piscofins_sugestao_cst_cofins: str = ""
    piscofins_sugestao_aliquota_cofins: float = 0.0
    piscofins_divergencia: bool = False
    piscofins_aplicado_automaticamente: bool = False

    # Motor ICMS/MG — Sprint 16.6
    icms_mg_status: str = ""
    icms_mg_confirmado: bool = False
    icms_mg_exige_revisao: bool = True
    icms_mg_tipo_operacao: str = ""
    icms_mg_aliquota_nominal: float = 0.0
    icms_mg_aliquota_status: str = ""
    icms_mg_fundamento: str = ""
    icms_mg_fonte: str = ""
    icms_mg_observacoes: str = ""
    icms_mg_confiabilidade: float = 0.0
    icms_mg_beneficio_status: str = ""
    icms_mg_beneficio: str = ""
    icms_mg_reducao_base: float = 0.0
    icms_mg_st_status: str = ""
    icms_mg_st_confirmado: bool = False
    icms_mg_cest: str = ""
    icms_mg_mva: float = 0.0

    # Reforma Tributária
    cclasstrib: str = ""
    ccredpres: str = ""
    cst_ibs: str = ""
    cst_cbs: str = ""

    aliquota_ibs: float = 0.0
    aliquota_cbs: float = 0.0

    imposto_seletivo: str = ""
    reforma_status: str = ""
    reforma_observacoes: str = ""

    # Inteligência
    fontes: List[str] = field(default_factory=list)

    base_legal: List[str] = field(default_factory=list)

    confiabilidade: float = 0.0

    status: str = "LOCAL"

    observacoes: Optional[str] = None
    quantidade_produtos: int = 0
    quantidade_variacoes: int = 0