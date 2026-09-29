"""Enquadramento oficial de ICMS-ST em Minas Gerais.

A consulta usa os segmentos estruturados da Parte 2 do Anexo VII do
RICMS/MG/2023 já sincronizados no banco local. O pacote offline preserva os
segmentos previamente validados e a Sprint 16.6 oferece atualização ampliada
para os demais capítulos que possuem MVA numérica estruturada.

O serviço cruza NCM, descrição, CEST, âmbito e MVA. A responsabilidade pelo
recolhimento em operação interestadual é tratada de forma conservadora, pois
pode depender de acordo vigente, exceções e características da operação.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository


URL_RICMS_MG_AUTOPECAS = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms_2023_seco/anexovii2023_4.html"
)
URL_RICMS_MG_MATERIAIS_CONSTRUCAO = URL_RICMS_MG_AUTOPECAS
URL_RICMS_MG_PNEUMATICOS = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms_2023_seco/anexovii2023_5.html"
)
URL_RICMS_MG_ANEXO_VII = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms2023/anexovii2023.pdf"
)
URL_RICMS_MG_RESPONSABILIDADE = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms_2023_seco/anexovii2023_2.html"
)
URL_CONSELHO_CONTRIBUINTES_25475_26 = (
    "https://www.fazenda.mg.gov.br/secretaria/conselho_contribuintes/"
    "acordaos/2026/3/25475263.pdf"
)
URL_CONSULTA_CONTRIBUINTE_143_2019 = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "consultas_contribuintes/2019/cc143_2019.html"
)

# 17.8.118 — posições conferidas nominalmente na Parte 2 do Anexo VII/MG,
# vigente na base legal consultada em 10/09/2026. Esses prefixos NÃO aparecem
# entre as mercadorias relacionadas à ST no enquadramento geral. A lista é
# propositalmente restrita: ausência na cobertura técnica local, por si só,
# continua CONDICIONAL até que o prefixo seja conferido na fonte oficial.
NCM_FORA_ST_MG_CONFIRMADOS = {
    "3506": "Colas e outros adesivos preparados",
    "6110": "Suéteres, pulôveres, cardigãs, coletes e artigos semelhantes, de malha",
}
PREFIXOS_NCM_FORA_ST_MG_CONFIRMADOS = tuple(NCM_FORA_ST_MG_CONFIRMADOS)

DESCRICAO_LEGAL_CEST_0109000 = (
    "Fitas, tiras, adesivos, autocolantes, de plástico, refletores, mesmo em rolos; "
    "placas metálicas com película de plástico refletora, próprias para colocação em "
    "carrocerias, para-choques de veículos de carga, motocicletas, ciclomotores, "
    "capacetes, bonés de agentes de trânsito e de condutores de veículos, atuando "
    "como dispositivos refletivos de segurança rodoviários"
)

APLICABILIDADE_7318_CONSTRUCAO = "CONSTRUCAO_CONGENERES"
APLICABILIDADE_7318_EXCLUSIVO_AUTOMOTIVO = "EXCLUSIVO_AUTOMOTIVO"
APLICABILIDADE_7318_PENDENTE = "PENDENTE"

FINALIDADE_AUTO_NAO_INFORMADA = "NAO_INFORMADA"
FINALIDADE_AUTO_CONFIRMADA = "AUTOPECA_CONFIRMADA"
FINALIDADE_AUTO_NEGADA = "NAO_AUTOMOTIVA"

CEST_RESIDUAL_AUTOPECAS = "01.999.00"
CEST_RESIDUAL_PORTA_A_PORTA = "28.999.00"

# UFs expressamente relacionadas nos âmbitos estruturados nesta sprint.
UFS_AMBITO_1_1: Tuple[str, ...] = (
    "AC", "AL", "AP", "AM", "BA", "DF", "MA", "MT", "PA", "PB",
    "PR", "PI", "RJ", "RR", "SP",
)
UFS_AMBITO_10_1: Tuple[str, ...] = ("AP", "BA", "ES", "PA", "PR", "RJ", "RS", "SP")
UFS_AMBITO_10_2: Tuple[str, ...] = ("DF",)
UFS_AMBITO_16_1: Tuple[str, ...] = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS",
    "RO", "RR", "SC", "SP", "SE", "TO",
)
UFS_AMBITO_16_2: Tuple[str, ...] = ("BA", "PR", "RJ", "SC", "SP")

METADADOS_SEGMENTOS: Dict[str, Dict[str, str]] = {
    "AUTOPEÇAS": {
        "fonte_codigo": "SEF_MG_ST_AUTOPECAS",
        "fonte_url": URL_RICMS_MG_AUTOPECAS,
        "fundamento": "RICMS/MG/2023 — Anexo VII, Parte 2, Segmento 1 — Autopeças",
    },
    "MATERIAIS DE CONSTRUÇÃO E CONGÊNERES": {
        "fonte_codigo": "SEF_MG_ST_MATERIAIS_CONSTRUCAO",
        "fonte_url": URL_RICMS_MG_MATERIAIS_CONSTRUCAO,
        "fundamento": (
            "RICMS/MG/2023 — Anexo VII, Parte 2, Segmento 10 — "
            "Materiais de construção e congêneres"
        ),
    },
    "PNEUMÁTICOS": {
        "fonte_codigo": "SEF_MG_ST_PNEUMATICOS",
        "fonte_url": URL_RICMS_MG_PNEUMATICOS,
        "fundamento": (
            "RICMS/MG/2023 — Anexo VII, Parte 2, Segmento 16 — "
            "Pneumáticos, câmaras de ar e protetores de borracha"
        ),
    },
}


@dataclass(frozen=True)
class ResultadoICMSSTMG:
    ncm: str
    status: str
    encontrado: bool
    confirmado: bool
    exige_revisao: bool
    item: str = ""
    cest: str = ""
    ncm_legal: str = ""
    descricao_legal: str = ""
    segmento: str = ""
    ambito: str = ""
    mva_original: Optional[float] = None
    aplicacao_operacao: str = ""
    responsabilidade: str = ""
    fundamento: str = "RICMS/MG/2023 — Anexo VII, Parte 2"
    artigo_item: str = ""
    fonte_codigo: str = "SEF_MG_ST"
    fonte_url: str = ""
    fundamento_complementar: str = ""
    fonte_complementar_url: str = ""
    aplicabilidade_segmento: str = ""
    nao_aplicavel: bool = False
    observacao: str = ""
    candidatos: int = 0
    uf_origem: str = ""
    uf_destino: str = ""
    potencial: bool = False
    decisao_st: str = "CONDICIONAL"
    finalidade_automotiva: str = FINALIDADE_AUTO_NAO_INFORMADA
    cest_sugerido: str = ""
    mva_sugerida: Optional[float] = None
    mva_texto: str = ""
    base_st_completa: bool = False
    base_st_atualizada_em: str = ""
    base_st_referencia: str = ""

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ICMSSTMGService:
    """Consulta a cópia oficial sincronizada dos segmentos de ST/MG."""

    @staticmethod
    def _normalizar_ncm(valor: Any) -> str:
        codigo = "".join(c for c in str(valor or "") if c.isdigit())
        if len(codigo) != 8:
            raise ValueError("O NCM deve possuir 8 dígitos.")
        return codigo

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return " ".join(texto.split())

    @staticmethod
    def _normalizar_token_descricao(palavra: str) -> str:
        """Reduz variações simples sem transformar a comparação em busca livre.

        A base legal usa muito plural (``pastilhas``, ``freios``,
        ``interruptores``), enquanto XML/cadastro costuma vir no singular. O
        motor anterior tratava essas formas como palavras diferentes.
        """
        token = str(palavra or "").strip(".,;:()[]{}\"'")
        if len(token) > 6 and token.endswith("ORES"):
            token = token[:-2]  # INTERRUPTORES -> INTERRUPTOR; MOTORES -> MOTOR
        elif len(token) > 4 and token.endswith("S"):
            token = token[:-1]  # PASTILHAS -> PASTILHA; FREIOS -> FREIO
        aliases = {
            "MANGUEIRA": "TUBO",
            "MANGUEIRAS": "TUBO",
            "CAB": "CABO",
            "MOT": "MOTOR",
            "PART": "PARTIDA",
            "BAT": "BATERIA",
            "POS": "POSITIVO",
            "FIACAO": "FIO",
            "FIOS": "FIO",
            "INTER": "INTERRUPTOR",
        }
        return aliases.get(token, token)

    @classmethod
    def _tokens(cls, valor: Any) -> set[str]:
        ignorar = {
            "A", "AS", "O", "OS", "DE", "DA", "DAS", "DO", "DOS", "E", "EM",
            "PARA", "POR", "COM", "SEM", "OU", "OUTRO", "OUTRA", "PARTE",
            "VEICULO", "AUTOMOTOR", "PRODUTO",
        }
        tokens: set[str] = set()
        for palavra in re.findall(r"[A-Z0-9]+", cls._normalizar_texto(valor)):
            token = cls._normalizar_token_descricao(palavra)
            if len(token) >= 3 and token not in ignorar:
                tokens.add(token)
        return tokens

    @classmethod
    def _aderencia_descricao(cls, descricao_produto: str, descricao_legal: str) -> float:
        produto = cls._tokens(descricao_produto)
        legal = cls._tokens(descricao_legal)
        if not produto or not legal:
            return 0.0
        intersecao = produto & legal
        return len(intersecao) / max(1, min(len(produto), len(legal)))

    @classmethod
    def _selecionar_candidato(
        cls,
        candidatos: Sequence[Dict[str, Any]],
        descricao: str,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        if not candidatos:
            return None, False

        maior_especificidade = max(len(str(item.get("ncm_digitos") or "")) for item in candidatos)
        especificos = [
            item for item in candidatos
            if len(str(item.get("ncm_digitos") or "")) == maior_especificidade
        ]
        if len(especificos) == 1:
            return dict(especificos[0]), False

        pontuados = sorted(
            [
                (
                    cls._aderencia_descricao(descricao, str(item.get("descricao") or "")),
                    str(item.get("cest") or ""),
                    dict(item),
                )
                for item in especificos
            ],
            reverse=True,
        )
        if not pontuados:
            return None, True
        melhor = pontuados[0]
        empate = len(pontuados) > 1 and abs(melhor[0] - pontuados[1][0]) < 0.001
        return melhor[2], empate

    @staticmethod
    def _origem_abrangida(ambito: str, origem: str) -> bool:
        codigos = set(re.findall(r"\d{1,2}\.\d", str(ambito or "")))
        if "1.1" in codigos and origem in UFS_AMBITO_1_1:
            return True
        if "10.1" in codigos and origem in UFS_AMBITO_10_1:
            return True
        if "10.2" in codigos and origem in UFS_AMBITO_10_2:
            return True
        if "16.1" in codigos and origem in UFS_AMBITO_16_1:
            return True
        if "16.2" in codigos and origem in UFS_AMBITO_16_2:
            return True
        return False

    @classmethod
    def _descricao_compativel_7318(cls, descricao: str) -> bool:
        texto = cls._normalizar_texto(descricao)
        raizes = (
            "PARAFUS", "PINO", "PERNO", "PORCA", "TIRA-FUNDO",
            "TIRAFUNDO", "GANCHO ROSC", "REBITE", "CHAVETA",
            "CONTRAPINO", "ARRUELA", "ANILHA",
        )
        return any(raiz in texto for raiz in raizes)

    @staticmethod
    def _normalizar_aplicabilidade_7318(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        aliases_construcao = {
            "SIM", "CONSTRUCAO", "CONSTRUÇÃO", "CONSTRUCAO_CONGENERES",
            "CONSTRUÇÃO E CONGÊNERES", "PASSIVEL_CONSTRUCAO",
        }
        aliases_auto = {
            "NAO", "NÃO", "AUTO", "AUTOMOTIVO", "EXCLUSIVO_AUTOMOTIVO",
            "USO EXCLUSIVAMENTE AUTOMOTIVO",
        }
        if texto in aliases_construcao:
            return APLICABILIDADE_7318_CONSTRUCAO
        if texto in aliases_auto:
            return APLICABILIDADE_7318_EXCLUSIVO_AUTOMOTIVO
        return APLICABILIDADE_7318_PENDENTE

    @classmethod
    def _normalizar_finalidade_automotiva(cls, valor: Any) -> str:
        texto = cls._normalizar_texto(valor)
        if texto in {
            "SIM", "AUTOPECA", "AUTOMOTIVA", "AUTOMOTIVO", "MOTO",
            "PECA DE MOTO", "PECA/COMPONENTE/ACESSORIO DE MOTO",
            "PECA COMPONENTE ACESSORIO DE MOTO", "AUTOPECA CONFIRMADA",
            "AUTOPECA_CONFIRMADA",
        }:
            return FINALIDADE_AUTO_CONFIRMADA
        if texto in {
            "NAO", "NAO AUTOMOTIVA", "NAO AUTOMOTIVO",
            "NAO E PECA AUTOMOTIVA", "FORA DO SETOR AUTOMOTIVO", "NAO_AUTOMOTIVA",
        }:
            return FINALIDADE_AUTO_NEGADA
        return FINALIDADE_AUTO_NAO_INFORMADA

    @classmethod
    def _descricao_indica_finalidade_automotiva(cls, descricao: str) -> bool:
        return cls.inferir_finalidade_automotiva(descricao) == FINALIDADE_AUTO_CONFIRMADA

    @classmethod
    def inferir_finalidade_automotiva(cls, descricao: str, cest: str = "") -> str:
        """Reconhece descrições objetivas de peças de moto sem usar só o NCM.

        Catálogos e XMLs costumam abreviar ``cabo do motor de partida`` como
        ``CAB.MOT.PART.`` e identificar a aplicação apenas pelo modelo da moto.
        A inferência exige uma pista de componente e uma pista de motocicleta;
        descrições genéricas continuam condicionais.
        """
        texto = re.sub(r"[^A-Z0-9]+", " ", cls._normalizar_texto(descricao)).strip()
        cest_digitos = "".join(c for c in str(cest or "") if c.isdigit())
        if not texto:
            return FINALIDADE_AUTO_NAO_INFORMADA

        pistas_explicitas = (
            "MOTO", "MOTOCIC", "MOTOR DE PARTIDA", "MOT PART", "ARRANQUE",
            "GUIDAO", "CARBURADOR", "INJECAO ELETRONICA", "AUTOPECA",
        )
        if any(pista in texto for pista in pistas_explicitas):
            return FINALIDADE_AUTO_CONFIRMADA

        # 17.8.127 — alguns itens de moto chegam no XML sem modelo da motocicleta
        # e sem CEST, mas a própria descrição comercial comprova a função. Não
        # usamos apenas a palavra "TAMPA" ou "VALVULA", pois seriam genéricas;
        # a confirmação exige uma combinação típica de válvula de pneu/roda.
        tampa_valvula = "TAMPA VALVULA" in texto
        pista_valvula_pneu = any(
            pista in texto for pista in ("BUTYL", "ALUM", "PNEU", "BICO", "RODA")
        )
        if tampa_valvula and pista_valvula_pneu:
            return FINALIDADE_AUTO_CONFIRMADA

        componentes = (
            "TRAVA", "FECHADURA", "CAB ", "CABO", "FIACAO", "CHICOTE",
            "INTERRUP", "SENSOR", "ESCOVA", "BATERIA", "BAT POS", "FAROL",
            "LANTERNA", "MANETE", "PEDAL", "PISCA", "RETROVISOR",
        )
        modelos_moto = (
            "BIZ", "CG ", "TITAN", "FAN", "BROS", "POP ", "XRE", "CB ",
            "CBR", "FAZER", "FACTOR", "YBR", "LANDER", "CROSSER", "XTZ",
            "YS ", "NXR", "NX ", "PCX", "LEAD", "SAHARA", "TWISTER",
        )
        componente = any(pista in f"{texto} " for pista in componentes)
        modelo = any(pista in f"{texto} " for pista in modelos_moto)
        if componente and (modelo or cest_digitos == "0199900"):
            return FINALIDADE_AUTO_CONFIRMADA
        return FINALIDADE_AUTO_NAO_INFORMADA


    @classmethod
    def _descricao_indica_filtro_ar_motor_completo(cls, descricao: str) -> bool:
        """Reconhece filtro completo de entrada de ar do motor.

        Evita tratar como ``8421.9`` (partes) mercadorias cuja descrição identifica
        o aparelho completo de filtragem de ar para motor. A regra é deliberadamente
        restrita: exige a ideia de FILTRO + AR e alguma pista objetiva de aplicação
        em motor/veículo/motocicleta.
        """
        texto = re.sub(r"[^A-Z0-9]+", " ", cls._normalizar_texto(descricao)).strip()
        if not texto or "FILTRO" not in texto or "AR" not in texto:
            return False
        pistas_motor = (
            "MOTOR", "MOTO", "MOTOCIC", "TITAN", "FAN", "BROS",
            "BIZ", "CG ", "XRE", "CB ", "FAZER", "FACTOR",
            "YBR", "LANDER", "CROSSER", "XTZ", "PCX", "TWISTER",
        )
        return any(pista in f"{texto} " for pista in pistas_motor)

    @classmethod
    def _descricao_indica_consumivel(cls, descricao: str) -> bool:
        texto = cls._normalizar_texto(descricao)
        if not texto:
            return False
        consumiveis = (
            "COLA", "ADESIVO", "SELANTE", "TINTA", "VERNIZ", "SOLVENTE",
            "LUBRIFICANTE", "GRAXA", "FLUIDO", "OLEO", "DESENGRIPANTE",
            "LIMPA ", "LIMPEZA", "DETERGENTE", "SHAMPOO", "SPRAY",
        )
        return any(termo in f"{texto} " for termo in consumiveis)

    @classmethod
    def _descricao_compativel_residual_autopecas(cls, descricao: str) -> bool:
        """Valida se o item 999.0 descreve de fato peça/parte/acessório.

        O CEST 01.999.00 não é um curinga para qualquer mercadoria utilizada em
        motocicleta. Consumíveis e materiais (cola, tinta, graxa, fluidos etc.)
        não podem ser convertidos em autopeça só porque a finalidade automotiva
        foi selecionada na tela.
        """
        texto = cls._normalizar_texto(descricao)
        if not texto or cls._descricao_indica_consumivel(texto):
            return False

        pistas_peca = (
            "PECA", "COMPONENTE", "ACESSORIO", "CABO", "CAB.", "CHICOTE", "FIACAO",
            "SENSOR", "ESCOVA", "BATERIA", "FAROL", "LANTERNA", "MANETE",
            "PEDAL", "PISCA", "RETROVISOR", "FECHADURA", "TRAVA", "MOLA",
            "ANEL", "BUCHA", "SUPORTE", "TAMPA", "PORCA", "PARAFUS",
            "ROLAMENTO", "CORRENTE", "ENGRENAGEM", "ESTATOR", "REGULADOR",
            "RELE", "INTERRUP", "BOMBA", "VALVULA", "JUNTA", "EIXO",
        )
        return any(pista in texto for pista in pistas_peca)

    @staticmethod
    def _item_residual_autopecas(codigo: str, descricao_legal: str) -> Dict[str, Any]:
        return {
            "item": "999.0",
            "cest": "01.999.00",
            "ncm_digitos": codigo,
            "ncm_formatado": codigo,
            "descricao": descricao_legal,
            "segmento": "AUTOPEÇAS",
            "ambito": "1.2",
            "mva": 71.78,
            "fonte_codigo": "SEF_MG_ST_AUTOPECAS",
        }

    @classmethod
    def _classificar_adesivo_391990(cls, descricao: str) -> str:
        """Classifica a aderência do NCM 3919.90 ao CEST 01.090.00.

        O item 90.0 do segmento de autopeças não alcança qualquer adesivo de
        plástico. A própria descrição legal restringe o CEST aos materiais
        *refletivos* que atuem como dispositivos de segurança rodoviária.
        A Consulta de Contribuinte 143/2019 da SEF/MG reforça que a coincidência
        do NCM, sem correspondência da descrição/finalidade, não sujeita o item à ST.

        Retornos:
        - REFLETIVO: descrição traz indicação objetiva de material refletivo;
        - DECORATIVO: descrição traz sinais fortes de kit/grafismo decorativo de moto;
        - PENDENTE: descrição insuficiente para decidir com segurança.
        """
        texto = re.sub(r"[^A-Z0-9]+", " ", cls._normalizar_texto(descricao)).strip()
        if not texto:
            return "PENDENTE"

        # A raiz REFLET cobre refletivo/refletora/refletores. Quando presente,
        # prevalece sobre palavras como KIT ou FAIXA, pois há kits refletivos.
        if "REFLET" in texto:
            return "REFLETIVO"

        sinais_decorativos = (
            "DECORAT", "GRAFISMO", "GRAFICO", "KIT ADESIVO", "ADESIVO KIT",
            "TANQUE", "CARENAGEM", "LATERAL", "RABETA", "PARALAMA",
        )
        modelos_moto = (
            "BIZ", "CG ", "TITAN", "FAN", "BROS", "POP ", "XRE", "CB ",
            "CBR", "FAZER", "FACTOR", "YBR", "LANDER", "CROSSER", "XTZ",
            "NXR", "PCX", "LEAD", "SAHARA", "TWISTER",
        )
        cores = (
            "PRATA", "PRETO", "PRETA", "BRANCO", "BRANCA", "VERMELHO",
            "VERMELHA", "AZUL", "VERDE", "AMARELO", "AMARELA", "DOURADO",
            "DOURADA", "CINZA", "ROSA", "LARANJA",
        )

        decorativo = any(x in texto for x in sinais_decorativos)
        kit_modelo = "KIT" in texto and any(x in f"{texto} " for x in modelos_moto)
        cor_modelo = any(x in texto for x in cores) and any(x in f"{texto} " for x in modelos_moto)
        if decorativo or kit_modelo or cor_modelo:
            return "DECORATIVO"
        return "PENDENTE"

    @classmethod
    def _resultado_391990_decorativo(
        cls, codigo: str, origem: str, destino: str, descricao: str
    ) -> Dict[str, Any]:
        return ResultadoICMSSTMG(
            ncm=codigo,
            status="NÃO APLICÁVEL — CEST 01.090.00 EXIGE ADESIVO REFLETIVO DE SEGURANÇA",
            encontrado=True,
            confirmado=False,
            exige_revisao=False,
            item="90.0",
            cest="",
            ncm_legal="3919.90",
            descricao_legal=DESCRICAO_LEGAL_CEST_0109000,
            segmento="AUTOPEÇAS",
            ambito="1.1",
            mva_original=None,
            aplicacao_operacao=(
                "NÃO APLICÁVEL AO ITEM 90.0 — descrição indica kit/adesivo decorativo "
                "e não dispositivo refletivo de segurança rodoviária"
            ),
            fundamento="RICMS/MG/2023 — Anexo VII, Parte 2, Segmento 1 — Autopeças",
            artigo_item="Parte 2, segmento 1, item 90.0, CEST 01.090.00 (não aplicável à descrição)",
            fonte_codigo="SEF_MG_ST_AUTOPECAS",
            fonte_url=URL_RICMS_MG_AUTOPECAS,
            fundamento_complementar=(
                "SEF/MG — Consulta de Contribuinte nº 143/2019: a coincidência do NCM 3919 "
                "não basta; o produto deve corresponder à descrição legal. Mercadoria que não "
                "atua como dispositivo refletivo de segurança rodoviária não se enquadra no item 90.0."
            ),
            fonte_complementar_url=URL_CONSULTA_CONTRIBUINTE_143_2019,
            aplicabilidade_segmento="DESCRICAO_FORA_CEST_0109000",
            nao_aplicavel=True,
            observacao=(
                f"A descrição '{descricao}' indica adesivo/kit decorativo para motocicleta. "
                "O CEST 01.090.00 alcança apenas fitas, tiras, adesivos e autocolantes refletores "
                "que atuem como dispositivos refletivos de segurança rodoviária. Não aplicar a "
                "MVA de 71,78% deste CEST. O CEST residual 01.999.00 também não deve ser aplicado "
                "automaticamente: no RICMS/MG ele depende da hipótese específica de regime especial "
                "entre fabricante/importador e concessionário da rede de distribuição."
            ),
            candidatos=1,
            uf_origem=origem,
            uf_destino=destino,
            potencial=False,
            decisao_st="NAO",
            finalidade_automotiva=FINALIDADE_AUTO_CONFIRMADA,
            cest_sugerido="",
            mva_sugerida=None,
        ).para_dict()

    @classmethod
    def _resultado_391990_pendente(
        cls, codigo: str, origem: str, destino: str, descricao: str
    ) -> Dict[str, Any]:
        return ResultadoICMSSTMG(
            ncm=codigo,
            status="CONDICIONAL — CONFIRMAR SE O ADESIVO É REFLETIVO DE SEGURANÇA",
            encontrado=True,
            confirmado=False,
            exige_revisao=True,
            item="90.0",
            cest="",
            ncm_legal="3919.90",
            descricao_legal=DESCRICAO_LEGAL_CEST_0109000,
            segmento="AUTOPEÇAS",
            ambito="1.1",
            mva_original=None,
            aplicacao_operacao="DESCRIÇÃO INSUFICIENTE PARA APLICAR O CEST 01.090.00",
            fundamento="RICMS/MG/2023 — Anexo VII, Parte 2, Segmento 1 — Autopeças",
            artigo_item="Parte 2, segmento 1, item 90.0, CEST 01.090.00 (condicional à descrição)",
            fonte_codigo="SEF_MG_ST_AUTOPECAS",
            fonte_url=URL_RICMS_MG_AUTOPECAS,
            fundamento_complementar=(
                "SEF/MG — Consulta de Contribuinte nº 143/2019: o NCM isolado não basta; "
                "é necessário que a mercadoria corresponda à descrição legal do item."
            ),
            fonte_complementar_url=URL_CONSULTA_CONTRIBUINTE_143_2019,
            aplicabilidade_segmento="CONFIRMAR_REFLETIVIDADE_CEST_0109000",
            nao_aplicavel=False,
            observacao=(
                "O NCM 3919.90 aparece no item 90.0, mas o CEST 01.090.00 é restrito a material "
                "refletivo que atue como dispositivo de segurança rodoviária. A descrição atual não "
                "permite confirmar nem excluir essa característica. O NCM isolado não autoriza aplicar ST/MVA. "
                "O CEST residual 01.999.00 também não deve ser presumido, pois depende da hipótese "
                "específica de regime especial prevista no RICMS/MG."
            ),
            candidatos=1,
            uf_origem=origem,
            uf_destino=destino,
            potencial=True,
            decisao_st="CONDICIONAL",
            finalidade_automotiva=FINALIDADE_AUTO_NAO_INFORMADA,
            cest_sugerido="01.090.00",
            mva_sugerida=71.78,
        ).para_dict()

    @classmethod
    def _resultado_ncm_fora_parte2_mg(
        cls,
        codigo: str,
        origem: str,
        destino: str,
        descricao: str,
        finalidade_automotiva: str,
    ) -> Dict[str, Any]:
        """Retorna NÃO quando há exclusão nominal confirmada no Anexo VII/MG.

        Diferente do fallback genérico (base local sem correspondência), este
        resultado só é usado para prefixos cuja ausência foi conferida na Parte
        2 vigente do Anexo VII. Assim, falta de cobertura técnica continua
        CONDICIONAL para os demais NCMs, mas um caso legalmente conferido não
        gera revisão falsa.
        """
        prefixo = next(
            (p for p in PREFIXOS_NCM_FORA_ST_MG_CONFIRMADOS if codigo.startswith(p)),
            codigo[:4],
        )
        descricao_posicao = NCM_FORA_ST_MG_CONFIRMADOS.get(prefixo, "Mercadoria consultada")

        return ResultadoICMSSTMG(
            ncm=codigo,
            status=f"NÃO — NCM {prefixo} SEM ENQUADRAMENTO NA PARTE 2 DO ANEXO VII/MG",
            encontrado=False,
            confirmado=False,
            exige_revisao=False,
            ncm_legal=prefixo,
            descricao_legal=descricao_posicao,
            segmento="",
            ambito="",
            mva_original=None,
            aplicacao_operacao="NÃO SUJEITO À ST/MG PELO ENQUADRAMENTO GERAL DO ANEXO VII",
            fundamento=(
                "RICMS/MG/2023 — Anexo VII, Parte 1, art. 12 e parágrafo único; "
                "Parte 2 (mercadorias relacionadas à substituição tributária)"
            ),
            artigo_item=f"Parte 2 — posição NCM {prefixo} não relacionada",
            fonte_codigo="SEF_MG_ST_ANEXO_VII",
            fonte_url=URL_RICMS_MG_ANEXO_VII,
            aplicabilidade_segmento="NCM_FORA_ANEXO_VII_PARTE_2",
            nao_aplicavel=True,
            observacao=(
                f"O NCM {codigo} ({descricao or descricao_posicao}) pertence à posição {prefixo}. "
                f"A posição {prefixo} não consta na Parte 2 do Anexo VII do RICMS/MG vigente na "
                "base legal conferida em 10/09/2026. Na regra geral de ST por mercadoria, o "
                "resultado é NÃO: sem CEST e sem MVA de ST para este enquadramento. "
                "Ressalva-se apenas eventual regime especial específico do contribuinte, que deve "
                "ser analisado separadamente quando existir."
            ),
            candidatos=0,
            uf_origem=origem,
            uf_destino=destino,
            potencial=False,
            decisao_st="NAO",
            finalidade_automotiva=finalidade_automotiva,
            cest_sugerido="",
            mva_sugerida=None,
        ).para_dict()

    @classmethod
    def _resultado_ncm_ausente_base_oficial(
        cls,
        codigo: str,
        origem: str,
        destino: str,
        descricao: str,
        finalidade_automotiva: str,
        cobertura: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Conclui NÃO ST quando a Parte 2 completa foi sincronizada.

        O resultado só é emitido com o selo de base completa da versão 2 do
        sincronizador. Regras sem NCM fechado, especialmente o residual
        01.999.00 de autopeças, são avaliadas antes desta negativa.
        """
        atualizado = str(
            cobertura.get("sincronizado_em")
            or cobertura.get("atualizado_em")
            or ""
        )
        referencia = str(
            cobertura.get("referencia")
            or "RICMS/MG/2023 — Anexo VII, Parte 2 vigente"
        )
        return ResultadoICMSSTMG(
            ncm=codigo,
            status="NÃO — NCM SEM ENQUADRAMENTO NOMINAL NA PARTE 2 DO ANEXO VII/MG",
            encontrado=False,
            confirmado=False,
            exige_revisao=False,
            ncm_legal=codigo,
            descricao_legal=descricao,
            segmento="",
            ambito="",
            mva_original=None,
            aplicacao_operacao="NÃO SUJEITO À ST/MG PELO ENQUADRAMENTO NOMINAL DA PARTE 2",
            fundamento=(
                "RICMS/MG/2023 — Anexo VII, Parte 1, art. 12 e parágrafo único; "
                "Parte 2 — mercadorias relacionadas à substituição tributária"
            ),
            artigo_item="Parte 2 — NCM não localizado na base oficial completa",
            fonte_codigo="SEF_MG_ST_COMPLETA",
            fonte_url=str(cobertura.get("fonte_url") or URL_RICMS_MG_AUTOPECAS),
            aplicabilidade_segmento="NCM_AUSENTE_BASE_OFICIAL_COMPLETA",
            nao_aplicavel=True,
            observacao=(
                f"O NCM {codigo} ({descricao or 'descrição não informada'}) não foi localizado em "
                "nenhuma linha nominal da Parte 2 do Anexo VII sincronizada integralmente. "
                "Por isso, na regra geral por mercadoria, o resultado é NÃO ST/MG, sem CEST e sem MVA. "
                "O motor avaliou antes as regras sem NCM fechado, inclusive 01.999.00 de autopeças "
                "e 28.999.00 de venda porta a porta. Permanece apenas a ressalva de eventual regime "
                "especial específico do contribuinte."
            ),
            candidatos=0,
            uf_origem=origem,
            uf_destino=destino,
            potencial=False,
            decisao_st="NAO",
            finalidade_automotiva=finalidade_automotiva,
            cest_sugerido="",
            mva_sugerida=None,
            mva_texto="",
            base_st_completa=True,
            base_st_atualizada_em=atualizado,
            base_st_referencia=referencia,
        ).para_dict()

    @classmethod
    def _operacao_porta_a_porta(cls, contexto: Dict[str, Any]) -> bool:
        if contexto.get("porta_a_porta") is True or contexto.get("marketing_direto") is True:
            return True
        texto = cls._normalizar_texto(
            " ".join(
                str(contexto.get(chave) or "")
                for chave in ("operacao", "canal_venda", "tipo_venda", "observacao_operacao")
            )
        )
        return any(
            termo in texto
            for termo in ("PORTA A PORTA", "MARKETING DIRETO", "VENDA DIRETA A CONSUMIDOR")
        )

    @staticmethod
    def _item_residual_porta_a_porta(codigo: str, descricao: str) -> Dict[str, Any]:
        return {
            "item": "999.0",
            "cest": CEST_RESIDUAL_PORTA_A_PORTA,
            "ncm_digitos": "",
            "ncm_formatado": "",
            "descricao": (
                "Outros produtos comercializados pelo sistema de marketing direto porta a porta "
                "a consumidor final não relacionados em outros itens deste capítulo"
            ),
            "segmento": "VENDA DE MERCADORIAS PELO SISTEMA PORTA A PORTA",
            "ambito": "28.1",
            "mva": 30.0,
            "mva_texto": "30%",
            "fonte_codigo": "SEF_MG_ST_COMPLETA",
            "descricao_produto": descricao,
            "ncm_produto": codigo,
        }

    @staticmethod
    def _item_0109000_refletivo(codigo: str) -> Dict[str, Any]:
        return {
            "item": "90.0",
            "cest": "01.090.00",
            "ncm_digitos": "391990",
            "ncm_formatado": "3919.90",
            "descricao": DESCRICAO_LEGAL_CEST_0109000,
            "segmento": "AUTOPEÇAS",
            "ambito": "1.1",
            "mva": 71.78,
            "fonte_codigo": "SEF_MG_ST_AUTOPECAS",
        }

    @classmethod
    def analisar(
        cls,
        ncm: Any,
        contexto: Optional[Dict[str, Any]] = None,
        descricao: str = "",
    ) -> Dict[str, Any]:
        codigo = cls._normalizar_ncm(ncm)
        contexto = contexto or {}
        origem = str(contexto.get("uf_origem") or "").strip().upper()
        destino = str(contexto.get("uf_destino") or "").strip().upper()
        aplicabilidade_7318 = cls._normalizar_aplicabilidade_7318(
            contexto.get("aplicabilidade_7318")
        )
        finalidade_automotiva = cls._normalizar_finalidade_automotiva(
            contexto.get("finalidade_automotiva")
        )
        cobertura_st = BaseOficialRepository.resumo_st_mg()
        base_st_completa = bool(
            cobertura_st.get("base_completa")
            and int(cobertura_st.get("versao_schema") or 0) >= 3
        )

        # Compatibilidade offline: antes da primeira sincronização completa da
        # 17.8.119, posições já conferidas manualmente continuam disponíveis.
        # Após o selo de base completa, a decisão passa a vir da tabela inteira.
        # 17.8.118 — decisão negativa legalmente conferida. Não confundir com
        # "NCM não encontrado na cobertura local": para os demais códigos, a
        # ausência técnica continua conservadora/condicional. Somente posições
        # presentes em NCM_FORA_ST_MG_CONFIRMADOS retornam NÃO sem CEST/MVA.
        if (
            not base_st_completa
            and codigo.startswith(PREFIXOS_NCM_FORA_ST_MG_CONFIRMADOS)
        ):
            return cls._resultado_ncm_fora_parte2_mg(
                codigo, origem, destino, descricao, finalidade_automotiva
            )

        # 17.8.84 — NCM 3919.90 / CEST 01.090.00. A legislação mineira exige
        # simultaneamente o código e a descrição de produto refletivo de segurança.
        # Um kit decorativo de motocicleta não pode virar ST apenas porque o NCM
        # coincide com a posição 3919.90. A decisão acontece antes da base local
        # para também neutralizar cadastros antigos que tratavam o NCM isoladamente.
        classificacao_391990 = ""
        if codigo.startswith("391990"):
            classificacao_391990 = cls._classificar_adesivo_391990(descricao)
            if classificacao_391990 == "DECORATIVO":
                return cls._resultado_391990_decorativo(codigo, origem, destino, descricao)
            if classificacao_391990 == "PENDENTE":
                return cls._resultado_391990_pendente(codigo, origem, destino, descricao)

        # 17.8.87 — a NCM 6506.10.00 foi desdobrada a partir de 01/02/2026.
        # Quando o produto 6506.10.90 está confirmado como capacete de motocicleta,
        # conserva-se o enquadramento material do item 13.0 / CEST 01.013.00 que
        # permanece publicado na tabela mineira sob o código anterior. A ponte só
        # é aplicada com finalidade automotiva confirmada e descrição de capacete.
        codigo_busca = codigo
        ponte_ncm_65061090 = False
        ponte_filtro_ar_motor = False
        descricao_norm = cls._normalizar_texto(descricao)

        # 17.8.126 — alguns cadastros/XMLs trazem filtro completo de entrada de ar
        # no NCM genérico de partes 8421.99.99. Quando a descrição comprova que se
        # trata do FILTRO completo aplicado ao motor, a consulta ST deve usar o
        # enquadramento material específico 8421.31.00 / CEST 01.041.00, e não
        # disputar com regras de "partes" de outros segmentos (ex.: 21.014.00).
        # O NCM original é preservado no documento e a divergência fica sinalizada
        # para revisão cadastral; apenas o enquadramento ST usa o código específico.
        if (
            codigo == "84219999"
            and cls._descricao_indica_filtro_ar_motor_completo(descricao)
        ):
            codigo_busca = "84213100"
            ponte_filtro_ar_motor = True
        descricao_capacete_moto = (
            "CAPACETE" in descricao_norm
            or (bool(re.search(r"(?:^|\s)CAP(?:\.|\s|$)", descricao_norm)) and ("MOTO" in descricao_norm or "MOTOCIC" in descricao_norm))
        )
        if (
            codigo == "65061090"
            and finalidade_automotiva == FINALIDADE_AUTO_CONFIRMADA
            and descricao_capacete_moto
            and not any(termo in descricao_norm for termo in ("BOMBEIRO", "BALISTIC", "INDUSTRIAL", "EPI"))
        ):
            codigo_busca = "65061000"
            ponte_ncm_65061090 = True

        # Pesquisa todos os segmentos já sincronizados. A seleção prioriza o
        # código NCM mais específico e depois a aderência da descrição.
        candidatos = BaseOficialRepository.buscar_st_mg_por_ncm(codigo_busca)

        # O Capítulo/Segmento 28 só alcança mercadorias comercializadas pelo
        # sistema porta a porta / marketing direto. As linhas nominais desse
        # capítulo podem usar NBM/SH muito amplo (até capítulos inteiros); sem
        # este filtro, uma venda comum de vestuário, acessórios etc. seria
        # classificada indevidamente como ST apenas por compartilhar o NCM.
        if not cls._operacao_porta_a_porta(contexto):
            candidatos = [
                item for item in candidatos
                if not str(item.get("cest") or "").startswith("28.")
            ]

        escolhido, ambiguo = cls._selecionar_candidato(candidatos, descricao)
        residual_origem = ""

        # 17.8.127 — NCM amplo pode aparecer em mais de um segmento. Se a busca
        # nominal trouxer uma regra de OUTRO segmento cuja descrição legal não
        # tenha qualquer aderência com a mercadoria, essa regra não pode bloquear
        # o residual de autopeças quando a finalidade automotiva já estiver
        # confirmada. Ex.: 7616.99.00 "TAMPA VALVULA ... ALUM" não é "obra de
        # alumínio própria para construções" só porque compartilha a posição 7616.
        # A regra nominal continua disponível quando a descrição realmente combinar.
        finalidade_inferida_descricao = cls.inferir_finalidade_automotiva(descricao)
        finalidade_auto_para_desempate = bool(
            finalidade_automotiva == FINALIDADE_AUTO_CONFIRMADA
            or (
                finalidade_automotiva == FINALIDADE_AUTO_NAO_INFORMADA
                and finalidade_inferida_descricao == FINALIDADE_AUTO_CONFIRMADA
            )
        )
        if escolhido and finalidade_auto_para_desempate:
            segmento_candidato = str(escolhido.get("segmento") or "").strip().upper()
            aderencia_candidato = cls._aderencia_descricao(
                descricao, str(escolhido.get("descricao") or "")
            )
            if (
                segmento_candidato != "AUTOPEÇAS"
                and aderencia_candidato == 0
                and cls._descricao_compativel_residual_autopecas(descricao)
            ):
                cest_descartado = str(escolhido.get("cest") or "")
                segmento_descartado = segmento_candidato or "OUTRO SEGMENTO"
                inferencia_usada = finalidade_automotiva != FINALIDADE_AUTO_CONFIRMADA
                if inferencia_usada:
                    finalidade_automotiva = FINALIDADE_AUTO_CONFIRMADA
                escolhido = cls._item_residual_autopecas(
                    codigo, str(descricao or "Peça, componente ou acessório de motocicleta")
                )
                candidatos = [escolhido]
                ambiguo = False
                origem_finalidade = (
                    "DESCRIÇÃO OBJETIVA DE PEÇA/ACESSÓRIO AUTOMOTIVO"
                    if inferencia_usada
                    else "FINALIDADE AUTOMOTIVA CONFIRMADA"
                )
                residual_origem = (
                    f"{origem_finalidade} E DESCRIÇÃO INCOMPATÍVEL COM "
                    f"O CEST {cest_descartado or 'NOMINAL'} DO SEGMENTO {segmento_descartado}"
                )

        # Se a descrição declarar expressamente que o item é refletivo, o item
        # 90.0 pode ser reconstruído da própria fonte oficial mesmo quando uma
        # base local antiga não tenha sincronizado a posição 3919.90 corretamente.
        if codigo.startswith("391990") and classificacao_391990 == "REFLETIVO" and not escolhido:
            escolhido = cls._item_0109000_refletivo(codigo)
            candidatos = [escolhido]
            ambiguo = False

        # O CEST 10.075.00 exclui expressamente as fechaduras de uso
        # automotivo. Quando essa finalidade estiver confirmada, o motor deve
        # desviar do segmento 10 para o residual de autopeças.
        descricao_candidato = cls._normalizar_texto(
            (escolhido or {}).get("descricao") if escolhido else ""
        )
        candidato_exclui_automotivo = bool(
            escolhido
            and "EXCETO" in descricao_candidato
            and "USO AUTOMOTIVO" in descricao_candidato
        )
        if candidato_exclui_automotivo and finalidade_automotiva == FINALIDADE_AUTO_CONFIRMADA:
            escolhido = cls._item_residual_autopecas(
                codigo, str(descricao or "Peça, componente ou acessório de motocicleta")
            )
            candidatos = [escolhido]
            ambiguo = False
            residual_origem = "EXCLUSÃO AUTOMOTIVA DO CEST NOMINAL E FINALIDADE CONFIRMADA"
        elif (
            candidato_exclui_automotivo
            and finalidade_automotiva == FINALIDADE_AUTO_NAO_INFORMADA
            and cls._descricao_indica_finalidade_automotiva(descricao)
        ):
            escolhido = None
            candidatos = []
            ambiguo = False

        # O item residual de autopeças (CEST 01.999.00) não possui NCM fechado.
        # Portanto, ausência na busca por NCM nunca pode virar uma conclusão
        # definitiva de "não ST". A finalidade informada pelo usuário confirma
        # o residual; a descrição apenas produz uma decisão condicional.
        residuais_autopecas = {
            "85452000": ("Escovas para motor de partida de motocicleta", ("ESCOVA",)),
            "90268000": ("Sensor híbrido destinado a motocicleta", ("HIBRID",)),
            "85444200": (
                "Cabo do motor de partida de motocicleta",
                ("PARTIDA", "ARRANQUE", "MOT.PART", "MOT PART"),
            ),
        }
        residual_bloqueado_descricao = False
        if not escolhido and finalidade_automotiva == FINALIDADE_AUTO_CONFIRMADA:
            if cls._descricao_compativel_residual_autopecas(descricao):
                descricao_residual = str(descricao or "Peça, componente ou acessório de motocicleta")
                escolhido = cls._item_residual_autopecas(codigo, descricao_residual)
                candidatos = [escolhido]
                ambiguo = False
                residual_origem = "FINALIDADE AUTOMOTIVA CONFIRMADA PELO USUÁRIO"
            else:
                # 17.8.115 — finalidade informada não transforma consumível/material
                # em "peça, parte ou acessório" do item residual 999.0.
                residual_bloqueado_descricao = True
        elif (
            not escolhido
            and finalidade_automotiva != FINALIDADE_AUTO_NEGADA
            and codigo in residuais_autopecas
        ):
            descricao_legal, pistas = residuais_autopecas[codigo]
            texto_produto = cls._normalizar_texto(descricao)
            finalidade_confirmada = bool(texto_produto) and any(
                pista in texto_produto for pista in pistas
            )
            if finalidade_confirmada:
                escolhido = cls._item_residual_autopecas(codigo, descricao_legal)
                candidatos = [escolhido]
                ambiguo = False
                residual_origem = "PRODUTO RESIDUAL VALIDADO NO MOTOR"

        # A Parte 2 também possui uma regra residual sem NCM no Capítulo 28.
        # Ela só é pertinente quando o contexto informa venda pelo sistema
        # porta a porta / marketing direto a consumidor final.
        if not escolhido and cls._operacao_porta_a_porta(contexto):
            escolhido = cls._item_residual_porta_a_porta(codigo, descricao)
            candidatos = [escolhido]
            ambiguo = False
            residual_origem = "OPERAÇÃO PORTA A PORTA/MARKETING DIRETO INFORMADA"

        if not escolhido:
            descricao_sugere_auto = cls._descricao_indica_finalidade_automotiva(descricao)

            # 17.8.119 — a ausência só é negativa depois que a Parte 2 inteira
            # foi sincronizada e validada. Antes disso, continua condicional.
            # A exceção é o residual 01.999.00, avaliado acima: se havia uma
            # peça/parte/acessório automotivo comprovado, ``escolhido`` já teria
            # sido preenchido. Quando a finalidade automotiva está negada ou a
            # descrição identifica consumível/material, o residual não se aplica.
            pode_concluir_ausencia = bool(
                base_st_completa
                and (
                    finalidade_automotiva == FINALIDADE_AUTO_NEGADA
                    or cls._descricao_indica_consumivel(descricao)
                )
            )
            if pode_concluir_ausencia:
                return cls._resultado_ncm_ausente_base_oficial(
                    codigo, origem, destino, descricao, finalidade_automotiva, cobertura_st
                )

            if residual_bloqueado_descricao:
                status = "CONDICIONAL — DESCRIÇÃO NÃO COMPROVA PEÇA/PARTE/ACESSÓRIO"
                observacao = (
                    "A finalidade automotiva foi informada, porém o CEST residual 01.999.00 alcança "
                    "outras peças, partes e acessórios para veículos automotores. A descrição do produto "
                    "não comprova que ele seja peça, parte ou acessório; por isso o FiscalPro não aplicou "
                    "o residual automaticamente. NCM/finalidade isolados não confirmam ICMS-ST."
                )
                potencial = False
                cest_sugerido = ""
                mva_sugerida = None
            elif cls._descricao_indica_consumivel(descricao):
                status = "CONDICIONAL — FORA DO RESIDUAL DE AUTOPEÇAS; REVISAR OUTROS SEGMENTOS"
                observacao = (
                    "A descrição indica consumível/material e não uma peça, parte ou acessório. Por isso o "
                    "FiscalPro não sugere o CEST residual 01.999.00. A análise permanece condicional apenas "
                    "para eventual enquadramento em outro segmento legal específico."
                )
                potencial = False
                cest_sugerido = ""
                mva_sugerida = None
            elif finalidade_automotiva == FINALIDADE_AUTO_NEGADA:
                status = "CONDICIONAL — NÃO ENQUADRADO COMO AUTOPEÇA; REVISAR OUTROS SEGMENTOS"
                observacao = (
                    "A finalidade automotiva foi negada. O CEST residual 01.999.00 não foi aplicado, "
                    "mas isso não confirma ausência de ICMS-ST em outros segmentos do Anexo VII."
                )
                potencial = False
                cest_sugerido = ""
                mva_sugerida = None
            else:
                status = "CONDICIONAL — CONFIRMAR FINALIDADE AUTOMOTIVA"
                if base_st_completa:
                    observacao = (
                        "O NCM não foi localizado na base oficial completa, mas a finalidade automotiva "
                        "ainda não foi definida e o CEST residual 01.999.00 não possui NCM fechado. "
                        "Confirme se o produto é realmente peça, parte ou acessório automotivo antes de concluir."
                    )
                else:
                    observacao = (
                        "O NCM não foi localizado nominalmente na cobertura instalada. Sem o selo de base "
                        "ST/MG completa, a ausência não pode ser usada para concluir NÃO ST. Atualize as bases "
                        "oficiais ou confirme a finalidade automotiva."
                    )
                if descricao_sugere_auto:
                    observacao += " A descrição possui indícios de uso automotivo, mas a confirmação do usuário ainda é necessária."
                potencial = True
                cest_sugerido = "01.999.00"
                mva_sugerida = 71.78
            return ResultadoICMSSTMG(
                ncm=codigo,
                status=status,
                encontrado=False,
                confirmado=False,
                exige_revisao=True,
                observacao=observacao,
                candidatos=0,
                uf_origem=origem,
                uf_destino=destino,
                potencial=potencial,
                decisao_st="CONDICIONAL",
                finalidade_automotiva=finalidade_automotiva,
                cest_sugerido=cest_sugerido,
                mva_sugerida=mva_sugerida,
                base_st_completa=base_st_completa,
                base_st_atualizada_em=str(cobertura_st.get("sincronizado_em") or cobertura_st.get("atualizado_em") or ""),
                base_st_referencia=str(cobertura_st.get("referencia") or ""),
            ).para_dict()

        if ponte_filtro_ar_motor and escolhido:
            # Mantém a fonte/documento intactos, mas explica que o enquadramento
            # específico foi escolhido pela descrição do produto completo.
            escolhido = dict(escolhido)
            escolhido["ponte_ncm_origem"] = codigo
            escolhido["ponte_ncm_sugerido"] = "84213100"

        segmento = str(escolhido.get("segmento") or "").strip().upper()
        metadados = dict(METADADOS_SEGMENTOS.get(segmento, {}))
        numero_segmento_previo = str(escolhido.get("cest") or "").split(".", 1)[0]
        if not metadados:
            metadados = {
                "fonte_codigo": str(escolhido.get("fonte_codigo") or "SEF_MG_ST_COMPLETA"),
                "fonte_url": URL_RICMS_MG_ANEXO_VII,
                "fundamento": (
                    "RICMS/MG/2023 — Anexo VII, Parte 2, Segmento "
                    f"{numero_segmento_previo or '?'} — {segmento or 'não identificado'}"
                ),
            }
        ambito = str(escolhido.get("ambito") or "").strip()
        mva = escolhido.get("mva")
        mva_texto = str(escolhido.get("mva_texto") or "").strip()
        cest = str(escolhido.get("cest") or "").strip()
        item = str(escolhido.get("item") or "").strip()
        numero_segmento = cest.split(".", 1)[0] if cest else ""
        artigo_item = f"Parte 2, segmento {numero_segmento}, item {item}, CEST {cest}"

        confirmado = False
        exige_revisao = True
        aplicacao = ""
        observacoes: List[str] = []
        if ponte_filtro_ar_motor:
            observacoes.append(
                "A descrição identifica filtro completo de entrada de ar para motor. "
                "Para o enquadramento de ICMS-ST foi utilizado o NCM específico 8421.31.00 "
                "(CEST 01.041.00), em vez do NCM 8421.99.99 de partes. Revise o cadastro/XML "
                "do produto; o FiscalPro não altera o documento fiscal de origem automaticamente."
            )
            exige_revisao = True
        if ponte_ncm_65061090:
            observacoes.append(
                "NCM 65061090 reconhecida como desdobramento vigente da antiga 65061000 para capacete de motocicleta; "
                "mantido o enquadramento material do CEST 01.013.00."
            )
        if residual_origem:
            observacoes.append(
                f"CEST residual {str(escolhido.get('cest') or '')} aplicado por {residual_origem.lower()}."
            )
        aplicabilidade_segmento = ""
        nao_aplicavel = False
        fundamento_complementar = ""
        fonte_complementar_url = ""
        responsabilidade = ""

        if destino and destino != "MG":
            aplicacao = "FORA DO ESCOPO DE MINAS GERAIS"
            observacoes.append("A tabela consultada é específica para operações com destino a Minas Gerais.")
        elif destino != "MG":
            aplicacao = "INFORME A UF DE DESTINO"
            observacoes.append("Informe MG como destino para avaliar a aplicação da tabela mineira.")
        elif origem == "MG":
            confirmado = True
            exige_revisao = ambiguo
            aplicacao = "OPERAÇÃO INTERNA EM MG"
            observacoes.append("O âmbito informado na tabela alcança a operação interna em Minas Gerais.")
        elif origem and cls._origem_abrangida(ambito, origem):
            confirmado = True
            exige_revisao = ambiguo
            aplicacao = f"OPERAÇÃO INTERESTADUAL ABRANGIDA PELO ÂMBITO {ambito}"
            responsabilidade = "REMETENTE/SUJEITO PASSIVO POR SUBSTITUIÇÃO — CONFORME ÂMBITO"
            observacoes.append(
                f"A UF de origem consta no âmbito {ambito}. Ainda devem ser conferidos sujeito passivo, "
                "exceções e condições específicas da operação."
            )
        elif origem:
            confirmado = True
            exige_revisao = ambiguo
            aplicacao = "ST DEVIDA PELO DESTINATÁRIO MG — ART. 15 DO ANEXO VII"
            responsabilidade = "DESTINATÁRIO MINEIRO — ART. 15 DO ANEXO VII"
            fundamento_complementar = (
                "RICMS/MG/2023 — Anexo VII, Parte 1, art. 15 — o contribuinte mineiro destinatário "
                "de mercadoria submetida à ST, em operação interestadual, responde pela apuração e "
                "recolhimento quando a responsabilidade não for atribuída ao alienante ou remetente."
            )
            fonte_complementar_url = URL_RICMS_MG_RESPONSABILIDADE
            observacoes.append(
                "A mercadoria está relacionada na Parte 2 do Anexo VII e a UF de origem não consta no "
                "âmbito interestadual indicado para o item. Nessa hipótese, não estando a responsabilidade "
                "atribuída ao alienante/remetente, o destinatário mineiro é responsável pela apuração e "
                "recolhimento do ICMS-ST na entrada em Minas Gerais, conforme art. 15 do Anexo VII. "
                "Confira apenas eventuais hipóteses de inaplicabilidade, regime especial ou condição "
                "específica da operação."
            )
        else:
            aplicacao = "PRODUTO ENQUADRADO EM MG — INFORME A UF DE ORIGEM"
            observacoes.append("Informe a UF de origem para avaliar o âmbito da operação.")

        if ambiguo:
            observacoes.append(
                "Há mais de um enquadramento com a mesma especificidade de NCM. Confira a descrição legal e o CEST."
            )
        elif not descricao.strip():
            exige_revisao = True
            observacoes.append("Confira se a descrição real do produto corresponde à descrição legal do item.")
        else:
            aderencia = cls._aderencia_descricao(descricao, str(escolhido.get("descricao") or ""))
            descricao_7318_compativel = (
                segmento == "MATERIAIS DE CONSTRUÇÃO E CONGÊNERES"
                and codigo.startswith("7318")
                and cls._descricao_compativel_7318(descricao)
            )
            residual_contextual_confirmado = (
                cest == CEST_RESIDUAL_PORTA_A_PORTA
                and cls._operacao_porta_a_porta(contexto)
            )
            autopeca_contextual_confirmada = bool(
                segmento == "AUTOPEÇAS"
                and finalidade_automotiva == FINALIDADE_AUTO_CONFIRMADA
                and not cls._descricao_indica_consumivel(descricao)
            )
            if aderencia == 0 and autopeca_contextual_confirmada:
                # 17.8.128 — quando o usuário confirma que a mercadoria é autopeça
                # e a regra localizada pertence ao segmento AUTOPEÇAS, abreviações
                # comerciais do XML não podem derrubar um enquadramento que já foi
                # confirmado pelo contexto. A descrição continua protegendo contra
                # consumíveis e contra regras de outros segmentos.
                observacoes.append(
                    "A descrição comercial não repetiu os termos da descrição legal, mas a finalidade "
                    "automotiva foi confirmada e o enquadramento localizado pertence ao segmento Autopeças. "
                    "O cálculo foi mantido; revise apenas se a aplicação real do produto divergir do cadastro."
                )
            elif aderencia == 0 and not descricao_7318_compativel and not residual_contextual_confirmado:
                # 17.8.115 — NCM + operação não bastam. A descrição do produto
                # também precisa sustentar o enquadramento legal quando não existe
                # confirmação contextual de autopeça.
                confirmado = False
                exige_revisao = True
                aplicabilidade_segmento = "DESCRICAO_NAO_CONFIRMADA"
                observacoes.append(
                    "O NCM foi localizado, mas a descrição real do produto não confirmou a descrição legal "
                    "do item. O NCM isolado não confirma ICMS-ST; mantenha como CONDICIONAL até validar "
                    "a correspondência da mercadoria com a descrição e o segmento aplicável."
                )
            elif residual_contextual_confirmado:
                observacoes.append(
                    "A regra residual 28.999.00 é definida pelo canal porta a porta/marketing direto, "
                    "por isso a confirmação decorre do contexto da operação e não de palavras da descrição do item."
                )

        if segmento == "MATERIAIS DE CONSTRUÇÃO E CONGÊNERES" and codigo.startswith("7318"):
            fundamento_7318 = (
                "Conselho de Contribuintes/MG — Acórdão nº 25.475/26/3ª: "
                "o item precisa corresponder à descrição legal e ser passível de uso como "
                "material de construção ou congênere."
            )
            fundamento_complementar = " | ".join(
                parte for parte in (fundamento_complementar, fundamento_7318) if parte
            )
            fonte_complementar_url = " | ".join(
                parte for parte in (fonte_complementar_url, URL_CONSELHO_CONTRIBUINTES_25475_26) if parte
            )

            descricao_compativel = cls._descricao_compativel_7318(descricao)
            if aplicabilidade_7318 == APLICABILIDADE_7318_EXCLUSIVO_AUTOMOTIVO:
                confirmado = False
                exige_revisao = False
                nao_aplicavel = True
                aplicabilidade_segmento = APLICABILIDADE_7318_EXCLUSIVO_AUTOMOTIVO
                aplicacao = "NÃO APLICÁVEL PELO SEGMENTO 10 — USO EXCLUSIVAMENTE AUTOMOTIVO INFORMADO"
                observacoes.append(
                    "O item foi informado como passível de uso apenas automotivo. Nessa condição, não foi "
                    "aplicado o ICMS-ST do segmento 10. Mantenha documentação técnica que sustente essa classificação."
                )
            elif aplicabilidade_7318 == APLICABILIDADE_7318_CONSTRUCAO:
                aplicabilidade_segmento = APLICABILIDADE_7318_CONSTRUCAO
                if not descricao_compativel:
                    exige_revisao = True
                    observacoes.append(
                        "A aplicação no segmento 10 foi confirmada manualmente, mas a descrição do XML não permitiu "
                        "reconhecer automaticamente parafuso, pino, perno, porca, rebite, chaveta, contrapino ou arruela."
                    )
                else:
                    observacoes.append(
                        "Foi confirmado que o item é passível de uso como material de construção ou congênere. "
                        "Aplica-se o CEST 10.058.00 e a MVA original de 50%, observado o âmbito da operação."
                    )
            else:
                confirmado = False
                exige_revisao = True
                aplicabilidade_segmento = APLICABILIDADE_7318_PENDENTE
                observacoes.append(
                    "O NCM 7318 está no CEST 10.058.00, com MVA original de 50%, mas é necessário informar se "
                    "o produto é passível de uso como material de construção/congênere ou se possui uso "
                    "exclusivamente automotivo antes de calcular o ICMS-ST."
                )

        if mva is None:
            exige_revisao = True
            if mva_texto:
                observacoes.append(
                    f"A mercadoria consta na tabela ST/MG, mas a coluna de cálculo não traz uma MVA única "
                    f"({mva_texto}). O enquadramento foi localizado; revise apenas a memória de cálculo."
                )
            else:
                observacoes.append(
                    "A mercadoria consta na tabela ST/MG, mas a MVA não foi reconhecida na fonte sincronizada; "
                    "confira a memória de cálculo oficial."
                )

        if nao_aplicavel:
            status = "NÃO APLICÁVEL — USO EXCLUSIVAMENTE AUTOMOTIVO"
        elif aplicabilidade_segmento == "DESCRICAO_NAO_CONFIRMADA":
            status = "CONDICIONAL — NCM LOCALIZADO; DESCRIÇÃO NÃO CONFIRMADA"
        elif aplicabilidade_segmento == APLICABILIDADE_7318_PENDENTE:
            status = "ENQUADRADO — CONFIRMAR APLICABILIDADE DO NCM 7318"
        elif confirmado and not exige_revisao:
            status = "CONFIRMADO — ICMS-ST MG"
        else:
            status = "ENQUADRADO — REVISAR DETALHES" if escolhido else "REVISÃO NECESSÁRIA"

        return ResultadoICMSSTMG(
            ncm=codigo,
            status=status,
            encontrado=True,
            confirmado=confirmado,
            exige_revisao=exige_revisao,
            item=item,
            cest=cest,
            ncm_legal=str(escolhido.get("ncm_formatado") or escolhido.get("ncm_digitos") or ""),
            descricao_legal=str(escolhido.get("descricao") or ""),
            segmento=segmento,
            ambito=ambito,
            mva_original=float(mva) if mva is not None else None,
            aplicacao_operacao=aplicacao,
            responsabilidade=responsabilidade,
            fundamento=metadados.get("fundamento", "RICMS/MG/2023 — Anexo VII, Parte 2"),
            artigo_item=artigo_item,
            fonte_codigo=str(escolhido.get("fonte_codigo") or metadados.get("fonte_codigo") or "SEF_MG_ST"),
            fonte_url=metadados.get("fonte_url", URL_RICMS_MG_ANEXO_VII),
            fundamento_complementar=fundamento_complementar,
            fonte_complementar_url=fonte_complementar_url,
            aplicabilidade_segmento=aplicabilidade_segmento,
            nao_aplicavel=nao_aplicavel,
            observacao=" ".join(observacoes),
            candidatos=len(candidatos),
            uf_origem=origem,
            uf_destino=destino,
            potencial=True,
            decisao_st="SIM" if confirmado and not exige_revisao else "CONDICIONAL",
            finalidade_automotiva=finalidade_automotiva,
            cest_sugerido=cest,
            mva_sugerida=float(mva) if mva is not None else None,
            mva_texto=mva_texto,
            base_st_completa=base_st_completa,
            base_st_atualizada_em=str(cobertura_st.get("sincronizado_em") or cobertura_st.get("atualizado_em") or ""),
            base_st_referencia=str(cobertura_st.get("referencia") or ""),
        ).para_dict()

    @staticmethod
    def aplicar_ao_parecer(parecer: Any, resultado: Dict[str, Any]) -> Any:
        """Aplica o enquadramento oficial ao parecer em memória, sem gravar regra local."""
        if parecer is None:
            return parecer

        tributacao = parecer.tributacao_atual
        revisao_manual = bool(tributacao.get("Revisão manual"))
        decisao_st_resultado = str(resultado.get("decisao_st") or "").strip().upper()
        nao_aplicavel_resultado = bool(resultado.get("nao_aplicavel")) or decisao_st_resultado == "NAO"
        if not resultado.get("encontrado") and not nao_aplicavel_resultado:
            status_condicional = str(
                resultado.get("status") or "CONDICIONAL — REVISAR ICMS-ST"
            )
            if not revisao_manual:
                # Substitui qualquer negativa automática/local. Ausência na base
                # não é prova legal de que a mercadoria está fora da ST.
                parecer.tributacao_atual["ICMS-ST"] = status_condicional
            else:
                parecer.tributacao_atual["ICMS-ST oficial MG — comparação"] = status_condicional
            parecer.tributacao_atual["CEST sugerido MG"] = str(
                resultado.get("cest_sugerido") or ""
            )
            if resultado.get("mva_sugerida") is not None:
                parecer.tributacao_atual["MVA sugerida MG"] = float(
                    resultado["mva_sugerida"]
                )
            alerta = str(resultado.get("observacao") or status_condicional)
            if alerta and alerta not in parecer.alertas:
                parecer.alertas.insert(0, alerta)
            conclusao = (
                "ICMS-ST/MG mantido como CONDICIONAL: a ausência de correspondência nominal do NCM "
                "não autoriza concluir que o produto não é ST. Confirme a finalidade automotiva."
            )
            if conclusao not in parecer.conclusoes:
                parecer.conclusoes.insert(0, conclusao)
            parecer.regras_aplicadas["icms_st_mg_condicional"] = dict(resultado)
            return parecer

        cest = str(resultado.get("cest") or "")
        cest_digitos = "".join(c for c in cest if c.isdigit())
        decisao_confirmada = bool(
            resultado.get("confirmado")
            and not resultado.get("exige_revisao")
            and str(resultado.get("decisao_st") or "SIM").strip().upper() == "SIM"
        )
        if cest_digitos and not resultado.get("nao_aplicavel") and decisao_confirmada:
            if not revisao_manual or not str(tributacao.get("CEST") or "").strip() or str(tributacao.get("CEST")).strip() == "Não informado":
                parecer.dados_gerais["CEST"] = cest_digitos
            parecer.tributacao_atual["CEST oficial MG"] = cest
            parecer.tributacao_atual.pop("CEST sugerido MG", None)
        elif cest_digitos and not resultado.get("nao_aplicavel"):
            # Candidato legal sem decisão confirmada: exibir como sugestão, sem
            # contaminar o CEST efetivamente aplicado na ficha.
            parecer.tributacao_atual.pop("CEST oficial MG", None)
            parecer.tributacao_atual["CEST sugerido MG"] = cest
        elif resultado.get("nao_aplicavel") and not revisao_manual:
            # Não deixe CEST/MVA antigos parecerem aplicados quando o motor
            # oficial concluiu NÃO — inclusive NCM sem enquadramento legal na
            # Parte 2 do Anexo VII.
            parecer.dados_gerais["CEST"] = ""
            parecer.tributacao_atual.pop("CEST oficial MG", None)
            parecer.tributacao_atual.pop("CEST sugerido MG", None)
            parecer.tributacao_atual.pop("MVA ST oficial MG", None)
            parecer.tributacao_atual.pop("MVA sugerida MG", None)

        if not revisao_manual:
            if resultado.get("nao_aplicavel"):
                parecer.tributacao_atual["ICMS-ST"] = str(
                    resultado.get("status") or "NÃO — ENQUADRAMENTO ST NÃO APLICÁVEL"
                )
            else:
                parecer.tributacao_atual["ICMS-ST"] = (
                    "SIM" if decisao_confirmada else "REVISAR"
                )
        else:
            parecer.tributacao_atual["ICMS-ST oficial MG — comparação"] = (
                "NÃO" if resultado.get("nao_aplicavel") else ("SIM" if decisao_confirmada else "REVISAR")
            )
            aviso = "Existe regra manual salva; o resultado oficial de ICMS-ST/CEST/MVA foi mantido para comparação e não sobrescreveu a revisão manual."
            if aviso not in parecer.alertas:
                parecer.alertas.append(aviso)
        if resultado.get("mva_original") is not None and decisao_confirmada:
            parecer.tributacao_atual["MVA ST oficial MG"] = float(resultado["mva_original"])
            parecer.tributacao_atual.pop("MVA sugerida MG", None)
        elif resultado.get("mva_original") is not None and not resultado.get("nao_aplicavel"):
            parecer.tributacao_atual.pop("MVA ST oficial MG", None)
            parecer.tributacao_atual["MVA sugerida MG"] = float(resultado["mva_original"])
        parecer.tributacao_atual["Âmbito ST MG"] = resultado.get("ambito") or ""
        parecer.tributacao_atual["Segmento ST MG"] = resultado.get("segmento") or ""
        parecer.tributacao_atual["Fonte ICMS-ST"] = (
            f"{resultado.get('fundamento')} — {resultado.get('artigo_item')}"
        )

        base = f"{resultado.get('fundamento')} — {resultado.get('artigo_item')}"
        if base and base not in parecer.base_legal:
            parecer.base_legal.append(base)
        fonte = resultado.get("fonte_url")
        if fonte and fonte not in parecer.fontes:
            parecer.fontes.append(fonte)
        base_complementar = str(resultado.get("fundamento_complementar") or "").strip()
        if base_complementar and base_complementar not in parecer.base_legal:
            parecer.base_legal.append(base_complementar)
        fonte_complementar = resultado.get("fonte_complementar_url")
        if fonte_complementar and fonte_complementar not in parecer.fontes:
            parecer.fontes.append(fonte_complementar)

        segmento = str(resultado.get("segmento") or "segmento oficial").lower()
        if resultado.get("nao_aplicavel"):
            aplicabilidade = str(resultado.get("aplicabilidade_segmento") or "")
            if aplicabilidade in {
                "NCM_FORA_ANEXO_VII_PARTE_2",
                "NCM_AUSENTE_BASE_OFICIAL_COMPLETA",
            }:
                origem_base = (
                    "na base oficial completa sincronizada da Parte 2 do Anexo VII/MG"
                    if aplicabilidade == "NCM_AUSENTE_BASE_OFICIAL_COMPLETA"
                    else "na Parte 2 do Anexo VII/MG"
                )
                conclusao = (
                    f"NCM {resultado.get('ncm')} sem enquadramento nominal {origem_base}; "
                    "ICMS-ST = NÃO, sem CEST e sem MVA de ST para a regra geral. "
                    "Eventual regime especial específico do contribuinte deve ser analisado à parte."
                )
            elif aplicabilidade == "DESCRICAO_FORA_CEST_0109000":
                conclusao = (
                    "NCM 3919.90 localizado no item 90.0 do segmento de autopeças, porém a descrição "
                    "do produto indica adesivo/kit decorativo e não dispositivo refletivo de segurança; "
                    "o CEST 01.090.00 e sua MVA não foram aplicados."
                )
            else:
                conclusao = (
                    "NCM 7318 localizado no segmento 10, porém classificado pelo usuário como de uso "
                    "exclusivamente automotivo; o ICMS-ST desse segmento não foi aplicado."
                )
        elif decisao_confirmada:
            prefixo = "Resultado oficial para comparação: " if revisao_manual else ""
            conclusao = (
                f"{prefixo}NCM enquadrado no segmento de {segmento} do ICMS-ST de Minas Gerais, CEST "
                f"{resultado.get('cest')}, MVA original {float(resultado.get('mva_original') or 0):.2f}%."
            )
        else:
            prefixo = "Resultado oficial para comparação: " if revisao_manual else ""
            conclusao = (
                f"{prefixo}NCM localizado como candidato no segmento de {segmento}, porém o ICMS-ST "
                "permanece CONDICIONAL porque a descrição/segmento/operação ainda não foram confirmados "
                "cumulativamente. O CEST e a MVA são apenas referências para revisão."
            )
        if conclusao not in parecer.conclusoes:
            parecer.conclusoes.insert(0, conclusao)

        parecer.pendencias = [
            item for item in parecer.pendencias
            if "VINCULAR A LEGISLACAO OFICIAL DE ICMS E ICMS-ST" not in ICMSSTMGService._normalizar_texto(item)
        ]
        if resultado.get("exige_revisao"):
            pendencia = "Conferir descrição, âmbito e responsabilidade pelo recolhimento do ICMS-ST na operação real."
            if pendencia not in parecer.pendencias:
                parecer.pendencias.append(pendencia)
        else:
            pendencia_icms = "Confirmar a alíquota interna de ICMS aplicável ao produto e eventuais benefícios fiscais."
            if pendencia_icms not in parecer.pendencias:
                parecer.pendencias.append(pendencia_icms)

        parecer.regras_aplicadas["icms_st_mg_oficial"] = dict(resultado)
        parecer.versao_motor = "14.7"
        return parecer
