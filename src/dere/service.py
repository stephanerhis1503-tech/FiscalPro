"""Pré-validação local de XMLs da DeRE.

Base técnica vigente implementada no FiscalPro 18.2.3:
- pacote DeRE 1.2.0 (RFB/CGIBS, setembro/2026);
- atualização de Produção Restrita vigente em 22/09/2026;
- D-1011 / evtPGCC: infoConta até 150.000 ocorrências, XSD v1.0.3;
- D-1101 / evtBalancete: infoConta até 90.000 ocorrências, XSD v1.0.1.

O módulo não transmite declarações. Ele faz conferência local, identifica o
leiaute e pode validar contra um pacote XSD oficial informado pelo usuário.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable
import re
import zipfile
import xml.etree.ElementTree as ET


EVENTOS_DERE = {
    "evtInfoContrib": {
        "codigo": "D-1001",
        "nome": "Informações do Contribuinte",
        "versao_xsd": "1.0.1",
        "grupo_contagem": "",
        "limite_grupo": None,
        "categoria": "Tabela",
    },
    "evtPGCC": {
        "codigo": "D-1011",
        "nome": "Plano Geral de Contas Comentado",
        "versao_xsd": "1.0.3",
        "grupo_contagem": "infoConta",
        "limite_grupo": 150_000,
        "categoria": "Tabela",
    },
    "evtBalancete": {
        "codigo": "D-1101",
        "nome": "Balancete Mensal",
        "versao_xsd": "1.0.1",
        "grupo_contagem": "infoConta",
        "limite_grupo": 90_000,
        "categoria": "Periódico mensal",
    },
    "evtAplicResTec": {
        "codigo": "D-1106",
        "nome": "Identificação de Aplicações Financeiras",
        "versao_xsd": "1.0.0",
        "grupo_contagem": "infoAplic",
        "limite_grupo": 100,
        "limite_secundario_grupo": "detAtivo",
        "limite_secundario": 500,
        "categoria": "Periódico mensal",
    },
    "evtFechMensal": {
        "codigo": "D-1199",
        "nome": "Fechamento Mensal",
        "versao_xsd": "0.0.2",
        "grupo_contagem": "detBCNeg",
        "limite_grupo": 99,
        "categoria": "Fechamento mensal",
        "xsd_pacote_completo": True,
    },
}


FONTE_TECNICA = (
    "DeRE 1.2.0 • atualização XSD Produção Restrita publicada em 21/09/2026 "
    "e vigente desde 22/09/2026"
)
URL_OFICIAL_DERE = "https://www.gov.br/sped/pt-br/assuntos/comunicados/dere"
URL_ATUALIZACAO_XSD = "https://www.cgibs.gov.br/dere-atualizacao-dos-esquemas-xsd-dos-eventos-d-1011-e-d-1101-na-producao-restrita"
URL_DERE_120 = "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/setembro/dere-receita-federal-publica-versao-1-2-0-da-documentacao-tecnica-da-dere/"


# O pacote oficial de Produção Restrita publicado em 21/09/2026 referencia
# xmldsig-core-schema.xsd, mas o ZIP disponibilizado não traz esse arquivo.
# Para permitir a validação estrutural dos eventos DeRE sem alterar o pacote
# oficial, o FiscalPro fornece um resolvedor local permissivo somente para o
# elemento ds:Signature. Isso NÃO valida criptograficamente a assinatura.
_XMLDSIG_FALLBACK_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="http://www.w3.org/2000/09/xmldsig#"
           xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
           elementFormDefault="qualified"
           attributeFormDefault="unqualified">
  <xs:element name="Signature">
    <xs:complexType mixed="true">
      <xs:sequence>
        <xs:any minOccurs="0" maxOccurs="unbounded" processContents="lax"/>
      </xs:sequence>
      <xs:anyAttribute processContents="lax"/>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


@dataclass(slots=True)
class XSDDisponibilidade:
    disponivel: bool
    mensagem: str


@dataclass(slots=True)
class ResultadoDeRE:
    arquivo: str
    evento: str = ""
    codigo_evento: str = ""
    nome_evento: str = ""
    namespace: str = ""
    versao_namespace: str = ""
    versao_esperada: str = ""
    info_conta: int = 0
    limite_info_conta: int | None = None
    grupo_contagem: str = ""
    quantidade_grupo: int = 0
    limite_grupo: int | None = None
    categoria_evento: str = ""
    cnpj_raiz: str = ""
    periodo: str = ""
    status_xml: str = "PENDENTE"
    status_versao: str = "N/A"
    status_capacidade: str = "N/A"
    status_xsd: str = "NÃO EXECUTADO"
    detalhes: str = ""

    def como_dict(self) -> dict:
        return asdict(self)

    @property
    def status_geral(self) -> str:
        if self.status_xml == "ERRO" or self.status_capacidade == "ERRO" or self.status_xsd == "ERRO":
            return "ERRO"
        if self.status_versao == "REVISAR" or self.status_xsd == "REVISAR":
            return "REVISAR"
        if self.status_xml == "OK" and self.status_capacidade in {"OK", "N/A"}:
            return "OK"
        return "REVISAR"


class ServicoDeRE:
    """Analisa XMLs DeRE e, quando possível, valida contra XSD oficial."""

    @staticmethod
    def disponibilidade_xsd() -> XSDDisponibilidade:
        try:
            import lxml.etree  # noqa: F401
        except Exception:
            return XSDDisponibilidade(
                False,
                "Validação XSD completa indisponível neste ambiente. A análise estrutural continua funcionando.",
            )
        return XSDDisponibilidade(True, "Motor XSD disponível.")

    @staticmethod
    def _local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    @staticmethod
    def _namespace(tag: str) -> str:
        if tag.startswith("{") and "}" in tag:
            return tag[1:].split("}", 1)[0]
        return ""

    @staticmethod
    def _versao_namespace(namespace: str) -> str:
        if not namespace:
            return ""
        match = re.search(r"/v(\d+(?:[_\.]\d+){1,3})/?$", namespace, flags=re.I)
        if not match:
            return ""
        return match.group(1).replace("_", ".")

    @classmethod
    def _achar_evento(cls, raiz: ET.Element) -> ET.Element | None:
        for elemento in raiz.iter():
            if cls._local(elemento.tag) in EVENTOS_DERE:
                return elemento
        return None

    @classmethod
    def _primeiro_texto(cls, raiz: ET.Element, nomes: Iterable[str]) -> str:
        procurados = set(nomes)
        for elemento in raiz.iter():
            if cls._local(elemento.tag) in procurados:
                texto = (elemento.text or "").strip()
                if texto:
                    return texto
        return ""

    @classmethod
    def analisar_xml(cls, caminho: str | Path) -> ResultadoDeRE:
        caminho = Path(caminho)
        resultado = ResultadoDeRE(arquivo=str(caminho))
        try:
            arvore = ET.parse(caminho)
            raiz = arvore.getroot()
        except ET.ParseError as exc:
            resultado.status_xml = "ERRO"
            resultado.detalhes = f"XML inválido: {exc}"
            return resultado
        except OSError as exc:
            resultado.status_xml = "ERRO"
            resultado.detalhes = f"Não foi possível abrir o arquivo: {exc}"
            return resultado

        resultado.status_xml = "OK"
        evento = cls._achar_evento(raiz)
        if evento is None:
            resultado.status_versao = "REVISAR"
            resultado.status_capacidade = "N/A"
            resultado.detalhes = (
                "XML bem formado, porém o FiscalPro não reconheceu um dos eventos suportados "
                "nesta versão: D-1001, D-1011, D-1101, D-1106 ou D-1199."
            )
            return resultado

        nome_tag = cls._local(evento.tag)
        meta = EVENTOS_DERE[nome_tag]
        resultado.evento = nome_tag
        resultado.codigo_evento = str(meta["codigo"])
        resultado.nome_evento = str(meta["nome"])
        resultado.namespace = cls._namespace(evento.tag)
        resultado.versao_namespace = cls._versao_namespace(resultado.namespace)
        resultado.versao_esperada = str(meta["versao_xsd"])
        resultado.categoria_evento = str(meta.get("categoria", ""))
        resultado.grupo_contagem = str(meta.get("grupo_contagem") or "")
        limite_grupo = meta.get("limite_grupo")
        resultado.limite_grupo = int(limite_grupo) if limite_grupo is not None else None
        resultado.quantidade_grupo = (
            sum(1 for item in evento.iter() if cls._local(item.tag) == resultado.grupo_contagem)
            if resultado.grupo_contagem
            else 0
        )
        # Compatibilidade com a grade/relatórios das versões 18.2.1/18.2.2.
        if resultado.grupo_contagem == "infoConta":
            resultado.info_conta = resultado.quantidade_grupo
            resultado.limite_info_conta = resultado.limite_grupo
        resultado.cnpj_raiz = cls._primeiro_texto(evento, ("nrInsc",))
        resultado.periodo = cls._primeiro_texto(
            evento, ("perApur", "iniValid", "dtApur", "competencia")
        )

        if resultado.versao_namespace:
            resultado.status_versao = (
                "OK" if resultado.versao_namespace == resultado.versao_esperada else "REVISAR"
            )
        else:
            resultado.status_versao = "REVISAR"

        if resultado.limite_grupo is None:
            resultado.status_capacidade = "N/A"
            resultado.detalhes = (
                f"Evento {resultado.codigo_evento} reconhecido. XSD esperado: "
                f"v{resultado.versao_esperada}."
            )
        elif resultado.quantidade_grupo > resultado.limite_grupo:
            resultado.status_capacidade = "ERRO"
            resultado.detalhes = (
                f"O evento possui {resultado.quantidade_grupo:,} grupos {resultado.grupo_contagem} "
                f"e ultrapassa o limite de {resultado.limite_grupo:,}."
            ).replace(",", ".")
        else:
            resultado.status_capacidade = "OK"
            resultado.detalhes = (
                f"Capacidade {resultado.grupo_contagem}: "
                f"{resultado.quantidade_grupo:,}/{resultado.limite_grupo:,}. "
                f"XSD esperado: v{resultado.versao_esperada}."
            ).replace(",", ".")

        # D-1106 possui ainda limite de 500 detAtivo dentro de cada infoAplic.
        grupo_sec = str(meta.get("limite_secundario_grupo") or "")
        limite_sec = meta.get("limite_secundario")
        if grupo_sec and limite_sec is not None:
            max_encontrado = 0
            for grupo in evento.iter():
                if cls._local(grupo.tag) != resultado.grupo_contagem:
                    continue
                qtd = sum(1 for item in grupo.iter() if cls._local(item.tag) == grupo_sec)
                max_encontrado = max(max_encontrado, qtd)
            if max_encontrado > int(limite_sec):
                resultado.status_capacidade = "ERRO"
                resultado.detalhes += (
                    f" Há grupo {resultado.grupo_contagem} com {max_encontrado:,} {grupo_sec}; "
                    f"o limite por grupo é {int(limite_sec):,}."
                ).replace(",", ".")
            else:
                resultado.detalhes += (
                    f" Limite adicional: até {int(limite_sec):,} {grupo_sec} por "
                    f"{resultado.grupo_contagem}."
                ).replace(",", ".")

        if resultado.status_versao == "REVISAR":
            atual = resultado.versao_namespace or "não identificada"
            resultado.detalhes += (
                f" Namespace indica versão {atual}; revisar antes de transmitir."
            )
        return resultado

    @staticmethod
    def _xsd_target_namespace(caminho: Path) -> str:
        try:
            raiz = ET.parse(caminho).getroot()
            return str(raiz.attrib.get("targetNamespace", "")).strip()
        except Exception:
            return ""

    @classmethod
    def _localizar_xsd(cls, pasta: Path, namespace: str, evento: str) -> Path | None:
        candidatos = sorted(pasta.rglob("*.xsd"))
        if namespace:
            for arquivo in candidatos:
                if cls._xsd_target_namespace(arquivo) == namespace:
                    return arquivo
        evento_cf = evento.casefold()
        for arquivo in candidatos:
            nome = arquivo.name.casefold()
            if evento_cf and evento_cf in nome:
                return arquivo
        return None

    @classmethod
    def validar_xsd(
        cls,
        caminho_xml: str | Path,
        resultado: ResultadoDeRE,
        pacote_xsd: str | Path,
    ) -> ResultadoDeRE:
        disponibilidade = cls.disponibilidade_xsd()
        if not disponibilidade.disponivel:
            resultado.status_xsd = "REVISAR"
            resultado.detalhes = f"{resultado.detalhes} {disponibilidade.mensagem}".strip()
            return resultado

        try:
            from lxml import etree
        except Exception as exc:  # proteção adicional
            resultado.status_xsd = "REVISAR"
            resultado.detalhes = f"{resultado.detalhes} Motor XSD indisponível: {exc}".strip()
            return resultado

        pacote = Path(pacote_xsd)

        def executar(pasta: Path) -> None:
            xsd = cls._localizar_xsd(pasta, resultado.namespace, resultado.evento)
            if xsd is None:
                resultado.status_xsd = "REVISAR"
                complemento = (
                    f" Não encontrei no pacote um XSD com o namespace "
                    f"{resultado.namespace or 'do XML'}."
                )
                if resultado.codigo_evento == "D-1199":
                    complemento += (
                        " O pacote de Produção Restrita Empresas Piloto atualmente usado para "
                        "D-1001/D-1011/D-1101/D-1106 não contém o schema do D-1199; para a "
                        "validação estrutural do fechamento use o pacote XSD v1.2.0 completo."
                    )
                resultado.detalhes = f"{resultado.detalhes}{complemento}".strip()
                return
            try:
                # Alguns pacotes oficiais DeRE referenciam xmldsig-core-schema.xsd
                # sem incluir esse arquivo no ZIP. Nesse caso resolvemos apenas
                # o elemento ds:Signature localmente; a assinatura criptográfica
                # continua fora do escopo deste pré-validador.
                usa_fallback_assinatura = not (xsd.parent / "xmldsig-core-schema.xsd").exists()

                class _AssinaturaResolver(etree.Resolver):
                    def resolve(self, url, public_id, context):
                        if str(url).replace("\\", "/").casefold().endswith("/xmldsig-core-schema.xsd") or str(url).casefold() == "xmldsig-core-schema.xsd":
                            return self.resolve_string(_XMLDSIG_FALLBACK_XSD, context)
                        return None

                parser_xsd = etree.XMLParser(no_network=True, resolve_entities=False)
                if usa_fallback_assinatura:
                    parser_xsd.resolvers.add(_AssinaturaResolver())

                esquema_doc = etree.parse(str(xsd), parser_xsd)
                esquema = etree.XMLSchema(esquema_doc)
                xml_doc = etree.parse(str(caminho_xml))
                esquema.assertValid(xml_doc)
                resultado.status_xsd = "OK"
                complemento = f" XSD validado com {xsd.name}."
                if usa_fallback_assinatura:
                    complemento += (
                        " Estrutura do evento validada; o pacote oficial não inclui "
                        "xmldsig-core-schema.xsd, portanto a assinatura digital não é "
                        "validada criptograficamente por este pré-validador."
                    )
                resultado.detalhes = f"{resultado.detalhes}{complemento}".strip()
            except etree.DocumentInvalid as exc:
                resultado.status_xsd = "ERRO"
                log = str(exc.error_log.last_error or exc).strip()
                resultado.detalhes = f"{resultado.detalhes} Erro XSD: {log}".strip()
            except (etree.XMLSyntaxError, etree.XMLSchemaParseError, OSError) as exc:
                resultado.status_xsd = "ERRO"
                resultado.detalhes = f"{resultado.detalhes} Falha ao validar XSD: {exc}".strip()

        if pacote.is_dir():
            executar(pacote)
            return resultado

        if pacote.suffix.casefold() != ".zip":
            resultado.status_xsd = "REVISAR"
            resultado.detalhes = (
                f"{resultado.detalhes} Informe uma pasta de XSDs ou o ZIP oficial da DeRE."
            ).strip()
            return resultado

        try:
            with TemporaryDirectory(prefix="fiscalpro_dere_xsd_") as temporaria:
                pasta = Path(temporaria)
                with zipfile.ZipFile(pacote) as arquivo_zip:
                    arquivo_zip.extractall(pasta)
                executar(pasta)
        except (OSError, zipfile.BadZipFile) as exc:
            resultado.status_xsd = "ERRO"
            resultado.detalhes = f"{resultado.detalhes} Pacote XSD inválido: {exc}".strip()
        return resultado

    @classmethod
    def analisar_varios(
        cls,
        arquivos: Iterable[str | Path],
        pacote_xsd: str | Path | None = None,
    ) -> list[ResultadoDeRE]:
        saida: list[ResultadoDeRE] = []
        for arquivo in arquivos:
            resultado = cls.analisar_xml(arquivo)
            if pacote_xsd and resultado.status_xml == "OK":
                resultado = cls.validar_xsd(arquivo, resultado, pacote_xsd)
            saida.append(resultado)
        return saida
