"""Motor conservador de ICMS para operações relacionadas a Minas Gerais.

Sprint 16.6.0

O serviço separa quatro perguntas que não devem ser confundidas:
1. qual é a alíquota nominal da operação;
2. se existe enquadramento de ICMS-ST no Anexo VII;
3. se existe benefício fiscal objetivamente reconhecível;
4. quais pontos ainda exigem conferência humana.

Nenhuma alíquota geral é gravada como regra definitiva por NCM. A alíquota de
18% é tratada como padrão residual das operações internas de MG e permanece
condicional quando o produto pode estar em hipótese específica do Anexo I.
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.icms_st_mg_service import ICMSSTMGService


URL_RICMS_MG = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms2023/sumario2023.html"
)
URL_ANEXO_I = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms2023/anexoi2023.pdf"
)
URL_ANEXO_II = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms2023/anexoii2023.pdf"
)
URL_ANEXO_VII = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms2023/anexovii2023.pdf"
)
URL_RESOLUCAO_SENADO_22 = "https://legis.senado.leg.br/norma/586152/publicacao/15646891"
URL_RESOLUCAO_SENADO_13 = "https://legis.senado.leg.br/norma/586999/publicacao/15839317"

REFERENCIA_RICMS = "RICMS/MG/2023 — consulta estruturada da Sprint 16.6"

UFS_NORTE = {"AC", "AP", "AM", "PA", "RO", "RR", "TO"}
UFS_NORDESTE = {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"}
UFS_CENTRO_OESTE = {"DF", "GO", "MT", "MS"}
UFS_SUL = {"PR", "RS", "SC"}
UFS_SUDESTE = {"ES", "MG", "RJ", "SP"}
UFS_7_DESTINO = UFS_NORTE | UFS_NORDESTE | UFS_CENTRO_OESTE | {"ES"}
UFS_ORIGEM_7 = UFS_SUL | {"MG", "RJ", "SP"}
UFS_BRASIL = UFS_NORTE | UFS_NORDESTE | UFS_CENTRO_OESTE | UFS_SUL | UFS_SUDESTE


@dataclass(frozen=True)
class ResultadoICMSMG:
    ncm: str
    status: str
    confirmado: bool
    exige_revisao: bool
    tipo_operacao: str = ""
    aliquota_nominal: Optional[float] = None
    aliquota_confirmada: bool = False
    aliquota_status: str = ""
    fundamento_aliquota: str = ""
    fonte_aliquota: str = ""
    beneficio_status: str = "NÃO IDENTIFICADO AUTOMATICAMENTE"
    beneficio: str = ""
    reducao_base_percentual: Optional[float] = None
    fundamento_beneficio: str = ""
    fonte_beneficio: str = ""
    st_status: str = ""
    st_confirmado: bool = False
    st_decisao_confirmada: bool = False
    st_exige_revisao: bool = True
    st_potencial: bool = False
    cest: str = ""
    cest_sugerido: str = ""
    segmento_st: str = ""
    mva_original: Optional[float] = None
    mva_sugerida: Optional[float] = None
    mva_texto_st: str = ""
    ambito_st: str = ""
    aplicacao_st: str = ""
    observacao_st: str = ""
    observacao: str = ""
    confiabilidade_aliquota: float = 0.0
    confiabilidade_st: float = 0.0
    cobertura_st_registros: int = 0
    cobertura_st_segmentos: int = 0
    cobertura_st_completa: bool = False
    cobertura_st_versao_schema: int = 0
    cobertura_st_atualizada_em: str = ""
    cobertura_st_referencia: str = ""
    data_operacao: str = ""

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ICMSMGNacionalService:
    """Analisa alíquota nominal, ST e benefícios sem inventar regra por NCM."""

    @staticmethod
    def _normalizar_ncm(valor: Any) -> str:
        codigo = "".join(c for c in str(valor or "") if c.isdigit())
        if len(codigo) != 8:
            raise ValueError("O NCM deve possuir 8 dígitos.")
        return codigo

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return " ".join(texto.split())

    @staticmethod
    def _normalizar_uf(valor: Any) -> str:
        uf = str(valor or "").strip().upper()
        if uf and uf not in UFS_BRASIL:
            raise ValueError(f"UF inválida: {uf}.")
        return uf

    @staticmethod
    def _booleano(valor: Any) -> bool:
        if isinstance(valor, bool):
            return valor
        texto = str(valor or "").strip().upper()
        return texto in {"1", "SIM", "S", "TRUE", "VERDADEIRO", "YES"}

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
    def _tipo_operacao(cls, origem: str, destino: str) -> str:
        if not origem or not destino:
            return "CONTEXTO INCOMPLETO"
        if origem == destino:
            return "INTERNA"
        return "INTERESTADUAL"

    @classmethod
    def _aliquota_interna_mg(
        cls,
        ncm: str,
        descricao: str,
        st: Dict[str, Any],
    ) -> Tuple[float, str, bool, float, str, str]:
        """Retorna alíquota, status, confirmação, confiança, fundamento e fonte."""

        # Hipóteses objetivas do Anexo I que podem ser reconhecidas por posição NCM.
        if ncm[:4] in {"3303", "3304", "3305", "3306", "3307"}:
            return (
                25.0,
                "CONFIRMADA PELO ANEXO I — PERFUMARIA/HIGIENE/COSMÉTICOS",
                True,
                100.0,
                "RICMS/MG/2023, Anexo I, Parte 1, subitem 9.7",
                URL_ANEXO_I,
            )

        # Veículos dos capítulos 25 e 26 do Anexo VII possuem alíquota interna de 12%.
        segmento = cls._normalizar_texto(st.get("segmento"))
        if segmento in {
            "VEICULOS AUTOMOTORES",
            "VEICULOS DE DUAS E TRES RODAS MOTORIZADOS",
        }:
            return (
                12.0,
                "CONFIRMADA PELO ANEXO I — VEÍCULO DO ANEXO VII",
                True,
                100.0,
                "RICMS/MG/2023, Anexo I, Parte 1, subitem 4.3",
                URL_ANEXO_I,
            )

        # Regra residual: não é prova de que o produto não possui alíquota específica.
        return (
            18.0,
            "PADRÃO RESIDUAL — REVISAR EXCEÇÕES DO ANEXO I",
            False,
            70.0,
            "RICMS/MG/2023, Anexo I, Parte 1, subitem 7.1",
            URL_ANEXO_I,
        )

    @classmethod
    def _aliquota_interestadual(
        cls,
        origem: str,
        destino: str,
        importada: bool,
        excecao_importada: bool,
    ) -> Tuple[float, str, bool, float, str, str]:
        if importada:
            if excecao_importada:
                return (
                    12.0,
                    "REVISAR — MERCADORIA IMPORTADA INFORMADA COM EXCEÇÃO À ALÍQUOTA DE 4%",
                    False,
                    55.0,
                    "Resolução do Senado Federal nº 13/2012, art. 1º, § 4º",
                    URL_RESOLUCAO_SENADO_13,
                )
            return (
                4.0,
                "CONDICIONAL — IMPORTADO/CONTEÚDO DE IMPORTAÇÃO SUPERIOR A 40%",
                False,
                85.0,
                "Resolução do Senado Federal nº 13/2012, art. 1º",
                URL_RESOLUCAO_SENADO_13,
            )

        if origem in UFS_ORIGEM_7 and destino in UFS_7_DESTINO:
            return (
                7.0,
                "CONFIRMADA — REGRA INTERESTADUAL 7%",
                True,
                100.0,
                "Resolução do Senado Federal nº 22/1989, art. 1º, parágrafo único",
                URL_RESOLUCAO_SENADO_22,
            )

        return (
            12.0,
            "CONFIRMADA — REGRA INTERESTADUAL 12%",
            True,
            100.0,
            "Resolução do Senado Federal nº 22/1989, art. 1º",
            URL_RESOLUCAO_SENADO_22,
        )

    @classmethod
    def _beneficio_pneumaticos(
        cls,
        ncm: str,
        contexto: Dict[str, Any],
        tipo_operacao: str,
        aliquota: Optional[float],
    ) -> Dict[str, Any]:
        if not (ncm.startswith("4011") or ncm.startswith("4013")):
            return {}

        perfil = cls._normalizar_texto(contexto.get("perfil_remetente"))
        operacao = cls._normalizar_texto(contexto.get("operacao"))
        finalidade = cls._normalizar_texto(contexto.get("finalidade"))
        consumidor_final = cls._booleano(contexto.get("consumidor_final"))

        if tipo_operacao != "INTERESTADUAL":
            return {
                "status": "NÃO APLICÁVEL À OPERAÇÃO INFORMADA",
                "beneficio": "Anexo II, item 30 — pneumáticos e câmaras",
                "observacao": "O item 30 alcança saída interestadual promovida por fabricante ou importador.",
            }

        if not any(chave in perfil for chave in ("FABRICANTE", "IMPORTADOR")):
            return {
                "status": "POSSÍVEL BENEFÍCIO — PERFIL DO REMETENTE NÃO CONFIRMADO",
                "beneficio": "Anexo II, item 30 — pneumáticos e câmaras",
                "observacao": "Informe se o remetente é fabricante ou importador.",
            }

        impedimento = (
            "TRANSFER" in operacao
            or "INDUSTR" in finalidade
            or "RETORNO" in operacao
            or "REMESSA" in operacao
            or consumidor_final
        )
        if impedimento:
            return {
                "status": "NÃO APLICÁVEL PELAS CONDIÇÕES INFORMADAS",
                "beneficio": "Anexo II, item 30 — pneumáticos e câmaras",
                "observacao": (
                    "O benefício não se aplica a transferência, industrialização, remessa com retorno "
                    "ou venda/faturamento direto a consumidor final."
                ),
            }

        percentuais = {12.0: 9.30, 7.0: 8.78, 4.0: 8.50}
        reducao = percentuais.get(float(aliquota)) if aliquota is not None else None
        if reducao is None:
            return {
                "status": "REVISAR ALÍQUOTA PARA DEFINIR A REDUÇÃO",
                "beneficio": "Anexo II, item 30 — pneumáticos e câmaras",
                "observacao": "A redução varia conforme a alíquota interestadual de 12%, 7% ou 4%.",
            }

        return {
            "status": "CONFIRMADO CONFORME O CONTEXTO INFORMADO",
            "beneficio": "Redução de base de cálculo — pneumáticos e câmaras",
            "reducao": reducao,
            "fundamento": "RICMS/MG/2023, Anexo II, Parte 1, item 30",
            "fonte": URL_ANEXO_II,
            "observacao": (
                "A confirmação depende de o remetente ser fabricante/importador e de a receita "
                "estar sujeita ao PIS/Cofins nos termos da Lei nº 10.485/2002."
            ),
        }

    @classmethod
    def analisar(
        cls,
        ncm: Any,
        contexto: Optional[Dict[str, Any]] = None,
        descricao: str = "",
    ) -> Dict[str, Any]:
        codigo = cls._normalizar_ncm(ncm)
        contexto = dict(contexto or {})
        origem = cls._normalizar_uf(contexto.get("uf_origem"))
        destino = cls._normalizar_uf(contexto.get("uf_destino"))
        data_operacao = cls._data_operacao(contexto)
        tipo = cls._tipo_operacao(origem, destino)
        importada = cls._booleano(contexto.get("mercadoria_importada"))
        excecao_importada = cls._booleano(contexto.get("excecao_aliquota_importacao"))

        st = ICMSSTMGService.analisar(codigo, contexto=contexto, descricao=descricao)

        aliquota: Optional[float] = None
        aliquota_status = "INFORME UF DE ORIGEM E DESTINO"
        aliquota_confirmada = False
        confianca_aliquota = 0.0
        fundamento_aliquota = ""
        fonte_aliquota = ""

        if origem and destino:
            if origem == destino == "MG":
                (
                    aliquota,
                    aliquota_status,
                    aliquota_confirmada,
                    confianca_aliquota,
                    fundamento_aliquota,
                    fonte_aliquota,
                ) = cls._aliquota_interna_mg(codigo, descricao, st)
            elif origem != destino:
                (
                    aliquota,
                    aliquota_status,
                    aliquota_confirmada,
                    confianca_aliquota,
                    fundamento_aliquota,
                    fonte_aliquota,
                ) = cls._aliquota_interestadual(
                    origem, destino, importada, excecao_importada
                )
            else:
                aliquota_status = "OPERAÇÃO INTERNA FORA DE MINAS GERAIS — FORA DO ESCOPO"

        beneficio = cls._beneficio_pneumaticos(codigo, contexto, tipo, aliquota)

        cobertura = BaseOficialRepository.resumo_st_mg()
        st_confirmado = bool(st.get("confirmado"))
        st_exige_revisao = bool(st.get("exige_revisao", True))
        st_decisao = str(st.get("decisao_st") or "").strip().upper()
        st_nao_aplicavel_confirmado = bool(
            (st.get("nao_aplicavel") or st_decisao == "NAO")
            and not st_exige_revisao
        )
        st_decisao_confirmada = st_confirmado or st_nao_aplicavel_confirmado
        if st_decisao_confirmada:
            confianca_st = 100.0
        elif st.get("encontrado"):
            confianca_st = 70.0
        else:
            # Sem selo de base completa ou com residual ainda possível, a
            # ausência nominal continua pendente.
            confianca_st = 45.0

        observacoes = []
        if tipo == "INTERNA" and origem != "MG":
            observacoes.append("Operação interna de outra UF: a alíquota estadual não foi determinada pelo motor MG.")
        if tipo == "INTERESTADUAL" and "MG" not in {origem, destino}:
            observacoes.append("A alíquota interestadual foi calculada pela regra nacional; benefícios estaduais exigem consulta da UF competente.")
        if not aliquota_confirmada and aliquota is not None:
            observacoes.append("A alíquota apresentada é condicional e não será gravada automaticamente como regra definitiva.")
        if not st.get("encontrado"):
            if st_nao_aplicavel_confirmado:
                observacoes.append(
                    str(st.get("observacao") or "ICMS-ST/MG = NÃO conforme base oficial completa.")
                )
            else:
                observacoes.append(
                    str(st.get("observacao") or (
                        "ICMS-ST condicional: a ausência de NCM nominal ainda não é conclusiva. "
                        "Atualize a base ST/MG completa ou confirme a finalidade automotiva."
                    ))
                )
        if beneficio.get("observacao"):
            observacoes.append(str(beneficio["observacao"]))

        exige_revisao = (
            not aliquota_confirmada
            or st_exige_revisao
            or str(beneficio.get("status") or "").startswith("POSSÍVEL")
            or str(beneficio.get("status") or "").startswith("REVISAR")
        )
        confirmado = aliquota_confirmada and st_decisao_confirmada

        if st_confirmado:
            status = "ALÍQUOTA ANALISADA E ICMS-ST ENQUADRADO"
        elif st_nao_aplicavel_confirmado:
            status = "ALÍQUOTA ANALISADA — ICMS-ST NÃO APLICÁVEL"
        elif st.get("encontrado"):
            status = "ALÍQUOTA ANALISADA — ICMS-ST REQUER REVISÃO"
        else:
            status = "ALÍQUOTA ANALISADA — ICMS-ST CONDICIONAL; ATUALIZAR/CONFIRMAR"

        return ResultadoICMSMG(
            ncm=codigo,
            status=status,
            confirmado=confirmado,
            exige_revisao=exige_revisao,
            tipo_operacao=tipo,
            aliquota_nominal=aliquota,
            aliquota_confirmada=aliquota_confirmada,
            aliquota_status=aliquota_status,
            fundamento_aliquota=fundamento_aliquota,
            fonte_aliquota=fonte_aliquota,
            beneficio_status=str(beneficio.get("status") or "NÃO IDENTIFICADO AUTOMATICAMENTE"),
            beneficio=str(beneficio.get("beneficio") or ""),
            reducao_base_percentual=beneficio.get("reducao"),
            fundamento_beneficio=str(beneficio.get("fundamento") or ""),
            fonte_beneficio=str(beneficio.get("fonte") or ""),
            st_status=str(st.get("status") or ""),
            st_confirmado=st_confirmado,
            st_decisao_confirmada=st_decisao_confirmada,
            st_exige_revisao=st_exige_revisao,
            st_potencial=bool(st.get("potencial") or st.get("encontrado")),
            cest=str(st.get("cest") or ""),
            cest_sugerido=str(st.get("cest_sugerido") or ""),
            segmento_st=str(st.get("segmento") or ""),
            mva_original=st.get("mva_original"),
            mva_sugerida=st.get("mva_sugerida"),
            mva_texto_st=str(st.get("mva_texto") or ""),
            ambito_st=str(st.get("ambito") or ""),
            aplicacao_st=str(st.get("aplicacao_operacao") or ""),
            observacao_st=str(st.get("observacao") or ""),
            observacao=" ".join(observacoes),
            confiabilidade_aliquota=confianca_aliquota,
            confiabilidade_st=confianca_st,
            cobertura_st_registros=int(cobertura.get("registros") or 0),
            cobertura_st_segmentos=int(cobertura.get("segmentos") or 0),
            cobertura_st_completa=bool(cobertura.get("base_completa")),
            cobertura_st_versao_schema=int(cobertura.get("versao_schema") or 0),
            cobertura_st_atualizada_em=str(cobertura.get("sincronizado_em") or cobertura.get("atualizado_em") or ""),
            cobertura_st_referencia=str(cobertura.get("referencia") or ""),
            data_operacao=data_operacao.strftime("%d/%m/%Y"),
        ).para_dict()

    @staticmethod
    def aplicar_ao_ficha(ficha: Any, resultado: Dict[str, Any]) -> Any:
        if ficha is None:
            return ficha

        ficha.icms_mg_status = str(resultado.get("status") or "")
        ficha.icms_mg_confirmado = bool(resultado.get("aliquota_confirmada"))
        ficha.icms_mg_exige_revisao = bool(resultado.get("exige_revisao", True))
        ficha.icms_mg_tipo_operacao = str(resultado.get("tipo_operacao") or "")
        ficha.icms_mg_aliquota_nominal = float(resultado.get("aliquota_nominal") or 0.0)
        ficha.icms_mg_aliquota_status = str(resultado.get("aliquota_status") or "")
        ficha.icms_mg_fundamento = str(resultado.get("fundamento_aliquota") or "")
        ficha.icms_mg_fonte = str(resultado.get("fonte_aliquota") or "")
        ficha.icms_mg_observacoes = str(resultado.get("observacao") or "")
        ficha.icms_mg_confiabilidade = float(resultado.get("confiabilidade_aliquota") or 0.0)
        ficha.icms_mg_beneficio_status = str(resultado.get("beneficio_status") or "")
        ficha.icms_mg_beneficio = str(resultado.get("beneficio") or "")
        ficha.icms_mg_reducao_base = float(resultado.get("reducao_base_percentual") or 0.0)
        ficha.icms_mg_st_status = str(resultado.get("st_status") or "")
        ficha.icms_mg_st_confirmado = bool(resultado.get("st_confirmado"))
        ficha.icms_mg_cest = str(resultado.get("cest") or "")
        ficha.icms_mg_mva = float(resultado.get("mva_original") or 0.0)

        # Só altera a alíquota operacional quando a regra nominal foi confirmada.
        if resultado.get("aliquota_confirmada") and resultado.get("aliquota_nominal") is not None:
            ficha.icms = float(resultado["aliquota_nominal"])

        if resultado.get("st_confirmado"):
            ficha.icms_st = "SIM"
            if resultado.get("cest"):
                ficha.cest = "".join(c for c in str(resultado["cest"]) if c.isdigit())

        fonte = str(resultado.get("fonte_aliquota") or "").strip()
        if fonte and fonte not in ficha.fontes:
            ficha.fontes.append(fonte)
        fundamento = str(resultado.get("fundamento_aliquota") or "").strip()
        if fundamento and fundamento not in ficha.base_legal:
            ficha.base_legal.append(fundamento)
        return ficha
