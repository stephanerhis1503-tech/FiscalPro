"""Tabela de vigencia RTC 2026-2027 e simulador SEM efeitos fiscais.

Sprint de preparacao 2027 (fotografia normativa: 18/11/2026).
- 2026: CBS 0,90%, IBS UF 0,10%, IBS municipio 0,00% (ano de teste).
- 2027: IBS UF 0,05%, IBS municipio 0,05%.
  CBS: SEM ALIQUOTA DEFINITIVA cadastrada neste modulo.
  11,3% e a referencia calculada pelo TCU, ainda nao fixada pelo Senado.
  11,2% e uma simulacao da referencia TCU menos 0,1 ponto percentual.
- Sem gravacao em banco, sem sobrescrita de XML, sem apuracao oficial.

Fontes:
https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/reforma-tributaria-do-consumo/entenda
https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?AspxAutoDetectCookieSupport=1&conteudo=VA%2F3IAyJmSw%3D
https://sites.tcu.gov.br/reforma-tributaria/visao-cbs-2027.html
https://www12.senado.leg.br/noticias/materias/2026/11/10/senado-recebe-acordao-do-tcu-que-propoe-aliquota-de-11-3-para-a-cbs
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


DATA_VERIFICACAO = "18/11/2026"
CENTAVO = Decimal("0.01")
CST_PADRAO = "000"
CLASS_PADRAO = "000001"
REGIMES_SIMULAVEIS = ("Lucro Real", "Lucro Presumido")
REGIMES = REGIMES_SIMULAVEIS + ("Simples Nacional", "Nao informado")


@dataclass(frozen=True)
class RegraAliquotaRTC:
    ano: int
    cbs_vigente: Decimal | None
    ibs_uf: Decimal
    ibs_municipal: Decimal
    status: str
    referencia_tcu_cbs: Decimal | None = None
    cbs_cenario_tcu: Decimal | None = None
    fonte: str = ""


# Percentuais em unidades de %, e nao fracoes (0,90 significa 0,90%).
# A CBS 2027 NAO integra cbs_vigente enquanto nao houver fundamento definitivo.
REGRAS = {
    2026: RegraAliquotaRTC(
        ano=2026,
        cbs_vigente=Decimal("0.90"),
        ibs_uf=Decimal("0.10"),
        ibs_municipal=Decimal("0.00"),
        status="VIGENTE_ANO_TESTE",
        fonte="LC 214/2025; Receita Federal; IT NF-e 2025.002",
    ),
    2027: RegraAliquotaRTC(
        ano=2027,
        cbs_vigente=None,
        ibs_uf=Decimal("0.05"),
        ibs_municipal=Decimal("0.05"),
        status="CBS_AGUARDANDO_RESOLUCAO_SENADO",
        referencia_tcu_cbs=Decimal("11.30"),
        cbs_cenario_tcu=Decimal("11.20"),
        fonte=(
            "LC 214/2025; IT NF-e 2025.002; "
            "Acórdao TCU TC 006.529/2026-7; Senado, 10/11/2026"
        ),
    ),
}


def _dinheiro(valor: str | int | Decimal) -> Decimal:
    """Aceita '1.234,56', '1234,56', '1234.56' e Decimal, sem floats."""
    if isinstance(valor, bool) or isinstance(valor, float):
        raise ValueError("Informe a base em reais, sem valores aproximados de ponto flutuante.")
    if isinstance(valor, (Decimal, int)):
        numero = Decimal(valor)
    else:
        texto = str(valor or "").strip().replace("R$", "").replace(" ", "")
        if not texto:
            raise ValueError("Informe a base de calculo em reais.")
        if "," in texto:
            # Ponto e separador de milhar, virgula e decimal (padrao brasileiro).
            if not re.fullmatch(r"(?:\d{1,3}(?:\.\d{3})+|\d+),\d{1,2}", texto):
                raise ValueError("Base invalida. Exemplo: 1.234,56.")
            texto = texto.replace(".", "").replace(",", ".")
        elif not re.fullmatch(r"\d+(?:\.\d{1,2})?", texto):
            raise ValueError("Base invalida. Exemplo: 1000,00.")
        try:
            numero = Decimal(texto)
        except InvalidOperation as exc:
            raise ValueError("Base invalida.") from exc
    if not numero.is_finite() or numero <= 0 or numero > Decimal("1000000000000"):
        raise ValueError("A base deve ser positiva e ate R$ 1 trilhão.")
    if numero != numero.quantize(CENTAVO):
        raise ValueError("A base deve ter no maximo duas casas decimais.")
    return numero.quantize(CENTAVO)


def _percentual(base: Decimal, taxa: Decimal) -> Decimal:
    return (base * taxa / Decimal("100")).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class ServicoAliquotasRTC:
    """Motor somente de consulta e simulacao; nunca altera dados do FiscalPro."""

    @staticmethod
    def consultar(ano: int | str) -> RegraAliquotaRTC:
        try:
            numero = int(ano)
        except (TypeError, ValueError) as exc:
            raise ValueError("Selecione o ano 2026 ou 2027.") from exc
        if str(ano).strip() not in (str(numero),):
            raise ValueError("Selecione o ano 2026 ou 2027.")
        if numero not in REGRAS:
            raise ValueError("Somente os anos 2026 e 2027 estao preparados neste painel.")
        return REGRAS[numero]

    @classmethod
    def simular(
        cls,
        ano: int | str,
        base: str | int | Decimal,
        *,
        cst: str = CST_PADRAO,
        cclass_trib: str = CLASS_PADRAO,
        regime: str = "Nao informado",
        usar_cenario_tcu: bool = False,
    ) -> dict:
        """So simula operacao PADRAO; regimes/tratamentos especiais ficam em revisao."""
        regra = cls.consultar(ano)
        base_monetaria = _dinheiro(base)
        cst = str(cst).strip()
        cclass_trib = str(cclass_trib).strip()
        if not re.fullmatch(r"\d{3}", cst) or not re.fullmatch(r"\d{6}", cclass_trib):
            raise ValueError("Informe CST (3 digitos) e cClassTrib (6 digitos).")
        if regime not in REGIMES:
            raise ValueError("Selecione um regime tributario valido.")
        if not isinstance(usar_cenario_tcu, bool):
            raise ValueError("A opcao de cenario TCU deve ser explicita.")

        resultado = {
            "ano": regra.ano,
            "base": base_monetaria,
            "cst": cst,
            "cclass_trib": cclass_trib,
            "regime": regime,
            "status": "",
            "ibs_uf": None,
            "ibs_municipal": None,
            "cbs": None,
            "total": None,
            "p_cbs_usado": None,
            "observacao": "",
            "efeito_fiscal": False,
        }

        if regime not in REGIMES_SIMULAVEIS:
            resultado["status"] = "REVISAR_REGIME"
            resultado["observacao"] = (
                "Nao simulavel automaticamente para Simples Nacional ou regime nao "
                "identificado. Conferir as regras da operacao e da empresa."
            )
            return resultado

        if (cst, cclass_trib) != (CST_PADRAO, CLASS_PADRAO):
            resultado["status"] = "REGRA_ESPECIAL_REVISAR"
            resultado["observacao"] = (
                "CST/cClassTrib diferente da tributacao integral padrao. "
                "Pode haver reducao, isencao, regime especifico ou outra excecao. "
                "Nao aplicar aliquotas gerais sem analise individual."
            )
            return resultado

        resultado["ibs_uf"] = _percentual(base_monetaria, regra.ibs_uf)
        resultado["ibs_municipal"] = _percentual(base_monetaria, regra.ibs_municipal)
        if regra.cbs_vigente is not None:
            resultado["p_cbs_usado"] = regra.cbs_vigente
            resultado["cbs"] = _percentual(base_monetaria, regra.cbs_vigente)
            resultado["total"] = (
                resultado["ibs_uf"] + resultado["ibs_municipal"] + resultado["cbs"]
            )
            resultado["status"] = "SIMULACAO_TESTE_2026"
            resultado["observacao"] = (
                "Calculo demonstrativo para operacao integral padrao no ano de teste "
                "2026. Nao substitui a apuracao oficial, nem reconhece creditos."
            )
            return resultado

        if not usar_cenario_tcu:
            resultado["status"] = "CBS_PENDENTE_DEFINICAO"
            resultado["observacao"] = (
                "IBS padrao previsto para 2027 exibido como demonstracao. "
                "CBS nao calculada: aguardando resolucao do Senado. "
                "Nao existe aliquota CBS definitiva cadastrada."
            )
            return resultado

        # Referencia aprovada pelo TCU NAO e norma definitiva do Senado.
        if regra.cbs_cenario_tcu is None:
            raise ValueError("Nao ha cenario TCU disponivel para este ano.")
        resultado["p_cbs_usado"] = regra.cbs_cenario_tcu
        resultado["cbs"] = _percentual(base_monetaria, regra.cbs_cenario_tcu)
        resultado["total"] = (
            resultado["ibs_uf"] + resultado["ibs_municipal"] + resultado["cbs"]
        )
        resultado["status"] = "CENARIO_TCU_NAO_OFICIAL"
        resultado["observacao"] = (
            "SIMULACAO: CBS 11,3% calculada pelo TCU menos 0,1 ponto percentual "
            "= 11,2%. NAO e aliquota vigente para emissao, SPED ou apuracao. "
            "Aguardar resolucao do Senado e validar cada tratamento tributario."
        )
        return resultado


    @classmethod
    def simular_item_2027(
        cls, item: dict, *, regime: str, usar_cenario_tcu: bool = False,
    ) -> dict:
        """Projecao isolada de um ITEM armazenado em XML, sem escrever no banco.

        Escopo deliberadamente conservador: SOMENTE saidas de venda com
        CFOP 5101/5102/6101/6102, CST 000, cClassTrib 000001 e
        auditoria original OK. Outros CFOPs (incluindo 5405/6405) NAO
        sao presumidos como nao tributados: exigem classificacao fiscal.
        Base e classificacao historicas nao provam o tratamento em 2027.
        """
        if not isinstance(item, dict):
            raise ValueError("Selecione um item da Auditoria por Item.")
        if type(usar_cenario_tcu) is not bool:
            raise ValueError("O cenario TCU deve ser escolhido explicitamente.")
        contexto = {
            "numero_nf": str(item.get("numero_nf") or ""),
            "numero_item": str(item.get("numero_item") or ""),
            "descricao": str(item.get("descricao") or ""),
            "direcao": str(item.get("direcao") or "").upper().strip(),
            "cfop": str(item.get("cfop") or "").strip(),
            "cst": str(item.get("cst_ibscbs") or "").strip(),
            "cclass_trib": str(item.get("cclass_trib") or "").strip(),
            "base_xml": str(item.get("base_ibs_cbs") or ""),
            "status_xml": str(item.get("status_auditoria") or ""),
        }

        def revisar(status: str, observacao: str) -> dict:
            return {
                **contexto, "ano": 2027, "regime": regime,
                "status": status, "observacao": observacao,
                "base": None, "ibs_uf": None, "ibs_municipal": None,
                "cbs": None, "total": None, "p_cbs_usado": None,
                "efeito_fiscal": False,
            }

        if contexto["direcao"] != "SAIDA":
            return revisar(
                "REVISAR_TIPO_OPERACAO",
                "Entrada ou operacao sem saida de venda: nao projetar debito "
                "padrao. Credito de aquisicao depende das regras proprias.",
            )
        if contexto["status_xml"] != "OK":
            return revisar(
                "REVISAR_AUDITORIA_XML",
                "O item ja possui alerta na auditoria original. "
                "Resolver o enquadramento antes de simular.",
            )
        if contexto["cfop"] not in {"5101", "5102", "6101", "6102"}:
            return revisar(
                "REVISAR_CFOP_OPERACAO",
                "CFOP nao esta entre as vendas comuns aceitas para esta "
                "simulacao. Transferencias, devolucoes, ST e outras "
                "operacoes exigem analise; nao se conclui isencao ou incidencia.",
            )
        try:
            calculo = cls.simular(
                2027, contexto["base_xml"],
                cst=contexto["cst"], cclass_trib=contexto["cclass_trib"],
                regime=regime, usar_cenario_tcu=usar_cenario_tcu,
            )
        except ValueError as exc:
            return revisar(
                "REVISAR_DADOS_ITEM",
                f"Base ou classificacao do XML insuficiente para projetar: {exc}",
            )
        calculo["contexto_item"] = contexto
        # Nunca sobrescreve o dict de entrada nem reconhece credito.
        return calculo
