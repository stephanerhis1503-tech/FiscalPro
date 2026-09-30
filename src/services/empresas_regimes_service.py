"""Cadastro fiscal central das empresas do grupo — Hotfix 17.8.26.

Esta camada é a fonte única para o regime tributário usado nas consultas do
FiscalPro. A empresa, quando reconhecida, prevalece sobre um regime digitado ou
herdado de uma tela antiga. Isso evita consultar a Mega Motos Comércio como
Lucro Real por engano.

As alíquotas abaixo são somente o *padrão do regime* para saídas comuns de
PIS/Cofins. Regras específicas (monofásico, alíquota zero, suspensão,
exportação etc.) continuam tendo prioridade no motor nacional.
"""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import unicodedata
from typing import Any, Dict, Iterable, Tuple

from src.core.caminhos import BANCO_ENTREGAS


@dataclass(frozen=True, slots=True)
class PerfilEmpresaFiscal:
    nome: str
    regime: str
    regime_piscofins: str
    pis_padrao: float | None
    cofins_padrao: float | None

    @property
    def aliquotas_piscofins_texto(self) -> str:
        if self.pis_padrao is None or self.cofins_padrao is None:
            return "PIS/COFINS: apuração conforme o regime/PGDAS-D"
        return (
            f"PIS padrão: {self.pis_padrao:.2f}% • "
            f"COFINS padrão: {self.cofins_padrao:.2f}%"
        ).replace(".", ",")


