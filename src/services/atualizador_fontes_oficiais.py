from __future__ import annotations

import json
import re
import tempfile
import unicodedata
import urllib.request
from html.parser import HTMLParser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openpyxl import load_workbook

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.repositorios.ncm_repository import NCMRepository

URL_NCM_JSON = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"
URL_RECEITA_NCM = "https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/download-ncm-nomenclatura-comum-do-mercosul"
URL_TIPI_PAGINA = "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/legislacao/tipi-tabela-de-incidencia-do-imposto-sobre-produtos-industrializados"
URL_TIPI_XLSX = "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/legislacao/documentos-e-arquivos/tipi.xlsx/@@download/file"
URL_CONFAZ = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"
URL_SEFAZ_MG = "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/ricms_2023_seco/sumario2023_1.html"
URL_SEFAZ_MG_ST = "https://www.fazenda.mg.gov.br/empresas/substituicao_tributaria/stminasgerais.html"
URL_SEFAZ_MG_ST_AUTOPECAS = "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/ricms_2023_seco/anexovii2023_4.html"
# O segmento 10 está na mesma página HTML do segmento 1.
URL_SEFAZ_MG_ST_MATERIAIS_CONSTRUCAO = URL_SEFAZ_MG_ST_AUTOPECAS
URL_SEFAZ_MG_ST_PNEUMATICOS = "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/ricms_2023_seco/anexovii2023_5.html"
# A Parte 2 do Anexo VII vigente está nas páginas 4/7, 5/7 e 6/7.
# A página 3 ainda é Parte 1 e a 7 já inicia a Parte 3; incluí-las na
# sincronização ampla pode misturar regras que não pertencem à tabela de ST.
URL_SEFAZ_MG_ST_PAGINAS = tuple(
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    f"ricms_2023_seco/anexovii2023_{pagina}.html"
    for pagina in range(4, 7)
)
ST_MG_SCHEMA_VERSAO = 3
# Linhas residuais da Parte 2 que não possuem NBM/SH fechado. Elas não podem
# entrar no índice nominal, mas precisam ser reconhecidas antes que a ausência
# de NCM seja usada como evidência de NÃO ST. A sincronização integral só recebe
# selo de base completa enquanto todos os residuais sem NCM publicados forem
# conhecidos pelo motor.
RESIDUAIS_ST_MG_SEM_NCM_SUPORTADOS = {"01.999.00", "28.999.00"}

SEGMENTOS_ST_MG: Dict[str, str] = {
    "01": "AUTOPEÇAS",
    "02": "BEBIDAS ALCOÓLICAS, EXCETO CERVEJA E CHOPE",
    "03": "CERVEJAS, CHOPES, REFRIGERANTES, ÁGUAS E OUTRAS BEBIDAS",
    "04": "CIGARROS E OUTROS PRODUTOS DERIVADOS DO FUMO",
    "05": "CIMENTOS",
    "06": "COMBUSTÍVEIS E LUBRIFICANTES",
    "07": "ENERGIA ELÉTRICA",
    "08": "FERRAMENTAS",
    "09": "LÂMPADAS, REATORES E STARTER",
    "10": "MATERIAIS DE CONSTRUÇÃO E CONGÊNERES",
    "11": "MATERIAIS DE LIMPEZA",
    "12": "MATERIAIS ELÉTRICOS",
    "13": "MEDICAMENTOS E OUTROS PRODUTOS FARMACÊUTICOS",
    "14": "PAPÉIS, PLÁSTICOS, PRODUTOS CERÂMICOS E VIDROS",
    "15": "PLÁSTICOS",
    "16": "PNEUMÁTICOS",
    "17": "PRODUTOS ALIMENTÍCIOS",
    "18": "PRODUTOS CERÂMICOS",
    "19": "PRODUTOS DE PAPELARIA",
    "20": "PRODUTOS DE PERFUMARIA E DE HIGIENE PESSOAL E COSMÉTICOS",
    "21": "PRODUTOS ELETRÔNICOS, ELETROELETRÔNICOS E ELETRODOMÉSTICOS",
    "22": "RAÇÕES PARA ANIMAIS DOMÉSTICOS",
    "23": "SORVETES E PREPARADOS PARA FABRICAÇÃO DE SORVETES",
    "24": "TINTAS E VERNIZES",
    "25": "VEÍCULOS AUTOMOTORES",
    "26": "VEÍCULOS DE DUAS E TRÊS RODAS MOTORIZADOS",
    "27": "VIDROS",
    "28": "VENDA DE MERCADORIAS PELO SISTEMA PORTA A PORTA",
}
URL_CCLASSTRIB = "https://dfe-portal.svrs.rs.gov.br/Cff/ClassificacaoTributaria"
URL_PISCOFINS = "https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/tributos/pis-pasep-cofins"
URL_LEI_10485 = "https://www.planalto.gov.br/ccivil_03/leis/2002/L10485compilado.htm"
URL_LEI_10637 = "https://www.planalto.gov.br/ccivil_03/leis/2002/l10637compilado.htm"
URL_LEI_10833 = "https://www.planalto.gov.br/ccivil_03/leis/2003/l10.833compilado.htm"
URL_SPED_TABELA_4310 = "https://sped.rfb.gov.br/item/show/1638"

# Rio Grande do Norte — fontes usadas pela cobertura estadual estruturada.
URL_RN_LEI_11999 = "https://www.al.rn.leg.br/storage/legislacao/2025/stqpzaxnkhj8e1efdy6wnsk815m85v.pdf"
URL_RN_ANEXO_005 = "https://www.diariooficial.rn.gov.br/dei/dorn3/documentos/00000001/20220819/783140.htm"
URL_RN_ANEXO_007 = "https://www.diariooficial.rn.gov.br/dei/dorn3/documentos/00000001/20220819/783145.htm"

# Sergipe — RICMS consolidado vigente em 2026 (Decreto nº 21.400/2002).
URL_SE_RICMS = "https://api.legislacao.se.gov.br/uploads/atos/31521/DN-21400-2002-atualizado-DN-1467-2026.pdf"

# Maranhão — portal oficial de legislação tributária da SEFAZ/MA.
URL_MA_LEGISLACAO = "https://www.ma.gov.br/servicos/consultar-legislacao-da-sefaz"

