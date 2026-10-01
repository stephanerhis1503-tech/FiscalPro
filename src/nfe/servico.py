"""Orquestração da Distribuição DF-e e Manifestação do Destinatário da NF-e."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from src.nfse.repositorio import RepositorioNFSe

from .assinatura import DESCRICOES_EVENTO
from .cliente import ClienteNFeAmbienteNacional, ErroNFe, UF_CODIGOS
from .parser import analisar_documento_distribuido
from .repositorio import RepositorioManifestacaoNFe


INTERVALO_SEFAZ_SEGUNDOS = 60 * 60


def _ler_data_iso(valor: str) -> datetime | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _data_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _data_humana(dt: datetime | None) -> str:
    return dt.strftime("%d/%m/%Y às %H:%M:%S") if dt else ""


class ServicoManifestacaoNFe:
    def __init__(self, repositorio: RepositorioManifestacaoNFe | None = None,
                 repo_empresas: RepositorioNFSe | None = None):
        self.repo = repositorio or RepositorioManifestacaoNFe()
        self.repo_empresas = repo_empresas or RepositorioNFSe()

    def listar_empresas(self):
        return self.repo_empresas.listar_empresas()

    def obter_empresa(self, empresa_id: int):
        return self.repo_empresas.obter_empresa(empresa_id)

    def obter_config(self, cnpj: str, ambiente: str):
        return self.repo.obter_config(cnpj, ambiente)

    def salvar_uf(self, cnpj: str, ambiente: str, uf: str):
        uf = str(uf or "").upper()
        if uf not in UF_CODIGOS:
            raise ValueError("Selecione uma UF válida.")
        self.repo.salvar_config(cnpj, ambiente, uf_autor=uf)

    def status_sincronizacao(self, empresa_id: int) -> dict:
        """Retorna o bloqueio local por CNPJ sem consultar a SEFAZ."""
        empresa = self.obter_empresa(empresa_id)
        if not empresa:
            return {
                "bloqueado": False, "segundos_restantes": 0, "bloqueado_ate": "",
                "ultimo_nsu": 0, "max_nsu": 0, "ultimo_cstat": "", "ultimo_motivo": "",
            }
        ambiente = str(empresa.get("ambiente") or "PRODUCAO").upper()
        config = self.repo.obter_config(empresa.get("cnpj", ""), ambiente)
        agora = datetime.now()
        ate = _ler_data_iso(config.get("bloqueado_ate", ""))
        restante = 0
        if ate and ate > agora:
            restante = max(1, int((ate - agora).total_seconds() + 0.999))
        return {
            **config,
            "bloqueado": bool(restante),
            "segundos_restantes": restante,
            "bloqueado_ate_dt": ate,
            "bloqueado_ate_formatado": _data_humana(ate),
        }

    def _registrar_bloqueio(self, cnpj: str, ambiente: str, uf_autor: str, *,
                            cstat: str, motivo: str, ultimo_nsu: int | None = None,
                            max_nsu: int | None = None) -> datetime:
        agora = datetime.now()
        ate = agora + timedelta(seconds=INTERVALO_SEFAZ_SEGUNDOS)
        self.repo.salvar_config(
            cnpj, ambiente, uf_autor=uf_autor,
            ultimo_nsu=ultimo_nsu, max_nsu=max_nsu,
            bloqueado_ate=_data_iso(ate), ultima_consulta_em=_data_iso(agora),
            ultimo_cstat=str(cstat or ""), ultimo_motivo=str(motivo or ""),
        )
        return ate

    def sincronizar(self, empresa_id: int, senha: str, uf_autor: str, *, max_lotes: int = 50,
                    pausa: float = 1.1, progresso=None) -> dict:
        empresa = self.obter_empresa(empresa_id)
        if not empresa:
            raise ValueError("Empresa não encontrada. Cadastre-a primeiro na área NFS-e.")
        uf_autor = str(uf_autor or "").upper()
        if uf_autor not in UF_CODIGOS:
            raise ValueError("Selecione a UF da empresa.")

        cnpj = empresa["cnpj"]
        ambiente = str(empresa.get("ambiente") or "PRODUCAO").upper()
        status = self.status_sincronizacao(empresa_id)
        if status.get("bloqueado"):
            motivo = str(status.get("ultimo_motivo") or "").strip()
            complemento = f" Motivo anterior: {motivo}" if motivo else ""
            raise ErroNFe(
                "A consulta DF-e deste CNPJ está protegida para evitar novo cStat 656. "
                f"Tente novamente somente após {status.get('bloqueado_ate_formatado')}." + complemento
            )

        cert = Path(empresa.get("certificado_path") or "")
        if not cert.is_file():
            raise FileNotFoundError("O certificado A1 desta empresa não foi encontrado. Atualize-o na área NFS-e.")
        if not senha:
            raise ValueError("Digite a senha do certificado A1.")

        config = self.repo.obter_config(cnpj, ambiente)
        self.repo.salvar_config(cnpj, ambiente, uf_autor=uf_autor, bloqueado_ate="")
        atual = int(config.get("ultimo_nsu") or 0)
        cliente = ClienteNFeAmbienteNacional(str(cert), senha, ambiente)
        processados = salvos = lotes = 0
        ultimo_cstat = ultimo_motivo = ""
        max_nsu = int(config.get("max_nsu") or 0)
        bloqueado_ate = ""

        while lotes < max_lotes:
            lotes += 1
            nsu_enviado = int(atual)
            if progresso:
                progresso(f"Consultando NF-e destinadas a partir do NSU {nsu_enviado:015d}…")
            try:
                resposta = cliente.consultar_distribuicao(cnpj, uf_autor, nsu_enviado)
            except ErroNFe as exc:
                instante_erro = datetime.now()
                self.repo.registrar_consulta_dfe(
                    cnpj, ambiente, uf_autor,
                    nsu_enviado=nsu_enviado, cstat="CONEXAO", motivo=str(exc),
                    observacao="A chamada não produziu retorno DF-e parseável.",
                    consultado_em=_data_iso(instante_erro),
                )
                self.repo.salvar_config(
                    cnpj, ambiente, uf_autor=uf_autor,
                    bloqueado_ate="", ultima_consulta_em=_data_iso(instante_erro),
                    ultimo_cstat="CONEXAO", ultimo_motivo=str(exc),
                )
                raise
            except Exception as exc:
                instante_erro = datetime.now()
                motivo_local = f"{exc.__class__.__name__}: {exc}"
                self.repo.registrar_consulta_dfe(
                    cnpj, ambiente, uf_autor,
                    nsu_enviado=nsu_enviado, cstat="ERRO_LOCAL", motivo=motivo_local,
                    observacao="Falha local antes de concluir a leitura do retorno DF-e.",
                    consultado_em=_data_iso(instante_erro),
                )
                self.repo.salvar_config(
                    cnpj, ambiente, uf_autor=uf_autor,
                    bloqueado_ate="", ultima_consulta_em=_data_iso(instante_erro),
                    ultimo_cstat="ERRO_LOCAL",
                    ultimo_motivo=motivo_local,
                )
                raise

            instante_resposta = datetime.now()
            ultimo_cstat, ultimo_motivo = resposta.cstat, resposta.motivo
            ult_retornado = int(resposta.ultimo_nsu or 0) if resposta.ultimo_nsu_informado else None
            max_retornado = int(resposta.max_nsu or 0) if resposta.max_nsu_informado else None
            self.repo.registrar_consulta_dfe(
                cnpj, ambiente, uf_autor,
                nsu_enviado=nsu_enviado,
                cstat=resposta.cstat,
                motivo=resposta.motivo,
                ultimo_nsu_retornado=ult_retornado,
                max_nsu_retornado=max_retornado,
                quantidade_documentos=len(resposta.documentos),
                observacao=(
                    "cStat 656: comparar NSU enviado com ultNSU retornado."
                    if resposta.cstat == "656" else ""
                ),
                consultado_em=_data_iso(instante_resposta),
            )

            # maxNSU só é atualizado por resposta normal da Distribuição. Uma rejeição
            # 656 pode omitir maxNSU ou devolvê-lo zerado; nunca apagamos o último
            # maxNSU válido por causa disso.
            if resposta.cstat in {"137", "138"} and resposta.max_nsu_informado:
                max_recebido = int(resposta.max_nsu or 0)
                if max_recebido > 0:
                    max_nsu = max(max_nsu, max_recebido)

            if resposta.cstat == "656":
                # A NT 2014.002 prevê que o 656 de distNSU devolva o ultNSU da última
                # consulta. Guardamos esse ponto para a próxima tentativa após 1 hora.
                nsu_sefaz = int(resposta.ultimo_nsu or 0) if resposta.ultimo_nsu_informado else atual
                max_retornado_656 = int(resposta.max_nsu or 0) if resposta.max_nsu_informado else 0
                max_sefaz = max(max_nsu, max_retornado_656) if max_retornado_656 > 0 else max_nsu
                ate = self._registrar_bloqueio(
                    cnpj, ambiente, uf_autor, cstat=resposta.cstat, motivo=resposta.motivo,
                    ultimo_nsu=nsu_sefaz, max_nsu=max_sefaz,
                )
                ajuste = ""
                if resposta.ultimo_nsu_informado:
                    ajuste = f" O FiscalPro guardou o ultNSU informado pela SEFAZ: {nsu_sefaz:015d}."
                raise ErroNFe(
                    "Consumo indevido (cStat 656). "
                    f"Este CNPJ foi bloqueado no FiscalPro até {_data_humana(ate)} para não reiniciar a contagem da SEFAZ."
                    + ajuste
                )

            if resposta.cstat not in {"137", "138"}:
                self.repo.salvar_config(
                    cnpj, ambiente, uf_autor=uf_autor,
                    ultima_consulta_em=_data_iso(instante_resposta),
                    ultimo_cstat=resposta.cstat, ultimo_motivo=resposta.motivo,
                )
                raise ErroNFe(f"Distribuição DF-e retornou {resposta.cstat}: {resposta.motivo}")

            for doc in resposta.documentos:
                dados = analisar_documento_distribuido(doc.xml, doc.schema)
                if dados.get("tipo") == "EVENTO":
                    self.repo.registrar_evento_distribuido(cnpj, ambiente, dados, doc.xml)
                if self.repo.salvar_documento(cnpj, ambiente, doc.nsu, doc.schema, doc.xml, dados):
                    salvos += 1
                processados += 1

            maior_doc_nsu = max((int(d.nsu or 0) for d in resposta.documentos), default=0)
            nsu_resposta = int(resposta.ultimo_nsu or 0) if resposta.ultimo_nsu_informado else 0
            novo_nsu = max(atual, nsu_resposta, maior_doc_nsu)
            atual = novo_nsu

            chegou_ao_fim = (
                resposta.cstat == "137"
                or (resposta.max_nsu_informado and atual >= max_nsu)
                or not resposta.documentos
            )
            if chegou_ao_fim:
                ate = instante_resposta + timedelta(seconds=INTERVALO_SEFAZ_SEGUNDOS)
                bloqueado_ate = _data_iso(ate)
            else:
                bloqueado_ate = ""

            self.repo.salvar_config(
                cnpj, ambiente, uf_autor=uf_autor, ultimo_nsu=atual, max_nsu=max_nsu,
                bloqueado_ate=bloqueado_ate, ultima_consulta_em=_data_iso(instante_resposta),
                ultimo_cstat=resposta.cstat, ultimo_motivo=resposta.motivo,
            )
            if progresso:
                progresso(f"{processados} documento(s) processado(s) • NSU {atual:015d} de {max_nsu:015d}")

            if chegou_ao_fim:
                break
            time.sleep(max(0.0, float(pausa)))

        return {
            "processados": processados,
            "salvos": salvos,
            "ultimo_nsu": atual,
            "max_nsu": max_nsu,
            "lotes": lotes,
            "cstat": ultimo_cstat,
            "motivo": ultimo_motivo,
            "bloqueado_ate": bloqueado_ate,
            "bloqueado_ate_formatado": _data_humana(_ler_data_iso(bloqueado_ate)),
        }

    def diagnostico(self, empresa_id: int) -> dict:
        """Monta um diagnóstico local sem consumir uma nova consulta DF-e."""
        empresa = self.obter_empresa(empresa_id)
        if not empresa:
            raise ValueError("Empresa não encontrada.")

        ambiente = str(empresa.get("ambiente") or "PRODUCAO").upper()
        cnpj = str(empresa.get("cnpj") or "")
        config = self.status_sincronizacao(empresa_id)
        cert = Path(empresa.get("certificado_path") or "")
        cert_ok = cert.is_file()
        ultima = _ler_data_iso(config.get("ultima_consulta_em", ""))
        ultimo_nsu = int(config.get("ultimo_nsu") or 0)
        max_nsu = int(config.get("max_nsu") or 0)
        cstat = str(config.get("ultimo_cstat") or "").strip()
        motivo = str(config.get("ultimo_motivo") or "").strip()
        faltantes = max(0, max_nsu - ultimo_nsu) if max_nsu else 0
        notas_locais = len(self.repo.listar_notas(cnpj, ambiente))
        ultima_chamada = self.repo.obter_ultima_consulta_dfe(cnpj, ambiente)
        historico_chamadas = self.repo.listar_consultas_dfe(cnpj, ambiente, 8)

        nsu_enviado = ultima_chamada.get("nsu_enviado")
        nsu_retornado = ultima_chamada.get("ultimo_nsu_retornado")
        max_retornado = ultima_chamada.get("max_nsu_retornado")
        qtd_retornada = int(ultima_chamada.get("quantidade_documentos") or 0)

        divergencia_nsu = (
            cstat == "656"
            and nsu_enviado is not None
            and nsu_retornado is not None
            and int(nsu_enviado) != int(nsu_retornado)
        )

        if not cert_ok:
            situacao = "CERTIFICADO A1 NÃO ENCONTRADO"
            orientacao = (
                "Atualize o certificado A1 na aba NFS-e Nacional antes de tentar sincronizar."
            )
        elif config.get("bloqueado"):
            situacao = "CONSULTA PROTEGIDA"
            orientacao = (
                "Aguarde o horário de liberação indicado abaixo. O FiscalPro está impedindo "
                "uma nova consulta para evitar cStat 656 (Consumo Indevido)."
            )
        elif cstat == "CONEXAO":
            situacao = "FALHA DE CONEXÃO / SERVIÇO"
            orientacao = (
                "A última tentativa não conseguiu completar a comunicação com o Ambiente Nacional. "
                "Isso pode ocorrer por indisponibilidade, timeout, rede, TLS ou resposta HTTP do serviço."
            )
        elif cstat == "ERRO_LOCAL":
            situacao = "ERRO LOCAL"
            orientacao = (
                "A comunicação foi interrompida por um erro local do FiscalPro/Windows. "
                "Use o detalhe abaixo para identificar a causa."
            )
        elif cstat == "656":
            situacao = "CONSUMO INDEVIDO"
            if divergencia_nsu:
                situacao = "CONSUMO INDEVIDO • SEQUÊNCIA DE NSU DIVERGENTE"
                orientacao = (
                    f"O FiscalPro enviou o NSU {int(nsu_enviado):015d}, mas a SEFAZ informou "
                    f"ultNSU {int(nsu_retornado):015d}. Isso é um indício forte de que a sequência "
                    "esperada pela SEFAZ avançou fora desta chamada do FiscalPro, por consulta concorrente "
                    "ou por outro processo/instância usando o mesmo CNPJ. Aguarde a liberação antes de testar novamente."
                )
            else:
                orientacao = (
                    "Não faça novas tentativas até a liberação. O rastro abaixo mostra exatamente o NSU "
                    "enviado pelo FiscalPro e o retorno recebido. Se outro sistema também consulta DF-e "
                    "desse CNPJ, ele precisa respeitar a mesma sequência de NSU."
                )
        elif cstat == "137":
            situacao = "SEM NOVOS DOCUMENTOS NA ÚLTIMA CONSULTA"
            orientacao = (
                "A SEFAZ informou que não havia novos documentos naquele momento. "
                "Se a proteção de 1 hora já terminou, uma nova sincronização pode ser feita."
            )
        elif cstat == "138":
            situacao = "DOCUMENTOS LOCALIZADOS"
            if max_nsu and ultimo_nsu < max_nsu:
                orientacao = (
                    f"Ainda existem aproximadamente {faltantes} NSU(s) entre o último NSU salvo "
                    "e o máximo informado. Sincronize novamente quando o botão estiver liberado."
                )
            else:
                orientacao = "A última consulta retornou documentos e alcançou o ponto informado pela SEFAZ."
        elif cstat:
            situacao = f"RETORNO cStat {cstat}"
            orientacao = "Confira o motivo retornado pela SEFAZ antes de repetir a consulta."
        else:
            situacao = "SEM CONSULTA REGISTRADA"
            orientacao = "Ainda não há retorno de sincronização gravado para este CNPJ/ambiente."

        proxima = str(config.get("bloqueado_ate_formatado") or "").strip()
        linhas = [
            "FISCALPRO • DIAGNÓSTICO DA MANIFESTAÇÃO / DISTRIBUIÇÃO DF-e",
            "",
            f"Empresa: {empresa.get('nome') or '—'}",
            f"CNPJ: {cnpj or '—'}",
            f"Ambiente: {ambiente}",
            f"UF autora: {config.get('uf_autor') or '—'}",
            f"Certificado A1: {'OK' if cert_ok else 'NÃO ENCONTRADO'}",
            f"Arquivo do certificado: {cert.name if cert.name else '—'}",
            "",
            f"Situação: {situacao}",
            f"Última tentativa: {_data_humana(ultima) or '—'}",
            f"Último cStat: {cstat or '—'}",
            f"Motivo/erro: {motivo or '—'}",
            f"Último NSU salvo: {ultimo_nsu:015d}",
            f"Último maxNSU válido preservado: {max_nsu:015d}",
            f"NSU enviado na última chamada do FiscalPro: {int(nsu_enviado):015d}" if nsu_enviado is not None else "NSU enviado na última chamada do FiscalPro: —",
            f"ultNSU retornado pela SEFAZ: {int(nsu_retornado):015d}" if nsu_retornado is not None else "ultNSU retornado pela SEFAZ: —",
            f"maxNSU retornado nesta chamada: {int(max_retornado):015d}" if max_retornado is not None else "maxNSU retornado nesta chamada: não informado",
            f"Documentos retornados nesta chamada: {qtd_retornada}",
            f"Indício de sequência concorrente: {'SIM' if divergencia_nsu else 'NÃO CONCLUÍDO'}",
            f"NF-e armazenadas localmente: {notas_locais}",
            f"Consulta protegida agora: {'SIM' if config.get('bloqueado') else 'NÃO'}",
            f"Próxima consulta permitida: {proxima or '—'}",
            "",
            "Orientação:",
            orientacao,
            "",
            "Rastro das últimas chamadas feitas pelo FiscalPro:",
        ]
        if historico_chamadas:
            for item in historico_chamadas:
                enviado = int(item.get("nsu_enviado") or 0)
                ret = item.get("ultimo_nsu_retornado")
                mx = item.get("max_nsu_retornado")
                docs = int(item.get("quantidade_documentos") or 0)
                ret_txt = f"{int(ret):015d}" if ret is not None else "—"
                max_txt = f"{int(mx):015d}" if mx is not None else "—"
                linhas.append(
                    f"- {item.get('consultado_em') or '—'} | enviado {enviado:015d} | "
                    f"cStat {item.get('cstat') or '—'} | ultNSU {ret_txt} | maxNSU {max_txt} | docs {docs}"
                )
        else:
            linhas.append("- Ainda não há chamadas registradas nesta versão.")
        linhas.extend([
            "",
            "Este diagnóstico é local e NÃO faz uma nova consulta à SEFAZ.",
        ])
        return {
            "situacao": situacao,
            "orientacao": orientacao,
            "cstat": cstat,
            "motivo": motivo,
            "ultimo_nsu": ultimo_nsu,
            "max_nsu": max_nsu,
            "nsu_enviado": nsu_enviado,
            "nsu_retornado": nsu_retornado,
            "max_nsu_retornado": max_retornado,
            "divergencia_nsu": bool(divergencia_nsu),
            "historico_chamadas": historico_chamadas,
            "bloqueado": bool(config.get("bloqueado")),
            "proxima_consulta": proxima,
            "certificado_ok": cert_ok,
            "texto": "\n".join(linhas),
        }

    def listar_notas(self, empresa_id: int, busca: str = "", manifestacao: str = "TODAS"):
        empresa = self.obter_empresa(empresa_id)
        if not empresa:
            return []
        return self.repo.listar_notas(
            empresa["cnpj"], str(empresa.get("ambiente") or "PRODUCAO").upper(), busca, manifestacao
        )

    def manifestar(self, empresa_id: int, senha: str, chave: str, tp_evento: str, justificativa: str = "") -> dict:
        empresa = self.obter_empresa(empresa_id)
        if not empresa:
            raise ValueError("Empresa não encontrada.")
        cert = Path(empresa.get("certificado_path") or "")
        if not cert.is_file():
            raise FileNotFoundError("Certificado A1 não encontrado para esta empresa.")
        if not senha:
            raise ValueError("Digite a senha do certificado A1.")
        ambiente = str(empresa.get("ambiente") or "PRODUCAO").upper()
        cliente = ClienteNFeAmbienteNacional(str(cert), senha, ambiente)
        retorno = cliente.enviar_manifestacao(empresa["cnpj"], chave, tp_evento, justificativa)
        self.repo.salvar_manifestacao(
            empresa["cnpj"], ambiente, chave, tp_evento, DESCRICOES_EVENTO[tp_evento], justificativa,
            retorno, retorno.get("xml_envio", ""), retorno.get("xml_retorno", ""),
        )
        return retorno

    def obter_xml_completo(self, empresa_id: int, chave: str) -> str:
        empresa = self.obter_empresa(empresa_id)
        if not empresa:
            return ""
        return self.repo.obter_xml_completo(
            empresa["cnpj"], str(empresa.get("ambiente") or "PRODUCAO").upper(), chave
        )
