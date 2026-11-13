"""RTC 1: base local de conferencia de IBS/CBS por CNPJ e competencia.

Somente leitura de XMLs NF-e; nao consulta nem altera a apuracao oficial.
Credito de entradas e sempre potencial, nunca apropriado automaticamente.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile

from src.core.caminhos import BANCO_FISCAL
from src.services.xml_ibscbs_service import ServicoXMLIBSCBS, _Documento

MAX_XML_BYTES = 10 * 1024 * 1024
MAX_ZIP_BYTES = 256 * 1024 * 1024
MAX_ZIP_ENTRADAS = 10000
CENTAVO = Decimal("0.01")


@dataclass
class ResultadoImportacaoRTC:
    lidos: int = 0
    importados: int = 0
    duplicados: int = 0
    atualizados: int = 0
    conflitos: int = 0
    ignorados: int = 0
    avisos: list[str] = field(default_factory=list)

    def avisar(self, mensagem: str) -> None:
        if len(self.avisos) < 35:
            self.avisos.append(mensagem)


class ServicoApuracaoLocalRTC:
    """Persistencia independente para conferir XML contra futuras APIs oficiais."""

    def __init__(self, banco: str | Path | None = None) -> None:
        self.banco = Path(banco) if banco is not None else BANCO_FISCAL
        self.banco.parent.mkdir(parents=True, exist_ok=True)
        self._criar_tabelas()

    @staticmethod
    def validar_cnpj(valor: str) -> str:
        cnpj = "".join(c for c in str(valor or "") if c.isdigit())
        if len(cnpj) != 14:
            raise ValueError("Selecione uma empresa com CNPJ de 14 digitos no Cadastro Central.")
        return cnpj

    @staticmethod
    def validar_competencia(valor: str) -> str:
        competencia = str(valor or "").strip()
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", competencia):
            raise ValueError("Competencia invalida. Utilize AAAA-MM (ex.: 2026-11).")
        return competencia

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.banco, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def _criar_tabelas(self) -> None:
        with closing(self._conectar()) as con, con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS rtc_documentos_xml (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cnpj_empresa TEXT NOT NULL,
                    competencia TEXT NOT NULL,
                    chave_nfe TEXT NOT NULL,
                    numero_nf TEXT NOT NULL DEFAULT '',
                    emissao TEXT NOT NULL,
                    cnpj_emitente TEXT NOT NULL,
                    cnpj_destinatario TEXT NOT NULL,
                    direcao TEXT NOT NULL CHECK (direcao IN ('SAIDA', 'ENTRADA')),
                    base_ibs_cbs TEXT NOT NULL DEFAULT '0.00',
                    valor_ibs TEXT NOT NULL DEFAULT '0.00',
                    valor_cbs TEXT NOT NULL DEFAULT '0.00',
                    status_conferencia TEXT NOT NULL,
                    status_protocolo TEXT NOT NULL,
                    status_credito TEXT NOT NULL,
                    observacao TEXT NOT NULL DEFAULT '',
                    arquivo_origem TEXT NOT NULL,
                    hash_xml TEXT NOT NULL,
                    importado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (cnpj_empresa, chave_nfe)
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS rtc_documentos_atualizacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    documento_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL,
                    hash_anterior TEXT NOT NULL,
                    hash_novo TEXT NOT NULL,
                    status_anterior TEXT NOT NULL,
                    status_novo TEXT NOT NULL,
                    registrado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (documento_id) REFERENCES rtc_documentos_xml(id)
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_rtc_empresa_comp "
                "ON rtc_documentos_xml (cnpj_empresa, competencia)"
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS rtc_documentos_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    documento_id INTEGER NOT NULL,
                    numero_item TEXT NOT NULL,
                    codigo_produto TEXT NOT NULL DEFAULT '',
                    descricao TEXT NOT NULL DEFAULT '',
                    ncm TEXT NOT NULL DEFAULT '',
                    cfop TEXT NOT NULL DEFAULT '',
                    cst_ibscbs TEXT NOT NULL DEFAULT '',
                    cclass_trib TEXT NOT NULL DEFAULT '',
                    base_ibs_cbs TEXT NOT NULL DEFAULT '',
                    valor_ibs TEXT NOT NULL DEFAULT '',
                    valor_cbs TEXT NOT NULL DEFAULT '',
                    status_auditoria TEXT NOT NULL,
                    perfil TEXT NOT NULL DEFAULT '',
                    regra TEXT NOT NULL DEFAULT '',
                    motivos TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (documento_id) REFERENCES rtc_documentos_xml(id),
                    UNIQUE (documento_id, numero_item)
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_rtc_itens_documento "
                "ON rtc_documentos_itens (documento_id)"
            )

    @staticmethod
    def _nome_tag(elemento: ET.Element) -> str:
        return str(elemento.tag).split("}", 1)[-1]

    @classmethod
    def _desc(cls, no: ET.Element, nome: str) -> ET.Element | None:
        return next((elem for elem in no.iter() if cls._nome_tag(elem) == nome), None)

    @classmethod
    def _filho_texto(cls, no: ET.Element | None, nome: str) -> str:
        if no is None:
            return ""
        return next((str(e.text or "").strip() for e in list(no) if cls._nome_tag(e) == nome), "")

    @staticmethod
    def _quantia(valor: str) -> str:
        try:
            num = Decimal(str(valor or "0").replace(",", "."))
        except (InvalidOperation, ValueError):
            raise ValueError("Valor IBS/CBS invalido no XML.") from None
        if not num.is_finite() or num < 0:
            raise ValueError("Valor IBS/CBS negativo ou nao finito no XML.")
        return format(num.quantize(CENTAVO), ".2f")

    @classmethod
    def _ler_documentos(cls, caminho: Path):
        if caminho.suffix.lower() == ".xml":
            if caminho.stat().st_size > MAX_XML_BYTES:
                raise ValueError("XML acima do limite de 10 MB.")
            yield caminho.name, caminho.read_bytes()
            return
        if caminho.suffix.lower() != ".zip":
            raise ValueError("Formato nao suportado (use XML ou ZIP).")
        with zipfile.ZipFile(caminho) as pacote:
            entradas = [
                item for item in pacote.infolist()
                if not item.is_dir() and item.filename.lower().endswith(".xml")
            ]
            if len(entradas) > MAX_ZIP_ENTRADAS:
                raise ValueError("ZIP com excesso de XMLs.")
            if sum(item.file_size for item in entradas) > MAX_ZIP_BYTES:
                raise ValueError("ZIP acima do limite de 256 MB descompactados.")
            for item in entradas:
                if item.file_size > MAX_XML_BYTES:
                    raise ValueError("ZIP contem XML acima do limite de 10 MB.")
                if item.flag_bits & 1:
                    raise ValueError("ZIP contem XML criptografado.")
                with pacote.open(item) as entrada:
                    dados = entrada.read(MAX_XML_BYTES + 1)
                if len(dados) > MAX_XML_BYTES:
                    raise ValueError("XML descompactado acima do limite.")
                yield f"{caminho.name}::{item.filename}", dados

    @staticmethod
    def _arquivos(caminhos: list[str | Path]) -> list[Path]:
        encontrados: list[Path] = []
        for entrada in caminhos:
            path = Path(entrada)
            if path.is_dir():
                encontrados.extend(
                    sorted(p for p in path.rglob("*")
                           if p.is_file() and p.suffix.lower() in {".xml", ".zip"})
                )
            else:
                encontrados.append(path)
        return encontrados

    @classmethod
    def _protocolo(cls, raiz: ET.Element, chave: str) -> str:
        protocolo = cls._desc(raiz, "infProt")
        if protocolo is None:
            return "SEM_PROTOCOLO"
        ch_prot = cls._filho_texto(protocolo, "chNFe")
        cstat = cls._filho_texto(protocolo, "cStat")
        if ch_prot != chave:
            return "PROTOCOLO_DIVERGENTE"
        if cstat in {"100", "150"}:
            return "PROTOCOLO_100_150_XML"
        return "PROTOCOLO_NAO_AUTORIZADO"

    @classmethod
    def _extrair(
        cls, nome: str, dados: bytes, cnpj: str, competencia: str,
        itens_auditoria: list[dict] | None = None,
    ) -> dict:
        if len(dados) > MAX_XML_BYTES or b"<!DOCTYPE" in dados.upper():
            raise ValueError("XML excede limite ou contem DTD nao permitida.")
        raiz = ET.fromstring(dados)
        if cls._nome_tag(raiz) not in {"NFe", "nfeProc"}:
            raise ValueError("Documento nao e uma NF-e (eventos e outros XMLs nao entram).")
        resumo, _itens, _tags, auditorias = ServicoXMLIBSCBS._analisar_documento(_Documento(nome, dados))
        if not re.fullmatch(r"\d{44}", resumo.chave):
            raise ValueError("Chave de NF-e ausente ou invalida.")
        if resumo.itens_xml == 0:
            raise ValueError("NF-e sem itens; revise o XML.")
        try:
            data_emissao = date.fromisoformat(resumo.emissao[:10])
        except (ValueError, TypeError):
            raise ValueError("Data de emissao ausente ou invalida.") from None
        if data_emissao.strftime("%Y-%m") != competencia:
            raise ValueError(
                f"NF-e emitida em {data_emissao:%Y-%m}; selecione a competencia correspondente."
            )
        emit = "".join(d for d in resumo.emitente_cnpj if d.isdigit())
        dest = "".join(d for d in resumo.destinatario_cnpj if d.isdigit())
        if emit == cnpj and dest == cnpj:
            raise ValueError("NF-e com emitente e destinatario iguais: conferir manualmente.")
        if emit != cnpj and dest != cnpj:
            raise ValueError("NF-e nao pertence ao CNPJ selecionado.")
        direcao = "SAIDA" if emit == cnpj else "ENTRADA"

        inf = cls._desc(raiz, "infNFe")
        if inf is None or inf.attrib.get("Id") != f"NFe{resumo.chave}":
            raise ValueError("Identificador da NF-e inconsistente.")
        protocolo = cls._protocolo(raiz, resumo.chave)
        if protocolo in {"PROTOCOLO_DIVERGENTE", "PROTOCOLO_NAO_AUTORIZADO"}:
            raise ValueError("Protocolo da NF-e divergente ou nao autorizado.")

        observacoes: list[str] = []
        if resumo.status != "OK":
            observacoes.append(resumo.detalhe or resumo.status)
        if protocolo == "SEM_PROTOCOLO":
            observacoes.append("XML sem protocolo SEFAZ: confirmar autorizacao.")
        revisoes = sum(1 for item in auditorias if item.status == "REVISAR")
        especiais = sum(1 for item in auditorias if item.status == "REGRA ESPECIAL")
        if revisoes:
            observacoes.append(f"{revisoes} item(ns) requerem revisao tributaria.")
        if especiais:
            observacoes.append(f"{especiais} item(ns) com regra especial a conferir.")
        situacao = (
            "CONFERIDO_XML"
            if resumo.status == "OK"
            and not revisoes and not especiais
            and protocolo != "SEM_PROTOCOLO"
            else "REVISAR"
        )
        # Captura todos os itens, inclusive os sem grupo IBS/CBS, para
        # revisao estrutural. O CFOP e conferido apenas em formato; seu
        # enquadramento legal depende da operacao e deve ser validado por pessoa.
        if itens_auditoria is not None:
            for posicao, item in enumerate(auditorias, 1):
                cfop = str(item.cfop or "").strip()
                motivos = str(item.motivos or "")
                status = item.status
                if not re.fullmatch(r"[0-9]{4}", cfop) or cfop[0] not in "123567":
                    status = "REVISAR"
                    motivos = "; ".join(
                        x for x in (motivos, "CFOP ausente ou fora do formato esperado")
                        if x
                    )
                numero = str(item.item or "").strip()
                if not numero:
                    status = "REVISAR"
                    numero = str(posicao)
                    motivos = "; ".join(
                        x for x in (motivos, "nItem ausente no XML") if x
                    )
                itens_auditoria.append({
                    "numero_item": numero,
                    "codigo_produto": str(item.codigo_produto or "")[:250],
                    "descricao": str(item.descricao or "")[:1000],
                    "ncm": str(item.ncm or ""),
                    "cfop": cfop,
                    "cst_ibscbs": str(item.cst_encontrado or ""),
                    "cclass_trib": str(item.cclass_encontrado or ""),
                    "base_ibs_cbs": str(item.vbc or ""),
                    "valor_ibs": str(item.v_ibs_encontrado or ""),
                    "valor_cbs": str(item.v_cbs_encontrado or ""),
                    "status_auditoria": status,
                    "perfil": str(item.perfil or "")[:250],
                    "regra": str(item.regra or "")[:1000],
                    "motivos": motivos[:1500],
                })
        # Entradas NAO constituem credito apropriado: so potencial contabilizavel
        # apos validacoes legais e confronto com a apuracao oficial.
        return {
            "cnpj_empresa": cnpj,
            "competencia": competencia,
            "chave_nfe": resumo.chave,
            "numero_nf": resumo.numero_nf,
            "emissao": data_emissao.isoformat(),
            "cnpj_emitente": emit,
            "cnpj_destinatario": dest,
            "direcao": direcao,
            "base_ibs_cbs": cls._quantia(resumo.total_base or resumo.soma_base_itens),
            "valor_ibs": cls._quantia(resumo.total_ibs or resumo.soma_ibs_itens),
            "valor_cbs": cls._quantia(resumo.total_cbs or resumo.soma_cbs_itens),
            "status_conferencia": situacao,
            "status_protocolo": protocolo,
            "status_credito": (
                "POTENCIAL_NAO_APROPRIADO" if direcao == "ENTRADA" else "NAO_APLICAVEL"
            ),
            "observacao": " ".join(observacoes),
            "arquivo_origem": nome[:500],
            "hash_xml": sha256(dados).hexdigest(),
        }

    @staticmethod
    def _mesmo_conteudo_fiscal(anterior: sqlite3.Row, novo: dict) -> bool:
        """Somente aceita promocao de XML sem protocolo se os dados fiscais conferirem."""
        campos = (
            "cnpj_empresa", "competencia", "chave_nfe", "numero_nf",
            "emissao", "cnpj_emitente", "cnpj_destinatario", "direcao",
            "base_ibs_cbs", "valor_ibs", "valor_cbs", "status_credito",
        )
        return all(str(anterior[campo]) == str(novo[campo]) for campo in campos)

    @staticmethod
    def _gravar_itens_se_ausentes(
        con: sqlite3.Connection, documento_id: int, itens: list[dict]
    ) -> int:
        """Backfill conservador; nunca sobrepoe item anteriormente salvo."""
        existente = con.execute(
            "SELECT 1 FROM rtc_documentos_itens WHERE documento_id=? LIMIT 1",
            (documento_id,),
        ).fetchone()
        if existente or not itens:
            return 0
        gravados = 0
        for item in itens:
            colunas = ("documento_id", *item.keys())
            cursor = con.execute(
                f"INSERT OR IGNORE INTO rtc_documentos_itens "
                f"({', '.join(colunas)}) "
                f"VALUES ({', '.join('?' for _ in colunas)})",
                (documento_id, *item.values()),
            )
            gravados += cursor.rowcount
        return gravados

    def importar(
        self, caminhos: list[str | Path], cnpj_empresa: str, competencia: str
    ) -> ResultadoImportacaoRTC:
        cnpj = self.validar_cnpj(cnpj_empresa)
        comp = self.validar_competencia(competencia)
        resultado = ResultadoImportacaoRTC()
        with closing(self._conectar()) as con:
            for caminho in self._arquivos(caminhos):
                try:
                    for nome, dados in self._ler_documentos(caminho):
                        resultado.lidos += 1
                        try:
                            itens_detalhados: list[dict] = []
                            doc = self._extrair(
                                nome, dados, cnpj, comp,
                                itens_auditoria=itens_detalhados,
                            )
                            anterior = con.execute(
                                "SELECT * FROM rtc_documentos_xml "
                                "WHERE cnpj_empresa = ? AND chave_nfe = ?",
                                (cnpj, doc["chave_nfe"]),
                            ).fetchone()
                            if anterior:
                                if anterior["hash_xml"] == doc["hash_xml"]:
                                    with con:
                                        self._gravar_itens_se_ausentes(
                                            con, anterior["id"], itens_detalhados,
                                        )
                                    resultado.duplicados += 1
                                elif (
                                    anterior["status_protocolo"] == "SEM_PROTOCOLO"
                                    and doc["status_protocolo"] == "PROTOCOLO_100_150_XML"
                                    and self._mesmo_conteudo_fiscal(anterior, doc)
                                ):
                                    # Apenas agrega autorizacao documental quando
                                    # a identidade e TODOS os totais permanecem iguais.
                                    # O historico registra o hash anterior.
                                    with con:
                                        con.execute(
                                            """
                                            INSERT INTO rtc_documentos_atualizacoes
                                            (documento_id, tipo, hash_anterior, hash_novo,
                                             status_anterior, status_novo)
                                            VALUES (?, ?, ?, ?, ?, ?)
                                            """,
                                            (
                                                anterior["id"], "COMPLEMENTO_PROTOCOLO",
                                                anterior["hash_xml"], doc["hash_xml"],
                                                anterior["status_conferencia"],
                                                doc["status_conferencia"],
                                            ),
                                        )
                                        con.execute(
                                            """
                                            UPDATE rtc_documentos_xml
                                            SET status_conferencia = ?, status_protocolo = ?,
                                                observacao = ?, arquivo_origem = ?,
                                                hash_xml = ?
                                            WHERE id = ? AND hash_xml = ?
                                            """,
                                            (
                                                doc["status_conferencia"],
                                                doc["status_protocolo"],
                                                doc["observacao"], doc["arquivo_origem"],
                                                doc["hash_xml"], anterior["id"],
                                                anterior["hash_xml"],
                                            ),
                                        )
                                    with con:
                                        self._gravar_itens_se_ausentes(
                                            con, anterior["id"], itens_detalhados,
                                        )
                                    resultado.atualizados += 1
                                else:
                                    resultado.conflitos += 1
                                    resultado.avisar(
                                        f"{nome}: chave ja registrada, mas XML diverge "
                                        "ou nao e complemento seguro de protocolo; "
                                        "o registro existente foi preservado."
                                    )
                                continue
                            campos = tuple(doc)
                            with con:
                                cursor = con.execute(
                                    f"INSERT INTO rtc_documentos_xml ({', '.join(campos)}) "
                                    f"VALUES ({', '.join('?' for _ in campos)})",
                                    tuple(doc.values()),
                                )
                                self._gravar_itens_se_ausentes(
                                    con, cursor.lastrowid, itens_detalhados,
                                )
                            resultado.importados += 1
                        except (ValueError, ET.ParseError, sqlite3.Error) as exc:
                            resultado.ignorados += 1
                            resultado.avisar(f"{nome}: {exc}")
                except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
                    resultado.ignorados += 1
                    resultado.avisar(f"{caminho.name}: {exc}")
        return resultado

    def listar(self, cnpj_empresa: str, competencia: str) -> list[dict]:
        cnpj = self.validar_cnpj(cnpj_empresa)
        comp = self.validar_competencia(competencia)
        with closing(self._conectar()) as con:
            linhas = con.execute(
                "SELECT * FROM rtc_documentos_xml "
                "WHERE cnpj_empresa = ? AND competencia = ? "
                "ORDER BY emissao, numero_nf, chave_nfe",
                (cnpj, comp),
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def listar_itens(
        self, cnpj_empresa: str, competencia: str, *, limite: int | None = None,
        revisar_apenas: bool = False,
    ) -> list[dict]:
        """Auditoria de itens extraidos dos XMLs locais (sem consulta externa)."""
        cnpj = self.validar_cnpj(cnpj_empresa)
        comp = self.validar_competencia(competencia)
        if limite is not None and (type(limite) is not int or not 1 <= limite <= 10000):
            raise ValueError("Limite de itens invalido.")
        sql = """
            SELECT d.cnpj_empresa, d.competencia, d.chave_nfe, d.numero_nf,
                   d.emissao, d.direcao, d.status_protocolo,
                   i.numero_item, i.codigo_produto, i.descricao,
                   i.ncm, i.cfop, i.cst_ibscbs, i.cclass_trib,
                   i.base_ibs_cbs, i.valor_ibs, i.valor_cbs,
                   i.status_auditoria, i.perfil, i.regra, i.motivos
            FROM rtc_documentos_itens AS i
            INNER JOIN rtc_documentos_xml AS d ON d.id=i.documento_id
            WHERE d.cnpj_empresa=? AND d.competencia=?
        """
        if revisar_apenas:
            sql += " AND i.status_auditoria != 'OK'"
        sql += " ORDER BY d.emissao, d.numero_nf, d.chave_nfe, i.id"
        parametros: tuple = (cnpj, comp)
        if limite is not None:
            sql += " LIMIT ?"
            parametros += (limite,)
        with closing(self._conectar()) as con:
            linhas = con.execute(sql, parametros).fetchall()
        return [dict(linha) for linha in linhas]

    def contar_itens(self, cnpj_empresa: str, competencia: str) -> int:
        cnpj = self.validar_cnpj(cnpj_empresa)
        comp = self.validar_competencia(competencia)
        with closing(self._conectar()) as con:
            return int(con.execute(
                """
                SELECT COUNT(*) FROM rtc_documentos_itens AS i
                JOIN rtc_documentos_xml AS d ON d.id=i.documento_id
                WHERE d.cnpj_empresa=? AND d.competencia=?
                """,
                (cnpj, comp),
            ).fetchone()[0])

    def resumo(self, cnpj_empresa: str, competencia: str) -> dict:
        linhas = self.listar(cnpj_empresa, competencia)
        totais = {
            "documentos": len(linhas),
            "saidas": 0,
            "entradas": 0,
            "revisar": 0,
            "ibs_debito_xml": Decimal("0.00"),
            "cbs_debito_xml": Decimal("0.00"),
            "ibs_credito_potencial": Decimal("0.00"),
            "cbs_credito_potencial": Decimal("0.00"),
        }
        for doc in linhas:
            if doc["status_conferencia"] == "REVISAR":
                totais["revisar"] += 1
            if doc["direcao"] == "SAIDA":
                totais["saidas"] += 1
                totais["ibs_debito_xml"] += Decimal(doc["valor_ibs"])
                totais["cbs_debito_xml"] += Decimal(doc["valor_cbs"])
            else:
                totais["entradas"] += 1
                totais["ibs_credito_potencial"] += Decimal(doc["valor_ibs"])
                totais["cbs_credito_potencial"] += Decimal(doc["valor_cbs"])
        return totais
