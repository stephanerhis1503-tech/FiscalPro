"""Importador do relatório DigiSat 'Lista de produtos com tributos'."""

import re
from pathlib import Path
from datetime import date

from src.banco.criar_banco import criar_banco
from src.repositorios.tributacao_base_repository import TributacaoBaseRepository


class ImportadorDigisat:
    PADRAO_LINHA = re.compile(
        r"^\s*(\S+)\s+(.+?)\s+(\d{8})\s+([\d.]{7,9})\s+"
        r"(\d{2,3})\s+([\d.,]+)%\s+(\d{2})\s+([\d.,]+)%\s+"
        r"(\d{2})\s+([\d.,]+)%\s+(\d{4})\s+([^\s]+)\s+"
        r"([^\s]+)\s+([\d.,]+)%\s+([\d.,]+)%\s+([\d.,]+)%"
        r"(?:\s+(.*))?$"
    )

    def __init__(self, callback_progresso=None):
        self.callback_progresso = callback_progresso

    @staticmethod
    def _limpar_texto(texto):
        return " ".join(str(texto or "").split())

    @staticmethod
    def _percentual(valor):
        texto = str(valor or "0").replace("%", "").strip()
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return 0.0

    @staticmethod
    def _empresa_do_texto(texto):
        for linha in texto.splitlines():
            linha = " ".join(linha.split())
            if linha and not re.fullmatch(r"[\d./-]+", linha):
                if "Lista de produtos" not in linha and "Situação:" not in linha:
                    return linha[:160]
        return ""

    def _avisar(self, atual, total, mensagem):
        if self.callback_progresso:
            self.callback_progresso(atual, total, mensagem)

    def _ler_paginas_pdf(self, arquivo):
        try:
            import pdfplumber
        except ImportError as erro:
            raise RuntimeError(
                "A biblioteca pdfplumber não está instalada. "
                "No terminal, execute: pip install pdfplumber"
            ) from erro

        with pdfplumber.open(arquivo) as pdf:
            total = len(pdf.pages)
            for indice, pagina in enumerate(pdf.pages, start=1):
                texto = pagina.extract_text(x_tolerance=2, y_tolerance=3) or ""
                self._avisar(indice, total, f"Lendo página {indice} de {total}")
                yield indice, total, texto

    def extrair_registros(self, arquivo):
        arquivo = Path(arquivo)
        if not arquivo.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
        if arquivo.suffix.lower() != ".pdf":
            raise ValueError("Selecione o PDF 'Lista de produtos com tributos' do DigiSat.")

        registros = []
        empresa = ""
        ultimo = None

        for _, _, texto in self._ler_paginas_pdf(arquivo):
            if not empresa:
                empresa = self._empresa_do_texto(texto)

            for linha in texto.splitlines():
                normalizada = " ".join(linha.split())
                correspondencia = self.PADRAO_LINHA.match(normalizada)

                if correspondencia:
                    (
                        codigo, descricao, ncm, cest, cst_ipi, ipi,
                        cst_pis, pis, cst_cofins, cofins, cfop,
                        cst_icms_bruto, base_icms_ibs_cbs,
                        icms, ibs, cbs, classificacao
                    ) = correspondencia.groups()

                    cst_icms = cst_icms_bruto.split("/")[0]
                    icms_st = "SIM" if cst_icms in {"10", "30", "60", "70"} or cfop.endswith("405") else "NÃO"

                    ultimo = {
                        "empresa": empresa,
                        "codigo_produto": codigo,
                        "descricao_produto": self._limpar_texto(descricao),
                        "ncm": ncm,
                        "cest": re.sub(r"\D", "", cest),
                        "cfop": cfop,
                        "cst_icms": cst_icms,
                        "icms": self._percentual(icms),
                        "icms_st": icms_st,
                        "fcp": 0.0,
                        "cst_pis": cst_pis,
                        "aliquota_pis": self._percentual(pis),
                        "cst_cofins": cst_cofins,
                        "aliquota_cofins": self._percentual(cofins),
                        "cst_ipi": cst_ipi,
                        "ipi": self._percentual(ipi),
                        "ibs": self._percentual(ibs),
                        "cbs": self._percentual(cbs),
                        "classificacao": self._limpar_texto(classificacao),
                        "beneficio": "",
                        "fonte": "DIGISAT - Lista de produtos com tributos",
                        "confiabilidade": 90,
                        "ultima_validacao": date.today().isoformat(),
                        "observacoes": f"Base ICMS/IBS-CBS informada no relatório: {base_icms_ibs_cbs}",
                        "ativo": 1,
                    }
                    registros.append(ultimo)
                    continue

                # Complementos de descrição aparecem em linhas logo abaixo do produto.
                if ultimo and normalizada:
                    ignorar = (
                        "MEGA MOTOS", "Lista de produtos", "Situação:", "Código Descrição",
                        "Gerado em", "Desenvolvido por DigiSat", "Página "
                    )
                    if not any(normalizada.startswith(item) for item in ignorar):
                        if not re.search(r"\d{8}\s+[\d.]{7,9}\s+\d{2,3}\s+", normalizada):
                            ultimo["descricao_produto"] = self._limpar_texto(
                                ultimo["descricao_produto"] + " " + normalizada
                            )

        return registros

    def importar(self, arquivo):
        criar_banco()
        registros = self.extrair_registros(arquivo)
        resultado = {
            "arquivo": str(arquivo),
            "total_extraidos": len(registros),
            "inseridos": 0,
            "atualizados": 0,
            "erros": 0,
            "detalhes_erros": [],
        }

        total = len(registros)
        for indice, registro in enumerate(registros, start=1):
            self._avisar(indice, total, f"Gravando produto {indice} de {total}")
            try:
                retorno = TributacaoBaseRepository.salvar(**registro)
                if retorno["status"] == "INSERIDO":
                    resultado["inseridos"] += 1
                else:
                    resultado["atualizados"] += 1
            except Exception as erro:
                resultado["erros"] += 1
                resultado["detalhes_erros"].append({
                    "linha": indice,
                    "codigo": registro.get("codigo_produto", ""),
                    "erro": str(erro),
                })

        return resultado
