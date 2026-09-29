"""Resolução de NCM por descrição digitada na Ficha Inteligente.

A NCM oficial nem sempre contém o nome comercial usado no balcão/estoque. Este
serviço combina três camadas sem inventar classificação automática:

1. catálogo nacional NCM/TIPI instalado no FiscalPro;
2. descrições já conhecidas no banco local do usuário;
3. aliases comerciais ambíguos, que retornam candidatos para escolha manual.

Os aliases nunca escolhem sozinhos um NCM quando a expressão pode representar
materiais/classificações diferentes.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Sequence, Tuple

from src.banco.conexao import Banco
from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.base_ncm_nacional_service import BaseNCMNacionalService


class NCMDescricaoService:
    """Pesquisa NCM por linguagem comercial com retorno auditável de candidatos."""

    # Termos que normalmente não aparecem literalmente na descrição legal da NCM.
    # O retorno é deliberadamente múltiplo quando material/aplicação muda o código.
    _CANDIDATOS_COMUNS: Dict[str, Sequence[Tuple[str, str]]] = {
        "ABRACADEIRA": (
            (
                "73269090",
                "Abraçadeira metálica/genérica — possível enquadramento em outras obras de ferro ou aço; confirmar material e aplicação.",
            ),
            (
                "39269090",
                "Abraçadeira plástica/nylon — possível enquadramento em outras obras de plástico; confirmar material e aplicação.",
            ),
        ),
    }

    @staticmethod
    def _texto_busca(texto: Any) -> str:
        valor = str(texto or "").upper().strip()
        valor = "".join(
            caractere
            for caractere in unicodedata.normalize("NFD", valor)
            if unicodedata.category(caractere) != "Mn"
        )
        valor = re.sub(r"[^A-Z0-9]+", " ", valor)
        return " ".join(valor.split())

    @classmethod
    def _tokens(cls, texto: Any) -> List[str]:
        return [token for token in cls._texto_busca(texto).split() if token]

    @staticmethod
    def _raiz_token(token: str) -> str:
        """Reduz plural simples para melhorar 'pastilha/pastilhas', 'freio/freios'."""
        token = str(token or "")
        if len(token) > 4 and token.endswith("S"):
            return token[:-1]
        return token

    @classmethod
    def _descricao_combina(cls, termo: str, descricao: str) -> bool:
        buscados = [cls._raiz_token(t) for t in cls._tokens(termo)]
        encontrados = {cls._raiz_token(t) for t in cls._tokens(descricao)}
        if not buscados:
            return False
        return all(token_busca in encontrados for token_busca in buscados)

    @classmethod
    def _candidatos_comuns(cls, termo: str) -> List[Tuple[str, str]]:
        normalizado = cls._texto_busca(termo)
        tokens = set(normalizado.split())
        resultados: List[Tuple[str, str]] = []
        for chave, candidatos in cls._CANDIDATOS_COMUNS.items():
            chave_tokens = set(chave.split())
            if not chave_tokens or not chave_tokens.issubset(tokens):
                continue

            # Para o termo comercial ABRAÇADEIRA, material muda a classificação.
            # Se a própria descrição já trouxer o material, reduza os candidatos;
            # sem material, mostre ambos para decisão humana.
            if chave == "ABRACADEIRA":
                plastico = bool(tokens & {"PLASTICO", "PLASTICA", "NYLON"})
                metal = bool(tokens & {"METAL", "METALICA", "ACO", "INOX", "FERRO"})
                if plastico and not metal:
                    resultados.extend(item for item in candidatos if item[0] == "39269090")
                    continue
                if metal and not plastico:
                    resultados.extend(item for item in candidatos if item[0] == "73269090")
                    continue

            resultados.extend(candidatos)
        return resultados

    @classmethod
    def _buscar_locais(cls, termo: str, limite: int = 120) -> List[Tuple[str, str]]:
        """Busca também no cadastro local, com comparação sem acentos."""
        conn = Banco.conectar()
        try:
            linhas = conn.execute(
                """
                SELECT ncm, descricao, 0 AS prioridade
                  FROM ncm
                 WHERE TRIM(COALESCE(descricao, '')) <> ''
                UNION ALL
                SELECT ncm, descricao_produto AS descricao, 1 AS prioridade
                  FROM tributacao_base
                 WHERE ativo = 1 AND TRIM(COALESCE(descricao_produto, '')) <> ''
                ORDER BY prioridade
                """
            ).fetchall()
        finally:
            conn.close()

        encontrados: List[Tuple[str, str]] = []
        for linha in linhas:
            descricao = str(linha["descricao"] or "").strip()
            if not cls._descricao_combina(termo, descricao):
                continue
            ncm = "".join(c for c in str(linha["ncm"] or "") if c.isdigit())
            if len(ncm) != 8:
                continue
            encontrados.append((ncm, descricao or "Descrição não informada"))
            if len(encontrados) >= max(1, int(limite or 120)):
                break
        return encontrados

    @classmethod
    def pesquisar(cls, termo: str, limite: int = 60) -> List[Tuple[str, str]]:
        """Retorna candidatos únicos, priorizando a base nacional oficial."""
        termo = str(termo or "").strip()
        if not termo:
            return []
        limite = max(1, min(int(limite or 60), 300))

        # A Ficha antes consultava apenas as tabelas antigas. Garantimos que a
        # mesma base nacional da janela Catálogo NCM esteja disponível aqui.
        try:
            BaseNCMNacionalService.garantir_instalada()
        except Exception:
            # A pesquisa local ainda pode funcionar em instalações sem o pacote.
            pass

        candidatos: List[Tuple[str, str]] = []
        try:
            oficiais = BaseOficialRepository.buscar_ncm_catalogo(termo, limite=max(limite * 3, 120))
        except Exception:
            oficiais = []

        for item in oficiais:
            descricao = str(item.get("descricao_completa") or item.get("descricao") or "").strip()
            # Filtra falsos positivos de substring, por exemplo PORCA em PROPORÇÃO.
            if descricao and not cls._descricao_combina(termo, descricao):
                continue
            ncm = "".join(c for c in str(item.get("ncm") or "") if c.isdigit())
            if len(ncm) == 8:
                candidatos.append((ncm, descricao or "Descrição oficial não informada"))

        # O banco local pode conter linguagem comercial aprendida/importada pela empresa.
        candidatos.extend(cls._buscar_locais(termo, limite=max(limite * 2, 80)))

        # Termos comerciais que não aparecem na nomenclatura legal geram opções,
        # nunca uma escolha automática quando há mais de uma possibilidade.
        candidatos.extend(cls._candidatos_comuns(termo))

        unicos: List[Tuple[str, str]] = []
        vistos = set()
        for ncm, descricao in candidatos:
            if ncm in vistos:
                continue
            vistos.add(ncm)
            unicos.append((ncm, descricao))
            if len(unicos) >= limite:
                break
        return unicos
