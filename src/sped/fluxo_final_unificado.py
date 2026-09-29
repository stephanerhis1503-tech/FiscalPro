from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from .corretor_assistido import (
    CorretorAssistidoPVA,
    ResultadoAplicacaoAssistida,
    ResultadoPreparacaoAssistida,
)
from .estorno_credito_icms import (
    EstornadorCreditosICMSMG,
    ResultadoAnaliseEstornoICMS,
    ResultadoGeracaoEstornoICMS,
)
from .leitor import LeitorSPEDUnificado
from .pre_validador import PreValidadorPVA, ResultadoPreValidacaoPVA

ProgressoCallback = Callable[[int, str], None]


@dataclass(frozen=True, slots=True)
class ResultadoGeracaoFinalUnificada:
    caminho_sped: Path
    caminho_relatorio: Path
    caminho_memoria_estorno: Path
    caminho_relatorio_estorno: Path
    codigo_ajuste: str
    correcoes_aplicadas: int
    erros_antes: int
    avisos_antes: int
    erros_depois: int
    avisos_depois: int
    total_estornado: Decimal
    notas_estornadas: int
    itens_estornados: int
    linhas_inseridas: int


class GeradorSPEDFinalUnificado:
    """Aplica a Correção Assistida e o estorno de ICMS em uma única saída.

    Os arquivos intermediários são criados apenas em uma pasta temporária e apagados
    ao final. Para a usuária, existe somente o arquivo final e seus relatórios.
    """

    def __init__(self) -> None:
        self.corretor_assistido = CorretorAssistidoPVA()
        self.estornador = EstornadorCreditosICMSMG()
        self.pre_validador = PreValidadorPVA()
        self.leitor = LeitorSPEDUnificado()

    def gerar(
        self,
        linhas: list[str],
        encoding: str,
        tipo_sped: str,
        pre_validacao: ResultadoPreValidacaoPVA,
        preparacao: ResultadoPreparacaoAssistida,
        caminho_saida: str | Path,
        codigo_ajuste: str,
        descricao_ajuste: str = "ESTORNO DE CREDITO DE ICMS",
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoGeracaoFinalUnificada:
        selecionadas = preparacao.selecionadas
        if not selecionadas:
            raise RuntimeError("Nenhuma correção assistida está marcada para aplicar.")

        destino = Path(caminho_saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            raise FileExistsError(f"O arquivo de destino já existe: {destino}")

        self._progresso(progresso, 2, "Iniciando fluxo final unificado...")
        with TemporaryDirectory(prefix="fiscalpro_final_") as pasta_temp:
            temp = Path(pasta_temp)
            caminho_corrigido = temp / "01_CORRECOES_ASSISTIDAS.txt"

            resultado_corr = self.corretor_assistido.aplicar(
                linhas,
                encoding,
                tipo_sped,
                pre_validacao,
                preparacao,
                caminho_corrigido,
                self._faixa_progresso(progresso, 3, 42),
            )

            linhas_corrigidas, encoding_corrigido = self.leitor.ler(caminho_corrigido)
            self._progresso(progresso, 45, "Analisando créditos no arquivo já corrigido...")
            analise_estorno = self.estornador.analisar(
                linhas_corrigidas,
                self._faixa_progresso(progresso, 45, 63),
            )
            self._validar_estorno(analise_estorno)

            resultado_estorno = self.estornador.gerar(
                linhas_corrigidas,
                encoding_corrigido,
                destino,
                analise_estorno,
                codigo_ajuste,
                descricao_ajuste,
                self._faixa_progresso(progresso, 64, 88),
            )

        linhas_finais, _ = self.leitor.ler(destino)
        self._progresso(progresso, 90, "Executando pré-validação do arquivo final...")
        validacao_final = self.pre_validador.validar(
            linhas_finais,
            tipo_sped,
            self._faixa_progresso(progresso, 90, 97),
        )
        relatorio = destino.with_name(f"{destino.stem}_RELATORIO_FINAL_UNIFICADO.txt")
        self._salvar_relatorio(
            relatorio,
            destino,
            resultado_corr,
            resultado_estorno,
            validacao_final,
        )
        self._progresso(progresso, 100, "Arquivo final corrigido e estornado gerado com sucesso.")

        return ResultadoGeracaoFinalUnificada(
            caminho_sped=destino,
            caminho_relatorio=relatorio,
            caminho_memoria_estorno=resultado_estorno.caminho_memoria,
            caminho_relatorio_estorno=resultado_estorno.caminho_relatorio,
            codigo_ajuste=resultado_estorno.codigo_ajuste,
            correcoes_aplicadas=resultado_corr.total_aplicadas,
            erros_antes=resultado_corr.erros_antes,
            avisos_antes=resultado_corr.avisos_antes,
            erros_depois=len(validacao_final.erros),
            avisos_depois=len(validacao_final.avisos),
            total_estornado=resultado_estorno.total_estornado,
            notas_estornadas=resultado_estorno.notas_alteradas,
            itens_estornados=resultado_estorno.itens_ajustados,
            linhas_inseridas=resultado_estorno.linhas_inseridas,
        )

    @staticmethod
    def _validar_estorno(analise: ResultadoAnaliseEstornoICMS) -> None:
        if analise.pode_gerar:
            return
        if analise.total_existente > 0 and analise.total_pendente <= 0:
            raise RuntimeError(
                "Os créditos localizados já possuem C197 correspondente. "
                "As correções podem ser geradas separadamente, mas não há novo estorno a incluir."
            )
        if analise.total_revisao > 0:
            raise RuntimeError(
                "Depois das correções, os créditos de ICMS ficaram em revisão. "
                "Confira a aba Estorno ICMS antes de gerar o arquivo final."
            )
        raise RuntimeError(
            "Depois das correções, não foram encontrados créditos seguros para estorno automático."
        )

    @staticmethod
    def _salvar_relatorio(
        caminho: Path,
        sped: Path,
        correcao: ResultadoAplicacaoAssistida,
        estorno: ResultadoGeracaoEstornoICMS,
        validacao: ResultadoPreValidacaoPVA,
    ) -> None:
        conteudo = [
            "FISCALPRO — RELATÓRIO FINAL UNIFICADO",
            "=" * 78,
            f"Gerado em: {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"SPED final: {sped}",
            "",
            "ETAPA 1 — CORREÇÕES ASSISTIDAS",
            "-" * 78,
            f"Correções aplicadas: {correcao.total_aplicadas}",
            f"Erros antes da correção: {correcao.erros_antes}",
            f"Avisos antes da correção: {correcao.avisos_antes}",
            "",
            "ETAPA 2 — ESTORNO DOS CRÉDITOS DE ICMS",
            "-" * 78,
            f"Código C197: {estorno.codigo_ajuste}",
            f"Notas estornadas: {estorno.notas_alteradas}",
            f"Itens estornados: {estorno.itens_ajustados}",
            f"Linhas incluídas: {estorno.linhas_inseridas}",
            f"Total estornado: R$ {str(estorno.total_estornado).replace('.', ',')}",
            "",
            "PRÉ-VALIDAÇÃO DO ARQUIVO FINAL",
            "-" * 78,
            f"Erros: {len(validacao.erros)}",
            f"Avisos: {len(validacao.avisos)}",
            f"Total de linhas: {validacao.total_linhas}",
            "",
            "ARQUIVOS AUXILIARES",
            "-" * 78,
            f"Memória do estorno: {estorno.caminho_memoria}",
            f"Relatório do estorno: {estorno.caminho_relatorio}",
            "",
            "ATENÇÃO",
            "- O arquivo original não foi alterado.",
            "- Os arquivos intermediários foram descartados automaticamente.",
            "- Faça a validação oficial no PVA antes da transmissão.",
        ]
        caminho.write_text("\n".join(conteudo) + "\n", encoding="utf-8")

    @staticmethod
    def _faixa_progresso(
        callback: ProgressoCallback | None,
        inicio: int,
        fim: int,
    ) -> ProgressoCallback | None:
        if callback is None:
            return None
        amplitude = max(fim - inicio, 0)

        def atualizar(percentual: int, mensagem: str) -> None:
            limitado = max(0, min(100, percentual))
            callback(inicio + int(amplitude * limitado / 100), mensagem)

        return atualizar

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(percentual, mensagem)
