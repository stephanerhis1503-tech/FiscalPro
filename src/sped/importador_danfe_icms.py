from __future__ import annotations

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Iterable

from src.services.icms_st_mg_service import ICMSSTMGService

ProgressoCallback = Callable[[int, str], None]
CENTAVO = Decimal("0.01")
TOLERANCIA = Decimal("0.05")
CFOPS_REVENDA = {"1102", "2102", "1403", "2403"}
CFOPS_SAIDA_VENDA_NORMAL = {"5101", "5102", "6101", "6102"}
CFOPS_SAIDA_VENDA_ST = {"5401", "5403", "5405", "6401", "6403", "6404", "6405"}

# Regimes especiais de e-commerce em MG com atribuição da responsabilidade pelo ICMS-ST
# ao próprio destinatário. Nesses casos, quando o XML chega como operação própria normal
# (sem retenção de ST pelo remetente), a entrada para revenda permanece 1102/2102.
# Fonte operacional validada em 2026: SEF/MG, PTA 45.000044018-75, vigência até 31/12/2032.
DESTINATARIOS_ECOMMERCE_ST_RESP_PROPRIA_MG = {
    "54304208000123": {"pta": "45.000044018-75", "vigencia_ate": "2032-12-31"},
}


@dataclass(slots=True)
class ItemDANFEICMS:
    ordem: int
    codigo_pdf: str
    ncm: str
    cst: str
    cfop_saida: str
    quantidade: Decimal
    valor_item: Decimal
    base_icms: Decimal
    aliquota_icms: Decimal
    valor_icms: Decimal
    descricao: str = ""
    cest: str = ""
    base_icms_st: Decimal = Decimal("0")
    valor_icms_st: Decimal = Decimal("0")


@dataclass(slots=True)
class DANFEICMS:
    arquivo: str
    chave_nfe: str
    numero_documento: str
    cnpj_destinatario: str
    base_icms_total: Decimal
    valor_icms_total: Decimal
    itens: list[ItemDANFEICMS] = field(default_factory=list)
    erro_leitura: str = ""
    uf_emitente: str = ""
    uf_destinatario: str = ""


@dataclass(slots=True)
class NotaConferenciaDANFEICMS:
    danfe: DANFEICMS
    status: str
    observacao: str
    indice_c100: int | None = None
    indice_fim_bloco: int | None = None
    indices_c170: tuple[int, ...] = ()
    indices_c190: tuple[int, ...] = ()
    cfop_entrada: str = ""
    cfops_entrada_itens: tuple[str, ...] = ()
    motivos_cfop_itens: tuple[str, ...] = ()
    total_cfop_corrigir: int = 0

    @property
    def apta(self) -> bool:
        return self.status == "APTA"


@dataclass(slots=True)
class ResultadoAnaliseDANFEICMS:
    notas: list[NotaConferenciaDANFEICMS]
    cnpj_empresa: str
    total_pdfs: int
    total_aptas: int
    total_sem_credito: int
    total_revisao: int
    total_nao_encontradas: int
    total_icms_apto: Decimal
    total_itens_aptos: int
    total_cfop_corrigir: int = 0

    @property
    def pode_gerar(self) -> bool:
        return self.total_aptas > 0 and self.total_itens_aptos > 0


@dataclass(slots=True)
class ResultadoGeracaoDANFEICMS:
    caminho_sped: Path
    caminho_relatorio: Path
    caminho_memoria: Path
    notas_alteradas: int
    itens_alterados: int
    total_icms: Decimal
    cfops_corrigidos: int = 0