# Piauí — RICMS/PI (Decreto 21.866/2023), atualização do art. 93 em 2025 e alíquota modal.
URL_PI_RICMS = "https://www.diario.pi.gov.br/doe/files/diarios/anexo/5714d565-bd46-4f50-950d-7fa74dbdc549/DIARIO-OFICIAL-DO-ESTADO-DO-PIAUI-PUBLICACAO-N-47.pdf"
URL_TO_LEI_1287 = "https://www.al.to.leg.br/arquivos/lei_1287-2001_68306.PDF"
URL_TO_LEI_1201 = "https://www.al.to.leg.br/arquivos/lei_1201-2000_51051.PDF"
URL_AC_IN_DIAT_01_2023 = "https://sefaz.ac.gov.br/2021/?p=16417"
URL_AM_LEI_6108 = "https://sistemas.sefaz.am.gov.br/get/Normas.do?metodo=viewDoc&uuidDoc=84be7172-451e-4ca0-802e-1a0303e5f0b2"
URL_AP_RICMS = "https://seadantigo.portal.ap.gov.br/diario/DOEn6091.pdf"
URL_RO_DEC_29048 = "https://legislacao.sefin.ro.gov.br/detalhe?lei=2284"
URL_PI_DECRETO_24244 = "https://www.diario.pi.gov.br/doe/files/diarios/anexo/e9755fe8-4b41-44be-a6f4-520a386f3b2f/DOEPI_240_2025.pdf"
URL_PI_MODAL_225 = "https://portal-admin.sefaz.pi.gov.br/wp-content/uploads/2025/03/SEI_GOV-PI-017374270-SEFAZ_-Comunicado-UNATRI.pdf"


