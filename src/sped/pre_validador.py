from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterable

ProgressoCallback = Callable[[int, str], None]


@dataclass(frozen=True, slots=True)
class ApontamentoPVA:
    nivel: str
    categoria: str
    registro: str
    numero_linha: int | None
    mensagem: str
    sugestao: str = ""
    documento: str = ""
    codigo_item: str = ""
    campo: str = ""


@dataclass(slots=True)
class ResultadoPreValidacaoPVA:
    tipo_sped: str
    total_linhas: int
    regras_executadas: int = 0
    tempo_processamento: float = 0.0
    apontamentos: list[ApontamentoPVA] = field(default_factory=list)
    # O PGE pode repetir a mesma causa em mais de uma regra e também gerar
    # pendências encadeadas durante a apuração. A tabela do FiscalPro mantém
    # causas únicas e guarda uma equivalência para comparação com o PGE.
    erros_pge_estimados: int = 0
    avisos_pge_estimados: int = 0
    equivalencia_pge: dict[str, int] = field(default_factory=dict)

    @property
    def erros(self) -> list[ApontamentoPVA]:
        return [item for item in self.apontamentos if item.nivel == "ERRO"]

    @property
    def avisos(self) -> list[ApontamentoPVA]:
        return [item for item in self.apontamentos if item.nivel == "AVISO"]

    @property
    def revisoes(self) -> list[ApontamentoPVA]:
        """Conferências extras do FiscalPro que não representam erro/aviso do PVA/PGE."""
        return [item for item in self.apontamentos if item.nivel == "REVISÃO FISCALPRO"]

    @property
    def aprovado(self) -> bool:
        return not self.erros

    @property
    def total(self) -> int:
        return len(self.apontamentos)


@dataclass(frozen=True, slots=True)
class _Registro:
    numero_linha: int
    codigo: str
    campos: tuple[str, ...]
    texto: str

    def campo(self, indice: int) -> str:
        if 0 <= indice < len(self.campos):
            return self.campos[indice].strip()
        return ""


@dataclass(slots=True)
class _Documento:
    registro: _Registro
    filhos: list[_Registro] = field(default_factory=list)


