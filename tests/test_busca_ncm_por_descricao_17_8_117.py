from src.services.ncm_descricao_service import NCMDescricaoService
from src.ui.janela_ficha_tributaria import JanelaFichaTributaria


class _VarFalsa:
    def __init__(self, valor: str):
        self.valor = valor

    def get(self) -> str:
        return self.valor


def test_abracadeira_com_acento_retorna_candidatos_comerciais_sem_falso_erro():
    candidatos = NCMDescricaoService.pesquisar("abraçadeira", limite=20)
    ncms = [ncm for ncm, _descricao in candidatos]
    assert "73269090" in ncms
    assert "39269090" in ncms


def test_abracadeira_plastica_reduz_para_candidato_de_plastico():
    candidatos = NCMDescricaoService.pesquisar("abraçadeira plástica", limite=20)
    ncms = [ncm for ncm, _descricao in candidatos]
    assert ncms == ["39269090"]


def test_abracadeira_inox_reduz_para_candidato_metalico():
    candidatos = NCMDescricaoService.pesquisar("abraçadeira inox", limite=20)
    ncms = [ncm for ncm, _descricao in candidatos]
    assert ncms == ["73269090"]


def test_ficha_resolve_descricao_sem_exigir_codigo_de_oito_digitos():
    janela = object.__new__(JanelaFichaTributaria)
    janela.pesquisa_var = _VarFalsa("abraçadeira plástica")
    assert janela._resolver_ncm() == "39269090"


def test_busca_oficial_continua_encontrando_pastilha_de_freio():
    candidatos = NCMDescricaoService.pesquisar("pastilha freio", limite=30)
    assert any(ncm == "68138110" for ncm, _descricao in candidatos)


def test_adaptador_retrovisor_retorna_candidatos_sem_reaproveitar_parafuso():
    candidatos = NCMDescricaoService.pesquisar("ADAPTADOR RETROVISOR", limite=20)
    ncms = [ncm for ncm, _descricao in candidatos]
    assert "87141000" in ncms
    assert "73181500" not in ncms
    assert len(ncms) >= 2


def test_adaptador_espelho_tambem_retorna_candidatos_comerciais():
    candidatos = NCMDescricaoService.pesquisar("adaptador espelho", limite=20)
    ncms = [ncm for ncm, _descricao in candidatos]
    assert "87141000" in ncms
    assert len(ncms) >= 2


def test_borracha_fix_tanque_retorna_candidatos_sem_forcar_um_ncm():
    candidatos = NCMDescricaoService.pesquisar("BORRACHA FIX TANQUE", limite=20)
    ncms = [ncm for ncm, _descricao in candidatos]
    assert "40169990" in ncms
    assert "87141000" in ncms


def test_borracha_fiz_tanque_tolera_erro_de_digitacao_comum():
    candidatos = NCMDescricaoService.pesquisar("BORRACHA FIZ TANQUE", limite=20)
    ncms = [ncm for ncm, _descricao in candidatos]
    assert "40169990" in ncms
    assert "87141000" in ncms
