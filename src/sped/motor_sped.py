from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable

from .analisador import AlertaEstrutural, AnalisadorEstruturalSPED
from .correcoes import (
    AuditorCorrecoesSPED,
    CorrecaoSPED,
    ResultadoAnaliseCorrecoes,
    ResultadoGeracaoSPED,
)
from .estatisticas import CalculadorEstatisticasSPED, EstatisticasSPED
from .indice import IndiceSPED
from .leitor import LeitorSPEDUnificado
from .pre_validador import PreValidadorPVA, ResultadoPreValidacaoPVA
from .recalculador_piscofins import RecalculadorPISCOFINS
from .corretor_assistido import (
    CorretorAssistidoPVA,
    ResultadoAplicacaoAssistida,
    ResultadoPreparacaoAssistida,
)
from .auditor_tributario import (
    AuditorTributarioSPED,
    ImportadorXMLNFe,
    ResultadoAuditoriaTributaria,
    ResultadoImportacaoXMLNFe,
)
from .corretor_tributario_assistido import (
    CorretorTributarioAssistido,
    ResultadoAplicacaoCorrecaoTributaria,
    ResultadoPreparacaoCorrecaoTributaria,
)
from .estorno_credito_icms import (
    EstornadorCreditosICMSMG,
    ResultadoAnaliseEstornoICMS,
    ResultadoGeracaoEstornoICMS,
)
from .fluxo_final_unificado import (
    GeradorSPEDFinalUnificado,
    ResultadoGeracaoFinalUnificada,
)
from .importador_danfe_icms import (
    ImportadorDANFEICMS,
    ResultadoAnaliseDANFEICMS,
    ResultadoGeracaoDANFEICMS,
)
from .exclusor_icms_creditos_piscofins import (
    ExclusorICMSCreditosPISCOFINS,
    ResultadoAnaliseExclusaoICMS,
    ResultadoAplicacaoExclusaoICMS,
)
from .corretor_cte_xml import (
    CorretorChavesCTeXML,
    ImportadorCTeXML,
    ResultadoAnaliseChavesCTe,
    ResultadoCorrecaoChavesCTe,
    ResultadoImportacaoCTeXML,
)
from .auditor_difal import AuditorDIFALSPED, ResultadoAuditoriaDIFAL

ProgressoCallback = Callable[[int, str], None]


@dataclass(slots=True)
class ResultadoSPED:
    caminho: Path
    encoding: str
    linhas: list[str]
    indice: IndiceSPED
    estatisticas: EstatisticasSPED
    alertas: list[AlertaEstrutural]
    tempo_processamento: float

    def obter_registros(self, codigo: str) -> list[list[str]]:
        registros: list[list[str]] = []
        for referencia in self.indice.referencias(codigo):
            linha = self.linhas[referencia.indice_lista].rstrip("\r\n")
            registros.append(linha.split("|"))
        return registros

    def obter_linhas(self, codigo: str) -> list[tuple[int, str]]:
        return [
            (referencia.numero_linha, self.linhas[referencia.indice_lista].rstrip("\r\n"))
            for referencia in self.indice.referencias(codigo)
        ]


