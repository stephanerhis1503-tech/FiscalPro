"""Auditoria e correção segura da exclusão do ICMS-ST nas saídas.

Hotfix 17.8.24 — SPED final cumulativo na Etapa 2.

A auditoria SPED + XML permanece conservadora. A geração do SPED final só
é liberada quando não há pendências de vínculo/base e todos os candidatos são
C170 com vínculo XML de confiança ALTA. O arquivo selecionado é tratado como
base cumulativa: qualquer correção anterior já existente nele é preservada, e a
Etapa 2 acrescenta apenas os ajustes confirmados de saída. O C100 é retotalizado,
o Bloco M é sincronizado pelo delta, o Pré-PVA é comparado e o arquivo final é
reauditado antes de ser gravado.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Optional
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from src.sped.pre_validador import PreValidadorPVA
from src.sped.reapurador_bloco_m import ReapuradorBlocoM
from src.sped.recalculador_piscofins import RecalculadorPISCOFINS


STATUS_CANDIDATO_XML = "CANDIDATO — CFOP 5405; VALIDAR COM XML"
STATUS_ALIQUOTA_ZERO = "SEM IMPACTO — PIS/COFINS ALÍQUOTA ZERO"
STATUS_REVISAR_BASE = "REVISAR — BASE/CST NO SPED"
STATUS_CORRIGIR_ST = "CORRIGIR — ST DESTACADO AINDA NA BASE"
STATUS_OK_ST_FORA = "OK — ST JÁ FORA DA BASE"
STATUS_SEM_ST_XML = "SEM VALOR ST NO XML — NÃO CORRIGIR AUTOMATICAMENTE"
STATUS_XML_NAO_LOCALIZADO = "REVISAR — XML NÃO LOCALIZADO"
STATUS_VINCULO_XML = "REVISAR — VÍNCULO XML"
STATUS_COMPOSICAO_BASE = "REVISAR — COMPOSIÇÃO DA BASE"

ACAO_CANDIDATO_XML = (
    "Operação de saída com CFOP 5405 e base de PIS/COFINS no SPED. "
    "Validar com os XMLs de saída antes de qualquer correção."
)
ACAO_ALIQUOTA_ZERO = (
    "Registro com PIS/COFINS a alíquota zero. Não há base tributada a reduzir nesta etapa."
)
ACAO_REVISAR_BASE = (
    "CFOP 5405 localizado, mas a combinação de CST/base não foi reconhecida como tributada nem como alíquota zero."
)
ACAO_CORRIGIR_ST = (
    "O XML autorizado informa ICMS-ST retido e a base do SPED permanece igual à base do XML/valor da operação. "
    "A auditoria sugere reduzir a base pelo vICMSSTRet; nenhuma alteração é aplicada automaticamente."
)
ACAO_OK_ST_FORA = (
    "O XML informa ICMS-ST retido e a base do SPED já reflete a retirada desse valor. Não excluir novamente."
)
ACAO_SEM_ST_XML = (
    "A operação é tributada e possui CFOP 5405, porém o XML de saída não informa valor positivo em vICMSSTRet. "
    "Sem esse valor documental, o FiscalPro não calcula exclusão automática."
)
ACAO_XML_NAO_LOCALIZADO = (
    "A chave do documento do SPED não foi localizada entre os XMLs autorizados selecionados."
)
ACAO_VINCULO_XML = (
    "O documento foi localizado no XML, mas o item/agrupamento não pôde ser vinculado com segurança ao registro do SPED."
)
ACAO_COMPOSICAO_BASE = (
    "Há ICMS-ST retido no XML, mas a relação entre valor da operação, base XML e base SPED não permite afirmar com segurança "
    "se o ST já foi excluído. Revisar manualmente."
)

_CSTS_ALIQUOTA_ZERO = {"04", "06", "07", "08", "09"}
_CFOP_SUBSTITUIDO = "5405"
_NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
_TOL = Decimal("0.02")
_TOL_OPERACAO = Decimal("0.05")


@dataclass(frozen=True)
class RegistroPreAuditoriaSaidas:
    status: str
    acao: str
    linha_sped: int
    registro: str
    modelo: str
    numero_documento: str
    chave_nfe: str
    data: str
    participante: str
    item: str
    codigo_item: str
    descricao: str
    cfop: str
    cst_icms: str
    valor_operacao: Decimal
    cst_pis: str
    base_pis: Decimal
    aliquota_pis: Decimal
    valor_pis: Decimal
    cst_cofins: str
    base_cofins: Decimal
    aliquota_cofins: Decimal
    valor_cofins: Decimal
    valor_st_xml: Decimal = Decimal("0")
    base_pis_xml: Decimal = Decimal("0")
    base_cofins_xml: Decimal = Decimal("0")
    valor_operacao_xml: Decimal = Decimal("0")
    base_pis_sugerida: Decimal = Decimal("0")
    valor_pis_sugerido: Decimal = Decimal("0")
    base_cofins_sugerida: Decimal = Decimal("0")
    valor_cofins_sugerido: Decimal = Decimal("0")
    xml_encontrado: bool = False
    origem_xml: str = ""
    confianca_vinculo: str = ""


@dataclass
class ResultadoPreAuditoriaSaidas:
    registros: list[RegistroPreAuditoriaSaidas]
    documentos_saida: int
    documentos_cfop_5405: int
    outras_operacoes: dict[str, int]
    documentos_xml_autorizados: int = 0
    arquivos_xml_lidos: int = 0
    auditoria_com_xml: bool = False

    def resumo(self) -> dict:
        por_status: dict[str, int] = {}
        por_registro: dict[str, int] = {}
        base_pis_candidata = Decimal("0")
        base_cofins_candidata = Decimal("0")
        valor_operacao = Decimal("0")
        st_corrigir = Decimal("0")
        reducao_pis = Decimal("0")
        reducao_cofins = Decimal("0")
        for item in self.registros:
            por_status[item.status] = por_status.get(item.status, 0) + 1
            por_registro[item.registro] = por_registro.get(item.registro, 0) + 1
            valor_operacao += item.valor_operacao
            if item.status == STATUS_CANDIDATO_XML:
                base_pis_candidata += item.base_pis
                base_cofins_candidata += item.base_cofins
            if item.status == STATUS_CORRIGIR_ST:
                st_corrigir += item.valor_st_xml
                reducao_pis += max(Decimal("0"), item.valor_pis - item.valor_pis_sugerido)
                reducao_cofins += max(Decimal("0"), item.valor_cofins - item.valor_cofins_sugerido)
        revisar_xml = sum(
            por_status.get(s, 0)
            for s in (STATUS_XML_NAO_LOCALIZADO, STATUS_VINCULO_XML, STATUS_COMPOSICAO_BASE, STATUS_REVISAR_BASE)
        )
        return {
            "documentos_saida": self.documentos_saida,
            "documentos_cfop_5405": self.documentos_cfop_5405,
            "registros_5405": len(self.registros),
            "candidatos_xml": por_status.get(STATUS_CANDIDATO_XML, 0),
            "aliquota_zero": por_status.get(STATUS_ALIQUOTA_ZERO, 0),
            "revisar": por_status.get(STATUS_REVISAR_BASE, 0),
            "corrigir": por_status.get(STATUS_CORRIGIR_ST, 0),
            "ok_st_fora": por_status.get(STATUS_OK_ST_FORA, 0),
            "sem_st_xml": por_status.get(STATUS_SEM_ST_XML, 0),
            "xml_nao_localizado": por_status.get(STATUS_XML_NAO_LOCALIZADO, 0),
            "vinculo_xml": por_status.get(STATUS_VINCULO_XML, 0),
            "composicao_base": por_status.get(STATUS_COMPOSICAO_BASE, 0),
            "revisar_xml": revisar_xml,
            "c170": por_registro.get("C170", 0),
            "c175": por_registro.get("C175", 0),
            "valor_operacao_5405": valor_operacao,
            "base_pis_candidata": base_pis_candidata,
            "base_cofins_candidata": base_cofins_candidata,
            "st_corrigir": st_corrigir,
            "reducao_pis": reducao_pis,
            "reducao_cofins": reducao_cofins,
            "documentos_xml_autorizados": self.documentos_xml_autorizados,
            "arquivos_xml_lidos": self.arquivos_xml_lidos,
            "auditoria_com_xml": self.auditoria_com_xml,
        }


@dataclass(frozen=True)
class ResultadoCorrecaoSaidas:
    caminho_saida: Path
    caminho_log: Path
    itens_corrigidos: int
    documentos_retotalizados: int
    alteracoes_documentais: int
    alteracoes_bloco_m: int
    st_excluido: Decimal
    reducao_pis: Decimal
    reducao_cofins: Decimal
    erros_pre_pva_antes: int
    erros_pre_pva_depois: int
    novos_erros_pre_pva: int
    ok_st_fora_apos: int
    corrigir_apos: int
    revisar_apos: int
    avisos: tuple[str, ...] = ()


@dataclass
class _ItemXML:
    n_item: str
    codigo: str
    descricao: str
    cfop: str
    valor_operacao: Decimal
    cst_pis: str
    base_pis: Decimal
    aliq_pis: Decimal
    valor_pis: Decimal
    cst_cofins: str
    base_cofins: Decimal
    aliq_cofins: Decimal
    valor_cofins: Decimal
    valor_st: Decimal


@dataclass
class _GrupoXML:
    valor_operacao: Decimal = Decimal("0")
    base_pis: Decimal = Decimal("0")
    base_cofins: Decimal = Decimal("0")
    valor_st: Decimal = Decimal("0")
    quantidade: int = 0


@dataclass
class _DocumentoXML:
    chave: str
    modelo: str
    numero: str
    origem: str
    itens: dict[str, _ItemXML]
    grupos: dict[tuple[str, str], _GrupoXML]


class AuditoriaICMSSTPISCOFINSSaidasService:
    """Etapa 2: pré-auditoria pelo SPED e auditoria segura com XMLs de saída."""


    @classmethod
    def sugerir_nome_sped_final(cls, caminho_sped: str) -> str:
        """Sugere um único nome final, evitando encadear sufixos das etapas.

        O arquivo selecionado pode ser o SPED original ou um arquivo intermediário
        já corrigido por uma etapa anterior. O nome final fica estável para que o
        usuário tenha um único TXT definitivo para validar no PGE/PVA.
        """
        stem = Path(caminho_sped).stem.strip() or "SPED"
        padroes = (
            r"_ICMS_ST_ENTRADAS_CORRIGIDO(?:_PVA)?$",
            r"_ICMS_ST_SAIDAS_CORRIGIDO(?:_PVA)?$",
            r"_FINAL_CORRIGIDO(?:_PVA)?$",
        )
        anterior = None
        while anterior != stem:
            anterior = stem
            for padrao in padroes:
                stem = re.sub(padrao, "", stem, flags=re.IGNORECASE)
        return f"{stem}_FINAL_CORRIGIDO.txt"

    @classmethod
    def pre_auditar(
        cls,
        caminho_sped: str,
        progresso: Optional[Callable[[str], None]] = None,
    ) -> ResultadoPreAuditoriaSaidas:
        sped = Path(caminho_sped)
        if not sped.is_file():
            raise FileNotFoundError("Selecione um arquivo SPED Contribuições válido.")

        cls._progresso(progresso, "Lendo o SPED Contribuições e identificando as saídas...")
        participantes: dict[str, str] = {}
        registros: list[RegistroPreAuditoriaSaidas] = []
        documentos_saida: set[tuple[str, str]] = set()
        documentos_5405: set[tuple[str, str]] = set()
        outras_operacoes: dict[str, int] = {}

        atual: dict | None = None
        with sped.open("r", encoding="latin-1", errors="replace") as arquivo:
            for numero_linha, linha in enumerate(arquivo, start=1):
                campos = linha.rstrip("\r\n").split("|")
                if len(campos) < 2:
                    continue
                registro = campos[1]

                if registro == "0150":
                    if len(campos) > 3 and campos[2]:
                        participantes[campos[2].strip()] = campos[3].strip()
                    continue

                if registro == "C100":
                    atual = None
                    if len(campos) <= 12 or campos[2] != "1":
                        continue
                    modelo = campos[5].strip() if len(campos) > 5 else ""
                    situacao = campos[6].strip() if len(campos) > 6 else ""
                    numero = campos[8].strip() if len(campos) > 8 else ""
                    chave = campos[9].strip() if len(campos) > 9 else ""
                    data = campos[10].strip() if len(campos) > 10 else ""
                    cod_part = campos[4].strip() if len(campos) > 4 else ""
                    atual = {
                        "modelo": modelo,
                        "situacao": situacao,
                        "numero": numero,
                        "chave": chave,
                        "data": data,
                        "cod_part": cod_part,
                    }
                    documentos_saida.add((modelo, chave or numero))
                    continue

                if atual is None:
                    continue

                if registro == "C170":
                    if len(campos) < 37:
                        continue
                    cfop = campos[11].strip()
                    if not cfop:
                        continue
                    if cfop != _CFOP_SUBSTITUIDO:
                        outras_operacoes[cfop] = outras_operacoes.get(cfop, 0) + 1
                        continue
                    documentos_5405.add((atual["modelo"], atual["chave"] or atual["numero"]))
                    cst_pis = campos[25].strip()
                    base_pis = cls._decimal_sped(campos[26])
                    aliq_pis = cls._decimal_sped(campos[27])
                    cst_cofins = campos[31].strip()
                    base_cofins = cls._decimal_sped(campos[32])
                    aliq_cofins = cls._decimal_sped(campos[33])
                    status, acao = cls._classificar(cst_pis, base_pis, aliq_pis, cst_cofins, base_cofins, aliq_cofins)
                    registros.append(
                        RegistroPreAuditoriaSaidas(
                            status=status,
                            acao=acao,
                            linha_sped=numero_linha,
                            registro="C170",
                            modelo=atual["modelo"],
                            numero_documento=atual["numero"],
                            chave_nfe=atual["chave"],
                            data=atual["data"],
                            participante=participantes.get(atual["cod_part"], ""),
                            item=campos[2].strip(),
                            codigo_item=campos[3].strip(),
                            descricao=campos[4].strip(),
                            cfop=cfop,
                            cst_icms=campos[10].strip(),
                            valor_operacao=cls._decimal_sped(campos[7]),
                            cst_pis=cst_pis,
                            base_pis=base_pis,
                            aliquota_pis=aliq_pis,
                            valor_pis=cls._decimal_sped(campos[30]),
                            cst_cofins=cst_cofins,
                            base_cofins=base_cofins,
                            aliquota_cofins=aliq_cofins,
                            valor_cofins=cls._decimal_sped(campos[36]),
                        )
                    )
                    continue

                if registro == "C175":
                    if len(campos) < 17:
                        continue
                    cfop = campos[2].strip()
                    if not cfop:
                        continue
                    if cfop != _CFOP_SUBSTITUIDO:
                        outras_operacoes[cfop] = outras_operacoes.get(cfop, 0) + 1
                        continue
                    documentos_5405.add((atual["modelo"], atual["chave"] or atual["numero"]))
                    cst_pis = campos[5].strip()
                    base_pis = cls._decimal_sped(campos[6])
                    aliq_pis = cls._decimal_sped(campos[7])
                    cst_cofins = campos[11].strip()
                    base_cofins = cls._decimal_sped(campos[12])
                    aliq_cofins = cls._decimal_sped(campos[13])
                    status, acao = cls._classificar(cst_pis, base_pis, aliq_pis, cst_cofins, base_cofins, aliq_cofins)
                    registros.append(
                        RegistroPreAuditoriaSaidas(
                            status=status,
                            acao=acao,
                            linha_sped=numero_linha,
                            registro="C175",
                            modelo=atual["modelo"],
                            numero_documento=atual["numero"],
                            chave_nfe=atual["chave"],
                            data=atual["data"],
                            participante=participantes.get(atual["cod_part"], ""),
                            item="",
                            codigo_item="",
                            descricao="Resumo analítico NFC-e (C175)",
                            cfop=cfop,
                            cst_icms="",
                            valor_operacao=cls._decimal_sped(campos[3]),
                            cst_pis=cst_pis,
                            base_pis=base_pis,
                            aliquota_pis=aliq_pis,
                            valor_pis=cls._decimal_sped(campos[10]),
                            cst_cofins=cst_cofins,
                            base_cofins=base_cofins,
                            aliquota_cofins=aliq_cofins,
                            valor_cofins=cls._decimal_sped(campos[16]),
                        )
                    )

        registros.sort(key=lambda r: (r.data, r.numero_documento.zfill(20), r.registro, r.item.zfill(10), r.linha_sped))
        cls._progresso(progresso, "Pré-auditoria concluída. Nenhum arquivo foi alterado.")
        return ResultadoPreAuditoriaSaidas(
            registros=registros,
            documentos_saida=len(documentos_saida),
            documentos_cfop_5405=len(documentos_5405),
            outras_operacoes=outras_operacoes,
        )

    @classmethod
    def auditar_com_xml(
        cls,
        caminho_sped: str,
        caminho_xml: str,
        progresso: Optional[Callable[[str], None]] = None,
    ) -> ResultadoPreAuditoriaSaidas:
        """Cruza a pré-auditoria do SPED com XMLs autorizados de saída, sem alterar arquivos."""
        pre = cls.pre_auditar(caminho_sped, progresso=progresso)
        cls._progresso(progresso, "Lendo XMLs autorizados de saída...")
        documentos_xml, arquivos_lidos = cls._carregar_xmls(caminho_xml, progresso)
        cls._progresso(progresso, "Cruzando SPED e XMLs por chave, item e agrupamento tributário...")

        enriquecidos: list[RegistroPreAuditoriaSaidas] = []
        for indice, item in enumerate(pre.registros, start=1):
            if indice % 500 == 0:
                cls._progresso(progresso, f"Cruzando registros... {indice}/{len(pre.registros)}")
            enriquecidos.append(cls._enriquecer_registro(item, documentos_xml.get(item.chave_nfe)))

        cls._progresso(progresso, "Auditoria SPED + XML concluída. Nenhum arquivo foi alterado.")
        return ResultadoPreAuditoriaSaidas(
            registros=enriquecidos,
            documentos_saida=pre.documentos_saida,
            documentos_cfop_5405=pre.documentos_cfop_5405,
            outras_operacoes=pre.outras_operacoes,
            documentos_xml_autorizados=len(documentos_xml),
            arquivos_xml_lidos=arquivos_lidos,
            auditoria_com_xml=True,
        )

    @classmethod
    def aplicar_correcoes(
        cls,
        caminho_sped: str,
        caminho_xml: str,
        resultado_auditoria: ResultadoPreAuditoriaSaidas,
        caminho_saida: str,
        progresso: Optional[Callable[[str], None]] = None,
    ) -> ResultadoCorrecaoSaidas:
        """Gera a EFD Contribuições FINAL corrigindo somente C170 confirmados.

        O arquivo informado em ``caminho_sped`` é a base cumulativa. Se ele já
        contiver correções de uma etapa anterior, elas são preservadas porque a
        rotina parte de uma cópia integral dessa base e altera somente os campos
        explicitamente confirmados nesta etapa.

        Regras de segurança:
        * o SPED base nunca é sobrescrito;
        * exige auditoria SPED + XML sem pendências de vínculo/base;
        * corrige somente registros C170 com vínculo ALTA e status confirmado;
        * atualiza bases/valores de PIS e COFINS, totais C100 e débitos do Bloco M;
        * roda o Pré-PVA antes/depois e aborta se surgir erro novo;
        * reaudita o arquivo gerado com os mesmos XMLs antes de gravá-lo.
        """
        origem = Path(caminho_sped)
        destino = Path(caminho_saida)
        if not origem.is_file():
            raise FileNotFoundError("Selecione um arquivo SPED Contribuições válido.")
        if not caminho_xml or not Path(caminho_xml).exists():
            raise FileNotFoundError("Selecione os mesmos XMLs usados na auditoria das saídas.")
        if not resultado_auditoria or not resultado_auditoria.auditoria_com_xml:
            raise ValueError("Execute primeiro a auditoria das saídas com os XMLs.")
        if origem.resolve() == destino.resolve():
            raise ValueError("O SPED base não pode ser sobrescrito. Escolha outro nome para o arquivo final corrigido.")

        resumo = resultado_auditoria.resumo()
        if resumo["revisar_xml"]:
            raise ValueError(
                f"Ainda existem {resumo['revisar_xml']} registro(s) para revisar. "
                "Resolva todas as pendências antes de aplicar correções."
            )
        candidatos = [x for x in resultado_auditoria.registros if x.status == STATUS_CORRIGIR_ST]
        if not candidatos:
            raise ValueError("A auditoria não possui itens confirmados para correção.")
        inseguros = [x for x in candidatos if x.registro != "C170" or x.confianca_vinculo != "ALTA"]
        if inseguros:
            raise ValueError(
                "A correção automática só é liberada para itens C170 com vínculo XML de confiança ALTA. "
                f"Há {len(inseguros)} item(ns) fora desse critério."
            )

        cls._progresso(progresso, "Validando o SPED original antes da correção...")
        texto_original = origem.read_bytes().decode("latin-1")
        linhas_antes = texto_original.splitlines(keepends=True)
        if not linhas_antes:
            raise ValueError("O arquivo SPED selecionado está vazio.")

        # Garante que o resultado da auditoria ainda corresponde ao arquivo selecionado.
        for item in candidatos:
            if item.linha_sped < 1 or item.linha_sped > len(linhas_antes):
                raise RuntimeError(f"Linha {item.linha_sped}: referência da auditoria não existe mais no SPED.")
            campos = cls._campos_sped(linhas_antes[item.linha_sped - 1])
            if not campos or campos[0].upper() != "C170":
                raise RuntimeError(f"Linha {item.linha_sped}: o registro esperado C170 foi alterado após a auditoria.")
            if cls._campo_sped(campos, 10) != _CFOP_SUBSTITUIDO:
                raise RuntimeError(f"Linha {item.linha_sped}: o CFOP não é mais 5405; refaça a auditoria.")
            if item.item and cls._campo_sped(campos, 1) != item.item:
                raise RuntimeError(f"Linha {item.linha_sped}: o número do item mudou após a auditoria.")
            if item.codigo_item and cls._campo_sped(campos, 2) != item.codigo_item:
                raise RuntimeError(f"Linha {item.linha_sped}: o código do item mudou após a auditoria.")
            if abs(cls._decimal_sped(cls._campo_sped(campos, 25)) - item.base_pis) > _TOL:
                raise RuntimeError(f"Linha {item.linha_sped}: a base de PIS mudou após a auditoria; audite novamente.")
            if abs(cls._decimal_sped(cls._campo_sped(campos, 31)) - item.base_cofins) > _TOL:
                raise RuntimeError(f"Linha {item.linha_sped}: a base de COFINS mudou após a auditoria; audite novamente.")

        pre_antes = PreValidadorPVA().validar(linhas_antes, "EFD Contribuições")
        linhas = list(linhas_antes)
        afetadas: set[tuple[int, str]] = set()
        st_total = Decimal("0")
        reducao_pis = Decimal("0")
        reducao_cofins = Decimal("0")

        cls._progresso(progresso, f"Aplicando {len(candidatos)} exclusão(ões) confirmada(s) de ICMS-ST...")
        for item in candidatos:
            indice = item.linha_sped - 1
            linhas[indice] = cls._substituir_campo_sped(
                linhas[indice], 25, cls._decimal_para_sped(item.base_pis_sugerida)
            )
            linhas[indice] = cls._substituir_campo_sped(
                linhas[indice], 31, cls._decimal_para_sped(item.base_cofins_sugerida)
            )
            afetadas.add((item.linha_sped, "PIS"))
            afetadas.add((item.linha_sped, "COFINS"))
            st_total += item.valor_st_xml
            reducao_pis += max(Decimal("0"), item.valor_pis - item.valor_pis_sugerido)
            reducao_cofins += max(Decimal("0"), item.valor_cofins - item.valor_cofins_sugerido)

        cls._progresso(progresso, "Recalculando PIS/COFINS dos itens e retotalizando os C100 afetados...")
        recalculo = RecalculadorPISCOFINS().recalcular(linhas, afetadas, "EFD Contribuições")

        cls._progresso(progresso, "Sincronizando os débitos do Bloco M pelo delta confirmado...")
        reapuracao = ReapuradorBlocoM().sincronizar(linhas_antes, recalculo.linhas, "EFD Contribuições")
        if reapuracao.avisos:
            raise RuntimeError(
                "Correção cancelada: o Bloco M não pôde ser sincronizado com segurança. "
                + " ".join(reapuracao.avisos)
            )
        linhas_finais = reapuracao.linhas

        cls._progresso(progresso, "Executando Pré-PVA comparativo antes de gerar o arquivo...")
        pre_depois = PreValidadorPVA().validar(linhas_finais, "EFD Contribuições")
        assinaturas_antes = {cls._assinatura_erro_pva(x) for x in pre_antes.erros}
        novos_erros = [x for x in pre_depois.erros if cls._assinatura_erro_pva(x) not in assinaturas_antes]
        if novos_erros:
            primeiro = novos_erros[0]
            raise RuntimeError(
                f"Correção cancelada: o Pré-PVA encontrou {len(novos_erros)} erro(s) novo(s). "
                f"Primeiro: {primeiro.registro} linha {primeiro.numero_linha or '-'} — {primeiro.mensagem}"
            )

        # Reaudita em arquivo temporário para provar que o ST corrigido passou a ficar fora da base.
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(destino.name + ".fiscalpro.tmp")
        try:
            temporario.write_bytes("".join(linhas_finais).encode("latin-1"))
            cls._progresso(progresso, "Reauditando o arquivo corrigido com os mesmos XMLs...")
            reauditoria = cls.auditar_com_xml(str(temporario), caminho_xml)
            resumo_final = reauditoria.resumo()
            if resumo_final["corrigir"]:
                raise RuntimeError(
                    f"Correção cancelada: a reaudição ainda encontrou {resumo_final['corrigir']} item(ns) com ST na base."
                )
            if resumo_final["revisar_xml"]:
                raise RuntimeError(
                    f"Correção cancelada: a reaudição gerou {resumo_final['revisar_xml']} pendência(s) de vínculo/base."
                )
            temporario.replace(destino)
        finally:
            if temporario.exists():
                temporario.unlink(missing_ok=True)

        avisos_recalculo = [
            x for x in recalculo.avisos
            if "Bloco M não foi alterado automaticamente" not in x
        ]
        avisos = tuple(dict.fromkeys(avisos_recalculo))
        caminho_log = destino.with_name(destino.stem + "_LOG.txt")
        cls._gravar_log_correcao(
            caminho_log, origem, destino, candidatos, recalculo.documentos_retotalizados,
            len(recalculo.alteracoes), len(reapuracao.alteracoes), pre_antes, pre_depois,
            resumo_final, avisos,
        )
        cls._progresso(progresso, "SPED FINAL corrigido gerado com segurança. O arquivo base foi preservado.")
        return ResultadoCorrecaoSaidas(
            caminho_saida=destino,
            caminho_log=caminho_log,
            itens_corrigidos=len(candidatos),
            documentos_retotalizados=recalculo.documentos_retotalizados,
            alteracoes_documentais=len(recalculo.alteracoes),
            alteracoes_bloco_m=len(reapuracao.alteracoes),
            st_excluido=st_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            reducao_pis=reducao_pis.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            reducao_cofins=reducao_cofins.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            erros_pre_pva_antes=len(pre_antes.erros),
            erros_pre_pva_depois=len(pre_depois.erros),
            novos_erros_pre_pva=0,
            ok_st_fora_apos=resumo_final["ok_st_fora"],
            corrigir_apos=resumo_final["corrigir"],
            revisar_apos=resumo_final["revisar_xml"],
            avisos=avisos,
        )

    @staticmethod
    def _assinatura_erro_pva(item) -> tuple:
        return (
            item.categoria, item.registro, item.numero_linha, item.campo,
            item.documento, item.codigo_item,
        )

    @staticmethod
    def _campos_sped(linha: str) -> list[str]:
        texto = linha.rstrip("\r\n")
        if not (texto.startswith("|") and texto.endswith("|")):
            return []
        partes = texto.split("|")
        return partes[1:-1]

    @staticmethod
    def _campo_sped(campos: list[str], indice: int) -> str:
        return campos[indice].strip() if 0 <= indice < len(campos) else ""

    @staticmethod
    def _substituir_campo_sped(linha: str, indice: int, valor: str) -> str:
        if linha.endswith("\r\n"):
            texto, fim = linha[:-2], "\r\n"
        elif linha.endswith("\n"):
            texto, fim = linha[:-1], "\n"
        elif linha.endswith("\r"):
            texto, fim = linha[:-1], "\r"
        else:
            texto, fim = linha, ""
        partes = texto.split("|")
        posicao = indice + 1
        if not (texto.startswith("|") and texto.endswith("|")) or posicao >= len(partes) - 1:
            raise RuntimeError(f"Não foi possível localizar o campo {indice} na linha SPED.")
        partes[posicao] = valor
        return "|".join(partes) + fim

    @staticmethod
    def _decimal_para_sped(valor: Decimal) -> str:
        numero = valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{numero:.2f}".replace(".", ",")

    @classmethod
    def _gravar_log_correcao(
        cls, caminho: Path, origem: Path, destino: Path, candidatos: list[RegistroPreAuditoriaSaidas],
        documentos_retotalizados: int, alteracoes_documentais: int, alteracoes_bloco_m: int,
        pre_antes, pre_depois, resumo_final: dict, avisos: tuple[str, ...],
    ) -> None:
        linhas = [
            "FiscalPro — Exclusão ICMS-ST da Base PIS/COFINS — Etapa 2",
            f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"SPED base cumulativo: {origem}",
            f"SPED FINAL corrigido: {destino}",
            "Correções já existentes no SPED base: preservadas; esta etapa altera somente os registros confirmados abaixo.",
            f"Itens corrigidos: {len(candidatos)}",
            f"ICMS-ST excluído das bases: R$ {sum((x.valor_st_xml for x in candidatos), Decimal('0')):.2f}",
            f"C100 retotalizados: {documentos_retotalizados}",
            f"Alterações documentais encadeadas: {alteracoes_documentais}",
            f"Alterações no Bloco M: {alteracoes_bloco_m}",
            f"Pré-PVA — erros antes: {len(pre_antes.erros)} | depois: {len(pre_depois.erros)} | novos: 0",
            f"Reauditoria — corrigir: {resumo_final['corrigir']} | revisar: {resumo_final['revisar_xml']} | OK ST fora: {resumo_final['ok_st_fora']}",
            "",
            "Itens alterados:",
        ]
        for x in candidatos:
            linhas.append(
                f"NF {x.numero_documento} | linha {x.linha_sped} | item {x.item} | código {x.codigo_item} | "
                f"ST R$ {x.valor_st_xml:.2f} | Base PIS {x.base_pis:.2f}->{x.base_pis_sugerida:.2f} | "
                f"Base COFINS {x.base_cofins:.2f}->{x.base_cofins_sugerida:.2f}"
            )
        if avisos:
            linhas.extend(["", "Avisos:", *[f"- {x}" for x in avisos]])
        caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    @classmethod
    def _enriquecer_registro(cls, item: RegistroPreAuditoriaSaidas, doc: _DocumentoXML | None) -> RegistroPreAuditoriaSaidas:
        # Alíquota zero permanece sem impacto tributário mesmo quando o XML não foi localizado.
        if item.status == STATUS_ALIQUOTA_ZERO:
            st = Decimal("0")
            origem = ""
            if doc:
                origem = doc.origem
                if item.registro == "C170":
                    xml_item, _ = cls._vincular_item(item, doc)
                    if xml_item:
                        st = xml_item.valor_st
                else:
                    grupo = doc.grupos.get((_CFOP_SUBSTITUIDO, "zero"))
                    if grupo:
                        st = grupo.valor_st
            return replace(item, valor_st_xml=st, xml_encontrado=bool(doc), origem_xml=origem, confianca_vinculo="ALTA" if doc else "")

        if item.status != STATUS_CANDIDATO_XML:
            return item
        if doc is None:
            return replace(item, status=STATUS_XML_NAO_LOCALIZADO, acao=ACAO_XML_NAO_LOCALIZADO)

        if item.registro == "C170":
            xml_item, confianca = cls._vincular_item(item, doc)
            if xml_item is None:
                return replace(
                    item,
                    status=STATUS_VINCULO_XML,
                    acao=ACAO_VINCULO_XML,
                    xml_encontrado=True,
                    origem_xml=doc.origem,
                    confianca_vinculo="BAIXA",
                )
            return cls._classificar_st_encontrado(
                item,
                valor_operacao_xml=xml_item.valor_operacao,
                base_pis_xml=xml_item.base_pis,
                base_cofins_xml=xml_item.base_cofins,
                valor_st=xml_item.valor_st,
                origem=doc.origem,
                confianca=confianca,
            )

        classe = cls._classe_tributaria(item.cst_pis, item.base_pis, item.aliquota_pis)
        grupo = doc.grupos.get((_CFOP_SUBSTITUIDO, classe))
        if grupo is None:
            return replace(
                item,
                status=STATUS_VINCULO_XML,
                acao=ACAO_VINCULO_XML,
                xml_encontrado=True,
                origem_xml=doc.origem,
                confianca_vinculo="BAIXA",
            )
        return cls._classificar_st_encontrado(
            item,
            valor_operacao_xml=grupo.valor_operacao,
            base_pis_xml=grupo.base_pis,
            base_cofins_xml=grupo.base_cofins,
            valor_st=grupo.valor_st,
            origem=doc.origem,
            confianca="ALTA" if abs(item.base_pis - grupo.base_pis) <= _TOL else "MÉDIA",
        )

    @classmethod
    def _classificar_st_encontrado(
        cls,
        item: RegistroPreAuditoriaSaidas,
        *,
        valor_operacao_xml: Decimal,
        base_pis_xml: Decimal,
        base_cofins_xml: Decimal,
        valor_st: Decimal,
        origem: str,
        confianca: str,
    ) -> RegistroPreAuditoriaSaidas:
        comuns = dict(
            valor_st_xml=valor_st,
            base_pis_xml=base_pis_xml,
            base_cofins_xml=base_cofins_xml,
            valor_operacao_xml=valor_operacao_xml,
            xml_encontrado=True,
            origem_xml=origem,
            confianca_vinculo=confianca,
        )
        if valor_st <= 0:
            return replace(item, status=STATUS_SEM_ST_XML, acao=ACAO_SEM_ST_XML, **comuns)

        sit_pis = cls._situacao_base(item.base_pis, base_pis_xml, valor_operacao_xml, valor_st)
        sit_cof = cls._situacao_base(item.base_cofins, base_cofins_xml, valor_operacao_xml, valor_st)
        if sit_pis == "fora" and sit_cof == "fora":
            return replace(item, status=STATUS_OK_ST_FORA, acao=ACAO_OK_ST_FORA, **comuns)
        if sit_pis == "incluido" and sit_cof == "incluido":
            base_pis_nova = max(Decimal("0"), item.base_pis - valor_st)
            base_cof_nova = max(Decimal("0"), item.base_cofins - valor_st)
            pis_novo = cls._calcular_contribuicao(base_pis_nova, item.aliquota_pis)
            cof_novo = cls._calcular_contribuicao(base_cof_nova, item.aliquota_cofins)
            return replace(
                item,
                status=STATUS_CORRIGIR_ST,
                acao=ACAO_CORRIGIR_ST,
                base_pis_sugerida=base_pis_nova,
                valor_pis_sugerido=pis_novo,
                base_cofins_sugerida=base_cof_nova,
                valor_cofins_sugerido=cof_novo,
                **comuns,
            )
        return replace(item, status=STATUS_COMPOSICAO_BASE, acao=ACAO_COMPOSICAO_BASE, **comuns)

    @classmethod
    def _situacao_base(cls, base_sped: Decimal, base_xml: Decimal, valor_operacao_xml: Decimal, valor_st: Decimal) -> str:
        if valor_st <= 0:
            return "sem_st"
        alvo_xml_menos_st = max(Decimal("0"), base_xml - valor_st)
        # SPED já ajustado manualmente em relação à base que veio do XML.
        if abs(base_sped - alvo_xml_menos_st) <= _TOL:
            return "fora"
        # O próprio XML já traz a base reduzida: base + ST recompõe a operação.
        if abs((base_xml + valor_st) - valor_operacao_xml) <= _TOL_OPERACAO and abs(base_sped - base_xml) <= _TOL:
            return "fora"
        # Base do XML/SPED coincide com o valor da operação: ST ainda está dentro.
        if abs(base_xml - valor_operacao_xml) <= _TOL_OPERACAO and abs(base_sped - base_xml) <= _TOL:
            return "incluido"
        # Fallback seguro usando diretamente a relação do SPED com a operação.
        if abs((base_sped + valor_st) - valor_operacao_xml) <= _TOL_OPERACAO:
            return "fora"
        if abs(base_sped - valor_operacao_xml) <= _TOL_OPERACAO:
            return "incluido"
        return "divergente"

    @classmethod
    def _vincular_item(cls, item: RegistroPreAuditoriaSaidas, doc: _DocumentoXML) -> tuple[_ItemXML | None, str]:
        xml_item = doc.itens.get(item.item)
        if xml_item and xml_item.cfop == _CFOP_SUBSTITUIDO:
            if not item.codigo_item or xml_item.codigo == item.codigo_item:
                return xml_item, "ALTA"
            return xml_item, "MÉDIA"
        candidatos = [x for x in doc.itens.values() if x.cfop == _CFOP_SUBSTITUIDO and x.codigo == item.codigo_item]
        if len(candidatos) == 1:
            return candidatos[0], "MÉDIA"
        return None, "BAIXA"

    @classmethod
    def _carregar_xmls(
        cls,
        caminho_xml: str,
        progresso: Optional[Callable[[str], None]],
    ) -> tuple[dict[str, _DocumentoXML], int]:
        origem = Path(caminho_xml)
        if not origem.exists():
            raise FileNotFoundError("Selecione um ZIP, XML ou pasta de XMLs de saída válida.")
        docs: dict[str, _DocumentoXML] = {}
        lidos = 0

        if origem.is_dir():
            arquivos = list(origem.rglob("*.xml"))
            total = len(arquivos)
            for idx, arquivo in enumerate(arquivos, start=1):
                lidos += 1
                try:
                    doc = cls._parse_xml(arquivo.read_bytes(), str(arquivo))
                    if doc:
                        docs[doc.chave] = doc
                except (ET.ParseError, OSError):
                    pass
                if idx % 500 == 0:
                    cls._progresso(progresso, f"Lendo XMLs... {idx}/{total}")
            return docs, lidos

        if origem.suffix.lower() == ".zip":
            with zipfile.ZipFile(origem, "r") as zf:
                nomes = [n for n in zf.namelist() if n.lower().endswith(".xml") and not n.endswith("/")]
                total = len(nomes)
                for idx, nome in enumerate(nomes, start=1):
                    lidos += 1
                    try:
                        doc = cls._parse_xml(zf.read(nome), nome)
                        if doc:
                            docs[doc.chave] = doc
                    except (ET.ParseError, KeyError, OSError):
                        pass
                    if idx % 500 == 0:
                        cls._progresso(progresso, f"Lendo XMLs do ZIP... {idx}/{total}")
            return docs, lidos

        if origem.suffix.lower() == ".xml":
            lidos = 1
            doc = cls._parse_xml(origem.read_bytes(), str(origem))
            if doc:
                docs[doc.chave] = doc
            return docs, lidos

        raise ValueError("Formato de XML inválido. Use arquivo .zip, .xml ou uma pasta.")

    @classmethod
    def _parse_xml(cls, conteudo: bytes, origem: str) -> _DocumentoXML | None:
        # Pacotes do DigiSat podem manter, na pasta Canceladas, o XML original que
        # chegou a ser autorizado antes do evento de cancelamento. Ele não deve
        # participar da auditoria das saídas válidas.
        if "cancelad" in origem.lower():
            return None
        raiz = ET.fromstring(conteudo)
        inf = raiz.find(".//nfe:infNFe", _NS)
        if inf is None:
            return None
        # Em procNFe autorizado, cStat 100 confirma autorização. XML sem protocolo também
        # pode ser lido quando contém infNFe, mas eventos/cancelamentos não possuem det.
        cstat = raiz.findtext(".//nfe:protNFe/nfe:infProt/nfe:cStat", default="", namespaces=_NS)
        if cstat and cstat != "100":
            return None
        ide = inf.find("nfe:ide", _NS)
        if ide is None or ide.findtext("nfe:tpNF", default="", namespaces=_NS) != "1":
            return None
        chave = (inf.attrib.get("Id") or "")
        if chave.startswith("NFe"):
            chave = chave[3:]
        if len(chave) != 44:
            return None
        modelo = ide.findtext("nfe:mod", default="", namespaces=_NS)
        numero = ide.findtext("nfe:nNF", default="", namespaces=_NS)
        itens: dict[str, _ItemXML] = {}
        grupos: dict[tuple[str, str], _GrupoXML] = {}

        for det in inf.findall("nfe:det", _NS):
            prod = det.find("nfe:prod", _NS)
            if prod is None:
                continue
            cfop = prod.findtext("nfe:CFOP", default="", namespaces=_NS)
            vprod = cls._decimal_xml(prod.findtext("nfe:vProd", default="0", namespaces=_NS))
            vdesc = cls._decimal_xml(prod.findtext("nfe:vDesc", default="0", namespaces=_NS))
            vfrete = cls._decimal_xml(prod.findtext("nfe:vFrete", default="0", namespaces=_NS))
            vseg = cls._decimal_xml(prod.findtext("nfe:vSeg", default="0", namespaces=_NS))
            voutro = cls._decimal_xml(prod.findtext("nfe:vOutro", default="0", namespaces=_NS))
            valor_operacao = vprod - vdesc + vfrete + vseg + voutro

            cst_pis, base_pis, aliq_pis, valor_pis = cls._tributo_xml(det.find("nfe:imposto/nfe:PIS", _NS), "PIS")
            cst_cof, base_cof, aliq_cof, valor_cof = cls._tributo_xml(det.find("nfe:imposto/nfe:COFINS", _NS), "COFINS")
            valor_st = Decimal("0")
            icms = det.find("nfe:imposto/nfe:ICMS", _NS)
            if icms is not None and len(icms):
                valor_st = cls._decimal_xml(icms[0].findtext("nfe:vICMSSTRet", default="0", namespaces=_NS))

            n_item = det.attrib.get("nItem", "")
            x = _ItemXML(
                n_item=n_item,
                codigo=prod.findtext("nfe:cProd", default="", namespaces=_NS),
                descricao=prod.findtext("nfe:xProd", default="", namespaces=_NS),
                cfop=cfop,
                valor_operacao=valor_operacao,
                cst_pis=cst_pis,
                base_pis=base_pis,
                aliq_pis=aliq_pis,
                valor_pis=valor_pis,
                cst_cofins=cst_cof,
                base_cofins=base_cof,
                aliq_cofins=aliq_cof,
                valor_cofins=valor_cof,
                valor_st=valor_st,
            )
            itens[n_item] = x
            if cfop == _CFOP_SUBSTITUIDO:
                classe = cls._classe_tributaria(cst_pis, base_pis, aliq_pis)
                chave_grupo = (cfop, classe)
                anterior = grupos.get(chave_grupo, _GrupoXML())
                grupos[chave_grupo] = _GrupoXML(
                    valor_operacao=anterior.valor_operacao + valor_operacao,
                    base_pis=anterior.base_pis + base_pis,
                    base_cofins=anterior.base_cofins + base_cof,
                    valor_st=anterior.valor_st + valor_st,
                    quantidade=anterior.quantidade + 1,
                )

        if not itens:
            return None
        return _DocumentoXML(chave=chave, modelo=modelo, numero=numero, origem=origem, itens=itens, grupos=grupos)

    @classmethod
    def _tributo_xml(cls, grupo: ET.Element | None, tributo: str) -> tuple[str, Decimal, Decimal, Decimal]:
        if grupo is None or not len(grupo):
            return "", Decimal("0"), Decimal("0"), Decimal("0")
        filho = grupo[0]
        cst = filho.findtext("nfe:CST", default="", namespaces=_NS)
        base = cls._decimal_xml(filho.findtext("nfe:vBC", default="0", namespaces=_NS))
        if tributo == "PIS":
            aliq = cls._decimal_xml(filho.findtext("nfe:pPIS", default="0", namespaces=_NS))
            valor = cls._decimal_xml(filho.findtext("nfe:vPIS", default="0", namespaces=_NS))
        else:
            aliq = cls._decimal_xml(filho.findtext("nfe:pCOFINS", default="0", namespaces=_NS))
            valor = cls._decimal_xml(filho.findtext("nfe:vCOFINS", default="0", namespaces=_NS))
        return cst, base, aliq, valor

    @classmethod
    def _classificar(
        cls,
        cst_pis: str,
        base_pis: Decimal,
        aliq_pis: Decimal,
        cst_cofins: str,
        base_cofins: Decimal,
        aliq_cofins: Decimal,
    ) -> tuple[str, str]:
        if (
            cst_pis in _CSTS_ALIQUOTA_ZERO
            and cst_cofins in _CSTS_ALIQUOTA_ZERO
            and base_pis <= 0
            and base_cofins <= 0
        ):
            return STATUS_ALIQUOTA_ZERO, ACAO_ALIQUOTA_ZERO
        if base_pis > 0 or base_cofins > 0:
            return STATUS_CANDIDATO_XML, ACAO_CANDIDATO_XML
        return STATUS_REVISAR_BASE, ACAO_REVISAR_BASE

    @classmethod
    def _classe_tributaria(cls, cst: str, base: Decimal, aliquota: Decimal) -> str:
        if cst in _CSTS_ALIQUOTA_ZERO and base <= 0:
            return "zero"
        if base > 0 or aliquota > 0:
            return "tributada"
        return "outra"

    @staticmethod
    def _calcular_contribuicao(base: Decimal, aliquota: Decimal) -> Decimal:
        if base <= 0 or aliquota <= 0:
            return Decimal("0")
        return (base * aliquota / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _progresso(callback: Optional[Callable[[str], None]], texto: str) -> None:
        if callback:
            callback(texto)

    @staticmethod
    def _decimal_sped(valor: str) -> Decimal:
        texto = (valor or "").strip()
        if not texto:
            return Decimal("0")
        try:
            return Decimal(texto.replace(".", "").replace(",", "."))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @staticmethod
    def _decimal_xml(valor: str) -> Decimal:
        texto = (valor or "").strip()
        if not texto:
            return Decimal("0")
        try:
            return Decimal(texto.replace(",", "."))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    # Compatibilidade com chamadas antigas da 17.8.19.
    _decimal = _decimal_sped
