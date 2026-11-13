"""RTC 2: cliente somente leitura da Apuracao Assistida CBS (Receita Federal).

Endpoints oficiais: https://docs.receitafederal.gov.br/apuracao-cbs/
Requer token OAuth2 pre-obtido, mantido somente em memoria na interface.
Sem webhook, sem envio de declaracoes e sem pagamentos.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

from src.services.cbs_apuracao_oficial_service import ServicoCBSOficial, TIPOS, TAMANHO_MAXIMO_JSON

BASE_API = "https://api.receitafederal.gov.br/apuracao-cbs/v2"
ESTADOS = {"PENDENTE", "EM_PROCESSAMENTO", "CONCLUIDA", "ERRO", "EXPIRADA"}


class ErroConsultaCBS(RuntimeError):
    pass


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ErroConsultaCBS("Redirecionamento nao autorizado pela API oficial.")


class ClienteCBSReceita:
    def __init__(self, token: str, servico: ServicoCBSOficial | None = None):
        self.token = str(token or "").strip()
        if not self.token or len(self.token) > 16000 or "\n" in self.token or "\r" in self.token:
            raise ValueError("Informe um token OAuth2 valido da Receita (somente memoria).")
        self.servico = servico or ServicoCBSOficial()
        self._opener = build_opener(
            HTTPSHandler(context=ssl.create_default_context()),
            _SemRedirecionamento(),
        )

    def _json(self, metodo, url, corpo=None):
        if not url.startswith(BASE_API + "/"):
            raise ErroConsultaCBS("URL fora da API oficial de CBS.")
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json",
        }
        data = None
        if corpo is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(corpo).encode("utf-8")
        req = Request(url, data=data, headers=headers, method=metodo)
        try:
            with self._opener.open(req, timeout=35) as resposta:
                if resposta.status not in (200, 201):
                    raise ErroConsultaCBS(f"Resposta da Receita: HTTP {resposta.status}.")
                conteudo = resposta.read(2 * 1024 * 1024 + 1)
                if len(conteudo) > 2 * 1024 * 1024:
                    raise ErroConsultaCBS("Resposta de controle excede limite permitido.")
                obj = json.loads(conteudo)
                if not isinstance(obj, dict):
                    raise ErroConsultaCBS("Resposta de controle invalida.")
                return obj
        except HTTPError as exc:
            # Nunca exponha resposta com URLs assinadas ou credenciais.
            raise ErroConsultaCBS(f"Consulta da CBS nao autorizada/concluida: HTTP {exc.code}.") from None
        except (URLError, OSError) as exc:
            raise ErroConsultaCBS("Nao foi possivel acessar a API da Receita. "
                                  "Verifique conexao, credenciais e acesso ao servico.") from None
        except (json.JSONDecodeError, UnicodeError):
            raise ErroConsultaCBS("Resposta nao e JSON valido.") from None

    @staticmethod
    def _ticket(valor: str) -> str:
        ticket = str(valor or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,250}", ticket):
            raise ErroConsultaCBS("Tiquete de consulta invalido.")
        return ticket

    def solicitar(self, cnpj_completo: str, tipo: str) -> str:
        if tipo not in TIPOS:
            raise ValueError("Selecione Debitos ou Creditos.")
        base = self.servico.cnpj_base(cnpj_completo)
        if self.servico.consultas_hoje(cnpj_completo, tipo) >= 4:
            raise ErroConsultaCBS("Limite local de 4 solicitacoes diarias desta API atingido.")
        if self.servico.existe_pendente(cnpj_completo, tipo):
            raise ErroConsultaCBS("Ja existe uma solicitacao pendente ou concluida ainda "
                                  "nao importada. Consulte o tiquete antes de solicitar outra.")
        resposta = self._json(
            "POST", f"{BASE_API}/{tipo}/{base}", {"urlRetorno": ""},
        )
        ticket = self._ticket(resposta.get("tiqueteSolicitacao"))
        self.servico.registrar_tiquete(cnpj_completo, tipo, ticket)
        return ticket

    def situacao(self, ticket: str) -> str:
        ticket = self._ticket(ticket)
        resposta = self._json("GET", f"{BASE_API}/situacao/{quote(ticket)}")
        estado = str(resposta.get("situacao") or "")
        if estado not in ESTADOS:
            raise ErroConsultaCBS("Situacao desconhecida na resposta oficial.")
        self.servico.atualizar_tiquete(ticket, estado)
        return estado

    def baixar_e_importar(self, cnpj_completo: str, tipo: str, ticket: str):
        if tipo not in TIPOS:
            raise ValueError("Tipo invalido.")
        ticket = self._ticket(ticket)
        base = self.servico.cnpj_base(cnpj_completo)
        titulos = self.servico.listar_tiquetes(cnpj_completo, tipo)
        if not any(t["ticket"] == ticket and t["situacao"] == "CONCLUIDA" for t in titulos):
            raise ErroConsultaCBS("Consulte a situacao e confirme CONCLUIDA antes do download.")
        dados = self._json("GET", f"{BASE_API}/download/{quote(ticket)}")
        url = dados.get("urlAssinada")
        if not isinstance(url, str) or len(url) > 4096:
            raise ErroConsultaCBS("URL assinada ausente ou invalida.")
        endereco = urlparse(url)
        if endereco.scheme != "https" or not endereco.hostname or endereco.username or endereco.password or endereco.fragment:
            raise ErroConsultaCBS("URL de download nao utiliza HTTPS seguro.")
        if endereco.hostname in {"localhost", "127.0.0.1", "::1"} or endereco.hostname.endswith((".local", ".internal")):
            raise ErroConsultaCBS("URL de download aponta para endereco nao permitido.")
        expira = dados.get("urlAssinadaExpiraEm")
        if expira:
            try:
                validade = datetime.fromisoformat(str(expira).replace("Z", "+00:00"))
                if validade.tzinfo is None or validade <= datetime.now(timezone.utc):
                    raise ErroConsultaCBS("Link do retorno expirado ou sem fuso.")
            except ValueError:
                raise ErroConsultaCBS("Data de validade do link invalida.") from None
        # URL assinada e secreta; nunca a persiste, imprime ou envia no header
        # Authorization. Nao segue redirecionamentos para outros enderecos.
        req = Request(url, method="GET")
        try:
            with self._opener.open(req, timeout=60) as retorno:
                if retorno.status != 200:
                    raise ErroConsultaCBS("Download indisponivel na Receita.")
                payload = retorno.read(TAMANHO_MAXIMO_JSON + 1)
        except (HTTPError, URLError, OSError):
            raise ErroConsultaCBS("Falha ao baixar o JSON oficial de CBS.") from None
        if len(payload) > TAMANHO_MAXIMO_JSON:
            raise ErroConsultaCBS("JSON oficial ultrapassa 40 MB.")
        return self.servico.importar(payload, tipo, cnpj_completo, ticket=ticket)