class EmpresasRegimesService:
    """Resolve empresa → regime e metadados fiscais de forma centralizada."""

    PERFIS: Tuple[PerfilEmpresaFiscal, ...] = (
        PerfilEmpresaFiscal(
            "Mega Motos Trilha", "LUCRO REAL", "NÃO CUMULATIVO", 1.65, 7.60
        ),
        PerfilEmpresaFiscal(
            "Mega T.O. E-commerce", "LUCRO REAL", "NÃO CUMULATIVO", 1.65, 7.60
        ),
        PerfilEmpresaFiscal(
            "Mega Mix E-commerce", "LUCRO REAL", "NÃO CUMULATIVO", 1.65, 7.60
        ),
        PerfilEmpresaFiscal(
            "Mega Motos Comércio", "LUCRO PRESUMIDO", "CUMULATIVO", 0.65, 3.00
        ),
        PerfilEmpresaFiscal(
            "Mega Serviços", "SIMPLES NACIONAL", "SIMPLES NACIONAL", None, None
        ),
        PerfilEmpresaFiscal(
            "Mega Serviços Profissionais", "SIMPLES NACIONAL", "SIMPLES NACIONAL", None, None
        ),
    )

    EMPRESAS_ATUAIS: Tuple[Tuple[str, str], ...] = tuple(
        (perfil.nome, perfil.regime) for perfil in PERFIS
    )
    REGIMES = ("LUCRO REAL", "LUCRO PRESUMIDO", "SIMPLES NACIONAL", "MEI", "OUTRO")

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return " ".join(texto.split())

    @classmethod
    def listar_cadastros(
        cls,
        incluir_inativas: bool = False,
        incluir_pessoas_fisicas: bool = False,
    ) -> Tuple[Dict[str, Any], ...]:
        """Retorna o cadastro central persistente do FiscalPro.

        Por padrão, somente pessoas jurídicas entram no contexto fiscal. Pessoas
        físicas podem ser solicitadas explicitamente por módulos administrativos,
        como Contas a Pagar.
        """
        banco = BANCO_ENTREGAS
        if not banco.is_file():
            return ()
        conexao: sqlite3.Connection | None = None
        try:
            uri = banco.resolve().as_uri() + "?mode=ro"
            conexao = sqlite3.connect(uri, uri=True, timeout=3)
            conexao.row_factory = sqlite3.Row
            existe = conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='empresas_entregas'"
            ).fetchone()
            if not existe:
                return ()
            colunas = {
                str(linha[1])
                for linha in conexao.execute("PRAGMA table_info(empresas_entregas)").fetchall()
            }
            campos = ["id", "nome", "cnpj"]
            campos.append("regime" if "regime" in colunas else "'' AS regime")
            campos.append("ativa" if "ativa" in colunas else "1 AS ativa")
            campos.append("manual" if "manual" in colunas else "0 AS manual")
            campos.append(
                "tipo_pessoa" if "tipo_pessoa" in colunas else "'PJ' AS tipo_pessoa"
            )

            filtros: list[str] = []
            if not incluir_inativas:
                filtros.append("ativa = 1")
            if not incluir_pessoas_fisicas and "tipo_pessoa" in colunas:
                filtros.append("COALESCE(tipo_pessoa, 'PJ') <> 'PF'")
            where = f"WHERE {' AND '.join(filtros)}" if filtros else ""

            linhas = conexao.execute(
                f"SELECT {', '.join(campos)} FROM empresas_entregas {where} ORDER BY nome"
            ).fetchall()
            return tuple(dict(linha) for linha in linhas)
        except (OSError, sqlite3.Error):
            return ()
        finally:
            if conexao is not None:
                conexao.close()

    @classmethod
    def _perfil_de_cadastro(cls, cadastro: Dict[str, Any]) -> PerfilEmpresaFiscal | None:
        nome = str(cadastro.get("nome") or "").strip()
        if not nome:
            return None
        regime = cls.normalizar_regime(cadastro.get("regime") or "") or "A DEFINIR"
        if regime == "LUCRO REAL":
            modalidade, pis, cofins = "NÃO CUMULATIVO", 1.65, 7.60
        elif regime == "LUCRO PRESUMIDO":
            modalidade, pis, cofins = "CUMULATIVO", 0.65, 3.00
        elif regime in {"SIMPLES NACIONAL", "MEI"}:
            modalidade, pis, cofins = regime, None, None
        else:
            modalidade, pis, cofins = regime, None, None
        return PerfilEmpresaFiscal(nome, regime, modalidade, pis, cofins)

    @classmethod
    def listar_perfis(cls) -> Tuple[PerfilEmpresaFiscal, ...]:
        # Os perfis em código são apenas defaults de primeira execução. Quando
        # existe cadastro persistente, ele prevalece inclusive para as seis
        # empresas-base; assim uma alteração de regime feita pela usuária passa
        # imediatamente a valer em todos os motores tributários.
        cadastros = cls.listar_cadastros()
        if not cadastros:
            return cls.PERFIS

        por_chave: Dict[str, PerfilEmpresaFiscal] = {
            cls._normalizar_texto(perfil.nome): perfil for perfil in cls.PERFIS
        }
        ordem = [cls._normalizar_texto(perfil.nome) for perfil in cls.PERFIS]
        extras: list[str] = []
        for cadastro in cadastros:
            perfil = cls._perfil_de_cadastro(cadastro)
            if perfil is None:
                continue
            chave = cls._normalizar_texto(perfil.nome)
            if chave not in por_chave:
                extras.append(chave)
            por_chave[chave] = perfil

        # Se uma empresa-base foi explicitamente desativada, ela não volta pela
        # constante em código. O banco é a autoridade quando já existe.
        ativas = {cls._normalizar_texto(str(c.get("nome") or "")) for c in cadastros}
        saida: list[PerfilEmpresaFiscal] = []
        for chave in ordem:
            if chave in ativas and chave in por_chave:
                saida.append(por_chave[chave])
        for chave in sorted(set(extras), key=lambda k: por_chave[k].nome.casefold()):
            saida.append(por_chave[chave])
        return tuple(saida)

    @classmethod
    def listar_empresas(cls, incluir_todas: bool = False) -> Tuple[str, ...]:
        nomes = tuple(perfil.nome for perfil in cls.listar_perfis())
        return (("Todas as empresas",) + nomes) if incluir_todas else nomes

    @classmethod
    def obter_perfil(cls, empresa: Any) -> PerfilEmpresaFiscal | None:
        chave = cls._normalizar_texto(empresa)
        if not chave or chave == "TODAS AS EMPRESAS":
            return None
        for perfil in cls.listar_perfis():
            if cls._normalizar_texto(perfil.nome) == chave:
                return perfil
        return None

    @classmethod
    def _perfis_cadastrados_no_controle_entregas(cls) -> Tuple[PerfilEmpresaFiscal, ...]:
        """Compatibilidade: converte o cadastro central em perfis fiscais."""
        saida: list[PerfilEmpresaFiscal] = []
        for cadastro in cls.listar_cadastros():
            perfil = cls._perfil_de_cadastro(cadastro)
            if perfil is not None:
                saida.append(perfil)
        return tuple(saida)

    @classmethod
    def normalizar_regime(cls, regime: Any) -> str:
        texto = cls._normalizar_texto(regime)
        if not texto:
            return ""
        if "PRESUM" in texto or texto == "CUMULATIVO":
            return "LUCRO PRESUMIDO"
        if "REAL" in texto or "NAO CUMULAT" in texto:
            return "LUCRO REAL"
        if "SIMPLES" in texto:
            return "SIMPLES NACIONAL"
        if texto == "MEI":
            return "MEI"
        return str(regime or "").strip().upper()

    @classmethod
    def regime_por_empresa(cls, empresa: Any, padrao: str = "") -> str:
        perfil = cls.obter_perfil(empresa)
        if perfil is not None:
            return perfil.regime
        return cls.normalizar_regime(padrao)

    @classmethod
    def resolver_regime(cls, empresa: Any = "", regime_informado: Any = "") -> str:
        """Empresa conhecida prevalece; empresa desconhecida mantém o regime informado."""
        return cls.regime_por_empresa(empresa, padrao=str(regime_informado or ""))

    @classmethod
    def aplicar_contexto(cls, contexto: Dict[str, Any] | None) -> Dict[str, Any]:
        """Retorna uma cópia do contexto com regime coerente com a empresa."""
        saida: Dict[str, Any] = dict(contexto or {})
        empresa = saida.get("empresa") or ""
        regime_anterior = saida.get("regime") or ""
        regime_resolvido = cls.resolver_regime(empresa, regime_anterior)
        if regime_resolvido:
            saida["regime"] = regime_resolvido
        perfil = cls.obter_perfil(empresa)
        if perfil is not None:
            saida["regime_origem"] = "EMPRESA"
            saida["regime_piscofins"] = perfil.regime_piscofins
        return saida

    @classmethod
    def aliquotas_padrao_piscofins(
        cls, empresa: Any = "", regime: Any = ""
    ) -> Dict[str, Any]:
        perfil = cls.obter_perfil(empresa)
        if perfil is not None:
            return {
                "empresa": perfil.nome,
                "regime": perfil.regime,
                "regime_piscofins": perfil.regime_piscofins,
                "pis": perfil.pis_padrao,
                "cofins": perfil.cofins_padrao,
            }
        regime_resolvido = cls.normalizar_regime(regime)
        if regime_resolvido == "LUCRO REAL":
            return {
                "empresa": "",
                "regime": regime_resolvido,
                "regime_piscofins": "NÃO CUMULATIVO",
                "pis": 1.65,
                "cofins": 7.60,
            }
        if regime_resolvido == "LUCRO PRESUMIDO":
            return {
                "empresa": "",
                "regime": regime_resolvido,
                "regime_piscofins": "CUMULATIVO",
                "pis": 0.65,
                "cofins": 3.00,
            }
        return {
            "empresa": "",
            "regime": regime_resolvido,
            "regime_piscofins": regime_resolvido,
            "pis": None,
            "cofins": None,
        }

    @classmethod
    def descricao_regime(cls, empresa: Any = "", regime: Any = "") -> str:
        dados = cls.aliquotas_padrao_piscofins(empresa=empresa, regime=regime)
        nome_regime = str(dados.get("regime") or "Regime não definido")
        modalidade = str(dados.get("regime_piscofins") or "").strip()
        pis = dados.get("pis")
        cofins = dados.get("cofins")
        partes = [nome_regime]
        if modalidade and modalidade != nome_regime:
            partes.append(modalidade)
        if pis is not None and cofins is not None:
            partes.append(
                (f"PIS {float(pis):.2f}% • COFINS {float(cofins):.2f}%").replace(".", ",")
            )
        elif nome_regime in {"SIMPLES NACIONAL", "MEI"}:
            partes.append("PIS/COFINS conforme PGDAS-D")
        return " • ".join(partes)
