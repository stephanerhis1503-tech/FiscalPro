"""Consolidação mensal e controle de pendências do Robô FiscalPro."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .classificador import pasta_empresa_segura
from .config import (
    CATEGORIAS_DOCUMENTOS_ESPERADOS,
    EMPRESAS_POR_ALIAS,
    ConfiguracaoRoboEmail,
)
from .leitor_documentos import LeitorInteligenteDocumentos
from .organizador import PASTA_REVISAO
from .repositorio import RoboEmailRepositorio


CATEGORIAS_PAINEL = ("XML", "Guias", "PDF", "ZIP", "Outros", "Links")


@dataclass(slots=True)
class ResumoEmpresaMensal:
    empresa: str
    emails: int = 0
    xml: int = 0
    guias: int = 0
    pdf: int = 0
    zip: int = 0
    outros: int = 0
    links_pendentes: int = 0
    duplicados: int = 0
    erros: int = 0
    conferidos: int = 0
    revisar_documentos: int = 0
    vencimentos_passados: int = 0
    ultimo_processamento: str = ""
    esperados: tuple[str, ...] = ()
    faltantes: tuple[str, ...] = ()
    situacao: str = "Sem documentos"

    @property
    def total_documentos(self) -> int:
        return self.xml + self.guias + self.pdf + self.zip + self.outros

    @property
    def total_pendencias(self) -> int:
        return (
            len(self.faltantes)
            + self.links_pendentes
            + self.erros
            + self.revisar_documentos
            + self.vencimentos_passados
        )

    @property
    def conferencia_texto(self) -> str:
        partes = [f"{self.conferidos} OK"]
        if self.revisar_documentos:
            partes.append(f"{self.revisar_documentos} revisar")
        if self.vencimentos_passados:
            partes.append(f"{self.vencimentos_passados} venc.")
        return " / ".join(partes)

    @property
    def esperados_texto(self) -> str:
        return ", ".join(self.esperados) if self.esperados else "Nenhum"

    @property
    def faltantes_texto(self) -> str:
        return ", ".join(self.faltantes) if self.faltantes else "—"

    def como_linha_csv(self) -> list[object]:
        return [
            self.empresa,
            self.emails,
            self.xml,
            self.guias,
            self.pdf,
            self.zip,
            self.outros,
            self.total_documentos,
            self.esperados_texto,
            self.faltantes_texto,
            self.links_pendentes,
            self.duplicados,
            self.erros,
            self.conferencia_texto,
            self.ultimo_processamento,
            self.situacao,
        ]


@dataclass(slots=True)
class DocumentoMensal:
    id: int
    empresa: str
    categoria: str
    nome_original: str
    nome_salvo: str
    origem: str
    status: str
    salvo_em: str
    caminho: Path
    documento_tipo: str = ""
    numero_documento: str = ""
    cnpj: str = ""
    competencia_documento: str = ""
    valor: float | None = None
    vencimento: str = ""
    tributo: str = ""
    status_conferencia: str = "NÃO ANALISADO"
    alertas: str = ""
    fonte_leitura: str = ""
    resumo_leitura: str = ""

    @property
    def pasta(self) -> Path:
        return self.caminho.parent

    @property
    def valor_texto(self) -> str:
        if self.valor is None:
            return "—"
        return f"R$ {self.valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @property
    def vencimento_texto(self) -> str:
        if not self.vencimento:
            return "—"
        try:
            return datetime.strptime(self.vencimento, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return self.vencimento


class PainelMensalService:
    """Monta o painel usando o banco local e os arquivos realmente existentes."""

    def __init__(
        self,
        configuracao: ConfiguracaoRoboEmail,
        repositorio: RoboEmailRepositorio | None = None,
    ):
        self.configuracao = configuracao
        self.repositorio = repositorio or RoboEmailRepositorio()

    def gerar(self, ano: int, mes: int) -> list[ResumoEmpresaMensal]:
        self._validar_periodo(ano, mes)
        banco = self.repositorio.resumo_mensal(ano, mes)
        resultados: list[ResumoEmpresaMensal] = []
        esperados_por_empresa = ConfiguracaoRoboEmail.normalizar_documentos_esperados(
            self.configuracao.documentos_esperados
        )

        for empresa in EMPRESAS_POR_ALIAS.values():
            dados_banco = banco.get(empresa, {})
            arquivos, ultima_data_arquivo = self._contar_arquivos(empresa, ano, mes)
            ultimo = dados_banco.get("ultimo_processamento", "") or ultima_data_arquivo
            esperados = tuple(esperados_por_empresa.get(empresa, ()))
            faltantes = tuple(
                categoria
                for categoria in esperados
                if arquivos.get(categoria, 0) <= 0
            )

            resumo = ResumoEmpresaMensal(
                empresa=empresa,
                emails=int(dados_banco.get("emails", 0)),
                xml=arquivos["XML"],
                guias=arquivos["Guias"],
                pdf=arquivos["PDF"],
                zip=arquivos["ZIP"],
                outros=arquivos["Outros"] + arquivos["Links"],
                links_pendentes=int(dados_banco.get("links_pendentes", 0)),
                duplicados=int(dados_banco.get("duplicados", 0)),
                erros=int(dados_banco.get("erros", 0)),
                conferidos=int(dados_banco.get("conferidos", 0)),
                revisar_documentos=int(dados_banco.get("revisar_documentos", 0)),
                vencimentos_passados=int(dados_banco.get("vencimentos_passados", 0)),
                ultimo_processamento=self._formatar_data(ultimo),
                esperados=esperados,
                faltantes=faltantes,
            )
            resumo.situacao = self._situacao(resumo)
            resultados.append(resumo)

        return resultados

    def pasta_empresa(self, empresa: str, ano: int, mes: int) -> Path:
        self._validar_periodo(ano, mes)
        return (
            self.configuracao.destino
            / pasta_empresa_segura(empresa)
            / f"{ano:04d}"
            / f"{mes:02d}"
        )

    def pasta_revisar(self, ano: int, mes: int) -> Path:
        self._validar_periodo(ano, mes)
        return self.configuracao.destino / PASTA_REVISAO / f"{ano:04d}" / f"{mes:02d}"

    def listar_documentos(
        self,
        empresa: str,
        ano: int,
        mes: int,
    ) -> list[DocumentoMensal]:
        """Lista nome original, nome padronizado e caminho gravado."""

        self._validar_periodo(ano, mes)
        competencia = f"{ano:04d}-{mes:02d}"
        linhas = self.repositorio.listar_documentos(
            empresa=empresa,
            competencia=competencia,
            limite=5000,
        )
        documentos: list[DocumentoMensal] = []
        caminhos_registrados: set[str] = set()
        for linha in linhas:
            caminho = Path(str(linha["caminho_salvo"] or ""))
            chave = str(caminho).casefold()
            caminhos_registrados.add(chave)
            documentos.append(
                DocumentoMensal(
                    id=int(linha["id"] or 0),
                    empresa=str(linha["empresa"] or empresa),
                    categoria=str(linha["categoria"] or "Outros"),
                    nome_original=str(linha["nome_original"] or ""),
                    nome_salvo=str(linha["nome_padronizado"] or caminho.name),
                    origem=str(linha["origem_documento"] or "GMAIL"),
                    status=str(linha["status_organizacao"] or "ORGANIZADO"),
                    salvo_em=self._formatar_data(str(linha["salvo_em"] or "")),
                    caminho=caminho,
                    documento_tipo=str(linha["documento_tipo"] or ""),
                    numero_documento=str(linha["documento_numero"] or ""),
                    cnpj=str(linha["cnpj_documento"] or ""),
                    competencia_documento=str(linha["competencia_documento"] or linha["competencia"] or ""),
                    valor=float(linha["valor_documento"]) if linha["valor_documento"] is not None else None,
                    vencimento=str(linha["vencimento_documento"] or ""),
                    tributo=str(linha["tributo_documento"] or ""),
                    status_conferencia=str(linha["status_conferencia"] or "NÃO ANALISADO"),
                    alertas=str(linha["alertas_conferencia"] or ""),
                    fonte_leitura=str(linha["fonte_leitura"] or ""),
                    resumo_leitura=str(linha["resumo_leitura"] or ""),
                )
            )

        # Preserva a visualização de documentos antigos, gravados antes da
        # Sprint 2.4 e ainda sem os novos metadados no banco.
        pasta_mes = self.pasta_empresa(empresa, ano, mes)
        if pasta_mes.is_dir():
            for arquivo in pasta_mes.rglob("*"):
                if not arquivo.is_file() or str(arquivo).casefold() in caminhos_registrados:
                    continue
                try:
                    data = datetime.fromtimestamp(arquivo.stat().st_mtime).strftime(
                        "%d/%m/%Y %H:%M"
                    )
                except OSError:
                    data = "—"
                documentos.append(
                    DocumentoMensal(
                        id=0,
                        empresa=empresa,
                        categoria=arquivo.parent.name,
                        nome_original=arquivo.name,
                        nome_salvo=arquivo.name,
                        origem="ARQUIVO ANTERIOR",
                        status="ARQUIVADO",
                        salvo_em=data,
                        caminho=arquivo,
                    )
                )

        documentos.sort(key=lambda item: (item.categoria, item.nome_salvo.casefold()))
        return documentos

    def listar_revisar(self, ano: int, mes: int) -> list[DocumentoMensal]:
        self._validar_periodo(ano, mes)
        competencia = f"{ano:04d}-{mes:02d}"
        linhas = self.repositorio.listar_documentos(
            empresa="Não Identificada",
            competencia=competencia,
            limite=5000,
        )
        documentos: list[DocumentoMensal] = []
        caminhos_registrados: set[str] = set()
        for linha in linhas:
            caminho = Path(str(linha["caminho_salvo"] or ""))
            caminhos_registrados.add(str(caminho).casefold())
            documentos.append(
                DocumentoMensal(
                    id=int(linha["id"] or 0),
                    empresa="Não Identificada",
                    categoria=str(linha["categoria"] or "Outros"),
                    nome_original=str(linha["nome_original"] or ""),
                    nome_salvo=str(linha["nome_padronizado"] or caminho.name),
                    origem=str(linha["origem_documento"] or "GMAIL"),
                    status=str(linha["status_organizacao"] or "ORGANIZADO"),
                    salvo_em=self._formatar_data(str(linha["salvo_em"] or "")),
                    caminho=caminho,
                    documento_tipo=str(linha["documento_tipo"] or ""),
                    numero_documento=str(linha["documento_numero"] or ""),
                    cnpj=str(linha["cnpj_documento"] or ""),
                    competencia_documento=str(linha["competencia_documento"] or linha["competencia"] or ""),
                    valor=float(linha["valor_documento"]) if linha["valor_documento"] is not None else None,
                    vencimento=str(linha["vencimento_documento"] or ""),
                    tributo=str(linha["tributo_documento"] or ""),
                    status_conferencia=str(linha["status_conferencia"] or "NÃO ANALISADO"),
                    alertas=str(linha["alertas_conferencia"] or ""),
                    fonte_leitura=str(linha["fonte_leitura"] or ""),
                    resumo_leitura=str(linha["resumo_leitura"] or ""),
                )
            )

        pasta = self.pasta_revisar(ano, mes)
        if pasta.is_dir():
            for arquivo in pasta.rglob("*"):
                if not arquivo.is_file() or str(arquivo).casefold() in caminhos_registrados:
                    continue
                documentos.append(
                    DocumentoMensal(
                        id=0,
                        empresa="Não Identificada",
                        categoria=arquivo.parent.name,
                        nome_original=arquivo.name,
                        nome_salvo=arquivo.name,
                        origem="ARQUIVO ANTERIOR",
                        status="REVISAR",
                        salvo_em="—",
                        caminho=arquivo,
                    )
                )
        documentos.sort(key=lambda item: (item.categoria, item.nome_salvo.casefold()))
        return documentos

    def reanalisar_documentos(
        self,
        empresa: str,
        ano: int,
        mes: int,
    ) -> dict[str, int]:
        """Relê documentos já salvos sem mover ou renomear arquivos antigos."""

        documentos = self.listar_documentos(empresa, ano, mes)
        leitor = LeitorInteligenteDocumentos(self.configuracao.cnpjs_empresas)
        resultado = {"analisados": 0, "conferidos": 0, "revisar": 0, "vencidos": 0, "erros": 0}
        for documento in documentos:
            if documento.id <= 0 or not documento.caminho.is_file():
                continue
            linha = self.repositorio.obter_documento(documento.id)
            try:
                dados = documento.caminho.read_bytes()
                data_email = datetime.now()
                if linha and linha["data_email"]:
                    try:
                        data_email = datetime.fromisoformat(str(linha["data_email"]))
                    except ValueError:
                        pass
                empresa_informada = None if documento.empresa == "Não Identificada" else documento.empresa
                leitura = leitor.analisar(
                    nome_original=documento.nome_original or documento.nome_salvo,
                    dados=dados,
                    categoria=documento.categoria,
                    empresa_informada=empresa_informada,
                    data_email=data_email,
                    assunto=str(linha["assunto"] or "") if linha else "",
                )
                status_org = "ORGANIZADO" if empresa_informada else "REVISAR"
                detalhe = f"Leitura: {leitura.resumo}."
                if leitura.alertas:
                    detalhe += " Alertas: " + " | ".join(leitura.alertas)
                self.repositorio.atualizar_conferencia_por_id(
                    documento.id,
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
                    status_organizacao=status_org,
                    detalhe_organizacao=detalhe,
                )
                resultado["analisados"] += 1
                if leitura.status == "CONFERIDO":
                    resultado["conferidos"] += 1
                elif leitura.status == "VENCIMENTO PASSADO":
                    resultado["vencidos"] += 1
                else:
                    resultado["revisar"] += 1
            except (OSError, ValueError) as erro:
                resultado["erros"] += 1
                self.repositorio.atualizar_conferencia_por_id(
                    documento.id,
                    status_conferencia="REVISAR",
                    alertas_conferencia=f"Falha ao reler o documento: {erro}",
                    status_organizacao="REVISAR",
                )
        return resultado

    def exportar_csv(
        self,
        destino: str | Path,
        ano: int,
        mes: int,
        linhas: Iterable[ResumoEmpresaMensal] | None = None,
    ) -> Path:
        self._validar_periodo(ano, mes)
        caminho = Path(destino).expanduser()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        dados = list(linhas) if linhas is not None else self.gerar(ano, mes)

        cabecalho = [
            "Empresa",
            "E-mails processados",
            "XML",
            "Guias",
            "PDF",
            "ZIP",
            "Outros",
            "Total de documentos",
            "Documentos esperados",
            "Documentos faltantes",
            "Links pendentes",
            "Duplicados",
            "Erros",
            "Conferência inteligente",
            "Último processamento",
            "Situação",
        ]
        with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow([f"Painel mensal do Robô FiscalPro — {mes:02d}/{ano:04d}"])
            escritor.writerow([])
            escritor.writerow(cabecalho)
            for linha in dados:
                escritor.writerow(linha.como_linha_csv())

            escritor.writerow([])
            escritor.writerow(
                [
                    "TOTAL",
                    sum(item.emails for item in dados),
                    sum(item.xml for item in dados),
                    sum(item.guias for item in dados),
                    sum(item.pdf for item in dados),
                    sum(item.zip for item in dados),
                    sum(item.outros for item in dados),
                    sum(item.total_documentos for item in dados),
                    "",
                    sum(len(item.faltantes) for item in dados),
                    sum(item.links_pendentes for item in dados),
                    sum(item.duplicados for item in dados),
                    sum(item.erros for item in dados),
                    f"{sum(item.conferidos for item in dados)} OK / "
                    f"{sum(item.revisar_documentos for item in dados)} revisar / "
                    f"{sum(item.vencimentos_passados for item in dados)} venc.",
                    "",
                    "",
                ]
            )
        return caminho

    def _contar_arquivos(
        self, empresa: str, ano: int, mes: int
    ) -> tuple[dict[str, int], str]:
        contagem = {categoria: 0 for categoria in CATEGORIAS_PAINEL}
        ultima_modificacao = 0.0
        pasta_mes = self.pasta_empresa(empresa, ano, mes)

        for categoria in CATEGORIAS_PAINEL:
            pasta_categoria = pasta_mes / categoria
            if not pasta_categoria.is_dir():
                continue
            for arquivo in pasta_categoria.rglob("*"):
                if not arquivo.is_file():
                    continue
                contagem[categoria] += 1
                try:
                    ultima_modificacao = max(ultima_modificacao, arquivo.stat().st_mtime)
                except OSError:
                    continue

        ultima = (
            datetime.fromtimestamp(ultima_modificacao).isoformat(timespec="seconds")
            if ultima_modificacao
            else ""
        )
        return contagem, ultima

    @staticmethod
    def _situacao(resumo: ResumoEmpresaMensal) -> str:
        if (
            resumo.erros
            or resumo.links_pendentes
            or resumo.revisar_documentos
            or resumo.vencimentos_passados
        ):
            return "Revisar conferência"
        if resumo.faltantes:
            return "Faltam: " + ", ".join(resumo.faltantes)
        if resumo.total_documentos == 0:
            return "Sem documentos"
        return "Completo"

    @staticmethod
    def _formatar_data(valor: str) -> str:
        if not valor:
            return "—"
        try:
            return datetime.fromisoformat(str(valor)).strftime("%d/%m/%Y %H:%M")
        except (TypeError, ValueError):
            return str(valor)

    @staticmethod
    def _validar_periodo(ano: int, mes: int) -> None:
        if not 2000 <= int(ano) <= 2100:
            raise ValueError("Informe um ano entre 2000 e 2100.")
        if not 1 <= int(mes) <= 12:
            raise ValueError("Informe um mês entre 1 e 12.")


__all__ = [
    "CATEGORIAS_PAINEL",
    "CATEGORIAS_DOCUMENTOS_ESPERADOS",
    "PainelMensalService",
    "DocumentoMensal",
    "ResumoEmpresaMensal",
]