class ImportadorDANFEICMS:
    """Importa ICMS próprio de NF-e de compras para revenda.

    A fonte preferencial é o XML autorizado da NF-e, pois traz os campos fiscais
    estruturados sem depender da leitura visual da DANFE. PDFs digitais continuam
    aceitos como contingência. O motor é conservador: somente aplica quando a chave
    existe no SPED, o destinatário coincide com a empresa, a operação é entrada de
    terceiro e os itens/totais conferem com C100/C170. Documentos sem ICMS próprio
    ou com divergência permanecem apenas para revisão.
    """

    def analisar(
        self,
        linhas: list[str],
        fontes: Iterable[str | Path],
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseDANFEICMS:
        cnpj_empresa = self._cnpj_empresa(linhas)
        if not cnpj_empresa:
            raise RuntimeError("Não foi possível identificar o CNPJ da empresa no registro 0000.")

        documentos = self._ler_fontes(fontes, progresso, cnpj_empresa)
        mapa_c100 = self._mapear_c100(linhas)
        conferencias: list[NotaConferenciaDANFEICMS] = []

        total = max(len(documentos), 1)
        for ordem, danfe in enumerate(documentos, start=1):
            self._progresso(
                progresso,
                45 + int(45 * ordem / total),
                f"Conferindo NF-e {ordem} de {len(documentos)}: {danfe.arquivo}",
            )
            conferencias.append(
                self._conferir_danfe(linhas, mapa_c100, cnpj_empresa, danfe)
            )

        total_aptas = sum(1 for n in conferencias if n.status == "APTA")
        total_sem_credito = sum(1 for n in conferencias if n.status == "SEM CRÉDITO")
        total_nao_encontradas = sum(1 for n in conferencias if n.status == "NÃO ENCONTRADA")
        total_revisao = len(conferencias) - total_aptas - total_sem_credito - total_nao_encontradas
        total_icms = sum(
            (n.danfe.valor_icms_total for n in conferencias if n.apta), Decimal("0")
        )
        total_itens = sum(len(n.danfe.itens) for n in conferencias if n.apta)
        total_cfop_corrigir = sum(n.total_cfop_corrigir for n in conferencias if n.apta)
        self._progresso(progresso, 100, "Conferência dos XMLs/PDFs de compra concluída.")
        return ResultadoAnaliseDANFEICMS(
            notas=conferencias,
            cnpj_empresa=cnpj_empresa,
            total_pdfs=len(documentos),
            total_aptas=total_aptas,
            total_sem_credito=total_sem_credito,
            total_revisao=total_revisao,
            total_nao_encontradas=total_nao_encontradas,
            total_icms_apto=self._moeda(total_icms),
            total_itens_aptos=total_itens,
            total_cfop_corrigir=total_cfop_corrigir,
        )

    def gerar(
        self,
        linhas: list[str],
        encoding: str,
        caminho_saida: str | Path,
        analise: ResultadoAnaliseDANFEICMS,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoGeracaoDANFEICMS:
        aptas = [nota for nota in analise.notas if nota.apta]
        if not aptas:
            raise RuntimeError("Nenhuma NF-e está apta para preencher o ICMS dos itens.")

        self._progresso(progresso, 5, "Aplicando base, alíquota e ICMS nos C170...")
        novas = list(linhas)
        quebra = self._quebra_padrao(novas)
        alteracoes_c170: dict[int, str] = {}
        substituicoes_c190: dict[int, tuple[set[int], list[str]]] = {}
        memoria: list[tuple[NotaConferenciaDANFEICMS, int, str, ItemDANFEICMS, str, str, str]] = []
        cfops_corrigidos = 0

        for nota in aptas:
            assert nota.indice_c100 is not None
            assert nota.indice_fim_bloco is not None
            if len(nota.indices_c170) != len(nota.danfe.itens):
                raise RuntimeError(
                    f"A NF {nota.danfe.numero_documento} mudou desde a análise; execute a conferência novamente."
                )

            grupos: dict[tuple[str, str, Decimal], dict[str, Decimal]] = defaultdict(
                lambda: {
                    "vl_itens": Decimal("0"),
                    "vl_opr": Decimal("0"),
                    "base": Decimal("0"),
                    "icms": Decimal("0"),
                }
            )
            for posicao, (indice_c170, item_pdf) in enumerate(
                zip(nota.indices_c170, nota.danfe.itens), start=1
            ):
                campos = self._campos(novas[indice_c170])
                if len(campos) < 15 or campos[0] != "C170":
                    raise RuntimeError(
                        f"Registro C170 inesperado na NF {nota.danfe.numero_documento}."
                    )
                codigo_item = campos[2].strip()
                cfop_anterior = campos[10].strip()
                cfop_novo = (
                    nota.cfops_entrada_itens[posicao - 1]
                    if len(nota.cfops_entrada_itens) == len(nota.danfe.itens)
                    else nota.cfop_entrada
                )
                motivo_cfop = (
                    nota.motivos_cfop_itens[posicao - 1]
                    if len(nota.motivos_cfop_itens) == len(nota.danfe.itens)
                    else "CFOP de entrada definido pela conferência da NF-e."
                )
                campos[9] = item_pdf.cst
                campos[10] = cfop_novo
                campos[12] = self._formatar(item_pdf.base_icms)
                campos[13] = self._formatar(item_pdf.aliquota_icms)
                campos[14] = self._formatar(item_pdf.valor_icms)
                alteracoes_c170[indice_c170] = self._montar(campos, self._fim_linha(novas[indice_c170]))
                chave_grupo = (item_pdf.cst, cfop_novo, item_pdf.aliquota_icms)
                grupos[chave_grupo]["vl_itens"] += self._decimal(campos[6])
                grupos[chave_grupo]["base"] += item_pdf.base_icms
                grupos[chave_grupo]["icms"] += item_pdf.valor_icms
                if cfop_anterior != cfop_novo:
                    cfops_corrigidos += 1
                memoria.append((nota, posicao, codigo_item, item_pdf, cfop_anterior, cfop_novo, motivo_cfop))

            # Preserva o VL_OPR já escriturado nos C190. Quando houver mais de
            # uma tributação, distribui eventual frete/IPI/desconto proporcionalmente
            # ao valor dos itens, evitando substituir o valor da operação pela base.
            vl_opr_original = sum(
                (self._decimal(self._campos(novas[i])[4]) for i in nota.indices_c190),
                Decimal("0"),
            )
            soma_itens = sum((v["vl_itens"] for v in grupos.values()), Decimal("0"))
            chaves_grupo = sorted(grupos)
            restante = vl_opr_original
            for posicao_grupo, chave in enumerate(chaves_grupo, start=1):
                valores = grupos[chave]
                if len(chaves_grupo) == 1:
                    valores["vl_opr"] = vl_opr_original
                elif posicao_grupo == len(chaves_grupo):
                    valores["vl_opr"] = restante
                elif soma_itens > 0:
                    parcela = self._moeda(vl_opr_original * valores["vl_itens"] / soma_itens)
                    valores["vl_opr"] = parcela
                    restante -= parcela
                else:
                    valores["vl_opr"] = valores["base"]
                    restante -= valores["vl_opr"]

            novos_c190 = []
            for (cst, cfop, aliquota), valores in sorted(grupos.items()):
                novos_c190.append(
                    "|C190|{cst}|{cfop}|{aliq}|{vl_opr}|{base}|{icms}|0,00|0,00|0,00|0,00||{q}".format(
                        cst=cst,
                        cfop=cfop,
                        aliq=self._formatar(aliquota),
                        vl_opr=self._formatar(valores["vl_opr"]),
                        base=self._formatar(valores["base"]),
                        icms=self._formatar(valores["icms"]),
                        q=quebra,
                    )
                )
            if not nota.indices_c190:
                raise RuntimeError(
                    f"A NF {nota.danfe.numero_documento} não possui C190 para substituição segura."
                )
            primeiro_c190 = min(nota.indices_c190)
            substituicoes_c190[primeiro_c190] = (set(nota.indices_c190), novos_c190)

        self._progresso(progresso, 55, "Reconstruindo os resumos C190 das notas elegíveis...")
        reconstruidas: list[str] = []
        indices_c190_remover = set()
        for _, (indices, _) in substituicoes_c190.items():
            indices_c190_remover.update(indices)
        for indice, linha in enumerate(novas):
            if indice in alteracoes_c170:
                linha = alteracoes_c170[indice]
            if indice in substituicoes_c190:
                reconstruidas.extend(substituicoes_c190[indice][1])
            if indice in indices_c190_remover:
                continue
            reconstruidas.append(linha)
        novas = reconstruidas

        self._progresso(progresso, 72, "Recalculando totalizadores do SPED...")
        # Reutiliza a rotina já validada pelo módulo de estorno.
        from .estorno_credito_icms import EstornadorCreditosICMSMG

        novas = EstornadorCreditosICMSMG()._recalcular_totalizadores(novas)

        destino = Path(caminho_saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        encoding_saida = self._encoding_sem_bom(encoding)
        with destino.open("w", encoding=encoding_saida, newline="") as arquivo:
            arquivo.writelines(novas)

        memoria_path = destino.with_name(f"{destino.stem}_MEMORIA_ICMS_DANFE.csv")
        relatorio_path = destino.with_name(f"{destino.stem}_RELATORIO_ICMS_DANFE.txt")
        self._salvar_memoria(memoria_path, memoria)
        self._salvar_relatorio(relatorio_path, destino, analise)
        self._progresso(progresso, 100, "SPED com ICMS das NF-e de entrada gerado com sucesso.")
        return ResultadoGeracaoDANFEICMS(
            caminho_sped=destino,
            caminho_relatorio=relatorio_path,
            caminho_memoria=memoria_path,
            notas_alteradas=len(aptas),
            itens_alterados=len(memoria),
            total_icms=analise.total_icms_apto,
            cfops_corrigidos=cfops_corrigidos,
        )

    def _ler_fontes(
        self,
        fontes: Iterable[str | Path],
        progresso: ProgressoCallback | None,
        cnpj_empresa: str,
    ) -> list[DANFEICMS]:
        # Cada entrada guarda nome, conteúdo/caminho e tipo. XML é a fonte
        # preferencial; PDF permanece como contingência para DANFE digital.
        entradas: list[tuple[str, bytes | Path, str]] = []
        for fonte in fontes:
            caminho = Path(fonte)
            if not caminho.exists():
                continue
            if caminho.is_dir():
                for arquivo in sorted(caminho.rglob("*")):
                    if not arquivo.is_file():
                        continue
                    sufixo = arquivo.suffix.lower()
                    if sufixo in {".xml", ".pdf"}:
                        entradas.append((arquivo.name, arquivo, sufixo[1:]))
            elif caminho.suffix.lower() in {".xml", ".pdf"}:
                entradas.append((caminho.name, caminho, caminho.suffix.lower()[1:]))
            elif caminho.suffix.lower() == ".zip":
                with zipfile.ZipFile(caminho) as pacote:
                    for nome in sorted(pacote.namelist()):
                        nome_lower = nome.lower()
                        if nome.startswith("__MACOSX/"):
                            continue
                        if not (nome_lower.endswith(".xml") or nome_lower.endswith(".pdf")):
                            continue
                        tipo = "xml" if nome_lower.endswith(".xml") else "pdf"
                        entradas.append((Path(nome).name, pacote.read(nome), tipo))

        if not entradas:
            raise RuntimeError(
                "Nenhum XML de NF-e nem PDF de DANFE foi localizado nas fontes selecionadas."
            )

        # Lê XMLs antes dos PDFs. Se o mesmo documento estiver nas duas formas,
        # preserva o XML e descarta a duplicata pelo número da chave de acesso.
        entradas.sort(key=lambda item: (0 if item[2] == "xml" else 1, item[0].lower()))
        documentos: list[DANFEICMS] = []
        chaves_vistas: set[str] = set()
        total = len(entradas)
        for indice, (nome, origem, tipo) in enumerate(entradas, start=1):
            self._progresso(
                progresso,
                5 + int(35 * indice / total),
                f"Lendo {tipo.upper()} {indice} de {total}: {nome}",
            )
            try:
                documento = (
                    self._ler_xml(nome, origem, cnpj_empresa)
                    if tipo == "xml"
                    else self._ler_pdf(nome, origem, cnpj_empresa)
                )
                if documento.chave_nfe and documento.chave_nfe in chaves_vistas:
                    continue
                if documento.chave_nfe:
                    chaves_vistas.add(documento.chave_nfe)
                documentos.append(documento)
            except Exception as erro:
                # ZIPs de documentos fiscais podem trazer eventos, inutilizações
                # ou XMLs auxiliares. Eles não são NF-e de entrada e devem ser
                # ignorados, sem virar falsa divergência na conferência.
                if tipo == "xml" and "não contém uma NF-e" in str(erro):
                    continue
                documentos.append(
                    DANFEICMS(
                        arquivo=nome,
                        chave_nfe="",
                        numero_documento="",
                        cnpj_destinatario="",
                        base_icms_total=Decimal("0"),
                        valor_icms_total=Decimal("0"),
                        erro_leitura=str(erro),
                    )
                )
        if not documentos:
            raise RuntimeError(
                "Nenhum XML válido de NF-e nem PDF de DANFE foi localizado nas fontes selecionadas."
            )
        return documentos

    def _ler_xml(
        self,
        nome: str,
        origem: bytes | Path,
        cnpj_empresa: str = "",
    ) -> DANFEICMS:
        try:
            if isinstance(origem, bytes):
                raiz = ET.fromstring(origem)
            else:
                raiz = ET.parse(origem).getroot()
        except ET.ParseError as erro:
            raise RuntimeError(f"XML inválido: {erro}") from erro

        inf = raiz.find(".//{*}infNFe")
        if inf is None and self._localname(raiz.tag) == "infNFe":
            inf = raiz
        if inf is None:
            raise RuntimeError("XML não contém uma NF-e (infNFe não localizado).")

        identificador = (inf.attrib.get("Id") or "").strip()
        chave = identificador[3:] if identificador.startswith("NFe") else ""
        if chave and not (len(chave) == 44 and chave.isdigit()):
            chave = ""
        if not chave:
            ch_nfe = raiz.find(".//{*}protNFe/{*}infProt/{*}chNFe")
            if ch_nfe is not None:
                candidato = (ch_nfe.text or "").strip()
                if len(candidato) == 44 and candidato.isdigit():
                    chave = candidato

        numero = self._xml_texto(inf, "./{*}ide/{*}nNF")
        uf_emitente = self._xml_texto(inf, "./{*}emit/{*}enderEmit/{*}UF").upper()
        uf_destinatario = self._xml_texto(inf, "./{*}dest/{*}enderDest/{*}UF").upper()
        cnpj_dest = re.sub(r"\D", "", self._xml_texto(inf, "./{*}dest/{*}CNPJ"))
        esperado = re.sub(r"\D", "", cnpj_empresa or "")
        # Não troca o destinatário lido pelo esperado: a comparação posterior
        # precisa detectar XML pertencente a outra empresa.
        if not cnpj_dest and esperado:
            cpf_dest = re.sub(r"\D", "", self._xml_texto(inf, "./{*}dest/{*}CPF"))
            cnpj_dest = cpf_dest

        total = inf.find("./{*}total/{*}ICMSTot")
        base_total = self._decimal_xml(self._xml_texto(total, "./{*}vBC")) if total is not None else Decimal("0")
        icms_total = self._decimal_xml(self._xml_texto(total, "./{*}vICMS")) if total is not None else Decimal("0")

        itens: list[ItemDANFEICMS] = []
        for posicao, det in enumerate(inf.findall("./{*}det"), start=1):
            prod = det.find("./{*}prod")
            if prod is None:
                continue
            imposto = det.find("./{*}imposto")
            icms_grupo = imposto.find("./{*}ICMS") if imposto is not None else None
            icms = next(iter(icms_grupo), None) if icms_grupo is not None else None

            orig = self._xml_texto(icms, "./{*}orig") if icms is not None else ""
            cst2 = self._xml_texto(icms, "./{*}CST") if icms is not None else ""
            cst = f"{orig}{cst2}" if orig.isdigit() and len(orig) == 1 and cst2.isdigit() and len(cst2) == 2 else ""

            itens.append(
                ItemDANFEICMS(
                    ordem=int(det.attrib.get("nItem") or posicao),
                    codigo_pdf=self._xml_texto(prod, "./{*}cProd"),
                    ncm=re.sub(r"\D", "", self._xml_texto(prod, "./{*}NCM")),
                    cst=cst,
                    cfop_saida=re.sub(r"\D", "", self._xml_texto(prod, "./{*}CFOP")),
                    quantidade=self._decimal_xml(self._xml_texto(prod, "./{*}qCom")),
                    valor_item=self._decimal_xml(self._xml_texto(prod, "./{*}vProd")),
                    base_icms=self._decimal_xml(self._xml_texto(icms, "./{*}vBC")) if icms is not None else Decimal("0"),
                    aliquota_icms=self._decimal_xml(self._xml_texto(icms, "./{*}pICMS")) if icms is not None else Decimal("0"),
                    valor_icms=self._decimal_xml(self._xml_texto(icms, "./{*}vICMS")) if icms is not None else Decimal("0"),
                    descricao=self._xml_texto(prod, "./{*}xProd"),
                    cest=re.sub(r"\D", "", self._xml_texto(prod, "./{*}CEST")),
                    base_icms_st=self._decimal_xml(self._xml_texto(icms, "./{*}vBCST")) if icms is not None else Decimal("0"),
                    valor_icms_st=self._decimal_xml(self._xml_texto(icms, "./{*}vICMSST")) if icms is not None else Decimal("0"),
                )
            )

        if not chave:
            raise RuntimeError("Chave de acesso da NF-e não localizada no XML.")
        if not itens:
            raise RuntimeError("Nenhum item (det) foi localizado no XML da NF-e.")

        return DANFEICMS(
            arquivo=nome,
            chave_nfe=chave,
            numero_documento=numero or (str(int(chave[25:34])) if chave else ""),
            cnpj_destinatario=cnpj_dest,
            base_icms_total=self._moeda(base_total),
            valor_icms_total=self._moeda(icms_total),
            itens=itens,
            uf_emitente=uf_emitente,
            uf_destinatario=uf_destinatario,
        )

    @staticmethod
    def _localname(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _xml_texto(no, caminho: str) -> str:
        if no is None:
            return ""
        achado = no.find(caminho)
        return (achado.text or "").strip() if achado is not None else ""

    @staticmethod
    def _decimal_xml(valor: str) -> Decimal:
        try:
            return Decimal((valor or "0").strip().replace(",", "."))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    def _ler_pdf(
        self,
        nome: str,
        origem: bytes | Path,
        cnpj_empresa: str = "",
    ) -> DANFEICMS:
        try:
            import pdfplumber
        except ImportError as erro:
            raise RuntimeError(
                "A biblioteca pdfplumber não está instalada. Execute: pip install pdfplumber"
            ) from erro

        alvo = io.BytesIO(origem) if isinstance(origem, bytes) else origem
        with pdfplumber.open(alvo) as pdf:
            texto = "\n".join(
                pagina.extract_text(x_tolerance=2, y_tolerance=3, layout=True) or ""
                for pagina in pdf.pages
            )
        if not texto.strip():
            raise RuntimeError("PDF sem texto pesquisável; utilize uma DANFE digital legível.")

        chave = self._extrair_chave(texto)
        numero = str(int(chave[25:34])) if chave else ""
        cnpjs = re.findall(r"\b\d{2}[.]\d{3}[.]\d{3}/\d{4}-\d{2}\b", texto)
        cnpj_dest = ""
        cnpjs_norm = [re.sub(r"\D", "", item) for item in cnpjs]
        # A mesma rotina atende todas as empresas cadastradas no FiscalPro:
        # primeiro procura o CNPJ lido do registro 0000 e, como contingência,
        # usa a segunda inscrição impressa na DANFE (emitente costuma ser a primeira).
        esperado = re.sub(r"\D", "", cnpj_empresa or "")
        if esperado and esperado in cnpjs_norm:
            cnpj_dest = esperado
        elif len(cnpjs_norm) >= 2:
            cnpj_dest = cnpjs_norm[1]

        base_total, icms_total = self._extrair_totais(texto)
        itens = self._extrair_itens(texto)
        return DANFEICMS(
            arquivo=nome,
            chave_nfe=chave,
            numero_documento=numero,
            cnpj_destinatario=cnpj_dest,
            base_icms_total=base_total,
            valor_icms_total=icms_total,
            itens=itens,
        )

    def _conferir_danfe(
        self,
        linhas: list[str],
        mapa_c100: dict[str, tuple[int, int]],
        cnpj_empresa: str,
        danfe: DANFEICMS,
    ) -> NotaConferenciaDANFEICMS:
        if danfe.erro_leitura:
            return NotaConferenciaDANFEICMS(danfe, "REVISAR", danfe.erro_leitura)
        if not danfe.chave_nfe:
            return NotaConferenciaDANFEICMS(
                danfe, "REVISAR", "Chave de acesso da NF-e não localizada no documento."
            )
        if danfe.cnpj_destinatario != cnpj_empresa:
            return NotaConferenciaDANFEICMS(
                danfe,
                "REVISAR",
                "O CNPJ do destinatário da NF-e não coincide com o registro 0000 do SPED.",
            )
        bloco = mapa_c100.get(danfe.chave_nfe)
        if bloco is None:
            return NotaConferenciaDANFEICMS(
                danfe, "NÃO ENCONTRADA", "A chave da NF-e não foi localizada em nenhum C100."
            )
        inicio, fim = bloco
        c100 = self._campos(linhas[inicio])
        if len(c100) < 22 or c100[1].strip() != "0" or c100[2].strip() != "1":
            return NotaConferenciaDANFEICMS(
                danfe,
                "REVISAR",
                "O C100 não representa compra de terceiro (IND_OPER=0 e IND_EMIT=1).",
                inicio,
                fim,
            )
        if danfe.valor_icms_total <= 0:
            return NotaConferenciaDANFEICMS(
                danfe,
                "SEM CRÉDITO",
                "A NF-e não possui ICMS próprio destacado; nenhum crédito será incluído.",
                inicio,
                fim,
            )

        indices_c170 = tuple(
            i for i in range(inicio + 1, fim) if self._codigo(linhas[i]) == "C170"
        )
        indices_c190 = tuple(
            i for i in range(inicio + 1, fim) if self._codigo(linhas[i]) == "C190"
        )
        if not indices_c170 or not indices_c190:
            return NotaConferenciaDANFEICMS(
                danfe,
                "REVISAR",
                "A nota não possui C170/C190 suficientes para correção segura.",
                inicio,
                fim,
                indices_c170,
                indices_c190,
            )
        cfops = {self._campos(linhas[i])[10].strip() for i in indices_c170}
        if not cfops or any(not re.fullmatch(r"\d{4}", cfop or "") for cfop in cfops):
            return NotaConferenciaDANFEICMS(
                danfe,
                "REVISAR",
                "Há CFOP vazio ou inválido nos C170; a correção automática exige um CFOP atual identificável.",
                inicio,
                fim,
                indices_c170,
                indices_c190,
            )
        if len(danfe.itens) != len(indices_c170):
            return NotaConferenciaDANFEICMS(
                danfe,
                "REVISAR",
                f"Itens divergentes: documento={len(danfe.itens)} e C170={len(indices_c170)}.",
                inicio,
                fim,
                indices_c170,
                indices_c190,
            )

        cfops_entrada_itens: list[str] = []
        motivos_cfop_itens: list[str] = []
        total_cfop_corrigir = 0
        for ordem, (indice_c170, item_doc) in enumerate(zip(indices_c170, danfe.itens), start=1):
            campos_item = self._campos(linhas[indice_c170])
            cfop_atual = campos_item[10].strip() if len(campos_item) > 10 else ""
            cfop_sugerido, motivo = self._sugerir_cfop_entrada(danfe, item_doc, cfop_atual)
            if not cfop_sugerido:
                return NotaConferenciaDANFEICMS(
                    danfe,
                    "REVISAR",
                    f"CFOP do item {ordem} requer revisão: {motivo}",
                    inicio,
                    fim,
                    indices_c170,
                    indices_c190,
                )
            cfops_entrada_itens.append(cfop_sugerido)
            motivos_cfop_itens.append(motivo)
            if cfop_atual != cfop_sugerido:
                total_cfop_corrigir += 1

        cfop_entrada = (
            cfops_entrada_itens[0]
            if len(set(cfops_entrada_itens)) == 1
            else "MISTO"
        )

        base_c100 = self._decimal(c100[20])
        icms_c100 = self._decimal(c100[21])
        if (base_c100 - danfe.base_icms_total).copy_abs() > TOLERANCIA or (
            icms_c100 - danfe.valor_icms_total
        ).copy_abs() > TOLERANCIA:
            return NotaConferenciaDANFEICMS(
                danfe,
                "REVISAR",
                "Base ou ICMS total da NF-e não coincide com os valores informados no C100.",
                inicio,
                fim,
                indices_c170,
                indices_c190,
                cfop_entrada,
            )

        for ordem, item_doc in enumerate(danfe.itens, start=1):
            if item_doc.valor_icms > 0 and not re.fullmatch(r"\d{3}", item_doc.cst or ""):
                return NotaConferenciaDANFEICMS(
                    danfe,
                    "REVISAR",
                    f"CST de ICMS do item {ordem} não pôde ser identificado com segurança no documento.",
                    inicio,
                    fim,
                    indices_c170,
                    indices_c190,
                    cfop_entrada,
                )

        soma_base = sum((item.base_icms for item in danfe.itens), Decimal("0"))
        soma_icms = sum((item.valor_icms for item in danfe.itens), Decimal("0"))
        if (soma_base - danfe.base_icms_total).copy_abs() > TOLERANCIA or (
            soma_icms - danfe.valor_icms_total
        ).copy_abs() > TOLERANCIA:
            return NotaConferenciaDANFEICMS(
                danfe,
                "REVISAR",
                "A soma dos itens da NF-e não fecha com o total do ICMS do documento.",
                inicio,
                fim,
                indices_c170,
                indices_c190,
                cfop_entrada,
            )

        for ordem, (indice_c170, item_pdf) in enumerate(
            zip(indices_c170, danfe.itens), start=1
        ):
            campos = self._campos(linhas[indice_c170])
            if len(campos) < 15:
                return NotaConferenciaDANFEICMS(
                    danfe,
                    "REVISAR",
                    f"C170 incompleto no item {ordem}.",
                    inicio,
                    fim,
                    indices_c170,
                    indices_c190,
                    cfop_entrada,
                )
            qtd_sped = self._decimal(campos[4])
            valor_sped = self._decimal(campos[6])
            if (qtd_sped - item_pdf.quantidade).copy_abs() > Decimal("0.0001") or (
                valor_sped - item_pdf.valor_item
            ).copy_abs() > TOLERANCIA:
                return NotaConferenciaDANFEICMS(
                    danfe,
                    "REVISAR",
                    f"O item {ordem} da NF-e não coincide em quantidade/valor com o C170.",
                    inicio,
                    fim,
                    indices_c170,
                    indices_c190,
                    cfop_entrada,
                )

        observacao_cfop = (
            f" {total_cfop_corrigir} CFOP(s) de entrada serão corrigidos conforme a natureza da compra e o enquadramento de ST."
            if total_cfop_corrigir
            else " CFOPs de entrada já estão coerentes com a conferência."
        )
        return NotaConferenciaDANFEICMS(
            danfe,
            "APTA",
            "NF-e, C100 e itens C170 conferidos; ICMS próprio pode ser preenchido com segurança." + observacao_cfop,
            inicio,
            fim,
            indices_c170,
            indices_c190,
            cfop_entrada,
            tuple(cfops_entrada_itens),
            tuple(motivos_cfop_itens),
            total_cfop_corrigir,
        )

    def _sugerir_cfop_entrada(
        self,
        danfe: DANFEICMS,
        item: ItemDANFEICMS,
        cfop_atual: str,
    ) -> tuple[str, str]:
        """Define o CFOP de entrada para compra destinada à revenda.

        A decisão nunca usa a alíquota isoladamente. Primeiro determina se a
        aquisição é interna ou interestadual; depois preserva/identifica a
        natureza de ST por evidência do XML e, para MG, pelo motor oficial.
        Quando o enquadramento continuar ambíguo, não há troca automática.
        """
        saida = re.sub(r"\D", "", item.cfop_saida or "")
        atual = re.sub(r"\D", "", cfop_atual or "")
        origem = (danfe.uf_emitente or "").strip().upper()
        destino = (danfe.uf_destinatario or "").strip().upper()

        interestadual: bool | None = None
        if len(saida) == 4 and saida[0] in {"5", "6"}:
            interestadual = saida[0] == "6"
        elif origem and destino:
            interestadual = origem != destino
        elif len(atual) == 4 and atual[0] in {"1", "2"}:
            interestadual = atual[0] == "2"
        if interestadual is None:
            return "", "não foi possível determinar se a compra é interna ou interestadual"

        cfop_normal = "2102" if interestadual else "1102"
        cfop_st = "2403" if interestadual else "1403"

        if saida in CFOPS_SAIDA_VENDA_ST or item.base_icms_st > 0 or item.valor_icms_st > 0:
            return cfop_st, (
                f"XML evidencia mercadoria em operação com ICMS-ST; compra para revenda -> {cfop_st}."
            )

        # 17.8.89 — regime especial de e-commerce/atribuição de responsabilidade em MG.
        # A mercadoria pode estar listada na ST (ex.: capacete CEST 01.013.00), mas o
        # remetente fica dispensado de reter o imposto e emite a operação própria normal.
        # Quando o XML confirma venda normal e não há base/valor de ST, não se deve
        # transformar a entrada em 1403/2403 apenas pelo NCM/CEST.
        cnpj_dest = re.sub(r"\D", "", danfe.cnpj_destinatario or "")
        regime_ecommerce = DESTINATARIOS_ECOMMERCE_ST_RESP_PROPRIA_MG.get(cnpj_dest)
        if (
            destino == "MG"
            and regime_ecommerce
            and saida in CFOPS_SAIDA_VENDA_NORMAL
            and item.base_icms_st <= 0
            and item.valor_icms_st <= 0
        ):
            pta = regime_ecommerce.get("pta", "")
            return cfop_normal, (
                f"Destinatário com regime especial de e-commerce/atribuição de responsabilidade do ICMS-ST"
                f" (PTA {pta}); XML sem retenção de ST pelo remetente -> compra para revenda {cfop_normal}."
            )

        # Se o SPED já informa corretamente a família ST/não-ST, apenas corrige
        # o prefixo interno/interestadual quando necessário.
        if atual in {"1403", "2403"}:
            return cfop_st, f"Mantida a natureza ST já escriturada; ajustado o alcance territorial para {cfop_st}."

        decisao_st: bool | None = None
        motivo_st = ""
        if destino == "MG" and item.ncm:
            descricao_consulta = " ".join(x for x in (item.descricao, item.codigo_pdf) if x).strip()
            finalidade = ICMSSTMGService.inferir_finalidade_automotiva(descricao_consulta)
            # 17.8.88 — NCM 65061090 / CEST 01.013.00. Alguns XMLs da LM
            # abreviam capacete como "CAP.". A classificação não pode depender
            # da palavra literal CAPACETE quando o próprio XML informa o CEST
            # 01.013.00 e o contexto confirma capacete de motocicleta.
            desc_norm = self._normalizar(item.descricao)
            cod_norm = (item.codigo_pdf or "").strip().upper()
            cest_norm = re.sub(r"\D", "", item.cest or "")
            desc_cap_abreviado = bool(re.search(r"(?:^|\s)CAP(?:\.|\s|$)", desc_norm))
            eh_capacete_moto = (
                item.ncm == "65061090"
                and (
                    "CAPACETE" in desc_norm
                    or (desc_cap_abreviado and ("MOTO" in desc_norm or "MOTOCIC" in desc_norm))
                    or (cest_norm == "0101300" and cod_norm.startswith("CAP-"))
                )
                and not any(termo in desc_norm for termo in ("BOMBEIRO", "BALISTIC", "INDUSTRIAL", "EPI"))
            )
            if eh_capacete_moto:
                finalidade = "AUTOPECA_CONFIRMADA"
            try:
                resultado_st = ICMSSTMGService.analisar(
                    item.ncm,
                    {
                        "uf_origem": origem,
                        "uf_destino": destino,
                        "finalidade_automotiva": finalidade,
                    },
                    item.descricao,
                )
                if resultado_st.get("nao_aplicavel") or resultado_st.get("decisao_st") == "NAO":
                    decisao_st = False
                    motivo_st = str(resultado_st.get("status") or "fora da ST")
                elif resultado_st.get("decisao_st") == "SIM":
                    decisao_st = True
                    motivo_st = str(resultado_st.get("status") or "ICMS-ST confirmado")
            except Exception:
                decisao_st = None

        if decisao_st is True:
            return cfop_st, f"{motivo_st}; compra para revenda -> {cfop_st}."
        if decisao_st is False:
            return cfop_normal, f"{motivo_st}; compra para revenda sem ST -> {cfop_normal}."

        if atual in {"1102", "2102"}:
            return cfop_normal, (
                f"Mantida a natureza de compra para revenda sem ST já escriturada; alcance territorial -> {cfop_normal}."
            )

        if saida in CFOPS_SAIDA_VENDA_NORMAL:
            return "", (
                f"o XML traz venda normal ({saida}), mas o enquadramento ST do NCM {item.ncm or '-'} "
                "não ficou determinístico; o FiscalPro não troca o CFOP por hipótese"
            )
        return "", f"CFOP de saída {saida or '-'} não permite definir automaticamente a compra para revenda"

    @classmethod
    def _extrair_chave(cls, texto: str) -> str:
        linhas = texto.splitlines()
        blocos: list[str] = []
        for i, linha in enumerate(linhas):
            if "CHAVE DE ACESSO" in linha.upper():
                blocos.extend(linhas[i : i + 6])
        blocos.extend(linhas)

        vistos: set[str] = set()
        for linha in blocos:
            digitos = re.sub(r"\D", "", linha)
            if len(digitos) < 44:
                continue
            for inicio in range(0, len(digitos) - 43):
                candidato = digitos[inicio : inicio + 44]
                if candidato in vistos:
                    continue
                vistos.add(candidato)
                if not (11 <= int(candidato[:2]) <= 53):
                    continue
                if candidato[20:22] != "55":
                    continue
                if cls._chave_nfe_valida(candidato):
                    return candidato
        return ""

    @staticmethod
    def _chave_nfe_valida(chave: str) -> bool:
        if len(chave) != 44 or not chave.isdigit():
            return False
        soma = 0
        peso = 2
        for caractere in reversed(chave[:43]):
            soma += int(caractere) * peso
            peso += 1
            if peso > 9:
                peso = 2
        resto = soma % 11
        digito = 11 - resto
        if digito >= 10:
            digito = 0
        return digito == int(chave[43])

    def _extrair_totais(self, texto: str) -> tuple[Decimal, Decimal]:
        linhas = texto.splitlines()
        for i, linha in enumerate(linhas):
            normal = self._normalizar(linha)
            if "BASE DE CALC" not in normal or "ICMS" not in normal or "VALOR DO ICMS" not in normal:
                continue
            for j in range(i + 1, min(i + 6, len(linhas))):
                valores = self._numeros_monetarios(linhas[j])
                if len(valores) >= 2:
                    return valores[0], valores[1]
        return Decimal("0"), Decimal("0")

    def _extrair_itens(self, texto: str) -> list[ItemDANFEICMS]:
        itens: list[ItemDANFEICMS] = []
        padrao = re.compile(
            r"^(?P<prefixo>.*?)\s+(?P<ncm>\d{8})\s+(?P<cst>\d/\d{2}|\d{3})\s+"
            r"(?P<cfop>\d{4})\s+(?P<un>[A-Z0-9.]+)\s+(?P<resto>.+)$",
            re.IGNORECASE,
        )
        for linha in texto.splitlines():
            normal = " ".join(linha.split())
            achado = padrao.match(normal)
            if not achado:
                continue
            resto = achado.group("resto")
            # Alguns geradores de DANFE colam o V.IPI e a alíquota (ex.: 0,0012.00%).
            resto = re.sub(
                r"(\d+,\d{2})(\d{1,2})\.(\d{2})%",
                r"\1 \2,\3%",
                resto,
            )
            resto = re.sub(r"(?<!\d)(\d{1,2})\.(\d{2})%", r"\1,\2%", resto)
            numeros = [self._decimal_token(token) for token in re.findall(r"\d[\d.]*,\d+", resto)]
            numeros = [numero for numero in numeros if numero is not None]
            if len(numeros) < 6:
                continue
            quantidade, _valor_unitario, valor_item = numeros[:3]
            par = self._encontrar_base_icms(numeros, valor_item)
            if par is None:
                continue
            base, icms, aliquota = par
            prefixo = achado.group("prefixo").strip()
            codigo = prefixo.split()[0] if prefixo else ""
            cst = achado.group("cst").replace("/", "")
            if len(cst) == 2:
                cst = "0" + cst
            itens.append(
                ItemDANFEICMS(
                    ordem=len(itens) + 1,
                    codigo_pdf=codigo,
                    ncm=achado.group("ncm"),
                    cst=cst.zfill(3),
                    cfop_saida=achado.group("cfop"),
                    quantidade=quantidade,
                    valor_item=valor_item,
                    base_icms=base,
                    aliquota_icms=aliquota,
                    valor_icms=icms,
                )
            )
        return itens

    @staticmethod
    def _encontrar_base_icms(
        numeros: list[Decimal], valor_item: Decimal
    ) -> tuple[Decimal, Decimal, Decimal] | None:
        # Depois de quantidade, unitário e total, procura base/ICMS/alíquota que
        # matematicamente fechem. Isso suporta os layouts EBF, FW3 e Pro Tork.
        melhores: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
        for i in range(3, len(numeros) - 2):
            base = numeros[i]
            icms = numeros[i + 1]
            if base <= 0 or icms <= 0:
                continue
            for j in range(i + 2, min(len(numeros), i + 5)):
                aliquota = numeros[j]
                if not (Decimal("1") <= aliquota <= Decimal("30")):
                    continue
                calculado = (base * aliquota / Decimal("100")).quantize(CENTAVO, rounding=ROUND_HALF_UP)
                diferenca = (calculado - icms).copy_abs()
                if diferenca <= TOLERANCIA:
                    penalidade = (base - valor_item).copy_abs() + diferenca
                    melhores.append((penalidade, base, icms, aliquota))
        if not melhores:
            return None
        _, base, icms, aliquota = min(melhores, key=lambda item: item[0])
        return base, icms, aliquota

    @classmethod
    def _mapear_c100(cls, linhas: list[str]) -> dict[str, tuple[int, int]]:
        indices = [i for i, linha in enumerate(linhas) if cls._codigo(linha) == "C100"]
        limite = next((i for i, linha in enumerate(linhas) if cls._codigo(linha) == "C990"), len(linhas))
        mapa: dict[str, tuple[int, int]] = {}
        for posicao, inicio in enumerate(indices):
            fim = indices[posicao + 1] if posicao + 1 < len(indices) else limite
            campos = cls._campos(linhas[inicio])
            if len(campos) > 8 and campos[8].strip():
                mapa[campos[8].strip()] = (inicio, fim)
        return mapa

    @classmethod
    def _cnpj_empresa(cls, linhas: list[str]) -> str:
        for linha in linhas:
            campos = cls._campos(linha)
            if campos and campos[0] == "0000" and len(campos) > 7:
                return re.sub(r"\D", "", campos[6])
        return ""

    def _salvar_memoria(
        self,
        caminho: Path,
        memoria: list[tuple[NotaConferenciaDANFEICMS, int, str, ItemDANFEICMS, str, str, str]],
    ) -> None:
        with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(
                [
                    "Arquivo PDF",
                    "NF",
                    "Chave NF-e",
                    "Item",
                    "Código no SPED",
                    "CST",
                    "CFOP anterior",
                    "CFOP corrigido",
                    "Motivo CFOP",
                    "Base ICMS",
                    "Alíquota ICMS",
                    "Valor ICMS",
                ]
            )
            for nota, ordem, codigo_sped, item, cfop_anterior, cfop_novo, motivo_cfop in memoria:
                escritor.writerow(
                    [
                        nota.danfe.arquivo,
                        nota.danfe.numero_documento,
                        nota.danfe.chave_nfe,
                        ordem,
                        codigo_sped,
                        item.cst,
                        cfop_anterior,
                        cfop_novo,
                        motivo_cfop,
                        self._formatar(item.base_icms),
                        self._formatar(item.aliquota_icms),
                        self._formatar(item.valor_icms),
                    ]
                )

    def _salvar_relatorio(
        self,
        caminho: Path,
        sped: Path,
        analise: ResultadoAnaliseDANFEICMS,
    ) -> None:
        linhas = [
            "FISCALPRO - ICMS DAS COMPRAS PARA REVENDA POR XML/PDF",
            "=" * 78,
            f"SPED gerado: {sped.name}",
            f"CNPJ da empresa: {analise.cnpj_empresa}",
            f"Documentos lidos: {analise.total_pdfs}",
            f"Notas aptas e alteradas: {analise.total_aptas}",
            f"Itens alterados: {analise.total_itens_aptos}",
            f"CFOPs de entrada a corrigir: {analise.total_cfop_corrigir}",
            f"ICMS incluído nos C170/C190: R$ {self._formatar(analise.total_icms_apto)}",
            f"Documentos sem crédito: {analise.total_sem_credito}",
            f"Documentos para revisão: {analise.total_revisao}",
            f"Documentos não encontrados no SPED: {analise.total_nao_encontradas}",
            "",
            "DETALHAMENTO",
            "-" * 78,
        ]
        for nota in analise.notas:
            linhas.append(
                f"{nota.status:15} | NF {nota.danfe.numero_documento or '-':>9} | "
                f"ICMS R$ {self._formatar(nota.danfe.valor_icms_total):>12} | "
                f"{nota.danfe.arquivo} | {nota.observacao}"
            )
        linhas.extend(
            [
                "",
                "REGRAS DE SEGURANÇA",
                "- Somente C100 de entrada de terceiros (IND_OPER=0 e IND_EMIT=1).",
                "- A finalidade desta etapa é compra para revenda; CFOP de entrada é conferido por item.",
                "- 1102/2102 são usados para revenda sem ST e 1403/2403 para mercadoria sujeita à ST.",
                "- A alíquota de ICMS isoladamente nunca determina o CFOP.",
                "- XML/PDF, C100 e C170 devem coincidir em chave, quantidade, valores e totais.",
                "- Notas sem ICMS próprio destacado não são alteradas.",
                "- O arquivo original não é alterado e a validação final deve ser feita no PVA.",
            ]
        )
        caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    @staticmethod
    def _normalizar(texto: str) -> str:
        return (
            texto.upper()
            .replace("Á", "A")
            .replace("À", "A")
            .replace("Â", "A")
            .replace("Ã", "A")
            .replace("Ç", "C")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ô", "O")
            .replace("Õ", "O")
            .replace("Ú", "U")
        )

    @classmethod
    def _numeros_monetarios(cls, texto: str) -> list[Decimal]:
        tokens = re.findall(r"(?:R\$)?\s*\d{1,3}(?:\.\d{3})*,\d{2}|(?:R\$)?\s*\d+,\d{2}", texto)
        return [cls._decimal_token(token) for token in tokens if cls._decimal_token(token) is not None]

    @staticmethod
    def _decimal_token(valor: str) -> Decimal | None:
        texto = re.sub(r"[^0-9,.-]", "", str(valor or ""))
        if not texto:
            return None
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            return Decimal(texto)
        except InvalidOperation:
            return None

    @classmethod
    def _decimal(cls, valor: str) -> Decimal:
        return cls._decimal_token(valor) or Decimal("0")

    @staticmethod
    def _moeda(valor: Decimal) -> Decimal:
        return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)

    @classmethod
    def _formatar(cls, valor: Decimal) -> str:
        return format(cls._moeda(valor), "f").replace(".", ",")

    @staticmethod
    def _codigo(linha: str) -> str:
        partes = linha.lstrip("\ufeff").split("|")
        return partes[1].strip() if len(partes) > 1 else ""

    @staticmethod
    def _campos(linha: str) -> list[str]:
        texto = linha.lstrip("\ufeff").rstrip("\r\n")
        if not texto.startswith("|"):
            return []
        partes = texto.split("|")
        return partes[1:-1] if partes and partes[-1] == "" else partes[1:]

    @staticmethod
    def _montar(campos: list[str], quebra: str) -> str:
        return "|" + "|".join(campos) + "|" + quebra

    @staticmethod
    def _fim_linha(linha: str) -> str:
        if linha.endswith("\r\n"):
            return "\r\n"
        if linha.endswith("\n"):
            return "\n"
        return ""

    @classmethod
    def _quebra_padrao(cls, linhas: list[str]) -> str:
        for linha in linhas:
            fim = cls._fim_linha(linha)
            if fim:
                return fim
        return "\n"

    @staticmethod
    def _encoding_sem_bom(encoding: str) -> str:
        normal = (encoding or "utf-8").lower().replace("_", "-")
        return "utf-8" if normal in {"utf-8-sig", "utf8-sig", "utf-8", "utf8"} else encoding

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(max(0, min(100, percentual)), mensagem)
