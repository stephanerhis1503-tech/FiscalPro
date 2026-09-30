"""Regras do Controle de Entregas — Hotfix 17.8.15.

A tela principal passa a funcionar como uma grade mensal por empresa, inspirada
na planilha de controle fornecida pela usuária. Competência e vencimento
continuam independentes, preservando a regra aprovada na Sprint 17.6.1/17.6.2.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from .repositorio import EntregasRepositorio
from src.services.empresas_regimes_service import EmpresasRegimesService


class EntregasServico:
    STATUS = ("PENDENTE", "EM ANDAMENTO", "ENTREGUE", "ATRASADO", "NÃO SE APLICA")
    REGIMES = (
        "LUCRO REAL",
        "LUCRO PRESUMIDO",
        "SIMPLES NACIONAL",
        "MEI",
        "OUTRO",
        "A DEFINIR",
    )
    OPCOES_PRAZO = ("Todos", "Hoje", "Próximos 7 dias", "Este mês", "Próximo mês")

    # Empresas atuais informadas pela usuária. As anteriores permanecem no banco
    # para histórico, mas deixam de aparecer como ativas no controle mensal.
    # Fonte única compartilhada com o módulo Tributação (Hotfix 17.8.26).
    EMPRESAS_ATUAIS = EmpresasRegimesService.EMPRESAS_ATUAIS

    # Colunas atuais da grade. A 17.8.15 remove da visualização os campos
    # DOCUMENTOS, ESCRITURAÇÃO, DAPI, DIF. ALÍQUOTA e REINF, conforme pedido
    # da usuária. Registros históricos desses tipos permanecem no banco.
    # "monetario" controla apenas a apresentação; não executa regra tributária.
    OBRIGACOES_REMOVIDAS_DA_GRADE = (
        "DOCUMENTOS", "ESCRITURAÇÃO", "DAPI", "DIF. ALÍQUOTA", "REINF"
    )
    OBRIGACOES_PADRAO = (
        ("RECEITA MENSAL", "RECEITA MENSAL", True),
        ("CRÉDITO ICMS", "CRÉDITO ICMS", True),
        ("ICMS", "ICMS", True),
        ("SPED FISCAL", "SPED FISCAL", False),
        ("GNRE", "GNRE", True),
        ("ISS", "ISS", True),
        ("EFD CONTRIBUIÇÕES", "EFD CONTRIB.", False),
        ("CRÉDITO PIS", "CRÉDITO PIS", True),
        ("PIS", "PIS", True),
        ("CRÉDITO COFINS", "CRÉDITO COFINS", True),
        ("COFINS", "COFINS", True),
        ("PARCELAMENTO", "PARCELAMENTO", False),
    )
    OBRIGACOES_NOMES = tuple(item[0] for item in OBRIGACOES_PADRAO)
    OBRIGACOES_MONETARIAS = {item[0] for item in OBRIGACOES_PADRAO if item[2]}

    # Dias que estavam explicitamente identificados na planilha de referência.
    # As demais obrigações começam sem prazo fixo (dia 0) para evitar inventar
    # vencimentos que a usuária ainda não configurou.
    PRAZOS_INICIAIS = {
        "ICMS": (8, 1),
        "ISS": (20, 1),
        "PIS": (25, 1),
        "COFINS": (25, 1),
    }

    # Na seção de Lucro Presumido da planilha de referência, os campos de
    # créditos aparecem como não aplicáveis. Isso é apenas um modelo inicial de
    # organização, editável pela usuária — não é uma decisão tributária automática.
    PRESUMIDO_NAO_APLICA_INICIAL = {"CRÉDITO ICMS", "CRÉDITO PIS", "CRÉDITO COFINS"}

    def __init__(self, repositorio: EntregasRepositorio | None = None):
        self.repositorio = repositorio or EntregasRepositorio()

    # ------------------------------------------------------------------
    # Estrutura mensal atual
    # ------------------------------------------------------------------
    def sincronizar_estrutura_atual(self) -> None:
        """Ativa somente as empresas atuais e prepara a grade padrão.

        Nenhuma empresa antiga é apagada; ela é apenas desativada para a tela
        atual. Modelos e entregas históricas continuam preservados no SQLite.
        """
        nomes_atuais = [nome for nome, _ in self.EMPRESAS_ATUAIS]
        for nome, regime in self.EMPRESAS_ATUAIS:
            # Hotfix 17.8.14: corrige a lista da 17.8.13 e grava os regimes
            # confirmados pela usuária. Isso também reativa empresas corretas que
            # a versão anterior possa ter deixado inativas.
            empresa_id = self.repositorio.salvar_empresa(nome, regime=regime)
            self._garantir_modelos_empresa(empresa_id)
        self.repositorio.desativar_empresas_exceto(nomes_atuais)

    def _garantir_modelos_empresa(self, empresa_id: int) -> None:
        empresa = self.repositorio.obter_empresa_por_id(empresa_id)
        regime_efetivo = (
            str(empresa["regime"] or "A DEFINIR").upper()
            if empresa is not None
            else "A DEFINIR"
        )
        for obrigacao, _rotulo, _monetario in self.OBRIGACOES_PADRAO:
            existente = self.repositorio.obter_modelo_por_empresa_tipo(
                empresa_id, obrigacao, incluir_inativo=True
            )
            if existente is not None:
                continue
            dia, meses = self.PRAZOS_INICIAIS.get(obrigacao, (0, 1))
            modelo_id = self.repositorio.salvar_modelo(
                empresa_id=empresa_id,
                tipo_arquivo=obrigacao,
                dia_prazo=dia,
                meses_apos_competencia=meses,
            )
            if (
                regime_efetivo == "LUCRO PRESUMIDO"
                and obrigacao in self.PRESUMIDO_NAO_APLICA_INICIAL
            ):
                self.repositorio.excluir_modelo(modelo_id)

    def cadastrar_empresa(self, nome: str, cnpj: str, regime: str) -> int:
        nome = " ".join((nome or "").strip().split())
        if not nome:
            raise ValueError("Informe o nome/razão social da empresa.")
        cnpj_limpo = "".join(ch for ch in (cnpj or "") if ch.isdigit())
        if len(cnpj_limpo) != 14:
            raise ValueError("Informe um CNPJ válido com 14 dígitos.")
        documento_existente = self.repositorio.obter_empresa_por_documento(cnpj_limpo)
        if documento_existente is not None:
            raise ValueError(
                f"Este CNPJ já está cadastrado para {documento_existente['nome']}. "
                "Edite o cadastro existente em vez de criar outro."
            )
        regime_limpo = " ".join((regime or "").strip().upper().split()) or "A DEFINIR"
        empresa_existente = self.repositorio.obter_empresa_por_nome(nome)
        if empresa_existente is not None and int(empresa_existente["ativa"] or 0):
            raise ValueError("Já existe uma empresa ativa cadastrada com esse nome.")
        empresa_id = self.repositorio.salvar_empresa(
            nome,
            cnpj=cnpj_limpo,
            regime=regime_limpo,
            manual=True,
        )
        self._garantir_modelos_empresa(empresa_id)
        return empresa_id

    def editar_empresa(self, empresa_id: int, nome: str, cnpj: str, regime: str) -> None:
        empresa = self.repositorio.obter_empresa_por_id(empresa_id)
        if empresa is None:
            raise ValueError("Empresa não localizada.")
        nome_limpo = " ".join((nome or "").strip().split())
        if not nome_limpo:
            raise ValueError("Informe o nome/razão social da empresa.")
        cnpj_limpo = "".join(ch for ch in (cnpj or "") if ch.isdigit())
        if len(cnpj_limpo) != 14:
            raise ValueError("Informe um CNPJ válido com 14 dígitos.")
        documento_existente = self.repositorio.obter_empresa_por_documento(
            cnpj_limpo, excluir_id=int(empresa_id)
        )
        if documento_existente is not None:
            raise ValueError(
                f"Este CNPJ já está cadastrado para {documento_existente['nome']}."
            )
        regime_limpo = " ".join((regime or "").strip().upper().split()) or "A DEFINIR"
        nome_original = str(empresa["nome"])
        nomes_fixos = {nome.casefold() for nome, _regime in self.EMPRESAS_ATUAIS}
        if nome_original.casefold() in nomes_fixos and nome_limpo.casefold() != nome_original.casefold():
            raise ValueError(
                "O nome das empresas-base do grupo não pode ser alterado. "
                "Você pode editar o CNPJ e o regime."
            )
        self.repositorio.atualizar_empresa(
            empresa_id,
            nome=nome_limpo,
            cnpj=cnpj_limpo,
            regime=regime_limpo,
        )
        self._garantir_modelos_empresa(empresa_id)

    def grade_competencia(self, competencia: str) -> list[dict[str, object]]:
        competencia_iso = self.competencia_iso(competencia)
        self.atualizar_status()
        linhas: list[dict[str, object]] = []
        ordem_empresas = {nome.casefold(): indice for indice, (nome, _regime) in enumerate(self.EMPRESAS_ATUAIS)}
        empresas = self.repositorio.listar_empresas()
        empresas.sort(key=lambda item: ordem_empresas.get(str(item["nome"]).casefold(), 9999))
        for empresa in empresas:
            empresa_id = int(empresa["id"])
            celulas: dict[str, dict[str, object]] = {}
            for obrigacao, rotulo, monetario in self.OBRIGACOES_PADRAO:
                modelo = self.repositorio.obter_modelo_por_empresa_tipo(
                    empresa_id, obrigacao, incluir_inativo=True
                )
                aplicavel = bool(modelo is not None and int(modelo["ativo"] or 0))
                entrega = self.repositorio.obter_entrega_por_chave(
                    empresa_id, competencia_iso, obrigacao
                )
                if not aplicavel:
                    # Se a obrigação foi desativada depois de uma competência já
                    # entregue, preserva a evidência histórica da entrega. Itens
                    # ainda abertos passam a aparecer como N/A.
                    status = (
                        "ENTREGUE"
                        if entrega is not None and str(entrega["status"] or "") == "ENTREGUE"
                        else "NÃO SE APLICA"
                    )
                else:
                    status = str(entrega["status"] or "PENDENTE") if entrega is not None else "PENDENTE"
                celulas[obrigacao] = {
                    "rotulo": rotulo,
                    "monetario": monetario,
                    "aplicavel": aplicavel,
                    "modelo": modelo,
                    "entrega": entrega,
                    "status": status,
                }
            linhas.append(
                {
                    "empresa": empresa,
                    "celulas": celulas,
                    "observacoes": self.repositorio.obter_observacao_competencia(
                        empresa_id, competencia_iso
                    ),
                }
            )
        return linhas

    def resumo_grade(self, competencia: str) -> dict[str, int]:
        resumo = {
            "pendentes": 0,
            "andamento": 0,
            "entregues": 0,
            "atrasados": 0,
            "nao_aplica": 0,
        }
        for linha in self.grade_competencia(competencia):
            for celula in linha["celulas"].values():
                status = str(celula["status"])
                if status == "EM ANDAMENTO":
                    resumo["andamento"] += 1
                elif status == "ENTREGUE":
                    resumo["entregues"] += 1
                elif status == "ATRASADO":
                    resumo["atrasados"] += 1
                elif status == "NÃO SE APLICA":
                    resumo["nao_aplica"] += 1
                else:
                    resumo["pendentes"] += 1
        return resumo

    def garantir_entrega(self, empresa_id: int, competencia: str, obrigacao: str):
        competencia_iso = self.competencia_iso(competencia)
        atual = self.repositorio.obter_entrega_por_chave(
            int(empresa_id), competencia_iso, obrigacao
        )
        if atual is not None:
            return atual
        modelo = self.repositorio.obter_modelo_por_empresa_tipo(
            int(empresa_id), obrigacao, incluir_inativo=False
        )
        if modelo is None:
            return None
        prazo = self.repositorio.prazo_modelo(
            competencia_iso,
            int(modelo["dia_prazo"]),
            int(modelo["meses_apos_competencia"]),
        )
        entrega_id = self.repositorio.inserir_entrega(
            {
                "empresa_id": int(empresa_id),
                "competencia": competencia_iso,
                "tipo_arquivo": obrigacao,
                "prazo": prazo,
                "status": "PENDENTE",
                "destinatario": str(modelo["destinatario"] or ""),
                "observacoes": str(modelo["observacoes"] or ""),
                "modelo_id": int(modelo["id"]),
            }
        )
        return self.repositorio.obter_entrega(entrega_id)

    @classmethod
    def obrigacao_monetaria(cls, obrigacao: str) -> bool:
        return str(obrigacao) in cls.OBRIGACOES_MONETARIAS

    # ------------------------------------------------------------------
    # Formatação/validação existente
    # ------------------------------------------------------------------
    @staticmethod
    def competencia_iso(valor: str) -> str:
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("Informe a competência.")
        if len(valor) == 7 and valor[4] == "-":
            ano, mes = valor.split("-", 1)
        elif len(valor) == 7 and valor[2] == "/":
            mes, ano = valor.split("/", 1)
        else:
            raise ValueError("Use a competência no formato MM/AAAA.")
        ano_i, mes_i = int(ano), int(mes)
        if not 1 <= mes_i <= 12 or not 2000 <= ano_i <= 2100:
            raise ValueError("Competência inválida.")
        return f"{ano_i:04d}-{mes_i:02d}"

    @staticmethod
    def competencia_br(valor: str) -> str:
        valor = (valor or "").strip()
        if len(valor) == 7 and valor[4] == "-":
            ano, mes = valor.split("-", 1)
            return f"{mes}/{ano}"
        return valor

    @staticmethod
    def periodo_prazo(opcao: str, hoje: date | None = None) -> tuple[str, str]:
        opcao = (opcao or "Todos").strip()
        hoje = hoje or date.today()
        if opcao in ("", "Todos"):
            return "", ""
        if opcao == "Hoje":
            iso = hoje.isoformat()
            return iso, iso
        if opcao == "Próximos 7 dias":
            return hoje.isoformat(), (hoje + timedelta(days=6)).isoformat()
        if opcao == "Este mês":
            inicio = hoje.replace(day=1)
            proximo = date(hoje.year + 1, 1, 1) if hoje.month == 12 else date(hoje.year, hoje.month + 1, 1)
            return inicio.isoformat(), (proximo - timedelta(days=1)).isoformat()
        if opcao == "Próximo mês":
            inicio = date(hoje.year + 1, 1, 1) if hoje.month == 12 else date(hoje.year, hoje.month + 1, 1)
            proximo = date(inicio.year + 1, 1, 1) if inicio.month == 12 else date(inicio.year, inicio.month + 1, 1)
            return inicio.isoformat(), (proximo - timedelta(days=1)).isoformat()
        raise ValueError("Filtro de prazo inválido.")

    @staticmethod
    def data_iso(valor: object, obrigatoria: bool = False) -> str:
        texto = str(valor or "").strip()
        if not texto:
            if obrigatoria:
                raise ValueError("Informe a data.")
            return ""
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto, formato).date().isoformat()
            except ValueError:
                pass
        raise ValueError("Data inválida. Use DD/MM/AAAA.")

    @staticmethod
    def data_br(valor: object) -> str:
        texto = str(valor or "").strip()
        if not texto:
            return ""
        try:
            return datetime.strptime(texto, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return texto

    @staticmethod
    def opcoes_competencia(anos_antes: int = 1, anos_depois: int = 2) -> list[str]:
        hoje = date.today()
        return [
            f"{mes:02d}/{ano}"
            for ano in range(hoje.year - anos_antes, hoje.year + anos_depois + 1)
            for mes in range(1, 13)
        ]

    @staticmethod
    def valor_decimal(valor: object) -> float:
        if valor in (None, ""):
            return 0.0
        if isinstance(valor, (int, float)):
            return float(valor)
        texto = str(valor).strip().replace("R$", "").replace(" ", "")
        if not texto:
            return 0.0
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            return float(texto)
        except ValueError as erro:
            raise ValueError("Valor inválido. Use, por exemplo, 1.234,56.") from erro

    @staticmethod
    def valor_br(valor: object) -> str:
        numero = float(valor or 0)
        return f"R$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def preparar_dados(self, dados: dict[str, object]) -> dict[str, object]:
        empresa_nome = str(dados.get("empresa") or "").strip()
        empresa = self.repositorio.obter_empresa_por_nome(empresa_nome)
        if not empresa or not int(empresa["ativa"]):
            raise ValueError("Selecione uma empresa cadastrada no Controle de Entregas.")
        tipo = " ".join(str(dados.get("tipo_arquivo") or "").strip().split())
        if not tipo:
            raise ValueError("Informe o arquivo ou obrigação.")
        competencia = self.competencia_iso(str(dados.get("competencia") or ""))
        prazo = self.data_iso(dados.get("prazo"))
        data_entrega = self.data_iso(dados.get("data_entrega"))
        status = str(dados.get("status") or "PENDENTE").strip().upper()
        if status not in self.STATUS:
            status = "PENDENTE"
        if status == "NÃO SE APLICA":
            data_entrega = ""
        elif status == "ENTREGUE":
            data_entrega = data_entrega or date.today().isoformat()
        elif data_entrega:
            status = "ENTREGUE"
        elif prazo and prazo < date.today().isoformat():
            status = "ATRASADO"
        elif status != "EM ANDAMENTO":
            status = "PENDENTE"
        return {
            "empresa_id": int(empresa["id"]),
            "competencia": competencia,
            "tipo_arquivo": tipo,
            "prazo": prazo,
            "data_entrega": data_entrega,
            "status": status,
            "destinatario": str(dados.get("destinatario") or "").strip(),
            "caminho_arquivo": str(dados.get("caminho_arquivo") or "").strip(),
            "observacoes": str(dados.get("observacoes") or "").strip(),
            "valor": self.valor_decimal(dados.get("valor")),
            "protocolo": str(dados.get("protocolo") or "").strip(),
        }

    def salvar_entrega(self, dados: dict[str, object], *, entrega_id: int | None = None) -> int:
        preparado = self.preparar_dados(dados)
        try:
            if entrega_id is None:
                return self.repositorio.inserir_entrega(preparado)
            self.repositorio.atualizar_entrega(int(entrega_id), preparado)
            return int(entrega_id)
        except Exception as erro:
            if "UNIQUE constraint failed" in str(erro):
                raise ValueError(
                    "Já existe esse item para a empresa e competência informadas. Edite o lançamento existente."
                ) from erro
            raise

    def gerar_competencia(self, competencia: str, empresa_nome: str = "") -> int:
        competencia_iso = self.competencia_iso(competencia)
        empresa_id = None
        if empresa_nome.strip():
            empresa = self.repositorio.obter_empresa_por_nome(empresa_nome)
            if not empresa:
                raise ValueError("Empresa não cadastrada.")
            empresa_id = int(empresa["id"])
        return self.repositorio.gerar_competencia(competencia_iso, empresa_id)

    def atualizar_status(self, hoje: date | None = None) -> None:
        self.repositorio.atualizar_status_em_lote((hoje or date.today()).isoformat())

    def exportar_csv(
        self,
        destino: str | Path,
        *,
        empresa_id: int | None = None,
        competencia: str = "",
        status: str = "",
        busca: str = "",
        prazo_inicio: str = "",
        prazo_fim: str = "",
    ) -> Path:
        self.atualizar_status()
        linhas = self.repositorio.listar_entregas(
            empresa_id=empresa_id, competencia=competencia, status=status, busca=busca,
            prazo_inicio=prazo_inicio, prazo_fim=prazo_fim
        )
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(
                [
                    "Empresa", "Regime", "Competência", "Arquivo/Obrigação", "Prazo",
                    "Data de entrega", "Status", "Valor", "Protocolo", "Destinatário", "Arquivo salvo", "Observações",
                ]
            )
            for item in linhas:
                escritor.writerow(
                    [
                        item["empresa"], item["regime"] if "regime" in item.keys() else "",
                        self.competencia_br(item["competencia"]), item["tipo_arquivo"],
                        self.data_br(item["prazo"]), self.data_br(item["data_entrega"]),
                        item["status"], self.valor_br(item["valor"] if "valor" in item.keys() else 0),
                        item["protocolo"] if "protocolo" in item.keys() else "",
                        item["destinatario"], item["caminho_arquivo"], item["observacoes"],
                    ]
                )
        return destino

    def exportar_grade_csv(self, destino: str | Path, competencia: str) -> Path:
        competencia_iso = self.competencia_iso(competencia)
        linhas = self.grade_competencia(competencia_iso)
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(
                ["Empresa", "Regime", *[rotulo for _nome, rotulo, _m in self.OBRIGACOES_PADRAO], "Observações"]
            )
            for linha in linhas:
                empresa = linha["empresa"]
                saida = [str(empresa["nome"]), str(empresa["regime"] or "A DEFINIR")]
                for obrigacao, _rotulo, monetario in self.OBRIGACOES_PADRAO:
                    celula = linha["celulas"][obrigacao]
                    texto = str(celula["status"])
                    entrega = celula["entrega"]
                    if monetario and entrega is not None and float(entrega["valor"] or 0):
                        texto += f" | {self.valor_br(entrega['valor'])}"
                    saida.append(texto)
                saida.append(str(linha["observacoes"] or ""))
                escritor.writerow(saida)
        return destino