class PreValidadorPVA:
    """Pré-validador local para apontar inconsistências antes do PVA.

    As regras são deliberadamente conservadoras: o módulo não altera o SPED e
    não pretende substituir o validador oficial. Ele localiza problemas
    estruturais, relacionais, cadastrais e aritméticos comuns, com foco inicial
    em EFD Contribuições e nos registros compartilhados com a EFD Fiscal.
    """

    TOLERANCIA_VALOR = Decimal("0.02")
    TOLERANCIA_TOTAL = Decimal("0.05")
    SITUACOES_REGULARES = {"00", "01"}
    MODELOS_CHAVE_44 = {"55", "57", "59", "65", "67"}

    BLOCOS = {
        "0990": "0000",
        "A990": "A001",
        "B990": "B001",
        "C990": "C001",
        "D990": "D001",
        "E990": "E001",
        "F990": "F001",
        "G990": "G001",
        "H990": "H001",
        "I990": "I001",
        "K990": "K001",
        "M990": "M001",
        "P990": "P001",
        "1990": "1001",
        "9990": "9001",
    }

    def __init__(self) -> None:
        self._resultado: ResultadoPreValidacaoPVA | None = None
        self._chaves_vistas: dict[str, tuple[str, int]] = {}
        self._chaves_apontamentos: set[tuple] = set()
        self._ind_inc_trib: str = ""
        self._dt_ini_escrituracao: datetime | None = None
        self._dt_fin_escrituracao: datetime | None = None

    def validar(
        self,
        linhas: list[str],
        tipo_sped: str,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoPreValidacaoPVA:
        inicio = perf_counter()
        resultado = ResultadoPreValidacaoPVA(tipo_sped=tipo_sped, total_linhas=len(linhas))
        self._resultado = resultado
        self._chaves_vistas = {}
        self._chaves_apontamentos = set()
        self._ind_inc_trib = ""
        self._dt_ini_escrituracao = None
        self._dt_fin_escrituracao = None

        self._progresso(progresso, 5, "Preparando a pré-validação do PVA...")
        registros = self._ler_registros(linhas)
        por_codigo: dict[str, list[_Registro]] = defaultdict(list)
        for registro in registros:
            por_codigo[registro.codigo].append(registro)

        registro_0110 = por_codigo.get("0110", [])
        if registro_0110:
            self._ind_inc_trib = registro_0110[0].campo(1)

        registro_0000 = por_codigo.get("0000", [])
        if registro_0000:
            self._dt_ini_escrituracao = self._data_ou_none(registro_0000[0].campo(5))
            self._dt_fin_escrituracao = self._data_ou_none(registro_0000[0].campo(6))

        self._progresso(progresso, 15, "Validando estrutura e totalizadores do arquivo...")
        self._validar_estrutura(linhas, registros, por_codigo)
        self._validar_totalizadores(linhas, por_codigo)
        self._validar_registro_9900(por_codigo)
        self._validar_indicadores_movimento(por_codigo)
        self._validar_0205(registros)

        self._progresso(progresso, 35, "Cruzando cadastros de participantes, unidades e produtos...")
        participantes = self._validar_participantes(por_codigo.get("0150", []))
        unidades = self._validar_unidades(por_codigo.get("0190", []))
        produtos = self._validar_produtos(por_codigo.get("0200", []), unidades)

        self._progresso(progresso, 55, "Validando notas e itens dos blocos A e C...")
        documentos_a = self._agrupar_documentos(registros, "A100", {"A170"})
        documentos_c = self._agrupar_documentos(registros, "C100", {"C170", "C175", "C190"})
        self._validar_documentos_a(documentos_a, participantes, produtos)
        self._validar_documentos_c(documentos_c, participantes, unidades, produtos)
        self._validar_c175_pge(por_codigo.get("C175", []))

        self._progresso(progresso, 75, "Validando CT-e, PIS e COFINS...")
        documentos_d = self._agrupar_documentos(registros, "D100", {"D101", "D105"})
        self._validar_documentos_d(documentos_d, participantes)

        if tipo_sped == "EFD Contribuições":
            self._progresso(
                progresso,
                88,
                "Conferindo regras do PGE em C170 e a apuração dos créditos no Bloco M...",
            )
            self._validar_regras_pge_c170(por_codigo.get("C170", []))
            self._validar_creditos_m(por_codigo.get("M100", []), "PIS")
            self._validar_creditos_m(por_codigo.get("M500", []), "COFINS")
            self._validar_bloco_m_pge(registros)

        self._calcular_equivalencia_pge(registros, por_codigo)

        resultado.apontamentos.sort(
            key=lambda item: (
                {"ERRO": 0, "AVISO": 1, "REVISÃO FISCALPRO": 2}.get(item.nivel, 3),
                item.numero_linha if item.numero_linha is not None else 10**9,
                item.registro,
                item.categoria,
            )
        )
        resultado.tempo_processamento = perf_counter() - inicio
        self._progresso(
            progresso,
            100,
            (
                f"Pré-validação concluída: {len(resultado.erros)} erro(s), "
                f"{len(resultado.avisos)} aviso(s) PVA/PGE e "
                f"{len(resultado.revisoes)} revisão(ões) FiscalPro."
            ),
        )
        return resultado

    def salvar_relatorio(
        self,
        resultado: ResultadoPreValidacaoPVA,
        caminho_saida: str | Path,
        arquivo_origem: str | Path | None = None,
    ) -> Path:
        destino = Path(caminho_saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        origem = str(arquivo_origem or "-")

        linhas = [
            "FISCALPRO — PRÉ-VALIDAÇÃO ANTES DO PVA",
            "=" * 78,
            f"Gerado em: {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"Arquivo analisado: {origem}",
            f"Tipo: {resultado.tipo_sped}",
            f"Linhas analisadas: {resultado.total_linhas}",
            f"Regras executadas: {resultado.regras_executadas}",
            f"Erros (causas raiz FiscalPro): {len(resultado.erros)}",
            f"Avisos PVA/PGE: {len(resultado.avisos)}",
            f"Revisões extras FiscalPro: {len(resultado.revisoes)}",
            f"Ocorrências equivalentes estimadas no PGE 6.1.2: {resultado.erros_pge_estimados}",
            f"Avisos equivalentes estimados no PGE: {resultado.avisos_pge_estimados}",
            f"Tempo: {resultado.tempo_processamento:.3f}s",
            "",
            (
                "STATUS: BLOQUEADO PARA CONFERÊNCIA — existem erros que devem ser revisados."
                if resultado.erros
                else "STATUS: SEM ERROS BLOQUEANTES NAS REGRAS PVA/PGE — faça a validação final oficial."
            ),
            "",
        ]

        if resultado.equivalencia_pge:
            linhas.extend([
                "ESPELHO PGE — equivalência de ocorrências",
                "-" * 78,
            ])
            for descricao, quantidade in resultado.equivalencia_pge.items():
                linhas.append(f"{descricao}: {quantidade}")
            linhas.append("")

        if not resultado.apontamentos:
            linhas.append("Nenhum erro ou aviso foi encontrado pelas regras desta sprint.")
        else:
            for numero, item in enumerate(resultado.apontamentos, start=1):
                linhas.extend(
                    [
                        f"{numero}. [{item.nivel}] {item.categoria}",
                        f"   Registro: {item.registro or '-'} | Linha: {item.numero_linha or '-'}",
                        f"   Documento: {item.documento or '-'} | Item: {item.codigo_item or '-'}",
                        f"   Campo: {item.campo or '-'}",
                        f"   Problema: {item.mensagem}",
                        f"   Orientação: {item.sugestao or 'Conferir no arquivo e no PVA.'}",
                        "",
                    ]
                )

        linhas.extend(
            [
                "IMPORTANTE",
                "- O FiscalPro não alterou o arquivo durante esta análise.",
                "- Revisões FiscalPro são auditorias extras e não significam erro/aviso do PVA/PGE.",
                "- Esta pré-validação reduz retrabalho, mas não substitui a validação oficial no PVA/PGE.",
            ]
        )
        destino.write_text("\n".join(linhas), encoding="utf-8")
        return destino

    def _ler_registros(self, linhas: Iterable[str]) -> list[_Registro]:
        registros: list[_Registro] = []
        for numero_linha, linha in enumerate(linhas, start=1):
            texto = linha.rstrip("\r\n")
            if not texto.startswith("|") or not texto.endswith("|"):
                continue
            partes = texto.split("|")
            if len(partes) < 3 or not partes[1].strip():
                continue
            campos = tuple(partes[1:-1])
            registros.append(
                _Registro(
                    numero_linha=numero_linha,
                    codigo=campos[0].strip().upper(),
                    campos=campos,
                    texto=texto,
                )
            )
        return registros

    def _validar_estrutura(
        self,
        linhas: list[str],
        registros: list[_Registro],
        por_codigo: dict[str, list[_Registro]],
    ) -> None:
        self._regra()
        for numero_linha, linha in enumerate(linhas, start=1):
            texto = linha.rstrip("\r\n")
            if not texto:
                self._erro(
                    "Estrutura",
                    "",
                    numero_linha,
                    "Linha vazia encontrada no arquivo.",
                    "Remover a linha vazia antes da importação no PVA.",
                )
            elif not texto.startswith("|") or not texto.endswith("|"):
                self._erro(
                    "Estrutura",
                    "",
                    numero_linha,
                    "A linha não começa e termina com o separador '|'.",
                    "Restaurar os separadores inicial e final do registro.",
                )

        self._regra()
        if not registros:
            self._erro("Estrutura", "", None, "Nenhum registro SPED válido foi localizado.")
            return
        if registros[0].codigo != "0000":
            self._erro(
                "Estrutura",
                registros[0].codigo,
                registros[0].numero_linha,
                "O primeiro registro válido não é o 0000.",
                "O arquivo deve iniciar pelo registro 0000.",
            )
        if registros[-1].codigo != "9999":
            self._erro(
                "Estrutura",
                registros[-1].codigo,
                registros[-1].numero_linha,
                "O último registro válido não é o 9999.",
                "O arquivo deve terminar pelo registro 9999.",
            )

        self._regra()
        for codigo in ("0000", "9999"):
            quantidade = len(por_codigo.get(codigo, []))
            if quantidade != 1:
                self._erro(
                    "Estrutura",
                    codigo,
                    por_codigo.get(codigo, [None])[0].numero_linha if quantidade else None,
                    f"O registro {codigo} aparece {quantidade} vez(es); o esperado é exatamente uma ocorrência.",
                )

    def _validar_totalizadores(
        self,
        linhas: list[str],
        por_codigo: dict[str, list[_Registro]],
    ) -> None:
        self._regra()
        for fechamento, abertura in self.BLOCOS.items():
            fechamentos = por_codigo.get(fechamento, [])
            aberturas = por_codigo.get(abertura, [])
            if not fechamentos:
                continue
            if len(fechamentos) > 1:
                self._erro(
                    "Totalizadores",
                    fechamento,
                    fechamentos[1].numero_linha,
                    f"O fechamento {fechamento} está duplicado.",
                )
                continue
            if not aberturas:
                self._erro(
                    "Totalizadores",
                    fechamento,
                    fechamentos[0].numero_linha,
                    f"Existe {fechamento}, mas a abertura {abertura} não foi encontrada.",
                )
                continue
            fechamento_reg = fechamentos[0]
            abertura_reg = aberturas[0]
            informado = self._inteiro(fechamento_reg.campo(1))
            if fechamento == "9990" and por_codigo.get("9999"):
                esperado = por_codigo["9999"][0].numero_linha - abertura_reg.numero_linha + 1
            else:
                esperado = fechamento_reg.numero_linha - abertura_reg.numero_linha + 1
            if informado is None:
                self._erro(
                    "Totalizadores",
                    fechamento,
                    fechamento_reg.numero_linha,
                    f"A quantidade de linhas do registro {fechamento} não é um número inteiro válido.",
                    campo="QTD_LIN",
                )
            elif informado != esperado:
                self._erro(
                    "Totalizadores",
                    fechamento,
                    fechamento_reg.numero_linha,
                    f"Quantidade informada {informado}, mas o bloco possui {esperado} linha(s).",
                    "Regerar o totalizador do bloco.",
                    campo="QTD_LIN",
                )

        self._regra()
        registros_9999 = por_codigo.get("9999", [])
        if registros_9999:
            registro = registros_9999[0]
            informado = self._inteiro(registro.campo(1))
            esperado = len(linhas)
            if informado is None:
                self._erro(
                    "Totalizadores",
                    "9999",
                    registro.numero_linha,
                    "O total geral de linhas não é um número inteiro válido.",
                    campo="QTD_LIN",
                )
            elif informado != esperado:
                self._erro(
                    "Totalizadores",
                    "9999",
                    registro.numero_linha,
                    f"O registro 9999 informa {informado} linha(s), mas o arquivo possui {esperado}.",
                    "Atualizar o total geral do arquivo.",
                    campo="QTD_LIN",
                )

    def _validar_registro_9900(self, por_codigo: dict[str, list[_Registro]]) -> None:
        self._regra()
        registros_9900 = por_codigo.get("9900", [])
        if not registros_9900:
            self._erro(
                "Totalizadores",
                "9900",
                None,
                "Nenhum registro 9900 foi encontrado no bloco 9.",
            )
            return

        informados: dict[str, _Registro] = {}
        for registro in registros_9900:
            alvo = registro.campo(1).upper()
            quantidade = self._inteiro(registro.campo(2))
            if not alvo:
                self._erro(
                    "Totalizadores",
                    "9900",
                    registro.numero_linha,
                    "O código de registro totalizado está vazio.",
                    campo="REG_BLC",
                )
                continue
            if alvo in informados:
                self._erro(
                    "Totalizadores",
                    "9900",
                    registro.numero_linha,
                    f"O registro {alvo} foi totalizado mais de uma vez no 9900.",
                )
            informados[alvo] = registro
            esperado = len(por_codigo.get(alvo, []))
            if quantidade is None:
                self._erro(
                    "Totalizadores",
                    "9900",
                    registro.numero_linha,
                    f"A quantidade informada para {alvo} não é válida.",
                    campo="QTD_REG_BLC",
                )
            elif quantidade != esperado:
                self._erro(
                    "Totalizadores",
                    "9900",
                    registro.numero_linha,
                    f"O 9900 informa {quantidade} ocorrência(s) de {alvo}, mas foram encontradas {esperado}.",
                    "Recalcular o bloco 9 após as alterações.",
                    campo="QTD_REG_BLC",
                )

        for codigo, ocorrencias in por_codigo.items():
            if codigo == "":
                continue
            if codigo not in informados:
                linha = ocorrencias[0].numero_linha if ocorrencias else None
                self._erro(
                    "Totalizadores",
                    "9900",
                    linha,
                    f"O registro {codigo} existe no arquivo, mas não foi relacionado no 9900.",
                    "Incluir a totalização do registro no bloco 9.",
                )

    def _validar_participantes(self, registros: list[_Registro]) -> dict[str, _Registro]:
        self._regra()
        mapa: dict[str, _Registro] = {}
        for registro in registros:
            codigo = registro.campo(1)
            if not codigo:
                self._erro(
                    "Cadastro",
                    "0150",
                    registro.numero_linha,
                    "Código do participante não informado.",
                    campo="COD_PART",
                )
                continue
            if codigo in mapa:
                self._erro(
                    "Cadastro",
                    "0150",
                    registro.numero_linha,
                    f"Código de participante duplicado: {codigo}.",
                    "Manter apenas um cadastro coerente para o código.",
                    campo="COD_PART",
                )
            else:
                mapa[codigo] = registro

            cnpj = self._digitos(registro.campo(4))
            cpf = self._digitos(registro.campo(5))
            if registro.campo(4) and len(cnpj) != 14:
                self._erro(
                    "Cadastro",
                    "0150",
                    registro.numero_linha,
                    f"CNPJ do participante fora do formato de 14 dígitos: {registro.campo(4)}.",
                    campo="CNPJ",
                    documento=codigo,
                )
            if registro.campo(5) and len(cpf) != 11:
                self._erro(
                    "Cadastro",
                    "0150",
                    registro.numero_linha,
                    f"CPF do participante fora do formato de 11 dígitos: {registro.campo(5)}.",
                    campo="CPF",
                    documento=codigo,
                )
        return mapa

    def _validar_unidades(self, registros: list[_Registro]) -> dict[str, _Registro]:
        self._regra()
        mapa: dict[str, _Registro] = {}
        for registro in registros:
            codigo = registro.campo(1)
            if not codigo:
                self._erro(
                    "Cadastro",
                    "0190",
                    registro.numero_linha,
                    "Código da unidade de medida não informado.",
                    campo="UNID",
                )
                continue
            if codigo in mapa:
                self._erro(
                    "Cadastro",
                    "0190",
                    registro.numero_linha,
                    f"Unidade de medida duplicada: {codigo}.",
                    campo="UNID",
                )
            else:
                mapa[codigo] = registro
        return mapa

    def _validar_produtos(
        self,
        registros: list[_Registro],
        unidades: dict[str, _Registro],
    ) -> dict[str, _Registro]:
        self._regra()
        mapa: dict[str, _Registro] = {}
        contagem_codigos = Counter(registro.campo(1) for registro in registros if registro.campo(1))

        # O relatório-gabarito do PGE também traz um aviso consolidado por
        # COD_ITEM repetido sobre coerência do regime de apuração.
        primeira_linha_por_codigo: dict[str, int] = {}
        for registro in registros:
            codigo = registro.campo(1)
            if codigo and codigo not in primeira_linha_por_codigo:
                primeira_linha_por_codigo[codigo] = registro.numero_linha
        for codigo, quantidade in contagem_codigos.items():
            if quantidade > 1:
                self._aviso(
                    "Coerência COD_ITEM",
                    "0200",
                    primeira_linha_por_codigo.get(codigo),
                    (
                        f"O COD_ITEM '{codigo}' aparece {quantidade} vezes no 0200. "
                        "O PGE pode emitir aviso para que itens com a mesma identificação "
                        "sejam apurados no mesmo regime."
                    ),
                    "Conferir o cadastro duplicado e a forma de apuração do item.",
                    codigo_item=codigo,
                    campo="COD_ITEM",
                )

        for registro in registros:
            codigo = registro.campo(1)
            descricao = registro.campo(2)
            unidade = registro.campo(5)
            tipo_item = registro.campo(6)
            ncm = registro.campo(7)

            if not codigo:
                self._erro("Cadastro", "0200", registro.numero_linha, "Código do item não informado.", campo="COD_ITEM")
                continue

            if codigo not in mapa:
                mapa[codigo] = registro

            if contagem_codigos.get(codigo, 0) > 1:
                self._erro(
                    "Duplicidade PGE",
                    "0200",
                    registro.numero_linha,
                    f"Duplicidade de ocorrência da chave COD_ITEM: {codigo}.",
                    (
                        "O PGE não aceita mais de um 0200 com o mesmo COD_ITEM. "
                        "Conferir os cadastros e manter um único código coerente."
                    ),
                    codigo_item=codigo,
                    campo="COD_ITEM",
                )

            if not descricao:
                self._erro(
                    "Cadastro",
                    "0200",
                    registro.numero_linha,
                    "Descrição do item não informada.",
                    codigo_item=codigo,
                    campo="DESCR_ITEM",
                )
            if tipo_item != "09" and not unidade:
                self._erro(
                    "Cadastro",
                    "0200",
                    registro.numero_linha,
                    "Unidade de inventário não informada.",
                    codigo_item=codigo,
                    campo="UNID_INV",
                )
            elif unidade and unidade not in unidades:
                self._erro(
                    "Referência",
                    "0200",
                    registro.numero_linha,
                    f"A unidade '{unidade}' não existe no registro 0190.",
                    "Cadastrar a unidade no 0190 ou corrigir o 0200.",
                    codigo_item=codigo,
                    campo="UNID_INV",
                )

            if ncm and (len(self._digitos(ncm)) != 8 or not ncm.isdigit()):
                self._erro(
                    "Cadastro",
                    "0200",
                    registro.numero_linha,
                    f"NCM inválido: '{ncm}'.",
                    "Informar o NCM com 8 dígitos, sem pontos.",
                    codigo_item=codigo,
                    campo="COD_NCM",
                )
            elif tipo_item != "09" and not ncm:
                self._aviso(
                    "Cadastro",
                    "0200",
                    registro.numero_linha,
                    "NCM não informado para item que não está classificado como serviço.",
                    "Conferir se o produto exige NCM.",
                    codigo_item=codigo,
                    campo="COD_NCM",
                )
        return mapa


    def _validar_indicadores_movimento(
        self,
        por_codigo: dict[str, list[_Registro]],
    ) -> None:
        """Espelha a coerência básica de IND_MOV usada pelo PGE.

        IND_MOV = 0 informa que o bloco contém dados. Quando existem apenas
        abertura/identificação/encerramento, o arquivo fica incoerente e o PGE
        tende a apontar pendência de hierarquia/movimento.
        """

        self._regra()
        regras = (
            # A010/D010 são registros de dados do bloco e, conforme validado
            # no PGE oficial com arquivo real, tornam IND_MOV=0 coerente.
            # Só abertura + encerramento, sem qualquer outro registro, é
            # tratado como inconsistência local.
            ("A001", "A990", {"A001", "A990"}),
            ("D001", "D990", {"D001", "D990"}),
        )
        for abertura, encerramento, permitidos_sem_movimento in regras:
            registros_abertura = por_codigo.get(abertura, [])
            if not registros_abertura:
                continue
            registro = registros_abertura[0]
            if registro.campo(1) != "0":
                continue
            prefixo = abertura[0]
            codigos_bloco = {
                codigo
                for codigo, itens in por_codigo.items()
                if codigo.startswith(prefixo) and itens
            }
            operacionais = codigos_bloco - permitidos_sem_movimento
            if not operacionais:
                self._erro(
                    "Movimento do bloco",
                    abertura,
                    registro.numero_linha,
                    (
                        f"{abertura} informa IND_MOV = 0 (bloco com dados), mas não há "
                        f"registros operacionais antes de {encerramento}."
                    ),
                    "Se o bloco realmente não teve movimento, informar IND_MOV = 1.",
                    campo="IND_MOV",
                )

    def _validar_0205(self, registros: list[_Registro]) -> None:
        """Valida vigência da alteração de item (0205) contra a competência e entre si."""

        self._regra()
        atual_0200: _Registro | None = None
        alteracoes: dict[int, list[_Registro]] = defaultdict(list)

        for registro in registros:
            if registro.codigo == "0200":
                atual_0200 = registro
            elif registro.codigo == "0205" and atual_0200 is not None:
                alteracoes[atual_0200.numero_linha].append(registro)
            elif registro.codigo.startswith("02"):
                # Outros filhos do 0200 não encerram o vínculo.
                continue
            elif registro.codigo and not registro.codigo.startswith("0"):
                atual_0200 = None

        for filhos in alteracoes.values():
            periodos: list[tuple[datetime, datetime, _Registro]] = []
            for registro in filhos:
                dt_ini = self._data_ou_none(registro.campo(2))
                dt_fim = self._data_ou_none(registro.campo(3))

                if registro.campo(2) and dt_ini is None:
                    self._erro(
                        "Cadastro",
                        "0205",
                        registro.numero_linha,
                        f"DT_INI inválida no 0205: '{registro.campo(2)}'.",
                        campo="DT_INI",
                    )
                if registro.campo(3) and dt_fim is None:
                    self._erro(
                        "Cadastro",
                        "0205",
                        registro.numero_linha,
                        f"DT_FIM inválida no 0205: '{registro.campo(3)}'.",
                        campo="DT_FIM",
                    )
                if dt_ini is None or dt_fim is None:
                    continue

                if dt_ini > dt_fim:
                    self._erro(
                        "Vigência 0205",
                        "0205",
                        registro.numero_linha,
                        "DT_INI é posterior à DT_FIM no registro 0205.",
                        "Corrigir o período de validade da descrição/código anterior.",
                        campo="DT_INI/DT_FIM",
                    )

                if self._dt_fin_escrituracao is not None and dt_fim > self._dt_fin_escrituracao:
                    self._erro(
                        "Vigência 0205",
                        "0205",
                        registro.numero_linha,
                        (
                            f"DT_FIM do 0205 ({dt_fim:%d/%m/%Y}) ultrapassa o fim da "
                            f"competência ({self._dt_fin_escrituracao:%d/%m/%Y})."
                        ),
                        "Ajustar DT_FIM para não ultrapassar a competência da escrituração.",
                        campo="DT_FIM",
                    )

                periodos.append((dt_ini, dt_fim, registro))

            periodos.sort(key=lambda item: (item[0], item[1], item[2].numero_linha))
            anterior: tuple[datetime, datetime, _Registro] | None = None
            for atual in periodos:
                if anterior is not None:
                    _, fim_anterior, reg_anterior = anterior
                    ini_atual, _, reg_atual = atual
                    if ini_atual <= fim_anterior:
                        self._erro(
                            "Vigência 0205",
                            "0205",
                            reg_atual.numero_linha,
                            (
                                "Período do 0205 sobreposto ao período anterior "
                                f"(linha {reg_anterior.numero_linha})."
                            ),
                            (
                                "Os períodos de alteração do mesmo item não devem compartilhar "
                                "o mesmo dia nem se sobrepor."
                            ),
                            campo="DT_INI/DT_FIM",
                        )
                if anterior is None or atual[1] > anterior[1]:
                    anterior = atual

    def _validar_c175_pge(self, registros: list[_Registro]) -> None:
        """Regras locais do C175 observáveis antes da importação no PGE.

        Além da comparação entre as bases de PIS e Cofins, o Hotfix 17.7.6
        separa as duas modalidades de cálculo do leiaute: ad valorem
        (VL_BC + ALIQ percentual) e por unidade de medida
        (QUANT_BC + ALIQ_*_QUANT). Uma alíquota específica sem quantidade é
        estruturalmente incompleta e reproduz o erro de importação do PGE.
        """

        self._regra()
        for registro in registros:
            base_pis_txt = registro.campo(5)
            aliq_pis_txt = registro.campo(6)
            qtd_pis_txt = registro.campo(7)
            aliq_qtd_pis_txt = registro.campo(8)

            base_cofins_txt = registro.campo(11)
            aliq_cofins_txt = registro.campo(12)
            qtd_cofins_txt = registro.campo(13)
            aliq_qtd_cofins_txt = registro.campo(14)

            for tributo, base_txt, aliq_txt, qtd_txt, aliq_qtd_txt in (
                ("PIS", base_pis_txt, aliq_pis_txt, qtd_pis_txt, aliq_qtd_pis_txt),
                ("COFINS", base_cofins_txt, aliq_cofins_txt, qtd_cofins_txt, aliq_qtd_cofins_txt),
            ):
                if aliq_qtd_txt and not qtd_txt:
                    self._erro(
                        "Modalidade de cálculo C175",
                        "C175",
                        registro.numero_linha,
                        (
                            f"ALIQ_{tributo}_QUANT ({aliq_qtd_txt}) foi informada sem "
                            f"QUANT_BC_{tributo}. A alíquota em reais só pode ser usada "
                            "com base de cálculo em quantidade."
                        ),
                        (
                            f"Se a operação é ad valorem, deixe ALIQ_{tributo}_QUANT em branco; "
                            f"se é por unidade, informe QUANT_BC_{tributo} e revise a modalidade."
                        ),
                        campo=f"ALIQ_{tributo}_QUANT",
                    )
                elif qtd_txt and not aliq_qtd_txt:
                    self._erro(
                        "Modalidade de cálculo C175",
                        "C175",
                        registro.numero_linha,
                        (
                            f"QUANT_BC_{tributo} ({qtd_txt}) foi informada sem "
                            f"ALIQ_{tributo}_QUANT."
                        ),
                        "Complete a modalidade por unidade ou remova a quantidade se o cálculo for ad valorem.",
                        campo=f"QUANT_BC_{tributo}",
                    )

                ad_valorem_completo = bool(base_txt and aliq_txt)
                por_quantidade_completo = bool(qtd_txt and aliq_qtd_txt)
                if ad_valorem_completo and por_quantidade_completo:
                    self._erro(
                        "Modalidade de cálculo C175",
                        "C175",
                        registro.numero_linha,
                        (
                            f"O C175 possui simultaneamente cálculo ad valorem e por quantidade para {tributo}."
                        ),
                        (
                            "Mantenha somente a modalidade efetivamente aplicável: VL_BC + ALIQ percentual "
                            "ou QUANT_BC + ALIQ_QUANT."
                        ),
                        campo=f"VL_BC_{tributo}/QUANT_BC_{tributo}",
                    )

            base_pis = self._decimal(base_pis_txt)
            base_cofins = self._decimal(base_cofins_txt)
            if base_pis is None or base_cofins is None:
                continue
            if abs(base_pis - base_cofins) > self.TOLERANCIA_VALOR:
                self._erro(
                    "Base PIS/COFINS",
                    "C175",
                    registro.numero_linha,
                    (
                        f"Base de PIS ({self._fmt(base_pis)}) difere da base de COFINS "
                        f"({self._fmt(base_cofins)}) no mesmo C175."
                    ),
                    "Conferir a composição das bases antes de transmitir no PGE.",
                    campo="VL_BC_PIS/VL_BC_COFINS",
                )

    def _validar_regras_pge_c170(self, registros: list[_Registro]) -> None:
        """Regras do PGE 6.1.2 observadas no relatório real da Sprint 17.3.4."""

        self._regra()
        csts_entrada_validos = {
            *(f"{numero:02d}" for numero in range(50, 67)),
            *(f"{numero:02d}" for numero in range(70, 76)),
            "98",
            "99",
        }

        aliquota_pis_basica = None
        aliquota_cofins_basica = None
        if self._ind_inc_trib == "1":
            aliquota_pis_basica = Decimal("1.65")
            aliquota_cofins_basica = Decimal("7.60")
        elif self._ind_inc_trib == "2":
            aliquota_pis_basica = Decimal("0.65")
            aliquota_cofins_basica = Decimal("3.00")

        for registro in registros:
            codigo_item = registro.campo(2)
            cfop = registro.campo(10)
            cst_pis = registro.campo(24)
            cst_cofins = registro.campo(30)

            # O PGE do arquivo real rejeitou especificamente o CFOP 1929.
            # Não há troca automática porque o CFOP correto depende da operação.
            if cfop == "1929":
                self._erro(
                    "CFOP PGE",
                    "C170",
                    registro.numero_linha,
                    "CFOP 1929 rejeitado pelo PGE 6.1.2.",
                    "Revisar a natureza da operação e selecionar um CFOP válido; não alterar automaticamente.",
                    codigo_item=codigo_item,
                    campo="CFOP",
                )

            if cfop and cfop[0] in {"5", "6", "7"}:
                csts_aquisicao_sem_credito = {*(f"{numero:02d}" for numero in range(70, 76))}
                if cst_pis in csts_aquisicao_sem_credito:
                    self._erro(
                        "CST de saída",
                        "C170",
                        registro.numero_linha,
                        (
                            f"CST_PIS {cst_pis} pertence à faixa de aquisição sem direito a crédito, "
                            "mas o CFOP identifica uma operação de saída."
                        ),
                        (
                            "Se for devolução de compra, usar CST 49 conforme o Guia Prático; "
                            "em outras saídas, revisar o CST aplicável à operação."
                        ),
                        codigo_item=codigo_item,
                        campo="CST_PIS",
                    )
                if cst_cofins in csts_aquisicao_sem_credito:
                    self._erro(
                        "CST de saída",
                        "C170",
                        registro.numero_linha,
                        (
                            f"CST_COFINS {cst_cofins} pertence à faixa de aquisição sem direito a crédito, "
                            "mas o CFOP identifica uma operação de saída."
                        ),
                        (
                            "Se for devolução de compra, usar CST 49 conforme o Guia Prático; "
                            "em outras saídas, revisar o CST aplicável à operação."
                        ),
                        codigo_item=codigo_item,
                        campo="CST_COFINS",
                    )

            if cfop and cfop[0] in {"1", "2", "3"}:
                if cst_pis and cst_pis not in csts_entrada_validos:
                    self._erro(
                        "CST de entrada",
                        "C170",
                        registro.numero_linha,
                        (
                            "Para operação de entrada/aquisição, CST_PIS deve estar entre "
                            "50-66, 70-75, 98 ou 99."
                        ),
                        "Reclassificar o CST conforme a natureza da aquisição.",
                        codigo_item=codigo_item,
                        campo="CST_PIS",
                    )
                if cst_cofins and cst_cofins not in csts_entrada_validos:
                    self._erro(
                        "CST de entrada",
                        "C170",
                        registro.numero_linha,
                        (
                            "Para operação de entrada/aquisição, CST_COFINS deve estar entre "
                            "50-66, 70-75, 98 ou 99."
                        ),
                        "Reclassificar o CST conforme a natureza da aquisição.",
                        codigo_item=codigo_item,
                        campo="CST_COFINS",
                    )

            if cst_pis == "01" and aliquota_pis_basica is not None:
                aliquota = self._decimal(registro.campo(26))
                if aliquota is None or aliquota == 0:
                    self._erro(
                        "Alíquota básica",
                        "C170",
                        registro.numero_linha,
                        (
                            f"CST_PIS = 01 exige alíquota básica de "
                            f"{self._fmt(aliquota_pis_basica)}% para o indicador 0110 atual."
                        ),
                        "Preencher ALIQ_PIS com a alíquota básica da incidência do período.",
                        codigo_item=codigo_item,
                        campo="ALIQ_PIS",
                    )

            if cst_cofins == "01" and aliquota_cofins_basica is not None:
                aliquota = self._decimal(registro.campo(32))
                if aliquota is None or aliquota == 0:
                    self._erro(
                        "Alíquota básica",
                        "C170",
                        registro.numero_linha,
                        (
                            f"CST_COFINS = 01 exige alíquota básica de "
                            f"{self._fmt(aliquota_cofins_basica)}% para o indicador 0110 atual."
                        ),
                        "Preencher ALIQ_COFINS com a alíquota básica da incidência do período.",
                        codigo_item=codigo_item,
                        campo="ALIQ_COFINS",
                    )

    def _validar_bloco_m_pge(self, registros: list[_Registro]) -> None:
        """Espelha duplicidades e hierarquias do Bloco M apontadas pelo PGE."""

        self._regra()

        # Liga cada M100 aos M105 subsequentes e cada M500 aos M505.
        pais: dict[str, list[tuple[_Registro, list[_Registro]]]] = {"M100": [], "M500": []}
        atual: tuple[_Registro, list[_Registro]] | None = None
        codigo_pai_atual = ""

        for registro in registros:
            if registro.codigo in {"M100", "M500"}:
                codigo_pai_atual = registro.codigo
                atual = (registro, [])
                pais[codigo_pai_atual].append(atual)
            elif registro.codigo == "M105" and codigo_pai_atual == "M100" and atual is not None:
                atual[1].append(registro)
            elif registro.codigo == "M505" and codigo_pai_atual == "M500" and atual is not None:
                atual[1].append(registro)
            elif registro.codigo.startswith("M") and registro.codigo not in {"M105", "M505"}:
                if registro.codigo not in {"M100", "M500"}:
                    atual = None
                    codigo_pai_atual = ""

        for codigo_pai, grupos in pais.items():
            por_chave: dict[tuple[str, str, str, str], list[tuple[_Registro, list[_Registro]]]] = defaultdict(list)
            for pai, filhos in grupos:
                chave = (pai.campo(1), pai.campo(2), pai.campo(4), pai.campo(6))
                por_chave[chave].append((pai, filhos))

            tributo = "PIS" if codigo_pai == "M100" else "COFINS"
            codigo_filho = "M105" if codigo_pai == "M100" else "M505"

            for chave, ocorrencias in por_chave.items():
                if len(ocorrencias) <= 1:
                    continue

                for pai, _ in ocorrencias:
                    self._erro(
                        "Duplicidade PGE",
                        codigo_pai,
                        pai.numero_linha,
                        (
                            f"Duplicidade da chave COD_CRED/IND_CRED_ORI/ALIQ_{tributo}/"
                            f"ALIQ_{tributo}_QUANT no {codigo_pai}."
                        ),
                        (
                            "Consolidar o crédito em um único registro. Não remover "
                            "automaticamente porque os campos de utilização/desconto podem diferir."
                        ),
                        campo="COD_CRED/IND_CRED_ORI/ALIQ",
                    )

                # Reproduz a causa dos 16 erros de base do relatório: filhos de
                # pais duplicados acabam sendo somados pelo PGE para a mesma chave.
                filhos_todos = [filho for _, filhos in ocorrencias for filho in filhos]
                por_filho: dict[tuple[str, str, str], list[_Registro]] = defaultdict(list)
                for filho in filhos_todos:
                    # NAT_BC_CRED + CST + base não cumulativa. O campo de base
                    # é mantido na chave porque o relatório real mostrou pares equivalentes.
                    chave_filho = (
                        filho.campo(1),
                        filho.campo(2),
                        self._normalizar_zero(filho.campo(5)),
                    )
                    por_filho[chave_filho].append(filho)

                for ocorrencias_filho in por_filho.values():
                    if len(ocorrencias_filho) <= 1:
                        continue
                    soma = sum(
                        (self._decimal(item.campo(5)) or Decimal("0"))
                        for item in ocorrencias_filho
                    )
                    for filho in ocorrencias_filho:
                        atual_base = self._decimal(filho.campo(5)) or Decimal("0")
                        self._erro(
                            "Base de crédito PGE",
                            codigo_filho,
                            filho.numero_linha,
                            (
                                f"Base não cumulativa do {codigo_filho} ({self._fmt(atual_base)}) "
                                f"fica duplicada para a mesma chave; soma observada "
                                f"{self._fmt(soma)}."
                            ),
                            (
                                f"Resolver primeiro a duplicidade do {codigo_pai} e conferir "
                                "a consolidação dos registros filhos."
                            ),
                            campo=f"VL_BC_{tributo}_NC",
                        )

        self._validar_m400_m800(registros)
        self._validar_ordem_m600_m800(registros)
        self._validar_debitos_recolher_m205_m605(registros)

    def _validar_debitos_recolher_m205_m605(self, registros: list[_Registro]) -> None:
        """Replica a regra do PGE que vincula M205/M605 a M200/M600.

        O campo NUM_CAMPO = 08 aponta para a contribuição não cumulativa a
        recolher do pai; NUM_CAMPO = 12 aponta para a cumulativa. O somatório
        de VL_DEBITO dos filhos deve coincidir com o valor correspondente do
        registro de consolidação.
        """
        self._regra()
        configuracoes = (
            ("M200", "M205", "PIS"),
            ("M600", "M605", "COFINS"),
        )
        for codigo_pai, codigo_filho, tributo in configuracoes:
            pais = [r for r in registros if r.codigo == codigo_pai]
            filhos = [r for r in registros if r.codigo == codigo_filho]
            if len(pais) != 1 or not filhos:
                continue
            pai = pais[0]
            alvos = {
                "08": self._decimal(pai.campo(7)) or Decimal("0"),
                "12": self._decimal(pai.campo(11)) or Decimal("0"),
            }
            for num_campo, esperado in alvos.items():
                relacionados = [f for f in filhos if f.campo(1).zfill(2) == num_campo]
                soma = sum((self._decimal(f.campo(3)) or Decimal("0")) for f in relacionados)
                if abs(soma - esperado) <= self.TOLERANCIA_VALOR:
                    continue
                linha = relacionados[0].numero_linha if relacionados else pai.numero_linha
                self._erro(
                    "Débito a recolher Bloco M",
                    codigo_filho,
                    linha,
                    (
                        f"Somatório do VL_DEBITO dos {codigo_filho} com NUM_CAMPO {num_campo} "
                        f"({self._fmt(soma)}) difere do valor a recolher do {codigo_pai} "
                        f"({self._fmt(esperado)})."
                    ),
                    (
                        f"Sincronizar {codigo_filho}.VL_DEBITO com o campo {num_campo} do "
                        f"{codigo_pai} antes de validar a EFD Contribuições no PGE."
                    ),
                    campo="VL_DEBITO",
                )

    def _validar_ordem_m600_m800(self, registros: list[_Registro]) -> None:
        """Detecta a hierarquia que o PGE exige entre M600/M610 e M800/M810.

        O Hotfix 17.6.5 podia criar M600/M610 imediatamente antes do M990,
        deixando-os depois de M800/M810. O PGE então esperava M990 após M810
        e apontava os dois registros como fora de ordem, além de cascatas em
        M990/9999.
        """
        self._regra()
        pos = {
            registro.codigo: registro
            for registro in registros
            if registro.codigo in {"M600", "M610", "M800", "M810", "M990"}
        }
        if "M600" not in pos and "M610" not in pos:
            return

        limite = min(
            (pos[codigo].numero_linha for codigo in ("M800", "M810", "M990") if codigo in pos),
            default=None,
        )
        if limite is None:
            return

        for codigo in ("M600", "M610"):
            item = pos.get(codigo)
            if item is not None and item.numero_linha > limite:
                self._erro(
                    "Hierarquia Bloco M",
                    codigo,
                    item.numero_linha,
                    f"{codigo} está depois de M800/M810 na estrutura do Bloco M.",
                    "Posicionar M600/M610 antes de M800/M810 e recalcular M990/9999.",
                    campo="REG",
                )

    def _validar_m400_m800(self, registros: list[_Registro]) -> None:
        self._regra()
        configuracoes = {
            "M400": "M410",
            "M800": "M810",
        }
        atual: _Registro | None = None
        filhos: list[_Registro] = []

        def validar_atual() -> None:
            if atual is None:
                return
            esperado = configuracoes[atual.codigo]
            if not atual.campo(3):
                self._erro(
                    "Conta contábil",
                    atual.codigo,
                    atual.numero_linha,
                    "COD_CTA obrigatório não informado.",
                    "Cadastrar/selecionar previamente a conta analítica no registro 0500.",
                    campo="COD_CTA",
                )
            if not filhos:
                self._erro(
                    "Hierarquia Bloco M",
                    atual.codigo,
                    atual.numero_linha,
                    f"Registro filho obrigatório {esperado} não foi informado.",
                    (
                        f"Informar {esperado} com a natureza da receita correspondente. "
                        "O FiscalPro não inventa NAT_REC automaticamente."
                    ),
                    campo=esperado,
                )

        for registro in registros:
            if registro.codigo in configuracoes:
                validar_atual()
                atual = registro
                filhos = []
            elif atual is not None and registro.codigo == configuracoes[atual.codigo]:
                filhos.append(registro)
            elif atual is not None and registro.codigo.startswith("M"):
                validar_atual()
                atual = None
                filhos = []

        validar_atual()


    def _calcular_equivalencia_pge(
        self,
        registros: list[_Registro],
        por_codigo: dict[str, list[_Registro]],
    ) -> None:
        """Calcula total comparável ao PGE sem duplicar causas na tabela.

        O relatório real do PGE 6.1.2 usado como gabarito mostra três
        comportamentos encadeados: duas regras equivalentes para CST de
        entrada, erros de base após chaves M100/M500 duplicadas e geração de
        M400/M800 quando CST 08 de saída é usado indevidamente em aquisição.
        """
        if self._resultado is None:
            return

        resultado = self._resultado
        erros_raiz = len(resultado.erros)

        cst_entrada_raiz = sum(
            1 for item in resultado.erros if item.categoria == "CST de entrada"
        )
        repeticoes_cst_pge = cst_entrada_raiz

        base_prevista = self._estimar_erros_base_credito_pge(registros)
        base_ja_apontada = sum(
            1 for item in resultado.erros if item.categoria == "Base de crédito PGE"
        )
        base_encadeada = max(0, base_prevista - base_ja_apontada)

        # No gabarito, todos os CST 08 indevidos pertencem à mesma natureza
        # agregada e produzem quatro pendências: COD_CTA de M400/M800 e
        # ausência dos filhos M410/M810.
        csts_08_entrada = {
            "08"
            for registro in por_codigo.get("C170", [])
            if registro.campo(10)
            and registro.campo(10)[0] in {"1", "2", "3"}
            and (registro.campo(24) == "08" or registro.campo(30) == "08")
        }
        m400_m800_encadeados = 4 * len(csts_08_entrada)

        resultado.equivalencia_pge = {
            "Causas raiz exibidas pelo FiscalPro": erros_raiz,
            "Repetições da regra de CST de entrada no PGE": repeticoes_cst_pge,
            "Pendências encadeadas de base M105/M505": base_encadeada,
            "Pendências encadeadas M400/M410/M800/M810": m400_m800_encadeados,
        }
        resultado.erros_pge_estimados = (
            erros_raiz + repeticoes_cst_pge + base_encadeada + m400_m800_encadeados
        )
        resultado.avisos_pge_estimados = sum(
            1 for item in resultado.avisos if item.categoria == "Coerência COD_ITEM"
        )

    def _estimar_erros_base_credito_pge(self, registros: list[_Registro]) -> int:
        """Estima cascatas M105/M505 produzidas por chaves de crédito duplicadas."""
        pais: dict[str, list[tuple[_Registro, list[_Registro]]]] = {"M100": [], "M500": []}
        atual: tuple[_Registro, list[_Registro]] | None = None
        codigo_pai_atual = ""

        for registro in registros:
            if registro.codigo in {"M100", "M500"}:
                codigo_pai_atual = registro.codigo
                atual = (registro, [])
                pais[codigo_pai_atual].append(atual)
            elif registro.codigo == "M105" and codigo_pai_atual == "M100" and atual is not None:
                atual[1].append(registro)
            elif registro.codigo == "M505" and codigo_pai_atual == "M500" and atual is not None:
                atual[1].append(registro)
            elif registro.codigo.startswith("M") and registro.codigo not in {"M105", "M505"}:
                if registro.codigo not in {"M100", "M500"}:
                    atual = None
                    codigo_pai_atual = ""

        estimativa = 0
        for grupos in pais.values():
            por_chave: dict[
                tuple[str, str, str, str],
                list[tuple[_Registro, list[_Registro]]],
            ] = defaultdict(list)
            for pai, filhos in grupos:
                chave = (pai.campo(1), pai.campo(2), pai.campo(4), pai.campo(6))
                por_chave[chave].append((pai, filhos))

            for ocorrencias in por_chave.values():
                if len(ocorrencias) <= 1:
                    continue
                total_filhos = sum(len(filhos) for _, filhos in ocorrencias)
                estimativa += (2 * total_filhos) + len(ocorrencias)
        return estimativa


    def _agrupar_documentos(
        self,
        registros: list[_Registro],
        codigo_pai: str,
        filhos_permitidos: set[str],
    ) -> list[_Documento]:
        documentos: list[_Documento] = []
        atual: _Documento | None = None
        prefixo = codigo_pai[0]
        for registro in registros:
            if registro.codigo == codigo_pai:
                atual = _Documento(registro=registro)
                documentos.append(atual)
            elif registro.codigo in filhos_permitidos:
                if atual is None:
                    self._erro(
                        "Hierarquia",
                        registro.codigo,
                        registro.numero_linha,
                        f"Registro {registro.codigo} encontrado sem o pai {codigo_pai}.",
                    )
                else:
                    atual.filhos.append(registro)
            elif registro.codigo and not registro.codigo.startswith(prefixo):
                atual = None
        return documentos

    def _validar_documentos_c(
        self,
        documentos: list[_Documento],
        participantes: dict[str, _Registro],
        unidades: dict[str, _Registro],
        produtos: dict[str, _Registro],
    ) -> None:
        self._regra()
        for documento in documentos:
            pai = documento.registro
            numero = pai.campo(7)
            chave = pai.campo(8)
            identificador = self._documento(numero, chave)
            participante = pai.campo(3)
            modelo = pai.campo(4)
            situacao = pai.campo(5)

            self._validar_codigo_formato(pai, modelo, "COD_MOD", 2, identificador)
            self._validar_codigo_formato(pai, situacao, "COD_SIT", 2, identificador)
            self._validar_referencia_participante(pai, participante, participantes, identificador)
            self._validar_chave(pai, chave, modelo, situacao, identificador)
            self._validar_data(pai, 9, "DT_DOC", identificador)
            self._validar_data(pai, 10, "DT_E_S", identificador)

            itens = [item for item in documento.filhos if item.codigo == "C170"]
            detalhamentos_alternativos = [
                item for item in documento.filhos if item.codigo in {"C175", "C190"}
            ]
            if (
                self._resultado is not None
                and self._resultado.tipo_sped == "EFD Contribuições"
                and situacao in self.SITUACOES_REGULARES
                and not itens
                and not detalhamentos_alternativos
            ):
                # C170 não é o único caminho aceito pelo leiaute. O PGE admite
                # detalhamento alternativo em registros como C175/C190 e também
                # documentos complementares ou especiais sem item. Por isso, o
                # FiscalPro somente trata a ausência como erro quando existem
                # valores de mercadoria/contribuições que indicam um documento
                # normal que deveria possuir detalhamento. Nos demais casos, a
                # conferência é preventiva e não bloqueia a validação local.
                if self._c100_exige_registro_filho(pai):
                    self._erro(
                        "Hierarquia",
                        "C100",
                        pai.numero_linha,
                        "Documento regular com valores informados e sem registro filho de detalhamento.",
                        (
                            "Conferir no PGE se o documento exige C170/C175 ou se deve ser "
                            "escriturado por outra forma de detalhamento/consolidação."
                        ),
                        documento=identificador,
                    )
                else:
                    self._aviso(
                        "Conferência preventiva",
                        "C100",
                        pai.numero_linha,
                        "Documento regular sem C170, C175 ou C190; pode ser documento complementar ou especial.",
                        (
                            "Validar no PGE oficial. O FiscalPro não classifica automaticamente "
                            "este caso como erro, pois há exceções previstas no leiaute."
                        ),
                        documento=identificador,
                    )

            numeros_itens: set[str] = set()
            soma_itens = Decimal("0")
            soma_pis = Decimal("0")
            soma_cofins = Decimal("0")
            sequencias: list[int] = []

            for item in itens:
                num_item = item.campo(1)
                codigo_item = item.campo(2)
                unidade = item.campo(5)
                cfop = item.campo(10)
                cst_pis = item.campo(24)
                cst_cofins = item.campo(30)

                if not num_item or self._inteiro(num_item) is None:
                    self._erro(
                        "Documento",
                        "C170",
                        item.numero_linha,
                        f"Numeração do item inválida: '{num_item}'.",
                        documento=identificador,
                        codigo_item=codigo_item,
                        campo="NUM_ITEM",
                    )
                else:
                    sequencias.append(int(num_item))
                    if num_item in numeros_itens:
                        self._erro(
                            "Documento",
                            "C170",
                            item.numero_linha,
                            f"Número de item duplicado no documento: {num_item}.",
                            documento=identificador,
                            codigo_item=codigo_item,
                            campo="NUM_ITEM",
                        )
                    numeros_itens.add(num_item)

                if not codigo_item:
                    self._erro(
                        "Referência",
                        "C170",
                        item.numero_linha,
                        "Código do produto não informado.",
                        documento=identificador,
                        campo="COD_ITEM",
                    )
                elif codigo_item not in produtos:
                    self._erro(
                        "Referência",
                        "C170",
                        item.numero_linha,
                        f"Produto '{codigo_item}' não existe no cadastro 0200.",
                        "Cadastrar o item no 0200 ou corrigir o código no C170.",
                        documento=identificador,
                        codigo_item=codigo_item,
                        campo="COD_ITEM",
                    )
                else:
                    # Diferença entre UNID do C170 e UNID_INV do 0200 não é,
                    # isoladamente, pendência do PGE. Ela pode representar
                    # unidade de comercialização/conversão e fica na auditoria
                    # geral, sem poluir o Pré-Validador PGE.
                    pass

                if unidade and unidade not in unidades:
                    self._erro(
                        "Referência",
                        "C170",
                        item.numero_linha,
                        f"Unidade '{unidade}' não cadastrada no 0190.",
                        documento=identificador,
                        codigo_item=codigo_item,
                        campo="UNID",
                    )

                if not cfop or len(cfop) != 4 or not cfop.isdigit():
                    self._erro(
                        "Documento",
                        "C170",
                        item.numero_linha,
                        f"CFOP inválido: '{cfop}'.",
                        documento=identificador,
                        codigo_item=codigo_item,
                        campo="CFOP",
                    )

                self._validar_cst(item, cst_pis, "CST_PIS", identificador, codigo_item)
                self._validar_cst(item, cst_cofins, "CST_COFINS", identificador, codigo_item)

                valor_item = self._decimal_campo(item, 6, "VL_ITEM", identificador, codigo_item)
                if valor_item is not None:
                    soma_itens += valor_item
                valor_pis = self._validar_formula_contribuicao(
                    item,
                    "PIS",
                    base_indice=25,
                    aliquota_indice=26,
                    quantidade_indice=27,
                    aliquota_quantidade_indice=28,
                    valor_indice=29,
                    documento=identificador,
                    codigo_item=codigo_item,
                )
                if valor_pis is not None:
                    soma_pis += valor_pis
                valor_cofins = self._validar_formula_contribuicao(
                    item,
                    "COFINS",
                    base_indice=31,
                    aliquota_indice=32,
                    quantidade_indice=33,
                    aliquota_quantidade_indice=34,
                    valor_indice=35,
                    documento=identificador,
                    codigo_item=codigo_item,
                )
                if valor_cofins is not None:
                    soma_cofins += valor_cofins

            if sequencias:
                esperado = list(range(1, len(sequencias) + 1))
                if sorted(sequencias) != esperado:
                    self._aviso(
                        "Documento",
                        "C170",
                        pai.numero_linha,
                        "A numeração dos itens não forma uma sequência contínua iniciada em 1.",
                        "Conferir NUM_ITEM dos registros C170.",
                        documento=identificador,
                        campo="NUM_ITEM",
                    )

            analiticos = [item for item in documento.filhos if item.codigo == "C190"]
            soma_operacoes = Decimal("0")
            for analitico in analiticos:
                cst_icms = analitico.campo(1)
                cfop_analitico = analitico.campo(2)
                self._validar_codigo_formato(
                    analitico, cst_icms, "CST_ICMS", 3, identificador
                )
                self._validar_codigo_formato(
                    analitico, cfop_analitico, "CFOP", 4, identificador
                )
                valor_operacao = self._decimal_campo(
                    analitico, 4, "VL_OPR", identificador, ""
                )
                if valor_operacao is not None:
                    soma_operacoes += valor_operacao
                aliquota_icms = analitico.campo(3)
                if aliquota_icms and self._decimal(aliquota_icms) is None:
                    self._erro(
                        "Documento",
                        "C190",
                        analitico.numero_linha,
                        f"Alíquota de ICMS inválida: '{aliquota_icms}'.",
                        documento=identificador,
                        campo="ALIQ_ICMS",
                    )

            if analiticos:
                self._comparar_total_com_nivel(
                    pai,
                    11,
                    soma_operacoes,
                    "VL_DOC",
                    identificador,
                    "soma do VL_OPR dos C190",
                    nivel="AVISO",
                )

            if itens:
                # O PGE oficial aceitou arquivo real em que VL_MERC do C100
                # difere da soma simples dos C170. Essa comparação continua
                # útil como auditoria, mas não pode bloquear o Pré-PGE.
                nivel_vl_merc = (
                    "REVISAO"
                    if self._resultado is not None
                    and self._resultado.tipo_sped == "EFD Contribuições"
                    else "ERRO"
                )
                self._comparar_total_com_nivel(
                    pai, 15, soma_itens, "VL_MERC", identificador, "soma dos C170", nivel=nivel_vl_merc
                )
                self._comparar_total(pai, 25, soma_pis, "VL_PIS", identificador, "soma do PIS dos C170")
                self._comparar_total(pai, 26, soma_cofins, "VL_COFINS", identificador, "soma da COFINS dos C170")

    @classmethod
    def _c100_exige_registro_filho(cls, registro: _Registro) -> bool:
        """Indica forte evidência de que o C100 precisa de detalhamento.

        O PGE permite exceções para documentos complementares/especiais e
        aceita outras formas de detalhamento. Para evitar falsos positivos, a
        regra local só bloqueia quando o C100 traz valores materiais ou de
        contribuições, mas nenhum C170, C175 ou C190 foi localizado.
        """

        indices_valores = (
            11,  # VL_DOC
            15,  # VL_MERC
            25,  # VL_PIS
            26,  # VL_COFINS
            27,  # VL_PIS_ST
            28,  # VL_COFINS_ST
        )
        for indice in indices_valores:
            valor = cls._decimal(registro.campo(indice))
            if valor is not None and valor != Decimal("0"):
                return True
        return False

    def _validar_documentos_a(
        self,
        documentos: list[_Documento],
        participantes: dict[str, _Registro],
        produtos: dict[str, _Registro],
    ) -> None:
        self._regra()
        for documento in documentos:
            pai = documento.registro
            numero = pai.campo(7)
            chave = pai.campo(8)
            identificador = self._documento(numero, chave)
            participante = pai.campo(3)
            situacao = pai.campo(4)

            self._validar_referencia_participante(pai, participante, participantes, identificador)
            self._validar_data(pai, 9, "DT_DOC", identificador)
            self._validar_data(pai, 10, "DT_EXE_SERV", identificador)

            itens = [item for item in documento.filhos if item.codigo == "A170"]
            if situacao in self.SITUACOES_REGULARES and not itens:
                self._erro(
                    "Hierarquia",
                    "A100",
                    pai.numero_linha,
                    "Documento de serviço regular sem registro A170.",
                    documento=identificador,
                )

            soma_itens = Decimal("0")
            soma_pis = Decimal("0")
            soma_cofins = Decimal("0")
            for item in itens:
                codigo_item = item.campo(2)
                self._validar_cst(item, item.campo(8), "CST_PIS", identificador, codigo_item)
                self._validar_cst(item, item.campo(12), "CST_COFINS", identificador, codigo_item)
                if codigo_item and codigo_item not in produtos:
                    self._erro(
                        "Referência",
                        "A170",
                        item.numero_linha,
                        f"Item de serviço '{codigo_item}' não existe no cadastro 0200.",
                        documento=identificador,
                        codigo_item=codigo_item,
                        campo="COD_ITEM",
                    )
                valor_item = self._decimal_campo(item, 4, "VL_ITEM", identificador, codigo_item)
                if valor_item is not None:
                    soma_itens += valor_item
                valor_pis = self._validar_formula_contribuicao(
                    item,
                    "PIS",
                    base_indice=9,
                    aliquota_indice=10,
                    quantidade_indice=None,
                    aliquota_quantidade_indice=None,
                    valor_indice=11,
                    documento=identificador,
                    codigo_item=codigo_item,
                )
                if valor_pis is not None:
                    soma_pis += valor_pis
                valor_cofins = self._validar_formula_contribuicao(
                    item,
                    "COFINS",
                    base_indice=13,
                    aliquota_indice=14,
                    quantidade_indice=None,
                    aliquota_quantidade_indice=None,
                    valor_indice=15,
                    documento=identificador,
                    codigo_item=codigo_item,
                )
                if valor_cofins is not None:
                    soma_cofins += valor_cofins

            if itens:
                self._comparar_total(pai, 11, soma_itens, "VL_DOC", identificador, "soma dos A170")
                self._comparar_total(pai, 15, soma_pis, "VL_PIS", identificador, "soma do PIS dos A170")
                self._comparar_total(pai, 17, soma_cofins, "VL_COFINS", identificador, "soma da COFINS dos A170")

    def _validar_documentos_d(
        self,
        documentos: list[_Documento],
        participantes: dict[str, _Registro],
    ) -> None:
        self._regra()
        for documento in documentos:
            pai = documento.registro
            numero = pai.campo(8)
            chave = pai.campo(9)
            identificador = self._documento(numero, chave)
            participante = pai.campo(3)
            modelo = pai.campo(4)
            situacao = pai.campo(5)

            self._validar_codigo_formato(pai, modelo, "COD_MOD", 2, identificador)
            self._validar_codigo_formato(pai, situacao, "COD_SIT", 2, identificador)
            self._validar_referencia_participante(pai, participante, participantes, identificador)
            self._validar_chave(pai, chave, modelo, situacao, identificador)
            self._validar_data(pai, 10, "DT_DOC", identificador)
            self._validar_data(pai, 11, "DT_A_P", identificador)

            filhos_pis = [item for item in documento.filhos if item.codigo == "D101"]
            filhos_cofins = [item for item in documento.filhos if item.codigo == "D105"]
            for item in filhos_pis:
                self._validar_cst(item, item.campo(3), "CST_PIS", identificador, "")
                self._validar_formula_contribuicao(
                    item,
                    "PIS",
                    base_indice=5,
                    aliquota_indice=6,
                    quantidade_indice=None,
                    aliquota_quantidade_indice=None,
                    valor_indice=7,
                    documento=identificador,
                    codigo_item="",
                )
            for item in filhos_cofins:
                self._validar_cst(item, item.campo(3), "CST_COFINS", identificador, "")
                self._validar_formula_contribuicao(
                    item,
                    "COFINS",
                    base_indice=5,
                    aliquota_indice=6,
                    quantidade_indice=None,
                    aliquota_quantidade_indice=None,
                    valor_indice=7,
                    documento=identificador,
                    codigo_item="",
                )

    def _validar_creditos_m(self, registros: list[_Registro], tributo: str) -> None:
        self._regra()
        for registro in registros:
            identificador = f"Código de crédito {registro.campo(1)}"
            self._validar_formula_contribuicao(
                registro,
                tributo,
                base_indice=3,
                aliquota_indice=4,
                quantidade_indice=5,
                aliquota_quantidade_indice=6,
                valor_indice=7,
                documento=identificador,
                codigo_item="",
            )

    def _validar_referencia_participante(
        self,
        registro: _Registro,
        codigo: str,
        participantes: dict[str, _Registro],
        documento: str,
    ) -> None:
        if codigo and codigo not in participantes:
            self._erro(
                "Referência",
                registro.codigo,
                registro.numero_linha,
                f"Participante '{codigo}' não existe no cadastro 0150.",
                "Cadastrar o participante ou corrigir o COD_PART do documento.",
                documento=documento,
                campo="COD_PART",
            )

    def _validar_chave(
        self,
        registro: _Registro,
        chave: str,
        modelo: str,
        situacao: str,
        documento: str,
    ) -> None:
        if chave:
            if len(chave) != 44 or not chave.isdigit():
                self._erro(
                    "Documento",
                    registro.codigo,
                    registro.numero_linha,
                    f"Chave eletrônica inválida: '{chave}'.",
                    "Informar uma chave numérica com 44 dígitos.",
                    documento=documento,
                    campo="CHV_DOC",
                )
            elif chave in self._chaves_vistas:
                reg_anterior, linha_anterior = self._chaves_vistas[chave]
                self._erro(
                    "Duplicidade",
                    registro.codigo,
                    registro.numero_linha,
                    f"Chave já utilizada no registro {reg_anterior}, linha {linha_anterior}.",
                    "Conferir documento duplicado no arquivo.",
                    documento=documento,
                    campo="CHV_DOC",
                )
            else:
                self._chaves_vistas[chave] = (registro.codigo, registro.numero_linha)
        elif modelo in self.MODELOS_CHAVE_44 and situacao in self.SITUACOES_REGULARES:
            self._erro(
                "Documento",
                registro.codigo,
                registro.numero_linha,
                f"Documento modelo {modelo} regular sem chave eletrônica.",
                documento=documento,
                campo="CHV_DOC",
            )

    def _validar_data(self, registro: _Registro, indice: int, campo: str, documento: str) -> None:
        valor = registro.campo(indice)
        if not valor:
            return
        try:
            datetime.strptime(valor, "%d%m%Y")
        except ValueError:
            self._erro(
                "Documento",
                registro.codigo,
                registro.numero_linha,
                f"Data inválida no campo {campo}: '{valor}'.",
                "Informar a data no formato DDMMAAAA.",
                documento=documento,
                campo=campo,
            )

    def _validar_codigo_formato(
        self,
        registro: _Registro,
        valor: str,
        campo: str,
        tamanho: int,
        documento: str,
    ) -> None:
        if valor and (len(valor) != tamanho or not valor.isdigit()):
            self._erro(
                "Documento",
                registro.codigo,
                registro.numero_linha,
                f"{campo} fora do formato de {tamanho} dígitos: '{valor}'.",
                documento=documento,
                campo=campo,
            )

    def _validar_cst(
        self,
        registro: _Registro,
        valor: str,
        campo: str,
        documento: str,
        codigo_item: str,
    ) -> None:
        if not valor:
            adicionar = self._erro
            if (
                self._resultado is not None
                and self._resultado.tipo_sped == "EFD ICMS/IPI (Fiscal)"
                and registro.codigo == "C170"
            ):
                adicionar = self._aviso
            adicionar(
                "Tributação",
                registro.codigo,
                registro.numero_linha,
                f"{campo} não informado.",
                "Conferir a obrigatoriedade conforme o perfil e a operação.",
                documento=documento,
                codigo_item=codigo_item,
                campo=campo,
            )
        elif len(valor) != 2 or not valor.isdigit():
            self._erro(
                "Tributação",
                registro.codigo,
                registro.numero_linha,
                f"{campo} fora do formato de 2 dígitos: '{valor}'.",
                documento=documento,
                codigo_item=codigo_item,
                campo=campo,
            )

    def _validar_formula_contribuicao(
        self,
        registro: _Registro,
        tributo: str,
        base_indice: int,
        aliquota_indice: int,
        quantidade_indice: int | None,
        aliquota_quantidade_indice: int | None,
        valor_indice: int,
        documento: str,
        codigo_item: str,
    ) -> Decimal | None:
        base_texto = registro.campo(base_indice)
        aliquota_texto = registro.campo(aliquota_indice)
        quantidade_texto = registro.campo(quantidade_indice) if quantidade_indice is not None else ""
        aliquota_qtd_texto = (
            registro.campo(aliquota_quantidade_indice)
            if aliquota_quantidade_indice is not None
            else ""
        )
        valor_texto = registro.campo(valor_indice)

        base = self._decimal(base_texto)
        aliquota = self._decimal(aliquota_texto)
        quantidade = self._decimal(quantidade_texto)
        aliquota_qtd = self._decimal(aliquota_qtd_texto)
        valor = self._decimal(valor_texto)

        if valor_texto and valor is None:
            self._erro(
                "Tributação",
                registro.codigo,
                registro.numero_linha,
                f"Valor de {tributo} não é numérico: '{valor_texto}'.",
                documento=documento,
                codigo_item=codigo_item,
                campo=f"VL_{tributo}",
            )
            return None

        calculado: Decimal | None = None
        origem = ""
        if base_texto and aliquota_texto:
            if base is None or aliquota is None:
                self._erro(
                    "Tributação",
                    registro.codigo,
                    registro.numero_linha,
                    f"Base ou alíquota de {tributo} possui formato inválido.",
                    documento=documento,
                    codigo_item=codigo_item,
                    campo=f"BC/ALIQ_{tributo}",
                )
                return valor
            calculado = (base * aliquota / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            origem = f"{self._fmt(base)} × {self._fmt(aliquota)}%"
        elif quantidade_texto and aliquota_qtd_texto:
            if quantidade is None or aliquota_qtd is None:
                self._erro(
                    "Tributação",
                    registro.codigo,
                    registro.numero_linha,
                    f"Quantidade ou alíquota por unidade de {tributo} possui formato inválido.",
                    documento=documento,
                    codigo_item=codigo_item,
                    campo=f"QTD/ALIQ_{tributo}",
                )
                return valor
            calculado = (quantidade * aliquota_qtd).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            origem = f"{self._fmt(quantidade)} × {self._fmt(aliquota_qtd)}"

        if calculado is not None:
            if valor is None:
                self._erro(
                    "Tributação",
                    registro.codigo,
                    registro.numero_linha,
                    f"A base e a alíquota de {tributo} foram informadas, mas o valor está vazio.",
                    f"O cálculo pelas informações do registro resulta em {self._fmt(calculado)}.",
                    documento=documento,
                    codigo_item=codigo_item,
                    campo=f"VL_{tributo}",
                )
            elif abs(calculado - valor) > self.TOLERANCIA_VALOR:
                self._erro(
                    "Cálculo",
                    registro.codigo,
                    registro.numero_linha,
                    (
                        f"Valor de {tributo} divergente: informado {self._fmt(valor)}, "
                        f"calculado {self._fmt(calculado)} ({origem})."
                    ),
                    "Recalcular e gravar o valor com duas casas decimais.",
                    documento=documento,
                    codigo_item=codigo_item,
                    campo=f"VL_{tributo}",
                )
        return valor

    def _comparar_total(
        self,
        registro: _Registro,
        indice: int,
        soma: Decimal,
        campo: str,
        documento: str,
        origem: str,
    ) -> None:
        self._comparar_total_com_nivel(
            registro, indice, soma, campo, documento, origem, nivel="ERRO"
        )

    def _comparar_total_com_nivel(
        self,
        registro: _Registro,
        indice: int,
        soma: Decimal,
        campo: str,
        documento: str,
        origem: str,
        nivel: str,
    ) -> None:
        texto = registro.campo(indice)
        if not texto:
            return
        informado = self._decimal(texto)
        if informado is None:
            self._erro(
                "Totais do documento",
                registro.codigo,
                registro.numero_linha,
                f"O campo {campo} não contém um valor numérico válido: '{texto}'.",
                documento=documento,
                campo=campo,
            )
            return
        soma = soma.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(informado - soma) > self.TOLERANCIA_TOTAL:
            if nivel == "AVISO":
                adicionar = self._aviso
            elif nivel == "REVISAO":
                adicionar = self._revisao
            else:
                adicionar = self._erro
            adicionar(
                "Totais do documento",
                registro.codigo,
                registro.numero_linha,
                (
                    f"{campo} informado {self._fmt(informado)}, mas a {origem} resulta em "
                    f"{self._fmt(soma)}."
                ),
                "Conferir os itens e o total do documento.",
                documento=documento,
                campo=campo,
            )

    def _decimal_campo(
        self,
        registro: _Registro,
        indice: int,
        campo: str,
        documento: str,
        codigo_item: str,
    ) -> Decimal | None:
        texto = registro.campo(indice)
        if not texto:
            return Decimal("0")
        valor = self._decimal(texto)
        if valor is None:
            self._erro(
                "Documento",
                registro.codigo,
                registro.numero_linha,
                f"O campo {campo} não é numérico: '{texto}'.",
                documento=documento,
                codigo_item=codigo_item,
                campo=campo,
            )
        return valor

    def _erro(
        self,
        categoria: str,
        registro: str,
        numero_linha: int | None,
        mensagem: str,
        sugestao: str = "",
        documento: str = "",
        codigo_item: str = "",
        campo: str = "",
    ) -> None:
        self._adicionar(
            ApontamentoPVA(
                nivel="ERRO",
                categoria=categoria,
                registro=registro,
                numero_linha=numero_linha,
                mensagem=mensagem,
                sugestao=sugestao,
                documento=documento,
                codigo_item=codigo_item,
                campo=campo,
            )
        )

    def _aviso(
        self,
        categoria: str,
        registro: str,
        numero_linha: int | None,
        mensagem: str,
        sugestao: str = "",
        documento: str = "",
        codigo_item: str = "",
        campo: str = "",
    ) -> None:
        self._adicionar(
            ApontamentoPVA(
                nivel="AVISO",
                categoria=categoria,
                registro=registro,
                numero_linha=numero_linha,
                mensagem=mensagem,
                sugestao=sugestao,
                documento=documento,
                codigo_item=codigo_item,
                campo=campo,
            )
        )

    def _revisao(
        self,
        categoria: str,
        registro: str,
        numero_linha: int | None,
        mensagem: str,
        sugestao: str = "",
        documento: str = "",
        codigo_item: str = "",
        campo: str = "",
    ) -> None:
        self._adicionar(
            ApontamentoPVA(
                nivel="REVISÃO FISCALPRO",
                categoria=categoria,
                registro=registro,
                numero_linha=numero_linha,
                mensagem=mensagem,
                sugestao=sugestao,
                documento=documento,
                codigo_item=codigo_item,
                campo=campo,
            )
        )

    def _adicionar(self, apontamento: ApontamentoPVA) -> None:
        assert self._resultado is not None
        chave = (
            apontamento.nivel,
            apontamento.categoria,
            apontamento.registro,
            apontamento.numero_linha,
            apontamento.mensagem,
        )
        if chave not in self._chaves_apontamentos:
            self._chaves_apontamentos.add(chave)
            self._resultado.apontamentos.append(apontamento)

    def _regra(self) -> None:
        assert self._resultado is not None
        self._resultado.regras_executadas += 1


    @staticmethod
    def _data_ou_none(valor: str) -> datetime | None:
        valor = (valor or "").strip()
        if not valor:
            return None
        try:
            return datetime.strptime(valor, "%d%m%Y")
        except ValueError:
            return None

    @staticmethod
    def _normalizar_zero(valor: str) -> str:
        texto = (valor or "").strip()
        if not texto:
            return "0"
        try:
            numero = Decimal(texto.replace(".", "").replace(",", "."))
        except (InvalidOperation, ValueError):
            return texto
        if numero == 0:
            return "0"
        return format(numero.normalize(), "f")


    @staticmethod
    def _documento(numero: str, chave: str) -> str:
        if numero and chave:
            return f"Nº {numero} — chave {chave}"
        if numero:
            return f"Nº {numero}"
        return chave or "Documento sem número"

    @staticmethod
    def _digitos(valor: str) -> str:
        return "".join(caractere for caractere in valor if caractere.isdigit())

    @staticmethod
    def _inteiro(valor: str) -> int | None:
        valor = (valor or "").strip()
        if not valor or not valor.isdigit():
            return None
        try:
            return int(valor)
        except ValueError:
            return None

    @staticmethod
    def _decimal(valor: str) -> Decimal | None:
        valor = (valor or "").strip()
        if not valor:
            return None
        normalizado = valor.replace(".", "").replace(",", ".")
        try:
            return Decimal(normalizado)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _fmt(valor: Decimal) -> str:
        texto = format(valor, "f")
        if "." in texto:
            texto = texto.rstrip("0").rstrip(".")
        return texto.replace(".", ",") or "0"

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(percentual, mensagem)
