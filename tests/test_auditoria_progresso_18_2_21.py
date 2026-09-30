from src.services.auditoria_cadastros_excel_service import AuditoriaCadastrosExcelService


class _Celula:
    def __init__(self, value, number_format="General"):
        self.value = value
        self.number_format = number_format


class _PlanilhaDimensaoIncorreta:
    """Simula XLSX cujo metadata informa só 1 linha, mas há dados reais."""

    max_row = 1

    def __init__(self):
        self._valores = [
            ("A1", "PECA TESTE 1", "87141000", "0107600", 0.0165),
            ("A2", "PECA TESTE 2", "00000000", "", 0.0165),
        ]
        self._celulas = [
            tuple(_Celula(v, "0.00%" if i == 4 else "General") for i, v in enumerate(linha))
            for linha in self._valores
        ]

    def iter_rows(self, min_row=1, max_row=None, values_only=False):
        if min_row <= 1:
            cab = ("Código", "Descrição", "NCM", "CEST", "Alíquota PIS")
            if max_row == 1:
                yield cab if values_only else tuple(_Celula(v) for v in cab)
                return
        linhas = self._valores if values_only else self._celulas
        for linha in linhas:
            yield linha


def test_total_real_nao_depende_de_max_row():
    ws = _PlanilhaDimensaoIncorreta()
    cabecalhos = {"codigo": 0, "descricao": 1, "ncm": 2, "cest": 3, "aliq_pis": 4}

    indice = AuditoriaCadastrosExcelService._construir_indice_ncm_descricao(ws, cabecalhos)

    assert ws.max_row == 1
    assert indice.total_linhas == 2


def test_formato_percentual_nao_depende_de_max_row():
    ws = _PlanilhaDimensaoIncorreta()
    cabecalhos = {"codigo": 0, "descricao": 1, "ncm": 2, "cest": 3, "aliq_pis": 4}

    formatos = AuditoriaCadastrosExcelService._detectar_formatos_percentuais(ws, cabecalhos)

    assert formatos["aliq_pis"] is True
