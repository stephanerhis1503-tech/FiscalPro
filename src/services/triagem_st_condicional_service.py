"""Triagem explicativa de alertas condicionais de ST na Ficha Assistida.

Nao confere documentos fiscais, nao classifica imposto como devido e nao
concede credito. Os grupos sao apenas PRIORIDADES de revisao que dependem de
NCM/descricao/CFOP registrados no SPED, nunca de regra tributaria aprovada.
"""
from __future__ import annotations

from typing import Any


REFERENCIA = "1 - REFERENCIA LEGAL IDENTIFICADA"
DIVERGENCIA = "2 - DIVERGENCIA / CADASTRO A REVISAR"
DOCUMENTAL = "3 - CONFERENCIA DOCUMENTAL / LEGAL"


def triagem_st_condicional(proposta: Any) -> tuple[str, str, str]:
    """Retorna (grupo, indício, providência) sem atribuir CEST/ST ao item.

    Informacoes como CFOP do fornecedor, CST e CEST do XML so podem ser
    consideradas apos leitura do proprio documento e vinculacao ao nItem.
    A triagem NUNCA marca a Ficha como aprovada.
    """
    # "CONDICIONAL" deve ser a classificacao PRINCIPAL do alerta.
    # Mensagens como "MVA AJUSTADA ... ALIQUOTA INTERNA CONDICIONAL"
    # nao sao propostas ST condicionais e nao devem entrar nesta aba.
    status_originais = getattr(proposta, "st_status", ()) or ()
    if isinstance(status_originais, str):
        status_originais = (status_originais,)
    if not any(
        str(status).strip().upper().startswith("CONDICIONAL")
        for status in status_originais
    ):
        return "", "", ""

    ncm = "".join(ch for ch in str(getattr(proposta, "ncm", "")) if ch.isdigit())
    descricao = str(getattr(proposta, "descricao", "") or "").upper()
    cfops = set(str(x).replace(".", "") for x in getattr(proposta, "cfops_sped", set()))

    if ncm == "65061090" and "CAPACETE" in descricao:
        return (
            REFERENCIA,
            "Capacete de motociclista; verificar CEST 01.013.00 e desdobramento do antigo NCM 65061000. "
            "O enquadramento na lista nao comprova ST devida na entrada.",
            "Conferir XML/UF/retencao, isencao da saida interna em MG e possivel estorno de credito. "
            "Nao calcular ST pela NCM isolada.",
        )

    if ncm == "39199090" and "ADESIVO" in descricao:
        return (
            DIVERGENCIA,
            "O CEST 01.090.00 exige adesivo refletivo de seguranca; a descricao nao confirma "
            "refletividade ou a aplicacao efetiva.",
            "Conferir produto, CEST/CFOP/CST do fornecedor e descricao legal. "
            "CEST residual 01.999.00 nao e enquadramento automatico.",
        )

    if ncm == "32141010" and "SILICONE" in descricao:
        return (
            DIVERGENCIA,
            "NCM de silicone sem enquadramento ST nominal identificado na referencia de autopecas; "
            "a finalidade real da entrada deve ser confrontada com o CFOP do SPED.",
            "Confirmar se e uso e consumo ou revenda e conferir XML/CFOP/CST; "
            "CFOP 1102 nao pode ser mantido automaticamente se destinado a uso interno.",
        )

    if ncm == "84879000" and "RETENTOR" in descricao:
        return (
            DIVERGENCIA,
            "Retentor de vedacao no NCM 84879000: material/composicao podem exigir "
            "outra classificacao; 40169300 e CEST 01.007.00 sao apenas candidatos.",
            "Pedir ficha tecnica do fabricante e conferir o XML antes de alterar NCM/CEST ou ST.",
        )

    if ncm == "90328925" and "SENSOR" in descricao:
        return (
            DIVERGENCIA,
            "Sensor x possivel controlador eletronico (CEST 01.083.00): "
            "identidade e funcao precisam ser confirmadas com codigo do fabricante.",
            "Comparar referencia, descricao e ficha do fabricante com xProd/NCM/CEST do XML. "
            "Nao mudar NCM so pela palavra MAP.",
        )

    if ncm == "65070000" and "VISEIRA" in descricao:
        motivo = "Mecanismo/parte de capacete nao se confunde com capacete completo CEST 01.013.00."
        acao = "Verificar NCM, CEST, XML/CST e regra especifica para o acessorio."
    elif ncm == "73151900" and "EMENDA" in descricao:
        motivo = "Parte de corrente, NCM 73151900, nao equivale a correntes completas dos CEST 01.111.00/01.112.00."
        acao = "Conferir XML, CEST e fundamento do tratamento ST declarado pelo fornecedor."
    elif ncm == "85444200" and "CABO" in descricao:
        motivo = "Cabo de bateria nao e automaticamente jogo de fios NCM 85443000/CEST 01.073.00."
        acao = "Conferir XML e CFOP do fornecedor; conciliar CFOP de entrada, retenção e eventual GNRE."
    elif ncm == "90328989" and "INCLINACAO" in descricao:
        motivo = "CEST 01.101.00 exige regulacao de grandeza nao eletrica; detectar queda pode ser funcao diferente."
        acao = "Conferir ficha tecnica, funcao e XML/CEST/ST da operacao."
    elif ncm == "90328990" and "CDI" in descricao:
        motivo = "Funcao de modulo CDI deve ser confrontada com CEST 01.101.00; NCM isolado nao basta."
        acao = "Conferir NCM/ficha do fabricante, CEST/CST e eventual ST anterior na NF-e."
    else:
        motivo = "Alerta ST condicional sem confirmacao de produto, funcao e fundamento legal especifico."
        acao = "Conferir NCM + descricao legal + XML/CEST/CFOP/CST e responsabilidade antes de aprovar."
    if "1403" in cfops or "2403" in cfops:
        acao += " CFOP de entrada indica ST: nao concluir apenas pela escrituracao."
    return DOCUMENTAL, motivo, acao
