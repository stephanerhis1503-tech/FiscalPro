"""Auditoria tributária de cadastro de produtos importado de planilha Excel.

Versão 18.2.1
--------------
- Audita também NCM válido porém semanticamente incompatível com a descrição.
- Usa consenso forte da mesma marca/família para detectar NCM isolado fora do padrão.
- Faixa/adesivo de tanque TWISTER passa a sugerir 39199020 como candidato de PVC,
  sempre em REVISAR para confirmação do material antes da alteração cadastral.

Versão 18.1.11
---------------
- Separa automaticamente linhas de serviço/mão de obra quando o NCM está zerado.
- Não sugere NCM de peça para descrições de troca, revisão, pintura, retífica etc.
- Reconhece gasolina automotiva genérica como NCM 27101259, mantendo CEST para revisão do tipo A/C/Premium.
- Serviços ganham status próprio e não entram no relatório de pendências de mercadorias.

Hotfix 17.8.8
--------------
- Lê cadastro de produtos sem alterar a planilha original.
- Reutiliza os motores nacionais/estaduais da Análise Tributária em Lote.
- Compara NCM, CEST, PIS/Cofins e TIPI e destaca divergências e pendências.
- Acrescenta alertas semânticos conservadores (ex.: retentor classificado fora
  do NCM de elementos de vedação), sempre como sugestão para conferência.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
import re
import unicodedata

from src.services.empresas_regimes_service import EmpresasRegimesService
from src.services.analise_tributaria_lote_service import (
    AnaliseTributariaLoteService,
    ItemBrutoLote,
    ResultadoItemLote,
)

STATUS_CORRIGIR = "CORRIGIR"
STATUS_REVISAR = "REVISAR"
STATUS_OK = "OK"
STATUS_SERVICO = "SERVIÇO"


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _normalizar_texto(valor: Any) -> str:
    texto = _texto(valor).upper()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(texto.split())


def _chave_cabecalho(valor: Any) -> str:
    texto = _normalizar_texto(valor)
    return re.sub(r"[^A-Z0-9]+", " ", texto).strip()


def _digitos(valor: Any) -> str:
    texto = _texto(valor)
    # Corrige somente a representação numérica típica do Excel (40169300.0).
    if re.fullmatch(r"\d+\.0+", texto):
        texto = texto.split(".", 1)[0]
    return "".join(c for c in texto if c.isdigit())


def _ncm(valor: Any) -> str:
    numero = _digitos(valor)
    return numero.zfill(8) if numero and len(numero) < 8 else numero


def _cest(valor: Any) -> str:
    numero = _digitos(valor)
    return numero.zfill(7) if numero and len(numero) < 7 else numero


def _formatar_cest(valor: Any) -> str:
    numero = _cest(valor)
    if len(numero) == 7:
        return f"{numero[:2]}.{numero[2:5]}.{numero[5:]}"
    return numero


def _numero(valor: Any) -> float:
    texto = _texto(valor).replace("%", "").replace("R$", "").strip()
    if not texto:
        return 0.0
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _percentual_valor(valor: Any, formatado_como_percentual: bool = False) -> float:
    """Converte um valor de percentual para pontos percentuais.

    A detecção do formato da coluna é feita uma única vez no início da leitura.
    Assim, a auditoria pode voltar a usar ``values_only=True`` no openpyxl, que é
    bem mais rápido em cadastros grandes, sem perder o tratamento correto de
    células formatadas como 18% (armazenadas como 0.18).
    """
    numero = _numero(valor)
    if formatado_como_percentual and isinstance(valor, (int, float)):
        return float(valor) * 100.0
    return numero


def _percentual_celula(celulas: Iterable[Any], cabecalhos: Dict[str, int], campo: str) -> float:
    """Compatibilidade com testes/integrações anteriores da 18.1.3.

    A rotina principal da 18.1.5 não usa esta função por linha; ela permanece
    apenas para chamadas pontuais e para preservar a API interna existente.
    """
    idx = cabecalhos.get(campo)
    if idx is None:
        return 0.0
    valores = list(celulas) if not isinstance(celulas, tuple) else celulas
    if idx >= len(valores):
        return 0.0
    cel = valores[idx]
    valor = getattr(cel, "value", cel)
    formato = str(getattr(cel, "number_format", "") or "")
    return _percentual_valor(valor, "%" in formato)


def _sim_nao(valor: Any) -> str:
    texto = _normalizar_texto(valor)
    if texto in {"SIM", "S", "1", "TRUE", "VERDADEIRO", "YES"}:
        return "SIM"
    if texto in {"NAO", "N", "0", "FALSE", "FALSO", "NO"}:
        return "NÃO"
    return _texto(valor)


def _codigo_fiscal(valor: Any, tamanho: int) -> str:
    texto = _texto(valor)
    digitos = _digitos(valor)
    if digitos and len(digitos) <= tamanho:
        return digitos.zfill(tamanho)
    return texto


def _pct(cst: str, aliquota: Optional[float]) -> str:
    partes = []
    if str(cst or "").strip():
        partes.append(f"CST {str(cst).strip()}")
    if aliquota is not None:
        partes.append(f"{float(aliquota):.2f}%".replace(".", ","))
    return " • ".join(partes) or "—"


_CORES_DESCRICAO = {
    "PRETO", "PRETA", "VERMELHO", "VERMELHA", "VERDE", "AZUL", "BRANCO",
    "BRANCA", "AMARELO", "AMARELA", "CINZA", "PRATA", "DOURADO", "DOURADA",
    "LARANJA", "ROSA", "ROXO", "ROXA", "FOSCO", "FOSCA", "CRISTAL",
}

_LADOS_DESCRICAO = {
    "LD", "LE", "DIR", "DIREITO", "DIREITA", "ESQ", "ESQUERDO", "ESQUERDA",
    "DIANTEIRO", "DIANTEIRA", "TRASEIRO", "TRASEIRA",
}

_RUIDO_DESCRICAO = {
    "ORIG", "ORIGINAL", "PAR", "UN", "UND", "PC", "PCS", "PÇ", "PÇS",
    "COM", "SEM",
}


def _ncm_valido(valor: Any) -> bool:
    ncm = _ncm(valor)
    return len(ncm) == 8 and ncm != "00000000"


def _marca_descricao(descricao: Any) -> str:
    """Extrai a marca informada entre parênteses sem deixar ruído como 'B BIKER'."""
    texto = _normalizar_texto(descricao)
    encontrados = re.findall(r"\(([^()]*)\)", texto)
    if not encontrados:
        return ""
    tokens = [t for t in encontrados[-1].split() if len(t) > 1 and not t.isdigit()]
    return " ".join(tokens)


def _assinatura_descricao_completa(descricao: Any) -> str:
    texto = _normalizar_texto(descricao)
    texto = texto.replace("(", " ").replace(")", " ")
    return " ".join(texto.split())


def _tokens_familia_descricao(descricao: Any) -> List[str]:
    """Remove apenas variações que normalmente não mudam a classificação fiscal.

    Material (nylon, plástico, aço, borracha etc.) é deliberadamente preservado,
    pois pode mudar o NCM. A finalidade é reconhecer variantes como cor, lado,
    medida/ano e embalagem sem transformar produtos diferentes em equivalentes.
    """
    texto = _normalizar_texto(descricao)
    texto = re.sub(r"\([^)]*\)", " ", texto)
    tokens: List[str] = []
    for token in texto.split():
        if token in _CORES_DESCRICAO or token in _LADOS_DESCRICAO or token in _RUIDO_DESCRICAO:
            continue
        if len(token) <= 1:
            continue
        if re.fullmatch(r"\d+(?:V|W|MM|CM|ML|G|KG)?", token):
            continue
        if re.fullmatch(r"\d{2,4}", token):
            continue
        tokens.append(token)
    return tokens


def _assinatura_familia_descricao(descricao: Any) -> str:
    return " ".join(_tokens_familia_descricao(descricao))


@dataclass(frozen=True)
class InferenciaNCMDescricao:
    ncm: str
    confianca: float
    metodo: str
    referencia: str


@dataclass(frozen=True)
class CandidatoNCMDescricao:
    ncm: str
    confianca: float
    metodo: str
    referencia: str
    ocorrencias: int = 0

    @property
    def resumo(self) -> str:
        base = f"{self.ncm} ({self.confianca:.0f}%)"
        if self.ocorrencias:
            base += f" • {self.ocorrencias} ref."
        return base


@dataclass
class IndiceNCMDescricao:
    por_codigo: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    por_ean: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    por_descricao_completa: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    por_assinatura: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    amostra_assinatura: Dict[tuple[str, str], str] = field(default_factory=dict)
    referencias_unicas: List[tuple[str, set[str], str, str, str]] = field(default_factory=list)
    por_marca: Dict[str, List[int]] = field(default_factory=lambda: defaultdict(list))
    por_token: Dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))
    # 18.1.9 — consenso hierárquico de família comercial. Estes índices não
    # substituem as regras semânticas oficiais; só entram como evidência de
    # baixa prioridade quando a família é muito estável no próprio cadastro.
    por_prefixo1: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    por_prefixo2: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    por_prefixo3: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    por_marca_prefixo2: Dict[tuple[str, str], Counter] = field(default_factory=lambda: defaultdict(Counter))
    amostra_prefixo: Dict[tuple[str, str], str] = field(default_factory=dict)


@dataclass
class ItemAuditoriaExcel:
    linha_excel: int
    codigo: str
    descricao: str
    ncm_atual: str
    cest_atual: str
    ncm_sugerido: str
    cest_sugerido: str
    status: str
    problema: str
    correcao_sugerida: str
    seguranca: float
    ncm_candidatos: str = ""
    cst_pis_atual: str = ""
    cst_pis_referencia: str = ""
    pis_atual: float = 0.0
    pis_referencia: Optional[float] = None
    cst_cofins_atual: str = ""
    cst_cofins_referencia: str = ""
    cofins_atual: float = 0.0
    cofins_referencia: Optional[float] = None
    cst_ipi_atual: str = ""
    ipi_atual: float = 0.0
    ipi_referencia: Optional[float] = None
    divergencias: List[str] = field(default_factory=list)
    pendencias: List[str] = field(default_factory=list)
    observacao: str = ""
    codigo_barras: str = ""
    ex_tipi: str = ""
    cst_icms_atual: str = ""
    cfop_atual: str = ""
    icms_desonerado_atual: str = ""
    reducao_bc_icms_atual: float = 0.0
    aliquota_icms_atual: float = 0.0
    icms_st_atual: str = ""
    mva_icms_st_atual: float = 0.0
    reducao_bc_icms_st_atual: float = 0.0
    aliquota_icms_st_atual: float = 0.0
    aliquota_fem_atual: float = 0.0
    nat_receita_atual: str = ""
    cst_icms_sugerido: str = ""
    cfop_sugerido: str = ""
    icms_desonerado_sugerido: str = ""
    cst_ipi_sugerido: str = ""
    nat_receita_sugerida: str = ""
    avisos_informativos: List[str] = field(default_factory=list)
    aliquota_icms_referencia: Optional[float] = None
    st_referencia: str = "REVISAR"
    mva_referencia: Optional[float] = None
    fem_referencia: Optional[float] = None
    fundamento_icms: str = ""
    fundamento_piscofins: str = ""
    fonte_icms: str = ""
    fonte_piscofins: str = ""

    @property
    def pis_atual_texto(self) -> str:
        return _pct(self.cst_pis_atual, self.pis_atual if self.pis_atual or self.cst_pis_atual else None)

    @property
    def pis_referencia_texto(self) -> str:
        return _pct(self.cst_pis_referencia, self.pis_referencia)

    @property
    def cofins_atual_texto(self) -> str:
        return _pct(self.cst_cofins_atual, self.cofins_atual if self.cofins_atual or self.cst_cofins_atual else None)

    @property
    def cofins_referencia_texto(self) -> str:
        return _pct(self.cst_cofins_referencia, self.cofins_referencia)


@dataclass
class ResultadoAuditoriaExcel:
    arquivo: str
    planilha: str
    itens: List[ItemAuditoriaExcel] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)
    contexto: Dict[str, Any] = field(default_factory=dict)

    def resumo(self) -> Dict[str, int]:
        return {
            "itens": len(self.itens),
            "corrigir": sum(1 for i in self.itens if i.status == STATUS_CORRIGIR),
            "revisar": sum(1 for i in self.itens if i.status == STATUS_REVISAR),
            "ok": sum(1 for i in self.itens if i.status == STATUS_OK),
            "servicos": sum(1 for i in self.itens if i.status == STATUS_SERVICO),
            "sem_ncm": sum(1 for i in self.itens if i.status != STATUS_SERVICO and len(i.ncm_atual) != 8),
            "ncm_unicos": len({i.ncm_atual for i in self.itens if len(i.ncm_atual) == 8}),
        }


class AuditoriaCadastrosExcelService:
    """Importa uma planilha de cadastro e produz uma auditoria somente analítica."""

    ALIASES = {
        "codigo": {
            "CODIGO", "COD PRODUTO", "CODIGO PRODUTO", "COD ITEM", "ITEM",
            "CODIGO DO PRODUTO", "COD DO PRODUTO", "COD PROD", "SKU", "REFERENCIA",
        },
        "descricao": {
            "DESCRICAO", "PRODUTO", "DESCRICAO PRODUTO", "NOME PRODUTO",
            "DESCRICAO DO PRODUTO", "DESC PRODUTO", "DESCRICAO ITEM",
        },
        "codigo_barras": {"CODIGO DE BARRAS", "COD BARRAS", "EAN", "GTIN"},
        "ncm": {
            "NCM", "COD NCM", "CODIGO NCM", "NCM ATUAL", "NCM CADASTRADO",
            "NCM ORIGINAL", "NCM PRODUTO", "CLASSIFICACAO FISCAL",
        },
        "ex_tipi": {"EX", "EX TIPI", "EXTIPI"},
        "cest": {"CEST", "CEST ATUAL", "CEST CADASTRADO", "CEST ORIGINAL"},
        "cst_icms": {"CST ICMS", "ICMS CST", "CSOSN"},
        "cfop": {"CFOP", "CFOP SAIDA", "CFOP DE SAIDA"},
        "icms_desonerado": {"ICMS DESONERADO", "DESONERACAO ICMS", "DESONERADO"},
        "red_bc_icms": {"RED BC ICMS", "RED BC ICMS %", "REDUCAO BC ICMS", "REDUCAO BC ICMS %"},
        "aliq_icms": {"ALIQ ICMS", "ALIQ ICMS %", "ALIQUOTA ICMS", "ALIQUOTA ICMS %"},
        "icms_st_indicador": {"ICMS ST", "ST", "TEM ST"},
        "mva_st": {"MVA ICMS ST", "MVA ICMS ST %", "MVA ST", "MVA"},
        "red_bc_st": {"RED BC ICMS ST", "RED BC ICMS ST %", "REDUCAO BC ICMS ST"},
        "aliq_icms_st": {"ALIQ ICMS ST", "ALIQ ICMS ST %", "ALIQUOTA ICMS ST"},
        "aliq_fem": {"ALIQ FEM", "ALIQ FEM %", "FEM", "FCP", "FCP FEM"},
        "cst_piscofins": {"CST PIS COFINS SAIDA", "CST PIS COFINS", "CST PIS/COFINS SAIDA", "CST PIS/COFINS"},
        "cst_pis": {"CST PIS", "PIS CST"},
        "aliq_pis": {"ALIQUOTA PIS", "ALIQ PIS", "PIS ALIQUOTA"},
        "cst_cofins": {"CST COFINS", "COFINS CST"},
        "aliq_cofins": {"ALIQUOTA COFINS", "ALIQ COFINS", "COFINS ALIQUOTA"},
        "cst_ipi": {"CST IPI", "IPI CST"},
        "aliq_ipi": {"ALIQUOTA IPI", "ALIQ IPI", "IPI ALIQUOTA"},
        "nat_receita": {"NAT DE RECEITA", "NAT RECEITA", "NATUREZA DA RECEITA", "NAT RECEITA PIS COFINS"},
    }

    CAMPOS_PERCENTUAIS = (
        "red_bc_icms", "aliq_icms", "mva_st", "red_bc_st",
        "aliq_icms_st", "aliq_fem", "aliq_pis", "aliq_cofins", "aliq_ipi",
    )

    # Avisos de cautela do motor nacional que são importantes para rastreabilidade,
    # mas não significam, por si só, que o cadastro esteja errado. Na 18.1.3 esses
    # textos faziam praticamente toda a base virar REVISAR, mesmo quando NCM, CEST,
    # ST e alíquotas estavam coerentes.
    PENDENCIAS_INFORMATIVAS = (
        "SUGESTAO CONDICIONAL REGIME CUMULATIVO",
        "SUGESTAO CONDICIONAL REGIME NAO CUMULATIVO",
        "PADRAO RESIDUAL REVISAR EXCECOES DO ANEXO I",
        "CONFORME MOTOR DETALHADO DE MG",
    )

    # Famílias em que uma palavra comercial pode esconder classificações muito
    # diferentes (material, tecnologia ou função). Nelas o consenso do cadastro
    # não é usado como atalho; somente uma regra semântica específica ou uma
    # correspondência forte (código/EAN/descrição/família) pode sugerir NCM.
    FAMILIAS_CONSENSO_BLOQUEADAS = {
        "ANEL", "BOIA", "CABO", "CAPA", "CHAVE", "CORREIA", "CORRENTE",
        "BOMBA", "ESCOVA", "ESTATOR", "FILTRO", "GUARNICAO", "JOGO", "JUNTA", "KIT",
        "LAMPADA", "LANTERNA", "LENTE", "LUVA", "MANGUEIRA", "MOTOR", "PAINEL",
        "REGULADOR", "ROLAMENTO", "SERVICO", "TRAVA", "VALVULA",
    }

    # 18.1.11 — linhas de mão de obra/serviço não devem receber NCM por
    # semelhança com a peça citada na descrição. A detecção só é usada para
    # registros com NCM ausente/zerado na rotina principal.
    PADROES_DESCRICAO_SERVICO = (
        (r"^SERVICO\b", "descrição identifica explicitamente um serviço", 99.0),
        (r"^REVISAO\b", "revisão/manutenção", 98.0),
        (r"^TROCA\b", "mão de obra de troca/substituição", 97.0),
        (r"^PINTURA\b", "serviço de pintura", 98.0),
        (r"^FRETE\b", "frete/encargo de transporte", 99.0),
        (r"^ENRAI(?:ACAO|CAO)\b", "serviço de enraiação de roda", 98.0),
        (r"^MONTAGEM\b", "mão de obra de montagem", 97.0),
        (r"^RETIFICA\b", "serviço de retífica", 99.0),
        (r"^SOLDA\b", "serviço de solda", 99.0),
        (r"^LIMPEZA\b", "serviço de limpeza/manutenção", 97.0),
        (r"^REGULAGEM\b", "serviço de regulagem", 98.0),
        (r"^DESEMPENO\b", "serviço de desempeno", 98.0),
        (r"^RECUPERACAO\b", "serviço de recuperação/reparo", 98.0),
        (r"^PASTILHAMENTO\b", "serviço de ajuste/pastilhamento", 98.0),
        (r"^FUNCIONAMENTO\b", "serviço de diagnóstico/funcionamento", 96.0),
        (r"^MODIFICACAO\b", "serviço de modificação", 97.0),
        (r"^DESCONJUGAR\b", "serviço mecânico", 97.0),
        (r"^DESCOMBINAR\b", "serviço mecânico", 97.0),
        (r"^DESENTUPIR\b", "serviço de desobstrução/limpeza", 98.0),
        (r"^SACAR\b", "mão de obra de remoção", 97.0),
        (r"^EMENDAR\b", "mão de obra de reparo", 97.0),
        (r"^INSTALACAO\b", "serviço de instalação", 98.0),
        (r"^ATIVAMENTO\b", "serviço de ativação/ajuste", 97.0),
        (r"^ROSCA\b.*\b(?:CILINDRO|BUJAO)\b", "reparo de rosca", 96.0),
    )

    @classmethod
    def _detectar_servico(cls, descricao: Any, codigo: Any = "") -> Optional[tuple[str, float]]:
        texto = _normalizar_texto(descricao)
        texto = re.sub(r"[^A-Z0-9]+", " ", texto).strip()
        if not texto:
            return None
        for padrao, motivo, confianca in cls.PADROES_DESCRICAO_SERVICO:
            if re.search(padrao, texto):
                return motivo, float(confianca)
        return None

    @classmethod
    def _item_servico(
        cls,
        *,
        linha_excel: int,
        codigo: Any,
        descricao: Any,
        ncm_atual: Any,
        cest_atual: Any,
        motivo: str,
        confianca: float,
        originais: Dict[str, Any],
        cst_pis: str = "",
        cst_cofins: str = "",
        aliq_pis: float = 0.0,
        aliq_cofins: float = 0.0,
        cst_ipi: str = "",
        aliq_ipi: float = 0.0,
    ) -> ItemAuditoriaExcel:
        problema = (
            "Item identificado como serviço/mão de obra. NCM, CEST, CST/CFOP de mercadoria, "
            "ICMS-ST e IPI de produto não se aplicam nesta auditoria de mercadorias."
        )
        correcao = (
            "Manter este registro separado do cadastro tributário de mercadorias. "
            "Conferir a tributação do serviço (código do serviço/ISS/NFS-e) no fluxo próprio, "
            "conforme o município e a natureza efetiva da prestação."
        )
        observacao = (
            f"FiscalPro identificou a linha como serviço ({motivo}; confiança {confianca:.0f}%). "
            "Nenhum NCM foi sugerido para evitar classificar como mercadoria a peça citada na descrição."
        )
        return ItemAuditoriaExcel(
            linha_excel=linha_excel,
            codigo=_texto(codigo),
            descricao=_texto(descricao),
            ncm_atual=_ncm(ncm_atual),
            cest_atual=_formatar_cest(cest_atual),
            ncm_sugerido="",
            cest_sugerido="",
            status=STATUS_SERVICO,
            problema=problema,
            correcao_sugerida=correcao,
            seguranca=float(confianca),
            ncm_candidatos="",
            cst_pis_atual=cst_pis,
            pis_atual=aliq_pis,
            cst_cofins_atual=cst_cofins,
            cofins_atual=aliq_cofins,
            cst_ipi_atual=cst_ipi,
            ipi_atual=aliq_ipi,
            observacao=observacao,
            codigo_barras=str(originais.get("codigo_barras") or ""),
            ex_tipi=str(originais.get("ex_tipi") or ""),
            nat_receita_atual=str(originais.get("nat_receita") or ""),
            st_referencia="N/A",
        )

    # Regras nacionais de alta confiança para descrições em que a própria NCM
    # contém uma abertura específica para a peça/função. A regra é propositalmente
    # curta e conservadora: se a descrição não trouxer o elemento distintivo, o
    # FiscalPro continua em REVISAR em vez de escolher um código genérico.
    REGRAS_NCM_SEMANTICAS = (
        (r"^ANEL\s+ORIG\b", "40169300", 93.0, "anel de vedação", "NCM oficial 40169300 — juntas, gaxetas e semelhantes"),
        (r"^GUARNICAO\b", "40169300", 91.0, "guarnição de vedação", "NCM oficial 40169300 — juntas, gaxetas e semelhantes"),
        (r"^RETENTOR\b", "40169300", 94.0, "elemento de vedação", "NCM oficial 40169300 — juntas, gaxetas e semelhantes"),
        (r"^MOTOR\s+PARTIDA\b", "85114000", 96.0, "motor de arranque", "NCM oficial 85114000 — motores de arranque"),
        (r"^ESCOVA(?:S)?\s+(?:ARRANQUE|MOTOR\s+PARTIDA)\b", "85452000", 96.0, "escova de carvão para uso elétrico", "NCM oficial 85452000 — escovas de carvão"),
        (r"^FILTRO\s+(?:DE\s+)?AR\b", "84213100", 96.0, "filtro de entrada de ar do motor", "NCM oficial 84213100 — filtros de entrada de ar para motores"),
        (r"^FILTRO\s+(?:DE\s+)?(?:OLEO|COMBUS(?:TIVEL)?)\b", "84212300", 96.0, "filtro de óleo/combustível do motor", "NCM oficial 84212300 — filtros de carburante ou óleo para motores"),
        (r"^VALVULA\s+(?:ADM(?:ISSAO)?|ESCAP(?:E|AMENTO)?)\b", "84099114", 96.0, "válvula de admissão/escape", "NCM oficial 84099114 — válvulas de admissão ou de escape"),
        (r"^COLETOR\s+(?:ADM(?:ISSAO)?|ESCAP(?:E|AMENTO)?)\b", "84099115", 96.0, "coletor de admissão/escape", "NCM oficial 84099115 — coletores de admissão ou de escape"),
        (r"^ANEL(?:EIS|ES)?\s+(?:DE\s+)?SEGMENTO\b", "84099116", 96.0, "anel de segmento", "NCM oficial 84099116 — anéis de segmento"),
        (r"^GUIA\s+(?:DE\s+)?VALVULA\b", "84099117", 96.0, "guia de válvula", "NCM oficial 84099117 — guias de válvulas"),
        (r"^CAMISA\s+(?:DE\s+)?CILINDRO\b", "84099130", 96.0, "camisa de cilindro", "NCM oficial 84099130 — camisas de cilindro"),
        (r"^BIELA\b", "84099111", 96.0, "biela", "NCM oficial 84099111 — bielas"),
        (r"^BALANCIM\b", "84099190", 92.0, "parte do motor de ignição por centelha", "NCM oficial 84099190 — outras partes de motores de ignição por centelha"),
        (r"^(?:KIT\s+)?PISTAO\b", "84099120", 96.0, "pistão/êmbolo", "NCM oficial 84099120 — pistões ou êmbolos"),
        (r"^CDI\b", "85118030", 96.0, "ignição eletrônica digital", "NCM oficial 85118030 — ignição eletrônica digital"),
        (r"^REGULADOR\s+(?:DE\s+)?VOLTAGEM\b", "85118020", 96.0, "regulador de voltagem", "NCM oficial 85118020 — reguladores de voltagem"),
        (r"^(?:REGULADOR\s+RETIFICADOR|RETIFICADOR\s+REGULADOR)\b", "85118020", 94.0, "regulador/retificador", "NCM oficial 85118020 — reguladores de voltagem"),
        (r"^REGULADOR\s+(?:DE\s+)?PRESSAO\b", "84811000", 93.0, "válvula redutora de pressão", "NCM oficial 84811000 — válvulas redutoras de pressão"),
        (r"^BOBINA\s+(?:DE\s+)?IGNICAO\b", "85113020", 96.0, "bobina de ignição", "NCM oficial 85113020 — bobinas de ignição"),
        (r"^VELA\s+(?:DE\s+)?IGNICAO\b", "85111000", 96.0, "vela de ignição", "NCM oficial 85111000 — velas de ignição"),
        (r"^ROLAMENTO\s+(?:DE\s+)?AGULHA(?:S)?\b", "84824000", 96.0, "rolamento de agulhas", "NCM oficial 84824000 — rolamentos de agulhas"),
        (r"^(?:PARAFUSO|PRISIONEIRO)\b", "73181500", 95.0, "parafuso/perno roscado", "NCM oficial 73181500 — outros parafusos e pinos/pernos"),
        (r"^PORCA\b", "73181600", 95.0, "porca", "NCM oficial 73181600 — porcas"),
        (r"^(?:CONTRAPINO|CONTRA\s+PINO)\b", "73182400", 95.0, "contrapino", "NCM oficial 73182400 — chavetas e contrapinos"),
        (r"^TRAVA\s+DISCO\b.*\bANTI\s*ROUBO\b", "83011000", 95.0, "trava do tipo cadeado", "NCM oficial 83011000 — cadeados"),
        (r"^KIT\s+RELACAO\b", "87141000", 95.0, "kit de transmissão para motocicleta", "NCM 87141000 — partes/acessórios de motocicletas; Siscomex 2026 vincula kit coroa+pinhão+corrente"),
        (r"^DISCO\s+FREIO\b", "87141000", 94.0, "parte de freio de motocicleta", "NCM oficial 87141000 — partes e acessórios de motocicletas"),
        (r"^CABO\s+MOTOR\s+PARTIDA\b", "85444200", 93.0, "condutor elétrico com conexão", "NCM oficial 85444200 — condutores elétricos munidos de peças de conexão"),
        (r"^(?:JOGO\s+JUNTA|JUNTA\s+KIT)\b", "84849000", 93.0, "jogo/sortido de juntas", "NCM oficial 84849000 — outros jogos/sortidos de juntas"),
        (r"^INTERRUPTOR\b", "85365090", 94.0, "interruptor/comutador elétrico", "NCM oficial 85365090 — outros interruptores/comutadores"),
        (r"^CHAVE\s+LUZ\b", "85365090", 94.0, "interruptor/comutador de luz", "NCM oficial 85365090 — outros interruptores/comutadores"),
        (r"^BOMBA\s+(?:DE\s+)?COMBUSTIVEL\b", "84133010", 94.0, "bomba de combustível para gasolina/álcool", "NCM oficial 84133010 — bombas para gasolina ou álcool"),
        (r"^BOMBA\s+(?:DE\s+)?OLEO\b", "84133030", 94.0, "bomba de óleo lubrificante do motor", "NCM oficial 84133030 — bombas para óleo lubrificante"),
        (
            r"^(?:FAIXA|ADESIVO)\s+TANQ(?:UE)?\b.*\b(?:TWISTER|TWSTER)\b",
            "39199020",
            89.0,
            "faixa/adesivo autoadesivo de tanque de motocicleta",
            "NCM 39199020 — materiais autoadesivos de plástico, de PVC; confirmar o material da faixa antes de corrigir",
        ),
        (r"^GASOLINA\b", "27101259", 96.0, "gasolina automotiva", "NCM 27101259 — gasolina automotiva; o CEST depende do tipo A/C e Premium"),
        (r"^BUZINA\b", "85123000", 95.0, "aparelho de sinalização acústica", "NCM oficial 85123000 — aparelhos de sinalização acústica"),
        (r"^CORRENTE\s+(?:DE\s+)?(?:TRANSMISSAO|RELACAO)\b", "73151210", 95.0, "corrente de transmissão", "NCM oficial 73151210 — correntes de transmissão"),
        (r"^CORRENTE\b.*\b(?:415|420|428|520|525|530)[A-Z0-9-]*\b", "73151210", 94.0, "corrente de transmissão identificada por medida comercial", "NCM oficial 73151210 — correntes de transmissão"),
    )

    @staticmethod
    def _tokens_prefixo_familia(descricao: Any) -> List[str]:
        texto = _normalizar_texto(descricao)
        texto = re.sub(r"\([^)]*\)", " ", texto)
        texto = re.sub(r"[^A-Z0-9]+", " ", texto)
        return [token for token in texto.split() if token]

    @classmethod
    def _inferir_ncm_regra_semantica(cls, descricao: Any) -> Optional[InferenciaNCMDescricao]:
        texto = _normalizar_texto(descricao)
        texto = re.sub(r"[^A-Z0-9]+", " ", texto).strip()
        if not texto:
            return None

        # Serviços não recebem NCM. A rotina principal os classifica em uma
        # categoria própria antes de chamar o motor tributário. Esta proteção
        # adicional impede inferência semântica quando o método é chamado isoladamente.
        if cls._detectar_servico(descricao):
            return None

        for padrao, ncm, confianca, motivo, referencia in cls.REGRAS_NCM_SEMANTICAS:
            if re.search(padrao, texto):
                return InferenciaNCMDescricao(
                    ncm=ncm,
                    confianca=float(confianca),
                    metodo=f"regra semântica por função: {motivo}",
                    referencia=referencia,
                )

        # Lâmpadas: a tecnologia e a tensão mudam o subitem. Por isso só há
        # sugestão quando a descrição traz a evidência necessária.
        if texto.startswith("LAMPADA "):
            if re.search(r"\bLED\b", texto):
                return InferenciaNCMDescricao(
                    "85395200", 95.0,
                    "regra semântica: lâmpada LED",
                    "NCM oficial 85395200 — lâmpadas e tubos de diodos emissores de luz (LED)",
                )
            if re.search(r"\b(?:6|12|15)\s*V\b", texto):
                if re.search(r"\b(?:H4|BIODO|HALOG(?:ENA|ENO)?)\b", texto):
                    return InferenciaNCMDescricao(
                        "85392110", 94.0,
                        "regra semântica: lâmpada halógena com tensão até 15 V",
                        "NCM oficial 85392110 — halógenas de tungstênio para tensão <= 15 V",
                    )
                return InferenciaNCMDescricao(
                    "85392910", 91.0,
                    "regra semântica: lâmpada de incandescência com tensão até 15 V",
                    "NCM oficial 85392910 — outras lâmpadas de incandescência para tensão <= 15 V",
                )
        return None

    @classmethod
    def _inferir_ncm_consenso_familia(
        cls, indice: IndiceNCMDescricao, descricao: Any
    ) -> Optional[InferenciaNCMDescricao]:
        tokens = cls._tokens_prefixo_familia(descricao)
        if not tokens or tokens[0] in cls.FAMILIAS_CONSENSO_BLOQUEADAS:
            return None
        marca = _marca_descricao(descricao)

        def dominante(contador: Optional[Counter]) -> Optional[tuple[str, int, int, float]]:
            if not contador:
                return None
            total = sum(int(v) for v in contador.values())
            if total <= 0:
                return None
            ncm, quantidade = contador.most_common(1)[0]
            if not _ncm_valido(ncm):
                return None
            return str(ncm), int(quantidade), total, float(quantidade) / float(total)

        if marca and len(tokens) >= 2:
            chave = (marca, " ".join(tokens[:2]))
            d = dominante(indice.por_marca_prefixo2.get(chave))
            if d and d[2] >= 5 and d[3] >= 0.999999:
                ncm, _, total, _ = d
                referencia = indice.amostra_prefixo.get(("M2:" + marca + ":" + chave[1], ncm), _texto(descricao))
                return InferenciaNCMDescricao(
                    ncm, min(89.0, 82.0 + total / 3.0),
                    f"consenso da mesma marca e família ({total} referências concordantes)",
                    referencia,
                )

        if len(tokens) >= 3:
            chave3 = " ".join(tokens[:3])
            d = dominante(indice.por_prefixo3.get(chave3))
            if d and d[2] >= 8 and d[3] >= 0.999999:
                ncm, _, total, _ = d
                referencia = indice.amostra_prefixo.get(("P3:" + chave3, ncm), _texto(descricao))
                return InferenciaNCMDescricao(
                    ncm, 87.0,
                    f"consenso de família comercial de 3 termos ({total} referências concordantes)",
                    referencia,
                )

        if len(tokens) >= 2:
            chave2 = " ".join(tokens[:2])
            d = dominante(indice.por_prefixo2.get(chave2))
            if d and d[2] >= 30 and d[3] >= 0.998:
                ncm, quantidade, total, pureza = d
                referencia = indice.amostra_prefixo.get(("P2:" + chave2, ncm), _texto(descricao))
                return InferenciaNCMDescricao(
                    ncm, 86.0,
                    f"consenso de família comercial ({quantidade}/{total}; {pureza*100:.1f}% no cadastro)",
                    referencia,
                )

        if len(tokens) >= 1:
            chave1 = tokens[0]
            d = dominante(indice.por_prefixo1.get(chave1))
            if d and d[2] >= 200 and d[3] >= 0.999999:
                ncm, _, total, _ = d
                referencia = indice.amostra_prefixo.get(("P1:" + chave1, ncm), _texto(descricao))
                return InferenciaNCMDescricao(
                    ncm, 84.0,
                    f"consenso de família principal ({total} referências concordantes)",
                    referencia,
                )
        return None

    @classmethod
    def _pendencia_bloqueia_status(cls, analise: ResultadoItemLote, texto: str) -> bool:
        normalizado = re.sub(r"[^A-Z0-9]+", " ", _normalizar_texto(texto)).strip()
        if not normalizado:
            return False
        if any(marcador in normalizado for marcador in cls.PENDENCIAS_INFORMATIVAS):
            return False
        # Quando a aplicabilidade da ST já foi confirmada, a ressalva de quem
        # recolhe o imposto é operacional. Ela continua na observação, mas não
        # rebaixa a classificação tributária do produto para REVISAR.
        if (
            bool(getattr(analise, "st_confirmado", False))
            and "RESPONSABILIDADE PELO RECOLHIMENTO" in normalizado
            and "ICMS ST" in normalizado
        ):
            return False
        return True

    @classmethod
    def _separar_pendencias(
        cls, analise: ResultadoItemLote, pendencias: Iterable[str]
    ) -> tuple[List[str], List[str]]:
        bloqueantes: List[str] = []
        informativas: List[str] = []
        for texto in dict.fromkeys(str(x or "").strip() for x in pendencias if str(x or "").strip()):
            if cls._pendencia_bloqueia_status(analise, texto):
                bloqueantes.append(texto)
            else:
                informativas.append(texto)
        return bloqueantes, informativas

    @classmethod
    def _sugerir_campos_operacionais(
        cls,
        bruto: ItemBrutoLote,
        analise: ResultadoItemLote,
        contexto: Dict[str, Any],
        originais: Dict[str, Any],
        pendencias_originais: Iterable[str],
    ) -> Dict[str, str]:
        """Preenche a ficha sem inventar campos que dependem de premissas ausentes.

        CFOP/CST ICMS são sugeridos apenas em vendas de revenda quando a decisão
        tributária é suficiente. CST IPI e Natureza da Receita permanecem como
        REVISAR quando a operação exige informação que o cadastro não trouxe.
        """
        regime = EmpresasRegimesService.normalizar_regime(contexto.get("regime"))
        operacao = _normalizar_texto(contexto.get("operacao") or bruto.operacao_sugerida)
        finalidade = _normalizar_texto(contexto.get("finalidade"))
        uf_origem = _normalizar_texto(contexto.get("uf_origem") or bruto.uf_origem)
        uf_destino = _normalizar_texto(contexto.get("uf_destino") or bruto.uf_destino)
        mesma_uf = bool(uf_origem and uf_destino and uf_origem == uf_destino)
        st_ref = cls._st_referencia(analise)
        pend_norm = " | ".join(_normalizar_texto(x) for x in pendencias_originais)
        responsabilidade_st_em_aberto = "RESPONSABILIDADE PELO RECOLHIMENTO" in pend_norm

        cst_icms = str(originais.get("cst_icms") or "").strip()
        if not cst_icms:
            if regime in {"LUCRO REAL", "LUCRO PRESUMIDO"} and operacao == "VENDA":
                if st_ref == "NÃO":
                    if float(originais.get("red_bc_icms") or 0.0) > 0.0001:
                        cst_icms = "20"
                    elif (analise.aliquota_icms_esperada or 0.0) > 0:
                        cst_icms = "00"
                    else:
                        cst_icms = "REVISAR"
                elif st_ref == "SIM" and finalidade == "REVENDA" and not responsabilidade_st_em_aberto:
                    cst_icms = "60"
                else:
                    cst_icms = "REVISAR"
            else:
                cst_icms = "REVISAR"

        cfop = str(originais.get("cfop") or bruto.cfop or "").strip()
        if not cfop:
            if operacao == "VENDA" and finalidade == "REVENDA":
                if st_ref == "NÃO":
                    cfop = "5102" if mesma_uf else "6102"
                elif st_ref == "SIM" and not responsabilidade_st_em_aberto:
                    cfop = "5405" if mesma_uf else "6404"
                else:
                    cfop = "REVISAR"
            else:
                cfop = "REVISAR"

        desonerado = str(originais.get("icms_desonerado") or "").strip()
        if not desonerado:
            tem_beneficio_aberto = any(
                termo in pend_norm
                for termo in ("BENEFICIO", "ISENCAO", "DIFERIMENTO", "REDUCAO")
            )
            if (
                regime in {"LUCRO REAL", "LUCRO PRESUMIDO"}
                and (analise.aliquota_icms_esperada or 0.0) > 0
                and float(originais.get("red_bc_icms") or 0.0) <= 0.0001
                and not tem_beneficio_aberto
            ):
                desonerado = "NÃO"
            else:
                desonerado = "REVISAR"

        cst_ipi = str(bruto.cst_ipi_atual or "").strip()
        if not cst_ipi:
            # A TIPI informa a alíquota do produto, mas o CST de saída também
            # depende de o estabelecimento ser industrial/equiparado. Sem essa
            # informação, não inventamos um código. A ficha deixa o CST IPI em
            # branco e registra a limitação na Observação FiscalPro.
            cst_ipi = ""

        nat_receita = str(originais.get("nat_receita") or "").strip()
        if not nat_receita:
            csts = {
                str(analise.cst_pis_esperado or "").strip(),
                str(analise.cst_cofins_esperado or "").strip(),
            } - {""}
            if csts and csts.issubset({"01", "02"}):
                nat_receita = ""  # não é exigida para a tributação padrão da saída
            elif csts.intersection({"04", "05", "06", "07", "08", "09"}):
                nat_receita = "REVISAR"

        return {
            "cst_icms": cst_icms,
            "cfop": cfop,
            "icms_desonerado": desonerado,
            "cst_ipi": cst_ipi,
            "nat_receita": nat_receita,
        }

    @classmethod
    def _detectar_formatos_percentuais(cls, ws, cabecalhos: Dict[str, int]) -> Dict[str, bool]:
        """Detecta uma vez se cada coluna percentual usa o formato % do Excel.

        Antes da 18.1.5 a auditoria carregava objetos de célula completos para
        cada item apenas para consultar ``number_format``. Isso deixou cadastros
        grandes mais lentos. Aqui examinamos só uma pequena amostra inicial e,
        depois, a leitura principal volta ao modo rápido ``values_only=True``.
        """
        presentes = {campo: cabecalhos[campo] for campo in cls.CAMPOS_PERCENTUAIS if campo in cabecalhos}
        resultado = {campo: False for campo in presentes}
        pendentes = set(presentes)
        if not pendentes:
            return resultado

        limite = min(int(ws.max_row or 1), 102)
        if limite < 2:
            return resultado

        for linha in ws.iter_rows(min_row=2, max_row=limite):
            if not pendentes:
                break
            resolvidos = []
            for campo in pendentes:
                idx = presentes[campo]
                if idx >= len(linha):
                    continue
                celula = linha[idx]
                valor = getattr(celula, "value", None)
                if valor in (None, ""):
                    continue
                formato = str(getattr(celula, "number_format", "") or "")
                resultado[campo] = "%" in formato
                resolvidos.append(campo)
            for campo in resolvidos:
                pendentes.discard(campo)
        return resultado

    @staticmethod
    def _ncm_unico(contador: Optional[Counter]) -> tuple[str, int] | None:
        if not contador or len(contador) != 1:
            return None
        ncm, quantidade = contador.most_common(1)[0]
        if not _ncm_valido(ncm):
            return None
        return str(ncm), int(quantidade)

    @classmethod
    def _construir_indice_ncm_descricao(cls, ws, cabecalhos: Dict[str, int]) -> IndiceNCMDescricao:
        """Aprende referências já existentes na própria planilha.

        A auditoria não usa um palpite genérico quando o NCM está zerado. Primeiro
        procura produtos equivalentes que já tenham NCM válido no mesmo cadastro.
        Isso é especialmente útil em catálogos de autopeças com variações de cor,
        lado, ano/modelo e marca comercial. Assinaturas ambíguas são descartadas.
        """
        indice = IndiceNCMDescricao()
        for linha in ws.iter_rows(min_row=2, values_only=True):
            ncm = _ncm(cls._valor(linha, cabecalhos, "ncm"))
            if not _ncm_valido(ncm):
                continue

            descricao = _texto(cls._valor(linha, cabecalhos, "descricao"))
            codigo = _normalizar_texto(cls._valor(linha, cabecalhos, "codigo"))
            if cls._detectar_servico(descricao, codigo):
                # Não aprende NCM a partir de mão de obra/serviço, mesmo que o
                # cadastro antigo tenha um código fiscal preenchido indevidamente.
                continue
            ean = _digitos(cls._valor(linha, cabecalhos, "codigo_barras"))
            assinatura_completa = _assinatura_descricao_completa(descricao)
            assinatura = _assinatura_familia_descricao(descricao)

            if codigo:
                indice.por_codigo[codigo][ncm] += 1
            if ean:
                indice.por_ean[ean][ncm] += 1
            if assinatura_completa:
                indice.por_descricao_completa[assinatura_completa][ncm] += 1
            if assinatura:
                indice.por_assinatura[assinatura][ncm] += 1
                indice.amostra_assinatura.setdefault((assinatura, ncm), descricao)

            tokens_prefixo = cls._tokens_prefixo_familia(descricao)
            if tokens_prefixo:
                chave1 = tokens_prefixo[0]
                indice.por_prefixo1[chave1][ncm] += 1
                indice.amostra_prefixo.setdefault(("P1:" + chave1, ncm), descricao)
            if len(tokens_prefixo) >= 2:
                chave2 = " ".join(tokens_prefixo[:2])
                indice.por_prefixo2[chave2][ncm] += 1
                indice.amostra_prefixo.setdefault(("P2:" + chave2, ncm), descricao)
                marca_prefixo = _marca_descricao(descricao)
                if marca_prefixo:
                    indice.por_marca_prefixo2[(marca_prefixo, chave2)][ncm] += 1
                    indice.amostra_prefixo.setdefault(("M2:" + marca_prefixo + ":" + chave2, ncm), descricao)
            if len(tokens_prefixo) >= 3:
                chave3 = " ".join(tokens_prefixo[:3])
                indice.por_prefixo3[chave3][ncm] += 1
                indice.amostra_prefixo.setdefault(("P3:" + chave3, ncm), descricao)

        # Só entram na busca aproximada famílias que apontam para um único NCM.
        # Se o próprio cadastro contém classificações diferentes para a mesma
        # assinatura, o FiscalPro não aprende esse conflito como verdade.
        for assinatura, contador in indice.por_assinatura.items():
            unico = cls._ncm_unico(contador)
            if not unico:
                continue
            ncm, _ = unico
            referencia = indice.amostra_assinatura.get((assinatura, ncm), assinatura)
            tokens = {t for t in assinatura.split() if t}
            marca = _marca_descricao(referencia)
            pos = len(indice.referencias_unicas)
            indice.referencias_unicas.append((assinatura, tokens, ncm, referencia, marca))
            if marca:
                indice.por_marca[marca].append(pos)
            for token in tokens:
                if len(token) >= 4:
                    indice.por_token[token].add(pos)
        return indice

    @staticmethod
    def _pontuar_assinaturas(consulta: str, tokens_consulta: set[str], referencia: str, tokens_ref: set[str]) -> float:
        if not tokens_consulta or not tokens_ref:
            return 0.0
        inter = len(tokens_consulta & tokens_ref)
        if inter < 2:
            return 0.0
        uniao = len(tokens_consulta | tokens_ref)
        jaccard = (inter / uniao) if uniao else 0.0
        sequencia = SequenceMatcher(None, consulta, referencia).ratio()
        contido = tokens_consulta.issubset(tokens_ref) or tokens_ref.issubset(tokens_consulta)
        return (0.60 * jaccard) + (0.40 * sequencia) + (0.05 if contido else 0.0)

    @classmethod
    def _inferir_ncm_descricao(
        cls,
        indice: IndiceNCMDescricao,
        *,
        codigo: Any,
        codigo_barras: Any,
        descricao: Any,
    ) -> Optional[InferenciaNCMDescricao]:
        """Sugere NCM para cadastro zerado sem transformar ambiguidade em certeza.

        Ordem de evidência: mesmo código/EAN, descrição idêntica, família idêntica,
        variante da mesma marca e, por último, similaridade forte no próprio catálogo.
        A tributação pode ser simulada com o candidato, mas a ficha mantém a origem
        da inferência e limita a segurança quando não é uma correspondência exata.
        """
        if cls._detectar_servico(descricao, codigo):
            return None

        codigo_norm = _normalizar_texto(codigo)
        ean = _digitos(codigo_barras)
        descricao_texto = _texto(descricao)
        assinatura_completa = _assinatura_descricao_completa(descricao_texto)
        assinatura = _assinatura_familia_descricao(descricao_texto)

        if codigo_norm:
            unico = cls._ncm_unico(indice.por_codigo.get(codigo_norm))
            if unico:
                ncm, qtd = unico
                return InferenciaNCMDescricao(ncm, 97.0, f"mesmo código em {qtd} item(ns) do cadastro", codigo_norm)

        if ean:
            unico = cls._ncm_unico(indice.por_ean.get(ean))
            if unico:
                ncm, qtd = unico
                return InferenciaNCMDescricao(ncm, 97.0, f"mesmo EAN em {qtd} item(ns) do cadastro", ean)

        # 18.1.9 — antes de copiar um NCM de uma descrição parecida, aplica regras
        # semânticas em que a função da peça coincide diretamente com uma abertura
        # específica da NCM. Isso corrige, por exemplo, motor de partida, escova de
        # arranque, filtro de ar/óleo, pistão, válvula e lâmpadas com tecnologia/tensão.
        semantica = cls._inferir_ncm_regra_semantica(descricao_texto)
        if semantica is not None:
            return semantica

        if assinatura_completa:
            unico = cls._ncm_unico(indice.por_descricao_completa.get(assinatura_completa))
            if unico:
                ncm, qtd = unico
                return InferenciaNCMDescricao(ncm, 95.0, f"descrição idêntica em {qtd} item(ns) do cadastro", descricao_texto)

        tokens_prefixo = cls._tokens_prefixo_familia(descricao_texto)
        if tokens_prefixo and tokens_prefixo[0] in cls.FAMILIAS_CONSENSO_BLOQUEADAS:
            # Nessas famílias, copiar por cor/modelo/marca pode ser perigoso: uma
            # palavra adicional (LED, material, pressão, tipo do rolamento etc.)
            # muda o NCM. Sem regra semântica suficiente, mantém REVISAR.
            return None

        if assinatura:
            unico = cls._ncm_unico(indice.por_assinatura.get(assinatura))
            if unico:
                ncm, qtd = unico
                referencia = indice.amostra_assinatura.get((assinatura, ncm), descricao_texto)
                confianca = 92.0 if qtd >= 2 else 90.0
                return InferenciaNCMDescricao(
                    ncm, confianca,
                    f"mesma família comercial em {qtd} item(ns) do cadastro",
                    referencia,
                )

        consenso = cls._inferir_ncm_consenso_familia(indice, descricao_texto)
        if consenso is not None:
            return consenso

        tokens_consulta = {t for t in assinatura.split() if t}
        if len(tokens_consulta) < 2:
            return None

        marca = _marca_descricao(descricao_texto)
        candidatos: List[tuple[float, str, str]] = []

        # Mesma marca recebe prioridade porque catálogos de peças costumam variar
        # apenas cor/lado/acabamento mantendo a mesma classificação fiscal.
        if marca:
            for pos in indice.por_marca.get(marca, []):
                assinatura_ref, tokens_ref, ncm, referencia, _ = indice.referencias_unicas[pos]
                score = cls._pontuar_assinaturas(assinatura, tokens_consulta, assinatura_ref, tokens_ref)
                if score >= 0.70:
                    candidatos.append((score, ncm, referencia))
            candidatos.sort(reverse=True)
            if candidatos:
                melhor = candidatos[0]
                proximos = [c for c in candidatos if c[0] >= melhor[0] - 0.03]
                if len({c[1] for c in proximos}) == 1:
                    confianca = min(90.0, 76.0 + (melhor[0] * 15.0))
                    return InferenciaNCMDescricao(
                        melhor[1], confianca,
                        f"variante semelhante da mesma marca ({marca})",
                        melhor[2],
                    )

        # Busca geral: usa os tokens mais raros para evitar comparar cada NCM
        # zerado com dezenas de milhares de itens, preservando a velocidade.
        tokens_indexados = [t for t in tokens_consulta if len(t) >= 4 and indice.por_token.get(t)]
        if len(tokens_indexados) < 2:
            return None
        tokens_indexados.sort(key=lambda t: len(indice.por_token.get(t, ())))
        conjuntos = [indice.por_token[t] for t in tokens_indexados[:3]]
        candidatos_ids = set(conjuntos[0])
        if len(conjuntos) > 1:
            inter = candidatos_ids & conjuntos[1]
            if inter:
                candidatos_ids = inter
        if len(candidatos_ids) > 500:
            candidatos_ids = set(sorted(candidatos_ids)[:500])

        candidatos = []
        for pos in candidatos_ids:
            assinatura_ref, tokens_ref, ncm, referencia, _ = indice.referencias_unicas[pos]
            score = cls._pontuar_assinaturas(assinatura, tokens_consulta, assinatura_ref, tokens_ref)
            if score >= 0.88:
                candidatos.append((score, ncm, referencia))
        candidatos.sort(reverse=True)
        if not candidatos:
            return None
        melhor = candidatos[0]
        proximos = [c for c in candidatos if c[0] >= melhor[0] - 0.02]
        if len({c[1] for c in proximos}) != 1:
            return None
        confianca = min(86.0, 78.0 + max(0.0, melhor[0] - 0.88) * 80.0)
        return InferenciaNCMDescricao(
            melhor[1], confianca,
            "descrição muito semelhante a item classificado no mesmo cadastro",
            melhor[2],
        )

    @classmethod
    def _inferir_ncm_validacao_existente(
        cls,
        indice: IndiceNCMDescricao,
        *,
        descricao: Any,
        ncm_atual: Any,
    ) -> Optional[InferenciaNCMDescricao]:
        """Procura evidência forte de que um NCM existente está fora da família.

        Diferente da inferência usada para NCM zerado, esta rotina não usa código
        nem EAN do próprio item, porque isso apenas repetiria um cadastro errado.
        Ela aceita apenas regra semântica específica ou consenso muito forte da
        mesma marca/família comercial. O retorno sempre deve ser tratado como
        REVISAR, nunca como correção automática.
        """
        atual = _ncm(ncm_atual)
        if not _ncm_valido(atual):
            return None

        semantica = cls._inferir_ncm_regra_semantica(descricao)
        if semantica is not None and semantica.ncm != atual:
            return semantica

        texto = _texto(descricao)
        tokens = cls._tokens_prefixo_familia(texto)
        marca = _marca_descricao(texto)

        def dominante(
            contador: Optional[Counter],
            *,
            minimo_total: int,
            minimo_pureza: float,
            metodo: str,
            referencia_chave: str,
        ) -> Optional[InferenciaNCMDescricao]:
            if not contador:
                return None
            total = sum(int(v) for v in contador.values())
            if total < minimo_total:
                return None
            ncm, qtd = contador.most_common(1)[0]
            pureza = float(qtd) / float(total or 1)
            if not _ncm_valido(ncm) or ncm == atual or pureza < minimo_pureza:
                return None
            referencia = indice.amostra_prefixo.get((referencia_chave, ncm), texto)
            confianca = min(94.0, 84.0 + pureza * 10.0)
            return InferenciaNCMDescricao(
                ncm=str(ncm),
                confianca=confianca,
                metodo=f"{metodo}: {qtd}/{total} referências ({pureza:.0%})",
                referencia=referencia,
            )

        # Marca + dois primeiros termos é o sinal mais útil em catálogos de
        # autopeças: cores, lados, medidas e modelos variam, mas a família tende
        # a manter a classificação. Ex.: SANFONA BENG ... (CIRCUIT).
        if marca and len(tokens) >= 2:
            chave2 = " ".join(tokens[:2])
            achado = dominante(
                indice.por_marca_prefixo2.get((marca, chave2)),
                minimo_total=5,
                minimo_pureza=0.90,
                metodo=f"consenso forte da mesma marca e família ({marca})",
                referencia_chave="M2:" + marca + ":" + chave2,
            )
            if achado is not None:
                return achado

        # Sem marca, exige um agrupamento maior e mais puro para evitar que uma
        # família comercial genérica contamine a classificação.
        if len(tokens) >= 3:
            chave3 = " ".join(tokens[:3])
            achado = dominante(
                indice.por_prefixo3.get(chave3),
                minimo_total=6,
                minimo_pureza=0.95,
                metodo="consenso forte dos três primeiros termos da descrição",
                referencia_chave="P3:" + chave3,
            )
            if achado is not None:
                return achado

        return None

    @classmethod
    def _candidatos_ncm_descricao(
        cls,
        indice: IndiceNCMDescricao,
        *,
        codigo: Any,
        codigo_barras: Any,
        descricao: Any,
        limite: int = 3,
    ) -> List[CandidatoNCMDescricao]:
        """Retorna 2–3 alternativas auditáveis quando não há um NCM único seguro.

        Esta rotina NÃO alimenta o motor tributário e NÃO transforma o melhor
        candidato em classificação automática. Ela serve para a revisão humana,
        principalmente nas famílias bloqueadas (capa, cabo, lâmpada, rolamento,
        junta, mangueira etc.), usando somente evidência já existente no cadastro.
        """
        limite = max(1, min(int(limite or 3), 5))
        if cls._detectar_servico(descricao, codigo):
            return []
        codigo_norm = _normalizar_texto(codigo)
        ean = _digitos(codigo_barras)
        descricao_texto = _texto(descricao)
        assinatura_completa = _assinatura_descricao_completa(descricao_texto)
        assinatura = _assinatura_familia_descricao(descricao_texto)
        tokens_consulta = {t for t in assinatura.split() if t}
        marca = _marca_descricao(descricao_texto)

        melhores: Dict[str, CandidatoNCMDescricao] = {}

        def adicionar(ncm: Any, confianca: float, metodo: str, referencia: str, ocorrencias: int = 0) -> None:
            ncm_limpo = _ncm(ncm)
            if not _ncm_valido(ncm_limpo):
                return
            cand = CandidatoNCMDescricao(
                ncm=ncm_limpo,
                confianca=max(0.0, min(99.0, float(confianca))),
                metodo=str(metodo or "").strip(),
                referencia=str(referencia or descricao_texto).strip(),
                ocorrencias=max(0, int(ocorrencias or 0)),
            )
            atual = melhores.get(ncm_limpo)
            if atual is None or (cand.confianca, cand.ocorrencias) > (atual.confianca, atual.ocorrencias):
                melhores[ncm_limpo] = cand

        def adicionar_counter(counter: Optional[Counter], confianca: float, metodo: str, referencia: str) -> None:
            if not counter:
                return
            total = sum(int(v) for v in counter.values()) or 1
            for ncm, qtd in counter.most_common(4):
                pureza = float(qtd) / float(total)
                # Quando o mesmo agrupamento aponta para vários NCMs, a confiança
                # acompanha a frequência sem esconder a ambiguidade.
                conf = min(confianca, max(62.0, confianca - (1.0 - pureza) * 22.0))
                adicionar(ncm, conf, metodo, referencia, int(qtd))

        if codigo_norm:
            adicionar_counter(
                indice.por_codigo.get(codigo_norm), 97.0,
                "mesmo código com mais de uma classificação no cadastro", codigo_norm,
            )
        if ean:
            adicionar_counter(
                indice.por_ean.get(ean), 97.0,
                "mesmo EAN com mais de uma classificação no cadastro", ean,
            )
        if assinatura_completa:
            adicionar_counter(
                indice.por_descricao_completa.get(assinatura_completa), 95.0,
                "descrição idêntica com classificações diferentes", descricao_texto,
            )
        if assinatura:
            adicionar_counter(
                indice.por_assinatura.get(assinatura), 91.0,
                "mesma família comercial no cadastro", descricao_texto,
            )

        tokens_prefixo = cls._tokens_prefixo_familia(descricao_texto)
        if marca and len(tokens_prefixo) >= 2:
            chave2 = " ".join(tokens_prefixo[:2])
            adicionar_counter(
                indice.por_marca_prefixo2.get((marca, chave2)), 88.0,
                f"mesma marca e família ({marca})", descricao_texto,
            )
        if len(tokens_prefixo) >= 3:
            chave3 = " ".join(tokens_prefixo[:3])
            adicionar_counter(
                indice.por_prefixo3.get(chave3), 85.0,
                "mesmos três termos iniciais no cadastro", descricao_texto,
            )
        if len(tokens_prefixo) >= 2:
            chave2 = " ".join(tokens_prefixo[:2])
            adicionar_counter(
                indice.por_prefixo2.get(chave2), 82.0,
                "mesma família de dois termos no cadastro", descricao_texto,
            )

        # Similaridade: mesmo nas famílias bloqueadas, pode mostrar alternativas,
        # mas nunca escolhe automaticamente uma delas.
        if len(tokens_consulta) >= 2:
            posicoes: set[int] = set()
            if marca:
                posicoes.update(indice.por_marca.get(marca, []))
            tokens_indexados = [t for t in tokens_consulta if len(t) >= 4 and indice.por_token.get(t)]
            tokens_indexados.sort(key=lambda t: len(indice.por_token.get(t, ())))
            for token in tokens_indexados[:3]:
                refs = indice.por_token.get(token, set())
                if not posicoes:
                    posicoes.update(refs)
                else:
                    inter = posicoes & refs
                    if inter:
                        posicoes = inter
            if len(posicoes) > 700:
                posicoes = set(sorted(posicoes)[:700])

            por_ncm: Dict[str, tuple[float, str, int]] = {}
            for pos in posicoes:
                assinatura_ref, tokens_ref, ncm, referencia, marca_ref = indice.referencias_unicas[pos]
                score = cls._pontuar_assinaturas(assinatura, tokens_consulta, assinatura_ref, tokens_ref)
                minimo = 0.68 if marca and marca_ref == marca else 0.74
                if score < minimo:
                    continue
                atual = por_ncm.get(ncm)
                qtd = 1 if atual is None else atual[2] + 1
                melhor_score = score if atual is None else max(score, atual[0])
                melhor_ref = referencia if atual is None or score >= atual[0] else atual[1]
                por_ncm[ncm] = (melhor_score, melhor_ref, qtd)
            for ncm, (score, referencia, qtd) in por_ncm.items():
                conf = 70.0 + min(18.0, max(0.0, score - 0.68) * 55.0)
                if marca:
                    conf += 2.0
                adicionar(
                    ncm, min(89.0, conf),
                    "descrição semelhante a produtos já classificados", referencia, qtd,
                )

        ordenados = sorted(
            melhores.values(),
            key=lambda c: (c.confianca, c.ocorrencias, c.ncm),
            reverse=True,
        )
        if not ordenados:
            return []

        # Famílias deliberadamente bloqueadas para classificação automática são
        # justamente as que mais se beneficiam de 2–3 alternativas. Nelas mantém
        # candidatos secundários com evidência razoável, sem eleger um vencedor.
        primeiro_token = tokens_prefixo[0] if tokens_prefixo else ""
        if primeiro_token in cls.FAMILIAS_CONSENSO_BLOQUEADAS:
            selecionados = [c for c in ordenados if c.confianca >= 62.0][:limite]
        else:
            # Nas demais famílias, corta opções muito distantes para não poluir a revisão.
            piso = max(68.0, ordenados[0].confianca - 14.0)
            selecionados = [c for c in ordenados if c.confianca >= piso][:limite]
        return selecionados

    @staticmethod
    def _texto_candidatos_ncm(candidatos: Iterable[CandidatoNCMDescricao]) -> str:
        return " | ".join(c.resumo for c in candidatos)

    @classmethod
    def analisar(
        cls,
        arquivo: str | Path,
        contexto: Optional[Dict[str, Any]] = None,
        progresso: Optional[Callable[[int, int, str], None]] = None,
    ) -> ResultadoAuditoriaExcel:
        try:
            from openpyxl import load_workbook
        except ImportError as erro:  # pragma: no cover
            raise RuntimeError("Instale o pacote openpyxl para auditar planilhas Excel.") from erro

        caminho = Path(arquivo)
        if not caminho.is_file() or caminho.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise ValueError("Selecione uma planilha Excel .xlsx ou .xlsm válida.")

        wb = load_workbook(caminho, read_only=True, data_only=True)
        try:
            ws = cls._escolher_aba(wb)
            cabecalhos = cls._mapear_cabecalhos(ws)
            faltantes = [campo for campo in ("codigo", "descricao", "ncm") if campo not in cabecalhos]
            if faltantes:
                nomes = {
                    "codigo": "Código",
                    "descricao": "Descrição",
                    "ncm": "NCM",
                }
                faltantes_legiveis = ", ".join(nomes.get(campo, campo) for campo in faltantes)
                raise ValueError(
                    "Não consegui reconhecer a estrutura desta planilha. "
                    "O FiscalPro aceita também colunas como Código/Cód. Produto, "
                    "Descrição e NCM/NCM atual/Cód. NCM. "
                    f"Não localizadas: {faltantes_legiveis}."
                )

            contexto_final = {
                "regime": "Lucro Real",
                "operacao": "Venda",
                "finalidade": "Revenda",
                "uf_origem": "MG",
                "uf_destino": "MG",
                "data_operacao": date.today().isoformat(),
                "consumidor_final": False,
            }
            contexto_final.update(contexto or {})
            contexto_final = EmpresasRegimesService.aplicar_contexto(contexto_final)
            motor = AnaliseTributariaLoteService()
            resultado = ResultadoAuditoriaExcel(
                arquivo=str(caminho.resolve()),
                planilha=ws.title,
                contexto=dict(contexto_final),
            )
            total = max(0, (ws.max_row or 1) - 1)
            formatos_percentuais = cls._detectar_formatos_percentuais(ws, cabecalhos)
            indice_ncm_descricao = cls._construir_indice_ncm_descricao(ws, cabecalhos)

            # Leitura rápida: valores puros, sem materializar objetos/estilos de
            # cada célula em todas as linhas. Em bases grandes faz diferença.
            for indice, linha in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                codigo = cls._valor(linha, cabecalhos, "codigo")
                descricao = cls._valor(linha, cabecalhos, "descricao")
                ncm_atual = _ncm(cls._valor(linha, cabecalhos, "ncm"))
                cest_atual = _cest(cls._valor(linha, cabecalhos, "cest"))
                codigo_barras_atual = _texto(cls._valor(linha, cabecalhos, "codigo_barras"))
                if not any((_texto(codigo), _texto(descricao), ncm_atual, cest_atual)):
                    continue

                inferencia_ncm: Optional[InferenciaNCMDescricao] = None
                candidatos_ncm: List[CandidatoNCMDescricao] = []
                ncm_para_motor = ncm_atual
                deteccao_servico = cls._detectar_servico(descricao, codigo) if not _ncm_valido(ncm_atual) else None
                if not _ncm_valido(ncm_atual) and not deteccao_servico:
                    inferencia_ncm = cls._inferir_ncm_descricao(
                        indice_ncm_descricao,
                        codigo=codigo,
                        codigo_barras=codigo_barras_atual,
                        descricao=descricao,
                    )
                    if inferencia_ncm is not None:
                        ncm_para_motor = inferencia_ncm.ncm
                    else:
                        candidatos_ncm = cls._candidatos_ncm_descricao(
                            indice_ncm_descricao,
                            codigo=codigo,
                            codigo_barras=codigo_barras_atual,
                            descricao=descricao,
                            limite=3,
                        )
                elif _ncm_valido(ncm_atual):
                    # 18.2.1 — um NCM com oito dígitos não é necessariamente um
                    # NCM coerente. Antes a auditoria tratava qualquer código
                    # formalmente válido como verdade e, por isso, repetia
                    # perfumes/vegetais em peças de motocicleta sem alertar.
                    inferencia_ncm = cls._inferir_ncm_validacao_existente(
                        indice_ncm_descricao,
                        descricao=descricao,
                        ncm_atual=ncm_atual,
                    )
                    if inferencia_ncm is not None and inferencia_ncm.ncm != ncm_atual:
                        ncm_para_motor = inferencia_ncm.ncm

                cst_compartilhado = _codigo_fiscal(cls._valor(linha, cabecalhos, "cst_piscofins"), 2)
                cst_pis = _codigo_fiscal(cls._valor(linha, cabecalhos, "cst_pis"), 2) or cst_compartilhado
                cst_cofins = _codigo_fiscal(cls._valor(linha, cabecalhos, "cst_cofins"), 2) or cst_compartilhado

                originais = {
                    "ncm_original": ncm_atual,
                    "inferencia_ncm": inferencia_ncm,
                    "candidatos_ncm": candidatos_ncm,
                    "deteccao_servico": deteccao_servico,
                    "codigo_barras": codigo_barras_atual,
                    "ex_tipi": _texto(cls._valor(linha, cabecalhos, "ex_tipi")),
                    "cst_icms": _codigo_fiscal(cls._valor(linha, cabecalhos, "cst_icms"), 3),
                    "cfop": _texto(cls._valor(linha, cabecalhos, "cfop")),
                    "icms_desonerado": _sim_nao(cls._valor(linha, cabecalhos, "icms_desonerado")),
                    "red_bc_icms": _percentual_valor(cls._valor(linha, cabecalhos, "red_bc_icms"), formatos_percentuais.get("red_bc_icms", False)),
                    "aliq_icms": _percentual_valor(cls._valor(linha, cabecalhos, "aliq_icms"), formatos_percentuais.get("aliq_icms", False)),
                    "icms_st_indicador": _sim_nao(cls._valor(linha, cabecalhos, "icms_st_indicador")),
                    "mva_st": _percentual_valor(cls._valor(linha, cabecalhos, "mva_st"), formatos_percentuais.get("mva_st", False)),
                    "red_bc_st": _percentual_valor(cls._valor(linha, cabecalhos, "red_bc_st"), formatos_percentuais.get("red_bc_st", False)),
                    "aliq_icms_st": _percentual_valor(cls._valor(linha, cabecalhos, "aliq_icms_st"), formatos_percentuais.get("aliq_icms_st", False)),
                    "aliq_fem": _percentual_valor(cls._valor(linha, cabecalhos, "aliq_fem"), formatos_percentuais.get("aliq_fem", False)),
                    "nat_receita": _texto(cls._valor(linha, cabecalhos, "nat_receita")),
                }

                if deteccao_servico:
                    motivo_servico, confianca_servico = deteccao_servico
                    item_saida = cls._item_servico(
                        linha_excel=indice,
                        codigo=codigo,
                        descricao=descricao,
                        ncm_atual=ncm_atual,
                        cest_atual=cest_atual,
                        motivo=motivo_servico,
                        confianca=confianca_servico,
                        originais=originais,
                        cst_pis=cst_pis,
                        cst_cofins=cst_cofins,
                        aliq_pis=_percentual_valor(cls._valor(linha, cabecalhos, "aliq_pis"), formatos_percentuais.get("aliq_pis", False)),
                        aliq_cofins=_percentual_valor(cls._valor(linha, cabecalhos, "aliq_cofins"), formatos_percentuais.get("aliq_cofins", False)),
                        cst_ipi=_codigo_fiscal(cls._valor(linha, cabecalhos, "cst_ipi"), 2),
                        aliq_ipi=_percentual_valor(cls._valor(linha, cabecalhos, "aliq_ipi"), formatos_percentuais.get("aliq_ipi", False)),
                    )
                    resultado.itens.append(item_saida)
                    if progresso and (indice % 250 == 0 or indice == total + 1):
                        progresso(indice - 1, total, item_saida.descricao)
                    continue

                bruto = ItemBrutoLote(
                    fonte_tipo="CADASTRO EXCEL",
                    arquivo=caminho.name,
                    documento=ws.title,
                    numero_item=str(indice - 1),
                    codigo=_texto(codigo),
                    descricao=_texto(descricao),
                    ncm=ncm_para_motor,
                    ex_tipi=originais["ex_tipi"],
                    cest_atual=cest_atual,
                    cfop=originais["cfop"],
                    uf_origem=str(contexto_final.get("uf_origem") or "MG").upper(),
                    uf_destino=str(contexto_final.get("uf_destino") or "MG").upper(),
                    data_operacao=str(contexto_final.get("data_operacao") or date.today().isoformat()),
                    operacao_sugerida=str(contexto_final.get("operacao") or "Venda"),
                    cst_icms_atual=originais["cst_icms"],
                    aliquota_icms_atual=originais["aliq_icms"],
                    mva_st_atual=originais["mva_st"],
                    aliquota_fcp_st_atual=originais["aliq_fem"],
                    cst_pis_atual=cst_pis,
                    aliquota_pis_atual=_percentual_valor(cls._valor(linha, cabecalhos, "aliq_pis"), formatos_percentuais.get("aliq_pis", False)),
                    cst_cofins_atual=cst_cofins,
                    aliquota_cofins_atual=_percentual_valor(cls._valor(linha, cabecalhos, "aliq_cofins"), formatos_percentuais.get("aliq_cofins", False)),
                    cst_ipi_atual=_codigo_fiscal(cls._valor(linha, cabecalhos, "cst_ipi"), 2),
                    aliquota_ipi_atual=_percentual_valor(cls._valor(linha, cabecalhos, "aliq_ipi"), formatos_percentuais.get("aliq_ipi", False)),
                    numero_linha_fonte=indice,
                )
                try:
                    analise = motor.analisar_item(bruto, contexto_final)
                    item_saida = cls._converter(bruto, analise, indice, originais, contexto_final)
                except Exception as erro:
                    item_saida = ItemAuditoriaExcel(
                        linha_excel=indice,
                        codigo=bruto.codigo,
                        descricao=bruto.descricao,
                        ncm_atual=ncm_atual,
                        cest_atual=_formatar_cest(cest_atual),
                        ncm_sugerido=(inferencia_ncm.ncm if inferencia_ncm else ncm_atual),
                        ncm_candidatos=cls._texto_candidatos_ncm(candidatos_ncm),
                        cest_sugerido="",
                        status=STATUS_REVISAR,
                        problema=f"Falha na análise: {erro}",
                        correcao_sugerida="Revisar manualmente este item.",
                        seguranca=0.0,
                        codigo_barras=originais["codigo_barras"],
                        ex_tipi=originais["ex_tipi"],
                        cst_icms_atual=originais["cst_icms"],
                        cfop_atual=originais["cfop"],
                        icms_desonerado_atual=originais["icms_desonerado"],
                        reducao_bc_icms_atual=originais["red_bc_icms"],
                        aliquota_icms_atual=originais["aliq_icms"],
                        icms_st_atual=originais["icms_st_indicador"],
                        mva_icms_st_atual=originais["mva_st"],
                        reducao_bc_icms_st_atual=originais["red_bc_st"],
                        aliquota_icms_st_atual=originais["aliq_icms_st"],
                        aliquota_fem_atual=originais["aliq_fem"],
                        nat_receita_atual=originais["nat_receita"],
                    )
                resultado.itens.append(item_saida)
                if progresso and (indice % 250 == 0 or indice == total + 1):
                    progresso(indice - 1, total, item_saida.descricao)

            cls._marcar_codigos_inconsistentes(resultado.itens)
            return resultado
        finally:
            wb.close()

    @classmethod
    def _escolher_aba(cls, wb):
        for nome in wb.sheetnames:
            ws = wb[nome]
            try:
                mapa = cls._mapear_cabecalhos(ws)
            except Exception:
                continue
            if {"codigo", "descricao", "ncm"}.issubset(mapa):
                return ws
        return wb[wb.sheetnames[0]]

    @classmethod
    def _mapear_cabecalhos(cls, ws) -> Dict[str, int]:
        primeira = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        mapa: Dict[str, int] = {}
        inverso = {
            alias: campo
            for campo, aliases in cls.ALIASES.items()
            for alias in aliases
        }
        for idx, valor in enumerate(primeira):
            chave = _chave_cabecalho(valor)
            campo = inverso.get(chave)
            if campo and campo not in mapa:
                mapa[campo] = idx
        return mapa

    @staticmethod
    def _valor(linha: Iterable[Any], cabecalhos: Dict[str, int], campo: str) -> Any:
        idx = cabecalhos.get(campo)
        if idx is None:
            return ""
        valores = list(linha) if not isinstance(linha, tuple) else linha
        return valores[idx] if idx < len(valores) else ""

    @staticmethod
    def _st_referencia(analise: ResultadoItemLote) -> str:
        if bool(analise.st_confirmado):
            return "SIM"
        texto = _normalizar_texto(f"{analise.icms_status} {analise.st_status} {analise.observacao}")
        marcadores_nao = (
            "ST NAO APLICAVEL",
            "ICMS ST NAO APLICAVEL",
            "ICMS ST MG NAO",
            "SEM RESPONSABILIDADE DE ST",
            "NAO INCIDE NA REGRA ESTADUAL",
            "NAO SUJEITO A ST",
        )
        if any(marcador in texto for marcador in marcadores_nao):
            return "NÃO"
        return "REVISAR"

    @classmethod
    def _converter(
        cls,
        bruto: ItemBrutoLote,
        analise: ResultadoItemLote,
        linha_excel: int,
        originais: Optional[Dict[str, Any]] = None,
        contexto: Optional[Dict[str, Any]] = None,
    ) -> ItemAuditoriaExcel:
        originais = dict(originais or {})
        contexto = dict(contexto or {})
        divergencias = list(dict.fromkeys(analise.divergencias or []))
        pendencias = list(dict.fromkeys(analise.pendencias or []))
        ncm_original = (
            _ncm(originais.get("ncm_original"))
            if "ncm_original" in originais
            else bruto.ncm
        )
        inferencia_ncm = originais.get("inferencia_ncm")
        candidatos_ncm = list(originais.get("candidatos_ncm") or [])
        ncm_sugerido = bruto.ncm
        cest_sugerido = analise.cest_esperado or bruto.cest_atual
        sugestoes: List[str] = []

        # 18.1.8 — quando o cadastro traz NCM zerado/ausente, o motor pode ser
        # recalculado com um candidato aprendido no próprio cadastro. A linha
        # continua mostrando o NCM original e deixa explícito como a sugestão
        # foi obtida; similaridade nunca é apresentada como classificação legal
        # definitivamente confirmada.
        avisos_candidatos = ""
        if isinstance(inferencia_ncm, InferenciaNCMDescricao):
            ncm_sugerido = inferencia_ncm.ncm
            if _ncm_valido(ncm_original):
                evidencia = (
                    f"NCM atual {ncm_original} é formalmente válido, mas diverge da evidência "
                    f"da descrição/família. Sugestão {inferencia_ncm.ncm} por "
                    f"{inferencia_ncm.metodo}; referência: '{inferencia_ncm.referencia}'."
                )
            else:
                evidencia = (
                    f"NCM atual {ncm_original or '-'} está zerado/ausente. "
                    f"Sugestão {inferencia_ncm.ncm} por {inferencia_ncm.metodo}; "
                    f"referência do cadastro: '{inferencia_ncm.referencia}'."
                )
            # A sugestão por descrição/família precisa de validação humana antes
            # de virar correção definitiva. Por isso permanece como REVISAR.
            pendencias.insert(0, evidencia)
            sugestoes.append(
                f"Validar o NCM {inferencia_ncm.ncm}. A tributação exibida foi recalculada "
                f"provisoriamente com esse NCM (confiança da inferência {inferencia_ncm.confianca:.0f}%)."
            )
        elif candidatos_ncm and not _ncm_valido(ncm_original):
            texto_candidatos = cls._texto_candidatos_ncm(candidatos_ncm)
            detalhes = "; ".join(
                f"{c.ncm}: {c.metodo} — ref. '{c.referencia}'"
                for c in candidatos_ncm
            )
            pendencias.insert(
                0,
                f"NCM atual {ncm_original or '-'} está zerado/ausente. "
                f"Há candidatos para revisão, mas nenhum é seguro o bastante para uso automático: {texto_candidatos}."
            )
            sugestoes.append(
                "Escolher o NCM somente após confirmar material, função e aplicação real da peça. "
                f"Candidatos do cadastro: {texto_candidatos}."
            )
            avisos_candidatos = f"Evidências dos candidatos NCM: {detalhes}"
        else:
            avisos_candidatos = ""

        # Mesmo quando o motor mantém PIS/Cofins como sugestão condicional, a auditoria
        # mostra de forma objetiva a diferença entre o cadastro atual e a referência.
        if analise.cst_pis_esperado and analise.cst_pis_atual and analise.cst_pis_atual != analise.cst_pis_esperado:
            pendencias.append(
                f"PIS: CST atual {analise.cst_pis_atual} ≠ referência/sugestão {analise.cst_pis_esperado}."
            )
        if analise.cst_cofins_esperado and analise.cst_cofins_atual and analise.cst_cofins_atual != analise.cst_cofins_esperado:
            pendencias.append(
                f"COFINS: CST atual {analise.cst_cofins_atual} ≠ referência/sugestão {analise.cst_cofins_esperado}."
            )
        if analise.cest_esperado and _cest(bruto.cest_atual) != _cest(analise.cest_esperado):
            mensagem_cest = (
                f"CEST atual {_formatar_cest(bruto.cest_atual) or '-'} ≠ referência {_formatar_cest(analise.cest_esperado)}."
            )
            if analise.st_confirmado:
                if mensagem_cest not in divergencias:
                    divergencias.append(mensagem_cest)
            elif mensagem_cest not in pendencias:
                pendencias.append(mensagem_cest)

        # Heurística semântica deliberadamente conservadora: não altera o cadastro.
        descricao_norm = _normalizar_texto(bruto.descricao)
        if "RETENTOR" in descricao_norm and bruto.ncm != "40169300":
            ncm_sugerido = "40169300"
            cest_sugerido = "0100700"
            pendencias.insert(
                0,
                "Descrição contém 'RETENTOR', mas o NCM não é 40169300 (elementos de vedação). Confirmar material e função da peça.",
            )
            sugestoes.append(
                "Conferir enquadramento em NCM 40169300 e, para autopeça sujeita à ST/MG, CEST 01.007.00; não corrigir sem confirmar a composição/função."
            )

        # Se o NCM foi inferido pela descrição, toda divergência tributária
        # calculada a partir desse candidato permanece provisória até o usuário
        # validar a classificação. Assim a ficha pode mostrar ST/CEST/PIS/IPI
        # sugeridos sem afirmar uma correção fiscal definitiva baseada em um
        # NCM ainda não confirmado.
        if isinstance(inferencia_ncm, InferenciaNCMDescricao) and divergencias:
            for texto in list(dict.fromkeys(divergencias)):
                pendencias.append(f"Com o NCM sugerido {inferencia_ncm.ncm}: {texto}")
            divergencias = []

        # Distingue pendência real de mensagem de cautela genérica do motor.
        # Os avisos informativos continuam rastreáveis na observação, porém não
        # impedem um item objetivamente coerente de receber status OK.
        pendencias_bloqueantes, avisos_informativos = cls._separar_pendencias(analise, pendencias)
        divergencias = list(dict.fromkeys(divergencias))

        campos_operacionais = cls._sugerir_campos_operacionais(
            bruto, analise, contexto, originais, pendencias
        )

        # 18.1.7 — coerência entre o status da linha e os campos operacionais
        # exibidos na Ficha Tributária. Um item não pode aparecer como OK se
        # CST ICMS/CFOP (ou outro campo operacional essencial que o próprio
        # FiscalPro marcou como REVISAR) ainda estiver em aberto.
        pendencias_operacionais: List[str] = []
        cst_icms_final = str(originais.get("cst_icms") or campos_operacionais.get("cst_icms") or "").strip()
        cfop_final = str(originais.get("cfop") or bruto.cfop or campos_operacionais.get("cfop") or "").strip()
        desonerado_final = str(originais.get("icms_desonerado") or campos_operacionais.get("icms_desonerado") or "").strip()
        nat_receita_final = str(originais.get("nat_receita") or campos_operacionais.get("nat_receita") or "").strip()

        if _normalizar_texto(cst_icms_final) == "REVISAR":
            pendencias_operacionais.append(
                "CST ICMS ainda depende da definição da responsabilidade tributária da operação."
            )
        if _normalizar_texto(cfop_final) == "REVISAR":
            pendencias_operacionais.append(
                "CFOP de saída ainda depende da definição da responsabilidade tributária da operação."
            )
        if _normalizar_texto(desonerado_final) == "REVISAR":
            pendencias_operacionais.append(
                "ICMS desonerado ainda precisa de confirmação quanto a benefício, isenção, diferimento ou redução."
            )

        csts_saida = {
            str(analise.cst_pis_esperado or "").strip(),
            str(analise.cst_cofins_esperado or "").strip(),
        } - {""}
        if csts_saida.intersection({"04", "05", "06", "07", "08", "09"}):
            if not nat_receita_final or _normalizar_texto(nat_receita_final) == "REVISAR":
                pendencias_operacionais.append(
                    "Natureza da receita PIS/COFINS precisa ser definida para a tributação não padrão indicada."
                )

        for texto in pendencias_operacionais:
            if texto not in pendencias_bloqueantes:
                pendencias_bloqueantes.append(texto)

        # CST IPI não é inferido somente pela TIPI: depende da condição do
        # estabelecimento (industrial/equiparado). Isso é uma limitação de
        # contexto, não um erro do produto, por isso permanece como aviso.
        if not str(originais.get("cst_ipi") or bruto.cst_ipi_atual or "").strip():
            aviso_ipi = (
                "CST IPI não inferido automaticamente: confirmar se o estabelecimento "
                "é industrial/equiparado antes de definir o código de saída."
            )
            if aviso_ipi not in avisos_informativos:
                avisos_informativos.append(aviso_ipi)

        if divergencias:
            sugestoes.append("Corrigir os campos divergentes após conferir a base legal indicada pelo FiscalPro.")
        if pendencias_bloqueantes and not sugestoes:
            sugestoes.append("Revisar os pontos específicos indicados antes de alterar o cadastro do ERP.")
        if not divergencias and not pendencias_bloqueantes:
            sugestoes.append("Nenhuma divergência objetiva foi encontrada para o contexto informado.")

        if divergencias:
            status = STATUS_CORRIGIR
        elif pendencias_bloqueantes:
            status = STATUS_REVISAR
        else:
            status = STATUS_OK

        # A sugestão semântica nunca eleva artificialmente a segurança oficial.
        seguranca = float(analise.confiabilidade or 0.0)
        if isinstance(inferencia_ncm, InferenciaNCMDescricao):
            seguranca = min(seguranca if seguranca > 0 else inferencia_ncm.confianca, inferencia_ncm.confianca)
        if "RETENTOR" in descricao_norm and bruto.ncm != "40169300":
            seguranca = min(seguranca if seguranca > 0 else 85.0, 85.0)

        problema = " | ".join(divergencias + pendencias_bloqueantes) or "Nenhuma divergência objetiva encontrada."
        observacao_partes = [str(analise.observacao or "").strip()]
        if isinstance(inferencia_ncm, InferenciaNCMDescricao):
            observacao_partes.append(
                f"NCM sugerido por descrição: {inferencia_ncm.ncm} ({inferencia_ncm.metodo}; "
                f"confiança {inferencia_ncm.confianca:.0f}%). A tributação de referência desta linha "
                "foi simulada com o NCM sugerido e deve ser validada antes de alterar o ERP."
            )
        if avisos_candidatos:
            observacao_partes.append(avisos_candidatos)
        if avisos_informativos:
            observacao_partes.append(
                "Alertas informativos (não alteram o status): " + " | ".join(avisos_informativos)
            )
        observacao_final = " ".join(parte for parte in observacao_partes if parte)

        mva_ref = (
            analise.mva_aplicada
            if analise.mva_aplicada is not None
            else (
                analise.mva_ajustada
                if analise.mva_ajustada is not None
                else analise.mva_original
            )
        )
        return ItemAuditoriaExcel(
            linha_excel=linha_excel,
            codigo=bruto.codigo,
            descricao=bruto.descricao,
            ncm_atual=ncm_original,
            cest_atual=_formatar_cest(bruto.cest_atual),
            ncm_sugerido=ncm_sugerido,
            ncm_candidatos=cls._texto_candidatos_ncm(candidatos_ncm),
            cest_sugerido=_formatar_cest(cest_sugerido),
            status=status,
            problema=problema,
            correcao_sugerida=" ".join(sugestoes),
            seguranca=seguranca,
            cst_pis_atual=analise.cst_pis_atual,
            cst_pis_referencia=analise.cst_pis_esperado,
            pis_atual=analise.aliquota_pis_atual,
            pis_referencia=analise.aliquota_pis_esperada,
            cst_cofins_atual=analise.cst_cofins_atual,
            cst_cofins_referencia=analise.cst_cofins_esperado,
            cofins_atual=analise.aliquota_cofins_atual,
            cofins_referencia=analise.aliquota_cofins_esperada,
            cst_ipi_atual=analise.cst_ipi_atual,
            ipi_atual=analise.aliquota_ipi_atual,
            ipi_referencia=analise.aliquota_ipi_referencia,
            divergencias=divergencias,
            pendencias=pendencias_bloqueantes,
            observacao=observacao_final,
            avisos_informativos=avisos_informativos,
            codigo_barras=str(originais.get("codigo_barras") or ""),
            ex_tipi=str(originais.get("ex_tipi") or ""),
            cst_icms_atual=str(originais.get("cst_icms") or analise.cst_icms_atual or ""),
            cfop_atual=str(originais.get("cfop") or bruto.cfop or ""),
            icms_desonerado_atual=str(originais.get("icms_desonerado") or ""),
            reducao_bc_icms_atual=float(originais.get("red_bc_icms") or 0.0),
            aliquota_icms_atual=float(originais.get("aliq_icms") or analise.aliquota_icms_atual or 0.0),
            icms_st_atual=str(originais.get("icms_st_indicador") or ""),
            mva_icms_st_atual=float(originais.get("mva_st") or analise.mva_st_atual or 0.0),
            reducao_bc_icms_st_atual=float(originais.get("red_bc_st") or 0.0),
            aliquota_icms_st_atual=float(originais.get("aliq_icms_st") or 0.0),
            aliquota_fem_atual=float(originais.get("aliq_fem") or analise.aliquota_fcp_st_atual or 0.0),
            nat_receita_atual=str(originais.get("nat_receita") or ""),
            cst_icms_sugerido=campos_operacionais["cst_icms"],
            cfop_sugerido=campos_operacionais["cfop"],
            icms_desonerado_sugerido=campos_operacionais["icms_desonerado"],
            cst_ipi_sugerido=campos_operacionais["cst_ipi"],
            nat_receita_sugerida=campos_operacionais["nat_receita"],
            aliquota_icms_referencia=analise.aliquota_icms_esperada,
            st_referencia=cls._st_referencia(analise),
            mva_referencia=mva_ref,
            fem_referencia=analise.fcp_esperado,
            fundamento_icms=analise.fundamento_icms,
            fundamento_piscofins=analise.fundamento_piscofins,
            fonte_icms=analise.fonte_icms,
            fonte_piscofins=analise.fonte_piscofins,
        )

    @staticmethod
    def _marcar_codigos_inconsistentes(itens: List[ItemAuditoriaExcel]) -> None:
        por_codigo: Dict[str, List[ItemAuditoriaExcel]] = {}
        for item in itens:
            chave = _normalizar_texto(item.codigo)
            if chave:
                por_codigo.setdefault(chave, []).append(item)
        for grupo in por_codigo.values():
            ncms = {i.ncm_atual for i in grupo if i.ncm_atual}
            cests = {_cest(i.cest_atual) for i in grupo if _cest(i.cest_atual)}
            if len(ncms) <= 1 and len(cests) <= 1:
                continue
            aviso = "Mesmo código aparece no Excel com NCM/CEST diferentes; revisar o cadastro antes de importar correções."
            for item in grupo:
                if aviso not in item.pendencias:
                    item.pendencias.append(aviso)
                    item.problema = f"{item.problema} | {aviso}" if item.problema else aviso
                if item.status == STATUS_OK:
                    item.status = STATUS_REVISAR
                item.seguranca = min(item.seguranca, 70.0) if item.seguranca else 70.0


class ExportadorAuditoriaCadastrosExcelXLSX:
    """Exporta a auditoria em XLSX com foco em grandes volumes.

    Hotfix 17.8.11:
    - usa Workbook(write_only=True), reduzindo memória e custo de serialização;
    - usa formatação condicional para colorir as linhas por status, em vez de
      aplicar estilo célula a célula;
    - aceita exportação somente de CORRIGIR/REVISAR;
    - informa progresso para a interface sem bloquear a janela.
    """

    HEADERS = [
        "Status", "Linha Excel", "Código", "Descrição", "NCM atual", "CEST atual",
        "NCM sugerido", "NCM candidatos", "CEST sugerido", "PIS atual", "PIS referência",
        "COFINS atual", "COFINS referência", "IPI atual %", "IPI TIPI ref. %",
        "Segurança %", "Problema encontrado", "Correção sugerida", "Observação FiscalPro",
    ]
    LARGURAS = [12, 11, 18, 48, 12, 14, 13, 34, 14, 20, 20, 22, 22, 12, 14, 12, 70, 70, 60]

    @classmethod
    def exportar(
        cls,
        resultado: ResultadoAuditoriaExcel,
        destino: str | Path,
        *,
        somente_pendencias: bool = False,
        progresso: Optional[Callable[[int, int, str], None]] = None,
    ) -> str:
        try:
            from openpyxl import Workbook
            from openpyxl.cell import WriteOnlyCell
            from openpyxl.formatting.rule import FormulaRule
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError as erro:  # pragma: no cover
            raise RuntimeError("Instale o pacote openpyxl para exportar o relatório.") from erro

        caminho = Path(destino)
        caminho.parent.mkdir(parents=True, exist_ok=True)

        if somente_pendencias:
            status_pendentes = {STATUS_CORRIGIR, STATUS_REVISAR}
            total = sum(1 for item in resultado.itens if item.status in status_pendentes)
            itens = (item for item in resultado.itens if item.status in status_pendentes)
        else:
            total = len(resultado.itens)
            itens = iter(resultado.itens)

        if total <= 0:
            raise ValueError("Não há itens para exportar neste modo.")

        # write_only evita manter centenas de milhares de células em memória.
        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Auditoria do cadastro")
        ws.freeze_panes = "A2"

        for idx, largura in enumerate(cls.LARGURAS, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = largura

        # Apenas o cabeçalho recebe estilo direto (18 células).
        fill_cab = PatternFill("solid", fgColor="1F4E78")
        fonte_cab = Font(bold=True, color="FFFFFF")
        alinh_cab = Alignment(vertical="center", horizontal="center", wrap_text=True)
        cabecalho = []
        for valor in cls.HEADERS:
            cel = WriteOnlyCell(ws, value=valor)
            cel.font = fonte_cab
            cel.fill = fill_cab
            cel.alignment = alinh_cab
            cabecalho.append(cel)
        ws.append(cabecalho)

        for indice, item in enumerate(itens, start=1):
            ws.append([
                item.status, item.linha_excel, item.codigo, item.descricao, item.ncm_atual,
                item.cest_atual, item.ncm_sugerido, item.ncm_candidatos, item.cest_sugerido,
                item.pis_atual_texto, item.pis_referencia_texto,
                item.cofins_atual_texto, item.cofins_referencia_texto,
                item.ipi_atual if item.ipi_atual else None,
                item.ipi_referencia,
                item.seguranca, item.problema, item.correcao_sugerida, item.observacao,
            ])
            if progresso and (indice % 500 == 0 or indice == total):
                progresso(indice, total, item.descricao or item.codigo or "")

        ultima_linha = total + 1
        ultima_coluna = get_column_letter(len(cls.HEADERS))
        ws.auto_filter.ref = f"A1:{ultima_coluna}{ultima_linha}"

        # Mantém as cores verde/amarelo/vermelho em toda a linha, mas com apenas
        # três regras no arquivo em vez de centenas de milhares de estilos.
        intervalo = f"A2:{ultima_coluna}{ultima_linha}"
        regras = {
            STATUS_CORRIGIR: "F4CCCC",
            STATUS_REVISAR: "FFF2CC",
            STATUS_OK: "D9EAD3",
            STATUS_SERVICO: "D9EAF7",
        }
        for status, cor in regras.items():
            ws.conditional_formatting.add(
                intervalo,
                FormulaRule(
                    formula=[f'$A2="{status}"'],
                    fill=PatternFill("solid", fgColor=cor),
                ),
            )

        resumo = resultado.resumo()
        wr = wb.create_sheet("Resumo")
        modo = "Somente pendências (CORRIGIR + REVISAR)" if somente_pendencias else "Auditoria completa"
        linhas_resumo = [
            ["FiscalPro — Auditoria de Cadastro por Excel", ""],
            ["Arquivo", resultado.arquivo],
            ["Aba lida", resultado.planilha],
            ["Modo de exportação", modo],
            ["Linhas exportadas", total],
            ["Itens auditados", resumo["itens"]],
            ["Corrigir", resumo["corrigir"]],
            ["Revisar", resumo["revisar"]],
            ["Serviços", resumo["servicos"]],
            ["OK", resumo["ok"]],
            ["NCMs únicos", resumo["ncm_unicos"]],
            ["Observação", "A auditoria não altera a planilha original nem o cadastro do ERP. Sugestões devem ser conferidas antes da aplicação."],
        ]
        fill_res = PatternFill("solid", fgColor="1F4E78")
        fonte_res = Font(bold=True, color="FFFFFF", size=14)
        for numero, (rotulo, valor) in enumerate(linhas_resumo, start=1):
            if numero == 1:
                c1 = WriteOnlyCell(wr, value=rotulo)
                c1.font = fonte_res
                c1.fill = fill_res
                c2 = WriteOnlyCell(wr, value=valor)
                c2.fill = fill_res
                wr.append([c1, c2])
            else:
                wr.append([rotulo, valor])
        wr.column_dimensions["A"].width = 30
        wr.column_dimensions["B"].width = 100

        if progresso:
            progresso(total, total, "Finalizando o arquivo Excel...")
        wb.save(caminho)
        return str(caminho.resolve())


class ExportadorFichaTributariaCompletaXLSX:
    """Gera uma ficha tributária no formato do modelo operacional do usuário.

    As 22 primeiras colunas reproduzem a estrutura do modelo fornecido. O
    FiscalPro acrescenta, à direita, colunas de auditoria/rastreabilidade para
    não transformar uma referência condicional em correção silenciosa.
    """

    CABECALHOS_MODELO = [
        "COD. PRODUTO", "DESCRIÇÃO", "Código de Barras", "Cód. NCM", "EX", "CEST",
        "CST ICMS", "CFOP Saída", "ICMS Desonerado", "Red. BC ICMS(%)",
        "Aliq. ICMS(%)", "ICMS ST", "MVA ICMS-ST(%)", "Red. BC ICMS-ST(%)",
        "Aliq. ICMS-ST(%)", "Aliq. FEM(%)", "CST IPI", "Aliq. IPI(%)",
        "CST PIS/COFINS SAÍDA", "Aliq. PIS(%)", "Aliq. COFINS(%)", "Nat. de receita",
    ]
    CABECALHOS_AUDITORIA = [
        "Status Auditoria", "NCM atual", "NCM sugerido", "NCM candidatos", "CEST atual", "CEST referência",
        "ICMS referência (%)", "ST FiscalPro", "MVA FiscalPro (%)", "FEM/FCP referência (%)",
        "PIS referência", "COFINS referência", "IPI TIPI ref. (%)", "Segurança (%)",
        "Problema encontrado", "Correção sugerida", "Observação FiscalPro",
        "Fundamento ICMS", "Fundamento PIS/COFINS", "Fontes",
    ]
    HEADERS = CABECALHOS_MODELO + CABECALHOS_AUDITORIA

    # Índices 1-based das colunas percentuais no arquivo final.
    COLUNAS_PERCENTUAIS = {
        10, 11, 13, 14, 15, 16, 18, 20, 21, 29, 31, 32, 35, 36,
    }

    LARGURAS_MODELO = [
        15, 42, 18, 12, 8, 14, 11, 12, 16, 16, 15, 12, 18, 19, 18, 14, 11, 14,
        23, 14, 17, 16,
    ]
    LARGURAS_AUDITORIA = [
        16, 12, 13, 34, 14, 16, 18, 14, 18, 20, 22, 24, 18, 15, 62, 62, 55, 55, 55, 60,
    ]

    @staticmethod
    def _pct_excel(valor: Optional[float]) -> Optional[float]:
        if valor is None:
            return None
        try:
            return float(valor) / 100.0
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _cst_piscofins(item: ItemAuditoriaExcel) -> str:
        pis_ref = str(item.cst_pis_referencia or "").strip()
        cof_ref = str(item.cst_cofins_referencia or "").strip()
        if pis_ref and cof_ref and pis_ref == cof_ref:
            return pis_ref
        pis_at = str(item.cst_pis_atual or "").strip()
        cof_at = str(item.cst_cofins_atual or "").strip()
        if pis_at and cof_at and pis_at == cof_at:
            return pis_at
        return "REVISAR" if any((pis_ref, cof_ref, pis_at, cof_at)) else ""

    @classmethod
    def _linha(cls, item: ItemAuditoriaExcel) -> List[Any]:
        if item.status == STATUS_SERVICO:
            # A ficha continua contendo a linha para rastreabilidade, porém não
            # força campos de mercadoria sobre um serviço.
            modelo = [
                item.codigo, item.descricao, item.codigo_barras, "", item.ex_tipi, "",
                "N/A", "N/A", "N/A", None, None, "N/A", None, None, None, None,
                "N/A", None, "", None, None, item.nat_receita_atual or "",
            ]
            auditoria = [
                item.status, item.ncm_atual, "", "", item.cest_atual, "", None, "N/A",
                None, None, "", "", None, cls._pct_excel(item.seguranca),
                item.problema, item.correcao_sugerida, item.observacao, "", "", "",
            ]
            return modelo + auditoria

        st_ref = str(item.st_referencia or "REVISAR").upper()
        if st_ref == "SIM":
            cest_ficha = item.cest_sugerido or item.cest_atual
            mva_ficha = item.mva_referencia
        elif st_ref in {"NÃO", "NAO"}:
            cest_ficha = ""
            mva_ficha = None
        else:
            cest_ficha = item.cest_atual or item.cest_sugerido
            mva_ficha = item.mva_icms_st_atual or item.mva_referencia

        aliq_icms = (
            item.aliquota_icms_referencia
            if item.aliquota_icms_referencia is not None
            else item.aliquota_icms_atual
        )
        fem = item.fem_referencia if item.fem_referencia is not None else item.aliquota_fem_atual
        ipi = item.ipi_referencia if item.ipi_referencia is not None else item.ipi_atual
        pis = item.pis_referencia if item.pis_referencia is not None else item.pis_atual
        cofins = item.cofins_referencia if item.cofins_referencia is not None else item.cofins_atual

        fontes = " | ".join(
            valor for valor in (str(item.fonte_icms or "").strip(), str(item.fonte_piscofins or "").strip())
            if valor
        )

        modelo = [
            item.codigo,
            item.descricao,
            item.codigo_barras,
            item.ncm_atual,
            item.ex_tipi,
            cest_ficha,
            item.cst_icms_atual or item.cst_icms_sugerido or "REVISAR",
            item.cfop_atual or item.cfop_sugerido or "REVISAR",
            item.icms_desonerado_atual or item.icms_desonerado_sugerido or "REVISAR",
            cls._pct_excel(item.reducao_bc_icms_atual),
            cls._pct_excel(aliq_icms),
            st_ref,
            cls._pct_excel(mva_ficha),
            cls._pct_excel(item.reducao_bc_icms_st_atual),
            cls._pct_excel(item.aliquota_icms_st_atual),
            cls._pct_excel(fem),
            item.cst_ipi_atual or item.cst_ipi_sugerido or "",
            cls._pct_excel(ipi),
            cls._cst_piscofins(item),
            cls._pct_excel(pis),
            cls._pct_excel(cofins),
            item.nat_receita_atual or item.nat_receita_sugerida,
        ]
        auditoria = [
            item.status,
            item.ncm_atual,
            item.ncm_sugerido,
            item.ncm_candidatos,
            item.cest_atual,
            item.cest_sugerido,
            cls._pct_excel(item.aliquota_icms_referencia),
            st_ref,
            cls._pct_excel(item.mva_referencia),
            cls._pct_excel(item.fem_referencia),
            item.pis_referencia_texto,
            item.cofins_referencia_texto,
            cls._pct_excel(item.ipi_referencia),
            cls._pct_excel(item.seguranca),
            item.problema,
            item.correcao_sugerida,
            item.observacao,
            item.fundamento_icms,
            item.fundamento_piscofins,
            fontes,
        ]
        return modelo + auditoria

    @classmethod
    def exportar(
        cls,
        resultado: ResultadoAuditoriaExcel,
        destino: str | Path,
        *,
        progresso: Optional[Callable[[int, int, str], None]] = None,
    ) -> str:
        try:
            from openpyxl import Workbook
            from openpyxl.cell import WriteOnlyCell
            from openpyxl.formatting.rule import FormulaRule
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError as erro:  # pragma: no cover
            raise RuntimeError("Instale o pacote openpyxl para exportar a ficha tributária.") from erro

        caminho = Path(destino)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        itens = list(resultado.itens)
        if not itens:
            raise ValueError("Não há itens auditados para gerar a ficha tributária.")

        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Ficha Tributária")
        ws.freeze_panes = "A2"

        larguras = cls.LARGURAS_MODELO + cls.LARGURAS_AUDITORIA
        for idx, largura in enumerate(larguras, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = largura

        azul = "5B9BD5"
        azul_escuro = "1F4E78"
        fonte_cab = Font(bold=True, color="FFFFFF")
        alinh_cab = Alignment(vertical="center", horizontal="center", wrap_text=True)
        cabecalho = []
        for indice, valor in enumerate(cls.HEADERS, start=1):
            cel = WriteOnlyCell(ws, value=valor)
            cel.font = fonte_cab
            cel.fill = PatternFill("solid", fgColor=azul if indice <= 22 else azul_escuro)
            cel.alignment = alinh_cab
            cabecalho.append(cel)
        ws.append(cabecalho)

        total = len(itens)
        for indice_item, item in enumerate(itens, start=1):
            valores = cls._linha(item)
            linha_saida = []
            for indice_col, valor in enumerate(valores, start=1):
                if indice_col in cls.COLUNAS_PERCENTUAIS and valor is not None:
                    cel = WriteOnlyCell(ws, value=valor)
                    cel.number_format = "0.00%"
                    linha_saida.append(cel)
                else:
                    linha_saida.append(valor)
            ws.append(linha_saida)
            if progresso and (indice_item % 300 == 0 or indice_item == total):
                progresso(indice_item, total, item.descricao or item.codigo or "")

        ultima_coluna = get_column_letter(len(cls.HEADERS))
        ultima_linha = total + 1
        ws.auto_filter.ref = f"A1:{ultima_coluna}{ultima_linha}"

        # Mantém o visual do modelo nas 22 primeiras colunas (faixas azul-claro)
        # e colore apenas a área de auditoria conforme o status.
        ws.conditional_formatting.add(
            f"A2:V{ultima_linha}",
            FormulaRule(
                formula=["=MOD(ROW(),2)=0"],
                fill=PatternFill("solid", fgColor="DDEBF7"),
            ),
        )
        intervalo_auditoria = f"W2:{ultima_coluna}{ultima_linha}"
        coluna_status = get_column_letter(23)
        regras = {
            STATUS_CORRIGIR: "F4CCCC",
            STATUS_REVISAR: "FFF2CC",
            STATUS_OK: "D9EAD3",
            STATUS_SERVICO: "D9EAF7",
        }
        for status, cor in regras.items():
            ws.conditional_formatting.add(
                intervalo_auditoria,
                FormulaRule(
                    formula=[f'${coluna_status}2="{status}"'],
                    fill=PatternFill("solid", fgColor=cor),
                ),
            )

        wr = wb.create_sheet("Resumo")
        resumo = resultado.resumo()
        contexto = dict(resultado.contexto or {})
        linhas = [
            ["FiscalPro — Ficha Tributária Completa", ""],
            ["Arquivo de origem", resultado.arquivo],
            ["Aba lida", resultado.planilha],
            ["Itens", resumo["itens"]],
            ["Corrigir", resumo["corrigir"]],
            ["Revisar", resumo["revisar"]],
            ["Serviços", resumo["servicos"]],
            ["OK", resumo["ok"]],
            ["Empresa", contexto.get("empresa") or "-"],
            ["Regime", contexto.get("regime") or "-"],
            ["Finalidade", contexto.get("finalidade") or "-"],
            ["UF origem", contexto.get("uf_origem") or "-"],
            ["UF destino", contexto.get("uf_destino") or "-"],
            ["Data de referência", contexto.get("data_operacao") or "-"],
            [
                "Critério",
                (
                    "As 22 primeiras colunas seguem o modelo fornecido. Campos que o motor consegue "
                    "confirmar usam a referência FiscalPro; campos sem regra determinística recebem "
                    "REVISAR em vez de uma tributação inventada."
                ),
            ],
            [
                "Status da auditoria",
                (
                    "CORRIGIR = divergência objetiva; REVISAR = pendência específica do item; "
                    "SERVIÇO = linha de mão de obra/serviço fora da classificação NCM de mercadorias; "
                    "OK = sem divergência objetiva. Alertas genéricos do motor permanecem na observação "
                    "e não rebaixam sozinhos o status."
                ),
            ],
            [
                "Atenção",
                (
                    "NCM sugerido, CST/CFOP e benefícios condicionais exigem conferência da composição, "
                    "função da mercadoria, operação e legislação vigente antes de alterar o ERP."
                ),
            ],
        ]
        fill_res = PatternFill("solid", fgColor=azul_escuro)
        fonte_res = Font(bold=True, color="FFFFFF", size=14)
        for numero, (rotulo, valor) in enumerate(linhas, start=1):
            if numero == 1:
                c1 = WriteOnlyCell(wr, value=rotulo)
                c1.font = fonte_res
                c1.fill = fill_res
                c2 = WriteOnlyCell(wr, value=valor)
                c2.fill = fill_res
                wr.append([c1, c2])
            else:
                wr.append([rotulo, valor])
        wr.column_dimensions["A"].width = 28
        wr.column_dimensions["B"].width = 115

        if progresso:
            progresso(total, total, "Finalizando a ficha tributária...")
        wb.save(caminho)
        return str(caminho.resolve())


__all__ = [
    "AuditoriaCadastrosExcelService",
    "ExportadorAuditoriaCadastrosExcelXLSX",
    "ExportadorFichaTributariaCompletaXLSX",
    "ResultadoAuditoriaExcel",
    "ItemAuditoriaExcel",
    "STATUS_CORRIGIR",
    "STATUS_REVISAR",
    "STATUS_OK",
    "STATUS_SERVICO",
]
