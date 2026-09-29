"""Diagnóstico da cobertura tributária instalada no FiscalPro.

Hotfix 17.8.72 — cobertura estadual de Rondônia com alíquota modal de 19,5%, tabelas estaduais de autopeças e pneumáticos do Decreto 29.048/2024 e FECOEP separado, sobre a base nacional iniciada na 17.8.38.

O objetivo deste serviço é medir *o que está instalado*, sem transformar ausência
de regra local em conclusão de que o tributo não se aplica. A classificação por
UF separa cobertura estadual detalhada, cobertura parcial e apenas regras gerais
interestaduais.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.banco.conexao import Banco
from src.services.icms_uf_service import UFS_BRASIL, UFS_COBERTURA
from src.services.icms_st_uf_service import ICMSSTUFService


class CoberturaTributariaService:
    UFS = tuple(sorted(UFS_BRASIL))

    @staticmethod
    def _contagem(conn, tabela: str, distinto: str | None = None) -> int:
        alvo = f"DISTINCT {distinto}" if distinto else "*"
        return int(conn.execute(f"SELECT COUNT({alvo}) FROM {tabela}").fetchone()[0])

    @classmethod
    def resumo_bases(cls) -> Dict[str, Any]:
        conn = Banco.conectar()
        try:
            ncm = cls._contagem(conn, "ncm_oficial")
            tipi = cls._contagem(conn, "tipi_oficial")
            st_mg = cls._contagem(conn, "st_mg_oficial")
            st_mg_ncm = cls._contagem(conn, "st_mg_oficial", "ncm_digitos")
            segmentos = [
                str(r[0]) for r in conn.execute(
                    "SELECT DISTINCT segmento FROM st_mg_oficial ORDER BY segmento"
                ).fetchall()
            ]
            atualizado = conn.execute(
                "SELECT MAX(atualizado_em) FROM st_mg_oficial"
            ).fetchone()[0] or ""
            versao = conn.execute(
                "SELECT versao, referencia, data_publicacao FROM base_nacional_versoes ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()

        return {
            "ncm_oficial": ncm,
            "tipi_oficial": tipi,
            "piscofins": "Motor federal nacional ativo",
            "st_mg_registros": st_mg,
            "st_mg_ncm": st_mg_ncm,
            "st_mg_segmentos": segmentos,
            "st_mg_atualizado_em": atualizado,
            "base_nacional_versao": str(versao[0]) if versao else "",
            "base_nacional_referencia": str(versao[1]) if versao else "",
            "base_nacional_data": str(versao[2] or "") if versao else "",
        }

    @classmethod
    def _ufs_recentes(cls) -> set[str]:
        conn = Banco.conectar()
        try:
            existe = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ficha_consultas_recentes'"
            ).fetchone()
            if not existe:
                return set()
            rows = conn.execute(
                "SELECT uf_origem, uf_destino FROM ficha_consultas_recentes ORDER BY consultado_em DESC LIMIT 50"
            ).fetchall()
        finally:
            conn.close()
        resultado: set[str] = set()
        for origem, destino in rows:
            for uf in (origem, destino):
                uf = str(uf or "").strip().upper()
                if uf in UFS_BRASIL:
                    resultado.add(uf)
        return resultado

    @classmethod
    def mapa_ufs(cls) -> List[Dict[str, Any]]:
        resumo = cls.resumo_bases()
        recentes = cls._ufs_recentes()
        detalhadas_icms = set(UFS_COBERTURA)
        detalhadas_st = set(ICMSSTUFService.UFS_COBERTAS)

        linhas: List[Dict[str, Any]] = []
        for uf in cls.UFS:
            uso_recente = uf in recentes
            if uf == "MG":
                nivel = 3
                status = "COBERTURA AMPLIADA"
                icms = "Motor estadual MG + regra interestadual"
                st = (
                    f"{len(resumo['st_mg_segmentos'])} segmentos • "
                    f"{resumo['st_mg_registros']} registros"
                )
                fcp = "Ainda não automatizado nesta camada"
                observacao = (
                    "É a cobertura estadual mais ampla instalada. A tabela ST/MG é parcial por segmentos; "
                    "NCM não localizado não significa ausência de ST."
                )
            elif uf == "SP":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 18% + regra interestadual"
                st = "Autopeças + pneumáticos até 30/09/2026"
                fcp = "FECOEP objetivo: 2203/cap. 24; demais NCMs 0%"
                observacao = (
                    "SP 17.8.40: autopeças do Anexo XIV e pneumáticos do Anexo VII estruturados com IVA-ST, "
                    "ajuste interestadual, vigência e exceções objetivas. A Portaria SRE 34/2026 revoga esses "
                    "segmentos da ST paulista em 01/10/2026; baterias de arranque permanecem como regra específica "
                    "para revisão até a revogação."
                )
            elif uf == "PA":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 19% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados"
                fcp = "Ainda não automatizado — revisar"
                observacao = (
                    "PA 17.8.39: alíquota modal de 19%; ST estruturada para autopeças do âmbito instalado "
                    "e pneumáticos do Anexo XIII. Demais segmentos, benefícios, exceções e FCP/fundo exigem revisão."
                )
            elif uf == "BA":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 20,5% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados (Anexo 1/2026)"
                fcp = "FECOP 0% confirmado p/ autopeças/pneus; 2% em hipóteses reconhecidas"
                observacao = (
                    "BA 17.8.41: alíquota modal de 20,5%; autopeças do item 1.1 e pneumáticos do item 10.0 "
                    "do Anexo 1/2026 estruturados com MVA original/ajustada. FECOP é confirmado como não aplicável "
                    "aos segmentos automotivos estruturados e permanece conservador nos demais NCMs."
                )
            elif uf == "ES":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 17% + regra interestadual"
                st = "Pneumáticos detalhados; autopeças em antecipação parcial/revisão"
                fcp = "2% bebidas alcoólicas/fumo; automotivo 0%"
                observacao = (
                    "ES 17.8.42: alíquota modal de 17%; pneumáticos estruturados pela Portaria 16-R atualizada. "
                    "Para autopeças, o Protocolo ICMS 41/08 foi denunciado pelo ES a partir de 03/02/2022 e a "
                    "Portaria 13-R/2022 passou a disciplinar antecipação parcial, por isso o FiscalPro não confirma "
                    "ST genérica em 2026 sem revisar credenciamento e eventual regra específica."
                )
            elif uf == "GO":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 19% + regra interestadual"
                st = "Pneumáticos detalhados; autopeças fora da ST desde 01/03/2018"
                fcp = "PROTEGE adicional até 2% — revisar lista de supérfluos"
                observacao = (
                    "GO 17.8.44: alíquota modal de 19%; pneumáticos do item V do Apêndice II do Anexo VIII "
                    "estruturados com MVA interna e ajustadas do Decreto 10.799/2025. Autopeças foram excluídas "
                    "da ST pelas operações posteriores em 01/03/2018 pelos Decretos 9.108/2017 e 9.147/2018. "
                    "PROTEGE, benefícios e demais segmentos permanecem conservadores para revisão."
                )
            elif uf == "PR":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 19,5% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados (Anexo IX / Res. SEFA 571/2019)"
                fcp = "FECOP 0% autopeças/pneus; 2% apenas na lista objetiva"
                observacao = (
                    "PR 17.8.45: alíquota modal de 19,5%; autopeças do art. 28 e pneumáticos do art. 116 "
                    "do Anexo IX estruturados com MVA original da Resolução SEFA 571/2019 e ajuste nas operações "
                    "interestaduais. FECOP é confirmado como não aplicável aos segmentos automotivos estruturados; "
                    "demais hipóteses permanecem conservadoras."
                )
            elif uf == "SC":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "12% internas p/ contribuinte; modal 17% + regra interestadual"
                st = "Pneumáticos detalhados; autopeças fora da ST desde 01/04/2020"
                fcp = "ACEP antigo revogado; Fundo Social sem adicional geral por operação"
                observacao = (
                    "SC 17.8.46: art. 26 do RICMS/SC estruturado para distinguir 12% nas operações internas "
                    "destinadas a contribuinte das hipóteses modais/exceções; pneumáticos seguem os arts. 53 a 55 "
                    "do Anexo 3 com MVA específica e ajuste. Autopeças saíram da ST em 01/04/2020 pelo Decreto "
                    "479/2020. O antigo FECEP/ACEP foi incorporado ao Fundo Social e sua lei instituidora foi revogada."
                )
            elif uf == "RS":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 17% + regra interestadual"
                st = "Pneumáticos detalhados; autopeças fora da ST desde 01/11/2024"
                fcp = "AMPARA 0% automotivo; 2% apenas no rol legal"
                observacao = (
                    "RS 17.8.47: alíquota modal de 17%; pneumáticos do item V do Apêndice II estruturados "
                    "com MVA interna e interestadual. Autopeças saíram da ST em 01/11/2024 pelo Decreto 57.848/2024. "
                    "AMPARA/RS é separado e confirmado como não aplicável aos segmentos automotivos estruturados."
                )
            elif uf == "MS":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 17% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados (Subanexo I/Anexo III)"
                fcp = "FECOMP 0% automotivo; 2% apenas no rol do art. 41-A"
                observacao = (
                    "MS 17.8.49: alíquota modal de 17%; autopeças da Tabela II com MVA padrão de 50% "
                    "e pneumáticos do segmento 16 estruturados com margens interna/interestaduais do RICMS/MS. "
                    "Regime especial pode autorizar MVA diferenciada; FECOMP é separado e não alcança os "
                    "segmentos automotivos estruturados."
                )
            elif uf == "MT":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 17% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados (Anexo X / Port. 195/2019)"
                fcp = "FCP 0% automotivo; 2% apenas nas hipóteses legais"
                observacao = (
                    "MT 17.8.50: alíquota modal de 17%; autopeças e pneumáticos do Anexo X estruturados pela "
                    "Portaria 195/2019. A MVA depende da situação do destinatário: tabela-base 50,39% (autopeças) "
                    "e 62,27% (pneumáticos), enquanto o art. 2º-B prevê 65,29% e 78,79% para destinatários não "
                    "optantes/não contemplados pelo benefício indicado. O art. 3º manda aplicar a MVA independentemente "
                    "da UF do remetente, sem fórmula de MVA ajustada interestadual."
                )
            elif uf == "CE":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 20% + regra interestadual"
                st = "Autopeças por carga líquida condicional; pneumáticos com bifurcação de regime"
                fcp = "FECOP 0% automotivo; 2% apenas no rol do art. 47"
                observacao = (
                    "CE 17.8.53: alíquota modal de 20%. Para autopeças, o Decreto 30.519/2011 usa carga líquida "
                    "condicionada ao CNAE principal do destinatário; na rota MG→CE e mercadoria de carga interna 20%, "
                    "a referência do Anexo III é 21,00%. O Protocolo 41/08 não inclui CE como destino. Para pneus de "
                    "motocicleta, o Convênio 102/17 confirma a ST interestadual, mas a Nota Explicativa 03/2022 exige "
                    "separar hipótese de redução de base/regime específico da carga líquida. FECOP não alcança os "
                    "segmentos automotivos estruturados."
                )
            elif uf == "AL":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 20,5% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados; Protocolo 41/08/Convênio 102/17"
                fcp = "FECOEP 1% no escopo automotivo; 2% apenas no rol específico"
                observacao = (
                    "AL 17.8.55: alíquota modal de 20,5% vigente desde 01/04/2026. Autopeças do Anexo I do "
                    "Decreto 90.309/2023 usam MVA original de 36,56% nas hipóteses qualificadas de fidelidade/"
                    "exclusividade e 71,78% nos demais casos; MG e AL integram o Protocolo 41/08, portanto a rota "
                    "MG→AL atribui em regra a retenção ao remetente, ressalvadas as exceções do acordo. Pneumáticos "
                    "seguem o Anexo XI e o Convênio 102/17. O FECOEP geral de 1% é separado do ICMS e também alcança "
                    "o cálculo da ST para os segmentos automotivos estruturados. Regimes especiais/credenciamentos do "
                    "destinatário devem ser conferidos antes da aplicação."
                )
            elif uf == "PB":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 20% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados (Anexo 05 / Prot. 41/08 / Conv. 102/17)"
                fcp = "FUNCEP 0% autopeças/pneus; 2% apenas no rol legal"
                observacao = (
                    "PB 17.8.56: alíquota modal de 20% vigente desde 01/01/2024. O Anexo 05 atualizado estrutura "
                    "autopeças com MVA original de 36,56% na hipótese qualificada de fidelidade e 71,78% nos "
                    "demais casos; na entrada interestadual a 7%, as margens oficiais são 58,75% e 99,69%. "
                    "Para MG→PB, o Protocolo 41/08 vigente atribui em regra a retenção ao remetente, ressalvadas "
                    "as exceções do acordo. Pneus de motocicleta (CEST 16.003.00) usam MVA 60% e 86% a 7%, "
                    "com responsabilidade pelo Convênio 102/17. FUNCEP/PB é 0% para autopeças e pneumáticos, "
                    "pois o adicional de 2% alcança apenas o rol específico da Lei 7.611/2004."
                )
            elif uf == "RN":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 20% + regra interestadual"
                st = "Autopeças em antecipação (Anexo 005) + pneumáticos em ST (Anexo 007)"
                fcp = "FECOP 0% autopeças/pneus; 2% apenas no rol do art. 27-A"
                observacao = (
                    "RN 17.8.58: alíquota modal de 20% vigente na legislação atual. Autopeças, inclusive NCM 8714.1, "
                    "estão no Anexo 005 como produtos sujeitos à antecipação com percentual de agregação de 40%; o RN "
                    "não figura entre os destinos atuais do Protocolo 41/08, portanto a rota MG→RN não é tratada como "
                    "ST automática do remetente. Pneus de motocicleta (CEST 16.003.00) permanecem em ST pelo Anexo 007 "
                    "e Convênio 102/17, com MVA original 60% e MVA 86% para alíquota interestadual de 7%. FECOP/RN não "
                    "alcança os segmentos automotivos estruturados."
                )
            elif uf == "MA":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 23% + regra interestadual"
                st = "Autopeças (Prot. 41/08) + pneumáticos (Conv. 102/17)"
                fcp = "FUMACOP 0% autopeças/pneus; revisar rol legal para outros produtos"
                observacao = (
                    "MA 17.8.63: alíquota interna modal de 23% vigente desde 23/02/2025. Autopeças de uso "
                    "especificamente automotivo seguem o Protocolo ICMS 41/08; para MG→MA, a responsabilidade "
                    "é atribuída em regra ao remetente, ressalvadas as exceções do acordo. A MVA-base usada é "
                    "36,56% na hipótese qualificada de fidelidade e 71,78% nos demais casos; com alíquota "
                    "interestadual de 7% e interna de 23%, as MVAs ajustadas são 64,94% e 107,47%. Pneus de "
                    "motocicleta CEST 16.003.00 usam MVA original 60% e ajustada 93,25% a 7%, pelo Convênio "
                    "102/17. FUMACOP fica em 0% para autopeças/pneumáticos estruturados; outros NCMs exigem revisão."
                )
            elif uf == "PI":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 22,5% + regra interestadual"
                st = "Autopeças (Anexo X, arts. 93-94) + pneumáticos (arts. 75-76 / Conv. 102/17)"
                fcp = "FECOP 0% autopeças/pneus; revisar rol legal para outros produtos"
                observacao = (
                    "PI 17.8.67: alíquota interna modal de 22,5% com efeitos desde 01/04/2025. Autopeças do "
                    "Anexo X usam MVA original de 26,50% nas hipóteses qualificadas de fidelidade e 40,00% nos "
                    "demais casos; na operação MG→PI a 7%, as MVAs ajustadas são 51,80% e 68,00%. O art. 93 "
                    "atribui, em regra, responsabilidade ao remetente nas operações entre PI e UFs signatárias "
                    "dos Protocolos 41/08/97/10, ressalvadas exceções. Pneus de motocicleta CEST 16.003.00 usam "
                    "MVA original 60% e ajustada 92% a 7%, pelo Convênio 102/17. Regime especial de atacadista "
                    "de peças para motocicletas, se houver credenciamento, deve ser revisado antes de aplicar a regra normal."
                )
            elif uf == "TO":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 20% + regra interestadual"
                st = "Autopeças (Anexo XXI / Prot. 97/10) + pneumáticos (Conv. 102/17)"
                fcp = "FECOEP 0% autopeças/pneus; +2 p.p. apenas nas hipóteses do art. 27, I"
                observacao = (
                    "TO 17.8.68: alíquota interna modal de 20%. Autopeças usam MVA original de 36,56% "
                    "na fidelidade/exclusividade qualificada e 71,78% nos demais casos; em MG→TO a 7%, "
                    "as MVAs ajustadas são 58,75% e 99,69%. Como MG não integra o Protocolo 97/10, o "
                    "FiscalPro não atribui retenção automática ao remetente mineiro, mantendo responsabilidade "
                    "local/antecipação em revisão. Pneus de motocicleta CEST 16.003.00 usam MVA 60% → 86% "
                    "pelo Convênio 102/17. Regime especial da Lei TO nº 1.201/2000 não é presumido."
                )
            elif uf == "AC":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 19% + regra interestadual"
                st = "Autopeças (IN 01/2023 / Prot. 41/08) + pneumáticos (Conv. 102/17)"
                fcp = "FCP 0% no escopo automotivo estruturado"
                observacao = (
                    "AC 17.8.72: alíquota interna modal de 19%. Autopeças usam MVA original de 36,56% "
                    "na fidelidade qualificada e 71,78% nos demais casos; em MG→AC a 7%, a IN DIAT 01/2023 "
                    "traz MVAs ajustadas de 56,79% e 97,23%. MG e AC integram o Protocolo 41/08, portanto "
                    "a retenção pelo remetente é reconhecida em regra, preservadas as exceções. Pneus de "
                    "motocicleta CEST 16.003.00 usam MVA 60% → 83,70% pelo Convênio 102/17."
                )
            elif uf == "AM":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 20% + regra interestadual"
                st = "Autopeças (Lei 6.108/2022 / Prot. 41/08) + pneumáticos (Conv. 102/17)"
                fcp = "Adicional 0% no escopo automotivo estruturado"
                observacao = (
                    "AM 17.8.72: alíquota interna modal de 20%. A Lei 6.108/2022 relaciona autopeças "
                    "e pneumáticos sujeitos à ST. Autopeças usam MVA original de 36,56% na fidelidade "
                    "qualificada e 71,78% nos demais casos; em MG→AM a 7%, as MVAs ajustadas são "
                    "58,75% e 99,69%. MG e AM integram o Protocolo 41/08, preservadas suas exceções. "
                    "Pneu de motocicleta CEST 16.003.00 usa MVA 60% → 86,00% pelo Convênio 102/17."
                )
            elif uf == "AP":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 18% + regra interestadual"
                st = "Autopeças (RICMS/AP / Prot. 41/08) + pneumáticos (Conv. 102/17)"
                fcp = "FCP 0% no escopo automotivo estruturado"
                observacao = (
                    "AP 17.8.72: alíquota interna modal de 18%. Autopeças usam MVA original de 36,56% "
                    "na fidelidade qualificada e 71,78% nos demais casos; em MG→AP a 7%, as MVAs "
                    "ajustadas são 54,88% e 94,82%. MG e AP integram o Protocolo 41/08, preservadas "
                    "as exceções legais. Pneu de motocicleta CEST 16.003.00 usa MVA 60% → 81,46% "
                    "pelo Convênio 102/17."
                )
            elif uf == "RO":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 19,5% + regra interestadual"
                st = "Autopeças e pneumáticos — Decreto 29.048/2024"
                fcp = "FECOEP 0% autopeças; 2% pneumáticos"
                observacao = (
                    "RO 17.8.72: autopeça CEST 01.076.00 usa MVA original 30% e ajustada 50,19% "
                    "na rota MG→RO a 7%. Como RO não integra os Protocolos 41/08 ou 97/10 vigentes, "
                    "a retenção pelo remetente mineiro não é presumida. Pneu de motocicleta CEST "
                    "16.003.00 usa MVA original 50% e ajustada 73,29%, com FECOEP/RO de 2% separado."
                )
            elif uf == "SE":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 19% + regra interestadual"
                st = "Autopeças (Prot. 97/10/Tabela VI) + pneumáticos (Conv. 102/17)"
                fcp = "FECOEP 1% automotivo; 2% apenas no rol especial do art. 40-C"
                observacao = (
                    "SE 17.8.62: alíquota interna modal de 19%. Para o escopo automotivo, o FECOEP geral é 1% "
                    "e o RICMS/SE determina que a MVA ajustada considere ICMS + FECOEP, totalizando 20% como "
                    "referência do ajuste. Autopeças usam 36,56% na hipótese qualificada de fidelidade e 71,78% "
                    "nos demais casos; a 7%, 58,75% e 99,69%. Como MG não é signatário do Protocolo 97/10, "
                    "MG→SE não força retenção ST pelo remetente e sinaliza antecipação do art. 784, II, d. "
                    "Pneus de motocicleta CEST 16.003.00 usam MVA 60% e 86% a 7%, pelo Convênio 102/17."
                )
            elif uf == "PE":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 20,5% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados; responsabilidade interestadual por acordo"
                fcp = "FECEP 0% autopeças/pneus; 2% apenas no rol legal"
                observacao = (
                    "PE 17.8.54: alíquota modal de 20,5%. Autopeças dos arts. 99 a 101 do Anexo 37 usam MVA original "
                    "de 36,56% nas hipóteses qualificadas de fidelidade/exclusividade e 71,78% nos demais casos, com "
                    "tabela oficial interestadual. Quando a origem não é signatária do Protocolo 97/10, como MG, o "
                    "FiscalPro mantém a MVA para antecipação, mas não atribui retenção automática ao remetente. "
                    "Pneumáticos seguem os arts. 49 a 54 e o Convênio 102/17, com tabela oficial própria. FECEP é "
                    "separado e não alcança autopeças/pneumáticos nesta cobertura."
                )
            elif uf == "DF":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota modal 20% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados (Anexo IV/Item 28 + Port. 189/1997)"
                fcp = "FCP 0% automotivo; 2% apenas no rol da Lei 4.220/2008"
                observacao = (
                    "DF 17.8.52: alíquota modal de 20%; autopeças do item 28 do Caderno I do Anexo IV "
                    "estruturadas com MVA-ST original de 71,78% nos demais casos e 36,56% nas hipóteses qualificadas "
                    "de fidelidade/exclusividade, com MVA ajustada nas operações interestaduais. Pneumáticos usam as "
                    "MVAs originais de 42%, 32%, 60% e 45% da Portaria 189/1997, alterada pela Portaria 173/2011, "
                    "também com ajuste interestadual. FCP é separado e não alcança os segmentos automotivos estruturados."
                )
            elif uf == "RJ":
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota geral 20% + regra interestadual"
                st = "Autopeças + pneumáticos detalhados (Anexo I/Livro II)"
                fcp = "FECP geral 2% estruturado; revisar exceções legais"
                observacao = (
                    "RJ 17.8.43: alíquota geral de 20%; autopeças do item 7 e pneumáticos do item 9 do "
                    "Anexo I do Livro II estruturados com MVA original/ajustada. FECP geral de 2% é tratado "
                    "separadamente e exceções legais permanecem visíveis para revisão."
                )
            elif uf in detalhadas_icms:
                nivel = 2
                status = "COBERTURA ESTADUAL PARCIAL"
                icms = "Alíquota interna/modal + exceções objetivas"
                st = "Autopeças detalhadas" if uf in detalhadas_st else "Sem regra ST estadual detalhada"
                fcp = "Regras locais objetivas instaladas"
                observacao = (
                    "Há perfil estadual, FCP e/ou ST para hipóteses específicas, mas não existe cobertura "
                    "completa de todos os NCMs, benefícios e segmentos."
                )
            else:
                nivel = 1
                status = "REGRA INTERESTADUAL GERAL"
                icms = "7% / 12% / 4% conforme contexto"
                st = "Sem regra estadual detalhada instalada"
                fcp = "Sem regra local detalhada instalada"
                observacao = (
                    "O FiscalPro conhece a regra interestadual geral, mas exige pesquisa da legislação local "
                    "para alíquota interna, FCP, ST, benefícios e exceções."
                )

            linhas.append({
                "uf": uf,
                "nivel": nivel,
                "status": status,
                "icms": icms,
                "st": st,
                "fcp": fcp,
                "uso_recente": uso_recente,
                "prioridade": "USO RECENTE" if uso_recente and nivel < 3 else "",
                "observacao": observacao,
            })
        return linhas

    @classmethod
    def diagnostico(cls) -> Dict[str, Any]:
        linhas = cls.mapa_ufs()
        resumo = cls.resumo_bases()
        totais = {
            "ampliada": sum(1 for x in linhas if x["nivel"] == 3),
            "parcial": sum(1 for x in linhas if x["nivel"] == 2),
            "geral": sum(1 for x in linhas if x["nivel"] == 1),
        }
        prioridades = [x["uf"] for x in linhas if x["prioridade"] and x["nivel"] == 1]
        return {
            "resumo": resumo,
            "ufs": linhas,
            "totais": totais,
            "prioridades": prioridades,
            "aviso": (
                "Cobertura mede regras instaladas no FiscalPro. Ausência de regra local nunca deve ser "
                "interpretada automaticamente como ausência de ICMS-ST, FCP, benefício ou exceção."
            ),
        }
