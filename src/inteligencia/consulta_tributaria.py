from dataclasses import dataclass


@dataclass
class ConsultaTributaria:
    ncm: str
    uf_origem: str
    uf_destino: str
    regime: str
    operacao: str
    consumidor_final: bool
    empresa: str = ""
    finalidade: str = "Revenda"
    descricao_produto: str = ""
    ex_tipi: str = ""
    data_operacao: str = ""
    perfil_remetente: str = ""
    situacao_icms_st: str = "Não informado"
    destinatario_contribuinte: bool | None = None
    mercadoria_importada: bool = False
    excecao_aliquota_importacao: bool = False

