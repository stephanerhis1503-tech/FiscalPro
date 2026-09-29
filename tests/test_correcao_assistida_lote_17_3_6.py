from src.sped.corretor_assistido import PropostaCorrecaoAssistida, ResultadoPreparacaoAssistida


def _p(identificador, *, sugerido="", tipo="CAMPO", linha=1, indice=1, segura=False, modo="Sugestão para confirmar"):
    return PropostaCorrecaoAssistida(
        identificador=identificador,
        selecionada=False,
        modo=modo,
        nivel="ERRO",
        categoria="Teste",
        registro="C170",
        numero_linha=linha,
        campo="VL_PIS",
        valor_atual="0,00",
        valor_sugerido=sugerido,
        justificativa="teste",
        indice_campo=indice,
        editavel=True,
        segura=segura,
        tipo_acao=tipo,
    )


def test_marcar_todas_aplicaveis_nao_marca_sem_valor():
    resultado = ResultadoPreparacaoAssistida([
        _p(1, sugerido="4,59", segura=False),
        _p(2, sugerido="21,12", segura=True),
        _p(3, sugerido="", modo="Preencher manualmente"),
        _p(4, sugerido="", linha=None, indice=None, modo="Somente revisão"),
    ])
    total = resultado.marcar_todas_aplicaveis()
    assert total == 2
    assert [p.selecionada for p in resultado.propostas] == [True, True, False, False]


def test_marcar_todas_aplicaveis_inclui_acoes_estruturais():
    estrutural = _p(1, sugerido="Recalcular", tipo="TOTALIZADORES", linha=None, indice=None, segura=True, modo="Automática segura")
    resultado = ResultadoPreparacaoAssistida([estrutural])
    assert resultado.marcar_todas_aplicaveis() == 1
    assert estrutural.selecionada is True
