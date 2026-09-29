"""Motor nacional conservador de PIS/Pasep e Cofins — Sprint 16.5.

O serviço combina regras oficiais confirmáveis com sugestões condicionais por
regime. Ele nunca trata a alíquota-padrão como prova de que um NCM não possui
regime especial. A conclusão automática é reservada a situações objetivas,
como a revenda monofásica de autopeças já mapeada e a exportação explicitamente
informada no contexto.

Fontes estruturantes:
- Tabelas 4.3.10 a 4.3.16 da EFD-Contribuições (Receita Federal/SPED);
- Lei nº 10.637/2002 (PIS/Pasep não cumulativo);
- Lei nº 10.833/2003 (Cofins não cumulativa);
- Lei nº 10.485/2002 (veículos, autopeças, pneus e câmaras);
- Lei nº 9.718/1998 e Decreto nº 4.524/2002 (regime cumulativo);
- legislação específica indicada por cada regra confirmada.
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from src.services.piscofins_monofasico_service import PISCOFINSMonofasicoService
from src.services.empresas_regimes_service import EmpresasRegimesService


URL_TABELAS_EFD = "https://sped.rfb.gov.br/item/show/1616"
URL_TABELA_4310 = "https://sped.rfb.gov.br/item/show/1638"
URL_TABELA_4313 = "https://sped.rfb.gov.br/item/show/1643"
URL_LEI_10637 = "https://www.planalto.gov.br/ccivil_03/leis/2002/l10637compilado.htm"
URL_LEI_10833 = "https://www.planalto.gov.br/ccivil_03/leis/2003/l10.833compilado.htm"
URL_LEI_9718 = "https://www.planalto.gov.br/ccivil_03/leis/l9718.htm"
URL_DECRETO_4524 = "https://www.planalto.gov.br/ccivil_03/decreto/2002/d4524.htm"


FONTES_OFICIAIS: Tuple[Dict[str, str], ...] = (
    {
        "codigo": "4.3.10",
        "titulo": "Produtos sujeitos a alíquotas diferenciadas — incidência monofásica",
        "cst": "02 e 04",
        "url": URL_TABELA_4310,
    },
    {
        "codigo": "4.3.11",
        "titulo": "Produtos sujeitos a alíquotas por unidade de medida",
        "cst": "03 e 04",
        "url": URL_TABELAS_EFD,
    },
    {
        "codigo": "4.3.12",
        "titulo": "Produtos sujeitos à substituição tributária das contribuições",
        "cst": "05",
        "url": URL_TABELAS_EFD,
    },
    {
        "codigo": "4.3.13",
        "titulo": "Produtos sujeitos à alíquota zero",
        "cst": "06",
        "url": URL_TABELA_4313,
    },
    {
        "codigo": "4.3.14",
        "titulo": "Operações com isenção",
        "cst": "07",
        "url": URL_TABELAS_EFD,
    },
    {
        "codigo": "4.3.15",
        "titulo": "Operações sem incidência",
        "cst": "08",
        "url": URL_TABELAS_EFD,
    },
    {
        "codigo": "4.3.16",
        "titulo": "Operações com suspensão",
        "cst": "09",
        "url": URL_TABELAS_EFD,
    },
)


@dataclass(frozen=True)
class ResultadoPISCOFINSNacional:
    ncm: str
    status: str
    enquadramento: str
    confirmado: bool = False
    exige_revisao: bool = True
    cst_pis: str = ""
    aliquota_pis: float = 0.0
    cst_cofins: str = ""
    aliquota_cofins: float = 0.0
    sugestao_cst_pis: str = ""
    sugestao_aliquota_pis: float = 0.0
    sugestao_cst_cofins: str = ""
    sugestao_aliquota_cofins: float = 0.0
    regime_apuracao: str = ""
    fundamento: str = ""
    artigo: str = ""
    fonte_url: str = URL_TABELAS_EFD
    tabela_efd: str = ""
    observacao: str = ""
    confiabilidade: float = 0.0
    codigo_legal: str = ""

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PISCOFINSNacionalService:
    """Classifica PIS/Cofins sem presumir que o NCM isolado encerra a análise."""

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            caractere
            for caractere in unicodedata.normalize("NFD", texto)
            if unicodedata.category(caractere) != "Mn"
        )
        return " ".join(texto.split())

    @staticmethod
    def _normalizar_ncm(valor: Any) -> str:
        codigo = "".join(c for c in str(valor or "") if c.isdigit())
        if len(codigo) != 8:
            raise ValueError("O NCM deve possuir 8 dígitos.")
        return codigo

    @staticmethod
    def _data_operacao(contexto: Dict[str, Any]) -> date:
        texto = str(contexto.get("data_operacao") or "").strip()
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto[:10], formato).date()
            except ValueError:
                continue
        return date.today()

    @classmethod
    def _resultado_reforma(cls, ncm: str) -> Dict[str, Any]:
        return ResultadoPISCOFINSNacional(
            ncm=ncm,
            status="REVISAR REFORMA TRIBUTÁRIA",
            enquadramento="PIS/COFINS — PERÍODO POSTERIOR A 2026",
            confirmado=False,
            exige_revisao=True,
            fundamento="Lei Complementar nº 214/2025 e legislação superveniente",
            observacao=(
                "A operação informada está em período posterior a 2026. O motor desta "
                "Sprint não aplica PIS/Cofins após a entrada da CBS; confirme a legislação "
                "vigente na competência."
            ),
            confiabilidade=100.0,
        ).para_dict()

    @classmethod
    def _analisar_exportacao(
        cls, ncm: str, operacao: str, regime: str
    ) -> Optional[Dict[str, Any]]:
        if "EXPORT" not in operacao:
            return None
        return ResultadoPISCOFINSNacional(
            ncm=ncm,
            status="CONFIRMADO — SEM INCIDÊNCIA NA EXPORTAÇÃO",
            enquadramento="RECEITA DE EXPORTAÇÃO",
            confirmado=True,
            exige_revisao=False,
            cst_pis="08",
            aliquota_pis=0.0,
            cst_cofins="08",
            aliquota_cofins=0.0,
            regime_apuracao=regime,
            fundamento="Leis nº 10.637/2002 e nº 10.833/2003",
            artigo="art. 5º e art. 6º, respectivamente",
            fonte_url=URL_LEI_10637,
            tabela_efd="4.3.15 — CST 08",
            observacao=(
                "Receita de exportação explicitamente informada. Confirme a documentação "
                "da exportação e eventual venda com fim específico de exportação."
            ),
            confiabilidade=95.0,
        ).para_dict()

    @classmethod
    def _analisar_padrao_por_regime(
        cls, ncm: str, operacao: str, regime: str
    ) -> Dict[str, Any]:
        eh_saida = any(token in operacao for token in ("VENDA", "SAIDA", "REVENDA"))
        if not eh_saida:
            return ResultadoPISCOFINSNacional(
                ncm=ncm,
                status="REVISAR OPERAÇÃO",
                enquadramento="ENTRADA/OUTRA OPERAÇÃO",
                confirmado=False,
                exige_revisao=True,
                regime_apuracao=regime,
                observacao=(
                    "A alíquota de saída não deve ser transportada automaticamente para "
                    "entrada, devolução, transferência ou crédito. Analise CST e direito a "
                    "crédito conforme a operação."
                ),
                confiabilidade=100.0,
            ).para_dict()

        if "SIMPLES" in regime or regime == "MEI":
            return ResultadoPISCOFINSNacional(
                ncm=ncm,
                status="REVISAR — SIMPLES NACIONAL",
                enquadramento="SEGREGAÇÃO NO PGDAS-D",
                confirmado=False,
                exige_revisao=True,
                regime_apuracao="Simples Nacional",
                observacao=(
                    "Não foi aplicada alíquota de PIS/Cofins no documento. Verifique o CSOSN, "
                    "a segregação da receita e a existência de tributação monofásica, "
                    "substituição ou alíquota zero no PGDAS-D."
                ),
                confiabilidade=100.0,
            ).para_dict()

        if "PRESUM" in regime or "CUMULAT" in regime:
            return ResultadoPISCOFINSNacional(
                ncm=ncm,
                status="SUGESTÃO CONDICIONAL — REGIME CUMULATIVO",
                enquadramento="TRIBUTAÇÃO PADRÃO — SUJEITA A EXCEÇÕES",
                confirmado=False,
                exige_revisao=True,
                sugestao_cst_pis="01",
                sugestao_aliquota_pis=0.65,
                sugestao_cst_cofins="01",
                sugestao_aliquota_cofins=3.0,
                regime_apuracao="Cumulativo",
                fundamento=(
                    "Lei nº 9.718/1998, Lei nº 9.715/1998, MP nº 2.158-35/2001 "
                    "e Decreto nº 4.524/2002"
                ),
                artigo="Decreto nº 4.524/2002, art. 51",
                fonte_url=URL_DECRETO_4524,
                observacao=(
                    "As alíquotas de 0,65% e 3% são apenas o padrão cumulativo. Antes de "
                    "confirmar, exclua monofásico, alíquota zero, suspensão, isenção, sem "
                    "incidência, substituição tributária e regimes setoriais."
                ),
                confiabilidade=65.0,
            ).para_dict()

        if "REAL" in regime or "NAO CUMULAT" in regime or "NÃO CUMULAT" in regime:
            return ResultadoPISCOFINSNacional(
                ncm=ncm,
                status="SUGESTÃO CONDICIONAL — REGIME NÃO CUMULATIVO",
                enquadramento="TRIBUTAÇÃO PADRÃO — SUJEITA A EXCEÇÕES",
                confirmado=False,
                exige_revisao=True,
                sugestao_cst_pis="01",
                sugestao_aliquota_pis=1.65,
                sugestao_cst_cofins="01",
                sugestao_aliquota_cofins=7.6,
                regime_apuracao="Não cumulativo",
                fundamento="Leis nº 10.637/2002 e nº 10.833/2003",
                artigo="art. 2º de cada lei",
                fonte_url=URL_LEI_10637,
                observacao=(
                    "As alíquotas de 1,65% e 7,60% são apenas o padrão não cumulativo. "
                    "Antes de confirmar, exclua regimes especiais e hipóteses das Tabelas "
                    "4.3.10 a 4.3.16 da EFD-Contribuições."
                ),
                confiabilidade=65.0,
            ).para_dict()

        return ResultadoPISCOFINSNacional(
            ncm=ncm,
            status="REGIME NÃO INFORMADO",
            enquadramento="ANÁLISE INCOMPLETA",
            confirmado=False,
            exige_revisao=True,
            observacao=(
                "Informe Lucro Real, Lucro Presumido ou Simples Nacional para obter uma "
                "sugestão de enquadramento."
            ),
            confiabilidade=100.0,
        ).para_dict()

    @classmethod
    def analisar(
        cls,
        ncm: Any,
        contexto: Optional[Dict[str, Any]] = None,
        descricao: str = "",
        ex_tipi: str = "",
    ) -> Dict[str, Any]:
        codigo = cls._normalizar_ncm(ncm)
        contexto = EmpresasRegimesService.aplicar_contexto(contexto)
        operacao = cls._normalizar_texto(contexto.get("operacao"))
        regime = cls._normalizar_texto(contexto.get("regime"))

        if cls._data_operacao(contexto) >= date(2027, 1, 1):
            return cls._resultado_reforma(codigo)

        exportacao = cls._analisar_exportacao(codigo, operacao, regime)
        if exportacao is not None:
            return exportacao

        resultado_monofasico = PISCOFINSMonofasicoService.analisar(
            codigo,
            contexto=contexto,
            descricao=descricao,
            ex_tipi=ex_tipi,
        )
        if resultado_monofasico.get("status") != "NÃO ENQUADRADO":
            confirmado = bool(resultado_monofasico.get("confirmado"))
            return ResultadoPISCOFINSNacional(
                ncm=codigo,
                status=str(resultado_monofasico.get("status") or ""),
                enquadramento=str(resultado_monofasico.get("enquadramento") or ""),
                confirmado=confirmado,
                exige_revisao=bool(resultado_monofasico.get("exige_revisao", True)),
                cst_pis=str(resultado_monofasico.get("cst_pis") or ""),
                aliquota_pis=float(resultado_monofasico.get("aliquota_pis") or 0.0),
                cst_cofins=str(resultado_monofasico.get("cst_cofins") or ""),
                aliquota_cofins=float(resultado_monofasico.get("aliquota_cofins") or 0.0),
                regime_apuracao=regime,
                fundamento=str(resultado_monofasico.get("fundamento") or ""),
                artigo=str(resultado_monofasico.get("artigo") or ""),
                fonte_url=str(resultado_monofasico.get("fonte_url") or URL_TABELA_4310),
                tabela_efd="4.3.10 — CST 02/04",
                observacao=str(resultado_monofasico.get("observacao") or ""),
                confiabilidade=100.0 if confirmado else 85.0,
                codigo_legal=str(resultado_monofasico.get("codigo_legal") or ""),
            ).para_dict()

        return cls._analisar_padrao_por_regime(codigo, operacao, regime)

    @staticmethod
    def aplicar_ao_parecer(parecer: Any, resultado: Dict[str, Any]) -> Any:
        """Anexa ao parecer a conclusão nacional sem transformar sugestão em regra confirmada.

        Resultados confirmados (por exemplo, exportação ou monofásico já enquadrado)
        podem preencher a tributação exibida. Já o padrão por regime permanece
        explicitamente identificado como *sugestão condicional*, mas deixa de aparecer
        como CST/alíquota simplesmente ausentes na Ficha Inteligente.
        """
        if parecer is None or not resultado:
            return parecer

        tributacao = parecer.tributacao_atual
        parecer.regras_aplicadas["piscofins_nacional"] = dict(resultado)

        fundamento = str(resultado.get("fundamento") or "").strip()
        artigo = str(resultado.get("artigo") or "").strip()
        base = " — ".join(parte for parte in (fundamento, artigo) if parte)
        if base and base not in parecer.base_legal:
            parecer.base_legal.append(base)

        fonte = str(resultado.get("fonte_url") or "").strip()
        if fonte and fonte not in parecer.fontes:
            parecer.fontes.append(fonte)

        status = str(resultado.get("status") or "").strip()
        tributacao["Status PIS/COFINS"] = status or "Revisar"

        if bool(resultado.get("confirmado")):
            cst_pis = str(resultado.get("cst_pis") or "").strip()
            cst_cofins = str(resultado.get("cst_cofins") or "").strip()
            revisao_manual = bool(tributacao.get("Revisão manual"))
            if not revisao_manual:
                if cst_pis:
                    tributacao["CST PIS"] = cst_pis
                    tributacao["PIS"] = float(resultado.get("aliquota_pis") or 0.0)
                if cst_cofins:
                    tributacao["CST COFINS"] = cst_cofins
                    tributacao["COFINS"] = float(resultado.get("aliquota_cofins") or 0.0)
                if base:
                    tributacao["Fonte PIS/COFINS"] = base
            else:
                tributacao["PIS/COFINS nacional — comparação"] = (
                    f"PIS CST {cst_pis or '-'} / {float(resultado.get('aliquota_pis') or 0.0):.2f}% | "
                    f"COFINS CST {cst_cofins or '-'} / {float(resultado.get('aliquota_cofins') or 0.0):.2f}%"
                )
                aviso = "Existe regra manual salva; a conclusão nacional de PIS/COFINS foi mantida para comparação e não sobrescreveu os valores manuais."
                if aviso not in parecer.alertas:
                    parecer.alertas.append(aviso)

            conclusao = (
                f"PIS/COFINS: {status}. "
                f"{str(resultado.get('observacao') or '').strip()}"
            ).strip()
            if conclusao and conclusao not in parecer.conclusoes:
                parecer.conclusoes.insert(0, conclusao)
            parecer.versao_motor = "17.8.4"
            return parecer

        sugestao_pis = str(resultado.get("sugestao_cst_pis") or "").strip()
        sugestao_cofins = str(resultado.get("sugestao_cst_cofins") or "").strip()
        if sugestao_pis or sugestao_cofins:
            tributacao["CST PIS sugerido"] = sugestao_pis or "Não informado"
            tributacao["PIS sugerido"] = float(resultado.get("sugestao_aliquota_pis") or 0.0)
            tributacao["CST COFINS sugerido"] = sugestao_cofins or "Não informado"
            tributacao["COFINS sugerido"] = float(resultado.get("sugestao_aliquota_cofins") or 0.0)
            tributacao["Fonte PIS/COFINS sugerida"] = base or fonte or "Motor nacional PIS/COFINS"

            regime = str(resultado.get("regime_apuracao") or "regime informado").strip()
            conclusao = (
                "PIS/COFINS: o produto não foi confirmado em regime especial pelo motor, "
                f"e o padrão do {regime} foi calculado como sugestão condicional: "
                f"PIS CST {sugestao_pis or '-'} / "
                f"{float(resultado.get('sugestao_aliquota_pis') or 0.0):.2f}% e "
                f"COFINS CST {sugestao_cofins or '-'} / "
                f"{float(resultado.get('sugestao_aliquota_cofins') or 0.0):.2f}%."
            )
            if conclusao not in parecer.conclusoes:
                parecer.conclusoes.insert(0, conclusao)

            pendencia = (
                "Confirmar, antes de aplicar a sugestão padrão de PIS/COFINS, se a operação "
                "não está sujeita a alíquota zero, suspensão, isenção, substituição, regime "
                "monofásico ou outra regra setorial específica."
            )
            if pendencia not in parecer.pendencias:
                parecer.pendencias.append(pendencia)

        parecer.versao_motor = "17.8.4"
        return parecer

    @staticmethod
    def fontes_oficiais() -> Tuple[Dict[str, str], ...]:
        """Retorna o catálogo das tabelas oficiais consideradas pelo motor."""
        return FONTES_OFICIAIS
