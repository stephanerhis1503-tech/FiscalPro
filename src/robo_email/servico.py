"""Orquestra leitura, classificação, anexos e links seguros do Gmail."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .classificador import (
    PALAVRAS_GUIA,
    classificar_arquivo,
    identificar_empresa,
    normalizar_texto,
)
from .config import ConfiguracaoRoboEmail, TOKEN_PATH
from .gmail_auth import criar_servico_gmail
from .gmail_client import GmailClient, MensagemGmail
from .leitor_documentos import LeitorInteligenteDocumentos
from .links_seguros import (
    BaixadorLinksSeguro,
    LinkEncontrado,
    extrair_links,
)
from .organizador import OrganizadorDocumentos, PlanoOrganizacao
from .repositorio import RoboEmailRepositorio

LogCallback = Callable[[str], None]


@dataclass(slots=True)
class ResultadoProcessamento:
    mensagens_encontradas: int = 0
    mensagens_processadas: int = 0
    mensagens_ja_processadas: int = 0
    empresas_nao_identificadas: int = 0
    arquivos_baixados: int = 0
    arquivos_duplicados: int = 0
    links_encontrados: int = 0
    links_baixados: int = 0
    links_pendentes: int = 0
    links_bloqueados: int = 0
    erros: int = 0


@dataclass(slots=True)
class ResultadoArquivamento:
    status: str
    plano: PlanoOrganizacao
    caminho: Path | None = None
    caminho_duplicado: str = ""
    empresa_duplicada: str = ""


class RoboEmailService:
    def __init__(
        self,
        configuracao: ConfiguracaoRoboEmail,
        repositorio: RoboEmailRepositorio | None = None,
        cliente: GmailClient | None = None,
        log: LogCallback | None = None,
        baixador_links: BaixadorLinksSeguro | None = None,
    ):
        self.configuracao = configuracao
        self.repositorio = repositorio or RoboEmailRepositorio()
        self.cliente = cliente
        self.log = log or (lambda _texto: None)
        self.baixador_links = baixador_links or BaixadorLinksSeguro(
            configuracao.dominios_confiaveis,
            configuracao.tamanho_maximo_link_mb,
        )
        self.organizador = OrganizadorDocumentos(configuracao.destino)
        self.leitor_documentos = LeitorInteligenteDocumentos(
            configuracao.cnpjs_empresas
        )

    def conectar(self) -> dict:
        erros = self.configuracao.validar()
        if erros:
            raise ValueError("\n".join(erros))
        servico = criar_servico_gmail(self.configuracao.credenciais, TOKEN_PATH)
        self.cliente = GmailClient(servico)
        return self.cliente.perfil()

    def processar(self) -> ResultadoProcessamento:
        erros = self.configuracao.validar()
        if erros:
            raise ValueError("\n".join(erros))
        if self.cliente is None:
            self.conectar()
        assert self.cliente is not None

        self.configuracao.destino.mkdir(parents=True, exist_ok=True)
        consulta = self._montar_consulta()
        self.log(f"Consulta Gmail: {consulta}")
        ids = self.cliente.listar_ids(consulta, int(self.configuracao.limite_mensagens))

        resultado = ResultadoProcessamento(mensagens_encontradas=len(ids))
        self.log(f"Mensagens encontradas: {len(ids)}")

        for indice, referencia in enumerate(ids, start=1):
            mensagem_id = referencia.get("id", "")
            if not mensagem_id:
                continue

            if self.repositorio.mensagem_concluida(mensagem_id):
                resultado.mensagens_ja_processadas += 1
                self.log(f"[{indice}/{len(ids)}] Mensagem já processada.")
                continue

            try:
                mensagem = self.cliente.obter_mensagem(mensagem_id)
                self._processar_mensagem(mensagem, resultado)
            except Exception as erro:
                resultado.erros += 1
                self.log(f"ERRO ao processar mensagem: {erro}")
                self.repositorio.registrar_mensagem(
                    mensagem_id=mensagem_id,
                    thread_id=referencia.get("threadId", ""),
                    empresa=None,
                    remetente="",
                    assunto="",
                    data_email=datetime.now(),
                    status="ERRO",
                    detalhe=str(erro),
                    links_verificados=False,
                )

        return resultado

    def processar_links_autorizados(self, limite: int = 500) -> ResultadoProcessamento:
        """Tenta baixar links pendentes após a usuária autorizar seus domínios."""
        erros = self.configuracao.validar()
        if erros:
            raise ValueError("\n".join(erros))

        resultado = ResultadoProcessamento()
        pendentes = self.repositorio.listar_links(
            statuses=("PENDENTE_DOMINIO", "AUTORIZADO_AGUARDANDO", "PENDENTE_ACESSO", "ERRO"),
            limite=limite,
        )
        self.log(f"Links pendentes analisados: {len(pendentes)}")

        for linha in pendentes:
            if not self.baixador_links.dominio_confiavel(linha["url"]):
                continue
            resultado.links_encontrados += 1
            self._baixar_link_registrado(linha, resultado)
        return resultado

    def baixar_link_por_id(self, link_id: int) -> ResultadoProcessamento:
        linha = self.repositorio.obter_link(link_id)
        if not linha:
            raise ValueError("Link não encontrado no histórico do robô.")
        if not self.baixador_links.dominio_confiavel(linha["url"]):
            raise ValueError(
                f"O domínio {linha['dominio']} ainda não está na lista de domínios autorizados."
            )
        resultado = ResultadoProcessamento(links_encontrados=1)
        self._baixar_link_registrado(linha, resultado)
        return resultado

    def importar_arquivo_link(self, link_id: int, arquivo_origem: str | Path) -> ResultadoProcessamento:
        """Arquiva um documento baixado manualmente de portal com login, como o Nibo."""
        linha = self.repositorio.obter_link(link_id)
        if not linha:
            raise ValueError("Link não encontrado no histórico do robô.")

        origem = Path(arquivo_origem).expanduser()
        if not origem.is_file():
            raise ValueError("O arquivo selecionado não foi encontrado.")
        if origem.suffix.lower() not in {".pdf", ".zip", ".xml"}:
            raise ValueError("Selecione um arquivo PDF, ZIP ou XML baixado do portal.")

        dados = origem.read_bytes()
        if not dados:
            raise ValueError("O arquivo selecionado está vazio.")
        if len(dados) > int(self.configuracao.tamanho_maximo_link_mb) * 1024 * 1024:
            raise ValueError("O arquivo ultrapassa o limite configurado por link.")

        resultado = ResultadoProcessamento(links_encontrados=1)
        empresa = linha["empresa"] or None
        data_email = self._data_iso(linha["data_email"])
        categoria = self._categoria_link(
            origem.name,
            "",
            linha["assunto"],
            linha["texto_link"],
        )
        arquivamento = self._arquivar_documento(
            mensagem_id=linha["mensagem_id"],
            empresa=empresa,
            nome_original=origem.name,
            dados=dados,
            data_email=data_email,
            mime_type="",
            assunto=linha["assunto"],
            contexto=linha["texto_link"],
            categoria_preferida=categoria,
            origem_documento="PORTAL_ASSISTIDO",
        )
        if arquivamento.status == "DUPLICADO":
            self.repositorio.atualizar_link(
                link_id,
                status="DUPLICADO",
                detalhe=(
                    "Documento baixado pelo navegador já estava arquivado"
                    + (
                        f" para {arquivamento.empresa_duplicada}."
                        if arquivamento.empresa_duplicada
                        else "."
                    )
                ),
                url_final=linha["url_final"] or linha["url"],
                caminho_salvo=arquivamento.caminho_duplicado,
            )
            resultado.arquivos_duplicados += 1
            self.log(f"Documento já existia: {origem.name}")
            return resultado

        assert arquivamento.caminho is not None
        self.repositorio.atualizar_link(
            link_id,
            status="BAIXADO",
            detalhe=(
                "Documento baixado no portal e organizado automaticamente. "
                f"Competência: {arquivamento.plano.mes:02d}/{arquivamento.plano.ano:04d}."
            ),
            url_final=linha["url_final"] or linha["url"],
            caminho_salvo=str(arquivamento.caminho),
        )
        resultado.arquivos_baixados += 1
        resultado.links_baixados += 1
        self.log(f"Documento do portal arquivado: {arquivamento.caminho}")
        return resultado

    def _processar_mensagem(
        self,
        mensagem: MensagemGmail,
        resultado: ResultadoProcessamento,
    ) -> None:
        assert self.cliente is not None
        empresa = identificar_empresa(
            mensagem.destinatarios,
            mensagem.assunto,
            f"{mensagem.snippet} {mensagem.corpo_texto[:2000]}",
        )
        if not empresa:
            resultado.empresas_nao_identificadas += 1
            self.log(
                f"Empresa não identificada: {mensagem.assunto} — documentos serão separados para revisão."
            )

        empresa_banco = empresa or "Não Identificada"
        links = (
            extrair_links(
                mensagem.corpo_texto,
                mensagem.corpo_html,
                contexto_mensagem=f"{mensagem.assunto} {mensagem.snippet} {mensagem.corpo_texto[:4000]}",
            )
            if self.configuracao.registrar_links
            else []
        )
        self.log(
            f"Processando: {mensagem.assunto} | Empresa: {empresa_banco} | "
            f"Anexos: {len(mensagem.anexos)} | Links úteis: {len(links)}"
        )

        self.repositorio.registrar_mensagem(
            mensagem_id=mensagem.id,
            thread_id=mensagem.thread_id,
            empresa=empresa,
            remetente=mensagem.remetente,
            assunto=mensagem.assunto,
            data_email=mensagem.data,
            status="PROCESSANDO",
            detalhe="Leitura iniciada",
            links_verificados=False,
        )

        salvos = self._processar_anexos(mensagem, empresa, empresa_banco, resultado)
        links_tratados = self._processar_links(
            mensagem,
            empresa,
            empresa_banco,
            links,
            resultado,
        )

        self.repositorio.registrar_mensagem(
            mensagem_id=mensagem.id,
            thread_id=mensagem.thread_id,
            empresa=empresa,
            remetente=mensagem.remetente,
            assunto=mensagem.assunto,
            data_email=mensagem.data,
            status="CONCLUIDO",
            detalhe=f"{salvos} anexo(s); {links_tratados} link(s) analisado(s)",
            links_verificados=True,
        )
        resultado.mensagens_processadas += 1

    def _processar_anexos(
        self,
        mensagem: MensagemGmail,
        empresa: str | None,
        empresa_banco: str,
        resultado: ResultadoProcessamento,
    ) -> int:
        assert self.cliente is not None
        salvos = 0
        for anexo in mensagem.anexos:
            dados = self.cliente.baixar_anexo(mensagem.id, anexo)
            if not dados:
                self.log(f"Anexo vazio ignorado: {anexo.nome}")
                continue

            arquivamento = self._arquivar_documento(
                mensagem_id=mensagem.id,
                empresa=empresa,
                nome_original=anexo.nome,
                dados=dados,
                data_email=mensagem.data,
                mime_type=anexo.mime_type,
                assunto=mensagem.assunto,
                contexto=f"{mensagem.snippet} {mensagem.corpo_texto[:2000]}",
                origem_documento="ANEXO_GMAIL",
            )
            if arquivamento.status == "DUPLICADO":
                resultado.arquivos_duplicados += 1
                detalhe = f"Anexo duplicado: {anexo.nome}"
                if arquivamento.empresa_duplicada:
                    detalhe += f"; já arquivado para {arquivamento.empresa_duplicada}"
                if arquivamento.caminho_duplicado:
                    detalhe += f" em {arquivamento.caminho_duplicado}"
                self.repositorio.registrar_evento(
                    tipo="DUPLICADO",
                    empresa=empresa_banco,
                    data_referencia=mensagem.data,
                    mensagem_id=mensagem.id,
                    detalhe=detalhe,
                )
                self.log(f"Duplicado ignorado: {anexo.nome}")
                continue

            assert arquivamento.caminho is not None
            resultado.arquivos_baixados += 1
            salvos += 1
            self.log(f"Anexo salvo: {arquivamento.caminho}")
        return salvos

    def _processar_links(
        self,
        mensagem: MensagemGmail,
        empresa: str | None,
        empresa_banco: str,
        links: list[LinkEncontrado],
        resultado: ResultadoProcessamento,
    ) -> int:
        for link in links:
            resultado.links_encontrados += 1
            confiavel = self.baixador_links.dominio_confiavel(link.url)
            status = "AUTORIZADO_AGUARDANDO" if confiavel else "PENDENTE_DOMINIO"
            detalhe = (
                "Domínio autorizado; aguardando comando para baixar."
                if confiavel
                else "Domínio ainda não autorizado pela usuária."
            )
            link_id = self.repositorio.registrar_link(
                mensagem_id=mensagem.id,
                empresa=empresa,
                remetente=mensagem.remetente,
                assunto=mensagem.assunto,
                data_email=mensagem.data,
                url=link.url,
                dominio=link.dominio,
                texto_link=link.texto,
                status=status,
                detalhe=detalhe,
            )

            atual = self.repositorio.obter_link(link_id)
            if atual and atual["status"] in {"BAIXADO", "DUPLICADO"}:
                continue

            if not confiavel:
                resultado.links_pendentes += 1
                self.log(f"Link aguardando autorização do domínio: {link.dominio}")
                continue

            if not self.configuracao.baixar_links_automaticamente:
                resultado.links_pendentes += 1
                self.log(f"Link autorizado aguardando confirmação: {link.dominio}")
                continue

            linha = self.repositorio.obter_link(link_id)
            if linha:
                self._baixar_link_registrado(linha, resultado, empresa_banco=empresa_banco)
        return len(links)

    def _baixar_link_registrado(
        self,
        linha,
        resultado: ResultadoProcessamento,
        *,
        empresa_banco: str | None = None,
    ) -> None:
        link_id = int(linha["id"])
        dominio = linha["dominio"]
        self.log(f"Verificando download seguro em: {dominio}")
        retorno = self.baixador_links.baixar(linha["url"])

        if retorno.status != "BAIXADO":
            self.repositorio.atualizar_link(
                link_id,
                status=retorno.status,
                detalhe=retorno.detalhe,
                url_final=retorno.url_final,
            )
            if retorno.status in {"PENDENTE_ACESSO", "PENDENTE_DOMINIO"}:
                resultado.links_pendentes += 1
            elif retorno.status == "BLOQUEADO":
                resultado.links_bloqueados += 1
            else:
                resultado.erros += 1
            self.log(f"Link não baixado ({retorno.status}): {retorno.detalhe}")
            return

        empresa = linha["empresa"] or None
        data_email = self._data_iso(linha["data_email"])
        categoria = self._categoria_link(
            retorno.nome_arquivo,
            retorno.mime_type,
            linha["assunto"],
            linha["texto_link"],
        )
        arquivamento = self._arquivar_documento(
            mensagem_id=linha["mensagem_id"],
            empresa=empresa,
            nome_original=retorno.nome_arquivo,
            dados=retorno.dados,
            data_email=data_email,
            mime_type=retorno.mime_type,
            assunto=linha["assunto"],
            contexto=linha["texto_link"],
            categoria_preferida=categoria,
            origem_documento="LINK_AUTOMATICO",
        )
        if arquivamento.status == "DUPLICADO":
            self.repositorio.atualizar_link(
                link_id,
                status="DUPLICADO",
                detalhe=(
                    "Documento já havia sido salvo anteriormente"
                    + (
                        f" para {arquivamento.empresa_duplicada}."
                        if arquivamento.empresa_duplicada
                        else "."
                    )
                ),
                url_final=retorno.url_final,
                caminho_salvo=arquivamento.caminho_duplicado,
            )
            resultado.arquivos_duplicados += 1
            self.log(f"Documento do link já existia: {retorno.nome_arquivo}")
            return

        assert arquivamento.caminho is not None
        self.repositorio.atualizar_link(
            link_id,
            status="BAIXADO",
            detalhe=(
                f"{retorno.detalhe} Documento organizado automaticamente na "
                f"competência {arquivamento.plano.mes:02d}/{arquivamento.plano.ano:04d}."
            ).strip(),
            url_final=retorno.url_final,
            caminho_salvo=str(arquivamento.caminho),
        )
        resultado.arquivos_baixados += 1
        resultado.links_baixados += 1
        self.log(f"Documento de link salvo: {arquivamento.caminho}")

    def _arquivar_documento(
        self,
        *,
        mensagem_id: str,
        empresa: str | None,
        nome_original: str,
        dados: bytes,
        data_email: datetime,
        mime_type: str = "",
        assunto: str = "",
        contexto: str = "",
        categoria_preferida: str | None = None,
        origem_documento: str = "GMAIL",
    ) -> ResultadoArquivamento:
        """Planeja, verifica duplicidade e somente então grava o documento."""

        categoria_inicial = categoria_preferida or classificar_arquivo(
            nome_original, mime_type
        )
        leitura = self.leitor_documentos.analisar(
            nome_original=nome_original,
            dados=dados,
            categoria=categoria_inicial,
            empresa_informada=empresa,
            data_email=data_email,
            assunto=assunto,
            contexto=contexto,
        )
        empresa_efetiva = empresa or leitura.empresa_identificada
        categoria_efetiva = (
            "Guias" if leitura.tipo_documento == "Guia" else categoria_inicial
        )
        plano = self.organizador.planejar(
            nome_original=nome_original,
            dados=dados,
            empresa=empresa_efetiva,
            data_email=data_email,
            mime_type=mime_type,
            assunto=assunto,
            contexto=contexto,
            categoria_preferida=categoria_efetiva,
            competencia_preferida=leitura.competencia,
            tipo_documento_preferido=leitura.tipo_documento,
            identificador_preferido=leitura.tributo or leitura.numero_documento,
        )
        hash_sha256 = hashlib.sha256(dados).hexdigest()
        duplicado = self.repositorio.localizar_anexo_duplicado(hash_sha256)
        if duplicado:
            return ResultadoArquivamento(
                status="DUPLICADO",
                plano=plano,
                caminho_duplicado=str(duplicado["caminho_salvo"] or ""),
                empresa_duplicada=str(duplicado["empresa"] or ""),
            )

        plano.pasta_destino.mkdir(parents=True, exist_ok=True)
        destino = self._caminho_disponivel(plano.caminho_sugerido)
        destino.write_bytes(dados)

        status = "REVISAR" if plano.precisa_revisao else "ORGANIZADO"
        detalhes = [plano.observacao, f"Leitura: {leitura.resumo}."]
        if empresa is None and leitura.empresa_identificada:
            detalhes.append(
                f"Empresa identificada pelo CNPJ do documento: {leitura.empresa_identificada}."
            )
        if leitura.alertas:
            detalhes.append("Alertas: " + " | ".join(leitura.alertas))
        detalhe_completo = " ".join(item for item in detalhes if item).strip()
        try:
            self.repositorio.registrar_anexo(
                mensagem_id=mensagem_id,
                empresa=plano.empresa_banco,
                nome_original=plano.nome_original,
                hash_sha256=hash_sha256,
                caminho_salvo=str(destino),
                categoria=plano.categoria,
                competencia=plano.competencia,
                nome_padronizado=destino.name,
                origem_documento=origem_documento,
                status_organizacao=status,
                detalhe_organizacao=detalhe_completo,
            )
            self.repositorio.atualizar_conferencia_por_hash(
                hash_sha256=hash_sha256,
                documento_tipo=leitura.tipo_documento,
                documento_numero=leitura.numero_documento,
                cnpj_documento=leitura.cnpj_principal,
                competencia_documento=leitura.competencia,
                valor_documento=leitura.valor,
                vencimento_documento=leitura.vencimento,
                tributo_documento=leitura.tributo,
                status_conferencia=leitura.status,
                alertas_conferencia=" | ".join(leitura.alertas),
                fonte_leitura=leitura.fonte,
                resumo_leitura=leitura.resumo,
                status_organizacao=status,
                detalhe_organizacao=detalhe_completo,
            )
        except Exception:
            try:
                destino.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        self.log(
            f"Organizado: {plano.nome_original} → {destino.name} | "
            f"{plano.empresa_banco} | {plano.competencia} | {plano.categoria}"
        )
        if status == "REVISAR":
            self.repositorio.registrar_evento(
                tipo="REVISAR",
                empresa=plano.empresa_banco,
                data_referencia=data_email,
                mensagem_id=mensagem_id,
                detalhe=f"{detalhe_completo} Caminho: {destino}",
            )
        return ResultadoArquivamento(
            status=status,
            plano=plano,
            caminho=destino,
        )

    def _montar_consulta(self) -> str:
        # Não usamos has:attachment porque as guias podem chegar somente por link.
        # Limitamos à caixa de entrada para não reprocessar mensagens enviadas pelo
        # próprio grupo. O banco local controla os message IDs já concluídos, então
        # mensagens lidas continuam sendo encontradas sem gerar duplicidade.
        partes = ["in:inbox", f"newer_than:{int(self.configuracao.dias_retroativos)}d"]
        if self.configuracao.somente_nao_lidos:
            partes.append("is:unread")
        return " ".join(partes)

    @staticmethod
    def _categoria_link(nome: str, mime: str, assunto: str, texto_link: str) -> str:
        categoria = classificar_arquivo(nome, mime)
        contexto = normalizar_texto(f"{nome} {assunto} {texto_link}")
        if categoria == "PDF" and any(palavra in contexto for palavra in PALAVRAS_GUIA):
            return "Guias"
        return "Links" if categoria == "Outros" else categoria

    @staticmethod
    def _data_iso(valor: str) -> datetime:
        try:
            return datetime.fromisoformat(valor)
        except (TypeError, ValueError):
            return datetime.now()

    @staticmethod
    def _caminho_disponivel(caminho: Path) -> Path:
        if not caminho.exists():
            return caminho
        for numero in range(2, 10000):
            candidato = caminho.with_name(f"{caminho.stem}_{numero}{caminho.suffix}")
            if not candidato.exists():
                return candidato
        raise OSError(f"Não foi possível criar um nome exclusivo para {caminho.name}")
