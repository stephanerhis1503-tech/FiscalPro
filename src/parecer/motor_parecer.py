"""Motor do Parecer Tributário Inteligente — Sprint 13.4.

O motor trabalha apenas com dados já cadastrados no FiscalPro. Ele seleciona a
regra mais aderente ao contexto da operação, explica os critérios usados e
mantém rastreabilidade da regra, da base legal e do nível de confiança.
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass
class ParecerTributario:
    ncm: str
    descricao: str
    contexto: Dict[str, str]
    dados_gerais: Dict[str, Any]
    tributacao_atual: Dict[str, Any]
    reforma: Dict[str, Any]
    creditos: Dict[str, str]
    base_legal: List[str] = field(default_factory=list)
    conclusoes: List[str] = field(default_factory=list)
    alertas: List[str] = field(default_factory=list)
    pendencias: List[str] = field(default_factory=list)
    fundamentos: List[str] = field(default_factory=list)
    fontes: List[str] = field(default_factory=list)
    regras_aplicadas: Dict[str, Any] = field(default_factory=dict)
    resumo_executivo: str = ""
    confiabilidade: float = 0.0
    nivel_confiabilidade: str = "BAIXA"
    gerado_em: str = ""
    versao_motor: str = "13.4"

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def secoes(self) -> List[Tuple[str, Any]]:
        return [
            ("RESUMO EXECUTIVO", self.resumo_executivo),
            ("CONTEXTO CONSIDERADO", self.contexto),
            ("DADOS GERAIS", self.dados_gerais),
            ("TRIBUTAÇÃO ATUAL", self.tributacao_atual),
            ("REFORMA TRIBUTÁRIA", self.reforma),
            ("ANÁLISE DE CRÉDITOS", self.creditos),
            ("CONCLUSÕES", self.conclusoes),
            ("FUNDAMENTOS", self.fundamentos),
            ("ALERTAS E RISCOS", self.alertas),
            ("PENDÊNCIAS PARA CONCLUSÃO", self.pendencias),
            ("BASE LEGAL", self.base_legal),
            ("FONTES", self.fontes),
            ("RASTREABILIDADE", self.regras_aplicadas),
        ]

    def para_texto(self) -> str:
        linhas = [
            "PARECER TRIBUTÁRIO INTELIGENTE",
            "=" * 78,
            f"NCM: {self.ncm}",
            f"Descrição: {self.descricao}",
            f"Confiabilidade: {self.confiabilidade:.0f}% ({self.nivel_confiabilidade})",
            f"Gerado em: {self.gerado_em}",
            f"Motor: FiscalPro {self.versao_motor}",
        ]
        for titulo, conteudo in self.secoes():
            linhas.extend(["", titulo, "-" * 78])
            if isinstance(conteudo, dict):
                if conteudo:
                    linhas.extend(f"• {campo}: {valor}" for campo, valor in conteudo.items())
                else:
                    linhas.append("• Não informado.")
            elif isinstance(conteudo, (list, tuple)):
                linhas.extend(f"• {item}" for item in conteudo) if conteudo else linhas.append("• Nenhum item.")
            else:
                linhas.append(str(conteudo or "Não informado."))
        linhas.extend(
            [
                "",
                "IMPORTANTE",
                "-" * 78,
                "Este parecer organiza e explica os dados cadastrados no FiscalPro. "
                "A conclusão fiscal deve ser confirmada conforme a operação real e a fonte oficial vigente.",
            ]
        )
        return "\n".join(linhas)


@dataclass
class _SelecaoRegra:
    regra: Optional[Dict[str, Any]]
    pontuacao: float = 0.0
    pontuacao_maxima: float = 0.0
    criterios: List[str] = field(default_factory=list)
    genericos: List[str] = field(default_factory=list)
    empatadas: int = 0

    @property
    def aderencia(self) -> float:
        if not self.regra or self.pontuacao_maxima <= 0:
            return 0.0
        return max(0.0, min(100.0, (self.pontuacao / self.pontuacao_maxima) * 100.0))


class MotorParecer:
    """Seleciona regras e produz parecer técnico rastreável."""

    CAMPOS_CONTEXTO = (
        "empresa", "regime", "operacao", "finalidade", "uf_origem", "uf_destino", "contribuinte"
    )

    @staticmethod
    def _texto(valor: Any) -> str:
        return str(valor or "").strip()

    @classmethod
    def _normalizar(cls, valor: Any) -> str:
        texto = cls._texto(valor).upper()
        texto = "".join(
            caractere for caractere in unicodedata.normalize("NFD", texto)
            if unicodedata.category(caractere) != "Mn"
        )
        return " ".join(texto.split())

    @staticmethod
    def _numero(valor: Any) -> float:
        if valor in (None, ""):
            return 0.0
        if isinstance(valor, (int, float)):
            return float(valor)
        texto = str(valor).strip().replace("%", "").replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            return float(texto)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _sim(cls, valor: Any) -> bool:
        return cls._normalizar(valor) in {"SIM", "S", "1", "TRUE", "ST"}

    @staticmethod
    def _data_iso(valor: Any, padrao: Optional[str] = None) -> Optional[str]:
        texto = str(valor or "").strip()
        if not texto:
            return padrao
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto[:10], formato).date().isoformat()
            except ValueError:
                continue
        return padrao

    @staticmethod
    def _data_br(valor: Any) -> str:
        texto = str(valor or "").strip()
        if not texto:
            return "Não informada"
        try:
            return datetime.strptime(texto[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return texto

    @classmethod
    def _valor_contexto(cls, contexto: Dict[str, Any], chave: str, padrao: str = "") -> str:
        aliases = {
            "contribuinte": ("contribuinte", "destinatario", "consumidor_final"),
            "operacao": ("operacao", "operação"),
        }
        for nome in aliases.get(chave, (chave,)):
            valor = cls._texto(contexto.get(nome))
            if valor:
                return valor
        return padrao

    @classmethod
    def _contexto_normalizado(cls, contexto: Optional[Dict[str, Any]]) -> Dict[str, str]:
        contexto = contexto or {}
        data_operacao = cls._data_iso(contexto.get("data_operacao"), date.today().isoformat())
        contribuinte = cls._valor_contexto(contexto, "contribuinte", "TODOS")
        if cls._normalizar(contribuinte) in {"SIM", "CONTRIBUINTE"}:
            contribuinte = "CONTRIBUINTE"
        elif cls._normalizar(contribuinte) in {"NAO", "NÃO", "NAO CONTRIBUINTE", "NÃO CONTRIBUINTE"}:
            contribuinte = "NÃO CONTRIBUINTE"
        elif cls._normalizar(contribuinte) in {"TODOS", "NAO INFORMADO", "NÃO INFORMADO", ""}:
            contribuinte = "TODOS"

        return {
            "empresa": cls._valor_contexto(contexto, "empresa", "Todas as empresas"),
            "regime": cls._valor_contexto(contexto, "regime", "Não informado"),
            "operacao": cls._valor_contexto(contexto, "operacao", "Não informada"),
            "finalidade": cls._valor_contexto(contexto, "finalidade", "Não informada"),
            "uf_origem": cls._valor_contexto(contexto, "uf_origem", "Não informada").upper(),
            "uf_destino": cls._valor_contexto(contexto, "uf_destino", "Não informada").upper(),
            "contribuinte": contribuinte,
            "data_operacao": data_operacao or date.today().isoformat(),
        }

    @classmethod
    def _campo_generico(cls, valor: Any, campo: str) -> bool:
        norm = cls._normalizar(valor)
        genericos = {"", "TODOS", "TODAS", "TODAS AS EMPRESAS", "NAO INFORMADO", "NAO INFORMADA"}
        if campo in {"uf_origem", "uf_destino"}:
            genericos |= {"TODAS AS UFS"}
        return norm in genericos

    @classmethod
    def _pontuar_regra(cls, regra: Dict[str, Any], contexto: Dict[str, str]) -> Optional[_SelecaoRegra]:
        status = cls._normalizar(regra.get("status"))
        tipo_origem = cls._normalizar(regra.get("tipo_origem"))
        data_op = contexto["data_operacao"]
        inicio = cls._data_iso(regra.get("vigencia_inicio"))
        fim = cls._data_iso(regra.get("vigencia_fim"))

        if status == "RASCUNHO":
            return None
        if inicio and data_op < inicio:
            return None
        if fim and data_op > fim:
            return None
        if status in {"ENCERRADA", "REVOGADA"} and not (inicio and fim and inicio <= data_op <= fim):
            return None

        pesos = {
            "empresa": 18,
            "uf_origem": 10,
            "uf_destino": 14,
            "regime": 13,
            "operacao": 13,
            "finalidade": 10,
            "contribuinte": 8,
        }
        pontuacao = 0.0
        maxima = float(sum(pesos.values()) + 15 + 10)
        criterios: List[str] = []
        genericos: List[str] = []

        for campo, peso in pesos.items():
            valor_regra = regra.get(campo)
            valor_contexto = contexto.get(campo)
            if campo == "empresa" and cls._normalizar(valor_regra) == "TODAS":
                valor_regra = ""
            if cls._campo_generico(valor_regra, campo):
                pontuacao += peso * 0.35
                genericos.append(campo)
                criterios.append(f"{campo}: regra genérica")
                continue
            if cls._campo_generico(valor_contexto, campo):
                pontuacao += peso * 0.15
                genericos.append(f"contexto {campo}")
                criterios.append(f"{campo}: contexto não informado")
                continue
            if cls._normalizar(valor_regra) != cls._normalizar(valor_contexto):
                return None
            pontuacao += peso
            criterios.append(f"{campo}: correspondência exata")

        if inicio or fim:
            pontuacao += 15
            criterios.append("vigência: data da operação abrangida")
        else:
            pontuacao += 5
            genericos.append("vigência")
            criterios.append("vigência: não delimitada")

        confiabilidade = max(0.0, min(100.0, cls._numero(regra.get("confiabilidade"))))
        pontuacao += confiabilidade / 10.0
        criterios.append(f"confiabilidade cadastrada: {confiabilidade:.0f}%")

        if tipo_origem == "TRIBUTACAO_BASE" or status == "OPERACIONAL":
            pontuacao -= 8
            genericos.append("cadastro operacional por produto")
            criterios.append("origem: cadastro operacional, sem contexto completo")
        elif tipo_origem in {"TRIBUTACAO_ATUAL", "TRIBUTACAO_REFORMA"}:
            pontuacao += 4
            maxima += 4
            criterios.append("origem: regra tributária versionada")

        return _SelecaoRegra(
            regra=dict(regra),
            pontuacao=pontuacao,
            pontuacao_maxima=maxima,
            criterios=criterios,
            genericos=genericos,
        )

    @classmethod
    def _selecionar_regra(cls, regras: Sequence[Dict[str, Any]], contexto: Dict[str, str]) -> _SelecaoRegra:
        candidatas: List[_SelecaoRegra] = []
        for regra in regras or []:
            pontuada = cls._pontuar_regra(regra, contexto)
            if pontuada is not None:
                candidatas.append(pontuada)
        if not candidatas:
            return _SelecaoRegra(None)
        candidatas.sort(
            key=lambda item: (
                item.pontuacao,
                cls._data_iso(item.regra.get("vigencia_inicio"), "") if item.regra else "",
                cls._numero(item.regra.get("id")) if item.regra else 0,
            ),
            reverse=True,
        )
        melhor = candidatas[0]
        melhor.empatadas = sum(1 for item in candidatas if abs(item.pontuacao - melhor.pontuacao) < 0.01)
        return melhor

    @classmethod
    def _base_legal_aplicavel(
        cls, normas: Sequence[Dict[str, Any]], contexto: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        data_op = contexto["data_operacao"]
        aplicaveis: List[Dict[str, Any]] = []
        for norma in normas or []:
            status = cls._normalizar(norma.get("status"))
            if status == "RASCUNHO":
                continue
            inicio = cls._data_iso(norma.get("vigencia_inicio") or norma.get("data_publicacao"))
            fim = cls._data_iso(norma.get("vigencia_fim"))
            if inicio and data_op < inicio:
                continue
            if fim and data_op > fim:
                continue
            if status in {"REVOGADA", "ENCERRADA"} and not (inicio and fim and inicio <= data_op <= fim):
                continue
            aplicaveis.append(dict(norma))
        aplicaveis.sort(
            key=lambda item: (
                int(bool(item.get("origem_oficial"))),
                cls._numero(item.get("confiabilidade")),
                cls._data_iso(item.get("vigencia_inicio") or item.get("data_publicacao"), ""),
            ),
            reverse=True,
        )
        return aplicaveis

    @classmethod
    def _formatar_norma(cls, norma: Dict[str, Any]) -> str:
        identificacao = " ".join(
            parte for parte in (
                cls._texto(norma.get("tipo_norma")),
                cls._texto(norma.get("numero_norma")),
            ) if parte
        ) or "Norma sem identificação"
        artigo = cls._texto(norma.get("artigo_item"))
        descricao = cls._texto(norma.get("descricao") or norma.get("assunto"))
        impacto = cls._texto(norma.get("impacto_tributario"))
        partes = [identificacao]
        if artigo:
            partes.append(artigo)
        if descricao:
            partes.append(descricao)
        if impacto:
            partes.append(f"Impacto: {impacto}")
        return " — ".join(partes)

    @classmethod
    def _credito_piscofins(cls, regime: str, operacao: str, finalidade: str, aliquota: float) -> str:
        reg = cls._normalizar(regime)
        op = cls._normalizar(operacao)
        fim = cls._normalizar(finalidade)
        if aliquota <= 0:
            return "NÃO IDENTIFICADO NA REGRA SELECIONADA"
        if "LUCRO REAL" in reg and op in {"ENTRADA", "COMPRA", "IMPORTACAO"}:
            if fim in {"REVENDA", "INDUSTRIALIZACAO", "INSUMO"}:
                return "POTENCIAL — conferir natureza do crédito e vedações legais"
            return "DEPENDE DA DESTINAÇÃO E DAS VEDAÇÕES DO REGIME NÃO CUMULATIVO"
        if "LUCRO REAL" in reg:
            return "NÃO SE CONCLUI CRÉDITO EM OPERAÇÃO DE SAÍDA"
        return "EM REGRA NÃO CUMULATIVO NÃO CONFIRMADO PARA O REGIME INFORMADO"

    @classmethod
    def _analise_creditos(cls, regra: Optional[Dict[str, Any]], contexto: Dict[str, str]) -> Dict[str, str]:
        regra = regra or {}
        operacao = contexto["operacao"]
        finalidade = contexto["finalidade"]
        regime = contexto["regime"]
        entrada = cls._normalizar(operacao) in {"ENTRADA", "COMPRA", "IMPORTACAO"}
        icms = cls._numero(regra.get("icms"))
        ipi = cls._numero(regra.get("ipi"))
        return {
            "ICMS": (
                "POTENCIAL — validar destaque, documento idôneo, destinação e vedações"
                if entrada and icms > 0 else
                "NÃO CONCLUÍDO PARA O CONTEXTO INFORMADO"
            ),
            "PIS": cls._credito_piscofins(regime, operacao, finalidade, cls._numero(regra.get("aliquota_pis"))),
            "COFINS": cls._credito_piscofins(regime, operacao, finalidade, cls._numero(regra.get("aliquota_cofins"))),
            "IPI": (
                "VALIDAR — depende do estabelecimento, destaque e destinação"
                if entrada and ipi > 0 else
                "NÃO IDENTIFICADO NA REGRA SELECIONADA"
            ),
        }

    @classmethod
    def _nivel(cls, confiabilidade: float) -> str:
        if confiabilidade >= 85:
            return "ALTA"
        if confiabilidade >= 65:
            return "MÉDIA"
        return "BAIXA"

    @classmethod
    def _confiabilidade(
        cls,
        selecao_atual: _SelecaoRegra,
        selecao_reforma: _SelecaoRegra,
        normas: Sequence[Dict[str, Any]],
        contexto: Dict[str, str],
        alertas: Sequence[str],
    ) -> float:
        pontos = 0.0
        pontos += selecao_atual.aderencia * 0.55
        pontos += selecao_reforma.aderencia * 0.12 if selecao_reforma.regra else 3.0
        if normas:
            oficiais = [n for n in normas if int(n.get("origem_oficial") or 0)]
            media_legal = sum(cls._numero(n.get("confiabilidade")) for n in normas[:5]) / min(len(normas), 5)
            pontos += min(18.0, media_legal * 0.15 + (3.0 if oficiais else 0.0))
        completos = sum(
            1 for chave in cls.CAMPOS_CONTEXTO
            if not cls._campo_generico(contexto.get(chave), chave)
        )
        pontos += (completos / len(cls.CAMPOS_CONTEXTO)) * 12.0
        pontos -= min(15.0, len(alertas) * 2.0)
        return max(0.0, min(100.0, pontos))

    @classmethod
    def _gerar_dados_ficha(cls, dados_ficha: Dict[str, Any], contexto_entrada: Optional[Dict[str, Any]]) -> ParecerTributario:
        contexto = cls._contexto_normalizado(contexto_entrada)
        dados = dict(dados_ficha.get("dados_gerais") or {})
        selecao_atual = cls._selecionar_regra(dados_ficha.get("tributacoes") or [], contexto)
        selecao_reforma = cls._selecionar_regra(dados_ficha.get("reforma") or [], contexto)
        regra = selecao_atual.regra or {}
        regra_reforma = selecao_reforma.regra or {}
        normas = cls._base_legal_aplicavel(dados_ficha.get("base_legal") or [], contexto)

        ncm = cls._texto(dados.get("ncm"))
        descricao = cls._texto(dados.get("descricao")) or "Descrição não cadastrada"
        alertas: List[str] = []
        pendencias: List[str] = []
        conclusoes: List[str] = []
        fundamentos: List[str] = []

        if not selecao_atual.regra:
            alertas.append("Nenhuma regra de tributação atual abrange integralmente o contexto e a data informados.")
            pendencias.append("Cadastrar ou revisar uma regra vigente para a operação consultada.")
        else:
            origem = cls._texto(regra.get("origem")) or cls._texto(regra.get("tipo_origem"))
            conclusoes.append(
                f"Foi selecionada a regra '{origem or 'tributária'}' com aderência de {selecao_atual.aderencia:.0f}% ao contexto."
            )
            if regra.get("cfop"):
                conclusoes.append(f"CFOP indicado pela regra: {regra.get('cfop')}.")
            if cls._numero(regra.get("icms")) > 0:
                conclusoes.append(f"Alíquota de ICMS cadastrada: {cls._numero(regra.get('icms')):.2f}%.")
            if cls._sim(regra.get("icms_st")):
                conclusoes.append("A regra selecionada indica incidência de ICMS-ST.")
                if not normas:
                    alertas.append("ICMS-ST foi indicado sem base legal vigente vinculada ao NCM para a data consultada.")
            if selecao_atual.genericos:
                alertas.append(
                    "A regra selecionada contém critérios genéricos: " + ", ".join(selecao_atual.genericos) + "."
                )
            if selecao_atual.empatadas > 1:
                alertas.append(
                    f"Existem {selecao_atual.empatadas} regras com a mesma pontuação; revise a vigência e o contexto."
                )

        if selecao_reforma.regra:
            classificacao = regra_reforma.get("cclasstrib") or regra_reforma.get("classificacao")
            conclusoes.append(
                "Há enquadramento de Reforma Tributária aplicável"
                + (f" com cClassTrib {classificacao}." if classificacao else ", porém sem cClassTrib informado.")
            )
            if not classificacao:
                pendencias.append("Confirmar e cadastrar o cClassTrib aplicável.")
            if selecao_reforma.genericos:
                alertas.append(
                    "O enquadramento de IBS/CBS usa critérios genéricos: " + ", ".join(selecao_reforma.genericos) + "."
                )
        else:
            alertas.append("Não há regra específica de IBS/CBS aplicável ao contexto e à data informados.")
            pendencias.append("Cadastrar ou validar o enquadramento da Reforma Tributária.")

        if not normas:
            alertas.append("Nenhuma base legal vigente foi vinculada ao NCM para a data da operação.")
            pendencias.append("Vincular a legislação oficial que fundamenta a conclusão.")
        else:
            fundamentos.append(
                f"Foram consideradas {len(normas)} norma(s) vigente(s) ou historicamente aplicável(is) na data consultada."
            )
            if not any(int(n.get("origem_oficial") or 0) for n in normas):
                alertas.append("A base legal encontrada não está marcada como fonte oficial.")

        for chave, rotulo in (
            ("regime", "regime tributário"),
            ("operacao", "operação"),
            ("finalidade", "finalidade"),
            ("uf_origem", "UF de origem"),
            ("uf_destino", "UF de destino"),
        ):
            if cls._campo_generico(contexto.get(chave), chave):
                pendencias.append(f"Informar {rotulo} para aumentar a precisão do parecer.")

        fundamentos.extend(selecao_atual.criterios)
        if selecao_reforma.regra:
            fundamentos.extend(f"Reforma — {item}" for item in selecao_reforma.criterios)

        confiabilidade = cls._confiabilidade(selecao_atual, selecao_reforma, normas, contexto, alertas)
        nivel = cls._nivel(confiabilidade)
        resumo = (
            f"Para o NCM {ncm}, o FiscalPro "
            + ("identificou uma regra tributária aplicável" if selecao_atual.regra else "não encontrou regra tributária conclusiva")
            + f" para {contexto['operacao'].lower()} com destino a {contexto['uf_destino']}. "
            + f"O parecer possui confiança {nivel.lower()} ({confiabilidade:.0f}%)."
        )

        tributacao = {
            "Regra aplicada": cls._texto(regra.get("origem")) or cls._texto(regra.get("tipo_origem")) or "Não localizada",
            "ID da regra": regra.get("id") if regra else "",
            "Status": regra.get("status") or "Não informado",
            "Vigência": f"{cls._data_br(regra.get('vigencia_inicio'))} a {cls._data_br(regra.get('vigencia_fim')) if regra.get('vigencia_fim') else 'sem data final'}" if regra else "Não informada",
            "CFOP": regra.get("cfop") or "Não informado",
            "CEST": regra.get("cest") or "Não informado",
            "MVA ST": cls._numero(regra.get("mva_st")),
            "Revisão manual": bool(int(regra.get("revisao_manual") or 0)) if str(regra.get("revisao_manual") or "").strip().isdigit() else bool(regra.get("revisao_manual")),
            "Tipo da regra": regra.get("tipo_origem") or "",
            "CST/CSOSN ICMS": regra.get("cst_icms") or "Não informado",
            "ICMS": cls._numero(regra.get("icms")),
            "ICMS-ST": regra.get("icms_st") or "Não informado",
            "FCP": cls._numero(regra.get("fcp")),
            "CST PIS": regra.get("cst_pis") or regra.get("pis_cst") or "Não informado",
            "PIS": cls._numero(regra.get("aliquota_pis")),
            "CST COFINS": regra.get("cst_cofins") or regra.get("cofins_cst") or "Não informado",
            "COFINS": cls._numero(regra.get("aliquota_cofins")),
            "CST IPI": regra.get("cst_ipi") or "Não informado",
            "IPI": cls._numero(regra.get("ipi")),
            "Benefício/Regime especial": regra.get("beneficio") or "Não informado",
            "Fonte da regra": regra.get("fonte") or "Não informada",
            "Aderência ao contexto": f"{selecao_atual.aderencia:.0f}%",
        }
        reforma = {
            "Regra aplicada": cls._texto(regra_reforma.get("tipo_origem")) or "Não localizada",
            "ID da regra": regra_reforma.get("id") if regra_reforma else "",
            "Status": regra_reforma.get("status") or "Não informado",
            "cClassTrib": regra_reforma.get("cclasstrib") or regra_reforma.get("classificacao") or "Não informado",
            "CST IBS": regra_reforma.get("cst_ibs") or "Não informado",
            "IBS": cls._numero(regra_reforma.get("aliquota_ibs")),
            "Redução IBS": cls._numero(regra_reforma.get("reducao_ibs")),
            "CST CBS": regra_reforma.get("cst_cbs") or "Não informado",
            "CBS": cls._numero(regra_reforma.get("aliquota_cbs")),
            "Redução CBS": cls._numero(regra_reforma.get("reducao_cbs")),
            "Crédito presumido": regra_reforma.get("ccredpres") or "Não informado",
            "Diferimento": regra_reforma.get("diferimento") or "Não informado",
            "Imposto Seletivo": regra_reforma.get("imposto_seletivo") or "Não informado",
            "Fonte da regra": regra_reforma.get("fonte") or "Não informada",
            "Aderência ao contexto": f"{selecao_reforma.aderencia:.0f}%" if regra_reforma else "0%",
        }

        fontes: List[str] = []
        for valor in (regra.get("fonte"), regra_reforma.get("fonte")):
            if cls._texto(valor):
                fontes.append(cls._texto(valor))
        for norma in normas:
            for valor in (norma.get("fonte"), norma.get("url")):
                if cls._texto(valor):
                    fontes.append(cls._texto(valor))
        fontes = list(dict.fromkeys(fontes))

        contexto_exibicao = {
            "Empresa": contexto["empresa"],
            "Regime": contexto["regime"],
            "Operação": contexto["operacao"],
            "Finalidade": contexto["finalidade"],
            "UF origem": contexto["uf_origem"],
            "UF destino": contexto["uf_destino"],
            "Destinatário": contexto["contribuinte"],
            "Data da operação": cls._data_br(contexto["data_operacao"]),
        }

        regras_aplicadas = {
            "Regra atual": f"ID {regra.get('id')}" if regra.get("id") is not None else "Sem ID/Não localizada",
            "Origem da regra atual": regra.get("tipo_origem") or regra.get("origem") or "Não localizada",
            "Aderência da regra atual": f"{selecao_atual.aderencia:.0f}%",
            "Regra da reforma": f"ID {regra_reforma.get('id')}" if regra_reforma.get("id") is not None else "Sem ID/Não localizada",
            "Aderência da reforma": f"{selecao_reforma.aderencia:.0f}%" if regra_reforma else "0%",
            "Normas consideradas": len(normas),
            "Data-base": cls._data_br(contexto["data_operacao"]),
        }

        return ParecerTributario(
            ncm=ncm,
            descricao=descricao,
            contexto=contexto_exibicao,
            dados_gerais={
                "NCM": ncm,
                "Descrição": descricao,
                "CEST": regra.get("cest") or dados.get("cest") or "Não informado",
                "EX TIPI": dados.get("ex_tipi") or "Não informado",
                "Status": dados.get("status") or "Não informado",
                "Produtos cadastrados": dados.get("total_produtos") or 0,
                "Empresas com produtos": dados.get("total_empresas") or 0,
                "Última atualização": dados.get("atualizado_em") or "Não informada",
            },
            tributacao_atual=tributacao,
            reforma=reforma,
            creditos=cls._analise_creditos(regra, contexto),
            base_legal=[cls._formatar_norma(norma) for norma in normas],
            conclusoes=conclusoes,
            alertas=list(dict.fromkeys(alertas)),
            pendencias=list(dict.fromkeys(pendencias)),
            fundamentos=list(dict.fromkeys(fundamentos)),
            fontes=fontes,
            regras_aplicadas=regras_aplicadas,
            resumo_executivo=resumo,
            confiabilidade=confiabilidade,
            nivel_confiabilidade=nivel,
            gerado_em=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        )

    @classmethod
    def _adaptar_ficha_antiga(cls, ficha: Any) -> Dict[str, Any]:
        tributacao = {
            "id": None,
            "tipo_origem": "compatibilidade",
            "origem": "Ficha tributária anterior",
            "empresa": "",
            "uf_origem": "",
            "uf_destino": getattr(ficha, "uf", ""),
            "regime": getattr(ficha, "regime", ""),
            "operacao": getattr(ficha, "operacao", ""),
            "finalidade": "",
            "contribuinte": "TODOS",
            "cfop": getattr(ficha, "cfop", ""),
            "cst_icms": getattr(ficha, "cst_icms", ""),
            "icms": getattr(ficha, "icms", 0),
            "icms_st": getattr(ficha, "icms_st", ""),
            "fcp": getattr(ficha, "fcp", 0),
            "cst_pis": getattr(ficha, "pis_cst", ""),
            "aliquota_pis": getattr(ficha, "aliquota_pis", 0),
            "cst_cofins": getattr(ficha, "cofins_cst", ""),
            "aliquota_cofins": getattr(ficha, "aliquota_cofins", 0),
            "cst_ipi": getattr(ficha, "cst_ipi", ""),
            "ipi": getattr(ficha, "ipi", 0),
            "confiabilidade": getattr(ficha, "confiabilidade", 0),
            "status": "VIGENTE",
        }
        reforma = {
            "id": None,
            "tipo_origem": "compatibilidade",
            "empresa": "",
            "uf_origem": "",
            "uf_destino": getattr(ficha, "uf", ""),
            "regime": getattr(ficha, "regime", ""),
            "operacao": getattr(ficha, "operacao", ""),
            "finalidade": "",
            "contribuinte": "TODOS",
            "cclasstrib": getattr(ficha, "cclasstrib", ""),
            "ccredpres": getattr(ficha, "ccredpres", ""),
            "cst_ibs": getattr(ficha, "cst_ibs", ""),
            "cst_cbs": getattr(ficha, "cst_cbs", ""),
            "aliquota_ibs": getattr(ficha, "aliquota_ibs", 0),
            "aliquota_cbs": getattr(ficha, "aliquota_cbs", 0),
            "imposto_seletivo": getattr(ficha, "imposto_seletivo", ""),
            "confiabilidade": getattr(ficha, "confiabilidade", 0),
            "status": "VIGENTE",
        }
        legais = [
            {"descricao": item, "status": "VIGENTE", "confiabilidade": 50, "origem_oficial": 0}
            for item in (getattr(ficha, "base_legal", []) or [])
        ]
        return {
            "dados_gerais": {
                "ncm": getattr(ficha, "ncm", ""),
                "descricao": getattr(ficha, "descricao", ""),
                "cest": getattr(ficha, "cest", ""),
                "status": getattr(ficha, "status", "LOCAL"),
                "total_produtos": getattr(ficha, "quantidade_produtos", 0),
            },
            "tributacoes": [tributacao],
            "reforma": [reforma] if any(reforma.get(k) for k in ("cclasstrib", "cst_ibs", "cst_cbs")) else [],
            "base_legal": legais,
        }

    @classmethod
    def gerar(cls, fonte: Any, contexto: Optional[Dict[str, Any]] = None) -> ParecerTributario:
        if isinstance(fonte, dict) and "dados_gerais" in fonte:
            return cls._gerar_dados_ficha(fonte, contexto)
        return cls._gerar_dados_ficha(cls._adaptar_ficha_antiga(fonte), contexto)
