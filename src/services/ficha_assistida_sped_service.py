"""Ficha Tributaria Assistida no SPED: propostas sem gravacao automatica.

O SPED e as consultas oficiais fornecem indicios. Nao se presumem CST,
aliquotas, ICMS-ST, credito, CEST ou CFOP corretos a partir do XML/NCM.
Cada regra aprovada exige revisao individual, fundamento e confirmacao
explicita da abrangencia por NCM antes da gravacao.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository

MARCADOR_CAMPOS = "FISCALPRO_ASSISTIDA_CAMPOS:"
CAMPOS_MANUAIS = (
    "cfop", "cest", "cst_icms", "icms", "icms_st", "fcp",
    "cst_pis", "aliquota_pis", "cst_cofins", "aliquota_cofins",
    "cst_ipi", "ipi",
)
CAMPOS_NUMERICOS = {"icms", "fcp", "aliquota_pis", "aliquota_cofins", "ipi"}
# Indicios da finalidade declarada no CFOP; nunca sao prova da
# tributacao material nem autorizam credito de PIS/Cofins ou ICMS.
CFOP_USO_CONSUMO = {"1407", "2407", "1556", "2556", "1653", "2653"}
CFOP_REVENDA = {"1102", "2102", "1403", "2403"}
CFOP_OUTROS = {"1910", "2910", "1949", "2949"}


def _indicio_cfop(cfop: str) -> str:
    codigo = _texto(cfop).replace(".", "")
    if codigo in CFOP_USO_CONSUMO:
        return "USO E CONSUMO"
    if codigo in CFOP_REVENDA:
        return "REVENDA"
    if codigo in CFOP_OUTROS:
        return "OUTRAS ENTRADAS - REVISAR"
    return "SEM CLASSIFICACAO AUTOMATICA"


def _texto(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _seguro_excel(v: Any) -> str:
    s = _texto(v)
    return "'" + s if s.lstrip().startswith(("=", "+", "-", "@")) else s


def _iso(v: Any) -> str:
    s = _texto(v)
    if not s:
        return ""
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return ""


@dataclass
class PropostaFichaAssistida:
    identificador: int
    ncm: str
    codigo_produto: str
    descricao: str
    empresa: str
    regime: str
    operacao: str
    finalidade: str
    uf_origem: str
    uf_destino: str
    contribuinte: str
    primeira_data: str = ""
    ultima_data: str = ""
    itens: int = 0
    documentos: set[str] = field(default_factory=set)
    cfops_sped: set[str] = field(default_factory=set)
    fontes_referenciais: set[str] = field(default_factory=set)
    st_status: set[str] = field(default_factory=set)
    pis_status: set[str] = field(default_factory=set)
    st_enquadramentos: set[str] = field(default_factory=set)
    st_recolhimentos: set[str] = field(default_factory=set)
    st_difal: set[str] = field(default_factory=set)
    icms_creditos: set[str] = field(default_factory=set)
    falha_tecnica: bool = False
    produtos_no_ncm: int = 0
    regra_id: int | None = None
    finalidade_informada: str = ""
    finalidade_status: str = ""
    finalidade_motivos: set[str] = field(default_factory=set)

    @property
    def situacao(self) -> str:
        return "APROVADA MANUALMENTE" if self.regra_id else "PENDENTE DE REVISAO"

    @property
    def indicios_cfop(self) -> set[str]:
        return {_indicio_cfop(cfop) for cfop in self.cfops_sped} or {
            "SEM CLASSIFICACAO AUTOMATICA"
        }

    @property
    def aviso_finalidade(self) -> str:
        indicios = self.indicios_cfop
        if len(indicios) != 1:
            return "REVISAR FINALIDADE: CFOPs de operacoes distintas"
        indicio = next(iter(indicios))
        if indicio in {"OUTRAS ENTRADAS - REVISAR", "SEM CLASSIFICACAO AUTOMATICA"}:
            return f"REVISAR FINALIDADE: {indicio}"
        if self.finalidade_status == "REVISAR":
            return "REVISAR FINALIDADE: CFOP sem classificação segura"
        if self.finalidade_status == "INDICIO_CFOP" and (
            self.finalidade_informada != self.finalidade
        ):
            return (
                f"REVISAR FINALIDADE: padrao {self.finalidade_informada or '-'}; "
                f"CFOP indica {self.finalidade or indicio}"
            )
        if indicio != self.finalidade:
            return f"REVISAR FINALIDADE: informada {self.finalidade or '-'}; CFOP indica {indicio}"
        return "INDICIO PELO CFOP (ainda exige revisao fiscal)"

    @property
    def requer_revisao_finalidade(self) -> bool:
        return (
            self.aviso_finalidade.startswith("REVISAR")
            or self.finalidade_status == "INDICIO_CFOP"
        )

    @property
    def contexto_completo(self) -> bool:
        return bool(
            self.empresa and self.regime and self.operacao and self.finalidade
            and self.uf_origem and self.uf_destino and self.contribuinte
            and self.primeira_data and self.ultima_data
        )


class FichaAssistidaSPEDService:
    """Cria memoria de propostas e permite salvar somente apos aprovacao."""

    @staticmethod
    def preparar(auditoria: Any) -> list[PropostaFichaAssistida]:
        """Somente leitura; nem sequer abre conexao com o banco."""
        grupos: dict[tuple[str, ...], PropostaFichaAssistida] = {}
        for ref in getattr(auditoria, "referencias_fiscais", ()):
            ncm = "".join(x for x in _texto(ref.get("ncm")) if x.isdigit())
            if len(ncm) != 8:
                continue
            chave = tuple(_texto(ref.get(campo)) for campo in (
                "ncm", "codigo_produto", "descricao_sped", "empresa", "regime",
                "operacao", "finalidade", "uf_origem", "uf_destino", "contribuinte",
                "cfop_sped",
            ))
            if chave not in grupos:
                grupos[chave] = PropostaFichaAssistida(
                    identificador=len(grupos) + 1,
                    ncm=ncm, codigo_produto=chave[1], descricao=chave[2],
                    empresa=chave[3], regime=chave[4], operacao=chave[5],
                    finalidade=chave[6], uf_origem=chave[7],
                    uf_destino=chave[8], contribuinte=chave[9],
                    finalidade_informada=_texto(ref.get("finalidade_informada")),
                    finalidade_status=_texto(ref.get("finalidade_status")),
                )
            proposta = grupos[chave]
            proposta.itens += 1
            numero = _texto(ref.get("chave") or ref.get("nota"))
            if numero:
                proposta.documentos.add(numero)
            cfop = _texto(ref.get("cfop_sped"))
            if cfop:
                proposta.cfops_sped.add(cfop)
            data = _iso(ref.get("data_operacao"))
            if data:
                if not proposta.primeira_data or data < proposta.primeira_data:
                    proposta.primeira_data = data
                if not proposta.ultima_data or data > proposta.ultima_data:
                    proposta.ultima_data = data
            for campo in ("pis_fonte", "icms_fonte", "ncm_fonte"):
                fonte = _texto(ref.get(campo))
                if fonte:
                    proposta.fontes_referenciais.add(fonte)
            for campo, destino in (
                ("st_status", proposta.st_status),
                ("pis_status", proposta.pis_status),
            ):
                if _texto(ref.get(campo)):
                    destino.add(_texto(ref[campo]))
            for nome, destino in (
                ("st_enquadramento_mercadoria_status", proposta.st_enquadramentos),
                ("st_recolhimento_status", proposta.st_recolhimentos),
                ("st_difal_status", proposta.st_difal),
                ("icms_credito_status", proposta.icms_creditos),
            ):
                if _texto(ref.get(nome)):
                    destino.add(_texto(ref[nome]))
            proposta.falha_tecnica |= bool(ref.get("falha_tecnica"))
            if _texto(ref.get("finalidade_motivo")):
                proposta.finalidade_motivos.add(_texto(ref["finalidade_motivo"]))

        grupos_por_ncm: dict[str, set[str]] = {}
        for proposta in grupos.values():
            grupos_por_ncm.setdefault(proposta.ncm, set()).add(
                proposta.codigo_produto or proposta.descricao
            )
        for proposta in grupos.values():
            proposta.produtos_no_ncm = len(grupos_por_ncm[proposta.ncm])
        return sorted(
            grupos.values(),
            key=lambda p: (-p.itens, p.ncm, p.codigo_produto, p.empresa),
        )

    @staticmethod
    def aprovar(
        proposta: PropostaFichaAssistida,
        campos: dict[str, Any],
        *,
        confirmar_revisao: bool = False,
        confirmar_abrangencia_ncm: bool = False,
    ) -> int:
        """Unico ponto que grava dados da Ficha, por acao humana expressa."""
        if proposta.regra_id:
            raise ValueError("Esta proposta ja foi salva. Reabra a Ficha para editar.")
        if not (confirmar_revisao and confirmar_abrangencia_ncm):
            raise ValueError(
                "Confirme a revisao fiscal e a abrangencia da regra a TODOS "
                "os produtos do NCM. Uma proposta por produto nao limita a regra "
                "operacional a esse codigo de produto."
            )
        if not proposta.contexto_completo:
            raise ValueError(
                "Empresa, regime, operacao, finalidade, UFs, contribuinte "
                "e datas sao obrigatorios para aprovar."
            )
        finalidade_revisada = _texto(campos.get("finalidade_revisada")).upper()
        indicios = proposta.indicios_cfop
        if proposta.requer_revisao_finalidade and not finalidade_revisada:
            raise ValueError(
                "A finalidade informada nao corresponde ao CFOP ou exige "
                "classificacao especifica. Selecione a finalidade revisada "
                "manualmente antes de aprovar."
            )
        if not finalidade_revisada:
            finalidade_revisada = proposta.finalidade
        if finalidade_revisada not in {
            "REVENDA", "USO E CONSUMO", "INSUMO", "INDUSTRIALIZAÇÃO",
            "ATIVO IMOBILIZADO", "SERVIÇO", "OUTRA",
        }:
            raise ValueError("Selecione uma finalidade tributaria valida.")
        if len(indicios) != 1:
            raise ValueError(
                "A proposta contem CFOPs de naturezas distintas. "
                "Separe as operacoes e revise a finalidade antes de aprovar."
            )
        indicio = next(iter(indicios))
        if indicio in {"USO E CONSUMO", "REVENDA"} and finalidade_revisada != indicio:
            raise ValueError(
                f"O CFOP indica {indicio}, mas a finalidade revisada e "
                f"{finalidade_revisada}. Corrija a classificacao documental "
                "ou cadastre uma regra individual pela Ficha, apos fundamentar."
            )
        justificativa = _texto(campos.get("justificativa_finalidade"))
        if indicio not in {"USO E CONSUMO", "REVENDA"} and len(justificativa) < 20:
            raise ValueError(
                "CFOP de outras entradas/sem classificacao: informe "
                "justificativa de pelo menos 20 caracteres para a finalidade."
            )
        fonte = _texto(campos.get("fonte"))
        if len(fonte) < 15:
            raise ValueError(
                "Informe fundamento legal especifico, vigente e conferido "
                "(norma/artigo ou URL); nao utilize apenas a sugestao do NCM."
            )
        inicio = _texto(campos.get("vigencia_inicio"))
        fim = _texto(campos.get("vigencia_fim"))
        try:
            inicio_dt = date.fromisoformat(inicio)
            fim_dt = date.fromisoformat(fim)
        except ValueError as exc:
            raise ValueError("Informe vigencia inicial e final no formato AAAA-MM-DD.") from exc
        if inicio_dt > fim_dt:
            raise ValueError("Vigencia final anterior a inicial.")
        if inicio > proposta.primeira_data or fim < proposta.ultima_data:
            raise ValueError(
                "O periodo informado nao abrange todas as notas da proposta. "
                "Revise a vigencia legal ou separe as operacoes."
            )
        if any(
            _texto(campos.get(k)) for k in ("ncm", "empresa", "operacao", "regime")
        ):
            raise ValueError("NCM, empresa, regime e operacao sao fixos nesta proposta.")
        aprovados: dict[str, str] = {}
        for campo in CAMPOS_MANUAIS:
            valor = _texto(campos.get(campo))
            if valor:
                aprovados[campo] = valor
        if not aprovados:
            raise ValueError(
                "Informe manualmente ao menos um campo fiscal validado "
                "e o fundamento correspondente. Nao basta aprovar o NCM."
            )
        if aprovados.get("icms_st", "").upper() in {"SIM", "S", "ST", "1"}:
            if not aprovados.get("cest"):
                raise ValueError("ICMS-ST SIM exige CEST e conferencia legal expressa.")
        obs = _texto(campos.get("observacoes"))
        # Marcador reconhecido pelo auditor para NAO comparar campos numericos
        # omitidos, os quais o repositorio legado normaliza como 0.0.
        obs = (
            "Regra assistida revisada individualmente; todos os produtos do "
            f"NCM {proposta.ncm} no contexto declarado. "
            "SPED/XML utilizados somente como evidencia.\n"
            f"Finalidade revisada: {finalidade_revisada}; "
            f"CFOP observado: {','.join(sorted(proposta.cfops_sped))}; "
            f"justificativa: {justificativa or 'CFOP compativel'}\n"
            f"[{MARCADOR_CAMPOS}{','.join(sorted(aprovados))}]\n"
            + obs
        )
        dados = {
            "ncm": proposta.ncm,
            "empresa": proposta.empresa,
            "regime": proposta.regime,
            "operacao": proposta.operacao,
            "finalidade": finalidade_revisada,
            "uf_origem": proposta.uf_origem,
            "uf_destino": proposta.uf_destino,
            "contribuinte": proposta.contribuinte,
            "vigencia_inicio": inicio,
            "vigencia_fim": fim,
            "status": "VIGENTE",
            "fonte": fonte,
            "confiabilidade": 80,  # Registro manual; nao e medida de certeza legal.
            "observacoes": obs,
            **aprovados,
        }
        # Falha do repositorio (inclusive regra duplicada) nao marca aprovada.
        regra_id = FichaTributariaRepository.salvar_tributacao_atual(
            dados, encerrar_anterior=False
        )
        proposta.regra_id = int(regra_id)
        return proposta.regra_id

    @staticmethod
    def exportar(propostas: list[PropostaFichaAssistida], destino: str | Path) -> Path:
        """Planilha de triagem sem gravar regras no banco."""
        destino = Path(destino)
        if destino.suffix.lower() != ".xlsx":
            raise ValueError("Informe um arquivo .xlsx.")
        wb = Workbook()
        ws = wb.active
        ws.title = "Propostas para revisao"
        colunas = [
            "Status", "NCM", "Codigo no SPED", "Descricao", "Empresa", "Regime",
            "Operacao", "Finalidade informada", "UF origem", "UF destino",
            "Contribuinte", "Primeira data", "Ultima data", "Itens C170",
            "NF-e distintas", "CFOP observado (NAO aprovado)",
            "Situacao PIS/Cofins", "Situacao ICMS-ST",
            "Fontes referenciais (NAO aprovadas)",
            "Qtde codigos do mesmo NCM", "Falha consulta", "ID regra aprovada",
            "Orientacao", "Indicio de finalidade pelo CFOP",
            "Conferencia da finalidade",
            "Finalidade padrão da tela", "Status da classificação",
            "Explicação da classificação",
            "ST - enquadramento original da mercadoria",
            "ST - responsabilidade/recolhimento",
            "ST-DIFAL na entrada",
            "Crédito ICMS - orientação",
        ]
        ws.append(colunas)
        for p in propostas:
            ws.append([
                p.situacao, p.ncm, p.codigo_produto, p.descricao, p.empresa,
                p.regime, p.operacao, p.finalidade, p.uf_origem, p.uf_destino,
                p.contribuinte, p.primeira_data, p.ultima_data, p.itens,
                len(p.documentos), ", ".join(sorted(p.cfops_sped)),
                "; ".join(sorted(p.pis_status)), "; ".join(sorted(p.st_status)),
                "; ".join(sorted(p.fontes_referenciais)),
                p.produtos_no_ncm, "SIM" if p.falha_tecnica else "NAO",
                p.regra_id or "",
                "Revisar enquadramento legal e campos. Nunca copiar do XML como regra.",
                "; ".join(sorted(p.indicios_cfop)), p.aviso_finalidade,
                p.finalidade_informada, p.finalidade_status,
                "; ".join(sorted(p.finalidade_motivos)),
                "; ".join(sorted(p.st_enquadramentos)),
                "; ".join(sorted(p.st_recolhimentos)),
                "; ".join(sorted(p.st_difal)),
                "; ".join(sorted(p.icms_creditos)),
            ])
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="214C74")
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[1].height = 34
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, str):
                    cell.value = _seguro_excel(cell.value)
                    cell.number_format = "@"
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if cell.row % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor="F2F6FA")
        for col in range(1, len(colunas) + 1):
            largura = 48 if col in (4, 19, 23, 25, 28, 29, 30, 31, 32) else 26 if col in (5, 16, 17, 18, 24, 26) else 18
            ws.column_dimensions[get_column_letter(col)].width = largura
        ws.freeze_panes = "E2"
        ws.auto_filter.ref = f"A1:AF{max(ws.max_row, 2)}"
        for linha in ws.iter_rows(min_row=2):
            if linha[24].value and str(linha[24].value).startswith("REVISAR"):
                for col in (7, 8, 15, 24, 25):
                    linha[col - 1].fill = PatternFill("solid", fgColor="FFF0D5")
        ws.sheet_view.showGridLines = False
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        return destino
