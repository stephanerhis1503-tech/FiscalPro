"""Regras estaduais rastreáveis de ICMS-ST para autopeças.

Sprint 17.1.0

Escopo deliberadamente conservador:
- classifica a mercadoria pelo CEST/descrição já validada no motor de MG;
- aplica regras estaduais documentadas para SP, ES, BA, RJ, PA, GO, PR, SC, RS, MS, MT, DF, CE, PE, AL, PB, RN, SE, MA, PI e TO; BA, PA, SP, RJ, MS, MT, DF e PE cobrem autopeças e pneumáticos; CE usa carga líquida condicionada ao CNAE e tratamento específico para pneumáticos, ES trata pneumáticos atuais e a transição das autopeças para antecipação parcial, SC mantém pneumáticos e exclui autopeças, e RS mantém pneumáticos mas exclui autopeças desde 01/11/2024;
- separa MVA original, MVA ajustada, vigência e responsabilidade;
- não reutiliza a MVA mineira como regra de outro estado;
- respeita a exclusão das autopeças da ST paulista a partir de 01/10/2026.

A confirmação de ST neste serviço significa que a mercadoria e o período foram
alcançados pela regra estadual instalada. A responsabilidade pelo recolhimento
pode continuar condicionada ao acordo interestadual e ao papel do contribuinte.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from src.services.icms_st_mg_service import ICMSSTMGService


URL_CONFAZ_142 = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"
URL_SP_CAT_68 = "https://legislacao.fazenda.sp.gov.br/Paginas/Portaria-CAT-68-de-2019.aspx"
URL_SP_SRE_16 = "https://legislacao.fazenda.sp.gov.br/Paginas/Portaria-SRE-16-de-2023.aspx"
URL_SP_SRE_15 = "https://legislacao.fazenda.sp.gov.br/Paginas/Portaria-SRE-15-de-2024.aspx"
URL_SP_SRE_34 = "https://legislacao.fazenda.sp.gov.br/Paginas/Portaria-SRE-34-de-2026.aspx"
URL_ES_PORTARIA_16 = (
    "https://www2.sefaz.es.gov.br/LegislacaoOnline/lpext.dll/InfobaseLegislacaoOnline/"
    "portarias/2019/port16-r%20-%20atualizada.htm?2.0=&f=templates&fn=document-frame.htm"
)
URL_ES_PORTARIA_13_2022 = (
    "https://www2.sefaz.es.gov.br/LegislacaoOnline/lpext.dll/InfobaseLegislacaoOnline/"
    "portarias/2022/port13-r%20-%20atualizada.htm?2.0=&f=templates&fn=document-frame.htm"
)
URL_BA_ANEXO_1_2026 = (
    "https://mbusca.sefaz.ba.gov.br/DITRI/normas_complementares/decretos/"
    "decreto_2012_13780_ricms_anexo_1_vigente_2026.pdf"
)
URL_RJ_ANEXO_I = (
    "https://portal.fazenda.rj.gov.br/icms/wp-content/uploads/sites/42/2023/10/"
    "anexo_I_livroII_2.pdf"
)
URL_PA_ANEXO_XIII_2022 = "https://www.ioepa.com.br/pages/2022/2022.03.29.DOE.pdf"
URL_PA_ANEXO_XIII_2024 = "https://www.ioepa.com.br/pages/2024/2024.01.11.DOE.pdf"
URL_CONFAZ_PROTOCOLO_41 = "https://www.confaz.fazenda.gov.br/legislacao/protocolos/2008/pt041_08"
URL_CONFAZ_CONVENIO_102 = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2017/CV102_17"
URL_CE_DECRETO_30519 = "https://sefazlegis.sefaz.ce.gov.br/api/openFile?id=d5e33d14-7888-4f67-8687-a18f4f657953"
URL_CE_NOTA_03_2022 = "https://portalservicos.sefaz.ce.gov.br/nota-explicativa-n-03-2022-icms-st-pneus-e-camaras-de-ar%2B66ff217326132447f21a67cc"
URL_CE_RICMS = "https://sefazlegis.sefaz.ce.gov.br/api/openFile?id=6e01bfd1-bbd2-49d3-bc27-0d44b5147803"
URL_PE_RICMS = "https://www.sefaz.pe.gov.br/Legislacao/Tributaria/Documents/legislacao/44650/texto/Dec44650_2017.htm"
URL_PE_AUTOPECAS_MVA = "https://www.sefaz.pe.gov.br/Legislacao/Tributaria/Documents/Legislacao/Tabelas/Tabela%20MVA%20Autope%C3%A7as.pdf"
URL_PE_PNEUS_MVA = "https://www.sefaz.pe.gov.br/Legislacao/Tributaria/Documents/Legislacao/Tabelas/Tabela%20MVA%20Pneus%20e%20C%C3%A2maras%20de%20Ar.pdf"
URL_CONFAZ_PROTOCOLO_97 = "https://www.confaz.fazenda.gov.br/legislacao/protocolos/2010/pt097_10"
URL_AL_DECRETO_90309 = "https://www.imprensaoficial.al.gov.br/storage/files/diary/2023/03/doeal-2023-03-28-completo-gzj6bahhh7ppehox9uz-3e0l0ql1ntyg9f803jf1srmbjjrryzswc.pdf"
URL_AL_REGIME_ATACADISTA_99605 = "https://diario.imprensaoficial.al.gov.br/apinova/api/editions/viewPdf/50010"
URL_PB_ANEXO_05 = "https://www.sefaz.pb.gov.br/attachments/article/1519/ANEXO%20%2005%20REL.%20MERC.EF.%20SUBST.%20TRIB.%20E%20RESP.%20TAX.%20VAL.%20%20AGREG.%20NR%20A%20PARTIR%20DE%2001.01.2024%20%20-%20ATUALIZADO%20EM%2009.07.2025.pdf"
URL_RN_RICMS = "https://www.diariooficial.rn.gov.br/dei/dorn3/documentos/00000001/20220819/783131.htm"
URL_RN_ANEXO_005 = "https://www.diariooficial.rn.gov.br/dei/dorn3/documentos/00000001/20220819/783140.htm"
URL_RN_ANEXO_007 = "https://www.diariooficial.rn.gov.br/dei/dorn3/documentos/00000001/20220819/783145.htm"
URL_SE_RICMS = "https://api.legislacao.se.gov.br/uploads/atos/31521/DN-21400-2002-atualizado-DN-1467-2026.pdf"
URL_MA_LEGISLACAO = "https://www.ma.gov.br/servicos/consultar-legislacao-da-sefaz"
URL_PI_RICMS = "https://www.diario.pi.gov.br/doe/files/diarios/anexo/5714d565-bd46-4f50-950d-7fa74dbdc549/DIARIO-OFICIAL-DO-ESTADO-DO-PIAUI-PUBLICACAO-N-47.pdf"
URL_PI_DECRETO_24244 = "https://www.diario.pi.gov.br/doe/files/diarios/anexo/e9755fe8-4b41-44be-a6f4-520a386f3b2f/DOEPI_240_2025.pdf"
URL_TO_LEI_1287 = "https://www.al.to.leg.br/arquivos/lei_1287-2001_68306.PDF"
URL_TO_LEI_1201 = "https://www.al.to.leg.br/arquivos/lei_1201-2000_51051.PDF"
URL_AC_IN_DIAT_01_2023 = "https://sefaz.ac.gov.br/2021/?p=16417"
URL_AC_PROTOCOLO_41 = "https://www.confaz.fazenda.gov.br/legislacao/protocolos/2008/pt041_08"
URL_AM_LEI_6108 = "https://sistemas.sefaz.am.gov.br/get/Normas.do?metodo=viewDoc&uuidDoc=84be7172-451e-4ca0-802e-1a0303e5f0b2"
URL_AP_RICMS = "https://www.sefaz.ap.gov.br/"
URL_AP_PROTOCOLO_41 = "https://www.confaz.fazenda.gov.br/legislacao/protocolos/2008/pt041_08"
URL_RO_RICMS = "https://legislacao.sefin.ro.gov.br/"
URL_RO_DECRETO_29048 = "https://legislacao.sefin.ro.gov.br/"
URL_GO_DECRETO_10799 = "https://legisla.casacivil.go.gov.br/pesquisa_legislacao/111443/decreto-numerado-10799"
URL_GO_EXCLUSAO_AUTOPECAS = "https://goias.gov.br/economia/wp-content/uploads/sites/45/2018/03/manual-de-exclusAo-de-mercadorias-da-st-versao-2-3a7.pdf"
URL_PR_RESOLUCAO_571 = "https://www.fazenda.pr.gov.br/sites/default/arquivos_restritos/files/documento/2020-06/101201900571.pdf"
URL_PR_ST_PORTAL = "https://www.fazenda.pr.gov.br/Pagina/ICMS-Substituicao-tributaria"
URL_SC_RICMS = "https://legislacao.sef.sc.gov.br/html/regulamentos/icms/ricms_01_00.htm"
URL_SC_ANEXO_3 = "https://legislacao.sef.sc.gov.br/html/regulamentos/icms/ricms_01_03.htm"
URL_SC_ANEXO_1A = "https://legislacao.sef.sc.gov.br/html/regulamentos/icms/ricms_01_01_a.htm"
URL_SC_DECRETO_479 = "https://legislacao.sef.sc.gov.br/html/decretos/2020/dec_20_0479.htm"
URL_SC_COPAT_37_2026 = (
    "https://legislacao.sef.sc.gov.br/consulta/views/Publico/"
    "DocumentoLegalViewer.ashx?id=5D4C431C-7C43-405C-835C-C4C5E1ECC76D"
)
URL_RS_EXCLUSAO_AUTOPECAS = "https://atendimento.receita.rs.gov.br/qual-foi-a-legislacao-alterada-relativa-a-exclusao-dos-produtos-da-st-a-partir-de-1-de-novembro-de-24"
URL_RS_RICMS = "https://receita.fazenda.rs.gov.br/servicos-ao-cidadao/servicos?servico=1802"
URL_RS_AMPARA = "https://atendimento.receita.rs.gov.br/fundo-de-combate-a-pobreza-ampara-e-a-ec-87-2015"
URL_MS_RICMS = "https://aacpdappls.net.ms.gov.br/appls/legislacao/secoge/govato.nsf/fd8600de8a55c7fc04256b210079ce25/9c9e3a59ea627ab40425715300728e6a"
URL_MS_DECRETO_14383 = "https://aacpdappls.net.ms.gov.br/appls/legislacao/secoge/govato.nsf/2cab8d75940ca72e04256d1a004acf14/bc0465648acae13204257f49003b2060"
URL_MS_SEFAZ_ST = "https://www.sefaz.ms.gov.br/substituicao-tributaria/"
URL_MT_LEI_7098 = "https://app1.sefaz.mt.gov.br/Sistema/legislacao/legislacaotribut.nsf/c83fc8b160f5810b032567550064fd41/cc9c3b9886404baa0325678b0043a842"
URL_MT_PORTARIA_195 = "https://app1.sefaz.mt.gov.br/Sistema/legislacao/legislacaotribut.nsf/07fa81bed2760c6b84256710004d3940/4c7283a0b4318486042584c4004436c1"
URL_MT_ANEXO_X = "https://sefaz.mt.gov.br/forum/wp-content/uploads/wpforo/default_attachments/1699636449-APENDICE-DO-ANEXO-X.pdf"
URL_DF_RICMS = "https://www.sinj.df.gov.br/sinj/Norma/33077/Decreto_18955_22_12_1997.html"
URL_DF_AUTOPECAS_2025 = "https://www.sinj.df.gov.br/sinj/TextoArquivoDiario.aspx?id_file=ee17c9e8-2f5a-30c1-a35a-a6a2a108c962"
URL_DF_AUTOPECAS_MVA = "https://www.sinj.df.gov.br/sinj/Diario/734832a8-8e1d-3fb1-8e85-d6457aed10b9/DODF%20062%2002-04-2018%20INTEGRA.pdf"
URL_DF_PORTARIA_189 = "https://www.sinj.df.gov.br/sinj/DetalhesDeNorma.aspx?id_norma=31526"
URL_DF_PORTARIA_173 = "https://www.sinj.df.gov.br/sinj/Norma/70210/Portaria_173_28_12_2011.pdf"

CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41 = {
    "01.019.00", "01.062.01", "01.112.00", "01.127.00", "01.128.00", "01.999.00",
}
CEST_PNEUMATICOS_ES = {
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 64.24, 7.0: 59.11, 12.0: 50.55}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 52.67, 7.0: 47.90, 12.0: 39.95}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 85.06, 7.0: 79.28, 12.0: 69.64}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
}
CEST_PNEUMATICOS_SP = {
    "16.001.00": 46.68,
    "16.002.00": 35.85,
    "16.003.00": 77.12,
    "16.004.00": 54.45,
    "16.005.00": 99.12,
    "16.007.00": 102.11,
    "16.008.00": 117.13,
    "16.009.00": 140.35,
}
CEST_PNEUMATICOS_BA = {
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 71.47, 7.0: 66.11, 12.0: 57.18}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 59.40, 7.0: 54.42, 12.0: 46.11}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 93.21, 7.0: 87.17, 12.0: 77.11}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 75.09, 7.0: 69.62, 12.0: 60.50}},
    "16.005.00": {"original": 64.67, "ajustada": {4.0: 98.85, 7.0: 92.63, 12.0: 82.28}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 75.09, 7.0: 69.62, 12.0: 60.50}},
    "16.007.01": {"original": 45.00, "ajustada": {4.0: 75.09, 7.0: 69.62, 12.0: 60.50}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 75.09, 7.0: 69.62, 12.0: 60.50}},
    "16.009.00": {"original": 64.67, "ajustada": {4.0: 98.85, 7.0: 92.63, 12.0: 82.28}},
}
CEST_PNEUMATICOS_PA = {
    "16.001.00": 42.0,
    "16.002.00": 32.0,
    "16.003.00": 60.0,
    "16.004.00": 45.0,
    "16.007.00": 45.0,
    "16.008.00": 45.0,
}
CEST_PNEUMATICOS_GO = {
    # Decreto GO nº 10.799/2025, Apêndice II do Anexo VIII, item V.
    # Tabela já atualizada para a alíquota modal de 19%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 68.30, 7.0: 63.04, 12.0: 54.27}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 56.44, 7.0: 51.56, 12.0: 43.41}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 89.63, 7.0: 83.70, 12.0: 73.83}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 71.85, 7.0: 66.48, 12.0: 57.53}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 71.85, 7.0: 66.48, 12.0: 57.53}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 71.85, 7.0: 66.48, 12.0: 57.53}},
}
CEST_PNEUMATICOS_PR = {
    # Resolução SEFA/PR nº 571/2019, art. 21, texto compilado.
    "16.001.00": 40.73,
    "16.002.00": 31.03,
    "16.003.00": 65.58,
    "16.004.00": 55.32,
    "16.005.00": 105.00,
    "16.007.00": 74.58,
    "16.007.01": 74.58,
    "16.008.00": 74.58,
    "16.009.00": 105.00,
}
CEST_PNEUMATICOS_SC = {
    # RICMS/SC, Anexo 3, art. 55, § 1º.
    "16.001.00": 50.55,
    "16.002.00": 39.95,
    "16.003.00": 69.64,
    "16.004.00": 53.73,
    "16.007.00": 53.73,
    "16.008.00": 53.73,
}
CEST_PNEUMATICOS_RS = {
    # RICMS/RS, Apêndice II, Seção III, item V, redação do Decreto nº 56.280/2021.
    # Tabela vigente em 2026: MVA interna e margens interestaduais para 12% e 4%.
    "16.001.00": {"original": 62.83, "ajustada": {12.0: 72.63, 4.0: 88.33}},
    "16.002.00": {"original": 38.20, "ajustada": {12.0: 46.52, 4.0: 59.84}},
    "16.003.00": {"original": 66.31, "ajustada": {12.0: 76.32, 4.0: 92.35}},
    "16.004.00": {"original": 74.82, "ajustada": {12.0: 85.35, 4.0: 102.20}},
    "16.007.00": {"original": 55.26, "ajustada": {12.0: 64.61, 4.0: 79.57}},
    "16.008.00": {"original": 72.36, "ajustada": {12.0: 82.74, 4.0: 99.35}},
}
CEST_PNEUMATICOS_MT = {
    # Portaria SEFAZ/MT nº 195/2019, Anexo Único, tabela de pneumáticos.
    # O art. 3º determina aplicação independentemente da UF do remetente.
    "16.001.00": 62.27,
    "16.002.00": 62.27,
    "16.003.00": 62.27,
    "16.004.00": 62.27,
    "16.005.00": 62.27,
    "16.006.00": 62.27,
    "16.007.00": 62.27,
    "16.007.01": 62.27,
    "16.008.00": 62.27,
    "16.009.00": 62.27,
}

CEST_PNEUMATICOS_DF = {
    # Portaria SEFP/DF nº 189/1997, alterada pela Portaria SEF/DF nº 173/2011.
    # MVA-ST original; em operação interestadual a margem é ajustada pela fórmula legal.
    "16.001.00": 42.00,
    "16.002.00": 32.00,
    "16.003.00": 60.00,
    "16.004.00": 45.00,
    "16.007.00": 45.00,
    "16.008.00": 45.00,
}

CEST_PNEUMATICOS_PE = {
    # Tabela MVA Pneus e Câmaras de Ar — SEFAZ/PE, vigente a partir de 01/01/2024.
    # Alíquota interna de referência: 20,5%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 71.47, 7.0: 66.11, 12.0: 57.18}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 59.40, 7.0: 54.42, 12.0: 46.11}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 93.21, 7.0: 87.17, 12.0: 77.11}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 75.09, 7.0: 69.62, 12.0: 60.50}},
    # CEST 16.005.00 consta na tabela interna de PE, mas é exceção do Convênio 102/17
    # para responsabilidade interestadual automática; por isso a rotina abaixo o revisa.
    "16.005.00": {"original": 105.00, "ajustada": {4.0: 147.55, 7.0: 139.81, 12.0: 126.92}},
}

MVA_AUTOPECAS_PE = {
    # Decreto PE nº 57.000/2024 + tabela oficial vigente desde 01/01/2024.
    "fidelidade": {"original": 36.56, "ajustada": {4.0: 64.90, 7.0: 59.75, 12.0: 51.16}},
    "demais": {"original": 71.78, "ajustada": {4.0: 107.43, 7.0: 100.95, 12.0: 90.15}},
}

CEST_PNEUMATICOS_AL = {
    # Decreto AL nº 90.309/2023, Anexo XI.
    # MVA-ST original; operação interestadual usa a fórmula geral do art. 16 da parte geral.
    "16.001.00": 42.00,
    "16.002.00": 32.00,
    "16.003.00": 60.00,
    "16.004.00": 45.00,
    "16.005.00": 45.00,
    "16.006.00": 30.00,
    "16.007.00": 45.00,
    "16.007.01": 45.00,
    "16.008.00": 45.00,
    "16.009.00": 45.00,
}

MVA_AUTOPECAS_AL = {
    # Decreto AL nº 90.309/2023, Anexo I.
    "fidelidade": 36.56,
    "demais": 71.78,
}

CEST_PNEUMATICOS_PB = {
    # Anexo 05 do RICMS/PB — tabela atualizada em 09/07/2025, alíquota interna 20%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 70.40, 7.0: 65.08, 12.0: 56.20}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 58.40, 7.0: 53.45, 12.0: 45.20}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 92.00, 7.0: 86.00, 12.0: 76.00}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
}

MVA_AUTOPECAS_PB = {
    # Anexo 05 do RICMS/PB — valores oficiais para operações interna e interestaduais.
    "fidelidade": {"original": 36.56, "ajustada": {4.0: 63.87, 7.0: 58.75, 12.0: 50.22}},
    "demais": {"original": 71.78, "ajustada": {4.0: 106.14, 7.0: 99.69, 12.0: 88.96}},
}

CEST_PNEUMATICOS_MS = {
    # RICMS/MS, Anexo III, Subanexo I, segmento 16.
    # Tabela vigente: operação interna e margens próprias para 4%, 7% e 12%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 64.24, 7.0: 59.11, 12.0: 50.55}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 52.67, 7.0: 47.90, 12.0: 39.95}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 85.06, 7.0: 79.28, 12.0: 69.64}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
    "16.005.00": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
    "16.006.00": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
    "16.007.01": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
    "16.009.00": {"original": 45.00, "ajustada": {4.0: 67.71, 7.0: 62.47, 12.0: 53.73}},
}

CEST_PNEUMATICOS_MA = {
    # Maranhão: MVA original do Convênio 102/17 e ajuste pela fórmula geral,
    # considerando alíquota interna modal de 23% vigente desde 23/02/2025.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 77.04, 7.0: 71.51, 12.0: 62.29}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 64.57, 7.0: 59.43, 12.0: 50.86}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 99.48, 7.0: 93.25, 12.0: 82.86}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 80.78, 7.0: 75.13, 12.0: 65.71}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 80.78, 7.0: 75.13, 12.0: 65.71}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 80.78, 7.0: 75.13, 12.0: 65.71}},
}

MVA_AUTOPECAS_MA = {
    # Protocolo ICMS 41/08: 36,56% para fidelidade/exclusividade qualificada
    # e 71,78% nos demais casos, ajustadas à alíquota interna de 23%.
    "fidelidade": {"original": 36.56, "ajustada": {4.0: 70.26, 7.0: 64.94, 12.0: 56.07}},
    "demais": {"original": 71.78, "ajustada": {4.0: 114.17, 7.0: 107.47, 12.0: 96.32}},
}

CEST_PNEUMATICOS_PI = {
    # RICMS/PI, Anexo X, arts. 75 e 76; alíquota interna modal 22,5%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 75.90, 7.0: 70.40, 12.0: 61.24}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 63.51, 7.0: 58.40, 12.0: 49.88}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 98.19, 7.0: 92.00, 12.0: 81.68}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 79.61, 7.0: 74.00, 12.0: 64.65}},
    "16.006.00": {"original": 30.00, "ajustada": {4.0: 61.03, 7.0: 56.00, 12.0: 47.61}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 79.61, 7.0: 74.00, 12.0: 64.65}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 79.61, 7.0: 74.00, 12.0: 64.65}},
}

MVA_AUTOPECAS_PI = {
    # RICMS/PI, Anexo X, art. 94: 26,50% nas hipóteses qualificadas de fidelidade
    # e 40,00% nos demais casos. Ajuste calculado para alíquota interna modal 22,5%.
    "fidelidade": {"original": 26.50, "ajustada": {4.0: 56.70, 7.0: 51.80, 12.0: 43.64}},
    "demais": {"original": 40.00, "ajustada": {4.0: 73.42, 7.0: 68.00, 12.0: 58.97}},
}

CEST_PNEUMATICOS_TO = {
    # Tocantins: MVA original do Convênio 102/17 e ajuste pela fórmula geral,
    # considerando alíquota interna modal de 20%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 70.40, 7.0: 65.07, 12.0: 56.20}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 58.40, 7.0: 53.45, 12.0: 45.20}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 92.00, 7.0: 86.00, 12.0: 76.00}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
}

MVA_AUTOPECAS_TO = {
    # Protocolo ICMS 97/10: 36,56% para fidelidade/exclusividade qualificada
    # e 71,78% nos demais casos; ajuste para alíquota interna modal de 20%.
    "fidelidade": {"original": 36.56, "ajustada": {4.0: 63.87, 7.0: 58.75, 12.0: 50.22}},
    "demais": {"original": 71.78, "ajustada": {4.0: 106.14, 7.0: 99.69, 12.0: 88.96}},
}

CEST_PNEUMATICOS_AC = {
    # IN DIAT/SEFAZ-AC nº 1/2023, Anexo I, segmento 16; alíquota interna 19%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 68.30, 7.0: 63.04, 12.0: 54.27}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 56.44, 7.0: 51.56, 12.0: 43.41}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 89.63, 7.0: 83.70, 12.0: 73.83}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 71.85, 7.0: 66.48, 12.0: 57.53}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 71.85, 7.0: 66.48, 12.0: 57.53}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 71.85, 7.0: 66.48, 12.0: 57.53}},
}

MVA_AUTOPECAS_AC = {
    # IN DIAT/SEFAZ-AC nº 1/2023, Anexo I, segmento 1 / Protocolo 41/08.
    "fidelidade": {"original": 36.56, "ajustada": {4.0: 61.85, 7.0: 56.79, 12.0: 48.36}},
    "demais": {"original": 71.78, "ajustada": {4.0: 103.59, 7.0: 97.23, 12.0: 86.63}},
}

CEST_PNEUMATICOS_AM = {
    # Lei AM 6.108/2022, Anexo XVI; ajuste para alíquota interna modal de 20%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 70.40, 7.0: 65.07, 12.0: 56.20}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 58.40, 7.0: 53.45, 12.0: 45.20}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 92.00, 7.0: 86.00, 12.0: 76.00}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
}

MVA_AUTOPECAS_AM = {
    # Lei AM 6.108/2022, Anexo III / Protocolo 41/08; alíquota interna 20%.
    "fidelidade": {"original": 36.56, "ajustada": {4.0: 63.87, 7.0: 58.75, 12.0: 50.22}},
    "demais": {"original": 71.78, "ajustada": {4.0: 106.14, 7.0: 99.69, 12.0: 88.96}},
}

CEST_PNEUMATICOS_AP = {
    # RICMS/AP / Convênio ICMS 102/17; alíquota interna de 18%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 66.24, 7.0: 61.05, 12.0: 52.39}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 54.54, 7.0: 49.71, 12.0: 41.66}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 87.32, 7.0: 81.46, 12.0: 71.71}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 69.76, 7.0: 64.45, 12.0: 55.61}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 69.76, 7.0: 64.45, 12.0: 55.61}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 69.76, 7.0: 64.45, 12.0: 55.61}},
}

MVA_AUTOPECAS_AP = {
    "fidelidade": {"original": 36.56, "ajustada": {4.0: 59.88, 7.0: 54.88, 12.0: 46.55}},
    "demais": {"original": 71.78, "ajustada": {4.0: 101.11, 7.0: 94.82, 12.0: 84.35}},
}

CEST_PNEUMATICOS_RO = {
    # Decreto RO 29.048/2024, Tabela XVI. A tabela consolidada instalada é
    # deliberadamente limitada aos CEST expressamente validados.
    "16.003.00": {"original": 50.00, "ajustada": {4.0: 78.88, 7.0: 73.29, 12.0: 63.98}},
    "16.005.00": {"original": 30.00, "ajustada": {4.0: 55.03, 7.0: 50.19, 12.0: 42.11}},
    "16.007.01": {"original": 30.00, "ajustada": {4.0: 55.03, 7.0: 50.19, 12.0: 42.11}},
    "16.009.00": {"original": 30.00, "ajustada": {4.0: 55.03, 7.0: 50.19, 12.0: 42.11}},
}

MVA_AUTOPECAS_RO = {
    # Escopo validado na consolidação: CEST 01.076.00 (peças/acessórios de motocicletas).
    "demais": {"original": 30.00, "ajustada": {4.0: 55.03, 7.0: 50.19, 12.0: 42.11}},
}

CEST_PNEUMATICOS_RN = {
    # RICMS/RN, Anexo 007, Seção IX, tabela atualizada para alíquota interna de 20%
    # com efeitos a partir de 20/03/2025.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 70.40, 7.0: 65.08, 12.0: 56.20}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 58.40, 7.0: 53.45, 12.0: 45.20}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 92.00, 7.0: 86.00, 12.0: 76.00}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
}

CEST_PNEUMATICOS_SE = {
    # RICMS/SE, art. 684, § 4º-E, XII. A MVA ajustada usa como alíquota interna
    # a soma do ICMS do produto com o adicional do FECOEP (§ 4º-D-B).
    # No escopo automotivo: ICMS modal 19% + FECOEP 1% = 20%.
    "16.001.00": {"original": 42.00, "ajustada": {4.0: 70.40, 7.0: 65.08, 12.0: 56.20}},
    "16.002.00": {"original": 32.00, "ajustada": {4.0: 58.40, 7.0: 53.45, 12.0: 45.20}},
    "16.003.00": {"original": 60.00, "ajustada": {4.0: 92.00, 7.0: 86.00, 12.0: 76.00}},
    "16.004.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.007.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
    "16.008.00": {"original": 45.00, "ajustada": {4.0: 74.00, 7.0: 68.56, 12.0: 59.50}},
}

MVA_AUTOPECAS_SE = {
    # RICMS/SE, art. 684, § 4º-E, X, e Tabela VI do Anexo IX.
    # A tabela vigente já reflete ICMS 19% + FECOEP 1% no ajuste interestadual.
    "fidelidade": {"original": 36.56, "ajustada": {4.0: 63.87, 7.0: 58.75, 12.0: 50.22}},
    "demais": {"original": 71.78, "ajustada": {4.0: 106.14, 7.0: 99.69, 12.0: 88.96}},
}

CEST_PNEUMATICOS_RJ = {
    # RICMS/RJ, Livro II, Anexo I, item 9.
    # As margens ajustadas refletem a alíquota interna de 20% usada na tabela vigente.
    "16.001.00": {"original": 42.00, "ajustada": {12.0: 56.20, 4.0: 70.40}},
    "16.002.00": {"original": 32.00, "ajustada": {12.0: 45.20, 4.0: 58.40}},
    "16.003.00": {"original": 60.00, "ajustada": {12.0: 76.00, 4.0: 92.00}},
    "16.004.00": {"original": 45.00, "ajustada": {12.0: 59.50, 4.0: 74.00}},
    "16.007.00": {"original": 45.00, "ajustada": {12.0: 59.50, 4.0: 74.00}},
    "16.008.00": {"original": 45.00, "ajustada": {12.0: 59.50, 4.0: 74.00}},
}

# Origens expressamente alcançadas pelo Protocolo ICMS 41/08 na redação
# instalada no Anexo 1/BA de 2026. O conjunto é usado apenas para indicar a
# provável responsabilidade do remetente; a sujeição interna da mercadoria
# permanece confirmada pela legislação da UF de destino.
SIGNATARIOS_PROTOCOLO_41 = {
    "AC", "AL", "AM", "AP", "BA", "DF", "MA", "MG", "MT", "PA",
    "PB", "PR", "PI", "RJ", "RR", "SP",
}

# Signatários atuais do Protocolo ICMS 97/10 após a exclusão do RS pelo
# Protocolo ICMS 33/24, com efeitos a partir de 01/11/2024. MG não integra o acordo.
SIGNATARIOS_PROTOCOLO_97 = {
    "AC", "AL", "AP", "BA", "MA", "MT", "PA", "PB", "PR", "PE",
    "PI", "RJ", "RR", "SE", "TO",
}


def _mva_ajustada_formula(mva_original: float, aliquota_inter: float, aliquota_intra: float) -> float:
    """Calcula MVA/IVA-ST ajustada pela fórmula legal padrão."""
    inter = float(aliquota_inter) / 100.0
    intra = float(aliquota_intra) / 100.0
    original = float(mva_original) / 100.0
    if intra >= 1:
        raise ValueError("Alíquota interna inválida para cálculo da MVA ajustada.")
    return round((((1.0 + original) * (1.0 - inter) / (1.0 - intra)) - 1.0) * 100.0, 2)


class ICMSSTUFService:
    UFS_COBERTAS = ("SP", "ES", "BA", "RJ", "PA", "GO", "PR", "SC", "RS", "MS", "MT", "DF", "CE", "PE", "AL", "PB", "RN", "SE", "MA", "PI", "TO", "AC", "AM", "AP", "RO")

    @staticmethod
    def _base_resultado() -> Dict[str, Any]:
        return {
            "status": "",
            "potencial": False,
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 0.0,
            "cest": "",
            "segmento": "",
            "ambito": "",
            "descricao_legal": "",
            "mva_original": None,
            "mva_ajustada": None,
            "mva_aplicada": None,
            "mva_tipo": "",
            "st_modelo_calculo": "",
            "carga_liquida_st": None,
            "carga_liquida_status": "",
            "antecipacao_percentual": None,
            "antecipacao_status": "",
            "contrato_fidelidade": False,
            "vigencia_inicio": "",
            "vigencia_fim": "",
            "responsabilidade": "",
            "acordo_status": "",
            "fundamento": "",
            "fonte": URL_CONFAZ_142,
            "observacao": "",
        }

    @classmethod
    def _classificar_autopeca(
        cls,
        ncm: str,
        descricao: str,
        finalidade_automotiva: str = "",
    ) -> Dict[str, Any]:
        pista = ICMSSTMGService.analisar(
            ncm,
            contexto={
                "uf_origem": "MG",
                "uf_destino": "MG",
                "finalidade_automotiva": finalidade_automotiva,
            },
            descricao=descricao,
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência local não confirma ausência de ST. "
                    "É necessária pesquisa específica na legislação da UF."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        resultado.update({
            "potencial": True,
            "cest": str(pista.get("cest") or ""),
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        if "AUTOPE" not in segmento:
            resultado.update({
                "status": "CEST IDENTIFICADO, MAS O SEGMENTO AINDA NÃO POSSUI REGRA ESTADUAL DETALHADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": "A Sprint 17.1 detalha inicialmente o segmento de autopeças.",
            })
        return resultado

    @classmethod
    def _classificar_sp(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """Classifica autopeças e pneumáticos alcançados pela cobertura paulista estruturada."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA SP INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST em São Paulo. "
                    "É necessária pesquisa específica na legislação paulista."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_SP
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/SP ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.40 detalha em São Paulo autopeças do Anexo XIV e pneumáticos do Anexo VII "
                    "vigentes até 30/09/2026. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_es(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """Classifica a cobertura ES: pneumáticos atuais e autopeças em transição pós-2022."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA ES INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Espírito Santo. "
                    "É necessária pesquisa específica na legislação capixaba."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_ES
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/ES ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.42 detalha pneumáticos do Anexo Único da Portaria 16-R e trata autopeças "
                    "pela sistemática pós-2022. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_ba(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """Classifica autopeças e pneumáticos alcançados pelo Anexo 1/BA vigente em 2026."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA BA INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST na Bahia. "
                    "É necessária pesquisa específica no Anexo 1 do RICMS/BA."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        ambito = str(pista.get("ambito") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": ambito,
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_BA
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/BA ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.41 detalha na Bahia autopeças do item 1.1 e pneumáticos do item 10.0 "
                    "do Anexo 1 vigente em 2026. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_rj(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """Classifica autopeças e pneumáticos alcançados pela cobertura fluminense estruturada."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA RJ INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Rio de Janeiro. "
                    "É necessária pesquisa específica na legislação fluminense."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_RJ
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/RJ ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.43 detalha no Rio de Janeiro autopeças do item 7 e pneumáticos do item 9 "
                    "do Anexo I do Livro II. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_go(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """Classifica a cobertura GO: pneumáticos em ST e autopeças excluídas da ST desde 01/03/2018."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA GO INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST em Goiás. "
                    "É necessária pesquisa específica na legislação goiana."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_GO
        if autopeca:
            resultado.update({
                "status": "AUTOPEÇA/GO — EXCLUÍDA DA ST PELAS OPERAÇÕES POSTERIORES DESDE 01/03/2018",
                "aplica_st": False,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "vigencia_inicio": "2018-03-01",
                "fundamento": "Decretos GO nº 9.108/2017 e 9.147/2018 — exclusão das autopeças da ST pelas operações posteriores.",
                "fonte": URL_GO_EXCLUSAO_AUTOPECAS,
                "observacao": (
                    "O CEST é preservado para identificação da mercadoria, mas a cobertura GO não aplica "
                    "a antiga ST genérica de autopeças. Benefícios, antecipações ou regimes especiais devem "
                    "ser avaliados separadamente quando houver."
                ),
            })
            return resultado
        if not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/GO ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.44 detalha em Goiás pneumáticos do item V do Apêndice II do Anexo VIII e "
                    "a exclusão de autopeças da ST. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_pr(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """Classifica autopeças e pneumáticos da cobertura paranaense estruturada."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA PR INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Paraná. "
                    "É necessária pesquisa específica no Anexo IX do RICMS/PR."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_PR
        if autopeca and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            resultado.update({
                "status": "AUTOPEÇA/PR — CEST EXCLUÍDO DO PROTOCOLO ICMS 41/08",
                "aplica_st": False,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "fundamento": "Protocolo ICMS 41/08, redação vigente.",
                "fonte": URL_CONFAZ_PROTOCOLO_41,
            })
            return resultado
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/PR ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.45 detalha no Paraná autopeças do art. 28 do Anexo IX e pneumáticos "
                    "do art. 116, com MVAs da Resolução SEFA 571/2019. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_sc(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """SC: pneumáticos em ST; autopeças fora da ST desde 01/04/2020."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA SC INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST em Santa Catarina. "
                    "É necessária pesquisa específica na legislação catarinense."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_SC
        if autopeca:
            resultado.update({
                "status": "AUTOPEÇA/SC — EXCLUÍDA DA ST DESDE 01/04/2020",
                "aplica_st": False,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "vigencia_inicio": "2020-04-01",
                "fundamento": (
                    "Decreto SC nº 479/2020, arts. 1º a 3º — denúncia dos Protocolos ICMS 41/08 e 97/10 "
                    "e revogação da seção de autopeças no RICMS/SC."
                ),
                "fonte": URL_SC_DECRETO_479,
                "observacao": (
                    "O CEST é preservado para identificação, mas a antiga ST genérica de autopeças não é aplicada "
                    "em Santa Catarina desde 01/04/2020. Benefícios, TTDs ou regras específicas supervenientes "
                    "devem ser avaliados separadamente."
                ),
            })
            return resultado
        if not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/SC ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.46 detalha pneumáticos dos arts. 53 a 55 do Anexo 3 e a exclusão das autopeças "
                    "da ST desde 01/04/2020. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_rs(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """RS: pneumáticos em ST; autopeças fora da ST desde 01/11/2024."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA RS INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Rio Grande do Sul. "
                    "É necessária pesquisa específica na legislação gaúcha."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_RS
        if autopeca:
            resultado.update({
                "status": "AUTOPEÇA/RS — EXCLUÍDA DA ST DESDE 01/11/2024",
                "aplica_st": False,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "vigencia_inicio": "2024-11-01",
                "fundamento": (
                    "Decreto RS nº 57.848/2024 — exclusão das mercadorias do segmento de autopeças "
                    "do regime de substituição tributária a partir de 01/11/2024."
                ),
                "fonte": URL_RS_EXCLUSAO_AUTOPECAS,
                "observacao": (
                    "O CEST é preservado para identificação, mas a ST genérica de autopeças não é aplicada "
                    "no Rio Grande do Sul desde 01/11/2024. Produtos com mesma NCM/descrição mas enquadrados "
                    "em outro CEST ou acordo específico devem ser revisados separadamente."
                ),
            })
            return resultado
        if not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/RS ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.47 detalha pneumáticos do item V do Apêndice II e a exclusão das autopeças "
                    "da ST desde 01/11/2024. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_ms(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """MS: autopeças e pneumáticos estruturados pelo Subanexo I do Anexo III."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA MS INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST em Mato Grosso do Sul. "
                    "É necessária pesquisa específica no RICMS/MS."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_MS
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/MS ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.49 detalha em Mato Grosso do Sul autopeças da Tabela II e pneumáticos do segmento 16 "
                    "do Subanexo I ao Anexo III. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_mt(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """MT: autopeças e pneumáticos estruturados pelo Anexo X e Portaria 195/2019."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA MT INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST em Mato Grosso. "
                    "É necessária pesquisa específica no Anexo X do RICMS/MT."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_MT
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/MT ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.50 detalha em Mato Grosso autopeças do segmento 01 e pneumáticos do segmento 16. "
                    "Outros segmentos exigem revisão local no Anexo X."
                ),
            })
        return resultado

    @classmethod
    def _classificar_df(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """DF: autopeças do item 28 e pneumáticos estruturados pela legislação distrital."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA DF INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Distrito Federal. "
                    "É necessária pesquisa específica no Caderno I do Anexo IV do RICMS/DF."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_DF
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/DF ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.52 detalha no Distrito Federal autopeças do item 28 do Caderno I do Anexo IV "
                    "e pneumáticos da Portaria 189/1997, alterada pela Portaria 173/2011. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_ce(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """CE: autopeças e pneumáticos com regra local de carga líquida/condicional."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA CE INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Ceará. "
                    "É necessária pesquisa específica na legislação cearense."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        if "AUTOPE" not in segmento and "PNEUM" not in segmento:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/CE ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.53 detalha no Ceará autopeças e pneumáticos do escopo automotivo. "
                    "Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_pe(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """PE: autopeças e pneumáticos estruturados pela legislação estadual vigente."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA PE INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST em Pernambuco. "
                    "É necessária pesquisa específica no Anexo 37 do RICMS/PE."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_PE
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/PE ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.54 detalha em Pernambuco autopeças dos arts. 99 a 101 do Anexo 37 "
                    "e pneumáticos dos arts. 49 a 54. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_al(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """AL: autopeças do Anexo I e pneumáticos do Anexo XI do Decreto 90.309/2023."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA AL INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST em Alagoas. "
                    "É necessária pesquisa específica no Decreto AL nº 90.309/2023."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_AL
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/AL ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.55 detalha em Alagoas autopeças do Anexo I e pneumáticos do Anexo XI "
                    "do Decreto nº 90.309/2023. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_pb(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """PB: autopeças e pneumáticos do Anexo 05 do RICMS/PB estruturados."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA PB INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST na Paraíba. "
                    "É necessária pesquisa específica no Anexo 05 do RICMS/PB."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_PB
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/PB ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.56 detalha na Paraíba autopeças e pneumáticos do Anexo 05 do RICMS/PB. "
                    "Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_pi(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """PI: autopeças (Anexo X, arts. 93-94) e pneumáticos (arts. 75-76)."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA PI INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Piauí. "
                    "É necessária pesquisa específica no RICMS/PI e seus anexos."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_PI
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/PI ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.67 detalha no Piauí autopeças dos arts. 93-94 do Anexo X e "
                    "pneumáticos dos arts. 75-76. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_ac(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """AC: autopeças da IN 01/2023/Prot. 41/08 e pneus do Conv. 102/17."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA AC INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Acre. "
                    "É necessária pesquisa específica no RICMS/AC e na IN DIAT 01/2023."
                ),
            })
            return resultado
        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_AC
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/AC ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.70 detalha no Acre autopeças do segmento 1 e pneumáticos do segmento 16 "
                    "da IN DIAT 01/2023. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_am(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """AM: autopeças e pneumáticos da Lei 6.108/2022."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA AM INSTALADA",
                "potencial": False, "decisao_confirmada": False, "confiabilidade": 25.0,
                "observacao": "A ausência na base instalada não confirma ausência de ST no Amazonas; revisar a Lei 6.108/2022.",
            })
            return resultado
        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True, "cest": cest, "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        if "AUTOPE" not in segmento and not ("PNEUM" in segmento and cest in CEST_PNEUMATICOS_AM):
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/AM ESTRUTURADA",
                "decisao_confirmada": False, "confiabilidade": 45.0,
                "observacao": "A 17.8.70 detalha autopeças e pneumáticos da Lei AM 6.108/2022; outros segmentos exigem revisão local.",
            })
        return resultado

    @classmethod
    def _classificar_ap(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """AP: autopeças do Prot. 41/08 e pneumáticos do Conv. 102/17."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA AP INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": "A ausência na base instalada não confirma ausência de ST no Amapá; revisar o RICMS/AP.",
            })
            return resultado
        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        if "AUTOPE" not in segmento and not ("PNEUM" in segmento and cest in CEST_PNEUMATICOS_AP):
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/AP ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": "A cobertura AP consolidada detalha autopeças e pneumáticos; outros segmentos exigem revisão local.",
            })
        return resultado

    @classmethod
    def _classificar_ro(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """RO: escopo validado para autopeças de motocicletas e pneumáticos."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA RO INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": "A ausência na base instalada não confirma ausência de ST em Rondônia; revisar o RICMS/RO.",
            })
            return resultado
        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        auto_moto = "AUTOPE" in segmento and cest == "01.076.00"
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_RO
        if not auto_moto and not pneu:
            resultado.update({
                "status": "ITEM FORA DO ESCOPO RO VALIDADO — REVISAR TABELA ESTADUAL",
                "decisao_confirmada": False,
                "confiabilidade": 55.0,
                "observacao": "A consolidação RO automatiza somente CESTs validados no Decreto 29.048/2024; não generaliza a MVA de motocicletas para outras autopeças.",
            })
        return resultado

    @classmethod
    def _classificar_to(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """TO: autopeças do Prot. 97/10/Anexo XXI e pneumáticos do Conv. 102/17."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA TO INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Tocantins. "
                    "É necessária pesquisa específica no RICMS/TO e Anexo XXI."
                ),
            })
            return resultado
        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_TO
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/TO ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.68 detalha no Tocantins autopeças do Anexo XXI/Protocolo 97/10 e "
                    "pneumáticos do Convênio 102/17. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_ma(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """MA: autopeças (Prot. 41/08) e pneumáticos (Conv. 102/17) estruturados."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA MA INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Maranhão. "
                    "É necessária pesquisa específica no RICMS/MA e anexos."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_MA
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/MA ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.63 detalha no Maranhão autopeças alcançadas pelo Protocolo 41/08 e "
                    "pneumáticos do Convênio 102/17. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_rn(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """RN: autopeças em antecipação e pneumáticos em substituição tributária."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST/NCM NÃO IDENTIFICADO NA COBERTURA RN INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de antecipação ou ST no RN. "
                    "É necessária pesquisa específica nos Anexos 005 e 007 do RICMS/RN."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_RN
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA RN ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.58 detalha no Rio Grande do Norte autopeças sujeitas à antecipação do Anexo 005 "
                    "e pneumáticos da Seção IX do Anexo 007. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _classificar_pa(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """Classifica somente segmentos cuja regra local do Pará foi estruturada."""
        pista = ICMSSTMGService.analisar(
            ncm,
            contexto={"uf_origem": "MG", "uf_destino": "MG"},
            descricao=descricao,
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA PA INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST no Pará. "
                    "É necessária pesquisa específica na legislação estadual."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        ambito = str(pista.get("ambito") or "").strip()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": ambito,
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })

        autopeca_coberta = "AUTOPE" in segmento and "1.1" in ambito
        pneu_coberto = "PNEUM" in segmento and "16.1" in ambito and cest in CEST_PNEUMATICOS_PA
        if autopeca_coberta and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            autopeca_coberta = False
            resultado.update({
                "status": "CEST EXCLUÍDO DO PROTOCOLO ICMS 41/08",
                "aplica_st": False,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "fundamento": "Protocolo ICMS 41/08, cláusula primeira, redação vigente.",
                "fonte": URL_CONFAZ_PROTOCOLO_41,
                "observacao": "O CEST está entre as exclusões expressas do protocolo interestadual de autopeças.",
            })
            return resultado

        if not autopeca_coberta and not pneu_coberto:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/PA ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.39 detalha no Pará somente autopeças do âmbito 1.1 e pneumáticos "
                    "expressamente estruturados no Anexo XIII. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _pa(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        aliquota_intra: Optional[float],
        fidelidade: bool,
    ) -> Dict[str, Any]:
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()

        if "PNEUM" in segmento:
            original = CEST_PNEUMATICOS_PA.get(cest)
            if original is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA PA ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            responsabilidade = (
                "REMETENTE, CONFORME CONVÊNIO ICMS 102/17 E ART. 701 DO RICMS/PA"
                if origem != "PA"
                else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
            )
            base.update({
                "status": "ICMS-ST/PA CONFIRMADO PARA PNEUMÁTICOS NA COBERTURA INSTALADA",
                "aplica_st": True,
                "decisao_confirmada": True,
                "confiabilidade": 98.0,
                "mva_original": original,
                "mva_ajustada": None,
                "mva_aplicada": original,
                "mva_tipo": "MVA DO ANEXO XIII/PA",
                "contrato_fidelidade": False,
                "responsabilidade": responsabilidade,
                "acordo_status": (
                    "CONVÊNIO ICMS 102/17 — REMETENTE RESPONSÁVEL"
                    if origem != "PA"
                    else "OPERAÇÃO INTERNA ALCANÇADA PELO ANEXO XIII/PA"
                ),
                "fundamento": (
                    "RICMS/PA, arts. 701 a 702-E e Anexo XIII — Pneumáticos, Câmaras de Ar e "
                    "Protetores de Borracha; Convênio ICMS 102/17."
                ),
                "fonte": URL_PA_ANEXO_XIII_2022,
                "observacao": (
                    "A MVA aplicada é a margem expressamente estruturada no Anexo XIII/PA para o CEST. "
                    "A base de cálculo e as exceções da operação concreta continuam sujeitas aos arts. 701 a 702-E."
                ),
            })
            return base

        # Autopeças: no mercado interno do PA a tabela estadual usa 71,78%.
        # Na entrada interestadual aplica-se a MVA do Protocolo 41/08 e a fórmula de ajuste.
        if cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41 and origem != "PA":
            base.update({
                "status": "CEST EXCLUÍDO DO PROTOCOLO ICMS 41/08",
                "aplica_st": False,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "fundamento": "Protocolo ICMS 41/08, cláusula primeira, redação vigente.",
                "fonte": URL_CONFAZ_PROTOCOLO_41,
            })
            return base

        if origem == "PA":
            original = 71.78
            ajustada = None
            aplicada = original
            mva_tipo = "MVA INTERNA ANEXO XIII/PA"
        else:
            original = 36.56 if fidelidade else 71.78
            ajustada = None
            aplicada = original
            mva_tipo = "MVA-ST ORIGINAL PROTOCOLO 41/08"
            if aliquota_inter is not None and aliquota_intra is not None:
                ajustada = _mva_ajustada_formula(original, aliquota_inter, aliquota_intra)
                aplicada = ajustada
                mva_tipo = "MVA AJUSTADA PROTOCOLO 41/08"

        responsabilidade, acordo = cls._responsabilidade(origem, "PA")
        base.update({
            "status": "ICMS-ST/PA CONFIRMADO PARA AUTOPEÇAS NA COBERTURA INSTALADA",
            "aplica_st": True,
            "decisao_confirmada": True,
            "confiabilidade": 96.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": mva_tipo,
            "contrato_fidelidade": fidelidade,
            "responsabilidade": responsabilidade,
            "acordo_status": acordo,
            "fundamento": (
                "Protocolo ICMS 41/08, cláusulas primeira e segunda; RICMS/PA, Anexo XIII — Autopeças."
            ),
            "fonte": f"{URL_CONFAZ_PROTOCOLO_41} | {URL_PA_ANEXO_XIII_2024}",
            "observacao": (
                "O protocolo alcança produtos de uso especificamente automotivo e exige que a mercadoria "
                "esteja sujeita à ST interna no Pará. CESTs expressamente excluídos do Protocolo 41/08 não "
                "são confirmados nesta regra. Na operação interestadual, a MVA é ajustada pela fórmula legal."
            ),
        })
        return base

    @staticmethod
    def _responsabilidade(origem: str, destino: str) -> tuple[str, str]:
        if origem == destino:
            return (
                "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA",
                "OPERAÇÃO INTERNA ALCANÇADA PELA REGRA ESTADUAL",
            )
        if origem in SIGNATARIOS_PROTOCOLO_41:
            return (
                "REMETENTE, CONFORME ACORDO INTERESTADUAL",
                "ORIGEM IDENTIFICADA ENTRE OS SIGNATÁRIOS INSTALADOS DO PROTOCOLO ICMS 41/08",
            )
        return (
            "DESTINATÁRIO/ADQUIRENTE - CONFIRMAR ANTECIPAÇÃO OU RECOLHIMENTO NA ENTRADA",
            "ORIGEM NÃO CONFIRMADA ENTRE OS SIGNATÁRIOS INSTALADOS",
        )

    @classmethod
    def _sp(
        cls,
        base: Dict[str, Any],
        data_operacao: date,
        origem: str,
        aliquota_inter: Optional[float],
        aliquota_intra: Optional[float],
        fidelidade: bool,
    ) -> Dict[str, Any]:
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        eh_pneu = "PNEUM" in segmento
        eh_autopeca = "AUTOPE" in segmento
        base.update({
            "vigencia_fim": "2026-09-30",
            "contrato_fidelidade": fidelidade,
        })

        if data_operacao >= date(2026, 10, 1):
            base.update({
                "vigencia_inicio": "2026-10-01",
                "status": "NÃO SUJEITO À ST PAULISTA DE AUTOPEÇAS/PNEUMÁTICOS A PARTIR DE 01/10/2026",
                "aplica_st": False,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "responsabilidade": "NÃO HÁ RETENÇÃO PELAS REGRAS PAULISTAS REVOGADAS",
                "acordo_status": "ANEXOS VII E XIV DA PORTARIA CAT 68/2019 REVOGADOS",
                "fundamento": "Portaria SRE 34/2026, arts. 1º e 3º.",
                "fonte": URL_SP_SRE_34,
                "observacao": (
                    "A Portaria SRE 34/2026 retira, a partir de 01/10/2026, autopeças e pneumáticos "
                    "dos anexos paulistas de ST. Conferir eventual regra especial superveniente."
                ),
            })
            return base

        if eh_pneu:
            original = CEST_PNEUMATICOS_SP.get(cest)
            if original is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA SP ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            ajustada = None
            aplicada = original
            if origem != "SP" and aliquota_inter is not None and aliquota_intra is not None:
                ajustada = _mva_ajustada_formula(original, aliquota_inter, aliquota_intra)
                aplicada = ajustada
            base.update({
                "vigencia_inicio": "2024-05-01",
                "status": "ICMS-ST/SP CONFIRMADO PARA PNEUMÁTICOS ATÉ 30/09/2026",
                "aplica_st": True,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "IVA-ST AJUSTADO" if ajustada is not None else "IVA-ST ORIGINAL",
                "responsabilidade": (
                    "REMETENTE — CONVÊNIO ICMS 102/17" if origem != "SP"
                    else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "CONVÊNIO ICMS 102/17" if origem != "SP" else "REGRA INTERNA SP",
                "fundamento": (
                    "RICMS/SP, arts. 310 e 311; Portaria CAT 68/2019, Anexo VII; "
                    "Portaria SRE 15/2024; Convênio ICMS 102/17; Portaria SRE 34/2026."
                ),
                "fonte": f"{URL_SP_CAT_68} | {URL_SP_SRE_15} | {URL_CONFAZ_CONVENIO_102} | {URL_SP_SRE_34}",
                "observacao": (
                    f"IVA-ST paulista do CEST {cest}: {original:.2f}% até 30/09/2026. "
                    "Em entrada interestadual, o IVA é ajustado quando a alíquota/carga interna informada "
                    "supera a interestadual. Benefícios ou reduções aplicáveis ao substituto podem alterar "
                    "a ALQ intra efetiva e devem ser conferidos. A ST paulista deste segmento é revogada em 01/10/2026."
                ),
            })
            return base

        if not eh_autopeca:
            return base

        # Vidros automotivos do CEST 01.015.00 saíram do Anexo XIV em 01/01/2026.
        if cest == "01.015.00" and data_operacao >= date(2026, 1, 1):
            base.update({
                "vigencia_inicio": "2026-01-01",
                "status": "NÃO SUJEITO À ST/SP PELO ANEXO XIV — CEST 01.015.00 REVOGADO EM 01/01/2026",
                "aplica_st": False,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "fundamento": "Portaria CAT 68/2019, Anexo XIV, item 15, revogado pela Portaria SRE 64/2025.",
                "fonte": URL_SP_CAT_68,
                "observacao": "A revogação específica deste item ocorreu antes da retirada geral das autopeças em 01/10/2026.",
            })
            return base

        # Baterias de arranque possuem base específica em 2026; não aplicar o IVA genérico de autopeças.
        if cest in {"01.053.00", "01.053.01"}:
            base.update({
                "vigencia_inicio": "2026-05-01",
                "status": "AUTOPEÇA COM REGRA ESPECÍFICA DE BATERIAS/SP — REVISAR PFC/IVA DA PORTARIA SRE 10/2026",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 70.0,
                "fundamento": "Portaria SRE 10/2026; Portaria CAT 68/2019, Anexo XIV, itens 53 e 54.",
                "fonte": "https://legislacao.fazenda.sp.gov.br/Paginas/Portaria-SRE-10-de-2026.aspx",
                "observacao": (
                    "Os CEST 01.053.00 e 01.053.01 não usam automaticamente o IVA genérico de 72,15%. "
                    "A base pode depender de preço final ao consumidor e das condições da Portaria SRE 10/2026. "
                    "A regra paulista é revogada em 01/10/2026."
                ),
            })
            return base

        original = 47.19 if fidelidade else 72.15
        aplicada = original
        ajustada = None
        if origem != "SP" and aliquota_inter is not None and aliquota_intra is not None:
            ajustada = _mva_ajustada_formula(original, aliquota_inter, aliquota_intra)
            aplicada = ajustada
        responsabilidade, acordo = cls._responsabilidade(origem, "SP")
        base.update({
            "vigencia_inicio": "2023-04-01",
            "status": "ICMS-ST/SP CONFIRMADO PARA AUTOPEÇAS ATÉ 30/09/2026",
            "aplica_st": True,
            "decisao_confirmada": True,
            "confiabilidade": 100.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "IVA-ST AJUSTADO" if ajustada is not None else "IVA-ST ORIGINAL",
            "responsabilidade": responsabilidade,
            "acordo_status": acordo,
            "fundamento": (
                "RICMS/SP, arts. 313-O e 313-P; Portaria CAT 68/2019, Anexo XIV; "
                "Portaria SRE 16/2023; Portaria SRE 34/2026."
            ),
            "fonte": f"{URL_SP_CAT_68} | {URL_SP_SRE_16} | {URL_SP_SRE_34}",
            "observacao": (
                "IVA-ST de 47,19% para hipóteses de fidelidade e 72,15% nos demais casos, vigente até "
                "30/09/2026. Em entrada interestadual, aplica-se a fórmula de ajuste. A ST paulista de "
                "autopeças é revogada em 01/10/2026."
            ),
        })
        return base

    @classmethod
    def _ba(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        fidelidade: bool,
        data_operacao: date,
    ) -> Dict[str, Any]:
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_BA.get(cest)
            if not regra:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA BA ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "BA" else regra["ajustada"].get(float(aliquota_inter or 0.0))
            aplicada = original if origem == "BA" else ajustada
            responsabilidade = "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA" if origem == "BA" else "REMETENTE — CONVÊNIO ICMS 102/17"
            acordo = "REGRA INTERNA DO ANEXO 1/BA" if origem == "BA" else "CONVÊNIO ICMS 102/17 — CONFERIR SIGNATÁRIO/VIGÊNCIA DA ORIGEM"
            if origem == "SP":
                responsabilidade = "REVISAR RESPONSABILIDADE DO REMETENTE DE SP"
                acordo = "CONVÊNIO ICMS 102/17 — ALTERAÇÕES DE 2026 EXIGEM CONFERÊNCIA PARA ORIGEM SP"
            base.update({
                "status": "ICMS-ST/BA CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": ajustada is not None or origem == "BA",
                "confiabilidade": 100.0 if (ajustada is not None or origem == "BA") else 75.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA DO ANEXO 1/BA" if ajustada is not None else "MVA ORIGINAL DO ANEXO 1/BA",
                "contrato_fidelidade": False,
                "vigencia_inicio": "2026-01-01",
                "vigencia_fim": "",
                "responsabilidade": responsabilidade,
                "acordo_status": acordo,
                "fundamento": "RICMS/BA 2012, Anexo 1, item 10.0; Convênio ICMS 102/17.",
                "fonte": URL_BA_ANEXO_1_2026,
                "observacao": (
                    f"CEST {cest}: MVA original {original:.2f}% e MVA ajustada conforme a alíquota interestadual "
                    "na tabela oficial do Anexo 1/BA vigente em 2026. Alterações de acordo interestadual com "
                    "origem SP em 2026 devem ser conferidas pela data da operação."
                ),
            })
            if origem != "BA" and ajustada is None:
                base.update({
                    "status": "ST/BA IDENTIFICADA PARA PNEUMÁTICOS, MAS A MVA AJUSTADA EXIGE REVISÃO",
                    "mva_aplicada": None,
                })
            return base

        # Autopeças — item 1.1 do Anexo 1/BA, redação 2026.
        original = 36.56 if fidelidade else 71.78
        tabelas = {
            True: {4.0: 64.90, 7.0: 59.75, 12.0: 51.16},
            False: {4.0: 107.43, 7.0: 100.95, 12.0: 90.15},
        }
        ajustada = None if origem == "BA" else tabelas[fidelidade].get(float(aliquota_inter or 0.0))
        aplicada = ajustada if ajustada is not None else original
        responsabilidade, acordo = cls._responsabilidade(origem, "BA")
        base.update({
            "status": "ICMS-ST/BA CONFIRMADO PARA AUTOPEÇAS",
            "aplica_st": True,
            "decisao_confirmada": True,
            "confiabilidade": 100.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA AJUSTADA" if ajustada is not None else "MVA ORIGINAL",
            "contrato_fidelidade": fidelidade,
            "vigencia_inicio": "2026-01-01",
            "vigencia_fim": "",
            "responsabilidade": responsabilidade,
            "acordo_status": acordo,
            "fundamento": "RICMS/BA 2012, Anexo 1, item 1.1, redação vigente em 2026 (Decreto 24.540/2026).",
            "fonte": URL_BA_ANEXO_1_2026,
            "observacao": (
                "MVA original de 36,56% com fidelidade ou 71,78% nos demais casos. "
                "As MVAs ajustadas oficiais de 2026 são 64,90/59,75/51,16% com fidelidade e "
                "107,43/100,95/90,15% nos demais casos para alíquotas interestaduais de 4/7/12%."
            ),
        })
        if origem != "BA" and ajustada is None:
            base.update({
                "decisao_confirmada": False,
                "confiabilidade": 75.0,
                "status": "ST/BA IDENTIFICADA, MAS A MVA AJUSTADA EXIGE REVISÃO",
                "observacao": base["observacao"] + " A alíquota interestadual informada não possui tabela instalada.",
            })
        return base

    @classmethod
    def _es(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        fidelidade: bool,
        data_operacao: date,
    ) -> Dict[str, Any]:
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()

        # Pneumáticos permanecem estruturados na Portaria 16-R/2019 atualizada.
        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_ES.get(cest)
            if not regra:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA ES ESTRUTURADA",
                    "aplica_st": False,
                    "decisao_confirmada": False,
                    "confiabilidade": 55.0,
                    "fonte": URL_ES_PORTARIA_16,
                    "observacao": "O segmento é pneumáticos, mas o CEST não possui MVA instalada nesta versão.",
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "ES" else regra["ajustada"].get(float(aliquota_inter or 0.0))
            aplicada = original if origem == "ES" else ajustada
            base.update({
                "status": "ICMS-ST/ES CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "ES" or ajustada is not None,
                "confiabilidade": 100.0 if origem == "ES" or ajustada is not None else 75.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA ORIGINAL" if origem == "ES" else "MVA AJUSTADA",
                "contrato_fidelidade": False,
                "vigencia_inicio": "2019-04-12",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/RESPONSÁVEL CONFORME CONVÊNIO ICMS 102/17 E RICMS/ES; REVISAR PAPEL DO CONTRIBUINTE"
                ),
                "acordo_status": "CONVÊNIO ICMS 102/17 — PNEUMÁTICOS",
                "fundamento": "Portaria SEFAZ/ES nº 16-R/2019, Anexo Único, XII — Pneumáticos; Convênio ICMS 102/17.",
                "fonte": URL_ES_PORTARIA_16,
                "observacao": (
                    f"CEST {cest}: MVA original {original:.2f}% e MVA ajustada conforme a alíquota "
                    "interestadual da tabela oficial capixaba."
                ),
            })
            if origem != "ES" and ajustada is None:
                base.update({
                    "status": "ST/ES DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA AJUSTADA EXIGE REVISÃO",
                    "decisao_confirmada": False,
                    "mva_aplicada": None,
                    "mva_tipo": "",
                })
            return base

        # Autopeças: o ES denunciou o Protocolo 41/08 a partir de 03/02/2022 e
        # a Portaria 13-R/2022 passou a listar autopeças sujeitas à antecipação parcial.
        if "AUTOPE" in segmento and data_operacao >= date(2022, 2, 3):
            base.update({
                "status": "AUTOPEÇA/ES — NÃO CONFIRMAR ST GENÉRICA; REVISAR ANTECIPAÇÃO PARCIAL",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 92.0,
                "mva_original": None,
                "mva_ajustada": None,
                "mva_aplicada": None,
                "mva_tipo": "",
                "contrato_fidelidade": fidelidade,
                "vigencia_inicio": "2022-02-03",
                "vigencia_fim": "",
                "responsabilidade": "REVISAR ANTECIPAÇÃO PARCIAL, CREDENCIAMENTO E EVENTUAL REGRA ESPECÍFICA",
                "acordo_status": "PROTOCOLO ICMS 41/08 DENUNCIADO PELO ES A PARTIR DE 03/02/2022",
                "fundamento": (
                    "Portaria SEFAZ/ES nº 13-R/2022, Anexo I (antecipação parcial de autopeças); "
                    "denúncia do ES ao Protocolo ICMS 41/08 a partir de 03/02/2022."
                ),
                "fonte": URL_ES_PORTARIA_13_2022,
                "observacao": (
                    "A lista ampla de autopeças deixou de ser tratada automaticamente como ST interestadual pelo "
                    "Protocolo 41/08 no Espírito Santo. Em 2026, o FiscalPro preserva o CEST identificado, mas "
                    "exige revisão da antecipação parcial, credenciamento do destinatário e regras específicas antes "
                    "de afirmar retenção de ICMS-ST."
                ),
            })
            return base

        # Histórico anterior à denúncia do ES: preserva a regra legada instalada,
        # útil para análise de documentos de competências antigas.
        original = 36.56 if fidelidade else 71.78
        tabela_padrao = {
            True: {4.0: 57.95, 7.0: 53.01, 12.0: 44.78},
            False: {4.0: 98.68, 7.0: 92.47, 12.0: 82.13},
        }
        tabela_sp = {
            True: {4.0: 57.95, 7.0: 53.01},
            False: {4.0: 98.68, 7.0: 92.47, 12.0: 69.21},
        }
        tabela = tabela_sp if origem == "SP" else tabela_padrao
        ajustada = None if origem == "ES" else tabela[fidelidade].get(float(aliquota_inter or 0.0))
        aplicada = ajustada if ajustada is not None else original
        responsabilidade, acordo = cls._responsabilidade(origem, "ES")
        base.update({
            "status": "ICMS-ST/ES HISTÓRICO PARA AUTOPEÇAS — REGRA ANTERIOR À DENÚNCIA",
            "aplica_st": True,
            "decisao_confirmada": True,
            "confiabilidade": 90.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA AJUSTADA" if ajustada is not None else "MVA ORIGINAL",
            "contrato_fidelidade": fidelidade,
            "vigencia_inicio": "2009-11-01",
            "vigencia_fim": "2022-02-02",
            "responsabilidade": responsabilidade,
            "acordo_status": acordo,
            "fundamento": "Regra histórica do Protocolo ICMS 41/08 antes da denúncia pelo Espírito Santo.",
            "fonte": URL_CONFAZ_PROTOCOLO_41,
            "observacao": "Regra mantida apenas para análise histórica anterior a 03/02/2022.",
        })
        if origem != "ES" and ajustada is None:
            base.update({
                "decisao_confirmada": False,
                "confiabilidade": 70.0,
                "status": "ST/ES HISTÓRICA IDENTIFICADA, MAS A MVA AJUSTADA EXIGE REVISÃO",
            })
        return base

    @classmethod
    def _go(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
    ) -> Dict[str, Any]:
        if base.get("decisao_confirmada") and not base.get("aplica_st"):
            return base
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        if "PNEUM" not in segmento:
            return base
        regra = CEST_PNEUMATICOS_GO.get(cest)
        if regra is None:
            base.update({
                "status": "PNEUMÁTICO FORA DA TABELA GO ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": "O segmento foi identificado, mas o CEST não possui MVA instalada nesta versão.",
            })
            return base
        original = float(regra["original"])
        ajustada = None if origem == "GO" else regra["ajustada"].get(float(aliquota_inter or 0.0))
        aplicada = original if origem == "GO" else ajustada
        base.update({
            "status": "ICMS-ST/GO CONFIRMADO PARA PNEUMÁTICOS",
            "aplica_st": True,
            "decisao_confirmada": origem == "GO" or ajustada is not None,
            "confiabilidade": 100.0 if (origem == "GO" or ajustada is not None) else 75.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada if aplicada is not None else original,
            "mva_tipo": "MVA AJUSTADA DO ANEXO VIII/GO" if ajustada is not None else "MVA INTERNA DO ANEXO VIII/GO",
            "vigencia_inicio": "2025-10-21",
            "vigencia_fim": "",
            "responsabilidade": (
                "REMETENTE — CONVÊNIO ICMS 102/17" if origem != "GO"
                else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
            ),
            "acordo_status": (
                "CONVÊNIO ICMS 102/17 — OPERAÇÃO INTERESTADUAL ALCANÇADA" if origem != "GO"
                else "REGRA INTERNA DO APÊNDICE II/ANEXO VIII"
            ),
            "fundamento": (
                "Decreto GO nº 10.799/2025, Apêndice II do Anexo VIII, item V — pneumáticos; "
                "Convênio ICMS 102/17."
            ),
            "fonte": f"{URL_GO_DECRETO_10799} | {URL_CONFAZ_CONVENIO_102}",
            "observacao": (
                f"CEST {cest}: MVA interna {original:.2f}% e margens interestaduais atualizadas pelo "
                "Decreto nº 10.799/2025 para a alíquota modal goiana de 19%."
            ),
        })
        if origem != "GO" and ajustada is None:
            base.update({
                "status": "ST/GO DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA AJUSTADA EXIGE REVISÃO",
                "decisao_confirmada": False,
                "confiabilidade": 75.0,
            })
        return base

    @classmethod
    def _sc(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
    ) -> Dict[str, Any]:
        if base.get("decisao_confirmada") and not base.get("aplica_st"):
            return base
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        if "PNEUM" not in segmento:
            return base
        original = CEST_PNEUMATICOS_SC.get(cest)
        if original is None:
            base.update({
                "status": "PNEUMÁTICO FORA DA TABELA SC ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
            })
            return base

        # O art. 55 do Anexo 3 define ALQ intra de 12% para o ajuste destes produtos.
        ajustada = None
        aplicada = original
        if origem != "SC" and aliquota_inter is not None:
            ajustada = _mva_ajustada_formula(original, aliquota_inter, 12.0)
            aplicada = ajustada

        base.update({
            "status": "ICMS-ST/SC CONFIRMADO PARA PNEUMÁTICOS",
            "aplica_st": True,
            "decisao_confirmada": True,
            "confiabilidade": 100.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA AJUSTADA ANEXO 3/SC" if ajustada is not None else "MVA ORIGINAL ANEXO 3/SC",
            "vigencia_inicio": "2020-12-11",
            "vigencia_fim": "",
            "responsabilidade": (
                "REMETENTE INDUSTRIAL/IMPORTADOR — REGRA DOS ARTS. 53 A 55" if origem != "SC"
                else "FABRICANTE/IMPORTADOR/SUBSTITUTO CONFORME ART. 53"
            ),
            "acordo_status": (
                "OPERAÇÃO INTERESTADUAL COM DESTINO A SC — REVISAR PAPEL DO REMETENTE E EXCEÇÕES"
                if origem != "SC" else "REGRA INTERNA SC"
            ),
            "fundamento": (
                "RICMS/SC, Anexo 3, arts. 53 a 55 — pneumáticos, câmaras de ar e protetores; "
                "art. 55, § 1º, MVA original e fórmula de ajuste."
            ),
            "fonte": f"{URL_SC_ANEXO_3} | {URL_SC_ANEXO_1A}",
            "observacao": (
                f"CEST {cest}: MVA original {original:.2f}%. O art. 55 usa alíquota interna de 12% para "
                "o ajuste deste segmento. Exceção relevante: pneumáticos/câmaras destinados como insumo a "
                "prestador de serviço de transporte contribuinte do ICMS podem ficar fora da ST quando comprovada "
                "a destinação, conforme COPAT 21/2026 e 37/2026."
            ),
        })
        return base

    @classmethod
    def _rs(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
    ) -> Dict[str, Any]:
        if base.get("decisao_confirmada") and not base.get("aplica_st"):
            return base
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        if "PNEUM" not in segmento:
            return base
        regra = CEST_PNEUMATICOS_RS.get(cest)
        if regra is None:
            base.update({
                "status": "PNEUMÁTICO FORA DA TABELA RS ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
            })
            return base

        original = float(regra["original"])
        ajustada = None
        aplicada = original
        if origem != "RS":
            ajustada = regra["ajustada"].get(float(aliquota_inter or 0.0))
            aplicada = ajustada

        base.update({
            "status": "ICMS-ST/RS CONFIRMADO PARA PNEUMÁTICOS",
            "aplica_st": True,
            "decisao_confirmada": origem == "RS" or ajustada is not None,
            "confiabilidade": 100.0 if (origem == "RS" or ajustada is not None) else 75.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA INTERESTADUAL RICMS/RS" if ajustada is not None else "MVA ORIGINAL RICMS/RS",
            "vigencia_inicio": "2022-01-01",
            "vigencia_fim": "",
            "responsabilidade": (
                "REMETENTE — CONVÊNIO ICMS 102/17 / REGRA INTERESTADUAL" if origem != "RS"
                else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
            ),
            "acordo_status": (
                "OPERAÇÃO INTERESTADUAL COM PNEUMÁTICOS — CONFERIR PAPEL DO REMETENTE" if origem != "RS"
                else "REGRA INTERNA DO APÊNDICE II/RS"
            ),
            "fundamento": (
                "RICMS/RS, Apêndice II, Seção III, item V, redação do Decreto nº 56.280/2021; "
                "Convênio ICMS 102/17 para operações interestaduais com pneumáticos."
            ),
            "fonte": f"{URL_RS_RICMS} | {URL_CONFAZ_CONVENIO_102}",
            "observacao": (
                f"CEST {cest}: MVA interna {original:.2f}%. Para operação interestadual a tabela gaúcha "
                "traz margens próprias para alíquotas de 12% e 4%. ROT-ST/RS e eventual ajuste do imposto "
                "retido são matérias posteriores à identificação da ST e devem ser avaliados no contribuinte gaúcho."
            ),
        })
        if origem != "RS" and ajustada is None:
            base.update({
                "status": "ST/RS DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                "mva_aplicada": None,
            })
        return base

    @classmethod
    def _ms(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        fidelidade: bool,
    ) -> Dict[str, Any]:
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_MS.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA MS ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "MS" else regra["ajustada"].get(float(aliquota_inter or 0.0))
            aplicada = original if origem == "MS" else ajustada
            base.update({
                "status": "ICMS-ST/MS CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "MS" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "MS" or ajustada is not None) else 75.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA INTERESTADUAL RICMS/MS" if ajustada is not None else "MVA ORIGINAL RICMS/MS",
                "vigencia_inicio": "2016-03-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE INSCRITO COMO SUBSTITUTO OU DESTINATÁRIO MS — CONFERIR CADASTRO/RESPONSABILIDADE"
                    if origem != "MS" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": (
                    "REGRA ESTADUAL MS + CONVÊNIO DE PNEUMÁTICOS — CONFERIR RESPONSÁVEL PELO RECOLHIMENTO"
                    if origem != "MS" else "REGRA INTERNA DO SUBANEXO I/ANEXO III"
                ),
                "fundamento": (
                    "RICMS/MS, Anexo III, Subanexo I, segmento 16; Lei MS nº 1.810/1997, art. 49, § 1º, XXII; "
                    "Convênio ICMS 85/93."
                ),
                "fonte": f"{URL_MS_RICMS} | {URL_MS_SEFAZ_ST}",
                "observacao": (
                    f"CEST {cest}: MVA interna {original:.2f}% e margens interestaduais próprias da tabela de MS. "
                    "A responsabilidade pelo recolhimento deve considerar inscrição do remetente como substituto e "
                    "as regras cadastrais vigentes no Estado."
                ),
            })
            if origem != "MS" and ajustada is None:
                base.update({
                    "status": "ST/MS DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                })
            return base

        if "AUTOPE" not in segmento:
            return base

        # Tabela II do Subanexo I/Anexo III: autopeças usam MVA interna de 50%
        # e margens interestaduais próprias. Regimes especiais podem autorizar MVA diferente.
        original = 50.0
        tabela = {4.0: 73.49, 7.0: 68.07, 12.0: 59.04}
        ajustada = None if origem == "MS" else tabela.get(float(aliquota_inter or 0.0))
        aplicada = original if origem == "MS" else ajustada
        base.update({
            "status": "ICMS-ST/MS CONFIRMADO PARA AUTOPEÇAS",
            "aplica_st": True,
            "decisao_confirmada": origem == "MS" or ajustada is not None,
            "confiabilidade": 100.0 if (origem == "MS" or ajustada is not None) else 75.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA INTERESTADUAL RICMS/MS" if ajustada is not None else "MVA ORIGINAL RICMS/MS",
            "contrato_fidelidade": fidelidade,
            "vigencia_inicio": "2016-03-01",
            "vigencia_fim": "",
            "responsabilidade": (
                "REMETENTE INSCRITO COMO SUBSTITUTO OU DESTINATÁRIO MS — CONFERIR CADASTRO/REGIME ESPECIAL"
                if origem != "MS" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
            ),
            "acordo_status": (
                "ST INTERNA DE MS; RESPONSABILIDADE INTERESTADUAL DEPENDE DE INSCRIÇÃO/CREDENCIAMENTO"
                if origem != "MS" else "REGRA INTERNA DO SUBANEXO I/ANEXO III"
            ),
            "fundamento": (
                "RICMS/MS, Anexo III, Subanexo I, Tabela II (Autopeças); Decreto MS nº 14.383/2016; "
                "Lei MS nº 1.810/1997, art. 49, § 1º, XXIX."
            ),
            "fonte": f"{URL_MS_DECRETO_14383} | {URL_MS_RICMS} | {URL_MS_SEFAZ_ST}",
            "observacao": (
                "MVA padrão da Tabela II: 50% interna; 73,49% para interestadual 4%; 68,07% para 7%; "
                "59,04% para 12%. O art. 5º do Decreto 14.383/2016 permite MVA diferenciada por regime especial, "
                "autorização específica ou termo de acordo, que deve ser conferido no contribuinte."
            ),
        })
        if origem != "MS" and ajustada is None:
            base.update({
                "status": "ST/MS DE AUTOPEÇAS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                "mva_aplicada": None,
                "mva_tipo": "",
            })
        return base

    @classmethod
    def _mt(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a MVA mato-grossense sem inventar MVA ajustada interestadual.

        A Portaria 195/2019 tem dois patamares relevantes para os segmentos
        automotivos. Na ausência de informação sobre benefício/ROST do
        destinatário, o FiscalPro usa conservadoramente o art. 2º-B e mantém
        a condição visível para revisão.
        """
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()

        if "PNEUM" in segmento:
            original = CEST_PNEUMATICOS_MT.get(cest)
            if original is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA MT ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            aplicada = 78.79
            base.update({
                "status": "ICMS-ST/MT CONFIRMADO PARA PNEUMÁTICOS — MVA CONDICIONAL AO BENEFÍCIO DO DESTINATÁRIO",
                "aplica_st": True,
                "decisao_confirmada": True,
                "confiabilidade": 92.0,
                "mva_original": float(original),
                "mva_ajustada": None,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA ART. 2º-B/MT — DESTINATÁRIO SEM BENEFÍCIO INFORMADO",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2020-01-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONFERIR INSCRIÇÃO E RESPONSABILIDADE NO ACORDO INTERESTADUAL"
                    if origem != "MT" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "ANEXO X/MT + PORTARIA 195/2019 — CONFERIR SITUAÇÃO DO DESTINATÁRIO",
                "fundamento": (
                    "RICMS/MT, Anexo X; Portaria SEFAZ/MT nº 195/2019, arts. 1º, 2º-B e 3º, "
                    "e Anexo Único, segmento XIV (pneumáticos)."
                ),
                "fonte": f"{URL_MT_ANEXO_X} | {URL_MT_PORTARIA_195}",
                "observacao": (
                    f"CEST {cest}: a tabela-base da Portaria 195/2019 traz MVA de {float(original):.2f}%. "
                    "Para destinatário não optante/não contemplado pelo benefício fiscal referido no art. 2º-B, "
                    "a MVA do segmento 16 é 78,79%. O art. 3º determina que os percentuais da Portaria sejam "
                    "aplicados independentemente da UF do remetente; portanto o FiscalPro NÃO calcula MVA ajustada "
                    "pela fórmula interestadual. Confirme a situação cadastral/benefício do destinatário antes de aplicar."
                ),
            })
            return base

        if "AUTOPE" not in segmento:
            return base

        base.update({
            "status": "ICMS-ST/MT CONFIRMADO PARA AUTOPEÇAS — MVA CONDICIONAL AO BENEFÍCIO DO DESTINATÁRIO",
            "aplica_st": True,
            "decisao_confirmada": True,
            "confiabilidade": 92.0,
            "mva_original": 50.39,
            "mva_ajustada": None,
            "mva_aplicada": 65.29,
            "mva_tipo": "MVA ART. 2º-B/MT — DESTINATÁRIO SEM BENEFÍCIO INFORMADO",
            "contrato_fidelidade": contrato_fidelidade,
            "vigencia_inicio": "2020-01-01",
            "vigencia_fim": "",
            "responsabilidade": (
                "REMETENTE/SUBSTITUTO — CONFERIR PROTOCOLO 41/08, INSCRIÇÃO E RESPONSABILIDADE"
                if origem != "MT" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
            ),
            "acordo_status": "AUTOPEÇAS/MT — PROTOCOLO 41/08 + ANEXO X; CONFERIR SITUAÇÃO DO DESTINATÁRIO",
            "fundamento": (
                "RICMS/MT, Anexo X; Portaria SEFAZ/MT nº 195/2019, arts. 1º, 2º-B e 3º, "
                "e Anexo Único, tabela I (autopeças); Protocolo ICMS 41/08."
            ),
            "fonte": f"{URL_MT_ANEXO_X} | {URL_MT_PORTARIA_195} | {URL_CONFAZ_PROTOCOLO_41}",
            "observacao": (
                "Autopeças: a tabela-base da Portaria 195/2019 traz MVA de 50,39%. Para destinatário não optante/"
                "não contemplado pelo benefício fiscal referido no art. 2º-B, a MVA do segmento 01 é 65,29%. "
                "O art. 3º manda aplicar os percentuais independentemente da UF do remetente; não se calcula MVA "
                "ajustada interestadual. Confirme benefício/ROST e eventual responsabilidade do remetente."
            ),
        })
        return base

    @staticmethod
    def _carga_liquida_ce_por_origem(origem: str) -> float:
        origem = str(origem or "").strip().upper()
        if origem == "CE":
            return 8.00
        if origem in {"AC", "AL", "AP", "AM", "BA", "DF", "GO", "MA", "MT", "MS", "PA", "PB", "PE", "PI", "RN", "RO", "RR", "SE", "TO", "ES"}:
            return 19.71
        return 21.00

    @classmethod
    def _ce(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a cobertura conservadora do regime automotivo do Ceará.

        O Decreto 30.519/2011 não é uma tabela simples de MVA: para destinatários
        enquadrados nos CNAEs dos Anexos I/II há carga tributária líquida na entrada.
        Como a Ficha ainda não captura o CNAE principal do destinatário cearense,
        o FiscalPro mostra a carga correspondente à origem, mas mantém a decisão
        como condicional. Pneus de motocicleta têm ainda bifurcação para o regime
        específico quando houver redução de base de cálculo.
        """
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        carga = cls._carga_liquida_ce_por_origem(origem)
        base.update({
            "mva_original": None,
            "mva_ajustada": None,
            "mva_aplicada": None,
            "mva_tipo": "NÃO USAR MVA AUTOMÁTICA — REGRA CE POR CARGA LÍQUIDA/REGIME ESPECÍFICO",
            "contrato_fidelidade": contrato_fidelidade,
            "vigencia_inicio": "2024-01-01",
            "vigencia_fim": "",
            "carga_liquida_st": carga,
        })

        if "PNEUM" in segmento:
            base.update({
                "status": "ICMS-ST/CE CONFIRMADO PARA PNEUMÁTICOS — MODELO DE CÁLCULO CONDICIONAL",
                "aplica_st": True,
                "decisao_confirmada": False,
                "confiabilidade": 90.0,
                "st_modelo_calculo": "CONDICIONAL — CARGA LÍQUIDA CE OU ST ESPECÍFICA DE PNEUMÁTICOS",
                "carga_liquida_status": (
                    f"Carga líquida de referência {carga:.2f}% para a origem informada, se o destinatário estiver "
                    "enquadrado no Decreto 30.519/2011 e não houver hipótese que imponha o regime específico."
                ),
                "responsabilidade": (
                    "REMETENTE NAS OPERAÇÕES INTERESTADUAIS ALCANÇADAS PELO CONVÊNIO 102/17; "
                    "REVISAR REGIME/BASE DO DESTINATÁRIO CE"
                    if origem != "CE" else "SUBSTITUTO/CONTRIBUINTE CE — REVISAR REGIME ESPECÍFICO"
                ),
                "acordo_status": "CONVÊNIO ICMS 102/17 + REGRA LOCAL CE; REVISAR REDUÇÃO DE BASE/CARGA LÍQUIDA",
                "fundamento": (
                    "Convênio ICMS 102/17; Decreto CE nº 30.519/2011, arts. 1º, 2º e 6º; "
                    "Nota Explicativa SEFAZ/CE nº 03/2022; RICMS/CE, arts. 539 a 542 (regime específico)."
                ),
                "fonte": f"{URL_CONFAZ_CONVENIO_102} | {URL_CE_DECRETO_30519} | {URL_CE_NOTA_03_2022} | {URL_CE_RICMS}",
                "observacao": (
                    f"CEST {cest}. O Ceará exige cuidado especial para pneus/câmaras de ar de motos: a Nota "
                    "Explicativa nº 03/2022 esclarece que, quando houver redução de base de cálculo, prevalece o "
                    "regime específico de pneumáticos; fora dessa hipótese, o Decreto 30.519/2011 pode levar à "
                    f"carga líquida de {carga:.2f}% conforme origem e enquadramento do destinatário. Não aplicar "
                    "MVA de outro Estado nem transformar a carga líquida em MVA."
                ),
            })
            return base

        if "AUTOPE" not in segmento:
            return base

        base.update({
            "status": "REGRA ST/CE IDENTIFICADA PARA AUTOPEÇAS — CARGA LÍQUIDA CONDICIONAL AO CNAE DO DESTINATÁRIO",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 94.0,
            "st_modelo_calculo": "CARGA LÍQUIDA ST/CE — DECRETO 30.519/2011",
            "carga_liquida_status": (
                f"{carga:.2f}% para mercadoria de carga interna 20% e origem {origem}, desde que o CNAE principal "
                "do destinatário esteja nos Anexos I/II do Decreto 30.519/2011 e não exista exclusão/regime específico."
            ),
            "responsabilidade": "DESTINATÁRIO CE COMO SUBSTITUTO NA ENTRADA — CONFIRMAR CNAE PRINCIPAL/REGIME ESPECIAL",
            "acordo_status": "PROTOCOLO ICMS 41/08 NÃO INCLUI CE COMO DESTINO; APLICAÇÃO DEPENDE DA REGRA LOCAL CE",
            "fundamento": (
                "Decreto CE nº 30.519/2011, arts. 1º e 2º e Anexos I, II e III; "
                "Protocolo ICMS 41/08 (CE não consta como destino na cláusula primeira vigente)."
            ),
            "fonte": f"{URL_CE_DECRETO_30519} | {URL_CONFAZ_PROTOCOLO_41}",
            "observacao": (
                f"CEST {cest}. Para contribuinte cearense com CNAE principal abrangido pelos Anexos I/II do "
                f"Decreto 30.519/2011, a tabela vigente desde 01/01/2024 traz carga líquida de {carga:.2f}% "
                "para mercadoria de carga interna 20% conforme a origem. Na rota MG→CE, a referência é 21,00%. "
                "O Protocolo 41/08 não atribui automaticamente ao remetente de MG a ST de autopeças destinada ao CE. "
                "Confirme CNAE principal, regime especial, Simples do remetente e eventuais exclusões antes de configurar a NF."
            ),
        })
        return base

    @classmethod
    def _classificar_se(cls, ncm: str, descricao: str) -> Dict[str, Any]:
        """SE: autopeças do Protocolo 97/10/Tabela VI e pneumáticos do Convênio 102/17."""
        pista = ICMSSTMGService.analisar(
            ncm, contexto={"uf_origem": "MG", "uf_destino": "MG"}, descricao=descricao
        )
        resultado = cls._base_resultado()
        if not pista.get("encontrado"):
            resultado.update({
                "status": "CEST NÃO IDENTIFICADO NA COBERTURA SE INSTALADA",
                "potencial": False,
                "decisao_confirmada": False,
                "confiabilidade": 25.0,
                "observacao": (
                    "A ausência de correspondência na base instalada não confirma ausência de ST/antecipação em Sergipe. "
                    "É necessária pesquisa específica no RICMS/SE."
                ),
            })
            return resultado

        segmento = str(pista.get("segmento") or "").strip().upper()
        cest = str(pista.get("cest") or "").strip()
        resultado.update({
            "potencial": True,
            "cest": cest,
            "segmento": str(pista.get("segmento") or ""),
            "ambito": str(pista.get("ambito") or ""),
            "descricao_legal": str(pista.get("descricao_legal") or ""),
        })
        autopeca = "AUTOPE" in segmento
        pneu = "PNEUM" in segmento and cest in CEST_PNEUMATICOS_SE
        if not autopeca and not pneu:
            resultado.update({
                "status": "SEGMENTO/ITEM FORA DA COBERTURA ST/SE ESTRUTURADA",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": (
                    "A 17.8.62 detalha em Sergipe autopeças do Anexo II do Convênio 142/18/Tabela VI do Anexo IX "
                    "e pneumáticos do art. 684, § 4º-E, XII. Outros segmentos exigem revisão local."
                ),
            })
        return resultado

    @classmethod
    def _pe(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a cobertura de Pernambuco sem atribuir ST interestadual a quem não é signatário.

        Autopeças: PE adota o regime dos Protocolos 97/10 e 129/10, com MVA própria.
        Quando a origem não é signatária do Protocolo 97/10 (caso de MG), o motor
        preserva a MVA de antecipação de PE, mas não manda o remetente reter ST
        automaticamente. Pneumáticos: o Convênio 102/17 alcança as operações
        interestaduais entre os Estados, observadas suas exceções de CEST.
        """
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_PE.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA PE ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "PE" else regra["ajustada"].get(inter)
            aplicada = original if origem == "PE" else ajustada
            excecao_convenio = cest in {"16.005.00", "16.006.00", "16.007.01", "16.009.00"}

            if origem != "PE" and excecao_convenio:
                base.update({
                    "status": "PNEUMÁTICO/PE COM CEST EXCLUÍDO DO CONVÊNIO 102/17 — REVISAR RESPONSABILIDADE",
                    "aplica_st": False,
                    "decisao_confirmada": False,
                    "confiabilidade": 75.0,
                    "mva_original": original,
                    "mva_ajustada": ajustada,
                    "mva_aplicada": aplicada,
                    "mva_tipo": "MVA PE — RESPONSABILIDADE INTERESTADUAL EM REVISÃO",
                    "vigencia_inicio": "2024-01-01",
                    "responsabilidade": "DESTINATÁRIO PE / REGRA LOCAL — CEST FORA DO CONVÊNIO 102/17",
                    "acordo_status": "CEST EXCLUÍDO DA CLÁUSULA PRIMEIRA DO CONVÊNIO 102/17",
                    "fundamento": "RICMS/PE, Anexo 37, arts. 49 a 54; Convênio ICMS 102/17, cláusula primeira.",
                    "fonte": f"{URL_PE_RICMS} | {URL_PE_PNEUS_MVA} | {URL_CONFAZ_CONVENIO_102}",
                    "observacao": (
                        f"CEST {cest}: a tabela de PE informa MVA interna de {original:.2f}%"
                        + (f" e MVA interestadual de {aplicada:.2f}%. " if aplicada is not None else ". ")
                        + "Entretanto, este CEST está entre as exceções do Convênio 102/17; confirme a responsabilidade local antes da NF."
                    ),
                })
                return base

            base.update({
                "status": "ICMS-ST/PE CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "PE" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "PE" or ajustada is not None) else 75.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA INTERESTADUAL OFICIAL PE" if ajustada is not None else "MVA ORIGINAL PE",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2024-01-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17"
                    if origem != "PE" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "CONVÊNIO ICMS 102/17 + ANEXO 37 DO RICMS/PE",
                "fundamento": "RICMS/PE, Anexo 37, arts. 49 a 54; Convênio ICMS 102/17.",
                "fonte": f"{URL_PE_RICMS} | {URL_PE_PNEUS_MVA} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA interna de {original:.2f}% na tabela oficial de PE. "
                    + (
                        f"Para a alíquota interestadual de {inter:.2f}%, a tabela oficial traz MVA de {float(aplicada):.2f}%."
                        if aplicada is not None and origem != "PE" else
                        "Na operação interna aplica-se a MVA original da tabela de PE."
                    )
                ),
            })
            if origem != "PE" and ajustada is None:
                base.update({
                    "status": "ST/PE DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        if "AUTOPE" not in segmento:
            return base

        chave = "fidelidade" if contrato_fidelidade else "demais"
        regra = MVA_AUTOPECAS_PE[chave]
        original = float(regra["original"])
        ajustada = None if origem == "PE" else regra["ajustada"].get(inter)
        aplicada = original if origem == "PE" else ajustada
        origem_signataria = origem in SIGNATARIOS_PROTOCOLO_97

        # A MVA de fidelidade é mostrada apenas quando o usuário informou a condição;
        # continua exigindo confirmação dos requisitos jurídicos do contrato.
        fidelidade_obs = (
            "Foi informada fidelidade/exclusividade. Confirmar se a operação atende integralmente aos requisitos do art. 100, I, 'a', do Anexo 37."
            if contrato_fidelidade else
            "Sem fidelidade/exclusividade qualificada informada, foi usada a MVA dos demais casos."
        )

        if origem == "PE" or origem_signataria:
            base.update({
                "status": (
                    "ICMS-ST/PE CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL AOS REQUISITOS LEGAIS"
                    if contrato_fidelidade else "ICMS-ST/PE CONFIRMADO PARA AUTOPEÇAS"
                ),
                "aplica_st": True,
                "decisao_confirmada": (origem == "PE" or ajustada is not None),
                "confiabilidade": 92.0 if contrato_fidelidade else 98.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA INTERESTADUAL OFICIAL PE" if ajustada is not None else "MVA ORIGINAL PE",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2024-01-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — PROTOCOLO ICMS 97/10"
                    if origem != "PE" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "AUTOPEÇAS/PE — PROTOCOLOS 97/10 E 129/10 + ANEXO 37, ARTS. 99 A 101",
                "fundamento": "RICMS/PE, Anexo 37, arts. 99 a 101; Protocolos ICMS 97/10 e 129/10.",
                "fonte": f"{URL_PE_RICMS} | {URL_PE_AUTOPECAS_MVA} | {URL_CONFAZ_PROTOCOLO_97}",
                "observacao": (
                    f"Autopeças/PE: MVA original de {original:.2f}%. "
                    + (f"Para alíquota interestadual de {inter:.2f}%, a tabela oficial traz {float(aplicada):.2f}%. " if aplicada is not None and origem != "PE" else "")
                    + fidelidade_obs
                ),
            })
            if origem != "PE" and ajustada is None:
                base.update({
                    "status": "ST/PE DE AUTOPEÇAS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        # Ex.: MG→PE. MG não é signatário do Protocolo 97/10. A mercadoria continua
        # sujeita ao regime/antecipação de PE, porém não se presume que o remetente
        # mineiro seja o substituto. Mantemos a MVA para cálculo/apoio, mas a decisão
        # de retenção na NF fica em revisão.
        base.update({
            "status": "REGIME ST/PE DE AUTOPEÇAS IDENTIFICADO — RETENÇÃO PELO REMETENTE NÃO AUTOMÁTICA",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 96.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA OFICIAL PE — ANTECIPAÇÃO/RESPONSABILIDADE A CONFIRMAR",
            "contrato_fidelidade": contrato_fidelidade,
            "vigencia_inicio": "2024-01-01",
            "vigencia_fim": "",
            "responsabilidade": (
                "DESTINATÁRIO PE — ANTECIPAÇÃO NA ENTRADA; REMETENTE NÃO SIGNATÁRIO SOMENTE COMO SUBSTITUTO SE AUTORIZADO/INSCRITO"
            ),
            "acordo_status": f"PROTOCOLO ICMS 97/10 NÃO ATRIBUI RESPONSABILIDADE AUTOMÁTICA À ORIGEM {origem}",
            "fundamento": "RICMS/PE, Anexo 37, arts. 99 a 101; Protocolo ICMS 97/10.",
            "fonte": f"{URL_PE_RICMS} | {URL_PE_AUTOPECAS_MVA} | {URL_CONFAZ_PROTOCOLO_97}",
            "observacao": (
                f"Autopeças/PE: MVA original de {original:.2f}% e, para alíquota interestadual de {inter:.2f}%, "
                + (f"MVA oficial de {float(aplicada):.2f}%. " if aplicada is not None else "MVA interestadual ainda não definida. ")
                + f"A origem {origem} não integra o Protocolo 97/10; portanto o FiscalPro não sugere retenção ST/CFOP 6403 automaticamente. "
                + "Confirme inscrição/autorização do remetente em PE ou a antecipação de responsabilidade do destinatário. "
                + fidelidade_obs
            ),
        })
        return base

    @classmethod
    def _al(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        aliquota_intra: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a cobertura de Alagoas com MVA ajustada e responsabilidade por acordo.

        Autopeças: Decreto 90.309/2023, Anexo I, com MVA original de 36,56%
        nas hipóteses qualificadas de fidelidade/exclusividade e 71,78% nos demais
        casos. MG e AL integram o Protocolo 41/08 vigente, portanto a rota MG→AL
        atribui, em regra, a retenção ao remetente, ressalvadas as exceções do acordo.
        Pneumáticos: Anexo XI + Convênio 102/17.
        """
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)
        intra = float(aliquota_intra or 0.0)

        if "PNEUM" in segmento:
            original = CEST_PNEUMATICOS_AL.get(cest)
            if original is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA AL ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(original)
            ajustada = None
            if origem != "AL" and inter > 0 and intra > 0:
                ajustada = _mva_ajustada_formula(original, inter, intra)
            aplicada = original if origem == "AL" else ajustada
            excecao_convenio = cest in {"16.005.00", "16.006.00", "16.007.01", "16.009.00"}

            if origem != "AL" and excecao_convenio:
                base.update({
                    "status": "PNEUMÁTICO/AL COM CEST FORA DA RESPONSABILIDADE AUTOMÁTICA DO CONVÊNIO 102/17 — REVISAR",
                    "aplica_st": False,
                    "decisao_confirmada": False,
                    "confiabilidade": 78.0,
                    "mva_original": original,
                    "mva_ajustada": ajustada,
                    "mva_aplicada": aplicada,
                    "mva_tipo": "MVA AL — RESPONSABILIDADE INTERESTADUAL EM REVISÃO",
                    "vigencia_inicio": "2023-08-01",
                    "responsabilidade": "DESTINATÁRIO AL / REGRA LOCAL — CONFIRMAR RESPONSABILIDADE",
                    "acordo_status": "CEST FORA DO ALCANCE AUTOMÁTICO DO CONVÊNIO 102/17",
                    "fundamento": "Decreto AL nº 90.309/2023, Anexo XI; Convênio ICMS 102/17.",
                    "fonte": f"{URL_AL_DECRETO_90309} | {URL_CONFAZ_CONVENIO_102}",
                    "observacao": (
                        f"CEST {cest}: MVA-ST original de {original:.2f}% em Alagoas. "
                        "O CEST exige confirmação da responsabilidade interestadual antes da NF."
                    ),
                })
                return base

            base.update({
                "status": "ICMS-ST/AL CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "AL" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "AL" or ajustada is not None) else 78.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA AL" if ajustada is not None else "MVA ORIGINAL AL",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2023-08-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17"
                    if origem != "AL" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "CONVÊNIO ICMS 102/17 + ANEXO XI DO DECRETO AL 90.309/2023",
                "fundamento": "Decreto AL nº 90.309/2023, Anexo XI; Convênio ICMS 102/17.",
                "fonte": f"{URL_AL_DECRETO_90309} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA-ST original de {original:.2f}%. "
                    + (
                        f"Com alíquota interestadual de {inter:.2f}% e interna de {intra:.2f}%, "
                        f"a fórmula legal resulta em MVA ajustada de {float(aplicada):.2f}%. "
                        if aplicada is not None and origem != "AL" else
                        "Na operação interna aplica-se a MVA-ST original. "
                    )
                    + "Revisar eventual regime especial/credenciamento do destinatário alagoano."
                ),
            })
            if origem != "AL" and ajustada is None:
                base.update({
                    "status": "ST/AL DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA AJUSTADA EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        if "AUTOPE" not in segmento:
            return base

        # Exceções expressas do caput vigente do Protocolo 41/08 não recebem
        # responsabilidade interestadual automática pelo remetente.
        if origem != "AL" and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            base.update({
                "status": "AUTOPEÇA/AL COM CEST EXCLUÍDO DO PROTOCOLO 41/08 — REVISAR RESPONSABILIDADE",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 85.0,
                "responsabilidade": "DESTINATÁRIO AL / REGRA LOCAL — CEST EXCLUÍDO DO PROTOCOLO 41/08",
                "acordo_status": "CEST EXPRESSAMENTE EXCLUÍDO DO CAPUT VIGENTE DO PROTOCOLO 41/08",
                "fundamento": "Decreto AL nº 90.309/2023, Anexo I; Protocolo ICMS 41/08.",
                "fonte": f"{URL_AL_DECRETO_90309} | {URL_CONFAZ_PROTOCOLO_41}",
            })
            return base

        chave = "fidelidade" if contrato_fidelidade else "demais"
        original = float(MVA_AUTOPECAS_AL[chave])
        ajustada = None
        if origem != "AL" and inter > 0 and intra > 0:
            ajustada = _mva_ajustada_formula(original, inter, intra)
        aplicada = original if origem == "AL" else ajustada
        origem_signataria = origem in SIGNATARIOS_PROTOCOLO_41
        fidelidade_obs = (
            "Foi informada fidelidade/exclusividade. Confirmar se a operação atende integralmente aos requisitos do Anexo I do Decreto 90.309/2023 e do Protocolo 41/08."
            if contrato_fidelidade else
            "Sem fidelidade/exclusividade qualificada informada, foi usada a MVA de 71,78% dos demais casos."
        )

        if origem == "AL" or origem_signataria:
            base.update({
                "status": (
                    "ICMS-ST/AL CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL AOS REQUISITOS LEGAIS"
                    if contrato_fidelidade else "ICMS-ST/AL CONFIRMADO PARA AUTOPEÇAS"
                ),
                "aplica_st": True,
                "decisao_confirmada": origem == "AL" or ajustada is not None,
                "confiabilidade": 94.0 if contrato_fidelidade else 100.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA AL" if ajustada is not None else "MVA ORIGINAL AL",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2023-08-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — PROTOCOLO ICMS 41/08"
                    if origem != "AL" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "AUTOPEÇAS/AL — ANEXO I DO DECRETO 90.309/2023 + PROTOCOLO ICMS 41/08",
                "fundamento": "Decreto AL nº 90.309/2023, Anexo I; Protocolo ICMS 41/08.",
                "fonte": f"{URL_AL_DECRETO_90309} | {URL_CONFAZ_PROTOCOLO_41}",
                "observacao": (
                    f"Autopeças/AL: MVA-ST original de {original:.2f}%. "
                    + (
                        f"Com alíquota interestadual de {inter:.2f}% e interna de {intra:.2f}%, "
                        f"a fórmula do Decreto 90.309/2023 resulta em MVA ajustada de {float(aplicada):.2f}%. "
                        if aplicada is not None and origem != "AL" else
                        "Na operação interna aplica-se a MVA-ST original. "
                    )
                    + fidelidade_obs
                    + " Confirmar se o destinatário está em regime especial/credenciamento atacadista que altere a apuração."
                ),
            })
            if origem != "AL" and ajustada is None:
                base.update({
                    "status": "ST/AL DE AUTOPEÇAS IDENTIFICADA, MAS A MVA AJUSTADA EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        base.update({
            "status": "REGIME ST/AL DE AUTOPEÇAS IDENTIFICADO — ORIGEM FORA DO PROTOCOLO 41/08",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 92.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA AL — RESPONSABILIDADE A CONFIRMAR",
            "responsabilidade": "DESTINATÁRIO AL / REGRA LOCAL — REMETENTE NÃO SIGNATÁRIO",
            "acordo_status": f"PROTOCOLO 41/08 NÃO ATRIBUI RESPONSABILIDADE AUTOMÁTICA À ORIGEM {origem}",
            "fundamento": "Decreto AL nº 90.309/2023, Anexo I; Protocolo ICMS 41/08.",
            "fonte": f"{URL_AL_DECRETO_90309} | {URL_CONFAZ_PROTOCOLO_41}",
            "observacao": "A mercadoria integra a ST interna de AL, mas a responsabilidade interestadual do remetente exige revisão do acordo aplicável.",
        })
        return base

    @classmethod
    def _df(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        aliquota_intra: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica as regras estruturadas de ICMS-ST do Distrito Federal."""
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()

        if "PNEUM" in segmento:
            original = CEST_PNEUMATICOS_DF.get(cest)
            if original is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA DF ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            ajustada = None
            aplicada = float(original)
            if origem != "DF":
                if aliquota_inter is None or aliquota_intra is None:
                    base.update({
                        "status": "ICMS-ST/DF IDENTIFICADO, MAS A MVA AJUSTADA EXIGE ALÍQUOTAS DA OPERAÇÃO",
                        "aplica_st": True,
                        "decisao_confirmada": False,
                        "confiabilidade": 65.0,
                        "mva_original": float(original),
                    })
                    return base
                ajustada = _mva_ajustada_formula(float(original), float(aliquota_inter), float(aliquota_intra))
                aplicada = ajustada
            base.update({
                "status": "ICMS-ST/DF CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": True,
                "confiabilidade": 96.0,
                "mva_original": float(original),
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA DF" if ajustada is not None else "MVA ORIGINAL DF",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2012-01-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONFERIR CONVÊNIO/RESPONSABILIDADE E INSCRIÇÃO NO DF"
                    if origem != "DF" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "PNEUMÁTICOS/DF — PORTARIA 189/1997 + PORTARIA 173/2011; CONFERIR ACORDO INTERESTADUAL",
                "fundamento": (
                    "Portaria SEFP/DF nº 189/1997, alterada pela Portaria SEF/DF nº 173/2011; "
                    "RICMS/DF, Decreto nº 18.955/1997; Convênio ICMS 102/17."
                ),
                "fonte": f"{URL_DF_PORTARIA_189} | {URL_DF_PORTARIA_173} | {URL_DF_RICMS} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA-ST original de {float(original):.2f}%. "
                    + (
                        f"Na operação interestadual, a fórmula legal com alíquota interestadual de {float(aliquota_inter):.2f}% "
                        f"e alíquota interna de {float(aliquota_intra):.2f}% resulta em MVA ajustada de {float(aplicada):.2f}%."
                        if ajustada is not None else
                        "Na operação interna do DF aplica-se a MVA-ST original instalada."
                    )
                ),
            })
            return base

        if "AUTOPE" not in segmento:
            return base

        if origem != "DF" and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            base.update({
                "status": "AUTOPEÇA/DF COM CEST EXCLUÍDO DO PROTOCOLO 41/08 — REVISAR REGRA LOCAL/RESPONSABILIDADE",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 60.0,
                "fundamento": "Protocolo ICMS 41/08, redação vigente; RICMS/DF, Anexo IV, Caderno I, item 28.",
                "fonte": f"{URL_CONFAZ_PROTOCOLO_41} | {URL_DF_RICMS}",
                "observacao": (
                    "O CEST está entre as exclusões do protocolo interestadual. A cobertura não conclui ausência de ST interna "
                    "ou de outra responsabilidade no DF sem pesquisa específica."
                ),
            })
            return base

        original = 36.56 if contrato_fidelidade else 71.78
        ajustada = None
        aplicada = float(original)
        if origem != "DF":
            if aliquota_inter is None or aliquota_intra is None:
                base.update({
                    "status": "ICMS-ST/DF DE AUTOPEÇAS IDENTIFICADO, MAS A MVA AJUSTADA EXIGE ALÍQUOTAS DA OPERAÇÃO",
                    "aplica_st": True,
                    "decisao_confirmada": False,
                    "confiabilidade": 65.0,
                    "mva_original": float(original),
                })
                return base
            ajustada = _mva_ajustada_formula(float(original), float(aliquota_inter), float(aliquota_intra))
            aplicada = ajustada

        fidelidade_obs = (
            "MVA reduzida de 36,56% informada por fidelidade/exclusividade: confirmar enquadramento integral nos subitens 28.5 e 28.15 "
            "e eventual autorização prévia do Fisco, conforme a estrutura societária/distributiva."
            if contrato_fidelidade else
            "Sem indicação de fidelidade qualificada, aplica-se a MVA-ST original de 71,78% prevista para os demais casos."
        )
        base.update({
            "status": (
                "ICMS-ST/DF CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL AOS REQUISITOS LEGAIS"
                if contrato_fidelidade else "ICMS-ST/DF CONFIRMADO PARA AUTOPEÇAS"
            ),
            "aplica_st": True,
            "decisao_confirmada": True,
            "confiabilidade": 90.0 if contrato_fidelidade else 97.0,
            "mva_original": float(original),
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": (
                ("MVA AJUSTADA DF — FIDELIDADE INFORMADA; CONFIRMAR REQUISITOS" if ajustada is not None else "MVA ORIGINAL DF — FIDELIDADE INFORMADA; CONFIRMAR REQUISITOS")
                if contrato_fidelidade else ("MVA AJUSTADA DF — DEMAIS CASOS" if ajustada is not None else "MVA ORIGINAL DF — DEMAIS CASOS")
            ),
            "contrato_fidelidade": contrato_fidelidade,
            "vigencia_inicio": "2015-02-01",
            "vigencia_fim": "",
            "responsabilidade": (
                "REMETENTE/SUBSTITUTO — PROTOCOLO 41/08; CONFERIR INSCRIÇÃO/RESPONSABILIDADE"
                if origem != "DF" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
            ),
            "acordo_status": "AUTOPEÇAS/DF — ITEM 28 DO CADERNO I/ANEXO IV + PROTOCOLO 41/08",
            "fundamento": (
                "RICMS/DF, Decreto nº 18.955/1997, Anexo IV, Caderno I, item 28, subitens 28.4, 28.5 e 28.15; "
                "Protocolo ICMS 41/08."
            ),
            "fonte": f"{URL_DF_RICMS} | {URL_DF_AUTOPECAS_2025} | {URL_DF_AUTOPECAS_MVA} | {URL_CONFAZ_PROTOCOLO_41}",
            "observacao": (
                f"Autopeças/DF: MVA-ST original de {float(original):.2f}%. "
                + (
                    f"Na operação interestadual, a fórmula legal com alíquota interestadual de {float(aliquota_inter):.2f}% "
                    f"e alíquota interna de {float(aliquota_intra):.2f}% resulta em MVA ajustada de {float(aplicada):.2f}%. "
                    if ajustada is not None else "Na operação interna do DF aplica-se a MVA-ST original. "
                )
                + fidelidade_obs
            ),
        })
        return base

    @classmethod
    def _pr(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        aliquota_intra: Optional[float],
        fidelidade: bool,
    ) -> Dict[str, Any]:
        if base.get("decisao_confirmada") and not base.get("aplica_st"):
            return base
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()

        if "PNEUM" in segmento:
            original = CEST_PNEUMATICOS_PR.get(cest)
            if original is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA PR ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            ajustada = None
            aplicada = original
            if origem != "PR" and aliquota_inter is not None and aliquota_intra is not None:
                ajustada = _mva_ajustada_formula(original, aliquota_inter, aliquota_intra)
                aplicada = ajustada
            base.update({
                "status": "ICMS-ST/PR CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA ANEXO IX/PR" if ajustada is not None else "MVA ORIGINAL RES. SEFA 571/2019",
                "vigencia_inicio": "2019-07-01",
                "responsabilidade": (
                    "REMETENTE — CONVÊNIO ICMS 102/17" if origem != "PR"
                    else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": (
                    "CONVÊNIO ICMS 102/17 — OPERAÇÃO INTERESTADUAL ALCANÇADA" if origem != "PR"
                    else "REGRA INTERNA DO ANEXO IX/PR"
                ),
                "fundamento": (
                    "RICMS/PR, Anexo IX, arts. 1º e 116; Resolução SEFA nº 571/2019, art. 21; "
                    "Convênio ICMS 102/17."
                ),
                "fonte": f"{URL_PR_RESOLUCAO_571} | {URL_PR_ST_PORTAL} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA ST original {original:.2f}%. Em operação interestadual, "
                    "a MVA é ajustada pela fórmula do § 5º do art. 1º do Anexo IX do RICMS/PR."
                ),
            })
            return base

        if "AUTOPE" not in segmento:
            return base
        original = 36.56 if fidelidade else 71.78
        ajustada = None
        aplicada = original
        if origem != "PR" and aliquota_inter is not None and aliquota_intra is not None:
            ajustada = _mva_ajustada_formula(original, aliquota_inter, aliquota_intra)
            aplicada = ajustada
        responsabilidade, acordo = cls._responsabilidade(origem, "PR")
        base.update({
            "status": "ICMS-ST/PR CONFIRMADO PARA AUTOPEÇAS",
            "aplica_st": True,
            "decisao_confirmada": True,
            "confiabilidade": 100.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA AJUSTADA ANEXO IX/PR" if ajustada is not None else "MVA ORIGINAL RES. SEFA 571/2019",
            "contrato_fidelidade": fidelidade,
            "vigencia_inicio": "2019-07-01",
            "responsabilidade": responsabilidade,
            "acordo_status": acordo,
            "fundamento": (
                "RICMS/PR, Anexo IX, arts. 1º e 28; Resolução SEFA nº 571/2019, art. 5º; "
                "Protocolo ICMS 41/08."
            ),
            "fonte": f"{URL_PR_RESOLUCAO_571} | {URL_PR_ST_PORTAL} | {URL_CONFAZ_PROTOCOLO_41}",
            "observacao": (
                "MVA original de 36,56% nas hipóteses de fidelidade e 71,78% nas demais. "
                "Nas operações interestaduais, aplica-se a MVA ajustada conforme o § 5º do art. 1º "
                "do Anexo IX do RICMS/PR, salvo hipótese legal específica."
            ),
        })
        return base

    @classmethod
    def _rj(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        fidelidade: bool,
    ) -> Dict[str, Any]:
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_RJ.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA RJ ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                    "observacao": (
                        "O item não está entre os CEST de pneumáticos estruturados no item 9 do Anexo I/Livro II. "
                        "A ausência de regra instalada não confirma ausência de ST."
                    ),
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "RJ" else regra["ajustada"].get(float(aliquota_inter or 0.0))
            aplicada = ajustada if ajustada is not None else original
            base.update({
                "status": "ICMS-ST/RJ CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA" if ajustada is not None else "MVA ORIGINAL",
                "contrato_fidelidade": False,
                "vigencia_inicio": "2016-03-23",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE, CONFORME CONVÊNIO ICMS 102/17"
                    if origem != "RJ"
                    else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": (
                    "CONVÊNIO ICMS 102/17 — OPERAÇÃO INTERESTADUAL ALCANÇADA"
                    if origem != "RJ"
                    else "OPERAÇÃO INTERNA ALCANÇADA PELO ANEXO I/LIVRO II"
                ),
                "fundamento": (
                    "RICMS/RJ, Livro II, Anexo I, item 9 — pneumáticos, câmaras de ar e protetores de borracha; "
                    "Convênio ICMS 102/17."
                ),
                "fonte": URL_RJ_ANEXO_I,
                "observacao": (
                    "MVA original e margens ajustadas conforme o item 9 do Anexo I/Livro II. "
                    "Os CEST 16.005.00, 16.006.00, 16.007.01 e 16.009.00 não são automaticamente abrangidos "
                    "pelo Convênio ICMS 102/17."
                ),
            })
            if origem != "RJ" and ajustada is None:
                base.update({
                    "decisao_confirmada": False,
                    "confiabilidade": 75.0,
                    "status": "ST/RJ DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA AJUSTADA EXIGE REVISÃO",
                })
            return base

        # Autopeças — item 7 do Anexo I/Livro II.
        original = 36.56 if fidelidade else 71.78
        tabelas = {
            True: {4.0: 63.87, 12.0: 50.22},
            False: {4.0: 106.14, 12.0: 88.96},
        }
        ajustada = None if origem == "RJ" else tabelas[fidelidade].get(float(aliquota_inter or 0.0))
        aplicada = ajustada if ajustada is not None else original
        responsabilidade, acordo = cls._responsabilidade(origem, "RJ")
        if origem not in SIGNATARIOS_PROTOCOLO_41 and origem != "RJ":
            responsabilidade = "DESTINATÁRIO FLUMINENSE, CONFORME AQUISIÇÃO DE UF NÃO SIGNATÁRIA"
            acordo = "A REGRA DO RJ ALCANÇA TAMBÉM AQUISIÇÕES DE UFS NÃO SIGNATÁRIAS"
        base.update({
            "status": "ICMS-ST/RJ CONFIRMADO PARA AUTOPEÇAS",
            "aplica_st": True,
            "decisao_confirmada": True,
            "confiabilidade": 100.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA AJUSTADA" if ajustada is not None else "MVA ORIGINAL",
            "contrato_fidelidade": fidelidade,
            "vigencia_inicio": "2019-03-21",
            "vigencia_fim": "",
            "responsabilidade": responsabilidade,
            "acordo_status": acordo,
            "fundamento": "RICMS/RJ, Livro II, Anexo I, item 7 - peças, partes e acessórios para veículos automotores.",
            "fonte": URL_RJ_ANEXO_I,
            "observacao": (
                "MVA original de 36,56% com fidelidade ou 71,78% nos demais casos. "
                "Para entradas com alíquota de 12%, as MVAs ajustadas são 50,22% e 88,96%; "
                "com 4%, 63,87% e 106,14%."
            ),
        })
        if origem != "RJ" and ajustada is None:
            base.update({
                "decisao_confirmada": False,
                "confiabilidade": 75.0,
                "status": "ST/RJ IDENTIFICADA, MAS A MVA AJUSTADA EXIGE REVISÃO",
            })
        return base

    @classmethod
    def _rn(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica antecipação de autopeças e ST de pneumáticos do Rio Grande do Norte."""
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_RN.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA RN ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "RN" else regra["ajustada"].get(inter)
            aplicada = original if origem == "RN" else ajustada
            excecao_convenio = cest in {"16.005.00", "16.006.00", "16.007.01", "16.009.00"}
            if origem != "RN" and excecao_convenio:
                base.update({
                    "status": "PNEUMÁTICO/RN FORA DA RESPONSABILIDADE AUTOMÁTICA DO CONVÊNIO 102/17 — REVISAR",
                    "aplica_st": False,
                    "decisao_confirmada": False,
                    "confiabilidade": 80.0,
                    "mva_original": original,
                    "mva_ajustada": ajustada,
                    "mva_aplicada": aplicada,
                    "mva_tipo": "MVA OFICIAL RN — RESPONSABILIDADE INTERESTADUAL EM REVISÃO",
                    "responsabilidade": "DESTINATÁRIO RN / REGRA LOCAL — CONFIRMAR RESPONSABILIDADE",
                    "acordo_status": "CEST EXCEPCIONADO PELO CONVÊNIO ICMS 102/17",
                    "fundamento": "RICMS/RN, Anexo 007, Seção IX; Convênio ICMS 102/17.",
                    "fonte": f"{URL_RN_ANEXO_007} | {URL_CONFAZ_CONVENIO_102}",
                })
                return base

            base.update({
                "status": "ICMS-ST/RN CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "RN" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "RN" or ajustada is not None) else 80.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA INTERESTADUAL OFICIAL RN" if ajustada is not None else "MVA ORIGINAL RN",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2025-03-20",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17"
                    if origem != "RN" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "PNEUMÁTICOS/RN — ANEXO 007 + CONVÊNIO ICMS 102/17",
                "fundamento": "RICMS/RN, Anexo 007, Seção IX, art. 14, § 7º; Convênio ICMS 102/17.",
                "fonte": f"{URL_RN_ANEXO_007} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA original de {original:.2f}% na tabela do RN. "
                    + (
                        f"Para a alíquota interestadual de {inter:.2f}%, a tabela atualizada para alíquota interna de 20% traz MVA de {float(aplicada):.2f}%."
                        if aplicada is not None and origem != "RN" else
                        "Na operação interna aplica-se a MVA original da tabela RN."
                    )
                ),
            })
            if origem != "RN" and ajustada is None:
                base.update({
                    "status": "ST/RN DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        if "AUTOPE" not in segmento:
            return base

        # O RN não figura entre os destinos atuais do Protocolo 41/08. Autopeças
        # estão no Anexo 005 do RICMS/RN como produtos sujeitos à antecipação,
        # com percentual de agregação de 40%, inclusive o NCM 8714.1.
        base.update({
            "status": "ANTECIPAÇÃO TRIBUTÁRIA/RN IDENTIFICADA PARA AUTOPEÇAS — NÃO TRATAR COMO ST DO REMETENTE",
            "aplica_st": False,
            "decisao_confirmada": True,
            "confiabilidade": 100.0,
            "mva_original": None,
            "mva_ajustada": None,
            "mva_aplicada": None,
            "mva_tipo": "",
            "st_modelo_calculo": "ANTECIPAÇÃO ICMS/RN — ANEXO 005",
            "antecipacao_percentual": 40.0,
            "antecipacao_status": "PERCENTUAL DE AGREGAÇÃO 40% — ANTECIPAÇÃO PELO DESTINATÁRIO/ADQUIRENTE NO RN",
            "contrato_fidelidade": contrato_fidelidade,
            "vigencia_inicio": "2022-08-19",
            "vigencia_fim": "",
            "responsabilidade": "DESTINATÁRIO/ADQUIRENTE NO RN — ANTECIPAÇÃO NA ENTRADA, CONFORME REGRA LOCAL",
            "acordo_status": "RN NÃO É DESTINO DO PROTOCOLO ICMS 41/08 VIGENTE — SEM ST AUTOMÁTICA DO REMETENTE MG",
            "fundamento": (
                "RICMS/RN, Decreto nº 31.825/2022, Anexo 005, art. 1º, III (percentual de agregação de 40%); "
                "NCM 8714.1 incluído na relação de peças e acessórios automotivos; Protocolo ICMS 41/08, cláusula primeira vigente."
            ),
            "fonte": f"{URL_RN_ANEXO_005} | {URL_CONFAZ_PROTOCOLO_41}",
            "observacao": (
                "Autopeças no RN são tratadas nesta cobertura como antecipação tributária na entrada, e não como "
                "retenção automática de ICMS-ST pelo remetente de MG. O Anexo 005 inclui NCM 8714.1 no grupo de "
                "agregação de 40%. Confirmar situação cadastral, benefícios e hipóteses de dispensa do destinatário antes do recolhimento."
            ),
        })
        return base

    @classmethod
    def _se(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a cobertura atual de Sergipe para autopeças e pneumáticos.

        A alíquota interna modal é 19%, porém o RICMS/SE determina que a MVA
        ajustada considere ICMS + FECOEP. Para o escopo automotivo estruturado,
        o FECOEP é 1%, logo a fórmula/tabela de ajuste usa 20%.
        """
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_SE.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA SE ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "SE" else regra["ajustada"].get(inter)
            aplicada = original if origem == "SE" else ajustada
            excecao_convenio = cest in {"16.005.00", "16.006.00", "16.007.01", "16.009.00"}
            if origem != "SE" and excecao_convenio:
                base.update({
                    "status": "PNEUMÁTICO/SE COM CEST EXCEPCIONADO DO CONVÊNIO 102/17 — REVISAR",
                    "aplica_st": False,
                    "decisao_confirmada": False,
                    "confiabilidade": 80.0,
                    "mva_original": original,
                    "mva_ajustada": ajustada,
                    "mva_aplicada": aplicada,
                    "mva_tipo": "MVA OFICIAL SE — RESPONSABILIDADE INTERESTADUAL EM REVISÃO",
                    "responsabilidade": "DESTINATÁRIO SE / REGRA LOCAL — CONFIRMAR RESPONSABILIDADE",
                    "acordo_status": "CEST EXCEPCIONADO PELO CONVÊNIO ICMS 102/17",
                    "fundamento": "RICMS/SE, arts. 681 e 684, § 4º-D-B e § 4º-E, XII; Convênio ICMS 102/17.",
                    "fonte": f"{URL_SE_RICMS} | {URL_CONFAZ_CONVENIO_102}",
                })
                return base

            base.update({
                "status": "ICMS-ST/SE CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "SE" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "SE" or ajustada is not None) else 80.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA INTERESTADUAL OFICIAL SE — ICMS + FECOEP" if ajustada is not None else "MVA ORIGINAL SE",
                "st_modelo_calculo": "ICMS-ST/SE — MVA AJUSTADA COM ICMS + FECOEP",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2024-08-02",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17"
                    if origem != "SE" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "PNEUMÁTICOS/SE — RICMS/SE + CONVÊNIO ICMS 102/17",
                "fundamento": (
                    "RICMS/SE, Decreto nº 21.400/2002, art. 681, III; art. 684, § 4º-D-B e § 4º-E, XII; "
                    "Convênio ICMS 102/17. Para a MVA ajustada, a alíquota interna considera ICMS + FECOEP."
                ),
                "fonte": f"{URL_SE_RICMS} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA original de {original:.2f}%. "
                    + (
                        f"Na operação interestadual a {inter:.2f}%, a MVA ajustada é {float(aplicada):.2f}%, "
                        "considerando 19% de ICMS + 1% de FECOEP como alíquota interna para o ajuste."
                        if aplicada is not None and origem != "SE" else
                        "Na operação interna aplica-se a MVA original de Sergipe."
                    )
                ),
            })
            if origem != "SE" and ajustada is None:
                base.update({
                    "status": "ST/SE DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        if "AUTOPE" not in segmento:
            return base

        chave = "fidelidade" if contrato_fidelidade else "demais"
        regra = MVA_AUTOPECAS_SE[chave]
        original = float(regra["original"])
        ajustada = None if origem == "SE" else regra["ajustada"].get(inter)
        aplicada = original if origem == "SE" else ajustada
        origem_signataria = origem in SIGNATARIOS_PROTOCOLO_97
        fidelidade_obs = (
            "Foi informada fidelidade/exclusividade. Confirmar o enquadramento integral nos requisitos do art. 684, § 4º-E, X. "
            if contrato_fidelidade else
            "Sem fidelidade/exclusividade qualificada informada, foi usada a MVA de 71,78% dos demais casos. "
        )

        if origem == "SE" or origem_signataria:
            base.update({
                "status": (
                    "ICMS-ST/SE CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL"
                    if contrato_fidelidade else "ICMS-ST/SE CONFIRMADO PARA AUTOPEÇAS"
                ),
                "aplica_st": True,
                "decisao_confirmada": origem == "SE" or ajustada is not None,
                "confiabilidade": 95.0 if contrato_fidelidade else 100.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA INTERESTADUAL OFICIAL SE — ICMS + FECOEP" if ajustada is not None else "MVA ORIGINAL SE",
                "st_modelo_calculo": "ICMS-ST/SE — TABELA VI DO ANEXO IX",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2024-08-02",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — PROTOCOLO ICMS 97/10"
                    if origem != "SE" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "AUTOPEÇAS/SE — PROTOCOLO ICMS 97/10 + TABELA VI DO ANEXO IX",
                "fundamento": (
                    "RICMS/SE, arts. 681 e 684, § 4º-D-B e § 4º-E, X, Tabela VI do Anexo IX; "
                    "Protocolo ICMS 97/10."
                ),
                "fonte": f"{URL_SE_RICMS} | {URL_CONFAZ_PROTOCOLO_97}",
                "observacao": (
                    f"Autopeças/SE: MVA original de {original:.2f}%. "
                    + (f"Para alíquota interestadual de {inter:.2f}%, a Tabela VI traz {float(aplicada):.2f}%. " if aplicada is not None and origem != "SE" else "")
                    + fidelidade_obs
                    + "No ajuste, o RICMS/SE considera ICMS + FECOEP como alíquota interna."
                ),
            })
            if origem != "SE" and ajustada is None:
                base.update({
                    "status": "ST/SE DE AUTOPEÇAS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        # MG→SE: MG não é signatário do Protocolo 97/10. O RICMS/SE, art. 784,
        # II, d, prevê antecipação quando a mercadoria sujeita à ST vem de UF
        # não signatária. O motor preserva a MVA oficial, mas não força ST na NF de MG.
        base.update({
            "status": "REGIME ST/SE DE AUTOPEÇAS IDENTIFICADO — ANTECIPAÇÃO PELO DESTINATÁRIO; RETENÇÃO MG NÃO AUTOMÁTICA",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 98.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA OFICIAL SE — ANTECIPAÇÃO/RESPONSABILIDADE A CONFIRMAR",
            "st_modelo_calculo": "ANTECIPAÇÃO ICMS/SE — ART. 784, II, d",
            "contrato_fidelidade": contrato_fidelidade,
            "vigencia_inicio": "2024-08-02",
            "vigencia_fim": "",
            "responsabilidade": "DESTINATÁRIO SE — ANTECIPAÇÃO NA ENTRADA (RICMS/SE, ART. 784, II, d); REMETENTE MG NÃO SIGNATÁRIO",
            "acordo_status": f"PROTOCOLO ICMS 97/10 NÃO ATRIBUI RESPONSABILIDADE AUTOMÁTICA À ORIGEM {origem}",
            "fundamento": (
                "RICMS/SE, Decreto nº 21.400/2002, arts. 681, 684, § 4º-D-B e § 4º-E, X, "
                "Tabela VI do Anexo IX, e art. 784, II, d; Protocolo ICMS 97/10."
            ),
            "fonte": f"{URL_SE_RICMS} | {URL_CONFAZ_PROTOCOLO_97}",
            "observacao": (
                f"Autopeças/SE: MVA original de {original:.2f}% e, para alíquota interestadual de {inter:.2f}%, "
                + (f"MVA oficial de {float(aplicada):.2f}%. " if aplicada is not None else "MVA interestadual ainda não definida. ")
                + f"A origem {origem} não integra o Protocolo 97/10; portanto o FiscalPro não sugere retenção ST/CFOP 6403 automaticamente. "
                + "O RICMS/SE prevê antecipação na entrada de mercadoria sujeita à ST oriunda de UF não signatária. "
                + fidelidade_obs
                + "A MVA ajustada considera 19% de ICMS + 1% de FECOEP."
            ),
        })
        return base

    @classmethod
    def _pi(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a cobertura estruturada de autopeças e pneumáticos do Piauí."""
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_PI.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA PI ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "PI" else regra["ajustada"].get(inter)
            aplicada = original if origem == "PI" else ajustada
            excecao_convenio = cest in {"16.006.00"}
            if origem != "PI" and excecao_convenio:
                base.update({
                    "status": "PNEUMÁTICO/PI COM RESPONSABILIDADE INTERESTADUAL A REVISAR",
                    "aplica_st": False,
                    "decisao_confirmada": False,
                    "confiabilidade": 80.0,
                    "mva_original": original,
                    "mva_ajustada": ajustada,
                    "mva_aplicada": aplicada,
                    "mva_tipo": "MVA PI — RESPONSABILIDADE INTERESTADUAL EM REVISÃO",
                    "responsabilidade": "DESTINATÁRIO PI / REGRA LOCAL — CONFIRMAR RESPONSABILIDADE",
                    "acordo_status": "CEST FORA DO NÚCLEO PRINCIPAL DO CONVÊNIO 102/17",
                    "fundamento": "RICMS/PI, Anexo X, arts. 75-76; Convênio ICMS 102/17.",
                    "fonte": f"{URL_PI_RICMS} | {URL_CONFAZ_CONVENIO_102}",
                })
                return base

            base.update({
                "status": "ICMS-ST/PI CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "PI" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "PI" or ajustada is not None) else 80.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA PI — ALÍQUOTA INTERNA 22,5%" if ajustada is not None else "MVA ORIGINAL PI",
                "st_modelo_calculo": "ICMS-ST/PI — PNEUMÁTICOS — CONVÊNIO 102/17",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2025-04-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17"
                    if origem != "PI" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "PNEUMÁTICOS/PI — RICMS/PI + CONVÊNIO ICMS 102/17",
                "fundamento": "RICMS/PI, Anexo X, arts. 75-76; Convênio ICMS 102/17; MVA ajustada pela fórmula legal.",
                "fonte": f"{URL_PI_RICMS} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA original de {original:.2f}%. "
                    + (
                        f"Para alíquota interestadual de {inter:.2f}% e interna PI de 22,5%, a MVA ajustada é {float(aplicada):.2f}%."
                        if aplicada is not None and origem != "PI" else
                        "Na operação interna aplica-se a MVA original."
                    )
                ),
            })
            if origem != "PI" and ajustada is None:
                base.update({
                    "status": "ST/PI DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        if "AUTOPE" not in segmento:
            return base

        if origem != "PI" and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            base.update({
                "status": "AUTOPEÇA/PI COM CEST EXCLUÍDO DO PROTOCOLO 41/08 — REVISAR RESPONSABILIDADE",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 85.0,
                "responsabilidade": "DESTINATÁRIO PI / REGRA LOCAL — CEST EXCLUÍDO DO PROTOCOLO 41/08",
                "acordo_status": "CEST EXPRESSAMENTE EXCLUÍDO DO CAPUT VIGENTE DO PROTOCOLO 41/08",
                "fundamento": "RICMS/PI, Anexo X, arts. 93-94; Protocolo ICMS 41/08.",
                "fonte": f"{URL_PI_RICMS} | {URL_CONFAZ_PROTOCOLO_41}",
            })
            return base

        chave = "fidelidade" if contrato_fidelidade else "demais"
        regra = MVA_AUTOPECAS_PI[chave]
        original = float(regra["original"])
        ajustada = None if origem == "PI" else regra["ajustada"].get(inter)
        aplicada = original if origem == "PI" else ajustada
        origem_signataria = origem in SIGNATARIOS_PROTOCOLO_41 or origem in SIGNATARIOS_PROTOCOLO_97
        fidelidade_obs = (
            "Foi informada fidelidade/exclusividade: usar 26,50% somente após confirmar os requisitos do art. 94; "
            "na hipótese de distribuição exclusiva agrícola/rodoviária, a autorização prévia do fisco do PI é exigida. "
            if contrato_fidelidade else
            "Sem fidelidade/exclusividade qualificada informada, foi usada a MVA original de 40,00% dos demais casos. "
        )
        regime_especial_obs = (
            "Regime especial/credenciamento de atacadista de peças para motocicletas pode alterar a carga; "
            "não é aplicado automaticamente sem comprovação do credenciamento. "
        )

        if origem == "PI" or origem_signataria:
            base.update({
                "status": (
                    "ICMS-ST/PI CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL"
                    if contrato_fidelidade else "ICMS-ST/PI CONFIRMADO PARA AUTOPEÇAS"
                ),
                "aplica_st": True,
                "decisao_confirmada": origem == "PI" or ajustada is not None,
                "confiabilidade": 93.0 if contrato_fidelidade else 98.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA PI — ALÍQUOTA INTERNA 22,5%" if ajustada is not None else "MVA ORIGINAL PI",
                "st_modelo_calculo": "ICMS-ST/PI — AUTOPEÇAS — RICMS/PI + PROTOCOLO 41/08",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2025-04-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — RICMS/PI + PROTOCOLO 41/08"
                    if origem != "PI" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "AUTOPEÇAS/PI — ANEXO X, ARTS. 93-94 + PROTOCOLOS 41/08 E 97/10",
                "fundamento": (
                    "RICMS/PI, Anexo X, arts. 93-94; Protocolo ICMS 41/08; Decreto PI nº 24.244/2025; "
                    "MVA ajustada pela fórmula legal."
                ),
                "fonte": f"{URL_PI_RICMS} | {URL_PI_DECRETO_24244} | {URL_CONFAZ_PROTOCOLO_41}",
                "observacao": (
                    f"Autopeças/PI: MVA original de {original:.2f}%. "
                    + (
                        f"Na operação interestadual a {inter:.2f}% e interna PI de 22,5%, a MVA ajustada é {float(aplicada):.2f}%. "
                        if aplicada is not None and origem != "PI" else
                        "Na operação interna aplica-se a MVA original. "
                    )
                    + fidelidade_obs + regime_especial_obs
                    + "O art. 93 do Anexo X atribui em regra a retenção ao remetente nas operações entre PI e UFs signatárias dos Protocolos 41/08/97/10, ressalvadas as exceções legais."
                ),
            })
            if origem != "PI" and ajustada is None:
                base.update({
                    "status": "ST/PI DE AUTOPEÇAS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        base.update({
            "status": "REGIME ST/PI DE AUTOPEÇAS IDENTIFICADO — ORIGEM FORA DOS PROTOCOLOS APLICÁVEIS",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 90.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA PI — RESPONSABILIDADE A CONFIRMAR",
            "responsabilidade": "DESTINATÁRIO PI / REGRA LOCAL — REMETENTE NÃO ALCANÇADO PELO ACORDO",
            "acordo_status": f"PROTOCOLOS 41/08/97/10 NÃO ATRIBUEM RESPONSABILIDADE AUTOMÁTICA À ORIGEM {origem}",
            "fundamento": "RICMS/PI, Anexo X, arts. 93-94; Protocolos ICMS 41/08 e 97/10.",
            "fonte": f"{URL_PI_RICMS} | {URL_CONFAZ_PROTOCOLO_41} | {URL_CONFAZ_PROTOCOLO_97}",
        })
        return base

    @classmethod
    def _to(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica cobertura conservadora do Tocantins para autopeças e pneumáticos."""
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_TO.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA TO ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "TO" else regra["ajustada"].get(inter)
            aplicada = original if origem == "TO" else ajustada
            base.update({
                "status": "ICMS-ST/TO CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "TO" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "TO" or ajustada is not None) else 80.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA TO — ALÍQUOTA INTERNA 20%" if ajustada is not None else "MVA ORIGINAL TO",
                "st_modelo_calculo": "ICMS-ST/TO — PNEUMÁTICOS — CONVÊNIO 102/17",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2023-04-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17"
                    if origem != "TO" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "PNEUMÁTICOS/TO — ANEXO XXI + CONVÊNIO ICMS 102/17",
                "fundamento": (
                    "Lei TO nº 1.201/2000, art. 3º-D, confirma pneumáticos no Anexo XXI do RICMS/TO; "
                    "Convênio ICMS 102/17; MVA ajustada pela fórmula legal."
                ),
                "fonte": f"{URL_TO_LEI_1201} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA original de {original:.2f}%. "
                    + (
                        f"Para alíquota interestadual de {inter:.2f}% e interna TO de 20%, a MVA ajustada é {float(aplicada):.2f}%."
                        if aplicada is not None and origem != "TO" else
                        "Na operação interna aplica-se a MVA original."
                    )
                    + " Benefício/regime especial da Lei TO nº 1.201/2000 não é presumido pelo motor."
                ),
            })
            if origem != "TO" and ajustada is None:
                base.update({
                    "status": "ST/TO DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        if "AUTOPE" not in segmento:
            return base

        chave = "fidelidade" if contrato_fidelidade else "demais"
        regra = MVA_AUTOPECAS_TO[chave]
        original = float(regra["original"])
        ajustada = None if origem == "TO" else regra["ajustada"].get(inter)
        aplicada = original if origem == "TO" else ajustada
        fidelidade_obs = (
            "Foi informada fidelidade/exclusividade: usar 36,56% somente após confirmar os requisitos do Protocolo 97/10 e eventual autorização fiscal. "
            if contrato_fidelidade else
            "Sem fidelidade/exclusividade qualificada informada, foi usada a MVA original de 71,78% dos demais casos. "
        )
        especial_obs = (
            "A Lei TO nº 1.201/2000 prevê tratamento de beneficiário que pode alterar a responsabilidade por ST; "
            "o FiscalPro não presume esse enquadramento sem comprovação. "
        )
        origem_signataria = origem in SIGNATARIOS_PROTOCOLO_97
        if origem == "TO" or origem_signataria:
            base.update({
                "status": (
                    "ICMS-ST/TO CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL"
                    if contrato_fidelidade else "ICMS-ST/TO CONFIRMADO PARA AUTOPEÇAS"
                ),
                "aplica_st": True,
                "decisao_confirmada": origem == "TO" or ajustada is not None,
                "confiabilidade": 93.0 if contrato_fidelidade else 98.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA TO — ALÍQUOTA INTERNA 20%" if ajustada is not None else "MVA ORIGINAL TO",
                "st_modelo_calculo": "ICMS-ST/TO — AUTOPEÇAS — PROTOCOLO 97/10 / ANEXO XXI",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2023-04-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — PROTOCOLO ICMS 97/10"
                    if origem != "TO" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "AUTOPEÇAS/TO — ANEXO XXI + PROTOCOLO ICMS 97/10",
                "fundamento": "Protocolo ICMS 97/10; Lei TO nº 1.201/2000, art. 3º-D; MVA ajustada pela fórmula legal.",
                "fonte": f"{URL_TO_LEI_1201} | {URL_CONFAZ_PROTOCOLO_97}",
                "observacao": (
                    f"Autopeças/TO: MVA original de {original:.2f}%. "
                    + (f"Na operação interestadual a {inter:.2f}% e interna TO de 20%, a MVA ajustada é {float(aplicada):.2f}%. " if aplicada is not None and origem != "TO" else "Na operação interna aplica-se a MVA original. ")
                    + fidelidade_obs + especial_obs
                ),
            })
            return base

        # MG não integra o Protocolo 97/10: a sujeição interna e a MVA são conhecidas,
        # mas não se atribui automaticamente a retenção ao remetente mineiro.
        base.update({
            "status": "REGIME ST/TO DE AUTOPEÇAS IDENTIFICADO — RETENÇÃO PELO REMETENTE MG NÃO AUTOMÁTICA",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 98.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA OFICIAL TO — RESPONSABILIDADE/ANTECIPAÇÃO A CONFIRMAR",
            "st_modelo_calculo": "ICMS-ST/TO — AUTOPEÇAS — PROTOCOLO 97/10 / ANEXO XXI",
            "contrato_fidelidade": contrato_fidelidade,
            "vigencia_inicio": "2023-04-01",
            "vigencia_fim": "",
            "responsabilidade": "DESTINATÁRIO TO / REGRA LOCAL — REMETENTE MG NÃO SIGNATÁRIO DO PROTOCOLO 97/10",
            "acordo_status": f"PROTOCOLO ICMS 97/10 NÃO ATRIBUI RESPONSABILIDADE AUTOMÁTICA À ORIGEM {origem}",
            "fundamento": "Protocolo ICMS 97/10; Lei TO nº 1.201/2000, art. 3º-D; Anexo XXI do RICMS/TO.",
            "fonte": f"{URL_TO_LEI_1201} | {URL_CONFAZ_PROTOCOLO_97}",
            "observacao": (
                f"Autopeças/TO: MVA original de {original:.2f}%"
                + (f" e MVA ajustada de {float(aplicada):.2f}% para alíquota interestadual de {inter:.2f}%. " if aplicada is not None else ". ")
                + f"A origem {origem} não integra o Protocolo 97/10; por isso o FiscalPro não sugere retenção ST/CFOP 6403 automaticamente. "
                + fidelidade_obs + especial_obs
            ),
        })
        return base

    @classmethod
    def _ac(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a tabela oficial acreana para autopeças e pneumáticos."""
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_AC.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA AC ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "AC" else regra["ajustada"].get(inter)
            aplicada = original if origem == "AC" else ajustada
            base.update({
                "status": "ICMS-ST/AC CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "AC" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "AC" or ajustada is not None) else 80.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA OFICIAL AC" if ajustada is not None else "MVA ORIGINAL AC",
                "st_modelo_calculo": "ICMS-ST/AC — PNEUMÁTICOS — IN DIAT 01/2023 / CONVÊNIO 102/17",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2023-04-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17"
                    if origem != "AC" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "PNEUMÁTICOS/AC — IN DIAT 01/2023 + CONVÊNIO ICMS 102/17",
                "fundamento": "IN DIAT/SEFAZ-AC nº 1/2023, Anexo I, segmento 16; Convênio ICMS 102/17.",
                "fonte": f"{URL_AC_IN_DIAT_01_2023} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA original de {original:.2f}%. "
                    + (
                        f"Para alíquota interestadual de {inter:.2f}% e interna AC de 19%, "
                        f"a tabela oficial traz MVA ajustada de {float(aplicada):.2f}%."
                        if aplicada is not None and origem != "AC" else
                        "Na operação interna aplica-se a MVA original."
                    )
                ),
            })
            if origem != "AC" and ajustada is None:
                base.update({
                    "status": "ST/AC DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        if "AUTOPE" not in segmento:
            return base
        if origem != "AC" and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            base.update({
                "status": "AUTOPEÇA/AC COM CEST EXCLUÍDO DO PROTOCOLO 41/08 — REVISAR RESPONSABILIDADE",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 85.0,
                "responsabilidade": "DESTINATÁRIO AC / REGRA LOCAL — CEST EXCLUÍDO DO PROTOCOLO 41/08",
                "acordo_status": "CEST EXPRESSAMENTE EXCLUÍDO DO CAPUT VIGENTE DO PROTOCOLO 41/08",
                "fundamento": "IN DIAT/SEFAZ-AC nº 1/2023; Protocolo ICMS 41/08.",
                "fonte": f"{URL_AC_IN_DIAT_01_2023} | {URL_AC_PROTOCOLO_41}",
            })
            return base

        chave = "fidelidade" if contrato_fidelidade else "demais"
        regra = MVA_AUTOPECAS_AC[chave]
        original = float(regra["original"])
        ajustada = None if origem == "AC" else regra["ajustada"].get(inter)
        aplicada = original if origem == "AC" else ajustada
        origem_signataria = origem in SIGNATARIOS_PROTOCOLO_41
        fidelidade_obs = (
            "Foi informada fidelidade/exclusividade; confirmar integralmente os requisitos legais antes de usar a MVA reduzida. "
            if contrato_fidelidade else
            "Sem fidelidade/exclusividade qualificada informada, foi usada a MVA de 71,78% dos demais casos. "
        )
        if origem == "AC" or origem_signataria:
            base.update({
                "status": (
                    "ICMS-ST/AC CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL"
                    if contrato_fidelidade else "ICMS-ST/AC CONFIRMADO PARA AUTOPEÇAS"
                ),
                "aplica_st": True,
                "decisao_confirmada": origem == "AC" or ajustada is not None,
                "confiabilidade": 95.0 if contrato_fidelidade else 100.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA OFICIAL AC" if ajustada is not None else "MVA ORIGINAL AC",
                "st_modelo_calculo": "ICMS-ST/AC — AUTOPEÇAS — IN DIAT 01/2023 / PROTOCOLO 41/08",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2023-04-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — PROTOCOLO ICMS 41/08"
                    if origem != "AC" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "AUTOPEÇAS/AC — IN DIAT 01/2023 + PROTOCOLO ICMS 41/08",
                "fundamento": "IN DIAT/SEFAZ-AC nº 1/2023, Anexo I, segmento 1; Protocolo ICMS 41/08.",
                "fonte": f"{URL_AC_IN_DIAT_01_2023} | {URL_AC_PROTOCOLO_41}",
                "observacao": (
                    f"Autopeças/AC: MVA original de {original:.2f}%. "
                    + (
                        f"Na operação interestadual a {inter:.2f}% e interna AC de 19%, "
                        f"a tabela oficial traz MVA ajustada de {float(aplicada):.2f}%. "
                        if aplicada is not None and origem != "AC" else
                        "Na operação interna aplica-se a MVA original. "
                    )
                    + fidelidade_obs
                    + "MG e AC integram o Protocolo 41/08, ressalvadas as exceções do acordo e a situação concreta do destinatário."
                ),
            })
            return base

        base.update({
            "status": "REGIME ST/AC DE AUTOPEÇAS IDENTIFICADO — ORIGEM FORA DO PROTOCOLO 41/08",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 92.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA OFICIAL AC — RESPONSABILIDADE A CONFIRMAR",
            "responsabilidade": "DESTINATÁRIO AC / REGRA LOCAL — REMETENTE NÃO ALCANÇADO PELO PROTOCOLO 41/08",
            "acordo_status": f"PROTOCOLO 41/08 NÃO ATRIBUI RESPONSABILIDADE AUTOMÁTICA À ORIGEM {origem}",
            "fundamento": "IN DIAT/SEFAZ-AC nº 1/2023; Protocolo ICMS 41/08.",
            "fonte": f"{URL_AC_IN_DIAT_01_2023} | {URL_AC_PROTOCOLO_41}",
        })
        return base

    @classmethod
    def _am(
        cls, base: Dict[str, Any], origem: str,
        aliquota_inter: Optional[float], contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a Lei AM 6.108/2022 a autopeças e pneumáticos."""
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)
        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_AM.get(cest)
            if regra is None:
                base.update({"status": "PNEUMÁTICO FORA DA TABELA AM ESTRUTURADA", "decisao_confirmada": False, "confiabilidade": 45.0})
                return base
            original = float(regra["original"])
            ajustada = None if origem == "AM" else regra["ajustada"].get(inter)
            aplicada = original if origem == "AM" else ajustada
            base.update({
                "status": "ICMS-ST/AM CONFIRMADO PARA PNEUMÁTICOS", "aplica_st": True,
                "decisao_confirmada": origem == "AM" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "AM" or ajustada is not None) else 80.0,
                "mva_original": original, "mva_ajustada": ajustada, "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA OFICIAL AM" if ajustada is not None else "MVA ORIGINAL AM",
                "st_modelo_calculo": "ICMS-ST/AM — PNEUMÁTICOS — LEI 6.108/2022 / CONVÊNIO 102/17",
                "contrato_fidelidade": contrato_fidelidade, "vigencia_inicio": "2023-01-01", "vigencia_fim": "",
                "responsabilidade": "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17" if origem != "AM" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA",
                "acordo_status": "PNEUMÁTICOS/AM — LEI 6.108/2022 + CONVÊNIO ICMS 102/17",
                "fundamento": "Lei AM nº 6.108/2022, Anexo XVI; Convênio ICMS 102/17.",
                "fonte": f"{URL_AM_LEI_6108} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": f"CEST {cest}: MVA original {original:.2f}%; na operação a {inter:.2f}% para alíquota interna AM de 20%, MVA ajustada {aplicada:.2f}%." if aplicada is not None and origem != "AM" else f"CEST {cest}: MVA original {original:.2f}%.",
            })
            return base
        if "AUTOPE" not in segmento:
            return base
        if origem != "AM" and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            base.update({
                "status": "AUTOPEÇA/AM COM CEST EXCLUÍDO DO PROTOCOLO 41/08 — REVISAR RESPONSABILIDADE",
                "aplica_st": False, "decisao_confirmada": False, "confiabilidade": 85.0,
                "responsabilidade": "DESTINATÁRIO AM / REGRA LOCAL", "acordo_status": "CEST EXCLUÍDO DO PROTOCOLO 41/08",
                "fundamento": "Lei AM nº 6.108/2022; Protocolo ICMS 41/08.",
                "fonte": f"{URL_AM_LEI_6108} | {URL_CONFAZ_PROTOCOLO_41}",
            })
            return base
        chave = "fidelidade" if contrato_fidelidade else "demais"
        regra = MVA_AUTOPECAS_AM[chave]
        original = float(regra["original"])
        ajustada = None if origem == "AM" else regra["ajustada"].get(inter)
        aplicada = original if origem == "AM" else ajustada
        signataria = origem in SIGNATARIOS_PROTOCOLO_41
        if origem == "AM" or signataria:
            base.update({
                "status": "ICMS-ST/AM CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL" if contrato_fidelidade else "ICMS-ST/AM CONFIRMADO PARA AUTOPEÇAS",
                "aplica_st": True, "decisao_confirmada": origem == "AM" or ajustada is not None,
                "confiabilidade": 95.0 if contrato_fidelidade else 100.0,
                "mva_original": original, "mva_ajustada": ajustada, "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA OFICIAL AM" if ajustada is not None else "MVA ORIGINAL AM",
                "st_modelo_calculo": "ICMS-ST/AM — AUTOPEÇAS — LEI 6.108/2022 / PROTOCOLO 41/08",
                "contrato_fidelidade": contrato_fidelidade, "vigencia_inicio": "2023-01-01", "vigencia_fim": "",
                "responsabilidade": "REMETENTE/SUBSTITUTO — PROTOCOLO ICMS 41/08" if origem != "AM" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA",
                "acordo_status": "AUTOPEÇAS/AM — LEI 6.108/2022 + PROTOCOLO ICMS 41/08",
                "fundamento": "Lei AM nº 6.108/2022, Anexo III; Protocolo ICMS 41/08.",
                "fonte": f"{URL_AM_LEI_6108} | {URL_CONFAZ_PROTOCOLO_41}",
                "observacao": (
                    (f"Autopeças/AM: MVA original {original:.2f}%; MG→AM a {inter:.2f}% e interna de 20% resulta em {aplicada:.2f}%." if aplicada is not None and origem != "AM" else f"Autopeças/AM: MVA original {original:.2f}%.")
                    + (" Hipótese de fidelidade/exclusividade informada; confirmar os requisitos legais antes de aplicar a MVA reduzida." if contrato_fidelidade else "")
                ),
            })
            return base
        base.update({
            "status": "REGIME ST/AM DE AUTOPEÇAS IDENTIFICADO — ORIGEM FORA DO PROTOCOLO 41/08",
            "aplica_st": False, "decisao_confirmada": False, "confiabilidade": 92.0,
            "mva_original": original, "mva_ajustada": ajustada, "mva_aplicada": aplicada,
            "responsabilidade": "DESTINATÁRIO AM / REGRA LOCAL", "fundamento": "Lei AM nº 6.108/2022; Protocolo ICMS 41/08.",
            "fonte": f"{URL_AM_LEI_6108} | {URL_CONFAZ_PROTOCOLO_41}",
        })
        return base

    @classmethod
    def _ap(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_AP.get(cest)
            if regra is None:
                base.update({"status": "PNEUMÁTICO FORA DA TABELA AP ESTRUTURADA", "decisao_confirmada": False, "confiabilidade": 45.0})
                return base
            original = float(regra["original"])
            ajustada = None if origem == "AP" else regra["ajustada"].get(inter)
            aplicada = original if origem == "AP" else ajustada
            base.update({
                "status": "ICMS-ST/AP CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "AP" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "AP" or ajustada is not None) else 80.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA AP — ALÍQUOTA INTERNA 18%" if ajustada is not None else "MVA ORIGINAL AP",
                "st_modelo_calculo": "ICMS-ST/AP — PNEUMÁTICOS — CONVÊNIO 102/17",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2018-01-01",
                "vigencia_fim": "",
                "responsabilidade": "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17" if origem != "AP" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA",
                "acordo_status": "PNEUMÁTICOS/AP — RICMS/AP + CONVÊNIO ICMS 102/17",
                "fundamento": "RICMS/AP; Convênio ICMS 102/17.",
                "fonte": f"{URL_AP_RICMS} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": f"CEST {cest}: MVA original de {original:.2f}% e MVA ajustada conforme alíquota interestadual e interna AP de 18%.",
            })
            return base

        if "AUTOPE" not in segmento:
            return base
        if origem != "AP" and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            base.update({
                "status": "AUTOPEÇA/AP COM CEST EXCLUÍDO DO PROTOCOLO 41/08 — REVISAR RESPONSABILIDADE",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 85.0,
                "responsabilidade": "DESTINATÁRIO AP / REGRA LOCAL — CEST EXCLUÍDO DO PROTOCOLO 41/08",
                "acordo_status": "CEST EXPRESSAMENTE EXCLUÍDO DO PROTOCOLO 41/08",
                "fundamento": "RICMS/AP; Protocolo ICMS 41/08.",
                "fonte": f"{URL_AP_RICMS} | {URL_AP_PROTOCOLO_41}",
            })
            return base
        chave = "fidelidade" if contrato_fidelidade else "demais"
        regra = MVA_AUTOPECAS_AP[chave]
        original = float(regra["original"])
        ajustada = None if origem == "AP" else regra["ajustada"].get(inter)
        aplicada = original if origem == "AP" else ajustada
        origem_signataria = origem in SIGNATARIOS_PROTOCOLO_41
        fidelidade_obs = (
            "Foi informada fidelidade/exclusividade; confirmar os requisitos legais antes de usar a MVA reduzida. "
            if contrato_fidelidade else
            "Sem fidelidade/exclusividade qualificada, foi usada a MVA de 71,78% dos demais casos. "
        )
        if origem == "AP" or origem_signataria:
            base.update({
                "status": "ICMS-ST/AP CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL" if contrato_fidelidade else "ICMS-ST/AP CONFIRMADO PARA AUTOPEÇAS",
                "aplica_st": True,
                "decisao_confirmada": origem == "AP" or ajustada is not None,
                "confiabilidade": 95.0 if contrato_fidelidade else 100.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA AP — ALÍQUOTA INTERNA 18%" if ajustada is not None else "MVA ORIGINAL AP",
                "st_modelo_calculo": "ICMS-ST/AP — AUTOPEÇAS — PROTOCOLO 41/08",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2016-07-01",
                "vigencia_fim": "",
                "responsabilidade": "REMETENTE/SUBSTITUTO — PROTOCOLO ICMS 41/08" if origem != "AP" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA",
                "acordo_status": "AUTOPEÇAS/AP — RICMS/AP + PROTOCOLO 41/08",
                "fundamento": "RICMS/AP; Protocolo ICMS 41/08.",
                "fonte": f"{URL_AP_RICMS} | {URL_AP_PROTOCOLO_41}",
                "observacao": f"Autopeças/AP: MVA original de {original:.2f}%. " + (f"Na operação interestadual a {inter:.2f}%, MVA ajustada de {float(aplicada):.2f}%. " if aplicada is not None and origem != "AP" else "Na operação interna aplica-se a MVA original. ") + fidelidade_obs,
            })
            return base
        base.update({
            "status": "REGIME ST/AP DE AUTOPEÇAS IDENTIFICADO — ORIGEM FORA DO PROTOCOLO 41/08",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 92.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA AP — RESPONSABILIDADE A CONFIRMAR",
            "responsabilidade": "DESTINATÁRIO AP / REGRA LOCAL",
            "fundamento": "RICMS/AP; Protocolo ICMS 41/08.",
            "fonte": f"{URL_AP_RICMS} | {URL_AP_PROTOCOLO_41}",
        })
        return base

    @classmethod
    def _ro(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_RO.get(cest)
            if regra is None:
                base.update({"status": "PNEUMÁTICO FORA DA TABELA RO VALIDADA", "decisao_confirmada": False, "confiabilidade": 50.0})
                return base
            original = float(regra["original"])
            ajustada = None if origem == "RO" else regra["ajustada"].get(inter)
            aplicada = original if origem == "RO" else ajustada
            base.update({
                "status": "ICMS-ST/RO CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "RO" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "RO" or ajustada is not None) else 80.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA RO — ALÍQUOTA INTERNA 19,5%" if ajustada is not None else "MVA ORIGINAL RO",
                "st_modelo_calculo": "ICMS-ST/RO — PNEUMÁTICOS — CONVÊNIO 102/17",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2024-01-12",
                "vigencia_fim": "",
                "responsabilidade": "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17" if origem != "RO" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA",
                "acordo_status": "PNEUMÁTICOS/RO — DECRETO 29.048/2024 + CONVÊNIO 102/17",
                "fundamento": "Decreto RO nº 29.048/2024, Tabela XVI; Convênio ICMS 102/17.",
                "fonte": URL_RO_DECRETO_29048,
                "observacao": f"Pneumáticos/RO CEST {cest}: MVA original de {original:.2f}% e MVA ajustada conforme a tabela estadual.",
            })
            return base

        if "AUTOPE" not in segmento:
            return base
        if cest != "01.076.00":
            base.update({
                "status": "AUTOPEÇA/RO FORA DO CEST DE MOTOCICLETAS VALIDADO — REVISAR TABELA II",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 60.0,
                "st_modelo_calculo": "ICMS-ST/RO — AUTOPEÇAS — TABELA II",
                "responsabilidade": "DESTINATÁRIO RO / REGRA LOCAL — MVA ESPECÍFICA DO CEST A CONFIRMAR",
                "fundamento": "Decreto RO nº 29.048/2024, Tabela II.",
                "fonte": URL_RO_DECRETO_29048,
            })
            return base
        regra = MVA_AUTOPECAS_RO["demais"]
        original = float(regra["original"])
        ajustada = None if origem == "RO" else regra["ajustada"].get(inter)
        aplicada = original if origem == "RO" else ajustada
        if origem == "RO":
            base.update({
                "status": "ICMS-ST/RO CONFIRMADO PARA AUTOPEÇAS DE MOTOCICLETAS",
                "aplica_st": True,
                "decisao_confirmada": True,
                "confiabilidade": 100.0,
                "mva_original": original,
                "mva_ajustada": None,
                "mva_aplicada": original,
                "mva_tipo": "MVA ORIGINAL RO",
                "st_modelo_calculo": "ICMS-ST/RO — AUTOPEÇAS — DECRETO 29.048/2024",
                "responsabilidade": "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA",
                "fundamento": "Decreto RO nº 29.048/2024, Tabela II, CEST 01.076.00.",
                "fonte": URL_RO_DECRETO_29048,
            })
            return base
        # Rondônia não integra atualmente os Protocolos 41/08/97/10: conhece-se
        # a ST interna/MVA, mas não se presume retenção pelo remetente de MG.
        base.update({
            "status": "REGIME ST/RO DE AUTOPEÇAS IDENTIFICADO — RESPONSABILIDADE INTERESTADUAL LOCAL",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 98.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA RO — RESPONSABILIDADE LOCAL",
            "st_modelo_calculo": "ICMS-ST/RO — AUTOPEÇAS — RESPONSABILIDADE LOCAL",
            "contrato_fidelidade": contrato_fidelidade,
            "vigencia_inicio": "2024-01-12",
            "vigencia_fim": "",
            "responsabilidade": "DESTINATÁRIO RO / REGRA LOCAL — REMETENTE MG SEM PROTOCOLO AUTOMÁTICO",
            "acordo_status": "RO NÃO INTEGRA OS PROTOCOLOS 41/08 OU 97/10 PARA ESTA ROTA",
            "fundamento": "Decreto RO nº 29.048/2024, Tabela II, CEST 01.076.00.",
            "fonte": URL_RO_DECRETO_29048,
            "observacao": f"CEST 01.076.00: MVA original de {original:.2f}% e ajustada de {float(aplicada):.2f}% para alíquota interestadual de {inter:.2f}%. A MVA é conhecida, mas a retenção pelo remetente de MG não é presumida.",
        })
        return base

    @classmethod
    def _ma(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a cobertura estruturada de autopeças e pneumáticos do Maranhão."""
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_MA.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA MA ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "MA" else regra["ajustada"].get(inter)
            aplicada = original if origem == "MA" else ajustada
            excecao_convenio = cest in {"16.005.00", "16.006.00", "16.007.01", "16.009.00"}
            if origem != "MA" and excecao_convenio:
                base.update({
                    "status": "PNEUMÁTICO/MA COM CEST FORA DA RESPONSABILIDADE AUTOMÁTICA DO CONVÊNIO 102/17 — REVISAR",
                    "aplica_st": False,
                    "decisao_confirmada": False,
                    "confiabilidade": 80.0,
                    "mva_original": original,
                    "mva_ajustada": ajustada,
                    "mva_aplicada": aplicada,
                    "mva_tipo": "MVA MA — RESPONSABILIDADE INTERESTADUAL EM REVISÃO",
                    "responsabilidade": "DESTINATÁRIO MA / REGRA LOCAL — CONFIRMAR RESPONSABILIDADE",
                    "acordo_status": "CEST EXCEPCIONADO PELO CONVÊNIO ICMS 102/17",
                    "fundamento": "RICMS/MA; Convênio ICMS 102/17.",
                    "fonte": f"{URL_MA_LEGISLACAO} | {URL_CONFAZ_CONVENIO_102}",
                })
                return base

            base.update({
                "status": "ICMS-ST/MA CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "MA" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "MA" or ajustada is not None) else 80.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA MA — ALÍQUOTA INTERNA 23%" if ajustada is not None else "MVA ORIGINAL MA",
                "st_modelo_calculo": "ICMS-ST/MA — PNEUMÁTICOS — CONVÊNIO 102/17",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2025-02-23",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17"
                    if origem != "MA" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "PNEUMÁTICOS/MA — RICMS/MA + CONVÊNIO ICMS 102/17",
                "fundamento": "RICMS/MA; Convênio ICMS 102/17; MVA ajustada pela fórmula legal.",
                "fonte": f"{URL_MA_LEGISLACAO} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA original de {original:.2f}%. "
                    + (
                        f"Para alíquota interestadual de {inter:.2f}% e interna MA de 23%, a MVA ajustada é {float(aplicada):.2f}%."
                        if aplicada is not None and origem != "MA" else
                        "Na operação interna aplica-se a MVA original."
                    )
                ),
            })
            if origem != "MA" and ajustada is None:
                base.update({
                    "status": "ST/MA DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        if "AUTOPE" not in segmento:
            return base

        if origem != "MA" and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            base.update({
                "status": "AUTOPEÇA/MA COM CEST EXCLUÍDO DO PROTOCOLO 41/08 — REVISAR RESPONSABILIDADE",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 85.0,
                "responsabilidade": "DESTINATÁRIO MA / REGRA LOCAL — CEST EXCLUÍDO DO PROTOCOLO 41/08",
                "acordo_status": "CEST EXPRESSAMENTE EXCLUÍDO DO CAPUT VIGENTE DO PROTOCOLO 41/08",
                "fundamento": "RICMS/MA; Protocolo ICMS 41/08.",
                "fonte": f"{URL_MA_LEGISLACAO} | {URL_CONFAZ_PROTOCOLO_41}",
            })
            return base

        chave = "fidelidade" if contrato_fidelidade else "demais"
        regra = MVA_AUTOPECAS_MA[chave]
        original = float(regra["original"])
        ajustada = None if origem == "MA" else regra["ajustada"].get(inter)
        aplicada = original if origem == "MA" else ajustada
        origem_signataria = origem in SIGNATARIOS_PROTOCOLO_41
        fidelidade_obs = (
            "Foi informada fidelidade/exclusividade; confirmar integralmente os requisitos legais antes de usar a MVA reduzida. "
            if contrato_fidelidade else
            "Sem fidelidade/exclusividade qualificada informada, foi usada a MVA original de 71,78% dos demais casos. "
        )

        if origem == "MA" or origem_signataria:
            base.update({
                "status": (
                    "ICMS-ST/MA CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL"
                    if contrato_fidelidade else "ICMS-ST/MA CONFIRMADO PARA AUTOPEÇAS"
                ),
                "aplica_st": True,
                "decisao_confirmada": origem == "MA" or ajustada is not None,
                "confiabilidade": 95.0 if contrato_fidelidade else 100.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA AJUSTADA MA — ALÍQUOTA INTERNA 23%" if ajustada is not None else "MVA ORIGINAL MA",
                "st_modelo_calculo": "ICMS-ST/MA — AUTOPEÇAS — PROTOCOLO 41/08",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2025-02-23",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — PROTOCOLO ICMS 41/08"
                    if origem != "MA" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "AUTOPEÇAS/MA — RICMS/MA + PROTOCOLO ICMS 41/08",
                "fundamento": "RICMS/MA; Protocolo ICMS 41/08; MVA ajustada pela fórmula legal.",
                "fonte": f"{URL_MA_LEGISLACAO} | {URL_CONFAZ_PROTOCOLO_41}",
                "observacao": (
                    f"Autopeças/MA: MVA original de {original:.2f}%. "
                    + (
                        f"Na operação interestadual a {inter:.2f}% e interna MA de 23%, a MVA ajustada é {float(aplicada):.2f}%. "
                        if aplicada is not None and origem != "MA" else
                        "Na operação interna aplica-se a MVA original. "
                    )
                    + fidelidade_obs
                    + "O Protocolo ICMS 41/08 vigente inclui Maranhão como destino e atribui, em regra, a responsabilidade ao remetente, ressalvadas as exceções do próprio acordo."
                ),
            })
            if origem != "MA" and ajustada is None:
                base.update({
                    "status": "ST/MA DE AUTOPEÇAS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        base.update({
            "status": "REGIME ST/MA DE AUTOPEÇAS IDENTIFICADO — ORIGEM FORA DO PROTOCOLO 41/08",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 92.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA MA — RESPONSABILIDADE A CONFIRMAR",
            "responsabilidade": "DESTINATÁRIO MA / REGRA LOCAL — REMETENTE NÃO ALCANÇADO PELO PROTOCOLO 41/08",
            "acordo_status": f"PROTOCOLO 41/08 NÃO ATRIBUI RESPONSABILIDADE AUTOMÁTICA À ORIGEM {origem}",
            "fundamento": "RICMS/MA; Protocolo ICMS 41/08.",
            "fonte": f"{URL_MA_LEGISLACAO} | {URL_CONFAZ_PROTOCOLO_41}",
        })
        return base

    @classmethod
    def _pb(
        cls,
        base: Dict[str, Any],
        origem: str,
        aliquota_inter: Optional[float],
        contrato_fidelidade: bool,
    ) -> Dict[str, Any]:
        """Aplica a tabela oficial do Anexo 05 da Paraíba.

        Autopeças usam as MVAs oficiais 36,56%/71,78% e respectivas margens
        interestaduais. Para destinos PB, o Protocolo 41/08 vigente atribui a
        responsabilidade ao remetente nos CEST abrangidos. Pneumáticos usam a
        tabela do segmento 16 e o Convênio 102/17.
        """
        segmento = str(base.get("segmento") or "").upper()
        cest = str(base.get("cest") or "").strip()
        inter = float(aliquota_inter or 0.0)

        if "PNEUM" in segmento:
            regra = CEST_PNEUMATICOS_PB.get(cest)
            if regra is None:
                base.update({
                    "status": "PNEUMÁTICO FORA DA TABELA PB ESTRUTURADA",
                    "decisao_confirmada": False,
                    "confiabilidade": 45.0,
                })
                return base
            original = float(regra["original"])
            ajustada = None if origem == "PB" else regra["ajustada"].get(inter)
            aplicada = original if origem == "PB" else ajustada
            excecao_convenio = cest in {"16.005.00", "16.006.00", "16.007.01", "16.009.00"}

            if origem != "PB" and excecao_convenio:
                base.update({
                    "status": "PNEUMÁTICO/PB COM CEST FORA DA RESPONSABILIDADE AUTOMÁTICA DO CONVÊNIO 102/17 — REVISAR",
                    "aplica_st": False,
                    "decisao_confirmada": False,
                    "confiabilidade": 80.0,
                    "mva_original": original,
                    "mva_ajustada": ajustada,
                    "mva_aplicada": aplicada,
                    "mva_tipo": "MVA OFICIAL PB — RESPONSABILIDADE INTERESTADUAL EM REVISÃO",
                    "responsabilidade": "DESTINATÁRIO PB / REGRA LOCAL — CONFIRMAR RESPONSABILIDADE",
                    "acordo_status": "CEST EXCEPCIONADO PELO CONVÊNIO ICMS 102/17",
                    "fundamento": "RICMS/PB, Anexo 05; Convênio ICMS 102/17.",
                    "fonte": f"{URL_PB_ANEXO_05} | {URL_CONFAZ_CONVENIO_102}",
                })
                return base

            base.update({
                "status": "ICMS-ST/PB CONFIRMADO PARA PNEUMÁTICOS",
                "aplica_st": True,
                "decisao_confirmada": origem == "PB" or ajustada is not None,
                "confiabilidade": 100.0 if (origem == "PB" or ajustada is not None) else 80.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA INTERESTADUAL OFICIAL PB" if ajustada is not None else "MVA ORIGINAL PB",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2024-01-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — CONVÊNIO ICMS 102/17"
                    if origem != "PB" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "PNEUMÁTICOS/PB — ANEXO 05 + CONVÊNIO ICMS 102/17",
                "fundamento": "RICMS/PB, Anexo 05; Convênio ICMS 102/17.",
                "fonte": f"{URL_PB_ANEXO_05} | {URL_CONFAZ_CONVENIO_102}",
                "observacao": (
                    f"CEST {cest}: MVA original de {original:.2f}% na tabela oficial da Paraíba. "
                    + (
                        f"Para a alíquota interestadual de {inter:.2f}%, o Anexo 05 traz MVA de {float(aplicada):.2f}%."
                        if aplicada is not None and origem != "PB" else
                        "Na operação interna aplica-se a MVA original da tabela PB."
                    )
                ),
            })
            if origem != "PB" and ajustada is None:
                base.update({
                    "status": "ST/PB DE PNEUMÁTICOS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        if "AUTOPE" not in segmento:
            return base

        if origem != "PB" and cest in CEST_AUTOPECAS_EXCLUIDOS_PROTOCOLO_41:
            base.update({
                "status": "AUTOPEÇA/PB COM CEST EXCLUÍDO DO PROTOCOLO 41/08 — REVISAR RESPONSABILIDADE",
                "aplica_st": False,
                "decisao_confirmada": False,
                "confiabilidade": 85.0,
                "responsabilidade": "DESTINATÁRIO PB / REGRA LOCAL — CEST EXCLUÍDO DO PROTOCOLO 41/08",
                "acordo_status": "CEST EXPRESSAMENTE EXCLUÍDO DO CAPUT VIGENTE DO PROTOCOLO 41/08",
                "fundamento": "RICMS/PB, Anexo 05; Protocolo ICMS 41/08.",
                "fonte": f"{URL_PB_ANEXO_05} | {URL_CONFAZ_PROTOCOLO_41}",
            })
            return base

        chave = "fidelidade" if contrato_fidelidade else "demais"
        regra = MVA_AUTOPECAS_PB[chave]
        original = float(regra["original"])
        ajustada = None if origem == "PB" else regra["ajustada"].get(inter)
        aplicada = original if origem == "PB" else ajustada
        origem_signataria = origem in SIGNATARIOS_PROTOCOLO_41
        fidelidade_obs = (
            "Foi informada fidelidade/exclusividade. Confirmar o enquadramento integral nos requisitos da legislação da Paraíba e do acordo aplicável."
            if contrato_fidelidade else
            "Sem fidelidade/exclusividade qualificada informada, foi usada a MVA de 71,78% dos demais casos."
        )

        if origem == "PB" or origem_signataria:
            base.update({
                "status": (
                    "ICMS-ST/PB CONFIRMADO PARA AUTOPEÇAS — MVA DE FIDELIDADE CONDICIONAL AOS REQUISITOS LEGAIS"
                    if contrato_fidelidade else "ICMS-ST/PB CONFIRMADO PARA AUTOPEÇAS"
                ),
                "aplica_st": True,
                "decisao_confirmada": origem == "PB" or ajustada is not None,
                "confiabilidade": 95.0 if contrato_fidelidade else 100.0,
                "mva_original": original,
                "mva_ajustada": ajustada,
                "mva_aplicada": aplicada,
                "mva_tipo": "MVA INTERESTADUAL OFICIAL PB" if ajustada is not None else "MVA ORIGINAL PB",
                "contrato_fidelidade": contrato_fidelidade,
                "vigencia_inicio": "2024-01-01",
                "vigencia_fim": "",
                "responsabilidade": (
                    "REMETENTE/SUBSTITUTO — PROTOCOLO ICMS 41/08"
                    if origem != "PB" else "REMETENTE/SUBSTITUTO NA OPERAÇÃO INTERNA"
                ),
                "acordo_status": "AUTOPEÇAS/PB — ANEXO 05 + PROTOCOLO ICMS 41/08",
                "fundamento": "RICMS/PB, Anexo 05; Protocolo ICMS 41/08.",
                "fonte": f"{URL_PB_ANEXO_05} | {URL_CONFAZ_PROTOCOLO_41}",
                "observacao": (
                    f"Autopeças/PB: MVA original de {original:.2f}%. "
                    + (
                        f"Para a alíquota interestadual de {inter:.2f}%, o Anexo 05 traz MVA oficial de {float(aplicada):.2f}%. "
                        if aplicada is not None and origem != "PB" else
                        "Na operação interna aplica-se a MVA original PB. "
                    )
                    + fidelidade_obs
                    + " Confirmar exceções do Protocolo 41/08 e eventual regime especial do destinatário antes da emissão."
                ),
            })
            if origem != "PB" and ajustada is None:
                base.update({
                    "status": "ST/PB DE AUTOPEÇAS IDENTIFICADA, MAS A MVA INTERESTADUAL EXIGE REVISÃO",
                    "mva_aplicada": None,
                    "mva_tipo": "",
                    "decisao_confirmada": False,
                })
            return base

        base.update({
            "status": "REGIME ST/PB DE AUTOPEÇAS IDENTIFICADO — ORIGEM FORA DO PROTOCOLO 41/08",
            "aplica_st": False,
            "decisao_confirmada": False,
            "confiabilidade": 92.0,
            "mva_original": original,
            "mva_ajustada": ajustada,
            "mva_aplicada": aplicada,
            "mva_tipo": "MVA OFICIAL PB — RESPONSABILIDADE A CONFIRMAR",
            "responsabilidade": "DESTINATÁRIO PB / REGRA LOCAL — REMETENTE NÃO ALCANÇADO PELO PROTOCOLO 41/08",
            "acordo_status": f"PROTOCOLO 41/08 NÃO ATRIBUI RESPONSABILIDADE AUTOMÁTICA À ORIGEM {origem}",
            "fundamento": "RICMS/PB, Anexo 05; Protocolo ICMS 41/08.",
            "fonte": f"{URL_PB_ANEXO_05} | {URL_CONFAZ_PROTOCOLO_41}",
            "observacao": "A mercadoria integra a ST interna da Paraíba, mas a responsabilidade interestadual do remetente exige revisão do acordo aplicável.",
        })
        return base

    @classmethod
    def analisar(
        cls,
        ncm: str,
        descricao: str,
        uf_origem: str,
        uf_destino: str,
        data_operacao: date,
        aliquota_interestadual: Optional[float],
        aliquota_interna: Optional[float],
        contrato_fidelidade: bool = False,
        finalidade_automotiva: str = "",
    ) -> Dict[str, Any]:
        origem = str(uf_origem or "").strip().upper()
        destino = str(uf_destino or "").strip().upper()
        if destino == "PA":
            base = cls._classificar_pa(str(ncm), descricao)
        elif destino == "SP":
            base = cls._classificar_sp(str(ncm), descricao)
        elif destino == "BA":
            base = cls._classificar_ba(str(ncm), descricao)
        elif destino == "ES":
            base = cls._classificar_es(str(ncm), descricao)
        elif destino == "RJ":
            base = cls._classificar_rj(str(ncm), descricao)
        elif destino == "GO":
            base = cls._classificar_go(str(ncm), descricao)
        elif destino == "PR":
            base = cls._classificar_pr(str(ncm), descricao)
        elif destino == "SC":
            base = cls._classificar_sc(str(ncm), descricao)
        elif destino == "RS":
            base = cls._classificar_rs(str(ncm), descricao)
        elif destino == "MS":
            base = cls._classificar_ms(str(ncm), descricao)
        elif destino == "MT":
            base = cls._classificar_mt(str(ncm), descricao)
        elif destino == "DF":
            base = cls._classificar_df(str(ncm), descricao)
        elif destino == "CE":
            base = cls._classificar_ce(str(ncm), descricao)
        elif destino == "PE":
            base = cls._classificar_pe(str(ncm), descricao)
        elif destino == "AL":
            base = cls._classificar_al(str(ncm), descricao)
        elif destino == "PB":
            base = cls._classificar_pb(str(ncm), descricao)
        elif destino == "RN":
            base = cls._classificar_rn(str(ncm), descricao)
        elif destino == "SE":
            base = cls._classificar_se(str(ncm), descricao)
        elif destino == "MA":
            base = cls._classificar_ma(str(ncm), descricao)
        elif destino == "PI":
            base = cls._classificar_pi(str(ncm), descricao)
        elif destino == "TO":
            base = cls._classificar_to(str(ncm), descricao)
        elif destino == "AC":
            base = cls._classificar_ac(str(ncm), descricao)
        elif destino == "AM":
            base = cls._classificar_am(str(ncm), descricao)
        elif destino == "AP":
            base = cls._classificar_ap(str(ncm), descricao)
        elif destino == "RO":
            base = cls._classificar_ro(str(ncm), descricao)
        else:
            base = cls._classificar_autopeca(
                str(ncm), descricao, finalidade_automotiva
            )
        # O CEST residual 01.999.00 depende da finalidade, não de um NCM
        # nominal. Se o classificador estadual específico não encontrou o
        # produto, reaproveita a confirmação explícita do usuário antes de
        # concluir a análise. Sem confirmação, a decisão permanece condicional.
        if not base.get("potencial") and finalidade_automotiva:
            residual = cls._classificar_autopeca(
                str(ncm), descricao, finalidade_automotiva
            )
            if residual.get("potencial"):
                base = residual
        if not base.get("potencial"):
            return base
        if destino not in {"PA", "SP", "BA", "ES", "RJ", "GO", "PR", "SC", "RS", "MS", "MT", "DF", "CE", "PE", "AL", "PB", "RN", "SE", "MA", "PI", "TO", "AC", "AM", "AP", "RO"} and "AUTOPE" not in str(base.get("segmento") or "").upper():
            return base
        if destino == "PA" and (
            (base.get("decisao_confirmada") and not base.get("aplica_st"))
            or "FORA DA COBERTURA" in str(base.get("status") or "").upper()
        ):
            return base
        if destino not in cls.UFS_COBERTAS:
            base.update({
                "status": "UF SEM REGRA ESTADUAL DETALHADA NESTA SPRINT",
                "decisao_confirmada": False,
                "confiabilidade": 45.0,
                "observacao": "A classificação CEST foi encontrada, mas a MVA da UF ainda não foi instalada.",
            })
            return base
        if destino == "SP":
            return cls._sp(base, data_operacao, origem, aliquota_interestadual, aliquota_interna, contrato_fidelidade)
        if destino == "BA":
            return cls._ba(base, origem, aliquota_interestadual, contrato_fidelidade, data_operacao)
        if destino == "ES":
            return cls._es(base, origem, aliquota_interestadual, contrato_fidelidade, data_operacao)
        if destino == "PA":
            return cls._pa(base, origem, aliquota_interestadual, aliquota_interna, contrato_fidelidade)
        if destino == "GO":
            return cls._go(base, origem, aliquota_interestadual)
        if destino == "PR":
            return cls._pr(base, origem, aliquota_interestadual, aliquota_interna, contrato_fidelidade)
        if destino == "SC":
            return cls._sc(base, origem, aliquota_interestadual)
        if destino == "RS":
            return cls._rs(base, origem, aliquota_interestadual)
        if destino == "MS":
            return cls._ms(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "MT":
            return cls._mt(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "DF":
            return cls._df(base, origem, aliquota_interestadual, aliquota_interna, contrato_fidelidade)
        if destino == "CE":
            return cls._ce(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "PE":
            return cls._pe(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "AL":
            return cls._al(base, origem, aliquota_interestadual, aliquota_interna, contrato_fidelidade)
        if destino == "PB":
            return cls._pb(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "RN":
            return cls._rn(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "SE":
            return cls._se(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "MA":
            return cls._ma(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "PI":
            return cls._pi(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "TO":
            return cls._to(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "AC":
            return cls._ac(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "AM":
            return cls._am(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "AP":
            return cls._ap(base, origem, aliquota_interestadual, contrato_fidelidade)
        if destino == "RO":
            return cls._ro(base, origem, aliquota_interestadual, contrato_fidelidade)
        return cls._rj(base, origem, aliquota_interestadual, contrato_fidelidade)


__all__ = ["ICMSSTUFService", "_mva_ajustada_formula"]
