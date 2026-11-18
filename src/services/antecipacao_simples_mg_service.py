"""Memoria assistida do ICMS antecipacao Simples Nacional em MG.

Esta rotina NAO confunde antecipacao SEM encerramento com ICMS-ST.
Base legal:
- RICMS/MG 2023, art. 3 VII, art. 11 II e art. 12 XII e par. 7/8.
- IN SUTRI 001/2016, art. 2 (metodologia da base dupla).
- LC 123/2006, art. 13 par. 1 XIII g.2.

Fonte oficial:
https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/instrucoes_normativas/2016/insutri001_2016.html

Apenas SIMULACAO local; NAO gera DAE, credito ou lancamento contabil.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

FONTE = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "instrucoes_normativas/2016/insutri001_2016.html"
)
CENTAVO = Decimal("0.01")
DESTINOS_PERMITIDOS = frozenset({
    "REVENDA", "INDUSTRIALIZACAO", "PRESTACAO_SERVICO"
})


def _numero(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        texto = str(valor).strip().replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        d = Decimal(texto)
        if not d.is_finite():
            return None
        return d
    except (InvalidOperation, TypeError, ValueError):
        return None


def _revisar(status: str, motivo: str, *, base=None, interna=None, inter=None):
    return {
        "status": status, "motivo": motivo, "base_operacao": base,
        "aliquota_interna": interna, "aliquota_interestadual": inter,
        "icms_interestadual": None, "base_recomposta": None,
        "icms_interno": None, "antecipacao_estimada": None,
        "fonte": FONTE, "carater": "SIMULACAO - NAO RECOLHER SEM CONFERENCIA",
    }


def calcular_item(
    item: dict,
    resultado_st: dict,
    *, uf_origem: str,
    uf_destino: str,
    destinatario_simples: bool,
    finalidade: str,
    aliquota_interna: object,
    aliquota_interestadual: object,
    base_manual: object = None,
) -> dict:
    """Calcula apenas quando destino/aliquotas/base foram confirmados.

    Na base da operacao sugerida nao inclui IPI; itens com IPI sao bloqueados
    ate revisao da inclusao/nao inclusao na BC conforme a operacao.
    """
    uf_origem = str(uf_origem or "").upper()
    uf_destino = str(uf_destino or "").upper()
    final = str(finalidade or "").upper()
    if not destinatario_simples:
        return _revisar("NAO APLICAVEL", "Destinatario nao confirmado como Simples Nacional.")
    if uf_destino != "MG" or not uf_origem or uf_origem == "MG":
        return _revisar("NAO APLICAVEL", "Exige compra interestadual destinada a MG.")
    if final not in DESTINOS_PERMITIDOS:
        return _revisar("REVISAR FINALIDADE", "Confirmar revenda, industrializacao ou uso na prestacao de servico.")

    st = dict(resultado_st.get("st_oficial") or {})
    if any((
        bool(st.get("confirmado")),
        bool(st.get("encontrado")) and not bool(st.get("nao_aplicavel")),
        bool(st.get("exige_revisao")),
        bool(resultado_st.get("calculo_condicional")) and bool(resultado_st.get("calculado")),
        bool(_numero(item.get("icms_st_xml")) or 0),
        bool(_numero(item.get("icms_st_retido_xml")) or 0),
        bool(_numero(item.get("base_st_retida_xml")) or 0),
    )):
        return _revisar(
            "REVISAR ICMS-ST",
            "ST encontrada, retida ou condicional. NAO somar antecipacao sem verificar o regime aplicavel."
        )

    interno = _numero(aliquota_interna)
    interestadual = _numero(aliquota_interestadual)
    if interno is None or interestadual is None or not (
        Decimal("0") < interno < Decimal("100")
        and Decimal("0") < interestadual < Decimal("100")
    ):
        return _revisar(
            "REVISAR ALIQUOTAS",
            "Confirmar aliquota interna da mercadoria em MG e interestadual efetiva (4/7/12% conforme caso)."
        )
    if interno <= interestadual:
        return _revisar(
            "REVISAR ALIQUOTAS", "Aliquota interna nao supera a interestadual; validar tratamento legal.",
            interna=interno, inter=interestadual
        )
    if base_manual is None and (_numero(item.get("ipi")) or 0) > 0:
        return _revisar(
            "REVISAR IPI/BASE",
            "IPI informado. Confirme se entra na base conforme finalidade/operacao; informe base manual.",
            interna=interno, inter=interestadual,
        )
    base = _numero(base_manual)
    origem_base = "MANUAL"
    if base is None:
        campos = [(_numero(item.get(k)) or Decimal("0")) for k in
                  ("valor_produtos", "frete", "seguro", "outros")]
        desconto = _numero(item.get("desconto")) or Decimal("0")
        base = sum(campos, Decimal("0")) - desconto
        origem_base = "PRODUTOS - DESCONTO + FRETE + SEGURO + OUTROS (SEM IPI)"
    if base <= 0:
        return _revisar("REVISAR BASE", "Base da operacao ausente ou nao positiva.")

    taxa_int = interno / Decimal("100")
    taxa_inter = interestadual / Decimal("100")
    icms_inter = (base * taxa_inter).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    base_recomposta = (base - base * taxa_inter) / (Decimal("1") - taxa_int)
    interno_val = (base_recomposta * taxa_int).quantize(
        CENTAVO, rounding=ROUND_HALF_UP
    )
    antecipacao = max(Decimal("0"), interno_val - icms_inter).quantize(
        CENTAVO, rounding=ROUND_HALF_UP
    )
    return {
        "status": "SIMULACAO CONDICIONAL",
        "motivo": (
            "Valor demonstrativo; conferir CST, CFOP de ENTRADA, eventual beneficio, "
            "aliquotas e base antes de qualquer recolhimento. Fonte base: " + origem_base
        ),
        "base_operacao": base.quantize(CENTAVO, rounding=ROUND_HALF_UP),
        "aliquota_interna": interno,
        "aliquota_interestadual": interestadual,
        "icms_interestadual": icms_inter,
        "base_recomposta": base_recomposta.quantize(CENTAVO, rounding=ROUND_HALF_UP),
        "icms_interno": interno_val,
        "antecipacao_estimada": antecipacao,
        "fonte": FONTE,
        "carater": "SIMULACAO - NAO RECOLHER SEM CONFERENCIA",
    }


def calcular_lote(resultado: dict, *, destinatario_simples: bool,
                   finalidade: str, aliquota_interna: object,
                   aliquota_interestadual: object) -> list[dict]:
    linhas = []
    for r in resultado.get("itens") or []:
        item = dict(r.get("item") or {})
        dado = calcular_item(
            item, r,
            uf_origem=resultado.get("uf_origem"),
            uf_destino=resultado.get("uf_destino"),
            destinatario_simples=destinatario_simples,
            finalidade=finalidade,
            aliquota_interna=aliquota_interna,
            aliquota_interestadual=aliquota_interestadual,
            base_manual=None,
        )
        linhas.append({"item": item, "resultado": dado})
    return linhas
