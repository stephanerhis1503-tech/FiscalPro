"""Mapa de lacunas da Ficha Assistida: somente triagem, nunca regra tributaria.

Agrupa os mesmos itens da auditoria por NCM e por contexto distinto; nao abre
fiscalpro.db, nao altera SPED, nao converte catalogos oficiais em regras e nao
associa regras operacionais de saida a entradas.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def _texto(valor: Any) -> str:
    return str(valor if valor is not None else "").strip()


def _condicional_st(proposta: Any) -> bool:
    status = getattr(proposta, "st_status", ()) or ()
    if isinstance(status, str):
        status = (status,)
    return any(_texto(s).upper().startswith("CONDICIONAL") for s in status)


def _prioridade(propostas: list[Any]) -> tuple[str, str]:
    finalidades = {_texto(p.finalidade) or "INDEFINIDA" for p in propostas}
    if "INDEFINIDA" in finalidades:
        return (
            "1 - FINALIDADE INDEFINIDA",
            "Conferir natureza da entrada, CFOP, documento e finalidade antes de criar regra.",
        )
    if len(finalidades) > 1:
        return (
            "2 - FINALIDADES DIFERENTES",
            "Separar revenda, uso e consumo ou outras entradas; verificar direitos a credito.",
        )
    if any(_condicional_st(p) for p in propostas):
        return (
            "3 - ST CONDICIONAL",
            "Conferir NCM, descricao legal, XML, CEST e responsabilidade ST, caso a caso.",
        )
    if finalidades == {"USO E CONSUMO"}:
        return (
            "4 - USO E CONSUMO",
            "Conferir finalidade e creditos; nao copiar regra de compra para revenda.",
        )
    return (
        "5 - REVENDA / CONFERIR",
        "Conferir o CFOP de entrada, UF, CST, ST e base legal antes de homologar.",
    )


def consolidar_lacunas(propostas: Iterable[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Retorna linhas para 1 aba por NCM e 1 aba por contexto operacional.

    ID de regra na proposta significa somente aprovacao nessa exportacao;
    ausente NAO significa que o banco global esteja vazio.
    """
    por_ncm: dict[str, list[Any]] = defaultdict(list)
    por_contexto: dict[tuple[str, ...], list[Any]] = defaultdict(list)
    for p in propostas:
        ncm = _texto(p.ncm)
        if len(ncm) != 8 or not ncm.isdigit():
            continue
        por_ncm[ncm].append(p)
        for cfop in sorted({_texto(v) for v in p.cfops_sped} or {""}):
            chave = (
                ncm, _texto(p.empresa), _texto(p.regime), _texto(p.operacao),
                _texto(p.finalidade), _texto(p.uf_origem), _texto(p.uf_destino),
                _texto(p.contribuinte), cfop,
            )
            por_contexto[chave].append(p)

    ncms: list[dict[str, Any]] = []
    for ncm, grupo in por_ncm.items():
        prioridade, orientacao = _prioridade(grupo)
        ncms.append({
            "prioridade": prioridade,
            "ncm": ncm,
            "propostas": len(grupo),
            "itens": sum(p.itens for p in grupo),
            "produtos": len({_texto(p.codigo_produto) for p in grupo}),
            "finalidades": ", ".join(sorted({_texto(p.finalidade) or "INDEFINIDA" for p in grupo})),
            "cfops": ", ".join(sorted({v for p in grupo for v in p.cfops_sped})),
            "ufs": ", ".join(sorted({_texto(p.uf_origem) for p in grupo})),
            "st_condicional": sum(_condicional_st(p) for p in grupo),
            "ids_aprovados": sum(bool(p.regra_id) for p in grupo),
            "situacao": "SEM ID APROVADO NESTA EXPORTACAO" if not any(p.regra_id for p in grupo)
                        else "HA ID NA EXPORTACAO - CONFERIR CONTEXTO",
            "orientacao": orientacao,
            "amostras": "; ".join(sorted({_texto(p.descricao) for p in grupo})[:3]),
        })
    ncms.sort(key=lambda row: (-row["itens"], row["ncm"]))

    contextos: list[dict[str, Any]] = []
    for chave, grupo in por_contexto.items():
        prioridade, orientacao = _prioridade(grupo)
        ncm, empresa, regime, operacao, finalidade, origem, destino, contribuinte, cfop = chave
        contextos.append({
            "prioridade": prioridade,
            "ncm": ncm,
            "empresa": empresa,
            "regime": regime,
            "operacao": operacao,
            "finalidade": finalidade or "INDEFINIDA",
            "origem": origem,
            "destino": destino,
            "contribuinte": contribuinte,
            "cfop": cfop,
            "propostas": len(grupo),
            "itens": sum(p.itens for p in grupo),
            "st_condicional": sum(_condicional_st(p) for p in grupo),
            "ids_aprovados": sum(bool(p.regra_id) for p in grupo),
            "orientacao": orientacao,
            "validacao": "PENDENTE - SEM HOMOLOGACAO AUTOMATICA",
        })
    contextos.sort(key=lambda row: (-row["itens"], row["ncm"], row["cfop"]))
    return ncms, contextos
