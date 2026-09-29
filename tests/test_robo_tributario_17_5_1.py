from src.inteligencia.consulta_tributaria import ConsultaTributaria
from src.inteligencia.ficha_tributaria import FichaTributaria
from src.services.robo_tributario_service import RoboTributarioService


def consulta(**kwargs):
    dados = dict(
        ncm="40114000",
        descricao_produto="Pneu novo para motocicleta",
        uf_origem="MG",
        uf_destino="MG",
        regime="Lucro Real",
        operacao="Venda",
        consumidor_final=True,
        finalidade="Revenda",
        perfil_remetente="Comerciante",
        situacao_icms_st="Não informado",
    )
    dados.update(kwargs)
    return ConsultaTributaria(**dados)


def ficha_pneu():
    ficha = FichaTributaria(ncm="40114000", descricao="PNEUS NOVOS PARA MOTOCICLETAS")
    ficha.pis_cst = "04"
    ficha.cofins_cst = "04"
    ficha.aliquota_pis = 0.0
    ficha.aliquota_cofins = 0.0
    ficha.piscofins_status = "CONFIRMADO — MONOFÁSICO"
    ficha.piscofins_confirmado = True
    ficha.piscofins_exige_revisao = False
    ficha.piscofins_confiabilidade = 100.0
    ficha.icms_mg_aliquota_status = "PADRÃO RESIDUAL — REVISAR EXCEÇÕES DO ANEXO I"
    ficha.icms_mg_confirmado = False
    ficha.icms_mg_confiabilidade = 70.0
    ficha.icms_mg_aliquota_nominal = 18.0
    ficha.icms_mg_fundamento = "RICMS/MG/2023, Anexo I"
    ficha.icms_mg_st_status = "CONFIRMADO — ICMS-ST MG"
    ficha.icms_mg_st_confirmado = True
    ficha.icms_mg_cest = "16.003.00"
    ficha.icms_mg_mva = 60.0
    ficha.reforma_status = "CENÁRIO PADRÃO 2026"
    ficha.cst_ibs = "000"
    ficha.cst_cbs = "000"
    ficha.aliquota_ibs = 0.10
    ficha.aliquota_cbs = 0.90
    return ficha


def diagnostico(resultado, tributo):
    return next(d for d in resultado.diagnosticos if d.tributo == tributo)


def test_st_retido_na_entrada_transforma_icms_em_saida_sem_destaque_cst_060():
    resultado = RoboTributarioService.avaliar_ficha(
        consulta(situacao_icms_st="ICMS-ST já retido na entrada"),
        ficha_pneu(),
    )
    icms = diagnostico(resultado, "ICMS")
    st = diagnostico(resultado, "ICMS-ST")
    assert icms.status == "CONFIRMADO"
    assert icms.confiabilidade == 100.0
    assert "sem destaque do ICMS" in icms.resumo
    assert "CST 060" in icms.resumo
    assert "alíquota nominal não aplicada como débito" in icms.resumo
    assert "art. 27" in icms.fundamento
    assert st.status == "CONFIRMADO"
    assert "não há nova retenção" in st.resumo
    assert "MVA: 60.00%" in st.resumo


def test_st_retido_na_entrada_no_simples_indica_csosn_500():
    resultado = RoboTributarioService.avaliar_ficha(
        consulta(regime="Simples Nacional", situacao_icms_st="ICMS-ST já retido na entrada"),
        ficha_pneu(),
    )
    icms = diagnostico(resultado, "ICMS")
    assert "CSOSN 500" in icms.resumo
    assert "CST 060" not in icms.resumo


def test_produto_st_sem_situacao_informada_nao_confunde_enquadramento_com_recolhimento():
    resultado = RoboTributarioService.avaliar_ficha(consulta(), ficha_pneu())
    icms = diagnostico(resultado, "ICMS")
    st = diagnostico(resultado, "ICMS-ST")
    assert icms.status == "REVISAR"
    assert st.status == "REVISAR"
    assert "responsabilidade pela retenção ainda não informada" in st.resumo
    assert any("situação da retenção não foi informada" in a for a in resultado.alertas)


def test_produto_st_marcado_sem_retencao_exige_excecao():
    resultado = RoboTributarioService.avaliar_ficha(
        consulta(situacao_icms_st="Mercadoria sem retenção de ICMS-ST"),
        ficha_pneu(),
    )
    assert diagnostico(resultado, "ICMS").status == "REVISAR"
    assert diagnostico(resultado, "ICMS-ST").status == "REVISAR"
    assert any("exceção legal" in a for a in resultado.alertas)


def test_substituto_informado_mantem_icms_proprio_separado_da_st():
    ficha = ficha_pneu()
    ficha.icms_mg_aliquota_status = "CONFIRMADA — ALÍQUOTA INTERNA"
    ficha.icms_mg_confirmado = True
    ficha.icms_mg_confiabilidade = 100.0
    resultado = RoboTributarioService.avaliar_ficha(
        consulta(situacao_icms_st="Responsável por reter ICMS-ST nesta saída"),
        ficha,
    )
    icms = diagnostico(resultado, "ICMS")
    st = diagnostico(resultado, "ICMS-ST")
    assert icms.status == "CONFIRMADO"
    assert "ICMS-ST informado para retenção nesta saída" in icms.resumo
    assert st.status == "CONFIRMADO"
    assert "responsabilidade de retenção informada para esta saída" in st.resumo


def test_fora_de_venda_interna_nao_aplica_automaticamente_cst_060():
    resultado = RoboTributarioService.avaliar_ficha(
        consulta(
            uf_destino="SP",
            situacao_icms_st="ICMS-ST já retido na entrada",
        ),
        ficha_pneu(),
    )
    icms = diagnostico(resultado, "ICMS")
    assert "CST 060" not in icms.resumo


def test_relatorio_registra_contexto_st_e_hotfix():
    resultado = RoboTributarioService.avaliar_ficha(
        consulta(situacao_icms_st="ICMS-ST já retido na entrada"),
        ficha_pneu(),
    )
    assert "Situação ICMS-ST: ICMS-ST já retido na entrada" in resultado.relatorio
    assert "Perfil remetente: Comerciante" in resultado.relatorio
    assert "SEGURANÇA DO HOTFIX 17.5.1" in resultado.relatorio
