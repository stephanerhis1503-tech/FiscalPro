from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.sped.auditor_tributario import ResultadoAuditoriaTributaria
from src.sped.corretor_tributario_assistido import (
    CorretorTributarioAssistido,
    PropostaCorrecaoTributaria,
    ResultadoPreparacaoCorrecaoTributaria,
)
from src.sped.pre_validador import ResultadoPreValidacaoPVA
from src.sped.recalculador_piscofins import RecalculadorPISCOFINS


def registro(codigo: str, ultimo_indice: int, **campos: str) -> str:
    valores = [""] * (ultimo_indice + 1)
    valores[0] = codigo
    for indice, valor in campos.items():
        valores[int(indice)] = str(valor)
    return "|" + "|".join(valores) + "|\n"


def campo(linha: str, indice: int) -> str:
    partes = linha.rstrip("\r\n").split("|")
    return partes[indice + 1]


class RecalculadorPISCOFINSTest(unittest.TestCase):
    def test_recalcula_item_e_total_do_documento(self) -> None:
        linhas = [
            registro("C100", 26, **{"25": "1,65", "26": "11,40"}),
            registro(
                "C170",
                35,
                **{
                    "24": "01", "25": "100,00", "26": "0", "29": "1,65",
                    "30": "01", "31": "100,00", "32": "7,60", "35": "7,60",
                },
            ),
            registro(
                "C170",
                35,
                **{
                    "24": "01", "25": "50,00", "26": "1,65", "29": "0,83",
                    "30": "01", "31": "50,00", "32": "7,60", "35": "3,80",
                },
            ),
            "|C990|4|\n",
        ]

        resultado = RecalculadorPISCOFINS().recalcular(
            linhas, {(2, "PIS")}, "EFD Contribuições"
        )

        self.assertEqual(campo(resultado.linhas[1], 29), "0,00")
        self.assertEqual(campo(resultado.linhas[0], 25), "0,83")
        self.assertEqual(campo(resultado.linhas[0], 26), "11,40")
        self.assertEqual(resultado.documentos_retotalizados, 1)
        self.assertTrue(resultado.requer_reapuracao_bloco_m)

    def test_recalcula_por_quantidade_quando_base_ad_valorem_esta_vazia(self) -> None:
        linhas = [
            registro("C100", 26, **{"25": "0,00", "26": "0,00"}),
            registro(
                "C170",
                35,
                **{
                    "24": "03", "27": "10", "28": "0,25", "29": "0,00",
                    "30": "03", "33": "10", "34": "1,10", "35": "0,00",
                },
            ),
            "|C990|3|\n",
        ]

        resultado = RecalculadorPISCOFINS().recalcular(
            linhas, {(2, "PIS"), (2, "COFINS")}, "EFD Contribuições"
        )

        self.assertEqual(campo(resultado.linhas[1], 29), "2,50")
        self.assertEqual(campo(resultado.linhas[1], 35), "11,00")
        self.assertEqual(campo(resultado.linhas[0], 25), "2,50")
        self.assertEqual(campo(resultado.linhas[0], 26), "11,00")

    def test_preserva_valor_quando_nao_ha_base_suficiente(self) -> None:
        linhas = [
            registro("C100", 26, **{"25": "1,65", "26": "7,60"}),
            registro(
                "C170",
                35,
                **{"24": "01", "26": "1,65", "29": "1,65"},
            ),
        ]

        resultado = RecalculadorPISCOFINS().recalcular(
            linhas, {(2, "PIS")}, "EFD Contribuições"
        )

        self.assertEqual(campo(resultado.linhas[1], 29), "1,65")
        self.assertEqual(resultado.alteracoes, [])
        self.assertTrue(any("não há base/alíquota" in aviso for aviso in resultado.avisos))
        self.assertFalse(resultado.requer_reapuracao_bloco_m)

    def test_nao_altera_outro_tipo_de_sped(self) -> None:
        linhas = [
            registro("C100", 26, **{"25": "1,65"}),
            registro("C170", 35, **{"25": "100", "26": "0", "29": "1,65"}),
        ]
        resultado = RecalculadorPISCOFINS().recalcular(
            linhas, {(2, "PIS")}, "EFD ICMS/IPI"
        )
        self.assertEqual(resultado.linhas, linhas)
        self.assertEqual(resultado.alteracoes, [])
        self.assertTrue(resultado.avisos)

    def test_integracao_com_correcao_tributaria(self) -> None:
        linhas = [
            registro("C100", 26, **{"25": "1,65", "26": "7,60"}),
            registro(
                "C170",
                35,
                **{
                    "24": "01", "25": "100,00", "26": "1,65", "29": "1,65",
                    "30": "01", "31": "100,00", "32": "7,60", "35": "7,60",
                },
            ),
        ]
        proposta = PropostaCorrecaoTributaria(
            identificador=1,
            selecionada=True,
            modo="Regra aderente — confirmar",
            origem="FICHA TRIBUTÁRIA",
            nivel="ERRO",
            registro="C170",
            numero_linha=2,
            documento="123",
            item="1",
            codigo="ABC",
            ncm="12345678",
            campo="Alíquota PIS",
            campo_sped="ALIQ_PIS",
            valor_atual="1,65",
            valor_sugerido="0",
            regra_id="1",
            aderencia=100,
            justificativa="Teste",
            indice_campo=26,
        )
        preparacao = ResultadoPreparacaoCorrecaoTributaria([proposta])
        auditoria = ResultadoAuditoriaTributaria(contexto={})
        pre = ResultadoPreValidacaoPVA(tipo_sped="EFD Contribuições", total_linhas=2)

        with tempfile.TemporaryDirectory() as pasta:
            saida = Path(pasta) / "corrigido.txt"
            with (
                patch(
                    "src.sped.corretor_tributario_assistido.AuditorTributarioSPED.auditar",
                    return_value=ResultadoAuditoriaTributaria(contexto={}),
                ),
                patch(
                    "src.sped.corretor_tributario_assistido.PreValidadorPVA.validar",
                    return_value=pre,
                ),
            ):
                resultado = CorretorTributarioAssistido().aplicar(
                    linhas=linhas,
                    encoding="utf-8",
                    tipo_sped="EFD Contribuições",
                    empresa_sped="EMPRESA TESTE",
                    auditoria_antes=auditoria,
                    preparacao=preparacao,
                    caminho_saida=saida,
                )

            gravadas = saida.read_text(encoding="utf-8").splitlines(keepends=True)
            self.assertEqual(campo(gravadas[1], 26), "0")
            self.assertEqual(campo(gravadas[1], 29), "0,00")
            self.assertEqual(campo(gravadas[0], 25), "0,00")
            self.assertEqual(resultado.total_confirmadas, 1)
            self.assertEqual(resultado.total_recalculadas, 2)
            self.assertTrue(resultado.requer_reapuracao_bloco_m)
            self.assertTrue(resultado.caminho_relatorio.exists())


if __name__ == "__main__":
    unittest.main()
