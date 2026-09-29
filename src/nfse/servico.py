"""Orquestração de cadastro, sincronização, consulta e exportação de NFS-e."""

from __future__ import annotations

import time
from pathlib import Path

from .adn_client import ClienteADN, ErroADN
from .certificado import ler_info_certificado
from .exportador import exportar_excel, exportar_xmls
from .parser import analisar_nfse, extrair_xml_item
from .repositorio import RepositorioNFSe


class ServicoNFSeNacional:
    def __init__(self, repositorio: RepositorioNFSe | None = None):
        self.repo = repositorio or RepositorioNFSe()

    def listar_empresas(self):
        return self.repo.listar_empresas()

    def salvar_empresa(self, **kwargs):
        return self.repo.salvar_empresa(**kwargs)

    def excluir_empresa(self, empresa_id: int):
        self.repo.excluir_empresa(empresa_id)

    def validar_certificado(self, caminho: str, senha: str):
        return ler_info_certificado(caminho, senha)

    def testar_conexao(self, empresa_id: int, senha: str) -> dict:
        empresa = self.repo.obter_empresa(empresa_id)
        if not empresa:
            raise ValueError("Empresa não encontrada.")
        cliente = ClienteADN(empresa["certificado_path"], senha, empresa["ambiente"])
        resposta = cliente.consultar_dfe(empresa["ultimo_nsu"], cnpj_consulta=empresa["cnpj"], lote=False)
        return {
            "status": resposta.status,
            "quantidade": len(resposta.documentos),
            "erros": resposta.erros,
            "alertas": resposta.alertas,
        }

    def sincronizar(self, empresa_id: int, senha: str, max_lotes: int = 100, pausa: float = 1.2, progresso=None) -> dict:
        empresa = self.repo.obter_empresa(empresa_id)
        if not empresa:
            raise ValueError("Empresa não encontrada.")
        if not Path(empresa["certificado_path"]).is_file():
            raise FileNotFoundError("Selecione novamente o certificado A1 desta empresa.")

        cliente = ClienteADN(empresa["certificado_path"], senha, empresa["ambiente"])
        nsu_atual = max(1, int(empresa.get("ultimo_nsu") or 1))
        salvos = 0
        processados = 0
        lotes = 0
        ultimo_status = ""

        while lotes < max_lotes:
            lotes += 1
            if progresso:
                progresso(f"Consultando ADN a partir do NSU {nsu_atual}…")
            resposta = cliente.consultar_dfe(nsu_atual, cnpj_consulta=empresa["cnpj"], lote=True)
            ultimo_status = resposta.status

            if resposta.erros and resposta.status.upper() == "REJEICAO":
                descricoes = [str(e.get("Descricao") or e.get("descricao") or e) for e in resposta.erros]
                raise ErroADN(" | ".join(descricoes))

            if not resposta.documentos:
                break

            maior_nsu = nsu_atual
            for item in resposta.documentos:
                nsu = int(item.get("NSU") or item.get("nsu") or 0)
                maior_nsu = max(maior_nsu, nsu)
                xml = extrair_xml_item(item)
                dados = analisar_nfse(xml, empresa["cnpj"]) if xml else {}
                if self.repo.salvar_documento(empresa_id, item, dados, xml):
                    salvos += 1
                processados += 1

            if maior_nsu <= nsu_atual:
                # Evita loop infinito diante de resposta anômala.
                break
            nsu_atual = maior_nsu
            self.repo.atualizar_ultimo_nsu(empresa_id, nsu_atual)
            if progresso:
                progresso(f"{processados} documento(s) processado(s). Último NSU: {nsu_atual}")
            # Pequena pausa para não martelar o endpoint em lotes consecutivos.
            time.sleep(max(0.0, float(pausa)))

        return {
            "processados": processados,
            "salvos": salvos,
            "ultimo_nsu": nsu_atual,
            "lotes": lotes,
            "status": ultimo_status,
        }

    def listar_documentos(self, **kwargs):
        return self.repo.listar_documentos(**kwargs)

    def exportar_excel(self, registros, caminho):
        return exportar_excel(registros, caminho)

    def exportar_xmls(self, registros, pasta):
        return exportar_xmls(registros, pasta)
