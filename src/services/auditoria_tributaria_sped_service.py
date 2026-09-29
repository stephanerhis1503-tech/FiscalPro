"""
==========================================================
FiscalPro
Serviço de Auditoria Tributária do SPED
Sprint 9.0
==========================================================
"""

from collections import Counter

from src.banco.conexao import Banco
from src.modelos.registro_0200 import Registro0200
from src.modelos.registro_c170 import RegistroC170


class AuditoriaTributariaSPEDService:

    CAMPOS_COMPARADOS = (
        "ncm",
        "cest",
        "cfop",
        "cst_icms",
        "icms",
        "cst_pis",
        "aliquota_pis",
        "cst_cofins",
        "aliquota_cofins",
        "cst_ipi",
        "ipi",
    )

    def __init__(self):

        self.cadastros_0200 = {}
        self.itens = []
        self.divergencias = []

    def analisar_arquivo(self, caminho_sped):

        with open(caminho_sped, "r", encoding="latin1") as arquivo:
            linhas = arquivo.readlines()

        return self.analisar_linhas(linhas)

    def analisar_linhas(self, linhas):

        self.cadastros_0200 = {}
        self.itens = []
        self.divergencias = []

        self._carregar_0200(linhas)
        self._carregar_c170(linhas)

        itens_com_base = 0
        itens_sem_base = 0

        for numero_linha, item in self.itens:

            cadastro = self.cadastros_0200.get(item.codigo)
            item.vincular_cadastro(cadastro)

            base = self._buscar_base(item)

            if base is None:
                itens_sem_base += 1

                self.divergencias.append({
                    "linha": numero_linha,
                    "codigo": item.codigo,
                    "descricao": (
                        item.descricao_0200
                        or item.descricao_complementar
                    ),
                    "ncm": item.ncm,
                    "campo": "BASE_TRIBUTARIA",
                    "atual": "",
                    "esperado": "",
                    "tipo": "SEM_BASE",
                    "mensagem": (
                        "Produto não localizado na base tributária."
                    )
                })

                continue

            itens_com_base += 1
            self._comparar_item(numero_linha, item, base)

        contagem = Counter(
            item["campo"]
            for item in self.divergencias
            if item["tipo"] == "DIVERGENCIA"
        )

        total_itens = len(self.itens)
        total_divergencias = sum(contagem.values())

        conformidade = 100.0

        if total_itens:
            campos_possiveis = total_itens * len(self.CAMPOS_COMPARADOS)
            conformidade = max(
                0.0,
                100.0 - (
                    total_divergencias / campos_possiveis * 100.0
                )
            )

        return {
            "total_linhas": len(linhas),
            "cadastros_0200": len(self.cadastros_0200),
            "itens_c170": total_itens,
            "itens_com_base": itens_com_base,
            "itens_sem_base": itens_sem_base,
            "divergencias": total_divergencias,
            "conformidade": round(conformidade, 2),
            "por_campo": dict(contagem),
            "detalhes": self.divergencias
        }

    def _carregar_0200(self, linhas):

        for linha in linhas:

            if not linha.startswith("|0200|"):
                continue

            registro = Registro0200(linha)

            if registro.codigo:
                self.cadastros_0200[registro.codigo] = registro

    def _carregar_c170(self, linhas):

        for numero_linha, linha in enumerate(linhas, start=1):

            if linha.startswith("|C170|"):
                self.itens.append((
                    numero_linha,
                    RegistroC170(linha)
                ))

    def _buscar_base(self, item):

        conn = Banco.conectar()
        cursor = conn.cursor()

        colunas = self._colunas_tabela(cursor, "tributacao_base")

        if not colunas:
            conn.close()
            return None

        resultado = None

        if (
            "codigo_produto" in colunas
            and item.codigo
        ):
            cursor.execute("""
                SELECT *
                FROM tributacao_base
                WHERE codigo_produto = ?
                  AND COALESCE(ativo, 1) = 1
                ORDER BY
                    COALESCE(confiabilidade, 50) DESC,
                    id DESC
                LIMIT 1
            """, (item.codigo,))

            resultado = cursor.fetchone()

        if resultado is None and item.ncm:
            condicao_ativo = ""

            if "ativo" in colunas:
                condicao_ativo = "AND COALESCE(ativo, 1) = 1"

            cursor.execute(f"""
                SELECT *
                FROM tributacao_base
                WHERE REPLACE(
                    REPLACE(
                        REPLACE(COALESCE(ncm, ''), '.', ''),
                        '-', ''
                    ),
                    ' ',
                    ''
                ) = ?
                {condicao_ativo}
                ORDER BY
                    COALESCE(confiabilidade, 50) DESC,
                    id DESC
                LIMIT 1
            """, (item.ncm,))

            resultado = cursor.fetchone()

        conn.close()

        return resultado

    @staticmethod
    def _colunas_tabela(cursor, tabela):

        cursor.execute(f"PRAGMA table_info({tabela})")

        return {
            linha["name"]
            for linha in cursor.fetchall()
        }

    def _comparar_item(self, numero_linha, item, base):

        self._comparar_texto(
            numero_linha,
            item,
            "ncm",
            item.ncm,
            self._valor(base, "ncm")
        )

        self._comparar_texto(
            numero_linha,
            item,
            "cest",
            item.cest,
            self._valor(base, "cest")
        )

        self._comparar_texto(
            numero_linha,
            item,
            "cfop",
            item.cfop,
            self._valor(base, "cfop")
        )

        self._comparar_texto(
            numero_linha,
            item,
            "cst_icms",
            item.cst_icms,
            self._valor(base, "cst_icms")
        )

        self._comparar_numero(
            numero_linha,
            item,
            "icms",
            item.aliquota_icms,
            self._valor(base, "icms")
        )

        self._comparar_texto(
            numero_linha,
            item,
            "cst_pis",
            item.cst_pis,
            self._valor(base, "cst_pis")
        )

        self._comparar_numero(
            numero_linha,
            item,
            "aliquota_pis",
            item.aliquota_pis,
            self._valor(base, "aliquota_pis")
        )

        self._comparar_texto(
            numero_linha,
            item,
            "cst_cofins",
            item.cst_cofins,
            self._valor(base, "cst_cofins")
        )

        self._comparar_numero(
            numero_linha,
            item,
            "aliquota_cofins",
            item.aliquota_cofins,
            self._valor(base, "aliquota_cofins")
        )

        self._comparar_texto(
            numero_linha,
            item,
            "cst_ipi",
            item.cst_ipi,
            self._valor(base, "cst_ipi")
        )

        self._comparar_numero(
            numero_linha,
            item,
            "ipi",
            item.aliquota_ipi,
            self._valor(base, "ipi")
        )

    def _comparar_texto(
        self,
        numero_linha,
        item,
        campo,
        atual,
        esperado
    ):

        atual_normalizado = self._normalizar_texto(campo, atual)
        esperado_normalizado = self._normalizar_texto(campo, esperado)

        if not esperado_normalizado:
            return

        if atual_normalizado == esperado_normalizado:
            return

        self._registrar_divergencia(
            numero_linha,
            item,
            campo,
            atual,
            esperado
        )

    def _comparar_numero(
        self,
        numero_linha,
        item,
        campo,
        atual,
        esperado
    ):

        esperado_numero = self._numero(esperado)

        if esperado in (None, ""):
            return

        atual_numero = self._numero(atual)

        if abs(atual_numero - esperado_numero) <= 0.0001:
            return

        self._registrar_divergencia(
            numero_linha,
            item,
            campo,
            atual_numero,
            esperado_numero
        )

    def _registrar_divergencia(
        self,
        numero_linha,
        item,
        campo,
        atual,
        esperado
    ):

        self.divergencias.append({
            "linha": numero_linha,
            "codigo": item.codigo,
            "descricao": (
                item.descricao_0200
                or item.descricao_complementar
            ),
            "ncm": item.ncm,
            "campo": campo.upper(),
            "atual": atual,
            "esperado": esperado,
            "tipo": "DIVERGENCIA",
            "mensagem": (
                f"{campo.upper()} divergente: "
                f"atual '{atual}' e esperado '{esperado}'."
            )
        })

    @staticmethod
    def _valor(linha, campo):

        if linha is None:
            return None

        try:
            return linha[campo]
        except (IndexError, KeyError):
            return None

    @staticmethod
    def _normalizar_texto(campo, valor):

        texto = str(valor or "").strip().upper()

        if campo in {"ncm", "cest", "cfop"}:
            return "".join(
                caractere
                for caractere in texto
                if caractere.isdigit()
            )

        return texto

    @staticmethod
    def _numero(valor):

        if valor is None:
            return 0.0

        if isinstance(valor, (int, float)):
            return float(valor)

        texto = str(valor).strip().replace("%", "")

        if not texto:
            return 0.0

        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", ".")

        try:
            return float(texto)
        except (TypeError, ValueError):
            return 0.0
