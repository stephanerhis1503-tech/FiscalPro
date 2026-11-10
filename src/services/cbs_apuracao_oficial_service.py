"""RTC 2 - respostas oficiais incrementais da Apuracao Assistida da CBS.

Importa JSONs oficiais e compara com XMLs locais SEM apropriar credito,
SEM fechar apuracao e SEM presumir que uma janela incremental seja completa.
A API devolve CNPJ BASICO (8 digitos), nao CNPJ de filial (14).
Fonte: https://docs.receitafederal.gov.br/apuracao-cbs/
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import json
import re
import sqlite3

from src.core.caminhos import BANCO_FISCAL
from src.services.apuracao_assistida_local_service import ServicoApuracaoLocalRTC

TAMANHO_MAXIMO_JSON = 40 * 1024 * 1024
DATA_MINIMA = "1970-01-01T00:00:00+00:00"
TIPOS = ("debitos", "creditos")


def _numero(valor) -> str:
    if valor is None or isinstance(valor, bool):
        raise ValueError("Valor monetario obrigatorio nao informado pela Receita.")
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ValueError("Valor monetario invalido no JSON oficial.") from None
    if not numero.is_finite():
        raise ValueError("Valor monetario nao finito no JSON oficial.")
    return format(numero.quantize(Decimal("0.01")), ".2f")


def _opcional(valor) -> str:
    return "0.00" if valor is None else _numero(valor)


def _data_utc(texto) -> str:
    if not texto:
        return DATA_MINIMA
    try:
        momento = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
        if momento.tzinfo is None:
            raise ValueError("fuso ausente")
        return momento.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        raise ValueError("Data/hora de atualizacao invalida na resposta oficial.") from None


def _competencia(pa: str) -> str:
    texto = str(pa or "").strip()
    valido = re.fullmatch(r"(0[1-9]|1[0-2])/([0-9]{4})", texto)
    if not valido:
        raise ValueError("Periodo da apuracao ausente ou invalido no JSON.")
    return f"{valido.group(2)}-{valido.group(1)}"


def _identificador(tipo: str, comp: str, linha: dict) -> str:
    base = "|".join(
        str(x or "") for x in (
            tipo, comp, linha.get("origem"), linha.get("documento"),
            linha.get("chave"), linha.get("emissao"), linha.get("registro"),
        )
    )
    return sha256(base.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResultadoOficial:
    tipo: str
    cnpj_base: str
    novos: int
    atualizados: int
    ignorados_antigos: int
    periodos: tuple[str, ...]
    duplicado: bool = False


class ServicoCBSOficial:
    """Armazena snapshots incrementais, reconciliando somente quando ha chave."""

    def __init__(self, banco: str | Path | None = None):
        self.banco = Path(banco) if banco is not None else BANCO_FISCAL
        self.banco.parent.mkdir(parents=True, exist_ok=True)
        self._criar_tabelas()

    @staticmethod
    def cnpj_base(cnpj_completo: str) -> str:
        return ServicoApuracaoLocalRTC.validar_cnpj(cnpj_completo)[:8]

    def _conectar(self):
        con = sqlite3.connect(self.banco, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def _criar_tabelas(self):
        with closing(self._conectar()) as con, con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS cbs_oficial_registros (
                    id INTEGER PRIMARY KEY,
                    cnpj_base TEXT NOT NULL,
                    tipo TEXT NOT NULL CHECK(tipo IN ('debitos','creditos')),
                    competencia TEXT NOT NULL,
                    identidade TEXT NOT NULL,
                    origem INTEGER NOT NULL,
                    modelo INTEGER NOT NULL,
                    chave TEXT NOT NULL,
                    emissao TEXT NOT NULL,
                    registro TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    apurado TEXT NOT NULL,
                    saldo_devedor TEXT NOT NULL DEFAULT '0.00',
                    extinto TEXT NOT NULL DEFAULT '0.00',
                    apropriado TEXT NOT NULL DEFAULT '0.00',
                    a_apropriar TEXT NOT NULL DEFAULT '0.00',
                    saldo_credor TEXT NOT NULL DEFAULT '0.00',
                    hash_linha TEXT NOT NULL,
                    UNIQUE(cnpj_base, tipo, competencia, identidade)
                );
                CREATE INDEX IF NOT EXISTS idx_cbs_base_pa
                    ON cbs_oficial_registros(cnpj_base,competencia,tipo);
                CREATE TABLE IF NOT EXISTS cbs_oficial_importacoes (
                    id INTEGER PRIMARY KEY,
                    cnpj_base TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    hash_resposta TEXT NOT NULL,
                    ticket TEXT NOT NULL DEFAULT '',
                    gerado_em TEXT NOT NULL,
                    importado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    registros_recebidos INTEGER NOT NULL,
                    registros_novos INTEGER NOT NULL,
                    registros_atualizados INTEGER NOT NULL,
                    UNIQUE(cnpj_base,tipo,hash_resposta)
                );
                CREATE TABLE IF NOT EXISTS cbs_api_solicitacoes (
                    ticket TEXT PRIMARY KEY,
                    cnpj_base TEXT NOT NULL,
                    tipo TEXT NOT NULL CHECK(tipo IN ('debitos','creditos')),
                    ambiente TEXT NOT NULL DEFAULT 'PRODUCAO_BETA',
                    situacao TEXT NOT NULL,
                    solicitado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    detalhe TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_cbs_ticket_cota
                    ON cbs_api_solicitacoes(cnpj_base,tipo,solicitado_em);
            """)

    def registrar_tiquete(self, cnpj_completo: str, tipo: str, ticket: str):
        base = self.cnpj_base(cnpj_completo)
        if tipo not in TIPOS:
            raise ValueError("Tipo de consulta invalido.")
        ticket = str(ticket or "").strip()
        if not ticket or len(ticket) > 250 or not re.fullmatch(r"[A-Za-z0-9._-]+", ticket):
            raise ValueError("Tiquete da Receita invalido.")
        with closing(self._conectar()) as con, con:
            con.execute(
                "INSERT OR IGNORE INTO cbs_api_solicitacoes "
                "(ticket,cnpj_base,tipo,situacao) VALUES (?,?,?,?)",
                (ticket, base, tipo, "PENDENTE"),
            )

    def listar_tiquetes(self, cnpj_completo: str, tipo: str | None = None):
        base = self.cnpj_base(cnpj_completo)
        with closing(self._conectar()) as con:
            if tipo:
                linhas = con.execute(
                    "SELECT * FROM cbs_api_solicitacoes WHERE cnpj_base=? AND tipo=? "
                    "ORDER BY solicitado_em DESC LIMIT 60", (base, tipo),
                ).fetchall()
            else:
                linhas = con.execute(
                    "SELECT * FROM cbs_api_solicitacoes WHERE cnpj_base=? "
                    "ORDER BY solicitado_em DESC LIMIT 60", (base,),
                ).fetchall()
        return [dict(l) for l in linhas]

    def atualizar_tiquete(self, ticket: str, situacao: str, detalhe: str = ""):
        allowed = {"PENDENTE", "EM_PROCESSAMENTO", "CONCLUIDA", "ERRO", "EXPIRADA", "IMPORTADA"}
        if situacao not in allowed:
            raise ValueError("Situacao da consulta invalida.")
        with closing(self._conectar()) as con, con:
            con.execute(
                "UPDATE cbs_api_solicitacoes SET situacao=?, atualizado_em=CURRENT_TIMESTAMP, "
                "detalhe=? WHERE ticket=?",
                (situacao, str(detalhe or "")[:300], ticket),
            )

    def consultas_hoje(self, cnpj_completo: str, tipo: str):
        base = self.cnpj_base(cnpj_completo)
        with closing(self._conectar()) as con:
            return int(con.execute(
                "SELECT COUNT(*) FROM cbs_api_solicitacoes "
                "WHERE cnpj_base=? AND tipo=? AND date(solicitado_em)=date('now')",
                (base, tipo),
            ).fetchone()[0])

    def existe_pendente(self, cnpj_completo: str, tipo: str):
        base = self.cnpj_base(cnpj_completo)
        with closing(self._conectar()) as con:
            return con.execute(
                "SELECT 1 FROM cbs_api_solicitacoes WHERE cnpj_base=? AND tipo=? "
                "AND situacao IN ('PENDENTE','EM_PROCESSAMENTO','CONCLUIDA') LIMIT 1",
                (base, tipo),
            ).fetchone() is not None

    @staticmethod
    def _ler_payload(payload):
        if isinstance(payload, (bytes, bytearray)):
            if len(payload) > TAMANHO_MAXIMO_JSON:
                raise ValueError("Arquivo JSON maior que 40 MB.")
            try:
                obj = json.loads(payload)
            except (UnicodeError, json.JSONDecodeError):
                raise ValueError("Arquivo JSON da Receita invalido.") from None
        elif isinstance(payload, dict):
            obj = payload
        else:
            raise ValueError("Informe um JSON valido.")
        if not isinstance(obj, dict):
            raise ValueError("O arquivo deve conter um objeto JSON.")
        return obj

    @staticmethod
    def _normalizar_linha(tipo, comp, linha):
        if not isinstance(linha, dict):
            raise ValueError("Registro oficial em formato invalido.")
        cbs = linha.get("cbs")
        if not isinstance(cbs, dict):
            raise ValueError("Registro sem grupo CBS.")
        chave = str(linha.get("chave") or "").strip()
        if len(chave) > 100:
            raise ValueError("Chave oficial excessivamente longa.")
        try:
            origem = int(linha["origem"])
            modelo = int(linha["documento"])
        except (ValueError, TypeError, KeyError):
            raise ValueError("Tipo de documento ou origem oficial invalida.") from None
        aprop = cbs.get("apropriacao") or {}
        if not isinstance(aprop, dict):
            raise ValueError("Bloco de apropriacao invalido.")
        uso = aprop.get("utilizacao") or {}
        if not isinstance(uso, dict):
            raise ValueError("Bloco de utilizacao invalido.")
        nao_utilizado = uso.get("naoUtilizado") or {}
        if not isinstance(nao_utilizado, dict):
            raise ValueError("Bloco de saldo credor invalido.")
        ident = _identificador(tipo, comp, linha)
        normalizado = {
            "tipo": tipo, "competencia": comp, "identidade": ident,
            "origem": origem, "modelo": modelo, "chave": chave,
            "emissao": str(linha.get("emissao") or ""),
            "registro": str(linha.get("registro") or ""),
            "atualizado_em": _data_utc(linha.get("atualizacao")),
            "apurado": _numero(cbs.get("apurado")),
            "saldo_devedor": _opcional(cbs.get("saldoDevedor")),
            "extinto": _opcional(cbs.get("extinto")),
            "apropriado": _opcional(aprop.get("apropriado")),
            "a_apropriar": _opcional(aprop.get("aApropriar")),
            "saldo_credor": _opcional(nao_utilizado.get("saldoCredor")),
            "hash_linha": sha256(
                json.dumps(linha, sort_keys=True, ensure_ascii=False, default=str).encode()
            ).hexdigest(),
        }
        return normalizado

    def importar(self, payload, tipo: str, cnpj_completo: str, ticket: str = "") -> ResultadoOficial:
        if tipo not in TIPOS:
            raise ValueError("Selecione Debitos ou Creditos.")
        base = self.cnpj_base(cnpj_completo)
        objeto = self._ler_payload(payload)
        if ticket:
            retorno_ticket = objeto.get("tiqueteSolicitacao")
            if not isinstance(retorno_ticket, str) or retorno_ticket != ticket:
                raise ValueError(
                    "O tiquete do JSON oficial nao corresponde a consulta concluida. "
                    "Nenhum dado foi importado."
                )
        # Campo 'ni' representa a RAIZ da empresa consultada (8 digitos).
        # 'niConsumidor' e a pessoa/empresa detentora da credencial e pode ser diferente.
        ni = objeto.get("ni")
        if not isinstance(ni, str) or not re.fullmatch(r"\d{8}", ni):
            raise ValueError(
                "Campo ni do retorno oficial ausente ou fora do formato esperado "
                "(8 digitos). O niConsumidor nao deve ser usado para identificar "
                "a empresa consultada. Nenhum dado foi importado."
            )
        if ni != base:
            raise ValueError(
                f"CNPJ basico divergente: empresa selecionada = {base}; "
                f"retorno oficial (campo ni) = {ni}. "
                "O campo niConsumidor identifica quem usa a credencial, nao "
                "a empresa da apuracao. Confira a representacao e o tiquete. "
                "Nenhum dado foi importado."
            )
        apuracoes = objeto.get("apuracao")
        if not isinstance(apuracoes, list):
            raise ValueError("JSON oficial sem lista de apuracoes.")
        declarados = []
        periodos: set[str] = set()
        for ap in apuracoes:
            if not isinstance(ap, dict):
                raise ValueError("Periodo oficial invalido.")
            comp = _competencia(ap.get("pa"))
            periodos.add(comp)
            itens = ap.get(tipo)
            if not isinstance(itens, list):
                raise ValueError(f"JSON oficial sem grupo {tipo} esperado.")
            for linha in itens:
                declarados.append(self._normalizar_linha(tipo, comp, linha))
        if len(declarados) > 150000:
            raise ValueError("Excesso de registros oficiais neste lote.")
        gerado = _data_utc(objeto.get("geradoEm"))
        ticket_resposta = str(objeto.get("tiqueteSolicitacao") or "")[:250]
        if ticket and ticket_resposta and ticket != ticket_resposta:
            raise ValueError("Tiquete do arquivo nao corresponde ao da solicitacao.")
        ticket = ticket or ticket_resposta
        hash_resposta = sha256(
            json.dumps(objeto, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        novos = atualizados = antigos = 0
        with closing(self._conectar()) as con, con:
            ja = con.execute(
                "SELECT 1 FROM cbs_oficial_importacoes WHERE "
                "cnpj_base=? AND tipo=? AND hash_resposta=?",
                (base, tipo, hash_resposta),
            ).fetchone()
            if ja:
                return ResultadoOficial(tipo, base, 0, 0, 0, tuple(sorted(periodos)), True)
            for linha in declarados:
                anterior = con.execute(
                    "SELECT * FROM cbs_oficial_registros WHERE "
                    "cnpj_base=? AND tipo=? AND competencia=? AND identidade=?",
                    (base, tipo, linha["competencia"], linha["identidade"]),
                ).fetchone()
                if anterior is None:
                    valores = {"cnpj_base": base, **linha}
                    colunas = tuple(valores)
                    con.execute(
                        f"INSERT INTO cbs_oficial_registros ({', '.join(colunas)}) "
                        f"VALUES ({', '.join('?' for _ in colunas)})",
                        tuple(valores.values()),
                    )
                    novos += 1
                elif (
                    linha["atualizado_em"] >= anterior["atualizado_em"]
                    and linha["hash_linha"] != anterior["hash_linha"]
                ):
                    chaves = tuple(linha.keys())
                    con.execute(
                        "UPDATE cbs_oficial_registros SET "
                        + ", ".join(f"{campo}=?" for campo in chaves)
                        + " WHERE id=?",
                        tuple(linha.values()) + (anterior["id"],),
                    )
                    atualizados += 1
                else:
                    antigos += 1
            con.execute(
                "INSERT INTO cbs_oficial_importacoes "
                "(cnpj_base,tipo,hash_resposta,ticket,gerado_em,registros_recebidos,"
                "registros_novos,registros_atualizados) VALUES (?,?,?,?,?,?,?,?)",
                (base, tipo, hash_resposta, ticket, gerado, len(declarados), novos, atualizados),
            )
            if ticket:
                con.execute(
                    "UPDATE cbs_api_solicitacoes SET situacao='IMPORTADA', "
                    "atualizado_em=CURRENT_TIMESTAMP WHERE ticket=? AND cnpj_base=? AND tipo=?",
                    (ticket, base, tipo),
                )
        return ResultadoOficial(tipo, base, novos, atualizados, antigos, tuple(sorted(periodos)))

    @staticmethod
    def filtrar_conciliacao(locais: list[dict], oficiais: list[dict], tipo: str):
        """Presenca numa janela incremental NAO prova completude do periodo."""
        if tipo not in TIPOS:
            raise ValueError("Tipo invalido.")
        direcao = "SAIDA" if tipo == "debitos" else "ENTRADA"
        comparaveis = [
            doc for doc in oficiais
            if int(doc["origem"]) == 0 and int(doc["modelo"]) in (55, 65)
            and re.fullmatch(r"\d{44}", doc["chave"])
        ]
        por_chave: dict[str, list[dict]] = {}
        for doc in comparaveis:
            por_chave.setdefault(doc["chave"], []).append(doc)
        saida = []
        for xml in locais:
            if xml["direcao"] != direcao:
                continue
            candidatos = por_chave.get(xml["chave_nfe"], [])
            # Pode haver mais de um registro oficial para a chave.
            if len(candidatos) != 1:
                estado = "SEM_DADO_NESTE_RETORNO" if not candidatos else "MULTIPLOS_OFICIAIS_REVISAR"
                oficial = None
            else:
                oficial = candidatos[0]
                vl_xml = Decimal(xml["valor_cbs"])
                vl_oficial = Decimal(oficial["apurado"])
                estado = "CONFERE" if abs(vl_xml - vl_oficial) <= Decimal("0.02") else "DIFERENCA_REVISAR"
            saida.append({
                "chave": xml["chave_nfe"],
                "nf": xml["numero_nf"],
                "tipo": direcao,
                "cbs_xml": xml["valor_cbs"],
                "cbs_oficial": oficial["apurado"] if oficial else "",
                "saldo_oficial": oficial["saldo_devedor"] if tipo == "debitos" and oficial else "",
                "apropriado_oficial": oficial["apropriado"] if tipo == "creditos" and oficial else "",
                "a_apropriar_oficial": oficial["a_apropriar"] if tipo == "creditos" and oficial else "",
                "status": estado,
            })
        return saida

    def conciliar(self, cnpj_completo: str, competencia: str, tipo: str):
        if tipo not in TIPOS:
            raise ValueError("Tipo invalido.")
        comp = ServicoApuracaoLocalRTC.validar_competencia(competencia)
        base = self.cnpj_base(cnpj_completo)
        local = ServicoApuracaoLocalRTC(self.banco).listar(cnpj_completo, comp)
        with closing(self._conectar()) as con:
            oficial = [
                dict(l) for l in con.execute(
                    "SELECT * FROM cbs_oficial_registros "
                    "WHERE cnpj_base=? AND competencia=? AND tipo=?",
                    (base, comp, tipo),
                ).fetchall()
            ]
        return self.filtrar_conciliacao(local, oficial, tipo)

    def historico(self, cnpj_completo: str, tipo: str | None = None):
        base = self.cnpj_base(cnpj_completo)
        with closing(self._conectar()) as con:
            if tipo:
                itens = con.execute(
                    "SELECT * FROM cbs_oficial_importacoes WHERE cnpj_base=? "
                    "AND tipo=? ORDER BY id DESC LIMIT 30", (base, tipo),
                ).fetchall()
            else:
                itens = con.execute(
                    "SELECT * FROM cbs_oficial_importacoes WHERE cnpj_base=? "
                    "ORDER BY id DESC LIMIT 30", (base,),
                ).fetchall()
        return [dict(x) for x in itens]
