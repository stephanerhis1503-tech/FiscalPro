"""Guarda de segurança antes do fluxo SPED -> Excel.

Hotfix 17.7.1

Evita exportar uma EFD Contribuições ainda "crua" do ERP quando existem
movimentos de crédito nos documentos, mas o Bloco M ainda não foi apurado no
PGE.  O objetivo é impedir que o usuário faça milhares de alterações no Excel
e só descubra no retorno Excel -> TXT que M100/M500/M105/M505 não existiam na
base original.

A validação é deliberadamente conservadora:
* não bloqueia SPED Fiscal;
* não exige M100/M500 quando não há evidência de crédito no arquivo;
* bloqueia quando há crédito documentado (CST 50..66 com base/valor positivo)
  e os respectivos registros de apuração não existem;
* bloqueia quando o Bloco M está ausente ou marcado como "sem movimento" apesar
  de haver movimento tributário relevante nos documentos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Iterable


@dataclass(slots=True)
class DiagnosticoApuracaoBlocoM:
    aplicavel: bool = False
    bloqueado: bool = False
    motivos: list[str] = field(default_factory=list)
    creditos_pis: int = 0
    creditos_cofins: int = 0
    movimentos_tributarios: int = 0
    qtd_m001: int = 0
    qtd_m100: int = 0
    qtd_m105: int = 0
    qtd_m500: int = 0
    qtd_m505: int = 0
    ind_mov_m001: str = ""

    @property
    def apurado_para_excel(self) -> bool:
        return self.aplicavel and not self.bloqueado

    def mensagem_bloqueio(self) -> str:
        detalhes = "\n".join(f"• {motivo}" for motivo in self.motivos)
        contagens = (
            f"M100: {self.qtd_m100} | M105: {self.qtd_m105} | "
            f"M500: {self.qtd_m500} | M505: {self.qtd_m505}"
        )
        return (
            "O FiscalPro detectou que esta EFD Contribuições ainda não está "
            "pronta para o fluxo SPED → Excel.\n\n"
            "O Bloco M aparenta não ter sido apurado no PGE.\n\n"
            f"{detalhes}\n\n"
            f"Registros encontrados: {contagens}.\n\n"
            "Para evitar perder alterações no Excel:\n"
            "1. Abra este SPED no PGE da EFD-Contribuições.\n"
            "2. Execute Gerar Apurações.\n"
            "3. Valide e salve/exporte a escrituração apurada.\n"
            "4. Abra o novo TXT no FiscalPro e só então exporte para Excel.\n\n"
            "A exportação foi bloqueada por segurança."
        )


class ValidadorApuracaoBlocoM:
    """Detecta EFD Contribuições com Bloco M ainda não apurado."""

    CST_CREDITO = {f"{n:02d}" for n in range(50, 67)}
    CST_TRIBUTADO = {"01", "02", "03"}

    # Índices considerando 0 = código do registro, sem os separadores externos.
    FONTES = {
        "A170": {
            "PIS": (8, 9, 11),
            "COFINS": (12, 13, 15),
        },
        "C170": {
            "PIS": (24, 25, 29),
            "COFINS": (30, 31, 35),
        },
        "D101": {
            "PIS": (3, 5, 7),
        },
        "D105": {
            "COFINS": (3, 5, 7),
        },
    }

    def validar(self, linhas: Iterable[str], tipo_sped: str) -> DiagnosticoApuracaoBlocoM:
        resultado = DiagnosticoApuracaoBlocoM()
        if str(tipo_sped or "").strip().upper() != "EFD CONTRIBUIÇÕES":
            return resultado

        resultado.aplicavel = True
        contagens: dict[str, int] = {}
        primeiro_m001: list[str] | None = None

        for linha in linhas:
            campos = self._campos(linha)
            if not campos:
                continue
            registro = campos[0].upper()
            contagens[registro] = contagens.get(registro, 0) + 1

            if registro == "M001" and primeiro_m001 is None:
                primeiro_m001 = campos

            mapa = self.FONTES.get(registro)
            if not mapa:
                continue

            encontrou_movimento_linha = False
            for tributo, (idx_cst, idx_base, idx_valor) in mapa.items():
                cst = self._campo(campos, idx_cst)
                base = self._decimal(self._campo(campos, idx_base))
                valor = self._decimal(self._campo(campos, idx_valor))
                tem_valor = base > 0 or valor > 0

                if tem_valor or cst in self.CST_CREDITO or cst in self.CST_TRIBUTADO:
                    encontrou_movimento_linha = True

                if cst in self.CST_CREDITO and tem_valor:
                    if tributo == "PIS":
                        resultado.creditos_pis += 1
                    else:
                        resultado.creditos_cofins += 1

            if encontrou_movimento_linha:
                resultado.movimentos_tributarios += 1

        resultado.qtd_m001 = contagens.get("M001", 0)
        resultado.qtd_m100 = contagens.get("M100", 0)
        resultado.qtd_m105 = contagens.get("M105", 0)
        resultado.qtd_m500 = contagens.get("M500", 0)
        resultado.qtd_m505 = contagens.get("M505", 0)
        if primeiro_m001:
            resultado.ind_mov_m001 = self._campo(primeiro_m001, 1)

        motivos: list[str] = []

        if resultado.movimentos_tributarios and resultado.qtd_m001 == 0:
            motivos.append("Há movimento tributário nos documentos, mas o registro M001 não existe.")

        if resultado.movimentos_tributarios and resultado.ind_mov_m001 == "1":
            motivos.append(
                "O M001 está marcado como bloco sem dados (IND_MOV=1), apesar de existirem movimentos tributários."
            )

        if resultado.creditos_pis:
            if resultado.qtd_m100 == 0:
                motivos.append(
                    f"Foram encontrados {resultado.creditos_pis} item(ns) com crédito de PIS, mas nenhum M100 foi encontrado."
                )
            elif resultado.qtd_m105 == 0:
                motivos.append(
                    "Existe M100, mas nenhum M105 foi encontrado para detalhar as bases de crédito de PIS."
                )

        if resultado.creditos_cofins:
            if resultado.qtd_m500 == 0:
                motivos.append(
                    f"Foram encontrados {resultado.creditos_cofins} item(ns) com crédito de COFINS, mas nenhum M500 foi encontrado."
                )
            elif resultado.qtd_m505 == 0:
                motivos.append(
                    "Existe M500, mas nenhum M505 foi encontrado para detalhar as bases de crédito de COFINS."
                )

        resultado.motivos = motivos
        resultado.bloqueado = bool(motivos)
        return resultado

    @staticmethod
    def _campos(linha: str) -> list[str]:
        texto = str(linha or "").rstrip("\r\n")
        if not texto:
            return []
        if texto.startswith("|"):
            texto = texto[1:]
        if texto.endswith("|"):
            texto = texto[:-1]
        return texto.split("|") if texto else []

    @staticmethod
    def _campo(campos: list[str], indice: int) -> str:
        if 0 <= indice < len(campos):
            return str(campos[indice] or "").strip()
        return ""

    @staticmethod
    def _decimal(valor: str) -> Decimal:
        texto = str(valor or "").strip()
        if not texto:
            return Decimal("0")
        try:
            return Decimal(texto.replace(".", "").replace(",", "."))
        except (InvalidOperation, ValueError):
            return Decimal("0")
