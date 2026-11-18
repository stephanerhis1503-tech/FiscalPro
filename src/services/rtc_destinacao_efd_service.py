"""Cruzamento opcional EFD ICMS/IPI (C100/C170) x XMLs RTC por chave e item.

Leitura somente: nunca altera arquivos, bancos, XMLs, creditos ou apuracoes.
O CFOP de entrada do adquirente NAO e o CFOP de saida do fornecedor.
Destino contabil nao determina, isoladamente, direito a credito IBS/CBS.

Referencias:
https://www.confaz.fazenda.gov.br/legislacao/ajustes/2022/ajuste-3-22
https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


USO_CONSUMO = frozenset({"1556", "2556", "3556"})
ATIVO = frozenset({"1551", "2551", "3551"})
REVENDA = frozenset({"1102", "2102", "3102"})
CHAVE_RE = re.compile(r"\d{44}")
CFOP_RE = re.compile(r"\d{4}")
ITEM_RE = re.compile(r"\d+")


def _digitos(valor: object) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def _num_item(valor: object) -> str:
    texto = str(valor or "").strip()
    if not ITEM_RE.fullmatch(texto):
        return ""
    return str(int(texto))


@dataclass
class MapaDestinacaoEFD:
    """Mapa da escrituracao de entrada; dados so de memoria, nenhuma gravacao."""

    cnpj: str
    competencia: str
    origem: str
    itens_cfop: dict[tuple[str, str], str]
    documentos: set[str]
    conflitos: set[tuple[str, str]]

    def localizar(self, item: dict) -> dict[str, str]:
        if str(item.get("direcao") or "").strip().upper() != "ENTRADA":
            return {
                "cfop_entrada": "", "destinacao": "NAO SE APLICA",
                "situacao": "SAIDA - CFOP do XML e do fornecedor",
            }
        chave = _digitos(item.get("chave_nfe"))
        numero = _num_item(item.get("numero_item"))
        if len(chave) != 44 or not numero:
            return {
                "cfop_entrada": "", "destinacao": "A CONFERIR",
                "situacao": "CHAVE OU NUMERO DO ITEM INVALIDO",
            }
        key = (chave, numero)
        if key in self.conflitos:
            return {
                "cfop_entrada": "", "destinacao": "A CONFERIR",
                "situacao": "CFOP DIVERGENTE PARA A MESMA CHAVE E ITEM",
            }
        cfop = self.itens_cfop.get(key)
        if cfop is None:
            return {
                "cfop_entrada": "", "destinacao": "A CONFERIR",
                "situacao": (
                    "ITEM NAO ENCONTRADO NO C170"
                    if chave in self.documentos else
                    "CHAVE DA ENTRADA NAO ENCONTRADA NO C100"
                ),
            }
        if cfop in USO_CONSUMO:
            destino = "USO E CONSUMO (CFOP EFD)"
        elif cfop in ATIVO:
            destino = "ATIVO IMOBILIZADO (CFOP EFD)"
        elif cfop in REVENDA:
            destino = "REVENDA (CFOP EFD)"
        else:
            destino = "OUTRA ENTRADA (CONFERIR)"
        return {
            "cfop_entrada": cfop, "destinacao": destino,
            "situacao": "CHAVE + ITEM CONFERIDOS NO SPED",
        }


def ler_efd_icms_ipi(
    arquivo: str | Path, *, cnpj_esperado: str, competencia_esperada: str,
) -> MapaDestinacaoEFD:
    """Le .txt da EFD ICMS/IPI validando estabelecimento e periodo.

    Registro 0000: CNPJ campo 07, DT_INI 04, DT_FIN 05 (indices da
    linha split por |). C100 entrada modelo 55, CHV_NFE campo 09;
    C170 NUM_ITEM campo 02, CFOP campo 11.
    """
    caminho = Path(arquivo)
    if caminho.suffix.lower() != ".txt":
        raise ValueError("Selecione o SPED Fiscal ICMS/IPI em arquivo TXT.")
    if not caminho.is_file():
        raise ValueError("Arquivo SPED Fiscal TXT nao encontrado.")
    if caminho.stat().st_size == 0:
        raise ValueError("O arquivo SPED Fiscal TXT esta vazio.")
    cnpj_esperado = _digitos(cnpj_esperado)
    if len(cnpj_esperado) != 14:
        raise ValueError("CNPJ de destino invalido para a conferencia.")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", competencia_esperada):
        raise ValueError("Competencia invalida para a conferencia EFD.")
    periodo = competencia_esperada.replace("-", "")
    encontrados: dict[tuple[str, str], str] = {}
    documentos: set[str] = set()
    conflitos: set[tuple[str, str]] = set()
    cabecalho = False
    ativo = ""
    qtde_c100 = 0

    # O SPED pode ter codificacao Windows-1252. Separadores/CFOP/chaves sao
    # ASCII e sobrevivem ao uso de replace sem modificar o arquivo original.
    with caminho.open("r", encoding="utf-8-sig", errors="replace") as f:
        for linha in f:
            if not linha.startswith("|"):
                continue
            col = linha.rstrip("\r\n").split("|")
            if len(col) < 3:
                continue
            reg = col[1]
            if reg == "0000":
                if cabecalho:
                    raise ValueError("Mais de um registro 0000 no SPED selecionado.")
                if len(col) <= 7:
                    raise ValueError("Registro 0000 incompleto no SPED selecionado.")
                cnpj = _digitos(col[7])
                if cnpj != cnpj_esperado:
                    raise ValueError(
                        "CNPJ do SPED Fiscal diferente da empresa selecionada. "
                        "Nao e permitido cruzar dados de empresas diferentes."
                    )
                for data in (col[4], col[5]):
                    if not re.fullmatch(r"\d{8}", data) or data[4:8]+data[2:4] != periodo:
                        raise ValueError(
                            "O periodo do SPED Fiscal e diferente da competencia RTC. "
                            "Selecione a EFD ICMS/IPI do mesmo mes."
                        )
                cabecalho = True
                ativo = ""
                continue
            if not cabecalho:
                continue
            if reg == "C100":
                ativo = ""
                qtde_c100 += 1
                if len(col) > 9 and col[2] == "0" and col[5] == "55":
                    chave = col[9].strip()
                    if CHAVE_RE.fullmatch(chave):
                        ativo = chave
                        documentos.add(chave)
                continue
            if reg == "C170" and ativo and len(col) > 11:
                numero = _num_item(col[2])
                cfop = col[11].strip()
                if not numero or not CFOP_RE.fullmatch(cfop):
                    continue
                key = (ativo, numero)
                if key in conflitos:
                    continue
                anterior = encontrados.get(key)
                if anterior is not None and anterior != cfop:
                    conflitos.add(key)
                    encontrados.pop(key, None)
                    continue
                encontrados[key] = cfop

    if not cabecalho:
        raise ValueError("Registro 0000 nao localizado: arquivo SPED invalido.")
    if qtde_c100 == 0:
        raise ValueError(
            "Nenhum C100 localizado. Selecione o SPED Fiscal (EFD ICMS/IPI), "
            "nao o SPED Contribuicoes."
        )
    return MapaDestinacaoEFD(
        cnpj=cnpj_esperado, competencia=competencia_esperada,
        origem=caminho.name, itens_cfop=encontrados,
        documentos=documentos, conflitos=conflitos,
    )
