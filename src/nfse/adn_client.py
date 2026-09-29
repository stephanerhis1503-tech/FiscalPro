"""Cliente HTTPS mTLS para a API de distribuição do ADN/NFS-e Nacional."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .certificado import contexto_ssl_a1


BASE_PRODUCAO = "https://adn.nfse.gov.br/contribuintes"
BASE_HOMOLOGACAO = "https://adn.producaorestrita.nfse.gov.br/contribuintes"


class ErroADN(RuntimeError):
    pass


@dataclass(frozen=True)
class RespostaADN:
    status: str
    documentos: list[dict]
    alertas: list[dict]
    erros: list[dict]
    bruto: dict


class ClienteADN:
    def __init__(
        self,
        certificado_path: str,
        senha: str,
        ambiente: str = "PRODUCAO",
        timeout: int = 45,
    ):
        self.certificado_path = certificado_path
        self.senha = senha
        self.ambiente = ambiente.upper().strip() or "PRODUCAO"
        self.timeout = int(timeout)

    @property
    def base_url(self) -> str:
        return BASE_HOMOLOGACAO if self.ambiente.startswith("HOM") else BASE_PRODUCAO

    @staticmethod
    def _mensagem_erro_http(exc: HTTPError) -> str:
        corpo = ""
        try:
            corpo = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        detalhe = corpo.strip()
        if detalhe:
            try:
                obj = json.loads(detalhe)
                erros = obj.get("Erros") or obj.get("erros") or []
                if erros:
                    descricoes = [str(e.get("Descricao") or e.get("descricao") or e) for e in erros]
                    detalhe = " | ".join(descricoes)
            except Exception:
                detalhe = detalhe[:500]
        return f"ADN retornou HTTP {exc.code}: {detalhe or exc.reason}"

    def consultar_dfe(
        self,
        ultimo_nsu: int,
        *,
        cnpj_consulta: str = "",
        lote: bool = True,
    ) -> RespostaADN:
        nsu = max(1, int(ultimo_nsu or 1))
        parametros = {"lote": "true" if lote else "false"}
        cnpj = "".join(ch for ch in str(cnpj_consulta) if ch.isdigit())
        if cnpj:
            parametros["cnpjConsulta"] = cnpj

        # O endpoint de contribuinte usa o NSU de distribuição. O parâmetro
        # tipoNSU é aceito pelo serviço atual e deixa explícita a intenção.
        parametros["tipoNSU"] = "DISTRIBUICAO"
        url = f"{self.base_url}/DFe/{nsu}?{urlencode(parametros)}"
        req = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "FiscalPro-NFSe/18.1",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with contexto_ssl_a1(self.certificado_path, self.senha) as contexto:
                with urlopen(req, context=contexto, timeout=self.timeout) as resposta:
                    corpo = resposta.read().decode("utf-8-sig", errors="replace")
        except HTTPError as exc:
            if exc.code == 429:
                raise ErroADN(
                    "O ADN limitou temporariamente as consultas (HTTP 429). Aguarde alguns minutos e tente novamente."
                ) from exc
            mensagem = self._mensagem_erro_http(exc)
            # O ADN de produção pode responder HTTP 404 quando a caixa postal
            # do contribuinte não possui DF-e a partir do NSU consultado.
            # Isso não é falha de certificado nem de conexão; é fim da fila.
            if exc.code == 404 and "nenhum documento localizado" in mensagem.lower():
                return RespostaADN(
                    status="NENHUM_DOCUMENTO_LOCALIZADO",
                    documentos=[],
                    alertas=[],
                    erros=[],
                    bruto={"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO"},
                )
            raise ErroADN(mensagem) from exc
        except URLError as exc:
            raise ErroADN(f"Não foi possível conectar ao ADN: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ErroADN("Tempo esgotado ao consultar o ADN.") from exc

        try:
            bruto = json.loads(corpo)
        except json.JSONDecodeError as exc:
            raise ErroADN(f"Resposta inválida do ADN (não é JSON): {corpo[:300]}") from exc

        status = str(bruto.get("StatusProcessamento") or bruto.get("statusProcessamento") or "")
        documentos = bruto.get("LoteDFe") or bruto.get("loteDFe") or []
        alertas = bruto.get("Alertas") or bruto.get("alertas") or []
        erros = bruto.get("Erros") or bruto.get("erros") or []
        if not isinstance(documentos, list):
            documentos = []
        return RespostaADN(status=status, documentos=documentos, alertas=alertas, erros=erros, bruto=bruto)

    def consultar_eventos(self, chave_acesso: str) -> dict:
        chave = "".join(ch for ch in str(chave_acesso) if ch.isalnum())
        if not chave:
            raise ValueError("Chave de acesso não informada.")
        url = f"{self.base_url}/NFSe/{chave}/Eventos"
        req = Request(url, method="GET", headers={"Accept": "application/json", "User-Agent": "FiscalPro-NFSe/18.1"})
        try:
            with contexto_ssl_a1(self.certificado_path, self.senha) as contexto:
                with urlopen(req, context=contexto, timeout=self.timeout) as resposta:
                    return json.loads(resposta.read().decode("utf-8-sig", errors="replace"))
        except HTTPError as exc:
            raise ErroADN(self._mensagem_erro_http(exc)) from exc
        except URLError as exc:
            raise ErroADN(f"Não foi possível conectar ao ADN: {exc.reason}") from exc
