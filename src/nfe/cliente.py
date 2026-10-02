"""Web services do Ambiente Nacional da NF-e: Distribuição DF-e e Recepção de Eventos."""

from __future__ import annotations

import base64
import gzip
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from lxml import etree

from src.nfse.certificado import contexto_ssl_a1


URL_DIST_PROD = "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
URL_DIST_HOM = "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
URL_EVENTO_PROD = "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"
URL_EVENTO_HOM = "https://hom1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_DIST = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"
NS_EVENTO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4"
NS_SOAP11 = "http://schemas.xmlsoap.org/soap/envelope/"

UF_CODIGOS = {
    "RO":"11","AC":"12","AM":"13","RR":"14","PA":"15","AP":"16","TO":"17",
    "MA":"21","PI":"22","CE":"23","RN":"24","PB":"25","PE":"26","AL":"27","SE":"28","BA":"29",
    "MG":"31","ES":"32","RJ":"33","SP":"35","PR":"41","SC":"42","RS":"43","MS":"50","MT":"51","GO":"52","DF":"53",
}


class ErroNFe(RuntimeError):
    pass


@dataclass(frozen=True)
class DocumentoDistribuido:
    nsu: int
    schema: str
    xml: str


@dataclass(frozen=True)
class RespostaDistribuicao:
    cstat: str
    motivo: str
    ultimo_nsu: int
    max_nsu: int
    documentos: list[DocumentoDistribuido]
    xml_retorno: str
    ultimo_nsu_informado: bool = False
    max_nsu_informado: bool = False


def _texto_local(raiz: etree._Element, nome: str) -> str:
    vals = raiz.xpath(f"//*[local-name()='{nome}']/text()")
    return str(vals[0]).strip() if vals else ""


def _so_digitos(valor: str) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


