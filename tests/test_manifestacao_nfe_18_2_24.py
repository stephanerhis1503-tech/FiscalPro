from __future__ import annotations

from pathlib import Path

from src.nfe.repositorio import RepositorioManifestacaoNFe
from src.nfe.servico import ServicoManifestacaoNFe


CNPJ = "11809691000195"


class RepoEmpresasFake:
    def __init__(self, certificado_path: str):
        self.empresa = {
            "id": 1,
            "cnpj": CNPJ,
            "nome": "MEGA MOTOS TRILHA",
            "ambiente": "PRODUCAO",
            "certificado_path": certificado_path,
        }

    def obter_empresa(self, empresa_id: int):
        return dict(self.empresa) if int(empresa_id) == 1 else None

    def listar_empresas(self):
        return [dict(self.empresa)]


def test_diagnostico_reconstroi_documento_de_consulta_antiga(tmp_path: Path):
    cert = tmp_path / "certificado.pfx"
    cert.write_bytes(b"teste")
    repo = RepositorioManifestacaoNFe(tmp_path / "manifestacao.db")
    repo.salvar_config(
        CNPJ, "PRODUCAO", uf_autor="MG", ultimo_nsu=62433, max_nsu=62433,
        ultimo_cstat="138", ultimo_motivo="Documento localizado",
    )
    repo.registrar_consulta_dfe(
        CNPJ, "PRODUCAO", "MG",
        nsu_enviado=62432, cstat="138", motivo="Documento localizado",
        ultimo_nsu_retornado=62433, max_nsu_retornado=62433,
        quantidade_documentos=1,
    )
    repo.salvar_documento(
        CNPJ, "PRODUCAO", 62433, "procEventoNFe_v1.00.xsd", "<evento/>",
        {
            "tipo": "EVENTO",
            "chave": "31260911111111000191550010000000011000000011",
            "emitente_nome": "",
            "tem_xml_completo": False,
        },
    )

    servico = ServicoManifestacaoNFe(repo, RepoEmpresasFake(str(cert)))
    diag = servico.diagnostico(1)

    assert "NSU 000000000062433" in diag["detalhes_documentos"]
    assert "EVENTO" in diag["detalhes_documentos"]
    assert "procEventoNFe_v1.00.xsd" in diag["detalhes_documentos"]
    assert "Documento(s) da última chamada:" in diag["texto"]


def test_repositorio_grava_detalhes_documentos_no_rastro(tmp_path: Path):
    repo = RepositorioManifestacaoNFe(tmp_path / "manifestacao.db")
    detalhe = (
        "NSU 000000000062433 | NF-e | Resumo | schema resNFe_v1.01.xsd | "
        "chave 31260911111111000191550010000000011000000011 | emitente FORNECEDOR"
    )
    repo.registrar_consulta_dfe(
        CNPJ, "PRODUCAO", "MG",
        nsu_enviado=62432, cstat="138", motivo="Documento localizado",
        ultimo_nsu_retornado=62433, max_nsu_retornado=62433,
        quantidade_documentos=1, detalhes_documentos=detalhe,
    )
    linha = repo.obter_ultima_consulta_dfe(CNPJ, "PRODUCAO")
    assert linha["detalhes_documentos"] == detalhe
