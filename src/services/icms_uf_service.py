"""Motor conservador de ICMS por unidade da Federação.

Sprint 17.0.0 — primeira fase da expansão nacional.

Cobertura desta fase:
- Minas Gerais: preserva o motor detalhado já aprovado;
- Espírito Santo, Bahia, Rio de Janeiro, São Paulo, Pará, Goiás, Paraná, Santa Catarina, Rio Grande do Sul, Mato Grosso do Sul, Mato Grosso, Distrito Federal, Ceará, Pernambuco, Alagoas, Paraíba, Rio Grande do Norte, Sergipe, Maranhão e Piauí: alíquota modal oficial,
  alíquota interestadual, adicional de combate à pobreza em hipóteses
  objetivamente reconhecíveis e indício de enquadramento CEST/ST;
- nenhuma MVA de outra UF é inventada ou reaproveitada da tabela mineira.

A alíquota modal é uma referência legal geral. Ela permanece condicional para
um NCM específico enquanto não forem descartadas alíquotas especiais,
reduções, isenções, diferimentos e regimes especiais da operação concreta.
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from src.services.icms_mg_nacional_service import ICMSMGNacionalService
from src.services.icms_st_mg_service import ICMSSTMGService
from src.services.icms_st_uf_service import ICMSSTUFService


URL_CONFAZ_142 = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"
URL_RESOLUCAO_SENADO_22 = "https://legis.senado.leg.br/norma/586152/publicacao/15646891"
URL_RESOLUCAO_SENADO_13 = "https://legis.senado.leg.br/norma/586999/publicacao/15839317"
URL_SP_RICMS_ART_52 = "https://legislacao.fazenda.sp.gov.br/Paginas/art052.aspx"
URL_SP_FECOEP = "https://legislacao.fazenda.sp.gov.br/Paginas/lei16006.aspx"
URL_ES_LEI_7000 = (
    "https://www3.sefaz.es.gov.br/legislacao/doc_viewer?"
    "src=%2Flegislacao%2Fdoc%2FLEIS%2F2001%2FLEI+N.%C2%B0+7.000+-+Atualizada.htm"
)
URL_BA_LEI_7014 = (
    "https://mbusca.sefaz.ba.gov.br/DITRI/leis/leis_estaduais/"
    "legest_1996_7014_icmscomnotas.pdf"
)
URL_BA_FECOP_COSMETICOS = (
    "https://mbusca.sefaz.ba.gov.br/DITRI/normas_complementares/"
    "instrucoes_normativas/instnorm_2016_05.pdf"
)
URL_RJ_ALIQUOTAS = "https://portal.fazenda.rj.gov.br/pagamentos/aliquotas-internas/"
URL_PA_LEI_9755 = "https://www.ioepa.com.br/pages/2022/2022.12.16.DOE.pdf"
URL_PA_RICMS_PNEUMATICOS = "https://www.ioepa.com.br/pages/2022/2022.03.29.DOE.pdf"
URL_GO_MODAL_19 = "https://goias.gov.br/economia/wp-content/uploads/sites/45/2026/07/NOTA_TECNICA_MALHA_118.pdf"
URL_GO_DECRETO_10799 = "https://legisla.casacivil.go.gov.br/pesquisa_legislacao/111443/decreto-numerado-10799"
URL_GO_EXCLUSAO_AUTOPECAS = "https://goias.gov.br/economia/wp-content/uploads/sites/45/2018/03/manual-de-exclusAo-de-mercadorias-da-st-versao-2-3a7.pdf"
URL_PR_RICMS_MODAL = "https://www.legislacao.pr.gov.br/legislacao/listarAtosAno.do?action=exibir&anoSelecionado=2024&anoSpan=2024&codAto=321803&indice=4&isPaginado=true&mesSelecionado=3&totalRegistros=293"
URL_PR_FECOP = "https://www.fazenda.pr.gov.br/Pagina/Instrucoes-de-preenchimento-da-GR-PR"
URL_SC_RICMS = "https://legislacao.sef.sc.gov.br/html/regulamentos/icms/ricms_01_00.htm"
URL_SC_FUNDO_SOCIAL = "https://legislacao.sef.sc.gov.br/html/leis/2022/lei_22_18334.htm"
URL_RS_MODAL_17 = "https://www.estado.rs.gov.br/upload/arquivos/202602/apresentacao-do-avanco-historico-na-capacidade-de-pagamento-do-rs.pdf"
URL_RS_AMPARA = "https://atendimento.receita.rs.gov.br/fundo-de-combate-a-pobreza-ampara-e-a-ec-87-2015"
URL_RS_EXCLUSAO_AUTOPECAS = "https://atendimento.receita.rs.gov.br/qual-foi-a-legislacao-alterada-relativa-a-exclusao-dos-produtos-da-st-a-partir-de-1-de-novembro-de-24"
URL_MS_LEI_1810 = "https://aacpdappls.net.ms.gov.br/appls/legislacao/secoge/govato.nsf/448b683bce4ca84704256c0b00651e9d/037448c46af3acaf04256d410048094b?OpenDocument="
URL_MS_RICMS = "https://aacpdappls.net.ms.gov.br/appls/legislacao/secoge/govato.nsf/fd8600de8a55c7fc04256b210079ce25/9c9e3a59ea627ab40425715300728e6a"
URL_MT_LEI_7098 = "https://app1.sefaz.mt.gov.br/Sistema/legislacao/legislacaotribut.nsf/c83fc8b160f5810b032567550064fd41/cc9c3b9886404baa0325678b0043a842"
URL_MT_PORTARIA_195 = "https://app1.sefaz.mt.gov.br/Sistema/legislacao/legislacaotribut.nsf/07fa81bed2760c6b84256710004d3940/4c7283a0b4318486042584c4004436c1"
URL_DF_LEI_1254 = "https://www.sinj.df.gov.br/sinj/Norma/49208/Lei_1254_08_11_1996.html"
URL_DF_RICMS = "https://www.sinj.df.gov.br/sinj/Norma/33077/Decreto_18955_22_12_1997.html"
URL_DF_FCP = "https://www.sinj.df.gov.br/sinj/Norma/58833/Lei_4220_2008.html"
URL_CE_LEI_18665 = "https://sefazlegis.sefaz.ce.gov.br/api/openFile?id=a131b7f7-c712-47a5-843f-57a37b11d319"
URL_CE_DECRETO_30519 = "https://sefazlegis.sefaz.ce.gov.br/api/openFile?id=d5e33d14-7888-4f67-8687-a18f4f657953"
URL_CE_RICMS = "https://sefazlegis.sefaz.ce.gov.br/api/openFile?id=6e01bfd1-bbd2-49d3-bc27-0d44b5147803"
URL_PE_RICMS = "https://www.sefaz.pe.gov.br/Legislacao/Tributaria/Documents/legislacao/44650/texto/Dec44650_2017.htm"
URL_PE_AUTOPECAS_MVA = "https://www.sefaz.pe.gov.br/Legislacao/Tributaria/Documents/Legislacao/Tabelas/Tabela%20MVA%20Autope%C3%A7as.pdf"
URL_PE_PNEUS_MVA = "https://www.sefaz.pe.gov.br/Legislacao/Tributaria/Documents/Legislacao/Tabelas/Tabela%20MVA%20Pneus%20e%20C%C3%A2maras%20de%20Ar.pdf"
URL_PE_FECEP = "https://www.sefaz.pe.gov.br/Legislacao/Tributaria/Documents/Legislacao/Leis_Tributarias/2003/Lei12523_2003.htm"
URL_AL_LEI_9776 = "https://sapl.al.al.leg.br/media/sapl/public/normajuridica/2025/3699/lei_no_9.776_de_22_de_dezembro_de_2025.pdf"
URL_AL_FECOEP = "https://sapl.al.al.leg.br/sapl_documentos/norma_juridica/746_texto_integral"
URL_AL_FECOEP_9440 = "https://sapl.al.al.leg.br/media/sapl/public/normajuridica/2024/3246/lei_no_9.440_de_27_de_dezembro_de_2024_2_-_ultima_publicacao.pdf"
URL_PB_LEI_6379 = "https://www.sefaz.pb.gov.br/legislacao/64-leis/icms/13798-lei-n-6-379-de-2-de-dezembro-de-1996-atualizada-em-06-09-2023"
URL_PB_ANEXO_05 = "https://www.sefaz.pb.gov.br/attachments/article/1519/ANEXO%20%2005%20REL.%20MERC.EF.%20SUBST.%20TRIB.%20E%20RESP.%20TAX.%20VAL.%20%20AGREG.%20NR%20A%20PARTIR%20DE%2001.01.2024%20%20-%20ATUALIZADO%20EM%2009.07.2025.pdf"
URL_PB_FUNCEP = "https://www.sefaz.pb.gov.br/legislacao/64-leis/icms/7765-lei-n-7-611-de-30-de-junho-de-2005?format=pdf&tmpl=component"
URL_RN_LEI_11999 = "https://www.al.rn.leg.br/storage/legislacao/2025/stqpzaxnkhj8e1efdy6wnsk815m85v.pdf"
URL_RN_RICMS = "https://www.diariooficial.rn.gov.br/dei/dorn3/documentos/00000001/20220819/783131.htm"
URL_RN_ANEXO_005 = "https://www.diariooficial.rn.gov.br/dei/dorn3/documentos/00000001/20220819/783140.htm"
URL_RN_ANEXO_007 = "https://www.diariooficial.rn.gov.br/dei/dorn3/documentos/00000001/20220819/783145.htm"
URL_SE_RICMS = "https://api.legislacao.se.gov.br/uploads/atos/31521/DN-21400-2002-atualizado-DN-1467-2026.pdf"
URL_MA_LEGISLACAO = "https://www.ma.gov.br/servicos/consultar-legislacao-da-sefaz"
URL_MA_FUMACOP = "https://seplan.ma.gov.br/uploads/seplan/docs/cartilha_fumacop_2009.pdf"
URL_PI_RICMS = "https://www.diario.pi.gov.br/doe/files/diarios/anexo/5714d565-bd46-4f50-950d-7fa74dbdc549/DIARIO-OFICIAL-DO-ESTADO-DO-PIAUI-PUBLICACAO-N-47.pdf"
URL_PI_DECRETO_24244 = "https://www.diario.pi.gov.br/doe/files/diarios/anexo/e9755fe8-4b41-44be-a6f4-520a386f3b2f/DOEPI_240_2025.pdf"
URL_PI_MODAL_225 = "https://portal-admin.sefaz.pi.gov.br/wp-content/uploads/2025/03/SEI_GOV-PI-017374270-SEFAZ_-Comunicado-UNATRI.pdf"
URL_PI_FECOP = "https://www.sefaz.pi.gov.br/images/Documentos/novo_ICMS_2016.pdf"
URL_TO_LEI_1287 = "https://www.al.to.leg.br/arquivos/lei_1287-2001_68306.PDF"
URL_TO_LEI_4141 = "https://www.al.to.leg.br/arquivos/lei_4141-2023_62676.PDF"
URL_TO_LEI_1201 = "https://www.al.to.leg.br/arquivos/lei_1201-2000_51051.PDF"

URL_AC_IN_DIAT_01_2023 = "https://sefaz.ac.gov.br/2021/?p=16417"
URL_AC_PROTOCOLO_41 = "https://www.confaz.fazenda.gov.br/legislacao/protocolos/2008/pt041_08"
URL_AM_LEI_6108 = "https://sistemas.sefaz.am.gov.br/get/Normas.do?metodo=viewDoc&uuidDoc=84be7172-451e-4ca0-802e-1a0303e5f0b2"
URL_AM_LC_242 = "https://sistemas.sefaz.am.gov.br/silt/norma/lei-complementar/0569a7de-c88a-4bc1-b895-6aaccb7f88b7/lei-complementar-n-242-de-29-de-dezembro-de-2022"
URL_AP_RICMS = "https://www.sefaz.ap.gov.br/"
URL_RO_RICMS = "https://legislacao.sefin.ro.gov.br/"
URL_RO_DECRETO_29048 = "https://legislacao.sefin.ro.gov.br/"
UFS_NORTE = {"AC", "AP", "AM", "PA", "RO", "RR", "TO"}
UFS_NORDESTE = {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"}
UFS_CENTRO_OESTE = {"DF", "GO", "MT", "MS"}
UFS_SUL = {"PR", "RS", "SC"}
UFS_SUDESTE = {"ES", "MG", "RJ", "SP"}
UFS_BRASIL = UFS_NORTE | UFS_NORDESTE | UFS_CENTRO_OESTE | UFS_SUL | UFS_SUDESTE
UFS_DESTINO_7 = UFS_NORTE | UFS_NORDESTE | UFS_CENTRO_OESTE | {"ES"}
UFS_ORIGEM_7 = UFS_SUL | {"MG", "RJ", "SP"}
UFS_COBERTURA = ("MG", "ES", "BA", "RJ", "SP", "PA", "GO", "PR", "SC", "RS", "MS", "MT", "DF", "CE", "PE", "AL", "PB", "RN", "SE", "MA", "PI", "TO", "AC", "AM", "AP", "RO")


@dataclass(frozen=True)
class ResultadoICMSUF:
    ncm: str
    uf_origem: str
    uf_destino: str
    data_operacao: str
    tipo_operacao: str
    status: str
    confirmado: bool
    exige_revisao: bool
    aliquota_operacao: Optional[float] = None
    aliquota_operacao_status: str = ""
    aliquota_operacao_confirmada: bool = False
    aliquota_interna_destino: Optional[float] = None
    aliquota_interna_status: str = ""
    aliquota_interna_confirmada: bool = False
    aliquota_total_consumidor: Optional[float] = None
    fcp: Optional[float] = None
    fcp_status: str = ""
    fcp_confirmado: bool = False
    st_status: str = ""
    st_potencial: bool = False
    st_confirmado: bool = False
    st_decisao_confirmada: bool = False
    cest: str = ""
    segmento_st: str = ""
    descricao_legal_st: str = ""
    mva_original: Optional[float] = None
    mva_ajustada: Optional[float] = None
    mva_aplicada: Optional[float] = None
    mva_tipo: str = ""
    st_modelo_calculo: str = ""
    carga_liquida_st: Optional[float] = None
    carga_liquida_status: str = ""
    antecipacao_percentual: Optional[float] = None
    antecipacao_status: str = ""
    st_vigencia_inicio: str = ""
    st_vigencia_fim: str = ""
    st_responsabilidade: str = ""
    st_acordo_status: str = ""
    contrato_fidelidade: bool = False
    beneficio_status: str = "NÃO AUTOMATIZADO NESTA FASE"
    confiabilidade_aliquota: float = 0.0
    confiabilidade_fcp: float = 0.0
    confiabilidade_st: float = 0.0
    fundamento_aliquota: str = ""
    fundamento_fcp: str = ""
    fundamento_st: str = ""
    fonte_aliquota: str = ""
    fonte_fcp: str = ""
    fonte_st: str = ""
    observacao: str = ""

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ICMSUFService:
    """Consulta ICMS próprio, FCP e indícios de ST para as UFs cobertas."""

    @staticmethod
    def _normalizar_ncm(valor: Any) -> str:
        codigo = "".join(c for c in str(valor or "") if c.isdigit())
        if len(codigo) != 8:
            raise ValueError("O NCM deve possuir 8 dígitos.")
        return codigo

    @staticmethod
    def _normalizar_uf(valor: Any) -> str:
        uf = str(valor or "").strip().upper()
        if uf not in UFS_BRASIL:
            raise ValueError(f"UF inválida: {uf or '(vazia)' }.")
        return uf

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return " ".join(texto.split())

    @staticmethod
    def _booleano(valor: Any) -> bool:
        if isinstance(valor, bool):
            return valor
        return str(valor or "").strip().upper() in {
            "1", "SIM", "S", "TRUE", "VERDADEIRO", "YES",
        }

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
    def _aliquota_interestadual(
        cls,
        origem: str,
        destino: str,
        importada: bool,
        excecao_importada: bool,
    ) -> Dict[str, Any]:
        if origem == destino:
            return {
                "aliquota": None,
                "status": "NÃO APLICÁVEL À OPERAÇÃO INTERNA",
                "confirmada": True,
                "confiabilidade": 100.0,
                "fundamento": "Operação interna.",
                "fonte": "",
            }
        if importada:
            if excecao_importada:
                return {
                    "aliquota": 12.0,
                    "status": "REVISAR — EXCEÇÃO INFORMADA À ALÍQUOTA INTERESTADUAL DE 4%",
                    "confirmada": False,
                    "confiabilidade": 55.0,
                    "fundamento": "Resolução do Senado Federal nº 13/2012, art. 1º, § 4º.",
                    "fonte": URL_RESOLUCAO_SENADO_13,
                }
            return {
                "aliquota": 4.0,
                "status": "CONDICIONAL — IMPORTADO OU CONTEÚDO DE IMPORTAÇÃO SUPERIOR A 40%",
                "confirmada": False,
                "confiabilidade": 85.0,
                "fundamento": "Resolução do Senado Federal nº 13/2012.",
                "fonte": URL_RESOLUCAO_SENADO_13,
            }
        aliquota = 7.0 if origem in UFS_ORIGEM_7 and destino in UFS_DESTINO_7 else 12.0
        return {
            "aliquota": aliquota,
            "status": f"CONFIRMADA — REGRA INTERESTADUAL DE {aliquota:.0f}%",
            "confirmada": True,
            "confiabilidade": 100.0,
            "fundamento": "Resolução do Senado Federal nº 22/1989.",
            "fonte": URL_RESOLUCAO_SENADO_22,
        }

    @staticmethod
    def _ncm_em_prefixos(ncm: str, prefixos: Tuple[str, ...]) -> bool:
        return any(ncm.startswith(prefixo) for prefixo in prefixos)

    @classmethod
    def _fcp_sp(cls, ncm: str, consumidor_final: bool) -> Dict[str, Any]:
        alcancado = ncm.startswith("2203") or ncm.startswith("24")
        if alcancado and consumidor_final:
            return {
                "aliquota": 2.0,
                "status": "CONFIRMADO — FECOEP/SP PARA CONSUMIDOR FINAL",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": "Lei paulista nº 16.006/2015, art. 2º; RICMS/SP, art. 56-C.",
                "fonte": URL_SP_FECOEP,
            }
        if alcancado:
            return {
                "aliquota": 2.0,
                "status": "CONDICIONAL — INFORME SE A DESTINAÇÃO É A CONSUMIDOR FINAL",
                "confirmado": False,
                "confiabilidade": 65.0,
                "fundamento": "Lei paulista nº 16.006/2015, art. 2º.",
                "fonte": URL_SP_FECOEP,
            }
        return {
            "aliquota": 0.0,
            "status": "NÃO APLICÁVEL A ESTE NCM NA REGRA OBJETIVA INSTALADA",
            "confirmado": True,
            "confiabilidade": 100.0,
            "fundamento": "FECOEP/SP restrito, nesta regra, à posição 2203 e ao capítulo 24.",
            "fonte": URL_SP_FECOEP,
        }

    @classmethod
    def _fcp_es(cls, ncm: str) -> Dict[str, Any]:
        bebidas = cls._ncm_em_prefixos(ncm, ("2203", "2204", "2205", "2206", "220720", "2208"))
        fumo = ncm.startswith("24")
        if bebidas or fumo:
            return {
                "aliquota": 2.0,
                "status": "CONFIRMADO — FUNDO DE COMBATE À POBREZA/ES",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": "Lei ES nº 7.000/2001, arts. 20, IV, d/e, e 20-A.",
                "fonte": URL_ES_LEI_7000,
            }
        return {
            "aliquota": 0.0,
            "status": "NÃO APLICÁVEL ÀS HIPÓTESES OBJETIVAS DO ART. 20-A",
            "confirmado": True,
            "confiabilidade": 100.0,
            "fundamento": "Lei ES nº 7.000/2001, art. 20-A.",
            "fonte": URL_ES_LEI_7000,
        }

    @classmethod
    def _fcp_ba(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        texto = cls._normalizar_texto(descricao)
        bebidas = cls._ncm_em_prefixos(ncm, ("2202", "2203", "2204", "2205", "2206", "2207", "2208"))
        fumo = ncm.startswith("24")
        cosmeticos = cls._ncm_em_prefixos(
            ncm,
            ("33041", "330420", "33043", "330491", "330499", "33052", "33053", "33059", "33073"),
        )
        descricao_bebida = any(chave in texto for chave in ("ISOTON", "ENERGET", "REFRIGER", "CERVEJA", "CHOPE"))
        if bebidas or fumo or cosmeticos or descricao_bebida:
            fonte = URL_BA_FECOP_COSMETICOS if cosmeticos else URL_BA_LEI_7014
            return {
                "aliquota": 2.0,
                "status": "ENQUADRAMENTO FECOP/BA RECONHECIDO — REVISAR ALÍQUOTA INTERNA ESPECÍFICA",
                "confirmado": True,
                "confiabilidade": 90.0,
                "fundamento": "Lei BA nº 7.014/1996, art. 16-A e lista aplicável.",
                "fonte": fonte,
            }

        # Para os segmentos automotivos estruturados nesta fase, a própria Lei 7.014/96
        # permite confirmar que o adicional do art. 16-A não se aplica: autopeças e
        # pneumáticos não integram os incisos II, IV, V e VII do art. 16 nem a lista
        # adicional do parágrafo único do art. 16-A. Mantemos os demais NCMs em revisão.
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FECOP/BA NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 98.0,
                "fundamento": "Lei BA nº 7.014/1996, arts. 16 e 16-A.",
                "fonte": URL_BA_LEI_7014,
            }
        return {
            "aliquota": 0.0,
            "status": "NÃO IDENTIFICADO AUTOMATICAMENTE — REVISAR A LISTA DO FECOP/BA",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei BA nº 7.014/1996, art. 16-A.",
            "fonte": URL_BA_LEI_7014,
        }

    @classmethod
    def _fcp_pa(cls) -> Dict[str, Any]:
        return {
            "aliquota": 0.0,
            "status": "NÃO AUTOMATIZADO — REVISAR FCP/FUNDO DO PARÁ",
            "confirmado": False,
            "confiabilidade": 40.0,
            "fundamento": (
                "A cobertura estadual 17.8.39 não estrutura adicional/FCP do Pará. "
                "Validar a hipótese e a legislação vigente antes de aplicar."
            ),
            "fonte": "",
        }

    @classmethod
    def _fcp_go(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """PROTEGE/GO: adicional de até 2% existe para bens/serviços supérfluos;
        a lista completa por NCM ainda não é automatizada nesta cobertura.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "PROTEGE/GO NÃO IDENTIFICADO NO ESCOPO AUTOMOTIVO INSTALADO — REVISAR EXCEÇÕES",
                "confirmado": False,
                "confiabilidade": 75.0,
                "fundamento": (
                    "O adicional de até 2% do Fundo PROTEGE/GO alcança produtos e serviços "
                    "supérfluos definidos na legislação estadual. A cobertura automotiva 17.8.44 "
                    "não presume incidência sem enquadramento objetivo na lista legal."
                ),
                "fonte": URL_GO_MODAL_19,
            }
        return {
            "aliquota": 0.0,
            "status": "NÃO AUTOMATIZADO — REVISAR ADICIONAL PROTEGE/GO",
            "confirmado": False,
            "confiabilidade": 45.0,
            "fundamento": "Validar eventual adicional de até 2% destinado ao Fundo PROTEGE/GO.",
            "fonte": URL_GO_MODAL_19,
        }

    @classmethod
    def _fcp_pr(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECOP/PR: adicional de 2% restrito à lista objetiva instalada.

        Autopeças e pneumáticos não integram os códigos de produto FECOP publicados
        pela SEFA/PR, portanto o adicional é confirmado em 0% para esses segmentos.
        Demais NCMs permanecem conservadores quando não houver enquadramento direto.
        """
        texto = cls._normalizar_texto(descricao)
        fecop = (
            ncm.startswith("2201")
            or ncm.startswith("2202")
            or ncm.startswith("24")
            or ncm.startswith("7113")
            or ncm.startswith("7114")
            or ncm.startswith("2203")
            or ncm.startswith("2204")
            or ncm.startswith("2205")
            or ncm.startswith("2206")
            or ncm.startswith("2208")
            or ncm.startswith("3303")
            or ncm.startswith("3304")
            or ncm.startswith("3305")
            or "GASOLINA" in texto
        )
        if fecop:
            return {
                "aliquota": 2.0,
                "status": "FECOP/PR 2% — ENQUADRAMENTO OBJETIVO NA LISTA INSTALADA",
                "confirmado": True,
                "confiabilidade": 95.0,
                "fundamento": "Lei PR nº 18.573/2015 e códigos de produto FECOP publicados pela SEFA/PR.",
                "fonte": URL_PR_FECOP,
            }

        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FECOP/PR NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 98.0,
                "fundamento": (
                    "Lista de códigos de produto FECOP/PR publicada pela SEFA/PR; "
                    "autopeças e pneumáticos não constam entre as hipóteses objetivas instaladas."
                ),
                "fonte": URL_PR_FECOP,
            }
        return {
            "aliquota": 0.0,
            "status": "NÃO IDENTIFICADO AUTOMATICAMENTE — REVISAR FECOP/PR",
            "confirmado": False,
            "confiabilidade": 65.0,
            "fundamento": "Lei PR nº 18.573/2015 e lista de produtos sujeitos ao FECOP/PR.",
            "fonte": URL_PR_FECOP,
        }

    @classmethod
    def _fcp_sc(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """SC: o antigo FECEP/ACEP foi incorporado ao FUNDO SOCIAL e a Lei 13.916/2006 foi revogada.

        No escopo automotivo estruturado não há adicional geral por operação. Contribuições de
        beneficiários de tratamentos tributários diferenciados são tratadas separadamente.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FCP/ACEP-SC 0% NO ESCOPO AUTOMOTIVO — LEI 13.916/2006 REVOGADA",
                "confirmado": True,
                "confiabilidade": 98.0,
                "fundamento": (
                    "Lei SC nº 18.334/2022, arts. 1º, 2º, 10 e 16, III: incorpora o FECEP ao Fundo Social "
                    "e revoga a Lei nº 13.916/2006; contribuições ligadas a tratamento tributário diferenciado "
                    "não constituem adicional geral por operação."
                ),
                "fonte": URL_SC_FUNDO_SOCIAL,
            }
        return {
            "aliquota": 0.0,
            "status": "SEM ADICIONAL GERAL FCP/ACEP AUTOMATIZADO — REVISAR FUNDO SOCIAL/TTD SE APLICÁVEL",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei SC nº 18.334/2022; eventual contribuição por TTD deve ser analisada separadamente.",
            "fonte": URL_SC_FUNDO_SOCIAL,
        }

    @classmethod
    def _fcp_rs(cls, ncm: str, descricao: str, consumidor_final: bool) -> Dict[str, Any]:
        """AMPARA/RS: adicional de 2% restrito ao rol legal; automotivo estruturado fica em 0%."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "AMPARA/RS NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": (
                    "RICMS/RS, Livro I, art. 27, parágrafo único; o rol do AMPARA/RS alcança bebidas, "
                    "tabaco e perfumaria/cosméticos, não autopeças ou pneumáticos."
                ),
                "fonte": URL_RS_AMPARA,
            }
        alcancado = (
            cls._ncm_em_prefixos(ncm, ("2203", "2204", "2205", "2206", "2208", "24", "3303", "3304", "3305", "3307"))
        )
        if alcancado and consumidor_final:
            return {
                "aliquota": 2.0,
                "status": "AMPARA/RS 2% — HIPÓTESE OBJETIVA A CONSUMIDOR FINAL",
                "confirmado": True,
                "confiabilidade": 95.0,
                "fundamento": "RICMS/RS, Livro I, art. 27, parágrafo único; Lei RS nº 14.742/2015 e Lei nº 16.109/2024.",
                "fonte": URL_RS_AMPARA,
            }
        if alcancado:
            return {
                "aliquota": 2.0,
                "status": "AMPARA/RS 2% — REVISAR DESTINAÇÃO/INCIDÊNCIA",
                "confirmado": False,
                "confiabilidade": 70.0,
                "fundamento": "RICMS/RS, Livro I, art. 27, parágrafo único.",
                "fonte": URL_RS_AMPARA,
            }
        return {
            "aliquota": 0.0,
            "status": "AMPARA/RS NÃO IDENTIFICADO PARA ESTE NCM NA REGRA OBJETIVA INSTALADA",
            "confirmado": True,
            "confiabilidade": 95.0,
            "fundamento": "Rol objetivo do AMPARA/RS no RICMS/RS, Livro I, art. 27, parágrafo único.",
            "fonte": URL_RS_AMPARA,
        }

    @classmethod
    def _fcp_ms(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECOMP/MS: 2% apenas nas hipóteses objetivas do art. 41-A da Lei 1.810/1997."""
        texto = cls._normalizar_texto(descricao)
        alcancado = (
            ncm.startswith("93")
            or ncm.startswith("360410")
            or cls._ncm_em_prefixos(ncm, ("2203", "2204", "2205", "2206", "2207", "2208"))
            or ncm.startswith("24")
            or ncm.startswith("7113")
            or ncm.startswith("7116")
            or ncm.startswith("43")
            or ncm.startswith("3303")
            or "OBRA DE ARTE" in texto
        )
        if alcancado:
            return {
                "aliquota": 2.0,
                "status": "FECOMP/MS 2% — ENQUADRAMENTO OBJETIVO DO ART. 41-A",
                "confirmado": True,
                "confiabilidade": 98.0,
                "fundamento": "Lei MS nº 1.810/1997, art. 41-A.",
                "fonte": URL_MS_LEI_1810,
            }

        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FECOMP/MS NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": "Lei MS nº 1.810/1997, art. 41-A — autopeças e pneumáticos não integram o rol do adicional.",
                "fonte": URL_MS_LEI_1810,
            }
        return {
            "aliquota": 0.0,
            "status": "FECOMP/MS NÃO IDENTIFICADO AUTOMATICAMENTE — REVISAR ENQUADRAMENTO",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei MS nº 1.810/1997, art. 41-A.",
            "fonte": URL_MS_LEI_1810,
        }

    @classmethod
    def _fcp_df(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FCP/DF: adicional de 2% somente sobre o rol do art. 2º, I, da Lei 4.220/2008."""
        texto = cls._normalizar_texto(descricao)
        alcancado = (
            ncm.startswith("24")
            or cls._ncm_em_prefixos(ncm, ("2203", "2204", "2205", "2206", "2207", "2208"))
            or ncm.startswith("93")
            or ncm.startswith("7113")
            or ncm.startswith("7116")
            or "ISOTONIC" in texto
            or "ENERGETIC" in texto
            or "EMBARCACAO ESPORTIVA" in texto
            or "IATE" in texto
            or "LANCHA" in texto
            or "VELEIRO" in texto
            or "CERVEJA SEM ALCOOL" in texto
            or "ULTRALEVE" in texto
            or "PLANADOR" in texto
            or "ASA DELTA" in texto
            or "PARAPENTE" in texto
        )
        if alcancado:
            return {
                "aliquota": 2.0,
                "status": "FCP/DF 2% — PRODUTO NO ROL OBJETIVO DA LEI 4.220/2008",
                "confirmado": True,
                "confiabilidade": 95.0,
                "fundamento": "Lei DF nº 4.220/2008, art. 2º, I; Lei DF nº 1.254/1996, art. 18-A.",
                "fonte": URL_DF_FCP,
            }

        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FCP/DF NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": (
                    "Lei DF nº 4.220/2008, art. 2º, I, e Lei DF nº 1.254/1996, art. 18-A — "
                    "autopeças e pneumáticos não integram o rol do adicional."
                ),
                "fonte": URL_DF_FCP,
            }
        return {
            "aliquota": 0.0,
            "status": "FCP/DF NÃO IDENTIFICADO AUTOMATICAMENTE — REVISAR ROL DA LEI 4.220/2008",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei DF nº 4.220/2008, art. 2º, I; Lei DF nº 1.254/1996, art. 18-A.",
            "fonte": URL_DF_FCP,
        }

    @classmethod
    def _fcp_ce(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECOP/CE: adicional de 2% apenas no rol do art. 47 do RICMS/CE.

        Para o escopo automotivo já estruturado (autopeças e pneumáticos),
        o adicional não integra o rol objetivo vigente. Outros NCMs permanecem
        em revisão para evitar generalização indevida.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FECOP/CE NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": (
                    "RICMS/CE, Decreto nº 33.327/2019, art. 47, redação do Decreto nº 36.536/2025 — "
                    "autopeças e pneumáticos não integram o rol do adicional de 2%."
                ),
                "fonte": URL_CE_RICMS,
            }
        return {
            "aliquota": 0.0,
            "status": "FECOP/CE NÃO CONFIRMADO AUTOMATICAMENTE — REVISAR O ROL DO ART. 47",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "RICMS/CE, Decreto nº 33.327/2019, art. 47, redação vigente.",
            "fonte": URL_CE_RICMS,
        }

    @classmethod
    def _fcp_al(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECOEP/AL: adicional geral de 1% também integra o cálculo da ST.

        A Lei 7.742/2015 incluiu o art. 2º-A na Lei 6.558/2004, prevendo 1%
        sobre mercadorias/serviços fora do rol de 2%, inclusive para fins de ST.
        Autopeças e pneumáticos do escopo instalado não estão entre as exceções
        objetivas; por isso o motor os trata com FECOEP de 1%, separado do ICMS.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 1.0,
                "status": "FECOEP/AL 1% — ADICIONAL GERAL APLICÁVEL AO SEGMENTO AUTOMOTIVO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": (
                    "Lei AL nº 6.558/2004, art. 2º-A, incluído pela Lei nº 7.742/2015: adicional de 1% "
                    "para mercadorias não incluídas no rol de 2%, inclusive no cálculo do ICMS-ST; "
                    "Lei nº 9.440/2024 preserva a sistemática e atualiza hipóteses específicas."
                ),
                "fonte": f"{URL_AL_FECOEP} | {URL_AL_FECOEP_9440}",
            }
        return {
            "aliquota": 0.0,
            "status": "FECOEP/AL EXIGE CLASSIFICAÇÃO DO PRODUTO — REVISAR 1%/2%/EXCEÇÕES",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei AL nº 6.558/2004, arts. 2º e 2º-A, com alterações posteriores.",
            "fonte": f"{URL_AL_FECOEP} | {URL_AL_FECOEP_9440}",
        }

    @classmethod
    def _fcp_ma(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FUMACOP/MA: adicional de 2% restrito às hipóteses legais específicas.

        Autopeças e pneumáticos do escopo estruturado não são tratados como
        mercadorias do rol do adicional; por isso recebem 0%. Outros itens
        permanecem em revisão para evitar generalização indevida.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FUMACOP/MA NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 98.0,
                "fundamento": (
                    "Lei MA nº 8.205/2004 e alterações posteriores: o adicional do FUMACOP incide "
                    "sobre hipóteses/produtos legalmente especificados. Autopeças e pneumáticos do "
                    "escopo estruturado não são enquadrados automaticamente no rol do adicional."
                ),
                "fonte": f"{URL_MA_LEGISLACAO} | {URL_MA_FUMACOP}",
            }
        return {
            "aliquota": 0.0,
            "status": "FUMACOP/MA NÃO CONFIRMADO AUTOMATICAMENTE — REVISAR ROL LEGAL",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei MA nº 8.205/2004 e alterações posteriores.",
            "fonte": f"{URL_MA_LEGISLACAO} | {URL_MA_FUMACOP}",
        }

    @classmethod
    def _fcp_pi(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECOP/PI: adicional restrito às mercadorias legalmente relacionadas.

        Autopeças e pneumáticos não integram o rol automotivo estruturado do
        adicional; permanecem em 0%. Para outros NCMs, exige revisão do rol.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FECOP/PI NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 98.0,
                "fundamento": (
                    "Legislação do FECOP/PI: o adicional alcança mercadorias legalmente relacionadas; "
                    "autopeças e pneumáticos do escopo estruturado não constam do rol consultado."
                ),
                "fonte": URL_PI_FECOP,
            }
        return {
            "aliquota": 0.0,
            "status": "FECOP/PI NÃO CONFIRMADO AUTOMATICAMENTE — REVISAR ROL LEGAL",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei estadual do FECOP/PI e alterações posteriores — revisar enquadramento do produto.",
            "fonte": URL_PI_FECOP,
        }

    @classmethod
    def _fcp_to(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECOEP/TO: +2 p.p. apenas nas hipóteses do art. 27, I.

        Autopeças e pneumáticos do escopo estruturado seguem a alíquota geral do
        art. 27, II, e por isso não recebem o adicional do § 11.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FECOEP/TO NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 99.0,
                "fundamento": (
                    "Lei TO nº 1.287/2001, art. 27, II e § 11: a alíquota geral interna é 20%; "
                    "o adicional de 2 pontos do FECOEP-TO é vinculado às mercadorias do inciso I, "
                    "não ao escopo estruturado de autopeças e pneumáticos."
                ),
                "fonte": f"{URL_TO_LEI_1287} | {URL_TO_LEI_4141}",
            }
        return {
            "aliquota": 0.0,
            "status": "FECOEP/TO NÃO CONFIRMADO AUTOMATICAMENTE — REVISAR ART. 27, I E § 11",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei TO nº 1.287/2001, art. 27, I, II e § 11 — revisar enquadramento específico.",
            "fonte": f"{URL_TO_LEI_1287} | {URL_TO_LEI_4141}",
        }

    @classmethod
    def _fcp_ac(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """Acre: sem adicional FCP separado na tabela estadual instalada."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FCP/AC 0% — SEM ADICIONAL NO ESCOPO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 98.0,
                "fundamento": (
                    "IN DIAT/SEFAZ-AC nº 1/2023: as tabelas de autopeças e pneumáticos "
                    "calculam a MVA ajustada com alíquota interna de 19%, sem adicional FCP separado."
                ),
                "fonte": URL_AC_IN_DIAT_01_2023,
            }
        return {
            "aliquota": 0.0,
            "status": "FCP/AC NÃO IDENTIFICADO — REVISAR O PRODUTO ESPECÍFICO",
            "confirmado": False,
            "confiabilidade": 75.0,
            "fundamento": "Revisar eventual regra específica do produto na legislação acreana.",
            "fonte": URL_AC_IN_DIAT_01_2023,
        }

    @classmethod
    def _fcp_am(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """AM: não soma adicional genérico ao ICMS de autopeças e pneumáticos."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "ADICIONAL/AM 0% NO ESCOPO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 98.0,
                "fundamento": (
                    "Lei AM nº 6.108/2022: as tabelas vigentes de autopeças e pneumáticos "
                    "estruturam a MVA sem adicional genérico separado para esses itens."
                ),
                "fonte": URL_AM_LEI_6108,
            }
        return {
            "aliquota": 0.0,
            "status": "ADICIONAL/AM NÃO IDENTIFICADO — REVISAR O PRODUTO ESPECÍFICO",
            "confirmado": False,
            "confiabilidade": 75.0,
            "fundamento": "Revisar fundos e contribuições estaduais aplicáveis ao produto específico.",
            "fonte": URL_AM_LEI_6108,
        }

    @classmethod
    def _fcp_ap(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        pista = ICMSSTMGService.analisar(ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao)
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {"aliquota": 0.0, "status": "FCP/AP 0% — ESCOPO AUTOMOTIVO ESTRUTURADO", "confirmado": True, "confiabilidade": 98.0, "fundamento": "Cobertura automotiva estruturada AP sem adicional FCP separado.", "fonte": URL_AP_RICMS}
        return {"aliquota": 0.0, "status": "FCP/AP NÃO IDENTIFICADO — REVISAR PRODUTO", "confirmado": False, "confiabilidade": 70.0, "fundamento": "Revisar eventual adicional aplicável ao produto específico.", "fonte": URL_AP_RICMS}

    @classmethod
    def _fcp_ro(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        pista = ICMSSTMGService.analisar(ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao)
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "PNEUM" in segmento:
            return {"aliquota": 2.0, "status": "FECOEP/RO 2% — PNEUMÁTICOS NO ESCOPO ESTRUTURADO", "confirmado": True, "confiabilidade": 98.0, "fundamento": "Cobertura RO 17.8.72/17.8.73: FECOEP separado para pneumáticos.", "fonte": URL_RO_DECRETO_29048}
        if "AUTOPE" in segmento:
            return {"aliquota": 0.0, "status": "FECOEP/RO 0% — AUTOPEÇAS NO ESCOPO ESTRUTURADO", "confirmado": True, "confiabilidade": 98.0, "fundamento": "Cobertura RO validada para autopeças sem FECOEP separado no item testado.", "fonte": URL_RO_DECRETO_29048}
        return {"aliquota": 0.0, "status": "FECOEP/RO NÃO IDENTIFICADO — REVISAR PRODUTO", "confirmado": False, "confiabilidade": 70.0, "fundamento": "Revisar o rol estadual do produto específico.", "fonte": URL_RO_RICMS}

    @classmethod
    def _fcp_pb(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FUNCEP/PB: adicional de 2% somente para o rol taxativo da Lei 7.611/2004.

        Autopeças e pneumáticos não constam do rol legal vigente do adicional.
        Por isso o escopo automotivo estruturado recebe 0%; demais mercadorias
        continuam em revisão para evitar extrapolar o rol da lei.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FUNCEP/PB NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": (
                    "Lei PB nº 7.611/2004, art. 2º, I: o adicional de 2% incide apenas sobre o rol "
                    "legal especificado; autopeças e pneumáticos não integram esse rol vigente."
                ),
                "fonte": URL_PB_FUNCEP,
            }
        return {
            "aliquota": 0.0,
            "status": "FUNCEP/PB NÃO CONFIRMADO AUTOMATICAMENTE — REVISAR O ROL DO ART. 2º",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei PB nº 7.611/2004, art. 2º, I, com alterações posteriores.",
            "fonte": URL_PB_FUNCEP,
        }

    @classmethod
    def _fcp_rn(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECOP/RN: 2% somente no rol taxativo do art. 27-A da Lei 6.968/1996.

        Autopeças e pneumáticos não integram o rol legal vigente, portanto o
        escopo automotivo estruturado recebe 0%. Outros itens permanecem em
        revisão para evitar aplicar ou afastar o adicional por aproximação.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FECOP/RN NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": (
                    "Lei RN nº 6.968/1996, art. 27-A, na redação da Lei nº 11.999/2024: "
                    "o adicional de 2% alcança somente o rol legal indicado; autopeças e pneumáticos "
                    "não constam desse rol."
                ),
                "fonte": URL_RN_LEI_11999,
            }
        return {
            "aliquota": 0.0,
            "status": "FECOP/RN NÃO CONFIRMADO AUTOMATICAMENTE — REVISAR O ROL DO ART. 27-A",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei RN nº 6.968/1996, art. 27-A, na redação da Lei nº 11.999/2024.",
            "fonte": URL_RN_LEI_11999,
        }

    @classmethod
    def _fcp_se(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECOEP/SE: 1% geral fora do rol especial de 2% dos arts. 40-C/40-D.

        Autopeças e pneumáticos não integram o rol de 2% do art. 40-C; portanto,
        no escopo automotivo estruturado, aplica-se o adicional geral de 1%.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 1.0,
                "status": "FECOEP/SE 1% — ADICIONAL GERAL APLICÁVEL AO SEGMENTO AUTOMOTIVO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": (
                    "RICMS/SE, Decreto nº 21.400/2002, arts. 40-C, 40-D e 616-B: itens não relacionados "
                    "no rol especial de 2% recebem adicional de 1%; autopeças e pneumáticos do escopo "
                    "estruturado não constam do art. 40-C."
                ),
                "fonte": URL_SE_RICMS,
            }
        return {
            "aliquota": 1.0,
            "status": "FECOEP/SE BASE GERAL 1% — REVISAR SE O PRODUTO INTEGRA O ROL DE 2% DO ART. 40-C",
            "confirmado": False,
            "confiabilidade": 80.0,
            "fundamento": "RICMS/SE, arts. 40-C, 40-D e 616-B.",
            "fonte": URL_SE_RICMS,
        }

    @classmethod
    def _fcp_pe(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECEP/PE: adicional de 2% somente para o rol legal específico.

        Autopeças e pneumáticos não integram o rol estruturado do adicional;
        por isso, no escopo automotivo coberto, o FECEP é 0%.
        """
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FECEP/PE NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": (
                    "Lei PE nº 12.523/2003 e Lei PE nº 15.730/2016 — autopeças e pneumáticos "
                    "não integram o rol objetivo do adicional de 2% do FECEP."
                ),
                "fonte": URL_PE_FECEP,
            }
        return {
            "aliquota": 0.0,
            "status": "FECEP/PE NÃO CONFIRMADO AUTOMATICAMENTE — REVISAR O ROL LEGAL",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei PE nº 12.523/2003 e Lei PE nº 15.730/2016.",
            "fonte": URL_PE_FECEP,
        }

    @classmethod
    def _fcp_rj(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """FECP/RJ: adicional geral de 2%, com confirmação reforçada no escopo automotivo estruturado."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 2.0,
                "status": "FECP/RJ 2% CONFIRMADO NO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 98.0,
                "fundamento": (
                    "Lei Complementar RJ nº 210/2023: adicional geral destinado ao FECP, "
                    "mantidas as exceções legais específicas."
                ),
                "fonte": URL_RJ_ALIQUOTAS,
            }
        return {
            "aliquota": 2.0,
            "status": "FECP/RJ GERAL DE 2% — REVISAR EXCEÇÕES DA LC 210/2023",
            "confirmado": False,
            "confiabilidade": 85.0,
            "fundamento": "Lei Complementar RJ nº 210/2023 e alterações posteriores.",
            "fonte": URL_RJ_ALIQUOTAS,
        }

    @classmethod
    def _fcp_mt(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        segmento = str(pista.get("segmento") or "").upper() if pista.get("encontrado") else ""
        if "AUTOPE" in segmento or "PNEUM" in segmento:
            return {
                "aliquota": 0.0,
                "status": "FCP/MT NÃO APLICÁVEL AO SEGMENTO AUTOMOTIVO ESTRUTURADO",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": (
                    "Lei MT nº 7.098/1998, art. 14, § 9º — adicional de 2% restrito às hipóteses legais; "
                    "autopeças e pneumáticos estruturados não integram o rol identificado."
                ),
                "fonte": URL_MT_LEI_7098,
            }
        return {
            "aliquota": 0.0,
            "status": "FCP/MT NÃO IDENTIFICADO AUTOMATICAMENTE — REVISAR ROL DO ART. 14, § 9º",
            "confirmado": False,
            "confiabilidade": 70.0,
            "fundamento": "Lei MT nº 7.098/1998, art. 14, § 9º.",
            "fonte": URL_MT_LEI_7098,
        }

    @classmethod
    def _perfil_interno(
        cls,
        uf: str,
        ncm: str,
        descricao: str,
        consumidor_final: bool,
    ) -> Dict[str, Any]:
        if uf == "SP":
            fcp = cls._fcp_sp(ncm, consumidor_final)
            return {
                "aliquota": 18.0,
                "status": "ALÍQUOTA MODAL OFICIAL — REVISAR EXCEÇÕES DOS ARTS. 53 A 55",
                "confirmada": False,
                "confiabilidade": 80.0,
                "fundamento": "RICMS/SP, art. 52, inciso I.",
                "fonte": URL_SP_RICMS_ART_52,
                "fcp": fcp,
            }

        if uf == "ES":
            fcp = cls._fcp_es(ncm)
            if cls._ncm_em_prefixos(ncm, ("87012", "8702", "8703", "8704", "870600", "8711")):
                return {
                    "aliquota": 12.0,
                    "status": "CONFIRMADA — VEÍCULO AUTOMOTOR RELACIONADO NA LEI ES",
                    "confirmada": True,
                    "confiabilidade": 100.0,
                    "fundamento": "Lei ES nº 7.000/2001, art. 20, II, h.",
                    "fonte": URL_ES_LEI_7000,
                    "fcp": fcp,
                }
            if cls._ncm_em_prefixos(ncm, ("2203", "2204", "2205", "2206", "220720", "2208", "24")):
                return {
                    "aliquota": 25.0,
                    "status": "CONFIRMADA — MERCADORIA DO ART. 20, IV, d/e",
                    "confirmada": True,
                    "confiabilidade": 100.0,
                    "fundamento": "Lei ES nº 7.000/2001, art. 20, IV, d/e.",
                    "fonte": URL_ES_LEI_7000,
                    "fcp": fcp,
                }
            return {
                "aliquota": 17.0,
                "status": "ALÍQUOTA MODAL OFICIAL — REVISAR HIPÓTESES ESPECÍFICAS DO ART. 20",
                "confirmada": False,
                "confiabilidade": 82.0,
                "fundamento": "Lei ES nº 7.000/2001, art. 20, I.",
                "fonte": URL_ES_LEI_7000,
                "fcp": fcp,
            }

        if uf == "BA":
            fcp = cls._fcp_ba(ncm, descricao)
            return {
                "aliquota": 20.5,
                "status": "ALÍQUOTA MODAL OFICIAL — REVISAR ALÍQUOTAS ESPECÍFICAS DO ART. 16",
                "confirmada": False,
                "confiabilidade": 80.0,
                "fundamento": "Lei BA nº 7.014/1996, art. 15, I.",
                "fonte": URL_BA_LEI_7014,
                "fcp": fcp,
            }

        if uf == "PA":
            return {
                "aliquota": 19.0,
                "status": "ALÍQUOTA MODAL OFICIAL — REVISAR EXCEÇÕES DA LEI/RICMS-PA",
                "confirmada": False,
                "confiabilidade": 88.0,
                "fundamento": (
                    "Lei PA nº 5.530/1989, art. 12, VII, na redação da Lei nº 9.755/2022."
                ),
                "fonte": URL_PA_LEI_9755,
                "fcp": cls._fcp_pa(),
            }

        if uf == "GO":
            return {
                "aliquota": 19.0,
                "status": "ALÍQUOTA MODAL OFICIAL 19% — REVISAR BENEFÍCIOS E ALÍQUOTAS ESPECÍFICAS",
                "confirmada": False,
                "confiabilidade": 95.0,
                "fundamento": (
                    "Lei GO nº 22.460/2023: alíquota modal de 19%, vigente desde 01/04/2024; "
                    "Nota Técnica Malha Fiscal 118/2026 confirma a referência em 2026."
                ),
                "fonte": URL_GO_MODAL_19,
                "fcp": cls._fcp_go(ncm, descricao),
            }

        if uf == "PR":
            return {
                "aliquota": 19.5,
                "status": "ALÍQUOTA MODAL OFICIAL 19,5% — REVISAR ALÍQUOTAS E BENEFÍCIOS ESPECÍFICOS",
                "confirmada": False,
                "confiabilidade": 95.0,
                "fundamento": (
                    "RICMS/PR, art. 17, V, na redação do Decreto nº 5.143/2024: "
                    "19,5% para os demais bens e mercadorias."
                ),
                "fonte": URL_PR_RICMS_MODAL,
                "fcp": cls._fcp_pr(ncm, descricao),
            }

        if uf == "SC":
            fcp = cls._fcp_sc(ncm, descricao)
            if consumidor_final:
                return {
                    "aliquota": 17.0,
                    "status": "ALÍQUOTA MODAL 17% — CONSUMIDOR FINAL/REVISAR EXCEÇÕES DO ART. 26",
                    "confirmada": False,
                    "confiabilidade": 90.0,
                    "fundamento": "RICMS/SC, art. 26, I e § 5º.",
                    "fonte": URL_SC_RICMS,
                    "fcp": fcp,
                }
            return {
                "aliquota": 12.0,
                "status": "12% — MERCADORIA DESTINADA A CONTRIBUINTE; REVISAR EXCEÇÕES DO ART. 26, § 5º",
                "confirmada": False,
                "confiabilidade": 95.0,
                "fundamento": "RICMS/SC, art. 26, III, n, e § 5º.",
                "fonte": URL_SC_RICMS,
                "fcp": fcp,
            }

        if uf == "RS":
            return {
                "aliquota": 17.0,
                "status": "ALÍQUOTA MODAL 17% — REVISAR ALÍQUOTAS E BENEFÍCIOS ESPECÍFICOS",
                "confirmada": False,
                "confiabilidade": 95.0,
                "fundamento": (
                    "RICMS/RS, Livro I, art. 27, I; alíquota modal de 17% mantida como referência em 2026."
                ),
                "fonte": URL_RS_MODAL_17,
                "fcp": cls._fcp_rs(ncm, descricao, consumidor_final),
            }

        if uf == "MS":
            return {
                "aliquota": 17.0,
                "status": "ALÍQUOTA MODAL 17% — REVISAR ALÍQUOTAS E BENEFÍCIOS ESPECÍFICOS",
                "confirmada": False,
                "confiabilidade": 95.0,
                "fundamento": "Lei MS nº 1.810/1997, art. 41, III, a.",
                "fonte": URL_MS_LEI_1810,
                "fcp": cls._fcp_ms(ncm, descricao),
            }

        if uf == "MT":
            return {
                "aliquota": 17.0,
                "status": "ALÍQUOTA MODAL 17% — REVISAR ALÍQUOTAS E BENEFÍCIOS ESPECÍFICOS",
                "confirmada": False,
                "confiabilidade": 95.0,
                "fundamento": "Lei MT nº 7.098/1998, art. 14, I; RICMS/MT, art. 95, I.",
                "fonte": URL_MT_LEI_7098,
                "fcp": cls._fcp_mt(ncm, descricao),
            }

        if uf == "DF":
            return {
                "aliquota": 20.0,
                "status": "ALÍQUOTA MODAL 20% — REVISAR ALÍQUOTAS ESPECÍFICAS E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 97.0,
                "fundamento": (
                    "Lei DF nº 1.254/1996, art. 18, II, c, na redação da Lei nº 7.326/2023: "
                    "20% para as demais mercadorias e serviços não listados nas alíquotas específicas."
                ),
                "fonte": URL_DF_LEI_1254,
                "fcp": cls._fcp_df(ncm, descricao),
            }

        if uf == "CE":
            return {
                "aliquota": 20.0,
                "status": "ALÍQUOTA MODAL 20% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 98.0,
                "fundamento": (
                    "Lei CE nº 18.665/2023, art. 65, I, g: 20% para as demais mercadorias ou bens "
                    "a partir de 01/01/2024."
                ),
                "fonte": URL_CE_LEI_18665,
                "fcp": cls._fcp_ce(ncm, descricao),
            }

        if uf == "AL":
            return {
                "aliquota": 20.5,
                "status": "ALÍQUOTA MODAL 20,5% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": (
                    "Lei AL nº 5.900/1996, art. 17, I, b, na redação da Lei nº 9.776/2025: "
                    "20,5% nos demais casos, com efeitos a partir de 01/04/2026."
                ),
                "fonte": URL_AL_LEI_9776,
                "fcp": cls._fcp_al(ncm, descricao),
            }

        if uf == "MA":
            return {
                "aliquota": 23.0,
                "status": "ALÍQUOTA MODAL 23% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": (
                    "Lei MA nº 7.799/2002, art. 23, com redação da Lei nº 12.426/2024: "
                    "alíquota geral de 23%, com efeitos desde 23/02/2025."
                ),
                "fonte": URL_MA_LEGISLACAO,
                "fcp": cls._fcp_ma(ncm, descricao),
            }

        if uf == "PI":
            return {
                "aliquota": 22.5,
                "status": "ALÍQUOTA MODAL 22,5% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": (
                    "Lei PI nº 8.558/2024 e Decreto nº 23.517/2025: alíquota interna modal de 22,5%, "
                    "com efeitos a partir de 01/04/2025, ressalvadas hipóteses específicas."
                ),
                "fonte": URL_PI_MODAL_225,
                "fcp": cls._fcp_pi(ncm, descricao),
            }

        if uf == "TO":
            return {
                "aliquota": 20.0,
                "status": "ALÍQUOTA MODAL 20% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": (
                    "Lei TO nº 1.287/2001, art. 27, II, na redação da Lei nº 4.141/2023: "
                    "20% nas operações e prestações internas, ressalvadas as hipóteses específicas."
                ),
                "fonte": f"{URL_TO_LEI_1287} | {URL_TO_LEI_4141}",
                "fcp": cls._fcp_to(ncm, descricao),
            }

        if uf == "AC":
            return {
                "aliquota": 19.0,
                "status": "ALÍQUOTA MODAL 19% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": "RICMS/AC e IN DIAT/SEFAZ-AC nº 1/2023: referência modal de 19%, ressalvadas hipóteses específicas.",
                "fonte": URL_AC_IN_DIAT_01_2023,
                "fcp": cls._fcp_ac(ncm, descricao),
            }

        if uf == "AM":
            return {
                "aliquota": 20.0,
                "status": "ALÍQUOTA MODAL 20% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": "Lei Complementar AM nº 242/2022: alíquota interna modal de 20% para as demais mercadorias, ressalvadas hipóteses específicas.",
                "fonte": URL_AM_LC_242,
                "fcp": cls._fcp_am(ncm, descricao),
            }

        if uf == "AP":
            return {
                "aliquota": 18.0,
                "status": "ALÍQUOTA MODAL 18% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 98.0,
                "fundamento": "RICMS/AP: referência modal de 18% para o escopo estruturado, ressalvadas hipóteses específicas.",
                "fonte": URL_AP_RICMS,
                "fcp": cls._fcp_ap(ncm, descricao),
            }

        if uf == "RO":
            return {
                "aliquota": 19.5,
                "status": "ALÍQUOTA MODAL 19,5% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": "RICMS/RO, com redação do Decreto nº 29.048/2024: 19,5% nos demais casos a partir de 12/01/2024.",
                "fonte": URL_RO_DECRETO_29048,
                "fcp": cls._fcp_ro(ncm, descricao),
            }

        if uf == "PB":
            return {
                "aliquota": 20.0,
                "status": "ALÍQUOTA MODAL 20% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": (
                    "Lei PB nº 6.379/1996, art. 11, I, na redação da Lei nº 12.788/2023: "
                    "20% nas operações/prestações internas e importações, com efeitos desde 01/01/2024."
                ),
                "fonte": URL_PB_LEI_6379,
                "fcp": cls._fcp_pb(ncm, descricao),
            }

        if uf == "RN":
            return {
                "aliquota": 20.0,
                "status": "ALÍQUOTA MODAL 20% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": (
                    "Lei RN nº 6.968/1996, art. 27, I, a, na redação da Lei nº 11.999/2024: "
                    "20% para mercadorias, bens e serviços não abrangidos pelas alíquotas específicas."
                ),
                "fonte": URL_RN_LEI_11999,
                "fcp": cls._fcp_rn(ncm, descricao),
            }


        if uf == "SE":
            return {
                "aliquota": 19.0,
                "status": "ALÍQUOTA MODAL 19% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 99.0,
                "fundamento": (
                    "RICMS/SE, Decreto nº 21.400/2002, art. 40, I: 19% nas operações e prestações internas, "
                    "ressalvadas as alíquotas específicas; vigência desde 01/04/2023."
                ),
                "fonte": URL_SE_RICMS,
                "fcp": cls._fcp_se(ncm, descricao),
            }

        if uf == "PE":
            return {
                "aliquota": 20.5,
                "status": "ALÍQUOTA MODAL 20,5% — REVISAR ALÍQUOTAS ESPECÍFICAS, REDUÇÕES E BENEFÍCIOS",
                "confirmada": False,
                "confiabilidade": 98.0,
                "fundamento": (
                    "Lei PE nº 15.730/2016, com alterações da Lei nº 18.305/2023: "
                    "alíquota interna modal de 20,5% a partir de 01/01/2024."
                ),
                "fonte": URL_PE_RICMS,
                "fcp": cls._fcp_pe(ncm, descricao),
            }

        if uf == "RJ":
            return {
                "aliquota": 20.0,
                "status": "ALÍQUOTA GERAL OFICIAL — REVISAR EXCEÇÕES E ALÍQUOTAS ESPECÍFICAS",
                "confirmada": False,
                "confiabilidade": 90.0,
                "fundamento": (
                    "Lei RJ nº 2.657/1996, art. 14, na redação vigente; alíquota geral de 20%."
                ),
                "fonte": URL_RJ_ALIQUOTAS,
                "fcp": cls._fcp_rj(ncm, descricao),
            }

        raise ValueError(f"UF {uf} ainda não possui perfil estadual nesta fase.")

    @classmethod
    def _indicio_st(
        cls,
        ncm: str,
        descricao: str,
        origem: str,
        destino: str,
        data_operacao: date,
        aliquota_interestadual: Optional[float],
        aliquota_interna: Optional[float],
        contrato_fidelidade: bool,
        finalidade_automotiva: str = "",
    ) -> Dict[str, Any]:
        if destino == "MG":
            resultado = ICMSSTMGService.analisar(
                ncm,
                contexto={
                    "uf_origem": origem,
                    "uf_destino": destino,
                    "finalidade_automotiva": finalidade_automotiva,
                },
                descricao=descricao,
            )
            confirmado = bool(resultado.get("confirmado"))
            return {
                "status": str(resultado.get("status") or ""),
                "potencial": bool(resultado.get("potencial") or resultado.get("encontrado")),
                "confirmado": confirmado,
                "decisao_confirmada": bool(
                    confirmado
                    or (resultado.get("nao_aplicavel") and not resultado.get("exige_revisao", True))
                ),
                "confiabilidade": 100.0 if confirmado else 65.0,
                "cest": str(resultado.get("cest") or ""),
                "segmento": str(resultado.get("segmento") or ""),
                "descricao_legal": str(resultado.get("descricao_legal") or ""),
                "mva": resultado.get("mva_original"),
                "mva_original": resultado.get("mva_original"),
                "mva_ajustada": None,
                "mva_aplicada": resultado.get("mva_original"),
                "mva_tipo": "MVA ORIGINAL MG" if resultado.get("mva_original") is not None else "",
                "vigencia_inicio": "",
                "vigencia_fim": "",
                "responsabilidade": "CONFORME MOTOR DETALHADO DE MG",
                "acordo_status": "CONFORME MOTOR DETALHADO DE MG",
                "contrato_fidelidade": contrato_fidelidade,
                "fundamento": str(resultado.get("fundamento_legal") or ""),
                "fonte": str(resultado.get("fonte_url") or ""),
                "observacao": str(resultado.get("observacao") or ""),
            }

        resultado = ICMSSTUFService.analisar(
            ncm=ncm,
            descricao=descricao,
            uf_origem=origem,
            uf_destino=destino,
            data_operacao=data_operacao,
            aliquota_interestadual=aliquota_interestadual,
            aliquota_interna=aliquota_interna,
            contrato_fidelidade=contrato_fidelidade,
            finalidade_automotiva=finalidade_automotiva,
        )
        return {
            "status": str(resultado.get("status") or ""),
            "potencial": bool(resultado.get("potencial")),
            "confirmado": bool(resultado.get("aplica_st")),
            "decisao_confirmada": bool(resultado.get("decisao_confirmada")),
            "confiabilidade": float(resultado.get("confiabilidade") or 0.0),
            "cest": str(resultado.get("cest") or ""),
            "segmento": str(resultado.get("segmento") or ""),
            "descricao_legal": str(resultado.get("descricao_legal") or ""),
            "mva": resultado.get("mva_aplicada"),
            "mva_original": resultado.get("mva_original"),
            "mva_ajustada": resultado.get("mva_ajustada"),
            "mva_aplicada": resultado.get("mva_aplicada"),
            "mva_tipo": str(resultado.get("mva_tipo") or ""),
            "st_modelo_calculo": str(resultado.get("st_modelo_calculo") or ""),
            "carga_liquida_st": resultado.get("carga_liquida_st"),
            "carga_liquida_status": str(resultado.get("carga_liquida_status") or ""),
            "antecipacao_percentual": resultado.get("antecipacao_percentual"),
            "antecipacao_status": str(resultado.get("antecipacao_status") or ""),
            "vigencia_inicio": str(resultado.get("vigencia_inicio") or ""),
            "vigencia_fim": str(resultado.get("vigencia_fim") or ""),
            "responsabilidade": str(resultado.get("responsabilidade") or ""),
            "acordo_status": str(resultado.get("acordo_status") or ""),
            "contrato_fidelidade": bool(resultado.get("contrato_fidelidade")),
            "fundamento": str(resultado.get("fundamento") or ""),
            "fonte": str(resultado.get("fonte") or ""),
            "observacao": str(resultado.get("observacao") or ""),
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
        origem = cls._normalizar_uf(contexto.get("uf_origem") or "MG")
        destino = cls._normalizar_uf(contexto.get("uf_destino") or origem)
        data_operacao = cls._data_operacao(contexto)
        consumidor_final = cls._booleano(contexto.get("consumidor_final"))
        importada = cls._booleano(contexto.get("mercadoria_importada"))
        excecao_importada = cls._booleano(contexto.get("excecao_aliquota_importacao"))
        contrato_fidelidade = cls._booleano(contexto.get("contrato_fidelidade"))
        finalidade_automotiva = str(
            contexto.get("finalidade_automotiva") or ""
        ).strip()
        tipo_operacao = "INTERNA" if origem == destino else "INTERESTADUAL"

        if destino not in UFS_COBERTURA:
            return ResultadoICMSUF(
                ncm=codigo,
                uf_origem=origem,
                uf_destino=destino,
                data_operacao=data_operacao.isoformat(),
                tipo_operacao=tipo_operacao,
                status="UF AINDA NÃO COBERTA NESTA FASE",
                confirmado=False,
                exige_revisao=True,
                observacao="A cobertura estadual instalada alcança MG e todas as demais UFs com níveis de detalhamento distintos; ausências de regra específica permanecem como revisão, nunca como conclusão automática de não incidência.",
            ).para_dict()

        if destino == "MG":
            mg_operacao = ICMSMGNacionalService.analisar(
                codigo,
                contexto={
                    **contexto,
                    "uf_origem": origem,
                    "uf_destino": destino,
                    "data_operacao": data_operacao.isoformat(),
                },
                descricao=descricao,
            )
            mg_interna = ICMSMGNacionalService.analisar(
                codigo,
                contexto={
                    **contexto,
                    "uf_origem": "MG",
                    "uf_destino": "MG",
                    "data_operacao": data_operacao.isoformat(),
                },
                descricao=descricao,
            )
            aliquota_operacao = mg_operacao.get("aliquota_nominal")
            aliquota_interna = mg_interna.get("aliquota_nominal")
            total = float(aliquota_interna) if aliquota_interna is not None else None
            confirmado = bool(
                mg_operacao.get("aliquota_confirmada")
                and mg_interna.get("aliquota_confirmada")
                and mg_operacao.get("st_confirmado")
            )
            observacao = " ".join(
                texto for texto in (
                    str(mg_operacao.get("observacao") or "").strip(),
                    "O FCP/MG ainda não está automatizado nesta camada nacional.",
                ) if texto
            )
            return ResultadoICMSUF(
                ncm=codigo,
                uf_origem=origem,
                uf_destino=destino,
                data_operacao=data_operacao.isoformat(),
                tipo_operacao=tipo_operacao,
                status=("ICMS/MG CONFIRMADO" if confirmado else str(mg_operacao.get("status") or "")),
                confirmado=confirmado,
                exige_revisao=not confirmado,
                aliquota_operacao=float(aliquota_operacao) if aliquota_operacao is not None else None,
                aliquota_operacao_status=str(mg_operacao.get("aliquota_status") or ""),
                aliquota_operacao_confirmada=bool(mg_operacao.get("aliquota_confirmada")),
                aliquota_interna_destino=float(aliquota_interna) if aliquota_interna is not None else None,
                aliquota_interna_status=str(mg_interna.get("aliquota_status") or ""),
                aliquota_interna_confirmada=bool(mg_interna.get("aliquota_confirmada")),
                aliquota_total_consumidor=total,
                fcp=0.0,
                fcp_status="NÃO AUTOMATIZADO PELO MOTOR ESTADUAL DE MG",
                fcp_confirmado=False,
                st_status=str(mg_operacao.get("st_status") or ""),
                st_potencial=bool(mg_operacao.get("st_potencial")),
                st_confirmado=bool(mg_operacao.get("st_confirmado")),
                st_decisao_confirmada=bool(mg_operacao.get("st_decisao_confirmada")),
                cest=str(mg_operacao.get("cest") or ""),
                segmento_st=str(mg_operacao.get("segmento_st") or ""),
                mva_original=mg_operacao.get("mva_original"),
                mva_aplicada=mg_operacao.get("mva_original"),
                mva_tipo="MVA ORIGINAL MG" if mg_operacao.get("mva_original") is not None else "",
                st_responsabilidade="CONFORME MOTOR DETALHADO DE MG",
                st_acordo_status="CONFORME MOTOR DETALHADO DE MG",
                contrato_fidelidade=contrato_fidelidade,
                beneficio_status=str(mg_operacao.get("beneficio_status") or ""),
                confiabilidade_aliquota=min(
                    float(mg_operacao.get("confiabilidade_aliquota") or 0.0),
                    float(mg_interna.get("confiabilidade_aliquota") or 0.0),
                ),
                confiabilidade_fcp=0.0,
                confiabilidade_st=float(mg_operacao.get("confiabilidade_st") or 0.0),
                fundamento_aliquota=(
                    f"Operação: {mg_operacao.get('fundamento_aliquota') or ''} | "
                    f"Interna MG: {mg_interna.get('fundamento_aliquota') or ''}"
                ).strip(" |"),
                fundamento_st=str(mg_operacao.get("fundamento_aliquota") or ""),
                fonte_aliquota=(
                    f"{mg_operacao.get('fonte_aliquota') or ''} | "
                    f"{mg_interna.get('fonte_aliquota') or ''}"
                ).strip(" |"),
                fonte_st=str(mg_operacao.get("fonte_aliquota") or ""),
                observacao=observacao,
            ).para_dict()

        perfil = cls._perfil_interno(destino, codigo, descricao, consumidor_final)
        fcp = dict(perfil["fcp"])
        interna = float(perfil["aliquota"])
        fcp_aliquota = float(fcp.get("aliquota") or 0.0)
        total_consumidor = interna + fcp_aliquota

        if tipo_operacao == "INTERNA":
            operacao = {
                "aliquota": interna,
                "status": str(perfil["status"]),
                "confirmada": bool(perfil["confirmada"]),
                "confiabilidade": float(perfil["confiabilidade"]),
                "fundamento": str(perfil["fundamento"]),
                "fonte": str(perfil["fonte"]),
            }
        else:
            operacao = cls._aliquota_interestadual(origem, destino, importada, excecao_importada)

        st = cls._indicio_st(
            codigo,
            descricao,
            origem,
            destino,
            data_operacao,
            operacao.get("aliquota"),
            interna,
            contrato_fidelidade,
            finalidade_automotiva,
        )
        pontos_revisao: List[str] = []
        if not perfil["confirmada"]:
            pontos_revisao.append("alíquota interna específica do produto")
        if not fcp.get("confirmado"):
            pontos_revisao.append("FCP/FECOP")
        if not st.get("decisao_confirmada"):
            pontos_revisao.append("ICMS-ST/MVA")
        pontos_revisao.append("benefícios, reduções, isenções e diferimentos")

        confirmado = bool(
            operacao.get("confirmada")
            and perfil.get("confirmada")
            and fcp.get("confirmado")
            and st.get("decisao_confirmada")
        )
        status = "ICMS CONFIRMADO" if confirmado else "ANÁLISE CONCLUÍDA — REVISAR"
        observacao = (
            "Pontos pendentes: " + "; ".join(dict.fromkeys(pontos_revisao)) + ". "
            + str(st.get("observacao") or "")
        )

        return ResultadoICMSUF(
            ncm=codigo,
            uf_origem=origem,
            uf_destino=destino,
            data_operacao=data_operacao.isoformat(),
            tipo_operacao=tipo_operacao,
            status=status,
            confirmado=confirmado,
            exige_revisao=not confirmado,
            aliquota_operacao=float(operacao["aliquota"]) if operacao.get("aliquota") is not None else None,
            aliquota_operacao_status=str(operacao.get("status") or ""),
            aliquota_operacao_confirmada=bool(operacao.get("confirmada")),
            aliquota_interna_destino=interna,
            aliquota_interna_status=str(perfil.get("status") or ""),
            aliquota_interna_confirmada=bool(perfil.get("confirmada")),
            aliquota_total_consumidor=total_consumidor,
            fcp=fcp_aliquota,
            fcp_status=str(fcp.get("status") or ""),
            fcp_confirmado=bool(fcp.get("confirmado")),
            st_status=str(st.get("status") or ""),
            st_potencial=bool(st.get("potencial")),
            st_confirmado=bool(st.get("confirmado")),
            st_decisao_confirmada=bool(st.get("decisao_confirmada")),
            cest=str(st.get("cest") or ""),
            segmento_st=str(st.get("segmento") or ""),
            descricao_legal_st=str(st.get("descricao_legal") or ""),
            mva_original=st.get("mva_original"),
            mva_ajustada=st.get("mva_ajustada"),
            mva_aplicada=st.get("mva_aplicada"),
            mva_tipo=str(st.get("mva_tipo") or ""),
            st_modelo_calculo=str(st.get("st_modelo_calculo") or ""),
            carga_liquida_st=(float(st.get("carga_liquida_st")) if st.get("carga_liquida_st") is not None else None),
            carga_liquida_status=str(st.get("carga_liquida_status") or ""),
            antecipacao_percentual=(float(st.get("antecipacao_percentual")) if st.get("antecipacao_percentual") is not None else None),
            antecipacao_status=str(st.get("antecipacao_status") or ""),
            st_vigencia_inicio=str(st.get("vigencia_inicio") or ""),
            st_vigencia_fim=str(st.get("vigencia_fim") or ""),
            st_responsabilidade=str(st.get("responsabilidade") or ""),
            st_acordo_status=str(st.get("acordo_status") or ""),
            contrato_fidelidade=bool(st.get("contrato_fidelidade")),
            confiabilidade_aliquota=min(
                float(operacao.get("confiabilidade") or 0.0),
                float(perfil.get("confiabilidade") or 0.0),
            ),
            confiabilidade_fcp=float(fcp.get("confiabilidade") or 0.0),
            confiabilidade_st=float(st.get("confiabilidade") or 0.0),
            fundamento_aliquota=(
                f"{operacao.get('fundamento') or ''} | Destino: {perfil.get('fundamento') or ''}"
            ).strip(" |"),
            fundamento_fcp=str(fcp.get("fundamento") or ""),
            fundamento_st=str(st.get("fundamento") or ""),
            fonte_aliquota=(
                f"{operacao.get('fonte') or ''} | {perfil.get('fonte') or ''}"
            ).strip(" |"),
            fonte_fcp=str(fcp.get("fonte") or ""),
            fonte_st=str(st.get("fonte") or ""),
            observacao=observacao,
        ).para_dict()


__all__ = ["ICMSUFService", "ResultadoICMSUF", "UFS_COBERTURA"]