class ClienteNFeAmbienteNacional:
    def __init__(self, certificado_path: str, senha: str, ambiente: str = "PRODUCAO", timeout: int = 60):
        self.certificado_path = certificado_path
        self.senha = senha
        self.ambiente = str(ambiente or "PRODUCAO").upper()
        self.timeout = int(timeout)

    @property
    def tp_amb(self) -> str:
        return "2" if self.ambiente.startswith("HOM") else "1"

    @property
    def url_distribuicao(self) -> str:
        return URL_DIST_HOM if self.tp_amb == "2" else URL_DIST_PROD

    @property
    def url_evento(self) -> str:
        return URL_EVENTO_HOM if self.tp_amb == "2" else URL_EVENTO_PROD

    def _post_soap(self, url: str, acao: str, corpo: bytes) -> str:
        req = Request(
            url,
            data=corpo,
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{acao}"',
                "User-Agent": "FiscalPro-NFe/18.2",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with contexto_ssl_a1(self.certificado_path, self.senha) as contexto:
                with urlopen(req, context=contexto, timeout=self.timeout) as resp:
                    return resp.read().decode("utf-8-sig", errors="replace")
        except HTTPError as exc:
            detalhe = ""
            try:
                detalhe = exc.read().decode("utf-8", errors="replace")[:1200]
            except Exception:
                pass
            raise ErroNFe(f"NF-e retornou HTTP {exc.code}: {detalhe or exc.reason}") from exc
        except URLError as exc:
            raise ErroNFe(f"Não foi possível conectar ao Ambiente Nacional da NF-e: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ErroNFe("Tempo esgotado na comunicação com o Ambiente Nacional da NF-e.") from exc

    def _ler_resposta_distribuicao(self, retorno: str) -> RespostaDistribuicao:
        try:
            raiz = etree.fromstring(retorno.encode("utf-8"))
        except etree.XMLSyntaxError as exc:
            raise ErroNFe(f"Resposta XML inválida da Distribuição DF-e: {retorno[:500]}") from exc

        cstat = _texto_local(raiz, "cStat")
        motivo = _texto_local(raiz, "xMotivo")
        ult_texto = _texto_local(raiz, "ultNSU")
        max_texto = _texto_local(raiz, "maxNSU")
        ult = int(_so_digitos(ult_texto) or 0)
        max_nsu = int(_so_digitos(max_texto) or 0)
        documentos: list[DocumentoDistribuido] = []
        for doc in raiz.xpath("//*[local-name()='docZip']"):
            conteudo = (doc.text or "").strip()
            if not conteudo:
                continue
            try:
                bruto = base64.b64decode(re.sub(r"\s+", "", conteudo))
                xml_doc = gzip.decompress(bruto).decode("utf-8-sig", errors="replace")
            except Exception as exc:
                raise ErroNFe(f"Falha ao descompactar documento NSU {doc.get('NSU') or ''}.") from exc
            documentos.append(DocumentoDistribuido(
                nsu=int(_so_digitos(doc.get("NSU") or "") or 0),
                schema=str(doc.get("schema") or ""),
                xml=xml_doc,
            ))
        return RespostaDistribuicao(
            cstat, motivo, ult, max_nsu, documentos, retorno,
            ultimo_nsu_informado=bool(str(ult_texto).strip()),
            max_nsu_informado=bool(str(max_texto).strip()),
        )

    def consultar_distribuicao(self, cnpj: str, uf_autor: str, ultimo_nsu: int) -> RespostaDistribuicao:
        cnpj = _so_digitos(cnpj)
        uf = str(uf_autor or "").upper().strip()
        if len(cnpj) != 14:
            raise ValueError("CNPJ da empresa deve conter 14 dígitos.")
        if uf not in UF_CODIGOS:
            raise ValueError("Selecione a UF da empresa para consultar as NF-e destinadas.")
        nsu = str(max(0, int(ultimo_nsu or 0))).zfill(15)

        envelope = etree.Element(etree.QName(NS_SOAP11, "Envelope"), nsmap={"soap": NS_SOAP11})
        body = etree.SubElement(envelope, etree.QName(NS_SOAP11, "Body"))
        oper = etree.SubElement(body, etree.QName(NS_DIST, "nfeDistDFeInteresse"), nsmap={None: NS_DIST})
        dados_msg = etree.SubElement(oper, etree.QName(NS_DIST, "nfeDadosMsg"))
        dist = etree.SubElement(dados_msg, etree.QName(NS_NFE, "distDFeInt"), nsmap={None: NS_NFE}, versao="1.01")
        etree.SubElement(dist, etree.QName(NS_NFE, "tpAmb")).text = self.tp_amb
        etree.SubElement(dist, etree.QName(NS_NFE, "cUFAutor")).text = UF_CODIGOS[uf]
        etree.SubElement(dist, etree.QName(NS_NFE, "CNPJ")).text = cnpj
        dist_nsu = etree.SubElement(dist, etree.QName(NS_NFE, "distNSU"))
        etree.SubElement(dist_nsu, etree.QName(NS_NFE, "ultNSU")).text = nsu

        xml_envio = etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")
        acao = f"{NS_DIST}/nfeDistDFeInteresse"
        retorno = self._post_soap(self.url_distribuicao, acao, xml_envio)
        return self._ler_resposta_distribuicao(retorno)

    def consultar_por_chave(self, cnpj: str, uf_autor: str, chave: str) -> RespostaDistribuicao:
        """Consulta pontual de um DF-e por chave, sem consumir a sequência distNSU."""
        cnpj = _so_digitos(cnpj)
        chave = _so_digitos(chave)
        uf = str(uf_autor or "").upper().strip()
        if len(cnpj) != 14:
            raise ValueError("CNPJ da empresa deve conter 14 dígitos.")
        if len(chave) != 44:
            raise ValueError("A chave da NF-e deve conter 44 dígitos.")
        if uf not in UF_CODIGOS:
            raise ValueError("Selecione a UF da empresa para consultar a NF-e.")

        envelope = etree.Element(etree.QName(NS_SOAP11, "Envelope"), nsmap={"soap": NS_SOAP11})
        body = etree.SubElement(envelope, etree.QName(NS_SOAP11, "Body"))
        oper = etree.SubElement(body, etree.QName(NS_DIST, "nfeDistDFeInteresse"), nsmap={None: NS_DIST})
        dados_msg = etree.SubElement(oper, etree.QName(NS_DIST, "nfeDadosMsg"))
        dist = etree.SubElement(dados_msg, etree.QName(NS_NFE, "distDFeInt"), nsmap={None: NS_NFE}, versao="1.01")
        etree.SubElement(dist, etree.QName(NS_NFE, "tpAmb")).text = self.tp_amb
        etree.SubElement(dist, etree.QName(NS_NFE, "cUFAutor")).text = UF_CODIGOS[uf]
        etree.SubElement(dist, etree.QName(NS_NFE, "CNPJ")).text = cnpj
        consulta = etree.SubElement(dist, etree.QName(NS_NFE, "consChNFe"))
        etree.SubElement(consulta, etree.QName(NS_NFE, "chNFe")).text = chave

        xml_envio = etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")
        acao = f"{NS_DIST}/nfeDistDFeInteresse"
        retorno = self._post_soap(self.url_distribuicao, acao, xml_envio)
        return self._ler_resposta_distribuicao(retorno)

    def enviar_manifestacao(self, cnpj: str, chave: str, tp_evento: str, justificativa: str = "") -> dict:
        from .assinatura import montar_evento_assinado, DESCRICOES_EVENTO

        cnpj = _so_digitos(cnpj)
        chave = _so_digitos(chave)
        if len(cnpj) != 14:
            raise ValueError("CNPJ da empresa deve conter 14 dígitos.")
        if len(chave) != 44:
            raise ValueError("A chave da NF-e deve conter 44 dígitos.")
        tp_evento = str(tp_evento or "")
        if tp_evento not in DESCRICOES_EVENTO:
            raise ValueError("Tipo de manifestação inválido.")

        env_evento = montar_evento_assinado(
            self.certificado_path, self.senha, cnpj, chave, tp_evento,
            ambiente=self.tp_amb, justificativa=justificativa,
        )
        envelope = etree.Element(etree.QName(NS_SOAP11, "Envelope"), nsmap={"soap": NS_SOAP11})
        body = etree.SubElement(envelope, etree.QName(NS_SOAP11, "Body"))
        oper = etree.SubElement(body, etree.QName(NS_EVENTO, "nfeRecepcaoEventoNF"), nsmap={None: NS_EVENTO})
        dados = etree.SubElement(oper, etree.QName(NS_EVENTO, "nfeDadosMsg"))
        dados.append(etree.fromstring(env_evento))
        xml_envio_soap = etree.tostring(envelope, xml_declaration=True, encoding="UTF-8")
        acao = f"{NS_EVENTO}/nfeRecepcaoEventoNF"
        retorno = self._post_soap(self.url_evento, acao, xml_envio_soap)
        try:
            raiz = etree.fromstring(retorno.encode("utf-8"))
        except etree.XMLSyntaxError as exc:
            raise ErroNFe(f"Resposta XML inválida da manifestação: {retorno[:500]}") from exc

        # O cStat externo costuma ser 128; o que interessa para o evento é o cStat dentro de retEvento/infEvento.
        infs = raiz.xpath("//*[local-name()='retEvento']/*[local-name()='infEvento']")
        inf = infs[0] if infs else raiz
        def tx(nome: str) -> str:
            vals = inf.xpath(f".//*[local-name()='{nome}']/text()")
            return str(vals[0]).strip() if vals else ""
        return {
            "cstat": tx("cStat") or _texto_local(raiz, "cStat"),
            "motivo": tx("xMotivo") or _texto_local(raiz, "xMotivo"),
            "protocolo": tx("nProt"),
            "data_evento": tx("dhRegEvento"),
            "chave": tx("chNFe") or chave,
            "tp_evento": tx("tpEvento") or tp_evento,
            "xml_envio": env_evento.decode("utf-8"),
            "xml_retorno": retorno,
        }