class _ParserTabelasHTML(HTMLParser):
    """Extrai linhas e células de tabelas HTML usando apenas a biblioteca padrão."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.linhas: List[List[str]] = []
        self._linha: Optional[List[str]] = None
        self._celula: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        nome = tag.lower()
        if nome == "tr":
            self._linha = []
        elif nome in {"td", "th"} and self._linha is not None:
            self._celula = []
        elif nome == "br" and self._celula is not None:
            self._celula.append(" ")

    def handle_data(self, data: str) -> None:
        if self._celula is not None:
            self._celula.append(data)

    def handle_endtag(self, tag: str) -> None:
        nome = tag.lower()
        if nome in {"td", "th"} and self._celula is not None and self._linha is not None:
            texto = re.sub(r"\s+", " ", "".join(self._celula)).strip()
            self._linha.append(texto)
            self._celula = None
        elif nome == "tr" and self._linha is not None:
            if any(celula.strip() for celula in self._linha):
                self.linhas.append(self._linha)
            self._linha = None
            self._celula = None


@dataclass
class ResultadoAtualizacao:
    status: str
    lidos: int = 0
    inseridos: int = 0
    atualizados: int = 0
    sem_alteracao: int = 0
    mensagem: str = ""
    fontes_ok: int = 0
    fontes_erro: int = 0
    detalhes: List[str] = field(default_factory=list)


class AtualizadorFontesOficiais:
    def __init__(self, timeout: int = 40):
        self.timeout = timeout
        self.registrar_catalogo()

    @staticmethod
    def registrar_catalogo() -> None:
        BaseOficialRepository.registrar_fonte(
            "RFB_NCM", "Tabela NCM vigente", URL_RECEITA_NCM,
            "Receita Federal/Siscomex", "JSON",
        )
        BaseOficialRepository.registrar_fonte(
            "RFB_TIPI", "Tabela de Incidência do IPI — TIPI", URL_TIPI_PAGINA,
            "Receita Federal", "XLSX",
        )
        BaseOficialRepository.registrar_fonte(
            "CONFAZ", "Convênio ICMS 142/2018", URL_CONFAZ,
            "CONFAZ", "HTML",
        )
        BaseOficialRepository.registrar_fonte(
            "SEF_MG", "RICMS/MG 2023 e Anexo VII", URL_SEFAZ_MG,
            "SEF/MG", "HTML/PDF",
        )
        BaseOficialRepository.registrar_fonte(
            "SEF_MG_ST", "Aplicativo e consulta ST/MinasGerais", URL_SEFAZ_MG_ST,
            "SEF/MG", "APLICATIVO/HTML",
        )
        BaseOficialRepository.registrar_fonte(
            "SEF_MG_ST_AUTOPECAS",
            "RICMS/MG — Anexo VII, Parte 2, Capítulo 1 — Autopeças",
            URL_SEFAZ_MG_ST_AUTOPECAS, "SEF/MG", "HTML ESTRUTURADO",
        )
        BaseOficialRepository.registrar_fonte(
            "SEF_MG_ST_MATERIAIS_CONSTRUCAO",
            "RICMS/MG — Anexo VII, Parte 2, Segmento 10 — Materiais de construção e congêneres",
            URL_SEFAZ_MG_ST_MATERIAIS_CONSTRUCAO, "SEF/MG", "HTML ESTRUTURADO",
        )
        BaseOficialRepository.registrar_fonte(
            "SEF_MG_ST_PNEUMATICOS",
            "RICMS/MG — Anexo VII, Parte 2, Segmento 16 — Pneumáticos",
            URL_SEFAZ_MG_ST_PNEUMATICOS, "SEF/MG", "HTML ESTRUTURADO",
        )
        BaseOficialRepository.registrar_fonte(
            "SEF_MG_ST_COMPLETA",
            "RICMS/MG — Anexo VII, Parte 2 — cobertura ampliada dos segmentos",
            URL_SEFAZ_MG_ST_PAGINAS[0], "SEF/MG", "HTML ESTRUTURADO",
        )
        BaseOficialRepository.registrar_fonte(
            "RTC_CCLASSTRIB", "CST e cClassTrib IBS/CBS", URL_CCLASSTRIB,
            "Portal DF-e/SVRS", "TABELA",
        )
        BaseOficialRepository.registrar_fonte(
            "RFB_PISCOFINS", "Orientações e legislação PIS/Cofins", URL_PISCOFINS,
            "Receita Federal", "HTML",
        )
        BaseOficialRepository.registrar_fonte(
            "PLANALTO_L10485", "Lei nº 10.485/2002 — PIS/Cofins monofásico", URL_LEI_10485,
            "Presidência da República / Planalto", "LEI COMPILADA",
        )
        BaseOficialRepository.registrar_fonte(
            "PLANALTO_L10637", "Lei nº 10.637/2002 — PIS/Pasep não cumulativo", URL_LEI_10637,
            "Presidência da República / Planalto", "LEI COMPILADA",
        )
        BaseOficialRepository.registrar_fonte(
            "PLANALTO_L10833", "Lei nº 10.833/2003 — Cofins não cumulativa", URL_LEI_10833,
            "Presidência da República / Planalto", "LEI COMPILADA",
        )
        BaseOficialRepository.registrar_fonte(
            "SPED_PISCOFINS_4310", "Tabela 4.3.10 — Produtos sujeitos à incidência monofásica",
            URL_SPED_TABELA_4310, "Receita Federal / SPED", "TABELA OFICIAL",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFA_RN", "Lei RN nº 11.999/2024 — alíquota modal do ICMS",
            URL_RN_LEI_11999, "SEFAZ/RN / Assembleia Legislativa do RN", "LEI ESTADUAL",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_RN_ANEXO_005", "RICMS/RN — Anexo 005 — Antecipação do ICMS",
            URL_RN_ANEXO_005, "SEFAZ/RN / Diário Oficial do RN", "RICMS — ANEXO",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_RN_ANEXO_007", "RICMS/RN — Anexo 007 — Substituição Tributária",
            URL_RN_ANEXO_007, "SEFAZ/RN / Diário Oficial do RN", "RICMS — ANEXO",
        )

        BaseOficialRepository.registrar_fonte(
            "SEFAZ_SE_RICMS", "RICMS/SE — Decreto nº 21.400/2002 — texto consolidado",
            URL_SE_RICMS, "Governo de Sergipe / LegisOn", "RICMS CONSOLIDADO",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_MA_RICMS", "RICMS/MA e legislação tributária estadual — autopeças/pneumáticos",
            URL_MA_LEGISLACAO, "SEFAZ/MA / Governo do Maranhão", "LEGISLAÇÃO ESTADUAL",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_PI_RICMS", "RICMS/PI — Anexo X — autopeças e pneumáticos",
            URL_PI_RICMS, "SEFAZ/PI / Diário Oficial do Piauí", "RICMS — ANEXO",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_TO_ICMS", "Código Tributário/TO — ICMS e alíquota interna",
            URL_TO_LEI_1287, "Assembleia Legislativa do Tocantins", "LEI ESTADUAL",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_TO_ANEXO_XXI", "RICMS/TO — Anexo XXI — autopeças e pneumáticos",
            URL_TO_LEI_1201, "Assembleia Legislativa do Tocantins", "LEGISLAÇÃO ESTADUAL / ANEXO XXI",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_AC_IN_DIAT_01_2023", "IN DIAT/SEFAZ-AC nº 1/2023 — autopeças e pneumáticos",
            URL_AC_IN_DIAT_01_2023, "SEFAZ/AC", "INSTRUÇÃO NORMATIVA / TABELAS ST",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_AM_LEI_6108", "Lei AM nº 6.108/2022 — autopeças e pneumáticos",
            URL_AM_LEI_6108, "SEFAZ/AM", "LEI ESTADUAL / TABELAS ST",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_AP_RICMS", "RICMS/AP — autopeças e pneumáticos",
            URL_AP_RICMS, "SEFAZ/AP", "REGULAMENTO ESTADUAL / TABELAS ST",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFIN_RO_DEC_29048", "Decreto RO nº 29.048/2024 — tabelas ST e MVA",
            URL_RO_DEC_29048, "SEFIN/RO", "DECRETO ESTADUAL / TABELAS ST",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_PI_DEC_24244", "Decreto PI nº 24.244/2025 — atualização da responsabilidade ST",
            URL_PI_DECRETO_24244, "Governo do Piauí / Diário Oficial", "DECRETO ESTADUAL",
        )
        BaseOficialRepository.registrar_fonte(
            "SEFAZ_PI_MODAL", "SEFAZ/PI — alíquota interna modal 22,5%",
            URL_PI_MODAL_225, "SEFAZ/PI — UNATRI", "COMUNICADO OFICIAL",
        )

    def atualizar_todas(self) -> ResultadoAtualizacao:
        ncm = self.atualizar_ncm_receita()
        tipi = self.atualizar_tipi_receita()
        st_completa = self.atualizar_st_mg_completa()

        resultados_tabelas = (ncm, tipi, st_completa)
        resultado = ResultadoAtualizacao(status="SUCESSO")
        resultado.lidos = sum(item.lidos for item in resultados_tabelas)
        resultado.inseridos = sum(item.inseridos for item in resultados_tabelas)
        resultado.atualizados = sum(item.atualizados for item in resultados_tabelas)
        resultado.sem_alteracao = sum(item.sem_alteracao for item in resultados_tabelas)
        resultado.detalhes.extend([
            f"NCM: {ncm.mensagem}",
            f"TIPI: {tipi.mensagem}",
            f"ST/MG Parte 2 completa: {st_completa.mensagem}",
        ])

        criticos_ok = sum(item.status == "SUCESSO" for item in (ncm, tipi))
        st_ok = st_completa.status == "SUCESSO"
        if criticos_ok == 0:
            resultado.status = "ERRO"
        elif criticos_ok < 2 or not st_ok:
            resultado.status = "PARCIAL"

        for codigo, url in (
            ("CONFAZ", URL_CONFAZ),
            ("SEF_MG", URL_SEFAZ_MG),
            ("SEF_MG_ST", URL_SEFAZ_MG_ST),
            ("RTC_CCLASSTRIB", URL_CCLASSTRIB),
        ):
            ok, msg = self._testar_fonte(codigo, url)
            if ok:
                resultado.fontes_ok += 1
                resultado.detalhes.append(f"{codigo}: disponível")
            else:
                resultado.fontes_erro += 1
                rotulo = "falha de certificado SSL" if "CERTIFICATE_VERIFY_FAILED" in msg else "indisponível"
                resultado.detalhes.append(f"{codigo}: {rotulo} ({msg})")

        resultado.fontes_ok += criticos_ok + int(st_ok)
        resultado.fontes_erro += (2 - criticos_ok) + (0 if st_ok else 1)
        cobertura = BaseOficialRepository.resumo_st_mg()
        selo = "COMPLETA" if cobertura.get("base_completa") else "INCOMPLETA"
        resultado.mensagem = (
            f"NCMs lidos: {ncm.lidos}. Registros TIPI: {tipi.lidos}. "
            f"ST/MG: {st_completa.lidos} registros em "
            f"{int(cobertura.get('segmentos') or 0)} segmentos — base {selo}. "
            f"Fontes disponíveis: {resultado.fontes_ok}; falhas: {resultado.fontes_erro}."
        )

        # Reaplica o pacote offline para recompor descrições hierárquicas após
        # uma sincronização do Classif, preservando os códigos recém-baixados.
        try:
            from src.services.base_ncm_nacional_service import BaseNCMNacionalService

            base = BaseNCMNacionalService.garantir_instalada(forcar=True)
            resultado.detalhes.append(
                f"Base nacional offline: {base.total_ncm} NCMs e "
                f"{base.total_tipi} registros TIPI."
            )
        except Exception as exc:
            resultado.detalhes.append(
                f"Base nacional offline: não foi possível enriquecer descrições ({exc})."
            )
        return resultado

    def _testar_fonte(self, codigo: str, url: str) -> Tuple[bool, str]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FiscalPro/1.0"})
            with urllib.request.urlopen(req, timeout=min(self.timeout, 20)) as resp:
                status = getattr(resp, "status", 200)
                ok = 200 <= status < 400
            BaseOficialRepository.atualizar_status_fonte(
                codigo, "DISPONIVEL" if ok else "ERRO", f"HTTP {status}"
            )
            return ok, f"HTTP {status}"
        except Exception as exc:
            BaseOficialRepository.atualizar_status_fonte(codigo, "ERRO", str(exc))
            return False, str(exc)

    def atualizar_st_mg_autopecas(self) -> ResultadoAtualizacao:
        log_id = BaseOficialRepository.iniciar_atualizacao("SEF_MG_ST_AUTOPECAS")
        resultado = ResultadoAtualizacao(status="ERRO")
        try:
            req = urllib.request.Request(
                URL_SEFAZ_MG_ST_AUTOPECAS,
                headers={"User-Agent": "Mozilla/5.0 FiscalPro/1.0", "Accept": "text/html,*/*"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                conteudo = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
            try:
                html = conteudo.decode(charset, errors="strict")
            except (LookupError, UnicodeDecodeError):
                html = conteudo.decode("latin-1", errors="replace")

            registros = self.ler_st_mg_autopecas_html(html)
            if len(registros) < 100:
                raise ValueError(
                    f"a página foi acessada, mas somente {len(registros)} registros válidos foram reconhecidos"
                )

            BaseOficialRepository.substituir_st_mg_segmento(
                registros,
                segmento="AUTOPEÇAS",
                fonte_codigo="SEF_MG_ST_AUTOPECAS",
                referencia="RICMS/MG/2023 — Anexo VII vigente",
            )
            resultado.status = "SUCESSO"
            resultado.lidos = len(registros)
            resultado.inseridos = len(registros)
            resultado.mensagem = "Tabela oficial de autopeças do Anexo VII sincronizada."
            BaseOficialRepository.atualizar_status_fonte(
                "SEF_MG_ST_AUTOPECAS", "DISPONIVEL", f"{len(registros)} registros lidos"
            )
            BaseOficialRepository.salvar_evidencia(
                None,
                "ST_MG_AUTOPECAS_VIGENTE",
                {"registros": len(registros), "segmento": "AUTOPEÇAS"},
                "SEF_MG_ST_AUTOPECAS",
                URL_SEFAZ_MG_ST_AUTOPECAS,
                confiabilidade=1.0,
                status="VALIDADO",
                observacao=(
                    "CEST, NCM, descrição, âmbito e MVA extraídos do Capítulo 1 da Parte 2 "
                    "do Anexo VII do RICMS/MG."
                ),
            )
        except Exception as exc:
            resultado.mensagem = f"Não foi possível sincronizar a tabela ST/MG de autopeças: {exc}"
            BaseOficialRepository.atualizar_status_fonte("SEF_MG_ST_AUTOPECAS", "ERRO", str(exc))
        finally:
            BaseOficialRepository.finalizar_atualizacao(
                log_id, resultado.status, resultado.lidos, resultado.inseridos,
                resultado.atualizados, resultado.mensagem,
            )
        return resultado

    def atualizar_st_mg_materiais_construcao(self) -> ResultadoAtualizacao:
        """Sincroniza o segmento 10, incluindo parafusos e itens semelhantes do NCM 7318."""
        codigo_fonte = "SEF_MG_ST_MATERIAIS_CONSTRUCAO"
        log_id = BaseOficialRepository.iniciar_atualizacao(codigo_fonte)
        resultado = ResultadoAtualizacao(status="ERRO")
        try:
            req = urllib.request.Request(
                URL_SEFAZ_MG_ST_MATERIAIS_CONSTRUCAO,
                headers={"User-Agent": "Mozilla/5.0 FiscalPro/1.0", "Accept": "text/html,*/*"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                conteudo = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
            try:
                html = conteudo.decode(charset, errors="strict")
            except (LookupError, UnicodeDecodeError):
                html = conteudo.decode("latin-1", errors="replace")

            registros = self.ler_st_mg_materiais_construcao_html(html)
            if len(registros) < 45:
                raise ValueError(
                    f"a página foi acessada, mas somente {len(registros)} registros válidos foram reconhecidos"
                )

            BaseOficialRepository.substituir_st_mg_segmento(
                registros,
                segmento="MATERIAIS DE CONSTRUÇÃO E CONGÊNERES",
                fonte_codigo=codigo_fonte,
                referencia="RICMS/MG/2023 — Anexo VII vigente",
            )
            resultado.status = "SUCESSO"
            resultado.lidos = len(registros)
            resultado.inseridos = len(registros)
            resultado.mensagem = "Tabela oficial de materiais de construção e congêneres sincronizada."
            BaseOficialRepository.atualizar_status_fonte(
                codigo_fonte, "DISPONIVEL", f"{len(registros)} registros lidos"
            )
            BaseOficialRepository.salvar_evidencia(
                None,
                "ST_MG_MATERIAIS_CONSTRUCAO_VIGENTE",
                {"registros": len(registros), "segmento": "MATERIAIS DE CONSTRUÇÃO E CONGÊNERES"},
                codigo_fonte,
                URL_SEFAZ_MG_ST_MATERIAIS_CONSTRUCAO,
                confiabilidade=1.0,
                status="VALIDADO",
                observacao=(
                    "CEST, NCM, descrição, âmbito e MVA extraídos do segmento 10 da Parte 2 "
                    "do Anexo VII do RICMS/MG, incluindo o CEST 10.058.00 para o NCM 7318."
                ),
            )
        except Exception as exc:
            resultado.mensagem = (
                "Não foi possível sincronizar a tabela ST/MG de materiais de construção e congêneres: "
                f"{exc}"
            )
            BaseOficialRepository.atualizar_status_fonte(codigo_fonte, "ERRO", str(exc))
        finally:
            BaseOficialRepository.finalizar_atualizacao(
                log_id, resultado.status, resultado.lidos, resultado.inseridos,
                resultado.atualizados, resultado.mensagem,
            )
        return resultado

    def atualizar_st_mg_pneumaticos(self) -> ResultadoAtualizacao:
        """Sincroniza o segmento 16: pneumáticos, câmaras de ar e protetores."""
        log_id = BaseOficialRepository.iniciar_atualizacao("SEF_MG_ST_PNEUMATICOS")
        resultado = ResultadoAtualizacao(status="ERRO")
        try:
            req = urllib.request.Request(
                URL_SEFAZ_MG_ST_PNEUMATICOS,
                headers={"User-Agent": "Mozilla/5.0 FiscalPro/1.0", "Accept": "text/html,*/*"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                conteudo = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
            try:
                html = conteudo.decode(charset, errors="strict")
            except (LookupError, UnicodeDecodeError):
                html = conteudo.decode("latin-1", errors="replace")

            registros = self.ler_st_mg_pneumaticos_html(html)
            if len(registros) < 7:
                raise ValueError(
                    f"a página foi acessada, mas somente {len(registros)} registros válidos foram reconhecidos"
                )

            BaseOficialRepository.substituir_st_mg_segmento(
                registros,
                segmento="PNEUMÁTICOS",
                fonte_codigo="SEF_MG_ST_PNEUMATICOS",
                referencia="RICMS/MG/2023 — Anexo VII vigente",
            )
            resultado.status = "SUCESSO"
            resultado.lidos = len(registros)
            resultado.inseridos = len(registros)
            resultado.mensagem = "Tabela oficial de pneumáticos do Anexo VII sincronizada."
            BaseOficialRepository.atualizar_status_fonte(
                "SEF_MG_ST_PNEUMATICOS", "DISPONIVEL", f"{len(registros)} registros lidos"
            )
            BaseOficialRepository.salvar_evidencia(
                None,
                "ST_MG_PNEUMATICOS_VIGENTE",
                {"registros": len(registros), "segmento": "PNEUMÁTICOS"},
                "SEF_MG_ST_PNEUMATICOS",
                URL_SEFAZ_MG_ST_PNEUMATICOS,
                confiabilidade=1.0,
                status="VALIDADO",
                observacao=(
                    "CEST, NCM, descrição, âmbito e MVA extraídos do segmento 16 da Parte 2 "
                    "do Anexo VII do RICMS/MG."
                ),
            )
        except Exception as exc:
            resultado.mensagem = f"Não foi possível sincronizar a tabela ST/MG de pneumáticos: {exc}"
            BaseOficialRepository.atualizar_status_fonte("SEF_MG_ST_PNEUMATICOS", "ERRO", str(exc))
        finally:
            BaseOficialRepository.finalizar_atualizacao(
                log_id, resultado.status, resultado.lidos, resultado.inseridos,
                resultado.atualizados, resultado.mensagem,
            )
        return resultado


    def atualizar_st_mg_completa(self) -> ResultadoAtualizacao:
        """Sincroniza toda a Parte 2 vigente do Anexo VII do RICMS/MG.

        A partir da 17.8.119, a base completa é a fonte primária do motor de ST:
        se a sincronização integral estiver validada e o NCM não aparecer em
        nenhuma linha nominal, a ausência passa a ser evidência para ``NÃO ST``
        (ressalvadas regras sem NCM, como o residual 01.999.00 de autopeças).

        Linhas com PMPF, preço fixado ou MVA textual também são armazenadas.
        Elas podem exigir revisão de cálculo, mas continuam essenciais para
        saber se a mercadoria pertence ou não à tabela oficial.
        """
        codigo_fonte = "SEF_MG_ST_COMPLETA"
        log_id = BaseOficialRepository.iniciar_atualizacao(codigo_fonte)
        resultado = ResultadoAtualizacao(status="ERRO")
        try:
            paginas: List[str] = []
            for url in URL_SEFAZ_MG_ST_PAGINAS:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 FiscalPro/17.8.120",
                        "Accept": "text/html,*/*",
                    },
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    conteudo = resp.read()
                    charset = resp.headers.get_content_charset() or "utf-8"
                try:
                    paginas.append(conteudo.decode(charset, errors="strict"))
                except (LookupError, UnicodeDecodeError):
                    paginas.append(conteudo.decode("latin-1", errors="replace"))

            html = "\n".join(paginas)

            residuais_sem_ncm = self._ler_st_mg_residuais_sem_ncm_html(html)
            cests_residuais = {str(item.get("cest") or "") for item in residuais_sem_ncm}
            desconhecidos = cests_residuais - RESIDUAIS_ST_MG_SEM_NCM_SUPORTADOS
            ausentes_esperados = RESIDUAIS_ST_MG_SEM_NCM_SUPORTADOS - cests_residuais
            if desconhecidos:
                raise ValueError(
                    "a SEF/MG publicou regra residual sem NCM ainda não suportada pelo motor: "
                    + ", ".join(sorted(desconhecidos))
                    + ". A base anterior foi preservada para evitar falso NÃO ST"
                )
            if ausentes_esperados:
                raise ValueError(
                    "a leitura integral não reconheceu as regras residuais esperadas sem NCM: "
                    + ", ".join(sorted(ausentes_esperados))
                    + ". A base anterior foi preservada"
                )

            unicos: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
            segmentos_com_dados: set[str] = set()
            for prefixo, segmento in SEGMENTOS_ST_MG.items():
                registros_segmento = self._ler_st_mg_segmento_html(
                    html,
                    prefixo_cest=prefixo,
                    segmento=segmento,
                    fonte_codigo=codigo_fonte,
                )
                if registros_segmento:
                    segmentos_com_dados.add(segmento)
                for item in registros_segmento:
                    chave = (
                        str(item.get("segmento") or ""),
                        str(item.get("item") or ""),
                        str(item.get("cest") or ""),
                        str(item.get("ncm_digitos") or ""),
                    )
                    unicos.setdefault(chave, item)

            registros = list(unicos.values())
            # A Parte 2 possui muitos capítulos. Os limites abaixo não tentam
            # fixar a quantidade exata (que muda com decretos), mas impedem que
            # uma página de erro ou uma leitura parcial seja promovida a base
            # completa e gere falsos "NÃO ST".
            if len(registros) < 300 or len(segmentos_com_dados) < 20:
                raise ValueError(
                    "a leitura integral parece incompleta: "
                    f"{len(registros)} registros em {len(segmentos_com_dados)} segmentos; "
                    "a base completa anterior foi preservada"
                )

            BaseOficialRepository.substituir_st_mg(
                registros, referencia="RICMS/MG/2023 — Anexo VII, Parte 2 vigente"
            )
            BaseOficialRepository.registrar_status_st_mg(
                base_completa=True,
                versao_schema=ST_MG_SCHEMA_VERSAO,
                paginas=len(URL_SEFAZ_MG_ST_PAGINAS),
                segmentos=len(segmentos_com_dados),
                registros=len(registros),
                referencia="RICMS/MG/2023 — Anexo VII, Parte 2 vigente",
                fonte_url=URL_SEFAZ_MG_ST_PAGINAS[0],
            )
            resultado.status = "SUCESSO"
            resultado.lidos = len(registros)
            resultado.inseridos = len(registros)
            resultado.mensagem = (
                f"Parte 2 do Anexo VII sincronizada por inteiro: {len(registros)} registros "
                f"nominais em {len(segmentos_com_dados)} segmentos."
            )
            resultado.detalhes.append(
                "A base inclui linhas com MVA numérica e também linhas cujo cálculo usa PMPF, "
                "preço fixado ou regra textual. Ausência de NCM só vira NÃO ST quando este selo "
                "de base completa estiver ativo."
            )
            resultado.detalhes.append(
                "As regras sem NCM fechado 01.999.00 (autopeças) e 28.999.00 (porta a porta) "
                "são avaliadas pelo contexto antes de qualquer negativa por ausência nominal."
            )
            BaseOficialRepository.atualizar_status_fonte(
                codigo_fonte, "DISPONIVEL", resultado.mensagem
            )
            BaseOficialRepository.salvar_evidencia(
                None,
                "ST_MG_PARTE2_COMPLETA_V2",
                {
                    "registros": len(registros),
                    "segmentos": len(segmentos_com_dados),
                    "paginas": len(URL_SEFAZ_MG_ST_PAGINAS),
                    "schema": ST_MG_SCHEMA_VERSAO,
                    "residuais_sem_ncm": sorted(cests_residuais),
                },
                codigo_fonte,
                URL_SEFAZ_MG_ST_PAGINAS[0],
                confiabilidade=1.0,
                status="VALIDADO",
                observacao=(
                    "Extração nominal completa da Parte 2 do Anexo VII (páginas 4/7 a 6/7), "
                    "incluindo registros com MVA textual/não numérica."
                ),
            )
        except Exception as exc:
            resultado.mensagem = f"Não foi possível sincronizar a Parte 2 completa do ST/MG: {exc}"
            BaseOficialRepository.atualizar_status_fonte(codigo_fonte, "ERRO", str(exc))
        finally:
            BaseOficialRepository.finalizar_atualizacao(
                log_id, resultado.status, resultado.lidos, resultado.inseridos,
                resultado.atualizados, resultado.mensagem,
            )
        return resultado

    @classmethod
    def _extrair_prefixos_nbm_sh(cls, texto: str) -> List[Tuple[str, str]]:
        """Converte a célula oficial NBM/SH em prefixos pesquisáveis.

        A Parte 2 usa vários níveis de granularidade: capítulo (``39``),
        posição (``8508``), subposição (``8471.60.5``), NCM completo e também
        expressões como ``Capítulos 13 e 15 a 23``. O índice local trabalha
        por prefixo; por isso dois dígitos também são válidos quando a própria
        SEF/MG publica a regra no nível do capítulo.
        """
        bruto = re.sub(r"\s+", " ", str(texto or "")).strip()
        if not bruto:
            return []

        encontrados: List[Tuple[str, str]] = []
        vistos: set[str] = set()

        def adicionar(formatado: str, digitos: str) -> None:
            codigo = cls._digitos(digitos)
            if 2 <= len(codigo) <= 8 and codigo not in vistos:
                vistos.add(codigo)
                encontrados.append((formatado.strip(), codigo))

        # Cobertura publicada no nível de capítulo, inclusive intervalos como
        # "Capítulos 13 e 15 a 23".
        if re.search(r"\bCAP[IÍ]TULOS?\b", bruto, flags=re.IGNORECASE):
            parte = re.sub(r"^.*?CAP[IÍ]TULOS?\s*", "", bruto, flags=re.IGNORECASE)
            ocupados: List[Tuple[int, int]] = []
            for m in re.finditer(r"(?<!\d)(\d{1,2})\s*(?:A|ATÉ|-)\s*(\d{1,2})(?!\d)", parte, flags=re.IGNORECASE):
                ini, fim = int(m.group(1)), int(m.group(2))
                if 0 <= ini <= fim <= 99 and fim - ini <= 40:
                    for cap in range(ini, fim + 1):
                        adicionar(f"Capítulo {cap:02d}", f"{cap:02d}")
                ocupados.append(m.span())

            parte_soltos = parte
            for a, b in reversed(ocupados):
                parte_soltos = parte_soltos[:a] + " " * (b - a) + parte_soltos[b:]
            for numero in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", parte_soltos):
                cap = int(numero)
                if 0 <= cap <= 99:
                    adicionar(f"Capítulo {cap:02d}", f"{cap:02d}")
            return encontrados

        # Demais células trazem códigos/prefixos NBM-SH diretamente, por
        # exemplo 08.13, 2202.99.00, 8471.60.5, 8508 e 9405.1.
        padrao = re.compile(r"(?<!\d)(\d{2,4}(?:\.\d{1,2}){0,3})(?!\d)")
        for token in padrao.findall(bruto):
            digitos = cls._digitos(token)
            if 4 <= len(digitos) <= 8:
                adicionar(token, digitos)
        return encontrados

    @classmethod
    def _ler_st_mg_residuais_sem_ncm_html(cls, html: str) -> List[Dict[str, Any]]:
        """Localiza somente linhas cuja coluna NBM/SH está realmente vazia.

        A SEF/MG também publica coberturas amplas como ``08.13`` e
        ``Capítulos 39, 42...``. Elas não são regras residuais: continuam tendo
        cobertura NBM/SH e precisam entrar no índice nominal.
        """
        parser = _ParserTabelasHTML()
        parser.feed(html)
        regex_cest = re.compile(r"\d{2}\.\d{3}\.\d{2}")
        regex_ambito = re.compile(r"(?<!\d)(\d{1,2}\.\d)(?!\d)")
        encontrados: Dict[str, Dict[str, Any]] = {}

        for celulas_brutas in parser.linhas:
            celulas = [re.sub(r"\s+", " ", str(c or "")).strip() for c in celulas_brutas]
            indice_cest = next(
                (i for i, texto in enumerate(celulas) if regex_cest.fullmatch(texto)),
                None,
            )
            if indice_cest is None:
                continue

            cest = celulas[indice_cest]
            cauda = celulas[indice_cest + 1:]
            if len(cauda) < 2:
                continue

            # Pela estrutura oficial da Parte 2, a primeira coluna após CEST é
            # NBM/SH. Só é residual quando essa célula está vazia.
            nbm_sh = cauda[0].strip()
            if nbm_sh:
                continue

            descricao = cauda[1].strip() if len(cauda) > 1 else ""
            if not descricao:
                continue
            posteriores = [texto for texto in cauda[2:] if texto]
            ambitos: List[str] = []
            for texto in posteriores:
                for codigo_ambito in regex_ambito.findall(texto):
                    if codigo_ambito not in ambitos:
                        ambitos.append(codigo_ambito)

            partes_mva: List[str] = []
            for texto in posteriores:
                sem_ambito = regex_ambito.sub("", texto)
                if re.sub(r"[ /;,-]+", "", sem_ambito):
                    partes_mva.append(texto)
            mva_texto = " | ".join(partes_mva)
            valores = [
                valor for valor in (cls._extrair_percentual(parte) for parte in partes_mva)
                if valor is not None
            ]
            mva = valores[0] if len(valores) == 1 else None

            item = ""
            for texto in reversed(celulas[:indice_cest]):
                match = re.search(r"(?<!\d)(\d{1,3}(?:\.\d)?)(?!\d)", texto)
                if match:
                    item = match.group(1)
                    break

            encontrados[cest] = {
                "item": item,
                "cest": cest,
                "descricao": descricao,
                "ambito": " / ".join(ambitos),
                "mva": mva,
                "mva_texto": mva_texto,
            }

        return list(encontrados.values())

    @classmethod
    def ler_st_mg_autopecas_html(cls, html: str) -> List[Dict[str, Any]]:
        return cls._ler_st_mg_segmento_html(
            html,
            prefixo_cest="01",
            segmento="AUTOPEÇAS",
            fonte_codigo="SEF_MG_ST_AUTOPECAS",
        )

    @classmethod
    def ler_st_mg_materiais_construcao_html(cls, html: str) -> List[Dict[str, Any]]:
        return cls._ler_st_mg_segmento_html(
            html,
            prefixo_cest="10",
            segmento="MATERIAIS DE CONSTRUÇÃO E CONGÊNERES",
            fonte_codigo="SEF_MG_ST_MATERIAIS_CONSTRUCAO",
        )

    @classmethod
    def ler_st_mg_pneumaticos_html(cls, html: str) -> List[Dict[str, Any]]:
        return cls._ler_st_mg_segmento_html(
            html,
            prefixo_cest="16",
            segmento="PNEUMÁTICOS",
            fonte_codigo="SEF_MG_ST_PNEUMATICOS",
        )

    @classmethod
    def _ler_st_mg_segmento_html(
        cls,
        html: str,
        *,
        prefixo_cest: str,
        segmento: str,
        fonte_codigo: str,
    ) -> List[Dict[str, Any]]:
        """Extrai linhas nominais de um segmento da Parte 2 do Anexo VII.

        Preserva a granularidade publicada pela SEF/MG. Além de NCMs de 8
        dígitos, aceita posição/subposição e capítulos inteiros, que são
        indexados como prefixos para a consulta local.
        """
        parser = _ParserTabelasHTML()
        parser.feed(html)
        registros: List[Dict[str, Any]] = []
        itens_processados: set[Tuple[str, str]] = set()
        regex_cest = re.compile(rf"{re.escape(prefixo_cest)}\.\d{{3}}\.\d{{2}}")
        regex_ambito = re.compile(r"(?<!\d)(\d{1,2}\.\d)(?!\d)")

        for celulas_brutas in parser.linhas:
            celulas = [re.sub(r"\s+", " ", str(c or "")).strip() for c in celulas_brutas]
            indice_cest = next(
                (i for i, texto in enumerate(celulas) if regex_cest.fullmatch(texto)),
                None,
            )
            if indice_cest is None:
                continue

            item = ""
            for texto in reversed(celulas[:indice_cest]):
                correspondencia = re.search(r"(?<!\d)(\d{1,3}(?:\.\d)?)(?!\d)", texto)
                if correspondencia:
                    item = correspondencia.group(1)
                    break
            if not item:
                continue

            cest = celulas[indice_cest]
            chave_item = (item, cest)
            if chave_item in itens_processados:
                continue

            cauda = celulas[indice_cest + 1:]
            if len(cauda) < 2:
                continue

            # Estrutura oficial: NBM/SH vem imediatamente após o CEST e a
            # descrição vem na coluna seguinte. Célula NBM/SH vazia identifica
            # regra residual e é tratada fora do índice nominal.
            nbm_sh = cauda[0].strip()
            prefixos = cls._extrair_prefixos_nbm_sh(nbm_sh)
            if not prefixos:
                continue

            descricao = cauda[1].strip() if len(cauda) > 1 else ""
            if not descricao:
                continue

            posteriores = [texto for texto in cauda[2:] if texto]
            codigos_ambito: List[str] = []
            for texto in posteriores:
                for codigo_ambito in regex_ambito.findall(texto):
                    if codigo_ambito not in codigos_ambito:
                        codigos_ambito.append(codigo_ambito)
            ambito = " / ".join(codigos_ambito)

            partes_mva: List[str] = []
            for texto in posteriores:
                limpo = texto.strip()
                if not limpo:
                    continue
                sem_ambito = regex_ambito.sub("", limpo)
                sem_ambito = re.sub(r"[ /;,-]+", "", sem_ambito)
                if not sem_ambito:
                    continue
                partes_mva.append(limpo)
            mva_texto = " | ".join(partes_mva)

            valores_mva = [
                cls._extrair_percentual(parte)
                for parte in partes_mva
                if cls._extrair_percentual(parte) is not None
            ]
            mva = valores_mva[0] if len(valores_mva) == 1 else None

            itens_processados.add(chave_item)
            for ncm_formatado, ncm_digitos in prefixos:
                registros.append({
                    "segmento": segmento,
                    "item": item,
                    "cest": cest,
                    "ncm_formatado": ncm_formatado,
                    "ncm_digitos": ncm_digitos,
                    "descricao": descricao,
                    "ambito": ambito,
                    "mva": mva,
                    "mva_texto": mva_texto,
                    "fonte_codigo": fonte_codigo,
                })

        return registros

    @staticmethod
    def _extrair_percentual(valor: Any) -> Optional[float]:
        """Extrai MVA apenas quando a célula representa um valor numérico claro.

        Textos legais como ``Vide Capítulo XII do Título II da Parte 1`` não
        podem virar MVA 1,00% só porque contêm um algarismo. Esses textos são
        preservados em ``mva_texto`` e exigem a regra de cálculo específica.
        """
        texto = str(valor or "").strip()
        correspondencia = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*%?\s*", texto)
        if not correspondencia:
            return None
        numero = correspondencia.group(1)
        if "," in numero:
            numero = numero.replace(".", "").replace(",", ".")
        try:
            return float(numero)
        except ValueError:
            return None

    def atualizar_ncm_receita(self) -> ResultadoAtualizacao:
        log_id = BaseOficialRepository.iniciar_atualizacao("RFB_NCM")
        resultado = ResultadoAtualizacao(status="ERRO")
        try:
            req = urllib.request.Request(URL_NCM_JSON, headers={"User-Agent": "FiscalPro/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8-sig"))
            registros_oficiais: List[Dict[str, str]] = []
            for item in self._extrair_itens(payload):
                codigo = self._digitos(
                    item.get("Codigo") or item.get("codigo") or item.get("code") or item.get("ncm")
                )
                descricao = str(
                    item.get("Descricao") or item.get("descricao") or item.get("description") or ""
                ).strip()
                if len(codigo) != 8 or not descricao:
                    continue
                resultado.lidos += 1
                registros_oficiais.append({"ncm": codigo, "descricao": descricao})
            contagem = NCMRepository.sincronizar_lote(registros_oficiais)
            resultado.inseridos = contagem["inseridos"]
            resultado.atualizados = contagem["atualizados"]
            resultado.sem_alteracao = contagem["sem_alteracao"]
            BaseOficialRepository.substituir_ncm_oficial(registros_oficiais)
            resultado.status = "SUCESSO"
            resultado.mensagem = "Tabela NCM oficial sincronizada."
            BaseOficialRepository.atualizar_status_fonte(
                "RFB_NCM", "DISPONIVEL", f"{resultado.lidos} NCMs lidos"
            )
            BaseOficialRepository.salvar_evidencia(
                None,
                "TABELA_NCM_VIGENTE",
                {"registros": resultado.lidos},
                "RFB_NCM",
                URL_RECEITA_NCM,
                confiabilidade=1.0,
                status="VALIDADO",
                observacao="Tabela estruturada oficial.",
            )
        except Exception as exc:
            resultado.mensagem = f"Não foi possível acessar a tabela NCM oficial: {exc}"
            BaseOficialRepository.atualizar_status_fonte("RFB_NCM", "ERRO", str(exc))
        finally:
            BaseOficialRepository.finalizar_atualizacao(
                log_id, resultado.status, resultado.lidos, resultado.inseridos,
                resultado.atualizados, resultado.mensagem,
            )
        return resultado

    def atualizar_tipi_receita(self) -> ResultadoAtualizacao:
        log_id = BaseOficialRepository.iniciar_atualizacao("RFB_TIPI")
        resultado = ResultadoAtualizacao(status="ERRO")
        arquivo: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as temporario:
                arquivo = Path(temporario.name)
            self._baixar(URL_TIPI_XLSX, arquivo)
            registros = self.ler_tipi_xlsx(arquivo)
            if not registros:
                raise ValueError("a planilha oficial foi baixada, mas nenhum NCM da TIPI foi reconhecido")

            BaseOficialRepository.substituir_tipi(registros, referencia="TIPI oficial vigente")
            resultado.status = "SUCESSO"
            resultado.lidos = len(registros)
            resultado.inseridos = len(registros)
            resultado.mensagem = "TIPI oficial sincronizada."
            BaseOficialRepository.atualizar_status_fonte(
                "RFB_TIPI", "DISPONIVEL", f"{len(registros)} registros lidos"
            )
            BaseOficialRepository.salvar_evidencia(
                None,
                "TIPI_VIGENTE",
                {"registros": len(registros)},
                "RFB_TIPI",
                URL_TIPI_PAGINA,
                confiabilidade=1.0,
                status="VALIDADO",
                observacao="Alíquotas de IPI extraídas da planilha oficial da Receita Federal.",
            )
        except Exception as exc:
            resultado.mensagem = f"Não foi possível sincronizar a TIPI oficial: {exc}"
            BaseOficialRepository.atualizar_status_fonte("RFB_TIPI", "ERRO", str(exc))
        finally:
            if arquivo is not None:
                try:
                    arquivo.unlink(missing_ok=True)
                except Exception:
                    pass
            BaseOficialRepository.finalizar_atualizacao(
                log_id, resultado.status, resultado.lidos, resultado.inseridos,
                resultado.atualizados, resultado.mensagem,
            )
        return resultado

    def _baixar(self, url: str, destino: Path) -> None:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 FiscalPro/1.0",
                "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resposta, destino.open("wb") as saida:
            while True:
                bloco = resposta.read(1024 * 128)
                if not bloco:
                    break
                saida.write(bloco)

    @classmethod
    def ler_tipi_xlsx(cls, caminho: Path | str) -> List[Dict[str, Any]]:
        """Lê a TIPI mesmo que a Receita altere a linha inicial do cabeçalho.

        O método procura semanticamente as colunas NCM/Código, EX, descrição e
        alíquota. Códigos de capítulo/posição são ignorados; somente NCMs de oito
        dígitos entram na base.
        """
        workbook = load_workbook(caminho, read_only=True, data_only=True)
        registros: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for planilha in workbook.worksheets:
            linhas = planilha.iter_rows(values_only=True)
            cabecalho: Optional[List[str]] = None
            indices: Dict[str, Optional[int]] = {}

            for linha in linhas:
                valores = list(linha)
                normalizados = [cls._normalizar_texto(valor) for valor in valores]
                if cabecalho is None:
                    possiveis = cls._mapear_cabecalho(normalizados)
                    if possiveis.get("ncm") is not None and possiveis.get("aliquota") is not None:
                        cabecalho = normalizados
                        indices = possiveis
                    continue

                indice_ncm = indices.get("ncm")
                if indice_ncm is None or indice_ncm >= len(valores):
                    continue
                ncm = cls._digitos(valores[indice_ncm])
                if len(ncm) != 8:
                    continue

                ex_tipi = cls._limpar_ex(cls._valor_indice(valores, indices.get("ex")))
                descricao = str(cls._valor_indice(valores, indices.get("descricao")) or "").strip()
                bruto = cls._valor_indice(valores, indices.get("aliquota"))
                aliquota, aliquota_texto = cls._converter_aliquota(bruto)
                if not aliquota_texto and aliquota is None:
                    continue

                registros[(ncm, ex_tipi)] = {
                    "ncm": ncm,
                    "ex_tipi": ex_tipi,
                    "descricao": descricao,
                    "aliquota": aliquota,
                    "aliquota_texto": aliquota_texto,
                }

        workbook.close()
        return list(registros.values())

    @classmethod
    def _mapear_cabecalho(cls, celulas: Iterable[str]) -> Dict[str, Optional[int]]:
        resultado: Dict[str, Optional[int]] = {"ncm": None, "ex": None, "descricao": None, "aliquota": None}
        for indice, texto in enumerate(celulas):
            if not texto:
                continue
            if resultado["ncm"] is None and (texto == "NCM" or "CODIGO" in texto or "NCM/SH" in texto):
                resultado["ncm"] = indice
            elif resultado["ex"] is None and (texto == "EX" or "EX TIPI" in texto):
                resultado["ex"] = indice
            elif resultado["descricao"] is None and ("DESCRICAO" in texto or "PRODUTO" in texto):
                resultado["descricao"] = indice
            elif resultado["aliquota"] is None and ("ALIQUOTA" in texto or texto in {"IPI", "ALIQ"}):
                resultado["aliquota"] = indice
        return resultado

    @staticmethod
    def _valor_indice(valores: List[Any], indice: Optional[int]) -> Any:
        if indice is None or indice >= len(valores):
            return None
        return valores[indice]

    @staticmethod
    def _converter_aliquota(valor: Any) -> Tuple[Optional[float], str]:
        if valor is None:
            return None, ""
        if isinstance(valor, (int, float)):
            numero = float(valor)
            return numero, (f"{numero:g}")
        texto = str(valor).strip().upper().replace("%", "")
        if not texto:
            return None, ""
        if texto in {"NT", "N/T", "NAO TRIBUTADO", "NÃO TRIBUTADO"}:
            return None, "NT"
        texto_numero = texto.replace(".", "").replace(",", ".")
        try:
            numero = float(texto_numero)
            return numero, str(valor).strip().replace("%", "")
        except ValueError:
            return None, str(valor).strip()

    @staticmethod
    def _limpar_ex(valor: Any) -> str:
        texto = str(valor or "").strip()
        if not texto or texto.lower() == "none":
            return ""
        digitos = "".join(c for c in texto if c.isdigit())
        return digitos.zfill(2) if digitos and len(digitos) <= 2 else texto

    @classmethod
    def _normalizar_texto(cls, valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            caractere for caractere in unicodedata.normalize("NFD", texto)
            if unicodedata.category(caractere) != "Mn"
        )
        return re.sub(r"\s+", " ", texto)

    @classmethod
    def _extrair_itens(cls, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            for chave in ("Nomenclaturas", "nomenclaturas", "items", "data", "listaNcm"):
                valor = payload.get(chave)
                if isinstance(valor, list):
                    return [x for x in valor if isinstance(x, dict)]
            for valor in payload.values():
                if isinstance(valor, (dict, list)):
                    encontrados = cls._extrair_itens(valor)
                    if encontrados:
                        return encontrados
        return []

    @staticmethod
    def _digitos(valor: Any) -> str:
        digitos = "".join(c for c in str(valor or "") if c.isdigit())
        return digitos.zfill(8) if len(digitos) == 7 else digitos
