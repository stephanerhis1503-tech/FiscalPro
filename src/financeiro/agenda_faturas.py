"""Agenda inteligente de faturas recorrentes do Contas a Pagar.

Controla a obrigação de buscar/baixar faturas antes que elas existam como contas
financeiras. Usa o mesmo banco do Contas a Pagar para que agenda e lançamentos
participem do mesmo fluxo de backup/restauração.
"""

from __future__ import annotations

import calendar
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .repositorio import ContasPagarRepositorio


STATUS_AGUARDANDO = "AGUARDANDO FATURA"
STATUS_BAIXADA = "FATURA BAIXADA"
STATUS_LANCADA = "LANÇADA"
STATUS_PAGA = "PAGA"
STATUS_AGENDA = (STATUS_AGUARDANDO, STATUS_BAIXADA, STATUS_LANCADA, STATUS_PAGA)

TIPOS_FATURA = ("ÁGUA", "ENERGIA", "INTERNET", "TELEFONE", "OUTROS")


class AgendaFaturasServico:
    """Persistência e regras da agenda mensal de faturas."""

    def __init__(self, repositorio: "ContasPagarRepositorio"):
        self.repositorio = repositorio
        self.preparar_banco()

    def preparar_banco(self) -> None:
        with self.repositorio._conectar() as conexao:
            conexao.executescript(
                """
                CREATE TABLE IF NOT EXISTS agenda_faturas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa TEXT NOT NULL,
                    fornecedor TEXT NOT NULL,
                    tipo_fatura TEXT NOT NULL DEFAULT 'OUTROS',
                    categoria TEXT NOT NULL DEFAULT 'OUTROS',
                    dia_disponibilidade INTEGER NOT NULL DEFAULT 1,
                    dia_vencimento INTEGER NOT NULL DEFAULT 10,
                    dias_alerta INTEGER NOT NULL DEFAULT 3,
                    competencia_inicial TEXT NOT NULL,
                    recorrente INTEGER NOT NULL DEFAULT 1,
                    ativa INTEGER NOT NULL DEFAULT 1,
                    observacoes TEXT NOT NULL DEFAULT '',
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_agenda_faturas_empresa
                    ON agenda_faturas(empresa, ativa);

                CREATE TABLE IF NOT EXISTS agenda_faturas_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lembrete_id INTEGER NOT NULL,
                    competencia TEXT NOT NULL,
                    data_prevista TEXT NOT NULL,
                    vencimento_previsto TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'AGUARDANDO FATURA',
                    caminho_documento TEXT NOT NULL DEFAULT '',
                    conta_id INTEGER,
                    baixada_em TEXT NOT NULL DEFAULT '',
                    lancada_em TEXT NOT NULL DEFAULT '',
                    concluida_em TEXT NOT NULL DEFAULT '',
                    atualizado_em TEXT NOT NULL,
                    UNIQUE(lembrete_id, competencia),
                    FOREIGN KEY(lembrete_id) REFERENCES agenda_faturas(id) ON DELETE CASCADE,
                    FOREIGN KEY(conta_id) REFERENCES contas_pagar(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_agenda_itens_competencia
                    ON agenda_faturas_itens(competencia, status);
                CREATE INDEX IF NOT EXISTS idx_agenda_itens_conta
                    ON agenda_faturas_itens(conta_id);
                """
            )

    @staticmethod
    def _competencia_iso(valor: object) -> str:
        texto = str(valor or "").strip()
        if not texto:
            return date.today().strftime("%Y-%m")
        if len(texto) == 7 and texto[4] == "-":
            ano, mes = texto.split("-", 1)
        elif len(texto) == 7 and texto[2] == "/":
            mes, ano = texto.split("/", 1)
        else:
            raise ValueError("Competência inválida. Use MM/AAAA.")
        try:
            ano_i, mes_i = int(ano), int(mes)
        except ValueError as erro:
            raise ValueError("Competência inválida. Use MM/AAAA.") from erro
        if not 1 <= mes_i <= 12:
            raise ValueError("Competência inválida. O mês deve ficar entre 01 e 12.")
        return f"{ano_i:04d}-{mes_i:02d}"

    @staticmethod
    def competencia_br(valor: str) -> str:
        if len(valor or "") == 7 and valor[4] == "-":
            return f"{valor[5:7]}/{valor[:4]}"
        return valor or ""

    @staticmethod
    def _dia(valor: object, nome: str) -> int:
        try:
            numero = int(str(valor).strip())
        except (TypeError, ValueError) as erro:
            raise ValueError(f"Informe o {nome} entre 1 e 31.") from erro
        if not 1 <= numero <= 31:
            raise ValueError(f"Informe o {nome} entre 1 e 31.")
        return numero

    @staticmethod
    def _data_no_mes(competencia: str, dia: int) -> date:
        ano, mes = (int(parte) for parte in competencia.split("-"))
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        return date(ano, mes, min(max(int(dia), 1), ultimo_dia))

    @staticmethod
    def _somar_meses(competencia: str, meses: int) -> str:
        ano, mes = (int(parte) for parte in competencia.split("-"))
        indice = ano * 12 + (mes - 1) + int(meses)
        novo_ano, novo_mes_zero = divmod(indice, 12)
        return f"{novo_ano:04d}-{novo_mes_zero + 1:02d}"

    def salvar_lembrete(
        self,
        dados: dict[str, object],
        *,
        lembrete_id: int | None = None,
    ) -> int:
        empresa = str(dados.get("empresa") or "").strip()
        fornecedor = str(dados.get("fornecedor") or "").strip()
        if empresa not in self.repositorio.listar_empresas():
            raise ValueError("Selecione uma empresa cadastrada.")
        if not fornecedor:
            raise ValueError("Informe o fornecedor da fatura.")
        fornecedor = self.repositorio.salvar_fornecedor(fornecedor)

        tipo = " ".join(str(dados.get("tipo_fatura") or "OUTROS").strip().upper().split())
        categoria = " ".join(str(dados.get("categoria") or "OUTROS").strip().upper().split())
        categoria = self.repositorio.salvar_categoria(categoria)
        dia_disp = self._dia(dados.get("dia_disponibilidade"), "dia previsto para disponibilização")
        dia_venc = self._dia(dados.get("dia_vencimento"), "dia previsto do vencimento")
        try:
            dias_alerta = int(str(dados.get("dias_alerta") or 3).strip())
        except ValueError as erro:
            raise ValueError("Dias de antecedência deve ser um número entre 0 e 30.") from erro
        if not 0 <= dias_alerta <= 30:
            raise ValueError("Dias de antecedência deve ficar entre 0 e 30.")

        competencia = self._competencia_iso(dados.get("competencia_inicial"))
        recorrente = 1 if bool(dados.get("recorrente", True)) else 0
        ativa = 1 if bool(dados.get("ativa", True)) else 0
        observacoes = str(dados.get("observacoes") or "").strip()
        agora = datetime.now().isoformat(timespec="seconds")

        with self.repositorio._conectar() as conexao:
            if lembrete_id is None:
                cursor = conexao.execute(
                    """
                    INSERT INTO agenda_faturas(
                        empresa, fornecedor, tipo_fatura, categoria,
                        dia_disponibilidade, dia_vencimento, dias_alerta,
                        competencia_inicial, recorrente, ativa, observacoes,
                        criado_em, atualizado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        empresa, fornecedor, tipo, categoria, dia_disp, dia_venc,
                        dias_alerta, competencia, recorrente, ativa, observacoes,
                        agora, agora,
                    ),
                )
                lembrete_id = int(cursor.lastrowid)
            else:
                conexao.execute(
                    """
                    UPDATE agenda_faturas
                    SET empresa = ?, fornecedor = ?, tipo_fatura = ?, categoria = ?,
                        dia_disponibilidade = ?, dia_vencimento = ?, dias_alerta = ?,
                        competencia_inicial = ?, recorrente = ?, ativa = ?,
                        observacoes = ?, atualizado_em = ?
                    WHERE id = ?
                    """,
                    (
                        empresa, fornecedor, tipo, categoria, dia_disp, dia_venc,
                        dias_alerta, competencia, recorrente, ativa, observacoes,
                        agora, int(lembrete_id),
                    ),
                )
                self._atualizar_itens_abertos(conexao, int(lembrete_id))

        self.gerar_competencias(meses_futuros=1)
        return int(lembrete_id)

    def _atualizar_itens_abertos(self, conexao: sqlite3.Connection, lembrete_id: int) -> None:
        lembrete = conexao.execute(
            "SELECT * FROM agenda_faturas WHERE id = ?", (lembrete_id,)
        ).fetchone()
        if not lembrete:
            return
        linhas = conexao.execute(
            """
            SELECT id, competencia FROM agenda_faturas_itens
            WHERE lembrete_id = ? AND status = ?
            """,
            (lembrete_id, STATUS_AGUARDANDO),
        ).fetchall()
        agora = datetime.now().isoformat(timespec="seconds")
        for linha in linhas:
            data_prevista = self._data_no_mes(
                str(linha["competencia"]), int(lembrete["dia_disponibilidade"])
            ).isoformat()
            vencimento = self._data_no_mes(
                str(linha["competencia"]), int(lembrete["dia_vencimento"])
            ).isoformat()
            conexao.execute(
                "UPDATE agenda_faturas_itens SET data_prevista = ?, vencimento_previsto = ?, atualizado_em = ? WHERE id = ?",
                (data_prevista, vencimento, agora, int(linha["id"])),
            )

    def obter_lembrete(self, lembrete_id: int) -> sqlite3.Row | None:
        with self.repositorio._conectar() as conexao:
            return conexao.execute(
                "SELECT * FROM agenda_faturas WHERE id = ?", (int(lembrete_id),)
            ).fetchone()

    def listar_lembretes(self, *, somente_ativos: bool = True) -> list[sqlite3.Row]:
        where = "WHERE ativa = 1" if somente_ativos else ""
        with self.repositorio._conectar() as conexao:
            return conexao.execute(
                f"SELECT * FROM agenda_faturas {where} ORDER BY empresa, fornecedor, tipo_fatura"
            ).fetchall()

    def desativar_lembrete(self, lembrete_id: int) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with self.repositorio._conectar() as conexao:
            conexao.execute(
                "UPDATE agenda_faturas SET ativa = 0, atualizado_em = ? WHERE id = ?",
                (agora, int(lembrete_id)),
            )

    def gerar_competencias(
        self,
        *,
        referencia: date | None = None,
        meses_futuros: int = 1,
    ) -> int:
        referencia = referencia or date.today()
        competencia_atual = referencia.strftime("%Y-%m")
        criados = 0
        agora = datetime.now().isoformat(timespec="seconds")
        with self.repositorio._conectar() as conexao:
            lembretes = conexao.execute(
                "SELECT * FROM agenda_faturas WHERE ativa = 1 ORDER BY id"
            ).fetchall()
            for lembrete in lembretes:
                inicial = str(lembrete["competencia_inicial"])
                if int(lembrete["recorrente"]):
                    competencias = [
                        self._somar_meses(competencia_atual, deslocamento)
                        for deslocamento in range(0, meses_futuros + 1)
                    ]
                    competencias = [comp for comp in competencias if comp >= inicial]
                else:
                    competencias = [inicial]
                for competencia in competencias:
                    data_prevista = self._data_no_mes(
                        competencia, int(lembrete["dia_disponibilidade"])
                    ).isoformat()
                    vencimento = self._data_no_mes(
                        competencia, int(lembrete["dia_vencimento"])
                    ).isoformat()
                    cursor = conexao.execute(
                        """
                        INSERT OR IGNORE INTO agenda_faturas_itens(
                            lembrete_id, competencia, data_prevista, vencimento_previsto,
                            status, atualizado_em
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(lembrete["id"]), competencia, data_prevista,
                            vencimento, STATUS_AGUARDANDO, agora,
                        ),
                    )
                    if cursor.rowcount:
                        criados += 1
        return criados

    def obter_item(self, item_id: int) -> sqlite3.Row | None:
        with self.repositorio._conectar() as conexao:
            return conexao.execute(
                """
                SELECT i.*, f.empresa, f.fornecedor, f.tipo_fatura, f.categoria,
                       f.dias_alerta, f.observacoes, f.ativa
                FROM agenda_faturas_itens i
                JOIN agenda_faturas f ON f.id = i.lembrete_id
                WHERE i.id = ?
                """,
                (int(item_id),),
            ).fetchone()

    @staticmethod
    def _normalizar_vinculo(texto: object) -> str:
        valor = unicodedata.normalize("NFKD", str(texto or ""))
        valor = "".join(letra for letra in valor if not unicodedata.combining(letra))
        return " ".join(valor.upper().split())

    def localizar_contas_candidatas(self, item_id: int, *, limite: int = 10) -> list[dict[str, object]]:
        """Localiza contas já lançadas que podem corresponder a um item da agenda.

        Esse fluxo existe para bases em que a conta foi cadastrada manualmente antes
        de a Agenda de Faturas criar o vínculo por ``conta_id``. A busca é conservadora:
        exige a mesma empresa e competência e, além disso, fornecedor igual ou
        claramente compatível. Contas já ligadas a outro item da agenda são ignoradas.
        """
        item = self.obter_item(int(item_id))
        if not item:
            raise ValueError("Lembrete mensal não encontrado.")

        empresa = str(item["empresa"] or "").strip()
        competencia = str(item["competencia"] or "").strip()
        fornecedor_alvo = self._normalizar_vinculo(item["fornecedor"])
        categoria_alvo = self._normalizar_vinculo(item["categoria"])
        vencimento_previsto = str(item["vencimento_previsto"] or "").strip()

        with self.repositorio._conectar() as conexao:
            linhas = conexao.execute(
                """
                SELECT c.*
                FROM contas_pagar c
                WHERE c.empresa = ? AND c.competencia = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM agenda_faturas_itens ai
                      WHERE ai.conta_id = c.id AND ai.id <> ?
                  )
                ORDER BY c.vencimento, c.fornecedor, c.id
                """,
                (empresa, competencia, int(item_id)),
            ).fetchall()

        candidatos: list[dict[str, object]] = []
        for linha in linhas:
            fornecedor = self._normalizar_vinculo(linha["fornecedor"])
            if not fornecedor_alvo or not fornecedor:
                continue

            score = 0
            if fornecedor == fornecedor_alvo:
                score += 100
            elif min(len(fornecedor), len(fornecedor_alvo)) >= 4 and (
                fornecedor in fornecedor_alvo or fornecedor_alvo in fornecedor
            ):
                score += 60
            else:
                continue

            categoria = self._normalizar_vinculo(linha["categoria"])
            if categoria_alvo and categoria == categoria_alvo:
                score += 10

            diferenca_dias = 9999
            try:
                diferenca_dias = abs(
                    (date.fromisoformat(str(linha["vencimento"])) - date.fromisoformat(vencimento_previsto)).days
                )
            except (TypeError, ValueError):
                pass
            if diferenca_dias == 0:
                score += 30
            elif diferenca_dias <= 3:
                score += 20
            elif diferenca_dias <= 10:
                score += 10

            candidato = dict(linha)
            candidato["score_vinculo"] = score
            candidato["diferenca_vencimento_dias"] = diferenca_dias
            candidatos.append(candidato)

        candidatos.sort(
            key=lambda conta: (
                -int(conta["score_vinculo"]),
                int(conta["diferenca_vencimento_dias"]),
                int(conta["id"]),
            )
        )
        return candidatos[: max(1, int(limite))]

    def listar_itens(
        self,
        *,
        empresa: str = "",
        competencia: str = "",
        status: str = "",
        incluir_concluidos: bool = False,
    ) -> list[dict[str, object]]:
        self.gerar_competencias(meses_futuros=1)
        filtros = ["f.ativa = 1"]
        parametros: list[object] = []
        if empresa:
            filtros.append("f.empresa = ?")
            parametros.append(empresa)
        if competencia:
            filtros.append("i.competencia = ?")
            parametros.append(self._competencia_iso(competencia))
        if status:
            filtros.append("i.status = ?")
            parametros.append(status)
        elif not incluir_concluidos:
            filtros.append("i.status <> ?")
            parametros.append(STATUS_PAGA)
        with self.repositorio._conectar() as conexao:
            linhas = conexao.execute(
                f"""
                SELECT i.*, f.empresa, f.fornecedor, f.tipo_fatura, f.categoria,
                       f.dias_alerta, f.observacoes, f.ativa
                FROM agenda_faturas_itens i
                JOIN agenda_faturas f ON f.id = i.lembrete_id
                WHERE {' AND '.join(filtros)}
                ORDER BY i.vencimento_previsto, f.empresa, f.fornecedor
                """,
                parametros,
            ).fetchall()
        resultado = []
        for linha in linhas:
            item = dict(linha)
            sinal, prioridade = self.sinalizacao(item)
            item["sinalizacao"] = sinal
            item["prioridade"] = prioridade
            resultado.append(item)
        return sorted(resultado, key=lambda x: (int(x["prioridade"]), str(x["vencimento_previsto"])))

    @staticmethod
    def sinalizacao(item: dict[str, object] | sqlite3.Row, *, hoje: date | None = None) -> tuple[str, int]:
        hoje = hoje or date.today()
        status = str(item["status"])
        if status == STATUS_PAGA:
            return "✅ CONCLUÍDA", 6
        vencimento = date.fromisoformat(str(item["vencimento_previsto"]))
        prevista = date.fromisoformat(str(item["data_prevista"]))
        dias_alerta = int(item["dias_alerta"] or 0)
        if status == STATUS_LANCADA:
            if vencimento < hoje:
                return "🔴 LANÇADA / VENCIDA", 0
            if vencimento <= hoje + timedelta(days=7):
                return "🟡 LANÇADA / VENCE EM BREVE", 3
            return "🟢 LANÇADA", 5
        if status == STATUS_BAIXADA:
            if vencimento < hoje:
                return "🔴 FATURA BAIXADA / LANÇAR URGENTE", 0
            return "🟠 FATURA BAIXADA / LANÇAR", 1
        if vencimento < hoje:
            return "🔴 ATRASADA / BAIXAR FATURA", 0
        if vencimento <= hoje + timedelta(days=2):
            return "🔴 VENCIMENTO PRÓXIMO", 0
        if hoje >= prevista:
            return "🟠 BAIXAR FATURA", 1
        if hoje >= prevista - timedelta(days=dias_alerta):
            return "🟡 EM BREVE", 2
        return "🟢 PROGRAMADA", 5

    def resumo(self, *, empresa: str = "", referencia: date | None = None) -> dict[str, int]:
        hoje = referencia or date.today()
        itens = self.listar_itens(empresa=empresa, incluir_concluidos=True)
        atual = hoje.strftime("%Y-%m")
        para_baixar = 0
        nao_lancadas = 0
        vencendo = 0
        concluidas = 0
        for item in itens:
            status = str(item["status"])
            prevista = date.fromisoformat(str(item["data_prevista"]))
            vencimento = date.fromisoformat(str(item["vencimento_previsto"]))
            alerta = int(item["dias_alerta"] or 0)
            if status == STATUS_PAGA and str(item["competencia"]) == atual:
                concluidas += 1
            if status == STATUS_AGUARDANDO and hoje >= prevista - timedelta(days=alerta):
                para_baixar += 1
            if status in {STATUS_AGUARDANDO, STATUS_BAIXADA} and hoje >= prevista - timedelta(days=alerta):
                nao_lancadas += 1
            if status != STATUS_PAGA and hoje <= vencimento <= hoje + timedelta(days=7):
                vencendo += 1
        return {
            "para_baixar": para_baixar,
            "nao_lancadas": nao_lancadas,
            "vencendo_7_dias": vencendo,
            "concluidas_mes": concluidas,
        }

    def marcar_fatura_baixada(self, item_id: int, caminho_documento: str = "") -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with self.repositorio._conectar() as conexao:
            atual = conexao.execute(
                "SELECT caminho_documento FROM agenda_faturas_itens WHERE id = ?",
                (int(item_id),),
            ).fetchone()
            if not atual:
                raise ValueError("Lembrete mensal não encontrado.")
            caminho = str(caminho_documento or atual["caminho_documento"] or "")
            conexao.execute(
                """
                UPDATE agenda_faturas_itens
                SET status = ?, caminho_documento = ?, baixada_em = ?, atualizado_em = ?
                WHERE id = ?
                """,
                (STATUS_BAIXADA, caminho, agora, agora, int(item_id)),
            )

    def marcar_aguardando(self, item_id: int) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with self.repositorio._conectar() as conexao:
            conexao.execute(
                """
                UPDATE agenda_faturas_itens
                SET status = ?, conta_id = NULL, lancada_em = '', concluida_em = '', atualizado_em = ?
                WHERE id = ?
                """,
                (STATUS_AGUARDANDO, agora, int(item_id)),
            )

    def prefill_conta(self, item_id: int) -> dict[str, object]:
        item = self.obter_item(item_id)
        if not item:
            raise ValueError("Lembrete mensal não encontrado.")
        return {
            "empresa": item["empresa"],
            "fornecedor": item["fornecedor"],
            "descricao": f"{item['tipo_fatura']} — {self.competencia_br(str(item['competencia']))}",
            "categoria": item["categoria"],
            "vencimento": item["vencimento_previsto"],
            "competencia": item["competencia"],
            "caminho_documento": item["caminho_documento"],
            "origem": "AGENDA DE FATURAS",
            "observacoes": item["observacoes"],
        }

    def vincular_conta(self, item_id: int, conta_id: int) -> None:
        conta = self.repositorio.obter_conta(int(conta_id))
        if not conta:
            raise ValueError("A conta criada não foi encontrada para vincular à agenda.")
        agora = datetime.now().isoformat(timespec="seconds")
        status = STATUS_PAGA if str(conta["status"]) == "PAGO" else STATUS_LANCADA
        concluida_em = agora if status == STATUS_PAGA else ""
        with self.repositorio._conectar() as conexao:
            conexao.execute(
                """
                UPDATE agenda_faturas_itens
                SET conta_id = ?, status = ?, lancada_em = ?, concluida_em = ?, atualizado_em = ?
                WHERE id = ?
                """,
                (int(conta_id), status, agora, concluida_em, agora, int(item_id)),
            )

    def sincronizar_conta(self, conta_id: int) -> None:
        conta = self.repositorio.obter_conta(int(conta_id))
        agora = datetime.now().isoformat(timespec="seconds")
        with self.repositorio._conectar() as conexao:
            itens = conexao.execute(
                "SELECT id FROM agenda_faturas_itens WHERE conta_id = ?", (int(conta_id),)
            ).fetchall()
            if not itens:
                return
            if conta is None:
                conexao.execute(
                    """
                    UPDATE agenda_faturas_itens
                    SET conta_id = NULL, status = ?, lancada_em = '', concluida_em = '', atualizado_em = ?
                    WHERE conta_id = ?
                    """,
                    (STATUS_BAIXADA, agora, int(conta_id)),
                )
                return
            status = STATUS_PAGA if str(conta["status"]) == "PAGO" else STATUS_LANCADA
            concluida = agora if status == STATUS_PAGA else ""
            conexao.execute(
                """
                UPDATE agenda_faturas_itens
                SET status = ?, concluida_em = ?, atualizado_em = ?
                WHERE conta_id = ?
                """,
                (status, concluida, agora, int(conta_id)),
            )
