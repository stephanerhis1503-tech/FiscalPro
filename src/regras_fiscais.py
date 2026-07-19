from dataclasses import dataclass


@dataclass
class RegraFiscal:

    codigo: str
    titulo: str
    descricao: str
    causa: str
    correcao: str
    gravidade: str
    corrige_automaticamente: bool


REGRAS = {

    "FP001": RegraFiscal(
        codigo="FP001",
        titulo="CFOP incompatível",
        descricao="CFOP incompatível com a operação escriturada.",
        causa="Natureza da operação cadastrada incorretamente.",
        correcao="Revisar a Natureza de Operação no Digisat e reescriturar a nota.",
        gravidade="Alta",
        corrige_automaticamente=False
    ),

    "FP002": RegraFiscal(
        codigo="FP002",
        titulo="NCM divergente",
        descricao="O NCM escriturado diverge do cadastro ou do XML.",
        causa="Cadastro do produto desatualizado.",
        correcao="Atualizar o cadastro do produto e gerar novamente o SPED.",
        gravidade="Alta",
        corrige_automaticamente=False
    ),

    "FP003": RegraFiscal(
        codigo="FP003",
        titulo="ICMS-ST ausente",
        descricao="Produto sujeito à ST sem escrituração correspondente.",
        causa="Regra tributária não aplicada.",
        correcao="Revisar tributação do produto e reescriturar a nota.",
        gravidade="Alta",
        corrige_automaticamente=False
    ),

    "FP004": RegraFiscal(
        codigo="FP004",
        titulo="Cadastro 0200 inconsistente",
        descricao="Produto sem cadastro válido no Registro 0200.",
        causa="Cadastro incompleto.",
        correcao="Completar o cadastro do produto.",
        gravidade="Média",
        corrige_automaticamente=True
    )

}