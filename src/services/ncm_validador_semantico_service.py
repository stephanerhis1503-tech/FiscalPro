"""Motor semântico nacional de validação de NCM.

Versão 18.2.22
---------------
Este serviço não associa peças diretamente a NCMs. Ele compara a linguagem
comercial do cadastro com TODO o catálogo NCM/TIPI oficial instalado, usando:
- descrição e hierarquia oficial;
- normalização de sinônimos comerciais/fiscais;
- pistas de função, material, aplicação e domínio;
- ranking conservador de candidatos.

O objetivo principal é detectar NCMs formalmente válidos porém semanticamente
incompatíveis. Quando a evidência não é suficiente, o motor retorna REVISAR em
vez de inventar uma classificação.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Sequence
import re
import unicodedata

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.base_ncm_nacional_service import BaseNCMNacionalService


@dataclass(frozen=True)
class CandidatoNCMSemantico:
    ncm: str
    descricao_oficial: str
    pontuacao: float

    @property
    def resumo(self) -> str:
        return f"{self.ncm} ({self.pontuacao:.0f}%)"


@dataclass(frozen=True)
class ResultadoValidacaoNCMSemantica:
    status: str
    ncm_atual: str
    compatibilidade_atual: float
    descricao_oficial_atual: str
    candidato_principal: Optional[CandidatoNCMSemantico]
    candidatos: tuple[CandidatoNCMSemantico, ...]
    motivo: str

    @property
    def possui_sugestao_forte(self) -> bool:
        return (
            self.status == "INCOMPATIVEL"
            and self.candidato_principal is not None
            and self.candidato_principal.ncm != self.ncm_atual
        )


@dataclass(frozen=True)
class _RegistroOficial:
    ncm: str
    descricao: str
    descricao_completa: str
    tokens: frozenset[str]
    tokens_folha: frozenset[str]


class NCMValidadorSemanticoService:
    """Valida qualquer NCM contra o catálogo nacional, sem lista peça→NCM."""

    _lock = RLock()
    _cache_chave: tuple[str, int] | None = None
    _registros: tuple[_RegistroOficial, ...] = ()
    _por_ncm: Dict[str, int] = {}
    _por_token: Dict[str, frozenset[int]] = {}

    _STOPWORDS = {
        "A", "AS", "AO", "AOS", "COM", "DA", "DAS", "DE", "DO", "DOS", "E",
        "EM", "NA", "NAS", "NO", "NOS", "O", "OS", "OU", "PARA", "POR", "SEM",
        "UM", "UMA", "UN", "UND", "PC", "PCS", "PCA", "PECAS", "PECA", "ITEM",
        "PRODUTO", "DIVERSO", "DIVERSOS", "DIVERSA", "DIVERSAS",
    }
    _RUIDOS = {
        "PRETO", "PRETA", "VERMELHO", "VERMELHA", "VERDE", "AZUL", "BRANCO",
        "BRANCA", "AMARELO", "AMARELA", "CINZA", "PRATA", "DOURADO", "DOURADA",
        "LARANJA", "ROSA", "ROXO", "ROXA", "FOSCO", "FOSCA", "CRISTAL",
        "LD", "LE", "DIR", "DIREITO", "DIREITA", "ESQ", "ESQUERDO", "ESQUERDA",
        "DIANTEIRO", "DIANTEIRA", "TRASEIRO", "TRASEIRA", "ORIG", "ORIGINAL",
    }

    # São equivalências de linguagem, NÃO classificações fiscais. Nenhuma entrada
    # abaixo contém NCM. Servem apenas para aproximar vocabulário de balcão da
    # nomenclatura legal usada pela NCM/TIPI.
    _GRUPOS_SEMANTICOS = (
        ("PARTIDA", "ARRANQUE"),
        ("BOIA", "NIVEL", "MEDIDOR"),
        ("TANQUE", "RESERVATORIO", "COMBUSTIVEL", "LIQUIDO"),
        ("PASTILHA", "GUARNICAO"),
        ("CAPA", "REVESTIMENTO", "PROTECAO"),
        ("BANCO", "ASSENTO"),
        ("BENGALA", "SUSPENSAO"),
        ("SANFONA", "PROTETOR", "PROTECAO"),
        ("PISCA", "INDICADOR", "DIRECAO", "SINALIZACAO"),
        ("FAROL", "ILUMINACAO", "LUZ"),
        ("LANTERNA", "SINALIZACAO", "LUZ"),
        ("CHICOTE", "FIACAO", "CONDUTOR", "CABO"),
        ("RETENTOR", "VEDACAO", "GAXETA"),
        ("JUNTA", "VEDACAO", "GAXETA"),
        ("ESCOVA", "CARVAO"),
        ("GUIDAO", "DIRECAO"),
        ("MANETE", "ALAVANCA"),
        ("MANOPLA", "PUNHO"),
        ("ARO", "RODA"),
        ("PINHAO", "ENGRENAGEM"),
        ("COROA", "ENGRENAGEM"),
        ("RELACAO", "TRANSMISSAO"),
        ("AMORTECEDOR", "SUSPENSAO"),
        ("PEDALEIRA", "APOIO"),
        ("PISTAO", "EMBOLO"),
        ("VELA", "IGNICAO"),
        ("BOBINA", "IGNICAO"),
        ("LED", "DIODO", "LUZ"),
        ("ADESIVO", "AUTOADESIVO"),
        ("FAIXA", "TIRA", "AUTOADESIVO"),
    )

    # Pistas de domínio: ajudam a interpretar descrições comerciais, mas não
    # escolhem NCM sozinhas. Ex.: TITAN/BROS sugerem contexto de motocicleta.
    _MODELOS_MOTOCICLETA = {
        "BIZ", "BROS", "CB", "CBX", "CG", "CG150", "CG160", "CRF", "CRYPTON",
        "FACTOR", "FAN", "FAZER", "LANDER", "NXR", "PCX", "POP", "TITAN",
        "TWISTER", "XRE", "XTZ", "YBR", "YES", "BURGMAN",
    }

    _SINONIMOS: Dict[str, frozenset[str]] = {}

    @classmethod
    def _montar_sinonimos(cls) -> None:
        if cls._SINONIMOS:
            return
        mapa: Dict[str, set[str]] = {}
        for grupo in cls._GRUPOS_SEMANTICOS:
            raizes = {cls._raiz_token(item) for item in grupo}
            for item in raizes:
                mapa.setdefault(item, set()).update(raizes - {item})
        cls._SINONIMOS = {chave: frozenset(valores) for chave, valores in mapa.items()}

    @staticmethod
    def _texto(valor: Any) -> str:
        texto = str(valor or "").upper().strip()
        texto = "".join(
            c
            for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        texto = re.sub(r"\([^)]*\)", " ", texto)
        texto = re.sub(r"[^A-Z0-9]+", " ", texto)
        return " ".join(texto.split())

    @staticmethod
    def _ncm(valor: Any) -> str:
        return "".join(c for c in str(valor or "") if c.isdigit())

    @staticmethod
    def _raiz_token(token: str) -> str:
        token = str(token or "").upper()
        if len(token) > 6 and token.endswith("COES"):
            return token[:-4] + "CAO"
        if len(token) > 6 and token.endswith("SOES"):
            return token[:-4] + "SAO"
        if len(token) > 6 and token.endswith("ZOES"):
            return token[:-4] + "ZAO"
        if len(token) > 5 and token.endswith("ORES"):
            return token[:-2]
        if len(token) > 4 and token.endswith("S"):
            return token[:-1]
        return token

    @classmethod
    def _tokens(cls, texto: Any, *, produto: bool) -> List[str]:
        normalizado = cls._texto(texto)
        tokens: List[str] = []
        for bruto in normalizado.split():
            if bruto in cls._STOPWORDS:
                continue
            if produto and bruto in cls._RUIDOS:
                continue
            # Cores/modelos com números, anos, medidas e códigos comerciais
            # raramente ajudam a localizar a abertura legal da NCM.
            if produto and re.search(r"\d", bruto):
                continue
            if len(bruto) <= 2:
                continue
            raiz = cls._raiz_token(bruto)
            if raiz and raiz not in cls._STOPWORDS:
                tokens.append(raiz)

        if produto:
            # As pistas semânticas entram logo após os dois primeiros termos
            # comerciais, para não serem soterradas por modelo/cor/acabamento.
            extras: List[str] = []
            brutos = {cls._raiz_token(t) for t in normalizado.split()}
            if brutos.intersection(cls._MODELOS_MOTOCICLETA):
                extras.append("MOTOCICLETA")
            # Expressões de balcão ganham conceitos funcionais, nunca NCMs.
            if "CAPA BANCO" in normalizado:
                extras.extend(("ASSENTO", "MOTOCICLETA"))
            if "BOIA TANQUE" in normalizado:
                extras.extend(("NIVEL", "COMBUSTIVEL"))
            if "PASTILHA FREIO" in normalizado:
                extras.extend(("GUARNICAO", "FREIO"))
            if extras:
                tokens = tokens[:2] + extras + tokens[2:]

        # Preserva ordem e evita que repetições dominem a pontuação.
        unicos: List[str] = []
        vistos = set()
        for token in tokens:
            if token in vistos:
                continue
            vistos.add(token)
            unicos.append(token)
        return unicos

    @classmethod
    def _expandir(cls, token: str) -> frozenset[str]:
        cls._montar_sinonimos()
        token = cls._raiz_token(token)
        return frozenset({token, *cls._SINONIMOS.get(token, ())})

    @classmethod
    def _registro(cls, item: Dict[str, Any]) -> Optional[_RegistroOficial]:
        ncm = cls._ncm(item.get("ncm"))
        if len(ncm) != 8:
            return None
        descricao = str(item.get("descricao") or "").strip()
        completa = str(item.get("descricao_completa") or descricao).strip()
        tokens = frozenset(cls._tokens(completa, produto=False))
        folha = frozenset(cls._tokens(descricao, produto=False))
        return _RegistroOficial(
            ncm=ncm,
            descricao=descricao,
            descricao_completa=completa,
            tokens=tokens,
            tokens_folha=folha,
        )

    @classmethod
    def _instalar_catalogo_em_memoria(
        cls,
        itens: Sequence[Dict[str, Any]],
        chave: tuple[str, int],
    ) -> None:
        registros: List[_RegistroOficial] = []
        por_ncm: Dict[str, int] = {}
        indice_mutavel: Dict[str, set[int]] = {}

        for item in itens:
            registro = cls._registro(item)
            if registro is None:
                continue
            pos = len(registros)
            registros.append(registro)
            por_ncm[registro.ncm] = pos
            for token in registro.tokens:
                indice_mutavel.setdefault(token, set()).add(pos)

        cls._registros = tuple(registros)
        cls._por_ncm = por_ncm
        cls._por_token = {
            token: frozenset(posicoes)
            for token, posicoes in indice_mutavel.items()
        }
        cls._cache_chave = chave

    @classmethod
    def _garantir_indice(cls) -> None:
        try:
            preparado = BaseNCMNacionalService.garantir_instalada()
            chave = (str(preparado.versao or ""), int(preparado.total_ncm or 0))
        except Exception:
            resumo = BaseOficialRepository.resumo_base_nacional()
            chave = (str(resumo.get("versao") or ""), int(resumo.get("total_ncm") or 0))

        if cls._cache_chave == chave and cls._registros:
            return

        with cls._lock:
            if cls._cache_chave == chave and cls._registros:
                return
            itens = BaseOficialRepository.listar_ncm_oficiais()
            cls._instalar_catalogo_em_memoria(itens, chave)

    @classmethod
    def _valor_match(cls, token: str, oficiais: frozenset[str]) -> float:
        if token in oficiais:
            return 1.0
        expandidos = cls._expandir(token)
        if expandidos.intersection(oficiais):
            return 0.82
        if len(token) >= 5:
            for oficial in oficiais:
                if len(oficial) >= 5 and (
                    oficial.startswith(token) or token.startswith(oficial)
                ):
                    return 0.72
        return 0.0

    @classmethod
    def _pontuar(cls, tokens_produto: Sequence[str], registro: _RegistroOficial) -> float:
        principais = list(tokens_produto[:6])
        if not principais or not registro.tokens:
            return 0.0

        valores = [cls._valor_match(token, registro.tokens) for token in principais]
        qtd_primaria = min(2, len(valores))
        primaria = sum(valores[:qtd_primaria]) / float(qtd_primaria or 1)
        qtd_janela = min(4, len(valores))
        janela = sum(valores[:qtd_janela]) / float(qtd_janela or 1)
        cobertura = sum(1 for valor in valores[:qtd_janela] if valor > 0) / float(qtd_janela or 1)

        texto_produto = " ".join(principais[:4])
        texto_oficial = " ".join(sorted(registro.tokens_folha or registro.tokens))
        sequencia = SequenceMatcher(None, texto_produto, texto_oficial).ratio()

        score = (58.0 * primaria) + (27.0 * janela) + (10.0 * cobertura) + (5.0 * sequencia)

        # Correspondência direta com a descrição terminal da NCM vale mais que
        # coincidência apenas na hierarquia superior.
        folha_matches = sum(
            1
            for token in principais[:3]
            if cls._valor_match(token, registro.tokens_folha) >= 0.82
        )
        score += min(6.0, float(folha_matches) * 2.0)
        return max(0.0, min(100.0, score))

    @classmethod
    def _candidatos(cls, tokens_produto: Sequence[str], limite: int = 5) -> List[CandidatoNCMSemantico]:
        ids: set[int] = set()
        for token in tokens_produto[:6]:
            for termo in cls._expandir(token):
                ids.update(cls._por_token.get(termo, ()))

        if not ids:
            return []

        # Proteção de desempenho para palavras muito amplas.
        if len(ids) > 2500:
            ids = set(sorted(ids)[:2500])

        pontuados: List[CandidatoNCMSemantico] = []
        for pos in ids:
            registro = cls._registros[pos]
            score = cls._pontuar(tokens_produto, registro)
            if score < 28.0:
                continue
            pontuados.append(
                CandidatoNCMSemantico(
                    ncm=registro.ncm,
                    descricao_oficial=registro.descricao_completa or registro.descricao,
                    pontuacao=score,
                )
            )

        pontuados.sort(key=lambda item: (item.pontuacao, item.ncm), reverse=True)
        return pontuados[: max(1, min(int(limite or 5), 10))]

    @classmethod
    def validar(cls, descricao_produto: Any, ncm_atual: Any) -> ResultadoValidacaoNCMSemantica:
        """Compara um item contra todo o catálogo NCM oficial instalado."""
        cls._garantir_indice()
        atual = cls._ncm(ncm_atual)
        tokens_produto = cls._tokens(descricao_produto, produto=True)

        if len(atual) != 8 or not tokens_produto:
            return ResultadoValidacaoNCMSemantica(
                status="SEM_EVIDENCIA",
                ncm_atual=atual,
                compatibilidade_atual=0.0,
                descricao_oficial_atual="",
                candidato_principal=None,
                candidatos=(),
                motivo="Descrição ou NCM insuficiente para validação semântica geral.",
            )

        pos_atual = cls._por_ncm.get(atual)
        registro_atual = cls._registros[pos_atual] if pos_atual is not None else None
        score_atual = cls._pontuar(tokens_produto, registro_atual) if registro_atual else 0.0
        candidatos = cls._candidatos(tokens_produto, limite=5)
        melhor = candidatos[0] if candidatos else None
        segundo = candidatos[1] if len(candidatos) > 1 else None

        if registro_atual is None:
            return ResultadoValidacaoNCMSemantica(
                status="REVISAR",
                ncm_atual=atual,
                compatibilidade_atual=0.0,
                descricao_oficial_atual="",
                candidato_principal=melhor,
                candidatos=tuple(candidatos[:3]),
                motivo=(
                    f"NCM {atual} não foi localizado no catálogo NCM oficial instalado. "
                    "Não usar a tributação desse código como referência sem validação."
                ),
            )

        # Se o próprio NCM atual lidera a busca e possui ligação semântica
        # razoável, não cria falso alerta.
        if melhor is not None and melhor.ncm == atual and melhor.pontuacao >= 42.0:
            return ResultadoValidacaoNCMSemantica(
                status="COMPATIVEL",
                ncm_atual=atual,
                compatibilidade_atual=score_atual,
                descricao_oficial_atual=registro_atual.descricao_completa or registro_atual.descricao,
                candidato_principal=melhor,
                candidatos=tuple(candidatos[:3]),
                motivo="Descrição comercial compatível com a hierarquia oficial do NCM atual.",
            )

        if score_atual >= 55.0 and (
            melhor is None or melhor.ncm == atual or melhor.pontuacao <= score_atual + 8.0
        ):
            return ResultadoValidacaoNCMSemantica(
                status="COMPATIVEL",
                ncm_atual=atual,
                compatibilidade_atual=score_atual,
                descricao_oficial_atual=registro_atual.descricao_completa or registro_atual.descricao,
                candidato_principal=melhor,
                candidatos=tuple(candidatos[:3]),
                motivo="NCM atual possui compatibilidade semântica suficiente com a descrição.",
            )

        if melhor is not None and melhor.ncm != atual:
            margem_segundo = melhor.pontuacao - (segundo.pontuacao if segundo else 0.0)
            ganho_atual = melhor.pontuacao - score_atual
            forte = (
                melhor.pontuacao >= 68.0
                and ganho_atual >= 20.0
                and margem_segundo >= 7.0
            )
            muito_forte = (
                melhor.pontuacao >= 76.0
                and ganho_atual >= 16.0
                and margem_segundo >= 4.0
            )
            if forte or muito_forte:
                return ResultadoValidacaoNCMSemantica(
                    status="INCOMPATIVEL",
                    ncm_atual=atual,
                    compatibilidade_atual=score_atual,
                    descricao_oficial_atual=registro_atual.descricao_completa or registro_atual.descricao,
                    candidato_principal=melhor,
                    candidatos=tuple(candidatos[:3]),
                    motivo=(
                        f"NCM atual {atual} tem compatibilidade semântica de {score_atual:.0f}%, "
                        f"enquanto {melhor.ncm} atingiu {melhor.pontuacao:.0f}% no catálogo oficial."
                    ),
                )

        # Não rebaixa todo item de balcão apenas porque a nomenclatura oficial usa
        # palavras diferentes. Exige ao menos alguma evidência alternativa antes
        # de bloquear o status.
        if melhor is not None and melhor.ncm != atual and melhor.pontuacao >= 45.0 and score_atual < 25.0:
            return ResultadoValidacaoNCMSemantica(
                status="REVISAR",
                ncm_atual=atual,
                compatibilidade_atual=score_atual,
                descricao_oficial_atual=registro_atual.descricao_completa or registro_atual.descricao,
                candidato_principal=melhor,
                candidatos=tuple(candidatos[:3]),
                motivo=(
                    f"A descrição não confirma semanticamente o NCM atual {atual}. "
                    f"O catálogo oficial encontrou alternativa(s) mais relacionadas, lideradas por {melhor.ncm} "
                    f"({melhor.pontuacao:.0f}%), mas sem segurança para correção automática."
                ),
            )

        return ResultadoValidacaoNCMSemantica(
            status="SEM_EVIDENCIA",
            ncm_atual=atual,
            compatibilidade_atual=score_atual,
            descricao_oficial_atual=registro_atual.descricao_completa or registro_atual.descricao,
            candidato_principal=melhor,
            candidatos=tuple(candidatos[:3]),
            motivo=(
                "A linguagem comercial não forneceu evidência suficiente para confirmar ou rejeitar "
                "o NCM atual. O motor manteve o cadastro sem inventar classificação."
            ),
        )

    @classmethod
    def _validar_com_catalogo_teste(
        cls,
        descricao_produto: Any,
        ncm_atual: Any,
        catalogo: Sequence[Dict[str, Any]],
    ) -> ResultadoValidacaoNCMSemantica:
        """Gancho determinístico para testes sem depender do banco do usuário."""
        with cls._lock:
            estado = (
                cls._cache_chave,
                cls._registros,
                dict(cls._por_ncm),
                dict(cls._por_token),
            )
            try:
                cls._instalar_catalogo_em_memoria(catalogo, ("TESTE", len(catalogo)))
                atual = cls._ncm(ncm_atual)
                tokens_produto = cls._tokens(descricao_produto, produto=True)
                pos_atual = cls._por_ncm.get(atual)
                registro_atual = cls._registros[pos_atual] if pos_atual is not None else None
                score_atual = cls._pontuar(tokens_produto, registro_atual) if registro_atual else 0.0
                candidatos = cls._candidatos(tokens_produto, limite=5)
                melhor = candidatos[0] if candidatos else None
                segundo = candidatos[1] if len(candidatos) > 1 else None

                if registro_atual is None:
                    status = "REVISAR"
                elif melhor is not None and melhor.ncm == atual and melhor.pontuacao >= 42.0:
                    status = "COMPATIVEL"
                elif score_atual >= 55.0 and (
                    melhor is None or melhor.ncm == atual or melhor.pontuacao <= score_atual + 8.0
                ):
                    status = "COMPATIVEL"
                elif melhor is not None and melhor.ncm != atual and (
                    (
                        melhor.pontuacao >= 68.0
                        and melhor.pontuacao - score_atual >= 20.0
                        and melhor.pontuacao - (segundo.pontuacao if segundo else 0.0) >= 7.0
                    )
                    or (
                        melhor.pontuacao >= 76.0
                        and melhor.pontuacao - score_atual >= 16.0
                        and melhor.pontuacao - (segundo.pontuacao if segundo else 0.0) >= 4.0
                    )
                ):
                    status = "INCOMPATIVEL"
                elif melhor is not None and melhor.ncm != atual and melhor.pontuacao >= 45.0 and score_atual < 25.0:
                    status = "REVISAR"
                else:
                    status = "SEM_EVIDENCIA"

                return ResultadoValidacaoNCMSemantica(
                    status=status,
                    ncm_atual=atual,
                    compatibilidade_atual=score_atual,
                    descricao_oficial_atual=(
                        registro_atual.descricao_completa or registro_atual.descricao
                        if registro_atual else ""
                    ),
                    candidato_principal=melhor,
                    candidatos=tuple(candidatos[:3]),
                    motivo="resultado de teste",
                )
            finally:
                cls._cache_chave, cls._registros, cls._por_ncm, cls._por_token = estado