class MotorSPED:
    """Ponto central de leitura, exportação, auditoria e conversões do SPED."""

    def __init__(self) -> None:
        self.leitor = LeitorSPEDUnificado()
        self.calculador = CalculadorEstatisticasSPED()
        self.analisador = AnalisadorEstruturalSPED()
        self.auditor_correcoes = AuditorCorrecoesSPED()
        self.pre_validador = PreValidadorPVA()
        self.corretor_assistido = CorretorAssistidoPVA()
        self.importador_cte_xml = ImportadorCTeXML()
        self.corretor_chaves_cte = CorretorChavesCTeXML()
        self.importador_xml_nfe = ImportadorXMLNFe()
        self.auditor_tributario = AuditorTributarioSPED()
        self.corretor_tributario = CorretorTributarioAssistido()
        self.estornador_creditos_icms = EstornadorCreditosICMSMG()
        self.gerador_final_unificado = GeradorSPEDFinalUnificado()
        self.importador_danfe_icms = ImportadorDANFEICMS()
        self.exclusor_icms_creditos = ExclusorICMSCreditosPISCOFINS()
        self.auditor_difal = AuditorDIFALSPED()
        self.resultado: ResultadoSPED | None = None
        self.analise_correcoes: ResultadoAnaliseCorrecoes | None = None
        self.caminho_excel: Path | None = None
        self.validacao_excel = None
        self.pre_validacao_pva: ResultadoPreValidacaoPVA | None = None
        self.preparacao_assistida: ResultadoPreparacaoAssistida | None = None
        self.importacao_cte_xml: ResultadoImportacaoCTeXML | None = None
        self.analise_chaves_cte: ResultadoAnaliseChavesCTe | None = None
        self.importacao_xml_nfe: ResultadoImportacaoXMLNFe | None = None
        self.auditoria_tributaria: ResultadoAuditoriaTributaria | None = None
        self.preparacao_correcao_tributaria: ResultadoPreparacaoCorrecaoTributaria | None = None
        self.analise_estorno_icms: ResultadoAnaliseEstornoICMS | None = None
        self.analise_danfe_icms: ResultadoAnaliseDANFEICMS | None = None
        self.analise_exclusao_icms_creditos: ResultadoAnaliseExclusaoICMS | None = None
        self.auditoria_difal: ResultadoAuditoriaDIFAL | None = None

    def abrir(self, caminho: str | Path, progresso: ProgressoCallback | None = None) -> ResultadoSPED:
        inicio = perf_counter()
        arquivo = Path(caminho)
        self._progresso(progresso, 5, "Abrindo arquivo SPED...")

        linhas, encoding = self.leitor.ler(arquivo)
        self._progresso(progresso, 35, f"{len(linhas):,} linhas carregadas.")

        indice = IndiceSPED().construir(linhas)
        self._progresso(progresso, 65, f"{len(indice.codigos())} tipos de registro indexados.")

        estatisticas = self.calculador.calcular(linhas, indice)
        self._progresso(progresso, 85, "Estatísticas calculadas.")

        alertas = self.analisador.analisar(linhas, estatisticas.contagens)
        tempo = perf_counter() - inicio

        self.resultado = ResultadoSPED(
            caminho=arquivo,
            encoding=encoding,
            linhas=linhas,
            indice=indice,
            estatisticas=estatisticas,
            alertas=alertas,
            tempo_processamento=tempo,
        )
        self.analise_correcoes = None
        self.pre_validacao_pva = None
        self.preparacao_assistida = None
        self.analise_chaves_cte = None
        self.auditoria_tributaria = None
        self.preparacao_correcao_tributaria = None
        self.analise_estorno_icms = None
        self.analise_danfe_icms = None
        self.analise_exclusao_icms_creditos = None
        self.auditoria_difal = None
        self._progresso(progresso, 100, "SPED carregado com sucesso.")
        return self.resultado

    def verificar_apuracao_bloco_m(self):
        """Valida se a EFD Contribuições está apurada antes do SPED -> Excel."""
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de verificar o Bloco M.")

        from .validador_apuracao_bloco_m import ValidadorApuracaoBlocoM

        return ValidadorApuracaoBlocoM().validar(
            self.resultado.linhas,
            self.resultado.estatisticas.tipo_sped,
        )

    def exportar_excel(
        self,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ):
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de exportar para Excel.")

        # Hotfix 17.7.1: impede começar o trabalho no Excel usando uma EFD
        # Contribuições ainda sem a apuração do Bloco M gerada no PGE.
        diagnostico_m = self.verificar_apuracao_bloco_m()
        if diagnostico_m.bloqueado:
            raise RuntimeError(diagnostico_m.mensagem_bloqueio())

        from .exportador_excel import ExportadorSPEDExcel

        return ExportadorSPEDExcel().exportar(
            self.resultado,
            caminho_saida,
            progresso,
        )

    def analisar_correcoes(
        self,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseCorrecoes:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de analisar correções.")
        self.analise_correcoes = self.auditor_correcoes.analisar(
            self.resultado.linhas,
            progresso,
        )
        return self.analise_correcoes

    def gerar_sped_corrigido(
        self,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoGeracaoSPED:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de gerar uma cópia corrigida.")
        if self.analise_correcoes is None:
            self.analisar_correcoes(progresso)
        assert self.analise_correcoes is not None
        if self.analise_correcoes.total_automaticas == 0:
            raise RuntimeError("A análise não encontrou correções automáticas seguras para aplicar.")

        novas_linhas = self.auditor_correcoes.aplicar_automaticas(
            self.resultado.linhas,
            self.analise_correcoes,
            progresso,
        )

        # Quando a correção automática altera ALIQ_PIS/ALIQ_COFINS do C170,
        # o valor da contribuição e os totais do C100 passam a ser dependências
        # determinísticas. Reutilizamos o recalculador encadeado já aprovado no
        # FiscalPro e mantemos o Bloco M como pendência explícita de re-apuração.
        afetadas: set[tuple[int, str]] = set()
        for correcao in self.analise_correcoes.automaticas:
            if correcao.registro != "C170":
                continue
            if correcao.indice_campo == 27:
                afetadas.add((correcao.numero_linha, "PIS"))
            elif correcao.indice_campo == 33:
                afetadas.add((correcao.numero_linha, "COFINS"))

        analise_saida = ResultadoAnaliseCorrecoes(
            correcoes=list(self.analise_correcoes.correcoes)
        )
        if afetadas:
            self._progresso(
                progresso,
                92,
                "Recalculando valores de PIS/COFINS e totais dos C100 afetados...",
            )
            recalculo = RecalculadorPISCOFINS().recalcular(
                novas_linhas,
                afetadas,
                self.resultado.estatisticas.tipo_sped,
            )
            novas_linhas = recalculo.linhas

            for alteracao in recalculo.alteracoes:
                analise_saida.correcoes.append(
                    CorrecaoSPED(
                        numero_linha=alteracao.numero_linha,
                        registro=alteracao.registro,
                        codigo_item="",
                        gravidade="Alta",
                        problema=f"{alteracao.campo} dependente da correção de alíquota.",
                        acao=alteracao.justificativa,
                        automatica=True,
                        indice_campo=None,
                        valor_anterior=alteracao.valor_anterior,
                        valor_novo=alteracao.valor_novo,
                    )
                )

            if recalculo.requer_reapuracao_bloco_m:
                linha_m = next(
                    (
                        numero
                        for numero, linha in enumerate(novas_linhas, start=1)
                        if linha.startswith("|M001|")
                    ),
                    1,
                )
                analise_saida.correcoes.append(
                    CorrecaoSPED(
                        numero_linha=linha_m,
                        registro="M001",
                        codigo_item="",
                        gravidade="Alta",
                        problema=(
                            "PIS/COFINS documental recalculado; o Bloco M precisa ser "
                            "reapurado após as correções."
                        ),
                        acao=(
                            "Regenerar/recalcular a apuração do Bloco M no PGE oficial "
                            "antes da transmissão. O FiscalPro não altera saldos, ajustes "
                            "ou créditos por aproximação."
                        ),
                        automatica=False,
                    )
                )

        return self.auditor_correcoes.salvar(
            novas_linhas,
            caminho_saida,
            self.resultado.encoding,
            analise_saida,
        )


    def carregar_xmls_nfe(
        self,
        fontes: list[str | Path],
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoImportacaoXMLNFe:
        self.importacao_xml_nfe = self.importador_xml_nfe.importar(fontes, progresso)
        self.auditoria_tributaria = None
        self.preparacao_correcao_tributaria = None
        return self.importacao_xml_nfe

    def auditar_tributacao(
        self,
        contexto: dict | None = None,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAuditoriaTributaria:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de executar a auditoria tributária.")
        self.auditoria_tributaria = self.auditor_tributario.auditar(
            self.resultado.linhas,
            self.resultado.estatisticas.tipo_sped,
            self.resultado.estatisticas.empresa,
            contexto,
            self.importacao_xml_nfe,
            progresso,
        )
        self.preparacao_correcao_tributaria = None
        return self.auditoria_tributaria

    def salvar_relatorio_auditoria_tributaria(
        self,
        caminho_saida: str | Path,
    ) -> Path:
        if self.resultado is None or self.auditoria_tributaria is None:
            raise RuntimeError("Execute primeiro a auditoria tributária integrada.")
        return self.auditor_tributario.salvar_relatorio(
            self.auditoria_tributaria,
            caminho_saida,
            self.resultado.caminho,
        )


    def auditar_difal(
        self,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAuditoriaDIFAL:
        """Audita DIFAL/FCP de saídas usando C101 e XMLs de NF-e já importados."""
        if self.resultado is None:
            raise RuntimeError("Abra um SPED Fiscal antes de executar a auditoria de DIFAL.")
        self.auditoria_difal = self.auditor_difal.auditar(
            self.resultado.linhas,
            self.resultado.estatisticas.tipo_sped,
            self.resultado.estatisticas.empresa,
            self.resultado.estatisticas.periodo,
            self.importacao_xml_nfe,
            progresso,
        )
        return self.auditoria_difal

    def salvar_relatorio_difal(self, caminho_saida: str | Path) -> Path:
        if self.resultado is None or self.auditoria_difal is None:
            raise RuntimeError("Execute primeiro a auditoria automática de DIFAL.")
        return self.auditor_difal.salvar_relatorio(
            self.auditoria_difal,
            caminho_saida,
            self.resultado.caminho,
        )

    def salvar_excel_difal(self, caminho_saida: str | Path) -> Path:
        if self.resultado is None or self.auditoria_difal is None:
            raise RuntimeError("Execute primeiro a auditoria automática de DIFAL.")
        return self.auditor_difal.salvar_excel(
            self.auditoria_difal,
            caminho_saida,
            self.resultado.caminho,
        )


    def preparar_correcoes_tributarias(
        self,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoPreparacaoCorrecaoTributaria:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de preparar correções tributárias.")
        if self.auditoria_tributaria is None:
            raise RuntimeError("Execute primeiro a auditoria tributária integrada.")
        self.preparacao_correcao_tributaria = self.corretor_tributario.preparar(
            self.resultado.linhas,
            self.auditoria_tributaria,
            progresso,
        )
        return self.preparacao_correcao_tributaria

    def atualizar_correcao_tributaria(
        self,
        identificador: int,
        valor_novo: str | None = None,
        selecionada: bool | None = None,
    ):
        if self.preparacao_correcao_tributaria is None:
            raise RuntimeError("Prepare primeiro as correções tributárias.")
        return self.corretor_tributario.atualizar_proposta(
            self.preparacao_correcao_tributaria,
            identificador,
            valor_novo,
            selecionada,
        )

    def aplicar_correcoes_tributarias(
        self,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAplicacaoCorrecaoTributaria:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de aplicar correções tributárias.")
        if self.auditoria_tributaria is None:
            raise RuntimeError("Execute primeiro a auditoria tributária integrada.")
        if self.preparacao_correcao_tributaria is None:
            self.preparar_correcoes_tributarias(progresso)
        assert self.preparacao_correcao_tributaria is not None
        return self.corretor_tributario.aplicar(
            self.resultado.linhas,
            self.resultado.encoding,
            self.resultado.estatisticas.tipo_sped,
            self.resultado.estatisticas.empresa,
            self.auditoria_tributaria,
            self.preparacao_correcao_tributaria,
            caminho_saida,
            self.importacao_xml_nfe,
            progresso,
        )



    def analisar_danfes_icms(
        self,
        fontes: list[str | Path],
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseDANFEICMS:
        """Confere XMLs/PDFs das compras para revenda, inclusive o CFOP de entrada por item."""
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de conferir as NF-e de entrada.")
        self.analise_danfe_icms = self.importador_danfe_icms.analisar(
            self.resultado.linhas,
            fontes,
            progresso,
        )
        return self.analise_danfe_icms

    def gerar_sped_com_icms_danfe(
        self,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoGeracaoDANFEICMS:
        """Gera cópia com CFOP de entrada conferido e ICMS próprio preenchido no C170/C190."""
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de preencher o ICMS das compras.")
        if self.analise_danfe_icms is None:
            raise RuntimeError("Selecione e confira primeiro os XMLs/PDFs/ZIP das compras para revenda.")
        return self.importador_danfe_icms.gerar(
            self.resultado.linhas,
            self.resultado.encoding,
            caminho_saida,
            self.analise_danfe_icms,
            progresso,
        )

    def analisar_exclusao_icms_creditos_piscofins(
        self,
        caminho_sped_fiscal: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseExclusaoICMS:
        """Cruza a EFD Contribuições aberta com um SPED Fiscal corrigido."""
        if self.resultado is None:
            raise RuntimeError("Abra a EFD Contribuições antes de importar o ICMS do SPED Fiscal.")
        self.analise_exclusao_icms_creditos = self.exclusor_icms_creditos.analisar(
            self.resultado.linhas,
            self.resultado.estatisticas.tipo_sped,
            self.resultado.estatisticas.cnpj,
            self.resultado.estatisticas.periodo,
            caminho_sped_fiscal,
            progresso,
        )
        return self.analise_exclusao_icms_creditos

    def gerar_contribuicoes_com_icms_fora_da_base(
        self,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAplicacaoExclusaoICMS:
        """Gera cópia com ICMS próprio excluído das bases de crédito PIS/COFINS."""
        if self.resultado is None:
            raise RuntimeError("Abra a EFD Contribuições antes de gerar a nova cópia.")
        if self.analise_exclusao_icms_creditos is None:
            raise RuntimeError("Selecione e confira primeiro o SPED Fiscal corrigido.")
        return self.exclusor_icms_creditos.gerar(
            self.resultado.linhas,
            self.resultado.encoding,
            self.resultado.estatisticas.tipo_sped,
            self.analise_exclusao_icms_creditos,
            caminho_saida,
            progresso,
        )


    def analisar_estorno_creditos_icms(
        self,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseEstornoICMS:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de analisar os créditos de ICMS.")
        self.analise_estorno_icms = self.estornador_creditos_icms.analisar(
            self.resultado.linhas, progresso
        )
        return self.analise_estorno_icms

    def gerar_sped_com_estorno_icms(
        self,
        caminho_saida: str | Path,
        codigo_ajuste: str,
        descricao_ajuste: str = "ESTORNO DE CREDITO DE ICMS",
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoGeracaoEstornoICMS:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de gerar o estorno de ICMS.")
        if self.analise_estorno_icms is None:
            self.analisar_estorno_creditos_icms(progresso)
        assert self.analise_estorno_icms is not None
        return self.estornador_creditos_icms.gerar(
            self.resultado.linhas,
            self.resultado.encoding,
            caminho_saida,
            self.analise_estorno_icms,
            codigo_ajuste,
            descricao_ajuste,
            progresso,
        )

    def gerar_sped_final_unificado(
        self,
        caminho_saida: str | Path,
        codigo_ajuste: str,
        descricao_ajuste: str = "ESTORNO DE CREDITO DE ICMS",
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoGeracaoFinalUnificada:
        """Aplica as correções assistidas marcadas e o estorno em um único TXT final."""
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de gerar o arquivo final unificado.")
        if self.pre_validacao_pva is None:
            self.validar_antes_pva(progresso)
        if self.preparacao_assistida is None:
            self.preparar_correcoes_assistidas(progresso)
        assert self.pre_validacao_pva is not None
        assert self.preparacao_assistida is not None
        return self.gerador_final_unificado.gerar(
            self.resultado.linhas,
            self.resultado.encoding,
            self.resultado.estatisticas.tipo_sped,
            self.pre_validacao_pva,
            self.preparacao_assistida,
            caminho_saida,
            codigo_ajuste,
            descricao_ajuste,
            progresso,
        )


    def carregar_xmls_cte(
        self,
        fontes: list[str | Path],
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoImportacaoCTeXML:
        self.importacao_cte_xml = self.importador_cte_xml.importar(fontes, progresso)
        self.analise_chaves_cte = None
        return self.importacao_cte_xml

    def analisar_chaves_cte(
        self,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseChavesCTe:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de conferir as chaves de CT-e.")
        if self.importacao_cte_xml is None:
            raise RuntimeError("Importe primeiro os XMLs ou o ZIP de CT-e.")
        self.analise_chaves_cte = self.corretor_chaves_cte.analisar(
            self.resultado.linhas, self.importacao_cte_xml, progresso
        )
        return self.analise_chaves_cte

    def corrigir_chaves_cte(
        self,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoCorrecaoChavesCTe:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de corrigir as chaves de CT-e.")
        if self.importacao_cte_xml is None:
            raise RuntimeError("Importe primeiro os XMLs ou o ZIP de CT-e.")
        if self.analise_chaves_cte is None:
            self.analisar_chaves_cte(progresso)
        assert self.analise_chaves_cte is not None
        return self.corretor_chaves_cte.corrigir_e_salvar(
            self.resultado.linhas,
            self.resultado.encoding,
            self.analise_chaves_cte,
            caminho_saida,
            progresso,
        )


    def validar_antes_pva(
        self,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoPreValidacaoPVA:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de validar para o PVA.")
        self.pre_validacao_pva = self.pre_validador.validar(
            self.resultado.linhas,
            self.resultado.estatisticas.tipo_sped,
            progresso,
        )
        self.preparacao_assistida = None
        return self.pre_validacao_pva

    def preparar_correcoes_assistidas(
        self,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoPreparacaoAssistida:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de preparar correções assistidas.")
        if self.pre_validacao_pva is None:
            self.validar_antes_pva(progresso)
        assert self.pre_validacao_pva is not None
        self.preparacao_assistida = self.corretor_assistido.preparar(
            self.resultado.linhas,
            self.pre_validacao_pva,
            progresso,
        )
        return self.preparacao_assistida

    def atualizar_correcao_assistida(
        self,
        identificador: int,
        valor_novo: str | None = None,
        selecionada: bool | None = None,
    ):
        if self.preparacao_assistida is None:
            raise RuntimeError("Prepare primeiro as correções assistidas.")
        return self.corretor_assistido.atualizar_proposta(
            self.preparacao_assistida, identificador, valor_novo, selecionada
        )

    def aplicar_correcoes_assistidas(
        self,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAplicacaoAssistida:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de aplicar correções assistidas.")
        if self.pre_validacao_pva is None:
            self.validar_antes_pva(progresso)
        if self.preparacao_assistida is None:
            self.preparar_correcoes_assistidas(progresso)
        assert self.pre_validacao_pva is not None
        assert self.preparacao_assistida is not None
        return self.corretor_assistido.aplicar(
            self.resultado.linhas,
            self.resultado.encoding,
            self.resultado.estatisticas.tipo_sped,
            self.pre_validacao_pva,
            self.preparacao_assistida,
            caminho_saida,
            progresso,
        )

    def salvar_relatorio_pre_pva(
        self,
        caminho_saida: str | Path,
    ) -> Path:
        if self.resultado is None or self.pre_validacao_pva is None:
            raise RuntimeError("Execute primeiro a validação antes do PVA.")
        return self.pre_validador.salvar_relatorio(
            self.pre_validacao_pva,
            caminho_saida,
            self.resultado.caminho,
        )

    def selecionar_excel(self, caminho: str | Path) -> Path:
        arquivo = Path(caminho)
        if not arquivo.exists():
            raise FileNotFoundError(f"Planilha não encontrada: {arquivo}")
        if arquivo.suffix.lower() != ".xlsx":
            raise RuntimeError("Selecione uma planilha .xlsx gerada pelo FiscalPro.")
        self.caminho_excel = arquivo
        self.validacao_excel = None
        return arquivo

    def validar_excel(
        self,
        caminho: str | Path | None = None,
        progresso: ProgressoCallback | None = None,
    ):
        from .importador_excel import ImportadorExcelSPED

        arquivo = Path(caminho) if caminho is not None else self.caminho_excel
        if arquivo is None:
            raise RuntimeError("Selecione uma planilha Excel antes de validar.")
        self.caminho_excel = arquivo
        self.validacao_excel = ImportadorExcelSPED().validar(arquivo, progresso)
        return self.validacao_excel

    def conferir_alteracoes_excel(self):
        """Retorna o comparativo Original × Novo da última validação Excel."""
        from .importador_excel import ImportadorExcelSPED

        if self.validacao_excel is None:
            raise RuntimeError("Valide a planilha Excel antes de conferir as alterações.")
        return ImportadorExcelSPED.obter_conferencia(self.validacao_excel)

    def filtrar_conferencia_excel(
        self,
        itens,
        registro: str = "",
        tipo: str = "",
        categoria: str = "",
        busca: str = "",
    ):
        from .importador_excel import ImportadorExcelSPED

        return ImportadorExcelSPED.filtrar_conferencia(
            itens,
            registro=registro,
            tipo=tipo,
            categoria=categoria,
            busca=busca,
        )

    def salvar_relatorio_conferencia_excel(
        self,
        caminho_saida: str | Path,
        itens=None,
    ) -> Path:
        from .importador_excel import ImportadorExcelSPED

        if self.validacao_excel is None:
            raise RuntimeError("Valide a planilha Excel antes de gerar o relatório de conferência.")
        return ImportadorExcelSPED.salvar_relatorio_conferencia(
            self.validacao_excel,
            caminho_saida,
            itens=itens,
        )

    def gerar_sped_de_excel(
        self,
        caminho_saida: str | Path,
        caminho_excel: str | Path | None = None,
        progresso: ProgressoCallback | None = None,
    ):
        from .importador_excel import ImportadorExcelSPED

        arquivo = Path(caminho_excel) if caminho_excel is not None else self.caminho_excel
        if arquivo is None:
            raise RuntimeError("Selecione uma planilha Excel antes de gerar o TXT.")
        self.caminho_excel = arquivo
        return ImportadorExcelSPED().gerar_txt(arquivo, caminho_saida, progresso)

    def obter_registros(self, codigo: str) -> list[list[str]]:
        if self.resultado is None:
            raise RuntimeError("Abra um arquivo SPED antes de consultar registros.")
        return self.resultado.obter_registros(codigo)

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(percentual, mensagem)
