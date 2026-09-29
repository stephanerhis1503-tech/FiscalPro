"""Janela da Ficha Tributária Inteligente — Sprint 13.7."""

from __future__ import annotations

import tkinter as tk
import threading
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.banco.conexao import Banco
from src.inteligencia.ficha_tributaria import FichaTributaria
from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.parecer.exportadores import ExportadorParecer
from src.parecer.historico import HistoricoParecerRepository
from src.parecer.motor_parecer import MotorParecer
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository
from src.services.atualizador_fontes_oficiais import AtualizadorFontesOficiais
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.indicador_seguranca_tributaria import IndicadorSegurancaTributaria
from src.services.ncm_descricao_service import NCMDescricaoService
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.ui.janela_calculo_icms_st import JanelaCalculoICMSSTMG
from src.ui.janela_xml_icms_st import JanelaXMLICMSST
from src.ui.layout_responsivo import dimensionar_janela


_UFS = ("", "TODAS", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")
_REGIMES = ("", "SIMPLES NACIONAL", "LUCRO PRESUMIDO", "LUCRO REAL", "MEI", "OUTRO")
_OPERACOES = ("", "ENTRADA", "SAÍDA", "DEVOLUÇÃO", "TRANSFERÊNCIA", "IMPORTAÇÃO", "EXPORTAÇÃO")
_FINALIDADES = ("", "REVENDA", "INDUSTRIALIZAÇÃO", "USO E CONSUMO", "ATIVO IMOBILIZADO", "SERVIÇO", "OUTRA")
_CONTRIBUINTES = ("TODOS", "CONTRIBUINTE", "NÃO CONTRIBUINTE")
_STATUS_REGRA = ("VIGENTE", "RASCUNHO", "ENCERRADA")
_TIPOS_NORMA = (
    "", "LEI", "LEI COMPLEMENTAR", "DECRETO", "CONVÊNIO ICMS", "PROTOCOLO ICMS",
    "AJUSTE SINIEF", "RESOLUÇÃO", "INSTRUÇÃO NORMATIVA", "PORTARIA", "ATO COTEPE",
    "SOLUÇÃO DE CONSULTA", "PARECER NORMATIVO", "REGULAMENTO", "OUTRA",
)
_ORGAOS_NORMA = (
    "", "RECEITA FEDERAL", "CONFAZ", "SEFAZ MG", "SEFAZ ESTADUAL", "UNIÃO",
    "ESTADO", "MUNICÍPIO", "COMITÊ GESTOR IBS", "OUTRO",
)
_STATUS_LEGAL = ("VIGENTE", "RASCUNHO", "ENCERRADA", "REVOGADA")


def _data_para_br(valor: Any) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return texto


def _numero_para_br(valor: Any) -> str:
    if valor in (None, ""):
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    texto = f"{numero:.6f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


class _FormularioBaseRegra(tk.Toplevel):
    """Base modal para cadastro versionado de regras tributárias."""

    def __init__(
        self,
        parent: tk.Misc,
        titulo: str,
        ncm: str,
        inicial: Optional[Dict[str, Any]],
        ao_salvar: Callable[[Dict[str, Any]], None],
        nova_regra: bool,
    ) -> None:
        super().__init__(parent)
        self.title(titulo)
        dimensionar_janela(self, 980, 740, 780, 560)
        self.transient(parent)
        self.grab_set()
        self.ncm = ncm
        self.inicial = dict(inicial or {})
        self.ao_salvar = ao_salvar
        self.nova_regra = nova_regra
        self.vars: Dict[str, tk.StringVar] = {}
        self.encerrar_var = tk.BooleanVar(value=True)
        self.texto_observacoes: Optional[tk.Text] = None

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 8))
        self.aba_contexto = ttk.Frame(self.notebook, padding=14)
        self.aba_tributos = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(self.aba_contexto, text="Contexto da operação")
        self.notebook.add(self.aba_tributos, text="Tributação e observações")

        self._montar_campos()

        rodape = ttk.Frame(self, padding=(12, 0, 12, 12))
        rodape.pack(fill=tk.X)
        if nova_regra:
            ttk.Checkbutton(
                rodape,
                text="Encerrar automaticamente a regra vigente anterior quando o contexto for igual",
                variable=self.encerrar_var,
            ).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(rodape, text="💾 Salvar", command=self._salvar).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(50, self._focar_primeiro)

    def _valor_inicial(self, chave: str, padrao: Any = "") -> str:
        aliases = {
            "cst_pis": "pis_cst",
            "cst_cofins": "cofins_cst",
        }
        valor = self.inicial.get(chave, self.inicial.get(aliases.get(chave, ""), padrao))
        if chave in {"vigencia_inicio", "vigencia_fim"}:
            return _data_para_br(valor)
        if chave in {
            "icms", "fcp", "aliquota_pis", "aliquota_cofins", "ipi",
            "aliquota_ibs", "aliquota_cbs", "reducao_ibs", "reducao_cbs",
        }:
            return _numero_para_br(valor)
        return str(valor if valor is not None else padrao)

    def _campo_entry(
        self,
        frame: ttk.Frame,
        linha: int,
        coluna: int,
        rotulo: str,
        chave: str,
        largura: int = 30,
        somente_leitura: bool = False,
        padrao: Any = "",
    ) -> ttk.Entry:
        ttk.Label(frame, text=rotulo, font=("Segoe UI", 9, "bold")).grid(
            row=linha, column=coluna * 2, sticky="w", padx=(0, 6), pady=5
        )
        var = tk.StringVar(value=self._valor_inicial(chave, padrao))
        self.vars[chave] = var
        entry = ttk.Entry(frame, textvariable=var, width=largura)
        if somente_leitura:
            entry.configure(state="readonly")
        entry.grid(row=linha, column=coluna * 2 + 1, sticky="ew", padx=(0, 14), pady=5)
        frame.columnconfigure(coluna * 2 + 1, weight=1)
        return entry

    def _campo_combo(
        self,
        frame: ttk.Frame,
        linha: int,
        coluna: int,
        rotulo: str,
        chave: str,
        valores: Sequence[str],
        largura: int = 28,
        padrao: Any = "",
        editavel: bool = False,
    ) -> ttk.Combobox:
        ttk.Label(frame, text=rotulo, font=("Segoe UI", 9, "bold")).grid(
            row=linha, column=coluna * 2, sticky="w", padx=(0, 6), pady=5
        )
        var = tk.StringVar(value=self._valor_inicial(chave, padrao))
        self.vars[chave] = var
        combo = ttk.Combobox(
            frame,
            textvariable=var,
            values=tuple(valores),
            state="normal" if editavel else "readonly",
            width=largura,
        )
        combo.grid(row=linha, column=coluna * 2 + 1, sticky="ew", padx=(0, 14), pady=5)
        frame.columnconfigure(coluna * 2 + 1, weight=1)
        return combo

    def _campo_observacoes(self, frame: ttk.Frame, linha: int) -> None:
        ttk.Label(frame, text="Observações", font=("Segoe UI", 9, "bold")).grid(
            row=linha, column=0, sticky="nw", padx=(0, 6), pady=5
        )
        self.texto_observacoes = tk.Text(frame, height=6, wrap=tk.WORD, font=("Segoe UI", 9))
        self.texto_observacoes.grid(row=linha, column=1, columnspan=3, sticky="nsew", padx=(0, 14), pady=5)
        self.texto_observacoes.insert("1.0", str(self.inicial.get("observacoes") or ""))
        frame.rowconfigure(linha, weight=1)

    def _dados(self) -> Dict[str, Any]:
        dados = {chave: var.get().strip() for chave, var in self.vars.items()}
        dados["ncm"] = self.ncm
        dados["_encerrar_anterior"] = bool(self.encerrar_var.get())
        if self.texto_observacoes is not None:
            dados["observacoes"] = self.texto_observacoes.get("1.0", tk.END).strip()
        return dados

    def _salvar(self) -> None:
        try:
            self.ao_salvar(self._dados())
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
            return
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível salvar a regra:\n{erro}", parent=self)
            return
        self.destroy()

    def _focar_primeiro(self) -> None:
        for descendente in self.aba_contexto.winfo_children():
            if isinstance(descendente, (ttk.Entry, ttk.Combobox)) and str(descendente.cget("state")) != "readonly":
                descendente.focus_set()
                break

    def _montar_campos(self) -> None:
        raise NotImplementedError


class _FormularioTributacaoAtual(_FormularioBaseRegra):
    def _montar_campos(self) -> None:
        hoje = date.today().strftime("%d/%m/%Y")
        self.vars["ncm"] = tk.StringVar(value=self.ncm)
        self._campo_entry(self.aba_contexto, 0, 0, "NCM", "ncm", somente_leitura=True, padrao=self.ncm)
        self._campo_combo(self.aba_contexto, 0, 1, "Empresa", "empresa", (), editavel=True, padrao="")
        self._campo_combo(self.aba_contexto, 1, 0, "UF de origem", "uf_origem", _UFS)
        self._campo_combo(self.aba_contexto, 1, 1, "UF de destino", "uf_destino", _UFS)
        self._campo_combo(self.aba_contexto, 2, 0, "Regime tributário", "regime", _REGIMES, editavel=True)
        self._campo_combo(self.aba_contexto, 2, 1, "Operação", "operacao", _OPERACOES, editavel=True)
        self._campo_combo(self.aba_contexto, 3, 0, "Finalidade", "finalidade", _FINALIDADES, editavel=True)
        self._campo_combo(self.aba_contexto, 3, 1, "Destinatário", "contribuinte", _CONTRIBUINTES, padrao="TODOS")
        self._campo_entry(self.aba_contexto, 4, 0, "Vigência inicial", "vigencia_inicio", padrao=hoje)
        self._campo_entry(self.aba_contexto, 4, 1, "Vigência final", "vigencia_fim")
        self._campo_combo(self.aba_contexto, 5, 0, "Status", "status", _STATUS_REGRA, padrao="VIGENTE")

        self._campo_entry(self.aba_tributos, 0, 0, "CFOP", "cfop")
        self._campo_entry(self.aba_tributos, 0, 1, "CEST", "cest")
        self._campo_entry(self.aba_tributos, 1, 0, "CST/CSOSN ICMS", "cst_icms")
        self._campo_entry(self.aba_tributos, 1, 1, "Alíquota ICMS (%)", "icms")
        self._campo_combo(self.aba_tributos, 2, 0, "ICMS-ST", "icms_st", ("", "SIM", "NÃO", "VERIFICAR"), editavel=True)
        self._campo_entry(self.aba_tributos, 2, 1, "MVA ST (%)", "mva_st")
        self._campo_entry(self.aba_tributos, 3, 0, "FCP (%)", "fcp")
        self._campo_entry(self.aba_tributos, 3, 1, "CST PIS", "cst_pis")
        self._campo_entry(self.aba_tributos, 4, 0, "Alíquota PIS (%)", "aliquota_pis")
        self._campo_entry(self.aba_tributos, 4, 1, "CST COFINS", "cst_cofins")
        self._campo_entry(self.aba_tributos, 5, 0, "Alíquota COFINS (%)", "aliquota_cofins")
        self._campo_entry(self.aba_tributos, 5, 1, "CST IPI", "cst_ipi")
        self._campo_entry(self.aba_tributos, 6, 0, "Alíquota IPI (%)", "ipi")
        self._campo_entry(self.aba_tributos, 6, 1, "Benefício/Regime especial", "beneficio")
        self._campo_entry(self.aba_tributos, 7, 0, "Fonte", "fonte")
        self._campo_entry(self.aba_tributos, 7, 1, "Confiabilidade (0 a 100)", "confiabilidade", padrao="50")
        self._campo_observacoes(self.aba_tributos, 8)


class _FormularioReformaTributaria(_FormularioBaseRegra):
    def _montar_campos(self) -> None:
        hoje = date.today().strftime("%d/%m/%Y")
        self._campo_entry(self.aba_contexto, 0, 0, "NCM", "ncm", somente_leitura=True, padrao=self.ncm)
        self._campo_combo(self.aba_contexto, 0, 1, "Empresa", "empresa", (), editavel=True)
        self._campo_combo(self.aba_contexto, 1, 0, "UF de origem", "uf_origem", _UFS)
        self._campo_combo(self.aba_contexto, 1, 1, "UF de destino", "uf_destino", _UFS)
        self._campo_combo(self.aba_contexto, 2, 0, "Regime tributário", "regime", _REGIMES, editavel=True)
        self._campo_combo(self.aba_contexto, 2, 1, "Operação", "operacao", _OPERACOES, editavel=True)
        self._campo_combo(self.aba_contexto, 3, 0, "Finalidade", "finalidade", _FINALIDADES, editavel=True)
        self._campo_combo(self.aba_contexto, 3, 1, "Destinatário", "contribuinte", _CONTRIBUINTES, padrao="TODOS")
        self._campo_entry(self.aba_contexto, 4, 0, "Vigência inicial", "vigencia_inicio", padrao=hoje)
        self._campo_entry(self.aba_contexto, 4, 1, "Vigência final", "vigencia_fim")
        self._campo_combo(self.aba_contexto, 5, 0, "Status", "status", _STATUS_REGRA, padrao="VIGENTE")

        self._campo_entry(self.aba_tributos, 0, 0, "cClassTrib", "cclasstrib")
        self._campo_entry(self.aba_tributos, 0, 1, "Código crédito presumido", "ccredpres")
        self._campo_entry(self.aba_tributos, 1, 0, "CST IBS", "cst_ibs")
        self._campo_entry(self.aba_tributos, 1, 1, "Alíquota IBS (%)", "aliquota_ibs")
        self._campo_entry(self.aba_tributos, 2, 0, "Redução IBS (%)", "reducao_ibs")
        self._campo_entry(self.aba_tributos, 2, 1, "CST CBS", "cst_cbs")
        self._campo_entry(self.aba_tributos, 3, 0, "Alíquota CBS (%)", "aliquota_cbs")
        self._campo_entry(self.aba_tributos, 3, 1, "Redução CBS (%)", "reducao_cbs")
        self._campo_combo(self.aba_tributos, 4, 0, "Diferimento", "diferimento", ("NÃO", "SIM", "PARCIAL", "VERIFICAR"), editavel=True, padrao="NÃO")
        self._campo_combo(self.aba_tributos, 4, 1, "Imposto Seletivo", "imposto_seletivo", ("", "NÃO", "SIM", "VERIFICAR"), editavel=True)
        self._campo_entry(self.aba_tributos, 5, 0, "Fonte", "fonte")
        self._campo_entry(self.aba_tributos, 5, 1, "Confiabilidade (0 a 100)", "confiabilidade", padrao="50")
        self._campo_observacoes(self.aba_tributos, 6)


class _FormularioBaseLegal(tk.Toplevel):
    """Cadastro versionado de normas e fontes oficiais vinculadas ao NCM."""

    def __init__(
        self,
        parent: tk.Misc,
        ncm: str,
        inicial: Optional[Dict[str, Any]],
        ao_salvar: Callable[[Dict[str, Any]], None],
        nova_norma: bool,
    ) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Base Legal")
        dimensionar_janela(self, 1040, 800, 800, 580)
        self.transient(parent)
        self.grab_set()
        self.ncm = ncm
        self.inicial = dict(inicial or {})
        self.ao_salvar = ao_salvar
        self.vars: Dict[str, tk.StringVar] = {}
        self.origem_oficial_var = tk.BooleanVar(
            value=bool(int(self.inicial.get("origem_oficial", 1) or 0))
        )
        self.gera_alerta_var = tk.BooleanVar(
            value=bool(int(self.inicial.get("gera_alerta", 1) or 0)) if not nova_norma else True
        )

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 8))
        self.aba_identificacao = ttk.Frame(self.notebook, padding=14)
        self.aba_conteudo = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(self.aba_identificacao, text="Identificação e vigência")
        self.notebook.add(self.aba_conteudo, text="Conteúdo e impacto")

        hoje = date.today().strftime("%d/%m/%Y")
        self._entry(self.aba_identificacao, 0, 0, "NCM", "ncm", self.ncm, readonly=True)
        self._combo(self.aba_identificacao, 0, 1, "Tipo da norma", "tipo_norma", _TIPOS_NORMA, editavel=True)
        self._entry(self.aba_identificacao, 1, 0, "Número/Identificação", "numero_norma")
        self._combo(self.aba_identificacao, 1, 1, "Órgão", "orgao", _ORGAOS_NORMA, editavel=True)
        self._entry(self.aba_identificacao, 2, 0, "Artigo/Anexo/Item", "artigo_item")
        self._entry(self.aba_identificacao, 2, 1, "Assunto", "assunto")
        self._entry(self.aba_identificacao, 3, 0, "Data de publicação", "data_publicacao")
        self._entry(self.aba_identificacao, 3, 1, "Início da vigência", "vigencia_inicio", hoje)
        self._entry(self.aba_identificacao, 4, 0, "Fim da vigência", "vigencia_fim")
        self._combo(self.aba_identificacao, 4, 1, "Status", "status", _STATUS_LEGAL, padrao="VIGENTE")
        self._entry(self.aba_identificacao, 5, 0, "Fonte/Responsável", "fonte")
        self._entry(self.aba_identificacao, 5, 1, "Confiabilidade (0 a 100)", "confiabilidade", "100")
        self._entry(self.aba_identificacao, 6, 0, "Link oficial", "url", coluna_span=3)

        opcoes = ttk.Frame(self.aba_identificacao)
        opcoes.grid(row=7, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Checkbutton(
            opcoes,
            text="Fonte oficial verificada",
            variable=self.origem_oficial_var,
        ).pack(side=tk.LEFT, padx=(0, 18))
        ttk.Checkbutton(
            opcoes,
            text="Criar/atualizar alerta legislativo para este NCM",
            variable=self.gera_alerta_var,
        ).pack(side=tk.LEFT)

        self.texto_descricao = self._texto_longo(self.aba_conteudo, 0, "Descrição/Ementa", 7)
        self.texto_trecho = self._texto_longo(self.aba_conteudo, 2, "Trecho relevante", 8)
        self.texto_impacto = self._texto_longo(self.aba_conteudo, 4, "Impacto tributário / O que mudou", 8)
        self.texto_descricao.insert("1.0", str(self.inicial.get("descricao") or ""))
        self.texto_trecho.insert("1.0", str(self.inicial.get("trecho_relevante") or ""))
        self.texto_impacto.insert("1.0", str(self.inicial.get("impacto_tributario") or ""))

        rodape = ttk.Frame(self, padding=(12, 0, 12, 12))
        rodape.pack(fill=tk.X)
        ttk.Label(
            rodape,
            text="A norma anterior é vinculada automaticamente pela data para permitir a comparação.",
        ).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(rodape, text="💾 Salvar", command=self._salvar).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(60, self._focar)

    def _valor(self, chave: str, padrao: Any = "") -> str:
        valor = self.inicial.get(chave, padrao)
        if chave in {"data_publicacao", "vigencia_inicio", "vigencia_fim"}:
            return _data_para_br(valor)
        return str(valor if valor is not None else padrao)

    def _entry(
        self,
        frame: ttk.Frame,
        linha: int,
        coluna: int,
        rotulo: str,
        chave: str,
        padrao: Any = "",
        readonly: bool = False,
        coluna_span: int = 1,
    ) -> ttk.Entry:
        ttk.Label(frame, text=rotulo, font=("Segoe UI", 9, "bold")).grid(
            row=linha, column=coluna * 2, sticky="w", padx=(0, 6), pady=5
        )
        var = tk.StringVar(value=self._valor(chave, padrao))
        self.vars[chave] = var
        entry = ttk.Entry(frame, textvariable=var)
        if readonly:
            entry.configure(state="readonly")
        entry.grid(
            row=linha,
            column=coluna * 2 + 1,
            columnspan=coluna_span,
            sticky="ew",
            padx=(0, 14),
            pady=5,
        )
        frame.columnconfigure(coluna * 2 + 1, weight=1)
        return entry

    def _combo(
        self,
        frame: ttk.Frame,
        linha: int,
        coluna: int,
        rotulo: str,
        chave: str,
        valores: Sequence[str],
        padrao: Any = "",
        editavel: bool = False,
    ) -> ttk.Combobox:
        ttk.Label(frame, text=rotulo, font=("Segoe UI", 9, "bold")).grid(
            row=linha, column=coluna * 2, sticky="w", padx=(0, 6), pady=5
        )
        var = tk.StringVar(value=self._valor(chave, padrao))
        self.vars[chave] = var
        combo = ttk.Combobox(
            frame,
            textvariable=var,
            values=tuple(valores),
            state="normal" if editavel else "readonly",
        )
        combo.grid(row=linha, column=coluna * 2 + 1, sticky="ew", padx=(0, 14), pady=5)
        frame.columnconfigure(coluna * 2 + 1, weight=1)
        return combo

    @staticmethod
    def _texto_longo(frame: ttk.Frame, linha: int, rotulo: str, altura: int) -> tk.Text:
        ttk.Label(frame, text=rotulo, font=("Segoe UI", 9, "bold")).grid(
            row=linha, column=0, sticky="w", pady=(4, 3)
        )
        texto = tk.Text(frame, height=altura, wrap=tk.WORD, font=("Segoe UI", 9))
        texto.grid(row=linha + 1, column=0, sticky="nsew", pady=(0, 8))
        frame.rowconfigure(linha + 1, weight=1)
        frame.columnconfigure(0, weight=1)
        return texto

    def _dados(self) -> Dict[str, Any]:
        dados = {chave: var.get().strip() for chave, var in self.vars.items()}
        dados.update(
            {
                "ncm": self.ncm,
                "descricao": self.texto_descricao.get("1.0", tk.END).strip(),
                "trecho_relevante": self.texto_trecho.get("1.0", tk.END).strip(),
                "impacto_tributario": self.texto_impacto.get("1.0", tk.END).strip(),
                "origem_oficial": bool(self.origem_oficial_var.get()),
                "gera_alerta": bool(self.gera_alerta_var.get()),
            }
        )
        return dados

    def _salvar(self) -> None:
        try:
            self.ao_salvar(self._dados())
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
            return
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível salvar a base legal:\n{erro}", parent=self)
            return
        self.destroy()

    def _focar(self) -> None:
        for item in self.aba_identificacao.winfo_children():
            if isinstance(item, (ttk.Entry, ttk.Combobox)) and str(item.cget("state")) != "readonly":
                item.focus_set()
                break


class _JanelaComparacaoLegal(tk.Toplevel):
    """Exibe lado a lado a norma anterior e a norma atual."""

    def __init__(self, parent: tk.Misc, comparacao: Dict[str, Any]) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Comparação legislativa")
        dimensionar_janela(self, 1180, 760, 860, 540)
        self.transient(parent)

        anterior = comparacao.get("anterior") or {}
        atual = comparacao.get("atual") or {}
        cabecalho = ttk.Frame(self, padding=12)
        cabecalho.pack(fill=tk.X)
        ttk.Label(cabecalho, text="Comparação da Base Legal", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            cabecalho,
            text=(
                f"Anterior: {anterior.get('tipo_norma') or 'não encontrada'} {anterior.get('numero_norma') or ''}  |  "
                f"Atual: {atual.get('tipo_norma') or ''} {atual.get('numero_norma') or ''}  |  "
                f"Campos alterados: {comparacao.get('total_alteracoes', 0)}"
            ),
        ).pack(anchor="w", pady=(4, 0))

        frame = ttk.Frame(self, padding=(12, 0, 12, 8))
        frame.pack(fill=tk.BOTH, expand=True)
        colunas = ("campo", "anterior", "atual", "situacao")
        tree = ttk.Treeview(frame, columns=colunas, show="headings")
        for nome, titulo, largura in (
            ("campo", "Campo", 190),
            ("anterior", "Valor anterior", 380),
            ("atual", "Valor atual", 380),
            ("situacao", "Situação", 100),
        ):
            tree.heading(nome, text=titulo)
            tree.column(nome, width=largura, anchor="w", stretch=False)
        barra_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        barra_x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        for item in comparacao.get("alteracoes", []):
            tree.insert(
                "",
                tk.END,
                values=(
                    item.get("rotulo", ""),
                    item.get("anterior", ""),
                    item.get("atual", ""),
                    "ALTERADO" if item.get("alterado") else "IGUAL",
                ),
            )

        rodape = ttk.Frame(self, padding=(12, 0, 12, 12))
        rodape.pack(fill=tk.X)
        ttk.Label(
            rodape,
            text="A comparação serve para conferência. A validade jurídica depende da fonte oficial cadastrada.",
        ).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())


class _JanelaFichaTributariaAvancada(tk.Toplevel):
    """Prontuário completo do NCM.

    A assinatura continua aceitando ``ficha`` para manter compatibilidade com
    a janela de consulta tributária das versões anteriores.
    """

    def __init__(
        self,
        master=None,
        ficha: Optional[FichaTributaria] = None,
        contexto: Optional[Dict[str, Any]] = None,
        ncm: str = "",
    ):
        super().__init__(master)
        self.ficha_inicial = ficha
        self.contexto = contexto or {}
        self.dados_ficha: Dict[str, Any] = {}
        self.parecer = None
        self.consulta_oficial: Dict[str, Any] = {}
        self.ncm_atual = ""

        self.title("FiscalPro — Ficha Tributária Inteligente")
        dimensionar_janela(self, 1320, 860, 920, 600)

        self.ncm_var = tk.StringVar(value=ncm or (ficha.ncm if ficha else ""))
        self.empresa_var = tk.StringVar(value="Todas as empresas")
        self.status_var = tk.StringVar(value="Informe um NCM para abrir o prontuário tributário.")
        self.titulo_var = tk.StringVar(value="Ficha Tributária Inteligente")
        self.descricao_var = tk.StringVar(value="Consulta centralizada de tributação, legislação e histórico.")
        self.resumo_var = tk.StringVar(value="Nenhum NCM carregado.")
        self.alerta_var = tk.StringVar(value="")
        self.parecer_contexto_vars: Dict[str, tk.StringVar] = {
            "empresa": tk.StringVar(value="Todas as empresas"),
            "regime": tk.StringVar(value=""),
            "operacao": tk.StringVar(value=""),
            "finalidade": tk.StringVar(value=""),
            "uf_origem": tk.StringVar(value="MG"),
            "uf_destino": tk.StringVar(value="MG"),
            "contribuinte": tk.StringVar(value="TODOS"),
            "data_operacao": tk.StringVar(value=date.today().strftime("%d/%m/%Y")),
        }
        self.parecer_confianca_var = tk.StringVar(value="Segurança geral: parecer ainda não gerado")
        self.parecer_regra_var = tk.StringVar(value="Regra aplicada: nenhuma")

        self._criar_interface()
        self.bind("<Escape>", lambda _evento: self.destroy())
        self.ncm_entry.bind("<Return>", lambda _evento: self.buscar())

        if self.ncm_var.get().strip():
            self.after(100, self.buscar)

    # ------------------------------------------------------------------
    # Construção visual
    # ------------------------------------------------------------------
    def _criar_interface(self) -> None:
        topo = ttk.Frame(self, padding=(12, 10))
        topo.pack(fill=tk.X)

        ttk.Label(topo, text="NCM:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.ncm_entry = ttk.Entry(topo, textvariable=self.ncm_var, width=18, font=("Segoe UI", 11))
        self.ncm_entry.grid(row=0, column=1, padx=(6, 12), sticky="w")

        ttk.Label(topo, text="Empresa:", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, sticky="w")
        self.combo_empresa = ttk.Combobox(
            topo,
            textvariable=self.empresa_var,
            state="readonly",
            width=42,
            values=("Todas as empresas",),
        )
        self.combo_empresa.grid(row=0, column=3, padx=(6, 12), sticky="ew")
        self.combo_empresa.bind("<<ComboboxSelected>>", lambda _evento: self.buscar(manter_empresa=True))

        ttk.Button(topo, text="🔎 Abrir ficha", command=self.buscar).grid(row=0, column=4, padx=4)
        self.botao_favorito = ttk.Button(topo, text="☆ Adicionar aos favoritos", command=self.alternar_favorito)
        self.botao_favorito.grid(row=0, column=5, padx=4)
        ttk.Button(topo, text="↻ Atualizar", command=lambda: self.buscar(manter_empresa=True)).grid(row=0, column=6, padx=4)
        ttk.Button(topo, text="🧮 Simular operação", command=self.abrir_simulador).grid(row=0, column=7, padx=4)
        topo.columnconfigure(3, weight=1)

        cabecalho = ttk.LabelFrame(self, text="Prontuário tributário", padding=10)
        cabecalho.pack(fill=tk.X, padx=12, pady=(0, 8))
        ttk.Label(cabecalho, textvariable=self.titulo_var, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(cabecalho, textvariable=self.descricao_var, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))
        ttk.Label(cabecalho, textvariable=self.resumo_var).pack(anchor="w", pady=(4, 0))
        self.lbl_alerta = ttk.Label(cabecalho, textvariable=self.alerta_var, font=("Segoe UI", 10, "bold"))
        self.lbl_alerta.pack(anchor="w", pady=(5, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        self.tree_dados = self._criar_tree_aba(
            "📄 Dados Gerais",
            (("campo", "Campo", 260), ("valor", "Valor", 760)),
        )
        self.tree_tributacao = self._criar_tree_aba_com_acoes(
            "💰 Tributação Atual",
            (
                ("origem", "Origem", 160),
                ("status", "Status", 90),
                ("empresa", "Empresa", 220),
                ("uf_origem", "UF Orig.", 75),
                ("uf_destino", "UF Dest.", 75),
                ("regime", "Regime", 150),
                ("operacao", "Operação", 120),
                ("finalidade", "Finalidade", 145),
                ("contribuinte", "Destinatário", 110),
                ("cfop", "CFOP", 70),
                ("cest", "CEST", 90),
                ("cst_icms", "CST ICMS", 85),
                ("icms", "ICMS %", 75),
                ("icms_st", "ICMS-ST", 80),
                ("mva_st", "MVA ST %", 85),
                ("fcp", "FCP %", 70),
                ("cst_pis", "CST PIS", 75),
                ("pis", "PIS %", 70),
                ("cst_cofins", "CST COFINS", 95),
                ("cofins", "COFINS %", 90),
                ("cst_ipi", "CST IPI", 75),
                ("ipi", "IPI %", 70),
                ("vigencia", "Vigência", 185),
                ("fonte", "Fonte", 190),
                ("manual", "Manual", 70),
                ("confiabilidade", "Confiança", 85),
                ("produto", "Produto vinculado", 280),
            ),
            (
                ("➕ Nova regra", self.nova_tributacao),
                ("✏️ Editar", self.editar_tributacao),
                ("📋 Duplicar", self.duplicar_tributacao),
                ("⏹ Encerrar vigência", self.encerrar_tributacao),
            ),
            "Cadastre regras por empresa, UF, regime, operação e vigência. Duplo clique para editar.",
        )
        self.tree_tributacao.bind("<Double-1>", lambda _evento: self.editar_tributacao())
        self.tree_reforma = self._criar_tree_aba_com_acoes(
            "🏛 Reforma Tributária",
            (
                ("status", "Status", 90),
                ("empresa", "Empresa", 210),
                ("uf_origem", "UF Orig.", 75),
                ("uf_destino", "UF Dest.", 75),
                ("regime", "Regime", 150),
                ("operacao", "Operação", 120),
                ("finalidade", "Finalidade", 145),
                ("contribuinte", "Destinatário", 110),
                ("classificacao", "cClassTrib", 135),
                ("cst_ibs", "CST IBS", 80),
                ("ibs", "IBS %", 75),
                ("reducao_ibs", "Red. IBS %", 90),
                ("cst_cbs", "CST CBS", 80),
                ("cbs", "CBS %", 75),
                ("reducao_cbs", "Red. CBS %", 90),
                ("credito", "Crédito presumido", 150),
                ("diferimento", "Diferimento", 95),
                ("is", "Imposto Seletivo", 150),
                ("vigencia", "Vigência", 185),
                ("fonte", "Fonte", 190),
                ("confiabilidade", "Confiança", 85),
            ),
            (
                ("➕ Nova regra", self.nova_reforma),
                ("✏️ Editar", self.editar_reforma),
                ("📋 Duplicar", self.duplicar_reforma),
                ("⏹ Encerrar vigência", self.encerrar_reforma),
            ),
            "Versione IBS/CBS por contexto operacional sem apagar regras antigas.",
        )
        self.tree_reforma.bind("<Double-1>", lambda _evento: self.editar_reforma())
        self.tree_legal = self._criar_tree_aba_com_acoes(
            "📚 Base Legal",
            (
                ("status", "Status", 90),
                ("tipo", "Tipo", 110),
                ("numero", "Número", 130),
                ("orgao", "Órgão", 150),
                ("artigo", "Artigo/Item", 120),
                ("assunto", "Assunto", 180),
                ("descricao", "Descrição/Ementa", 320),
                ("publicacao", "Publicação", 100),
                ("vigencia", "Vigência", 190),
                ("impacto", "Impacto tributário", 320),
                ("fonte", "Fonte", 170),
                ("confiabilidade", "Confiança", 85),
                ("url", "Link oficial", 330),
            ),
            (
                ("➕ Nova norma", self.nova_base_legal),
                ("✏️ Editar", self.editar_base_legal),
                ("📋 Duplicar", self.duplicar_base_legal),
                ("⏹ Encerrar/Revogar", self.encerrar_base_legal),
                ("🔀 Comparar", self.comparar_base_legal),
                ("🌐 Abrir fonte", self.abrir_fonte_legal),
            ),
            "Cadastre a fonte oficial, vigência e impacto. A comparação usa automaticamente a norma anterior.",
        )
        self.tree_legal.bind("<Double-1>", lambda _evento: self.editar_base_legal())
        self.texto_parecer = self._criar_aba_parecer()
        self.tree_historico = self._criar_tree_aba(
            "📊 Histórico",
            (
                ("data", "Data", 150),
                ("evento", "Evento", 170),
                ("campo", "Campo", 180),
                ("anterior", "Valor anterior", 220),
                ("novo", "Valor novo", 220),
                ("origem", "Origem", 150),
                ("motivo", "Motivo/Contexto", 320),
            ),
        )
        self.tree_exemplos = self._criar_tree_aba(
            "🧾 Exemplos de Notas",
            (
                ("tipo", "Documento", 100),
                ("numero", "Número/Série", 130),
                ("operacao", "Operação", 150),
                ("cfop", "CFOP", 70),
                ("cst", "CST", 70),
                ("descricao", "Descrição", 320),
                ("chave", "Chave", 330),
                ("origem", "Arquivo de origem", 260),
            ),
        )
        self.tree_alertas = self._criar_tree_aba_com_acoes(
            "📈 Alterações na Legislação",
            (
                ("status", "Situação", 100),
                ("data", "Alteração", 100),
                ("vigencia", "Vigência", 100),
                ("titulo", "Alteração", 270),
                ("resumo", "O que mudou", 430),
                ("comparacao", "Campos alterados", 280),
                ("norma", "Norma", 180),
                ("url", "Fonte oficial", 320),
            ),
            (
                ("✓ Marcar lido", lambda: self._definir_alerta_selecionado(True)),
                ("↩ Marcar não lido", lambda: self._definir_alerta_selecionado(False)),
                ("🔀 Comparar", self.comparar_alerta_selecionado),
                ("🌐 Abrir fonte", self.abrir_fonte_alerta),
            ),
            "Alertas são criados automaticamente ao salvar uma base legal vigente com a opção marcada.",
        )
        self.tree_favoritos = self._criar_tree_aba(
            "⭐ Favoritos",
            (("ncm", "NCM", 120), ("descricao", "Descrição", 660), ("data", "Atualizado em", 180)),
        )
        self.tree_favoritos.bind("<Double-1>", self._abrir_favorito_selecionado)
        self.tree_alertas.bind("<Double-1>", self._marcar_alerta_selecionado)

        rodape = ttk.Frame(self, padding=(12, 2, 12, 10))
        rodape.pack(fill=tk.X)
        ttk.Label(rodape, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Button(rodape, text="💾 Salvar parecer", command=self.salvar_parecer).pack(side=tk.RIGHT, padx=4)
        ttk.Button(rodape, text="📊 Exportar Excel", command=self.gerar_excel).pack(side=tk.RIGHT, padx=4)
        ttk.Button(rodape, text="📄 Gerar PDF", command=self.gerar_pdf).pack(side=tk.RIGHT, padx=4)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT, padx=4)

    def _criar_tree_aba(
        self,
        titulo: str,
        colunas: Sequence[Tuple[str, str, int]],
    ) -> ttk.Treeview:
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text=titulo)

        nomes = tuple(coluna[0] for coluna in colunas)
        tree = ttk.Treeview(frame, columns=nomes, show="headings", selectmode="browse")
        barra_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        barra_x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)

        for nome, cabecalho, largura in colunas:
            tree.heading(nome, text=cabecalho)
            tree.column(nome, width=largura, minwidth=60, anchor="w", stretch=False)

        tree.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _criar_tree_aba_com_acoes(
        self,
        titulo: str,
        colunas: Sequence[Tuple[str, str, int]],
        acoes: Sequence[Tuple[str, Callable[[], None]]],
        orientacao: str = "",
    ) -> ttk.Treeview:
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text=titulo)

        barra_acoes = ttk.Frame(frame)
        barra_acoes.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        for texto, comando in acoes:
            ttk.Button(barra_acoes, text=texto, command=comando).pack(side=tk.LEFT, padx=(0, 5))
        if orientacao:
            ttk.Label(barra_acoes, text=orientacao).pack(side=tk.LEFT, padx=(10, 0))

        nomes = tuple(coluna[0] for coluna in colunas)
        tree = ttk.Treeview(frame, columns=nomes, show="headings", selectmode="browse")
        barra_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        barra_x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)

        for nome, cabecalho, largura in colunas:
            tree.heading(nome, text=cabecalho)
            tree.column(nome, width=largura, minwidth=60, anchor="w", stretch=False)

        tree.grid(row=1, column=0, sticky="nsew")
        barra_y.grid(row=1, column=1, sticky="ns")
        barra_x.grid(row=2, column=0, sticky="ew")
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _criar_aba_texto(self, titulo: str) -> tk.Text:
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text=titulo)
        texto = tk.Text(frame, wrap=tk.WORD, font=("Segoe UI", 10), padx=10, pady=10)
        barra = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=texto.yview)
        texto.configure(yscrollcommand=barra.set)
        texto.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return texto

    def _criar_aba_parecer(self) -> tk.Text:
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="🔍 Parecer Inteligente")

        contexto = ttk.LabelFrame(frame, text="Contexto da operação", padding=8)
        contexto.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))

        campos = (
            ("Empresa", "empresa", (), True),
            ("Regime", "regime", _REGIMES, True),
            ("Operação", "operacao", _OPERACOES, True),
            ("Finalidade", "finalidade", _FINALIDADES, True),
            ("UF origem", "uf_origem", _UFS, False),
            ("UF destino", "uf_destino", _UFS, False),
            ("Destinatário", "contribuinte", _CONTRIBUINTES, False),
        )
        self.parecer_contexto_combos: Dict[str, ttk.Combobox] = {}
        for indice, (rotulo, chave, valores, editavel) in enumerate(campos):
            linha = indice // 4
            coluna = (indice % 4) * 2
            ttk.Label(contexto, text=rotulo, font=("Segoe UI", 9, "bold")).grid(
                row=linha, column=coluna, sticky="w", padx=(0, 5), pady=4
            )
            combo = ttk.Combobox(
                contexto, textvariable=self.parecer_contexto_vars[chave], values=valores,
                state="normal" if editavel else "readonly", width=22,
            )
            combo.grid(row=linha, column=coluna + 1, sticky="ew", padx=(0, 10), pady=4)
            self.parecer_contexto_combos[chave] = combo
            contexto.columnconfigure(coluna + 1, weight=1)

        ttk.Label(contexto, text="Data da operação", font=("Segoe UI", 9, "bold")).grid(
            row=2, column=0, sticky="w", padx=(0, 5), pady=4
        )
        ttk.Entry(contexto, textvariable=self.parecer_contexto_vars["data_operacao"], width=16).grid(
            row=2, column=1, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Button(
            contexto, text="🧠 Gerar/Atualizar parecer",
            command=lambda: self._gerar_parecer_local(silencioso=False),
        ).grid(row=2, column=2, columnspan=2, sticky="w", padx=(0, 8), pady=4)
        ttk.Button(contexto, text="📋 Copiar parecer", command=self.copiar_parecer).grid(
            row=2, column=4, columnspan=2, sticky="w", padx=(0, 8), pady=4
        )

        indicadores = ttk.Frame(frame)
        indicadores.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Label(indicadores, textvariable=self.parecer_confianca_var, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Label(indicadores, textvariable=self.parecer_regra_var).pack(side=tk.LEFT, padx=(18, 0))

        texto = tk.Text(frame, wrap=tk.WORD, font=("Consolas", 9), padx=10, pady=10, state=tk.DISABLED)
        barra = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=texto.yview)
        texto.configure(yscrollcommand=barra.set)
        texto.grid(row=2, column=0, sticky="nsew")
        barra.grid(row=2, column=1, sticky="ns")
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)
        return texto

    def abrir_simulador(self) -> None:
        try:
            from src.ui.janela_simulador_tributario import JanelaSimuladorTributario

            contexto = {chave: variavel.get() for chave, variavel in self.parecer_contexto_vars.items()}
            JanelaSimuladorTributario(self, ncm=self.ncm_var.get(), contexto=contexto)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível abrir o Simulador Tributário:\n{erro}", parent=self)

    def copiar_parecer(self) -> None:
        if self.parecer is None:
            messagebox.showwarning("FiscalPro", "Gere um parecer antes de copiar.", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(self.parecer.para_texto())
        self.status_var.set("Parecer copiado para a área de transferência.")

    # ------------------------------------------------------------------
    # Consulta e preenchimento
    # ------------------------------------------------------------------
    def buscar(self, manter_empresa: bool = False) -> None:
        try:
            ncm = FichaTributariaRepository.normalizar_ncm(self.ncm_var.get())
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
            self.ncm_entry.focus_set()
            return

        empresa_selecionada = self.empresa_var.get().strip()
        empresa = "" if empresa_selecionada in {"", "Todas as empresas"} else empresa_selecionada
        self.status_var.set(f"Carregando a ficha do NCM {ncm}...")
        self.update_idletasks()

        try:
            ncm_anterior = self.ncm_atual
            self.dados_ficha = FichaTributariaRepository.carregar_ficha(ncm, empresa=empresa)
            self.ncm_atual = ncm

            empresas = ["Todas as empresas", *self.dados_ficha.get("empresas", [])]
            self.combo_empresa.configure(values=empresas)
            if not manter_empresa or empresa_selecionada not in empresas:
                self.empresa_var.set("Todas as empresas")
                if empresa:
                    # Recarrega sem filtro quando a empresa não existe mais na lista.
                    self.dados_ficha = FichaTributariaRepository.carregar_ficha(ncm)

            self._atualizar_cabecalho()
            self._preencher_dados_gerais()
            self._preencher_tributacao()
            self._preencher_reforma()
            self._preencher_base_legal()
            self._preencher_historico()
            self._preencher_exemplos()
            self._preencher_alertas()
            self._preencher_favoritos()
            self._preencher_contexto_parecer(reiniciar=ncm_anterior != ncm)
            self._gerar_parecer_local()
            self._atualizar_botao_favorito()

            encontrado = self.dados_ficha["dados_gerais"].get("encontrado", False)
            if encontrado:
                self.status_var.set(f"Ficha do NCM {ncm} carregada com sucesso.")
            else:
                self.status_var.set(f"NCM {ncm} sem cadastro tributário. A estrutura da ficha foi aberta para complementação.")
        except Exception as erro:
            self.status_var.set("Não foi possível carregar a ficha tributária.")
            messagebox.showerror("FiscalPro", f"Erro ao abrir a Ficha Tributária:\n{erro}", parent=self)

    def _atualizar_cabecalho(self) -> None:
        dados = self.dados_ficha.get("dados_gerais", {})
        ncm = dados.get("ncm", self.ncm_atual)
        self.titulo_var.set(f"NCM {ncm}")
        self.descricao_var.set(str(dados.get("descricao") or "Descrição ainda não cadastrada"))
        self.resumo_var.set(
            " | ".join(
                [
                    f"Status: {dados.get('status') or '-'}",
                    f"Produtos vinculados: {dados.get('total_produtos', 0)}",
                    f"Empresas: {dados.get('total_empresas', 0)}",
                    f"Última validação: {self._texto(dados.get('ultima_validacao'))}",
                    f"Consulta: {dados.get('consultado_em', '-')}",
                ]
            )
        )
        alertas_pendentes = [item for item in self.dados_ficha.get("alertas", []) if not int(item.get("lido") or 0)]
        if alertas_pendentes:
            mais_recente = alertas_pendentes[0]
            data = mais_recente.get("vigencia_inicio") or mais_recente.get("data_alteracao") or "data não informada"
            self.alerta_var.set(
                f"⚠ Este NCM possui {len(alertas_pendentes)} alteração(ões) legislativa(s) pendente(s). "
                f"Mais recente: {mais_recente.get('titulo', 'Alteração')} — vigência {data}."
            )
        else:
            self.alerta_var.set("✓ Nenhuma alteração legislativa pendente registrada para este NCM.")

    def _preencher_dados_gerais(self) -> None:
        self._limpar_tree(self.tree_dados)
        dados = self.dados_ficha.get("dados_gerais", {})
        campos = (
            ("NCM", dados.get("ncm")),
            ("Descrição oficial/predominante", dados.get("descricao")),
            ("CEST", dados.get("cest") or "Não informado"),
            ("EX TIPI", dados.get("ex_tipi") or "Não informado"),
            ("Status do cadastro", dados.get("status")),
            ("Início da vigência", dados.get("data_inicio") or "Não informado"),
            ("Fim da vigência", dados.get("data_fim") or "Vigente/Não informado"),
            ("Ato legal", dados.get("ato_legal") or "Não informado"),
            ("Número/Ano do ato", self._juntar(dados.get("numero_ato"), dados.get("ano_ato"))),
            ("Produtos cadastrados", dados.get("total_produtos", 0)),
            ("Empresas com produtos", dados.get("total_empresas", 0)),
            ("CESTs encontrados na base operacional", dados.get("total_cest", 0)),
            ("Primeira validação", dados.get("primeira_validacao") or "Não informada"),
            ("Última validação", dados.get("ultima_validacao") or "Não informada"),
            ("Última atualização", dados.get("atualizado_em") or "Não informada"),
            ("Favorito", "Sim" if self.dados_ficha.get("favorito") else "Não"),
        )
        for campo, valor in campos:
            self.tree_dados.insert("", tk.END, values=(campo, self._texto(valor)))

    def _preencher_tributacao(self) -> None:
        self._limpar_tree(self.tree_tributacao)
        itens = self.dados_ficha.get("tributacoes", [])
        for indice, item in enumerate(itens):
            produto = self._juntar(item.get("codigo_produto"), item.get("descricao_produto"), separador=" — ")
            vigencia = self._periodo(item.get("vigencia_inicio"), item.get("vigencia_fim"))
            tipo = item.get("tipo_origem") or "tributacao_base"
            registro_id = item.get("id")
            iid = f"{tipo}_{registro_id}" if registro_id is not None else f"tributacao_{indice}"
            self.tree_tributacao.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    item.get("origem", ""),
                    item.get("status", ""),
                    item.get("empresa") or "Todas",
                    item.get("uf_origem", ""),
                    item.get("uf_destino") or item.get("uf", ""),
                    item.get("regime", ""),
                    item.get("operacao", ""),
                    item.get("finalidade", ""),
                    item.get("contribuinte", ""),
                    item.get("cfop", ""),
                    item.get("cest", ""),
                    item.get("cst_icms", ""),
                    self._percentual(item.get("icms")),
                    item.get("icms_st", ""),
                    self._percentual(item.get("mva_st")),
                    self._percentual(item.get("fcp")),
                    item.get("cst_pis", ""),
                    self._percentual(item.get("aliquota_pis")),
                    item.get("cst_cofins", ""),
                    self._percentual(item.get("aliquota_cofins")),
                    item.get("cst_ipi", ""),
                    self._percentual(item.get("ipi")),
                    vigencia,
                    item.get("fonte", ""),
                    "SIM" if int(item.get("revisao_manual") or 0) else "",
                    f"{int(item.get('confiabilidade') or 0)}%",
                    produto,
                ),
            )
        if not itens:
            total_colunas = len(self.tree_tributacao["columns"])
            self.tree_tributacao.insert("", tk.END, values=("Sem tributação cadastrada",) + ("",) * (total_colunas - 1))

    def _preencher_reforma(self) -> None:
        self._limpar_tree(self.tree_reforma)
        itens = self.dados_ficha.get("reforma", [])
        for indice, item in enumerate(itens):
            tipo = item.get("tipo_origem") or "tributacao_reforma"
            registro_id = item.get("id")
            iid = f"{tipo}_{registro_id}" if registro_id is not None else f"reforma_{indice}"
            self.tree_reforma.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    item.get("status", ""),
                    item.get("empresa") or "Todas",
                    item.get("uf_origem", ""),
                    item.get("uf_destino", ""),
                    item.get("regime", ""),
                    item.get("operacao", ""),
                    item.get("finalidade", ""),
                    item.get("contribuinte", ""),
                    item.get("cclasstrib") or item.get("classificacao") or "",
                    item.get("cst_ibs", ""),
                    self._percentual(item.get("aliquota_ibs")),
                    self._percentual(item.get("reducao_ibs")),
                    item.get("cst_cbs", ""),
                    self._percentual(item.get("aliquota_cbs")),
                    self._percentual(item.get("reducao_cbs")),
                    item.get("ccredpres", ""),
                    item.get("diferimento", ""),
                    item.get("imposto_seletivo", ""),
                    self._periodo(item.get("vigencia_inicio"), item.get("vigencia_fim")),
                    item.get("fonte", "FiscalPro"),
                    f"{int(item.get('confiabilidade') or 0)}%",
                ),
            )
        if not itens:
            self.tree_reforma.insert("", tk.END, values=("Sem enquadramento específico validado",) + ("",) * 20)

    def _preencher_base_legal(self) -> None:
        self._limpar_tree(self.tree_legal)
        itens = self.dados_ficha.get("base_legal", [])
        for item in itens:
            vigencia = self._periodo(item.get("vigencia_inicio"), item.get("vigencia_fim"))
            registro_id = item.get("id")
            tipo_origem = item.get("tipo_origem") or "ficha_base_legal"
            iid = f"legal_{registro_id}" if tipo_origem == "ficha_base_legal" and registro_id is not None else ""
            self.tree_legal.insert(
                "",
                tk.END,
                iid=iid or None,
                values=(
                    item.get("status", ""),
                    item.get("tipo_norma", ""),
                    item.get("numero_norma", ""),
                    item.get("orgao", ""),
                    item.get("artigo_item", ""),
                    item.get("assunto", ""),
                    item.get("descricao", ""),
                    item.get("data_publicacao", ""),
                    vigencia,
                    item.get("impacto_tributario", ""),
                    item.get("fonte", ""),
                    f"{int(item.get('confiabilidade') or 0)}%",
                    item.get("url", ""),
                ),
            )
        if not itens:
            self.tree_legal.insert(
                "",
                tk.END,
                values=("PENDENTE", "", "", "", "", "", "Base legal ainda não vinculada ao NCM.") + ("",) * 6,
            )

    def _preencher_historico(self) -> None:
        self._limpar_tree(self.tree_historico)
        itens = self.dados_ficha.get("historico", [])
        for item in itens:
            self.tree_historico.insert(
                "",
                tk.END,
                values=(
                    item.get("criado_em", ""),
                    item.get("evento", ""),
                    item.get("campo", ""),
                    item.get("valor_anterior", ""),
                    item.get("valor_novo", ""),
                    item.get("origem", ""),
                    item.get("motivo", ""),
                ),
            )
        if not itens:
            self.tree_historico.insert("", tk.END, values=("", "Sem histórico registrado", "", "", "", "", ""))

    def _preencher_exemplos(self) -> None:
        self._limpar_tree(self.tree_exemplos)
        itens = self.dados_ficha.get("exemplos", [])
        for item in itens:
            numero = self._juntar(item.get("numero_documento"), item.get("serie"), separador=" / ")
            self.tree_exemplos.insert(
                "",
                tk.END,
                values=(
                    item.get("tipo_documento", ""),
                    numero,
                    item.get("operacao", ""),
                    item.get("cfop", ""),
                    item.get("cst", ""),
                    item.get("descricao", ""),
                    item.get("chave", ""),
                    item.get("arquivo_origem", ""),
                ),
            )
        if not itens:
            self.tree_exemplos.insert("", tk.END, values=("", "", "", "", "", "Nenhum exemplo de nota vinculado ainda.", "", ""))

    def _preencher_alertas(self) -> None:
        self._limpar_tree(self.tree_alertas)
        itens = self.dados_ficha.get("alertas", [])
        for item in itens:
            situacao = "LIDO" if int(item.get("lido") or 0) else item.get("status", "PENDENTE")
            norma = self._juntar(item.get("tipo_norma"), item.get("numero_norma"), separador=" ")
            iid = f"alerta_{item.get('id')}"
            self.tree_alertas.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    situacao,
                    item.get("data_alteracao", ""),
                    item.get("vigencia_inicio", ""),
                    item.get("titulo", ""),
                    item.get("resumo", ""),
                    item.get("comparacao_resumo", ""),
                    norma,
                    item.get("url", ""),
                ),
            )
        if not itens:
            self.tree_alertas.insert("", tk.END, values=("", "", "", "Nenhuma alteração registrada", "", "", "", ""))

    def _preencher_favoritos(self) -> None:
        self._limpar_tree(self.tree_favoritos)
        itens = FichaTributariaRepository.listar_favoritos()
        for item in itens:
            self.tree_favoritos.insert(
                "",
                tk.END,
                iid=f"fav_{item['ncm']}",
                values=(item.get("ncm", ""), item.get("descricao", ""), item.get("atualizado_em", "")),
            )
        if not itens:
            self.tree_favoritos.insert("", tk.END, values=("", "Nenhum NCM favorito ainda.", ""))

    # ------------------------------------------------------------------
    # Parecer e exportação
    # ------------------------------------------------------------------
    def _preencher_contexto_parecer(self, reiniciar: bool = False) -> None:
        empresas = ["Todas as empresas", *self.dados_ficha.get("empresas", [])]
        combo_empresa = self.parecer_contexto_combos.get("empresa")
        if combo_empresa is not None:
            combo_empresa.configure(values=empresas)

        empresa_principal = self.empresa_var.get().strip() or "Todas as empresas"
        tributacoes = self.dados_ficha.get("tributacoes", [])
        primeira_regra = next(
            (item for item in tributacoes if item.get("tipo_origem") == "tributacao_atual"),
            tributacoes[0] if tributacoes else {},
        )
        if reiniciar:
            padroes = {
                "empresa": empresa_principal,
                "regime": primeira_regra.get("regime") or "",
                "operacao": primeira_regra.get("operacao") or "",
                "finalidade": primeira_regra.get("finalidade") or "",
                "uf_origem": primeira_regra.get("uf_origem") or "MG",
                "uf_destino": primeira_regra.get("uf_destino") or "MG",
                "contribuinte": primeira_regra.get("contribuinte") or "TODOS",
                "data_operacao": date.today().strftime("%d/%m/%Y"),
            }
            for chave, valor in padroes.items():
                self.parecer_contexto_vars[chave].set(str(valor))
        else:
            self.parecer_contexto_vars["empresa"].set(empresa_principal)

    def _gerar_parecer_local(self, silencioso: bool = True) -> None:
        self.texto_parecer.configure(state=tk.NORMAL)
        self.texto_parecer.delete("1.0", tk.END)
        if not self.ncm_atual:
            self.texto_parecer.insert(tk.END, "Abra um NCM para gerar o parecer.")
            self.texto_parecer.configure(state=tk.DISABLED)
            return

        data_texto = self.parecer_contexto_vars["data_operacao"].get().strip()
        try:
            datetime.strptime(data_texto, "%d/%m/%Y")
        except ValueError:
            if not silencioso:
                messagebox.showwarning("FiscalPro", "A data da operação deve estar em dd/mm/aaaa.", parent=self)
            self.texto_parecer.insert(tk.END, "Data da operação inválida. Use dd/mm/aaaa.")
            self.texto_parecer.configure(state=tk.DISABLED)
            return

        contexto = {chave: variavel.get().strip() for chave, variavel in self.parecer_contexto_vars.items()}
        try:
            self.parecer = MotorParecer.gerar(self.dados_ficha, contexto)
        except Exception as erro:
            self.parecer = None
            self.texto_parecer.insert(tk.END, f"Não foi possível gerar o parecer:\n{erro}")
            self.texto_parecer.configure(state=tk.DISABLED)
            if not silencioso:
                messagebox.showerror("FiscalPro", f"Não foi possível gerar o parecer:\n{erro}", parent=self)
            return

        self.texto_parecer.insert(tk.END, self.parecer.para_texto())
        self.texto_parecer.configure(state=tk.DISABLED)
        self.parecer_confianca_var.set(
            f"Segurança geral do parecer: {self.parecer.confiabilidade:.0f}% "
            f"({self.parecer.nivel_confiabilidade})"
        )
        rastreabilidade = self.parecer.regras_aplicadas
        self.parecer_regra_var.set(
            f"Regra atual: {rastreabilidade.get('Regra atual', 'não localizada')} | "
            f"Aderência: {rastreabilidade.get('Aderência da regra atual', '0%')}"
        )
        self.status_var.set(f"Parecer do NCM {self.ncm_atual} atualizado para o contexto informado.")

    def _montar_ficha_motor(self) -> FichaTributaria:
        dados = self.dados_ficha.get("dados_gerais", {})
        tributacoes = self.dados_ficha.get("tributacoes", [])
        tributacao = tributacoes[0] if tributacoes else {}
        reformas = self.dados_ficha.get("reforma", [])
        reforma = reformas[0] if reformas else {}
        legais = self.dados_ficha.get("base_legal", [])

        perfis = {
            (
                item.get("cfop"), item.get("cst_icms"), item.get("icms"), item.get("icms_st"),
                item.get("cst_pis"), item.get("aliquota_pis"), item.get("cst_cofins"), item.get("aliquota_cofins"),
            )
            for item in tributacoes
        }
        fontes = sorted({str(item.get("fonte")) for item in tributacoes if item.get("fonte")})
        base_legal = [
            self._juntar(item.get("tipo_norma"), item.get("numero_norma"), item.get("artigo_item"), item.get("descricao"), separador=" — ")
            for item in legais
        ]

        return FichaTributaria(
            ncm=dados.get("ncm", self.ncm_atual),
            descricao=dados.get("descricao", ""),
            cest=tributacao.get("cest") or dados.get("cest", ""),
            uf=tributacao.get("uf_destino") or tributacao.get("uf", ""),
            regime=tributacao.get("regime", ""),
            operacao=tributacao.get("operacao", ""),
            cfop=tributacao.get("cfop", ""),
            cst_icms=tributacao.get("cst_icms", ""),
            cst_ipi=tributacao.get("cst_ipi", ""),
            pis_cst=tributacao.get("cst_pis", ""),
            cofins_cst=tributacao.get("cst_cofins", ""),
            aliquota_pis=self._numero(tributacao.get("aliquota_pis")),
            aliquota_cofins=self._numero(tributacao.get("aliquota_cofins")),
            icms=self._numero(tributacao.get("icms")),
            icms_st=str(tributacao.get("icms_st") or ""),
            fcp=self._numero(tributacao.get("fcp")),
            ipi=self._numero(tributacao.get("ipi")),
            cclasstrib=str(reforma.get("cclasstrib") or reforma.get("classificacao") or ""),
            ccredpres=str(reforma.get("ccredpres") or ""),
            cst_ibs=str(reforma.get("cst_ibs") or ""),
            cst_cbs=str(reforma.get("cst_cbs") or ""),
            aliquota_ibs=self._numero(reforma.get("aliquota_ibs")),
            aliquota_cbs=self._numero(reforma.get("aliquota_cbs")),
            imposto_seletivo=str(reforma.get("imposto_seletivo") or ""),
            reforma_status="CADASTRADA" if reformas else "SEM ENQUADRAMENTO ESPECÍFICO",
            fontes=fontes,
            base_legal=[texto for texto in base_legal if texto],
            confiabilidade=max([self._numero(item.get("confiabilidade")) for item in tributacoes] or [0]),
            status=str(dados.get("status") or "LOCAL"),
            quantidade_produtos=int(dados.get("total_produtos") or 0),
            quantidade_variacoes=len(perfis),
        )

    def salvar_parecer(self) -> None:
        if self.parecer is None:
            messagebox.showwarning("FiscalPro", "Abra uma ficha para gerar o parecer.", parent=self)
            return
        registro_id = HistoricoParecerRepository.salvar(self.parecer)
        FichaTributariaRepository.registrar_historico(
            self.ncm_atual,
            evento="PARECER SALVO",
            campo="Parecer tributário",
            valor_novo=f"Registro {registro_id}",
            origem="Ficha Tributária Inteligente",
            motivo=(
                f"Empresa: {self.parecer.contexto.get('Empresa', '')} | "
                f"Regime: {self.parecer.contexto.get('Regime', '')} | "
                f"Operação: {self.parecer.contexto.get('Operação', '')} | "
                f"Confiança: {self.parecer.confiabilidade:.0f}%"
            ),
        )
        self.dados_ficha["historico"] = FichaTributariaRepository.buscar_historico(self.ncm_atual)
        self._preencher_historico()
        messagebox.showinfo("FiscalPro", f"Parecer salvo no histórico. Registro {registro_id}.", parent=self)

    def gerar_pdf(self) -> None:
        if self.parecer is None:
            messagebox.showwarning("FiscalPro", "Abra uma ficha para gerar o parecer.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"Ficha_Tributaria_NCM_{self.ncm_atual}.pdf",
        )
        if not caminho:
            return
        try:
            ExportadorParecer.para_pdf(self.parecer, caminho)
            messagebox.showinfo("FiscalPro", "PDF gerado com sucesso.", parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível gerar o PDF:\n{erro}", parent=self)

    def gerar_excel(self) -> None:
        if self.parecer is None:
            messagebox.showwarning("FiscalPro", "Abra uma ficha para gerar o parecer.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=f"Ficha_Tributaria_NCM_{self.ncm_atual}.xlsx",
        )
        if not caminho:
            return
        try:
            ExportadorParecer.para_excel(self.parecer, caminho)
            messagebox.showinfo("FiscalPro", "Planilha gerada com sucesso.", parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível gerar a planilha:\n{erro}", parent=self)

    # ------------------------------------------------------------------
    # Cadastro e versionamento tributário — Sprint 13.2
    # ------------------------------------------------------------------
    def _garantir_ncm_aberto(self) -> bool:
        if self.ncm_atual:
            return True
        messagebox.showwarning("FiscalPro", "Abra a ficha de um NCM antes de cadastrar regras.", parent=self)
        return False

    @staticmethod
    def _registro_id_da_selecao(tree: ttk.Treeview, prefixo: str) -> Optional[int]:
        selecionados = tree.selection()
        if not selecionados:
            return None
        iid = str(selecionados[0])
        if not iid.startswith(prefixo):
            return None
        try:
            return int(iid[len(prefixo):])
        except ValueError:
            return None

    def nova_tributacao(self) -> None:
        if not self._garantir_ncm_aberto():
            return
        empresa = self.empresa_var.get().strip()
        inicial = {"empresa": "" if empresa == "Todas as empresas" else empresa}

        def salvar(dados: Dict[str, Any]) -> None:
            registro_id = FichaTributariaRepository.salvar_tributacao_atual(
                dados,
                encerrar_anterior=bool(dados.pop("_encerrar_anterior", True)),
            )
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Regra tributária {registro_id} cadastrada com sucesso.")

        _FormularioTributacaoAtual(self, "Nova regra — Tributação Atual", self.ncm_atual, inicial, salvar, True)

    def editar_tributacao(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_tributacao, "tributacao_atual_")
        if registro_id is None:
            if self.tree_tributacao.selection():
                messagebox.showinfo(
                    "FiscalPro",
                    "Esta linha veio do cadastro operacional por produto. Para criar uma regra completa por UF, regime e operação, clique em 'Nova regra'.",
                    parent=self,
                )
            else:
                messagebox.showwarning("FiscalPro", "Selecione uma regra da Tributação Atual.", parent=self)
            return
        registro = FichaTributariaRepository.buscar_tributacao_atual_por_id(registro_id)
        if not registro:
            messagebox.showerror("FiscalPro", "A regra selecionada não foi encontrada.", parent=self)
            return

        def salvar(dados: Dict[str, Any]) -> None:
            dados.pop("_encerrar_anterior", None)
            FichaTributariaRepository.salvar_tributacao_atual(dados, registro_id=registro_id, encerrar_anterior=False)
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Regra tributária {registro_id} atualizada.")

        _FormularioTributacaoAtual(self, "Editar regra — Tributação Atual", self.ncm_atual, registro, salvar, False)

    def duplicar_tributacao(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_tributacao, "tributacao_atual_")
        if registro_id is None:
            messagebox.showwarning("FiscalPro", "Selecione uma regra cadastrada para duplicar.", parent=self)
            return
        registro = FichaTributariaRepository.buscar_tributacao_atual_por_id(registro_id)
        if not registro:
            return
        inicial = dict(registro)
        inicial.pop("id", None)
        inicial.pop("vigencia_inicio", None)
        inicial["vigencia_fim"] = ""
        inicial["status"] = "VIGENTE"

        def salvar(dados: Dict[str, Any]) -> None:
            novo_id = FichaTributariaRepository.salvar_tributacao_atual(
                dados,
                encerrar_anterior=bool(dados.pop("_encerrar_anterior", True)),
            )
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Regra duplicada como novo registro {novo_id}.")

        _FormularioTributacaoAtual(self, "Duplicar regra — Tributação Atual", self.ncm_atual, inicial, salvar, True)

    def encerrar_tributacao(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_tributacao, "tributacao_atual_")
        if registro_id is None:
            messagebox.showwarning("FiscalPro", "Selecione uma regra cadastrada para encerrar.", parent=self)
            return
        data_fim = simpledialog.askstring(
            "Encerrar vigência",
            "Informe o último dia de validade da regra (dd/mm/aaaa):",
            initialvalue=date.today().strftime("%d/%m/%Y"),
            parent=self,
        )
        if not data_fim:
            return
        try:
            FichaTributariaRepository.encerrar_tributacao_atual(registro_id, data_fim)
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Vigência da regra {registro_id} encerrada.")
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível encerrar a regra:\n{erro}", parent=self)

    def nova_reforma(self) -> None:
        if not self._garantir_ncm_aberto():
            return
        empresa = self.empresa_var.get().strip()
        inicial = {"empresa": "" if empresa == "Todas as empresas" else empresa}

        def salvar(dados: Dict[str, Any]) -> None:
            registro_id = FichaTributariaRepository.salvar_reforma(
                dados,
                encerrar_anterior=bool(dados.pop("_encerrar_anterior", True)),
            )
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Regra da Reforma {registro_id} cadastrada com sucesso.")

        _FormularioReformaTributaria(self, "Nova regra — Reforma Tributária", self.ncm_atual, inicial, salvar, True)

    def editar_reforma(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_reforma, "tributacao_reforma_")
        if registro_id is None:
            if self.tree_reforma.selection():
                messagebox.showinfo(
                    "FiscalPro",
                    "Esta linha veio do cadastro operacional por produto. Clique em 'Nova regra' para criar um enquadramento completo da Reforma.",
                    parent=self,
                )
            else:
                messagebox.showwarning("FiscalPro", "Selecione uma regra da Reforma Tributária.", parent=self)
            return
        registro = FichaTributariaRepository.buscar_reforma_por_id(registro_id)
        if not registro:
            messagebox.showerror("FiscalPro", "A regra selecionada não foi encontrada.", parent=self)
            return

        def salvar(dados: Dict[str, Any]) -> None:
            dados.pop("_encerrar_anterior", None)
            FichaTributariaRepository.salvar_reforma(dados, registro_id=registro_id, encerrar_anterior=False)
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Regra da Reforma {registro_id} atualizada.")

        _FormularioReformaTributaria(self, "Editar regra — Reforma Tributária", self.ncm_atual, registro, salvar, False)

    def duplicar_reforma(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_reforma, "tributacao_reforma_")
        if registro_id is None:
            messagebox.showwarning("FiscalPro", "Selecione uma regra da Reforma para duplicar.", parent=self)
            return
        registro = FichaTributariaRepository.buscar_reforma_por_id(registro_id)
        if not registro:
            return
        inicial = dict(registro)
        inicial.pop("id", None)
        inicial.pop("vigencia_inicio", None)
        inicial["vigencia_fim"] = ""
        inicial["status"] = "VIGENTE"

        def salvar(dados: Dict[str, Any]) -> None:
            novo_id = FichaTributariaRepository.salvar_reforma(
                dados,
                encerrar_anterior=bool(dados.pop("_encerrar_anterior", True)),
            )
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Regra da Reforma duplicada como registro {novo_id}.")

        _FormularioReformaTributaria(self, "Duplicar regra — Reforma Tributária", self.ncm_atual, inicial, salvar, True)

    def encerrar_reforma(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_reforma, "tributacao_reforma_")
        if registro_id is None:
            messagebox.showwarning("FiscalPro", "Selecione uma regra da Reforma para encerrar.", parent=self)
            return
        data_fim = simpledialog.askstring(
            "Encerrar vigência",
            "Informe o último dia de validade da regra (dd/mm/aaaa):",
            initialvalue=date.today().strftime("%d/%m/%Y"),
            parent=self,
        )
        if not data_fim:
            return
        try:
            FichaTributariaRepository.encerrar_reforma(registro_id, data_fim)
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Vigência da regra da Reforma {registro_id} encerrada.")
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível encerrar a regra:\n{erro}", parent=self)

    # ------------------------------------------------------------------
    # Base Legal e histórico legislativo — Sprint 13.3
    # ------------------------------------------------------------------
    def nova_base_legal(self) -> None:
        if not self._garantir_ncm_aberto():
            return

        def salvar(dados: Dict[str, Any]) -> None:
            registro_id = FichaTributariaRepository.salvar_base_legal(dados)
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Base legal {registro_id} cadastrada e histórico atualizado.")

        _FormularioBaseLegal(self, self.ncm_atual, {}, salvar, True)

    def editar_base_legal(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_legal, "legal_")
        if registro_id is None:
            messagebox.showwarning("FiscalPro", "Selecione uma norma cadastrada para editar.", parent=self)
            return
        registro = FichaTributariaRepository.buscar_base_legal_por_id(registro_id)
        if not registro:
            messagebox.showerror("FiscalPro", "A base legal selecionada não foi encontrada.", parent=self)
            return

        def salvar(dados: Dict[str, Any]) -> None:
            FichaTributariaRepository.salvar_base_legal(dados, registro_id=registro_id)
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Base legal {registro_id} atualizada.")

        _FormularioBaseLegal(self, self.ncm_atual, registro, salvar, False)

    def duplicar_base_legal(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_legal, "legal_")
        if registro_id is None:
            messagebox.showwarning("FiscalPro", "Selecione uma norma cadastrada para duplicar.", parent=self)
            return
        registro = FichaTributariaRepository.buscar_base_legal_por_id(registro_id)
        if not registro:
            return
        inicial = dict(registro)
        inicial.pop("id", None)
        inicial["norma_anterior_id"] = registro_id
        inicial["numero_norma"] = ""
        inicial["data_publicacao"] = ""
        inicial["vigencia_inicio"] = ""
        inicial["vigencia_fim"] = ""
        inicial["status"] = "VIGENTE"
        inicial["gera_alerta"] = 1

        def salvar(dados: Dict[str, Any]) -> None:
            dados["norma_anterior_id"] = registro_id
            novo_id = FichaTributariaRepository.salvar_base_legal(dados)
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Base legal duplicada como novo registro {novo_id}.")

        _FormularioBaseLegal(self, self.ncm_atual, inicial, salvar, True)

    def encerrar_base_legal(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_legal, "legal_")
        if registro_id is None:
            messagebox.showwarning("FiscalPro", "Selecione uma norma cadastrada para encerrar ou revogar.", parent=self)
            return
        escolha = messagebox.askyesnocancel(
            "Encerrar ou revogar",
            "Clique em Sim para marcar como REVOGADA.\nClique em Não para marcar como ENCERRADA.\nClique em Cancelar para voltar.",
            parent=self,
        )
        if escolha is None:
            return
        status = "REVOGADA" if escolha else "ENCERRADA"
        data_fim = simpledialog.askstring(
            status.title(),
            "Informe o último dia de vigência (dd/mm/aaaa):",
            initialvalue=date.today().strftime("%d/%m/%Y"),
            parent=self,
        )
        if not data_fim:
            return
        try:
            FichaTributariaRepository.encerrar_base_legal(registro_id, data_fim, status=status)
            self.buscar(manter_empresa=True)
            self.status_var.set(f"Base legal {registro_id} marcada como {status}.")
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível encerrar a base legal:\n{erro}", parent=self)

    def comparar_base_legal(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_legal, "legal_")
        if registro_id is None:
            messagebox.showwarning("FiscalPro", "Selecione uma norma para comparar.", parent=self)
            return
        try:
            comparacao = FichaTributariaRepository.comparar_base_legal(registro_id)
            _JanelaComparacaoLegal(self, comparacao)
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível comparar as normas:\n{erro}", parent=self)

    def abrir_fonte_legal(self) -> None:
        registro_id = self._registro_id_da_selecao(self.tree_legal, "legal_")
        if registro_id is None:
            messagebox.showwarning("FiscalPro", "Selecione uma norma para abrir a fonte oficial.", parent=self)
            return
        registro = FichaTributariaRepository.buscar_base_legal_por_id(registro_id)
        self._abrir_url((registro or {}).get("url"), "Esta norma não possui link oficial cadastrado.")

    def _alerta_id_selecionado(self) -> Optional[int]:
        return self._registro_id_da_selecao(self.tree_alertas, "alerta_")

    def _definir_alerta_selecionado(self, lido: bool) -> None:
        alerta_id = self._alerta_id_selecionado()
        if alerta_id is None:
            messagebox.showwarning("FiscalPro", "Selecione um alerta legislativo.", parent=self)
            return
        FichaTributariaRepository.marcar_alerta_lido(alerta_id, lido)
        self.dados_ficha["alertas"] = FichaTributariaRepository.buscar_alertas(self.ncm_atual)
        self._preencher_alertas()
        self._atualizar_cabecalho()
        self.status_var.set("Alerta marcado como lido." if lido else "Alerta marcado como não lido.")

    def comparar_alerta_selecionado(self) -> None:
        alerta_id = self._alerta_id_selecionado()
        if alerta_id is None:
            messagebox.showwarning("FiscalPro", "Selecione um alerta para comparar.", parent=self)
            return
        alerta = FichaTributariaRepository.buscar_alerta_por_id(alerta_id)
        base_legal_id = (alerta or {}).get("base_legal_id")
        if not base_legal_id:
            messagebox.showinfo(
                "FiscalPro",
                "Este alerta antigo não está vinculado a um registro da Base Legal para comparação.",
                parent=self,
            )
            return
        try:
            comparacao = FichaTributariaRepository.comparar_base_legal(int(base_legal_id))
            _JanelaComparacaoLegal(self, comparacao)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível comparar o alerta:\n{erro}", parent=self)

    def abrir_fonte_alerta(self) -> None:
        alerta_id = self._alerta_id_selecionado()
        if alerta_id is None:
            messagebox.showwarning("FiscalPro", "Selecione um alerta para abrir a fonte oficial.", parent=self)
            return
        alerta = FichaTributariaRepository.buscar_alerta_por_id(alerta_id)
        self._abrir_url((alerta or {}).get("url"), "Este alerta não possui link oficial cadastrado.")

    def _abrir_url(self, url: Any, mensagem_vazia: str) -> None:
        endereco = str(url or "").strip()
        if not endereco:
            messagebox.showinfo("FiscalPro", mensagem_vazia, parent=self)
            return
        try:
            webbrowser.open_new_tab(endereco)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível abrir a fonte oficial:\n{erro}", parent=self)

    # ------------------------------------------------------------------
    # Favoritos e alertas
    # ------------------------------------------------------------------
    def alternar_favorito(self) -> None:
        if not self.ncm_atual:
            messagebox.showwarning("FiscalPro", "Abra uma ficha antes de favoritar.", parent=self)
            return
        novo_status = not bool(self.dados_ficha.get("favorito"))
        FichaTributariaRepository.definir_favorito(self.ncm_atual, novo_status)
        self.dados_ficha["favorito"] = novo_status
        FichaTributariaRepository.registrar_historico(
            self.ncm_atual,
            evento="FAVORITO ALTERADO",
            campo="Favorito",
            valor_anterior="Não" if novo_status else "Sim",
            valor_novo="Sim" if novo_status else "Não",
            origem="Ficha Tributária Inteligente",
        )
        self._atualizar_botao_favorito()
        self._preencher_dados_gerais()
        self._preencher_favoritos()

    def _atualizar_botao_favorito(self) -> None:
        if self.dados_ficha.get("favorito"):
            self.botao_favorito.configure(text="★ Remover favorito")
        else:
            self.botao_favorito.configure(text="☆ Favoritar NCM")

    def _abrir_favorito_selecionado(self, _evento=None) -> None:
        selecionados = self.tree_favoritos.selection()
        if not selecionados:
            return
        valores = self.tree_favoritos.item(selecionados[0], "values")
        if not valores or not str(valores[0]).strip():
            return
        self.ncm_var.set(str(valores[0]))
        self.empresa_var.set("Todas as empresas")
        self.buscar()
        self.notebook.select(0)

    def _marcar_alerta_selecionado(self, _evento=None) -> None:
        alerta_id = self._alerta_id_selecionado()
        if alerta_id is not None:
            self._definir_alerta_selecionado(True)

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------
    @staticmethod
    def _limpar_tree(tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

    @staticmethod
    def _texto(valor: Any) -> str:
        if valor is None or valor == "":
            return "-"
        return str(valor)

    @staticmethod
    def _numero(valor: Any) -> float:
        if valor in (None, ""):
            return 0.0
        try:
            return float(str(valor).replace("%", "").replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _percentual(cls, valor: Any) -> str:
        numero = cls._numero(valor)
        return f"{numero:.2f}".replace(".", ",")

    @staticmethod
    def _juntar(*valores: Any, separador: str = "/") -> str:
        partes = [str(valor).strip() for valor in valores if valor not in (None, "") and str(valor).strip()]
        return separador.join(partes) if partes else ""

    @staticmethod
    def _periodo(inicio: Any, fim: Any) -> str:
        inicio = str(inicio or "").strip()
        fim = str(fim or "").strip()
        if inicio and fim:
            return f"{inicio} até {fim}"
        if inicio:
            return f"A partir de {inicio}"
        if fim:
            return f"Até {fim}"
        return "Não informada"

class _SeletorNCM(tk.Toplevel):
    """Seleção simples quando uma descrição encontra mais de um NCM."""

    def __init__(self, parent: tk.Misc, resultados: Sequence[Tuple[str, str]]) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Escolha o produto")
        dimensionar_janela(self, 820, 520, 620, 380, maximizar_em_tela_baixa=False)
        self.transient(parent)
        self.grab_set()
        self.resultado: Optional[str] = None

        ttk.Label(
            self,
            text="Mais de um NCM foi encontrado. Selecione o produto correto:",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 8))

        frame = ttk.Frame(self, padding=(14, 0, 14, 8))
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(frame, columns=("ncm", "descricao"), show="headings", selectmode="browse")
        self.tree.heading("ncm", text="NCM")
        self.tree.heading("descricao", text="Descrição")
        self.tree.column("ncm", width=120, anchor="center", stretch=False)
        self.tree.column("descricao", width=560, anchor="w")
        barra = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        barra.pack(side=tk.RIGHT, fill=tk.Y)

        for ncm, descricao in resultados:
            self.tree.insert("", tk.END, values=(ncm, descricao))

        rodape = ttk.Frame(self, padding=(14, 4, 14, 14))
        rodape.pack(fill=tk.X)
        ttk.Button(rodape, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(rodape, text="Selecionar", command=self._selecionar).pack(side=tk.RIGHT)

        self.tree.bind("<Double-1>", lambda _e: self._selecionar())
        self.bind("<Escape>", lambda _e: self.destroy())
        if self.tree.get_children():
            primeiro = self.tree.get_children()[0]
            self.tree.selection_set(primeiro)
            self.tree.focus(primeiro)

    def _selecionar(self) -> None:
        selecao = self.tree.selection()
        if not selecao:
            messagebox.showwarning("FiscalPro", "Selecione um produto.", parent=self)
            return
        valores = self.tree.item(selecao[0], "values")
        self.resultado = str(valores[0]) if valores else None
        self.destroy()


class _JanelaParecerSimplificado(tk.Toplevel):
    """Leitura e exportação do parecer sem expor a tela técnica completa."""

    def __init__(self, parent: tk.Misc, parecer: Any) -> None:
        super().__init__(parent)
        self.parecer = parecer
        self.title(f"FiscalPro — Parecer NCM {parecer.ncm}")
        dimensionar_janela(self, 1020, 760, 720, 520)
        self.transient(parent)

        ttk.Label(
            self,
            text="Parecer Tributário Inteligente",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 2))
        ttk.Label(
            self,
            text=f"NCM {parecer.ncm} — confiança {parecer.confiabilidade:.0f}% ({parecer.nivel_confiabilidade})",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        frame = ttk.Frame(self, padding=(14, 0, 14, 8))
        frame.pack(fill=tk.BOTH, expand=True)
        texto = tk.Text(frame, wrap=tk.WORD, font=("Segoe UI", 10), padx=10, pady=10)
        barra = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=texto.yview)
        texto.configure(yscrollcommand=barra.set)
        texto.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        barra.pack(side=tk.RIGHT, fill=tk.Y)
        texto.insert("1.0", parecer.para_texto())
        texto.configure(state=tk.DISABLED)
        self.texto = texto

        rodape = ttk.Frame(self, padding=(14, 4, 14, 14))
        rodape.pack(fill=tk.X)
        ttk.Button(rodape, text="Copiar", command=self._copiar).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Salvar PDF", command=self._salvar_pdf).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(rodape, text="Salvar Excel", command=self._salvar_excel).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _copiar(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.parecer.para_texto())
        messagebox.showinfo("FiscalPro", "Parecer copiado para a área de transferência.", parent=self)

    def _salvar_pdf(self) -> None:
        caminho = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar parecer em PDF",
            defaultextension=".pdf",
            initialfile=f"Parecer_Tributario_{self.parecer.ncm}.pdf",
            filetypes=(("Arquivo PDF", "*.pdf"),),
        )
        if not caminho:
            return
        try:
            ExportadorParecer.para_pdf(self.parecer, caminho)
            messagebox.showinfo("FiscalPro", f"Parecer salvo em:\n{caminho}", parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível gerar o PDF:\n{erro}", parent=self)

    def _salvar_excel(self) -> None:
        caminho = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar parecer em Excel",
            defaultextension=".xlsx",
            initialfile=f"Parecer_Tributario_{self.parecer.ncm}.xlsx",
            filetypes=(("Planilha Excel", "*.xlsx"),),
        )
        if not caminho:
            return
        try:
            ExportadorParecer.para_excel(self.parecer, caminho)
            messagebox.showinfo("FiscalPro", f"Parecer salvo em:\n{caminho}", parent=self)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível gerar a planilha:\n{erro}", parent=self)


class _JanelaDetalhesTecnicosAmpliados(tk.Toplevel):
    """Visualização ampla dos detalhes técnicos da Ficha Simplificada."""

    def __init__(
        self,
        parent: tk.Misc,
        titulo: str,
        linhas: Sequence[Tuple[str, str, str]],
        explicacao_texto: str,
    ) -> None:
        super().__init__(parent)
        self.title(f"FiscalPro — Detalhes técnicos — {titulo}")
        dimensionar_janela(self, 1280, 760, 980, 620)
        self.transient(parent)

        cabecalho = tk.Frame(self, bg="#1F4E78", height=64)
        cabecalho.pack(fill=tk.X)
        tk.Label(
            cabecalho,
            text="Detalhes técnicos ampliados",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", padx=18, pady=(10, 0))
        tk.Label(
            cabecalho,
            text=titulo,
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=(0, 8))

        corpo = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        corpo.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        quadro = ttk.LabelFrame(corpo, text="Tributação e validações", padding=8)
        explicacao = ttk.LabelFrame(corpo, text="Explicação e alertas", padding=8)
        corpo.add(quadro, weight=3)
        corpo.add(explicacao, weight=2)

        quadro.rowconfigure(0, weight=1)
        quadro.columnconfigure(0, weight=1)
        tree = ttk.Treeview(
            quadro,
            columns=("campo", "resultado", "observacao"),
            show="headings",
            height=24,
        )
        tree.heading("campo", text="Campo")
        tree.heading("resultado", text="Resultado")
        tree.heading("observacao", text="Observação")
        tree.column("campo", width=190, stretch=False)
        tree.column("resultado", width=330, stretch=True)
        tree.column("observacao", width=620, stretch=True)
        barra_y = ttk.Scrollbar(quadro, orient=tk.VERTICAL, command=tree.yview)
        barra_x = ttk.Scrollbar(quadro, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")

        for linha in linhas:
            valores = tuple(linha)[:3]
            if len(valores) < 3:
                valores = valores + ("",) * (3 - len(valores))
            tree.insert("", tk.END, values=valores)

        explicacao.rowconfigure(0, weight=1)
        explicacao.columnconfigure(0, weight=1)
        texto = tk.Text(
            explicacao,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            padx=10,
            pady=10,
        )
        barra_texto = ttk.Scrollbar(explicacao, orient=tk.VERTICAL, command=texto.yview)
        texto.configure(yscrollcommand=barra_texto.set)
        texto.grid(row=0, column=0, sticky="nsew")
        barra_texto.grid(row=0, column=1, sticky="ns")
        texto.insert("1.0", explicacao_texto or "Sem explicações adicionais para esta análise.")
        texto.configure(state=tk.DISABLED)

        rodape = ttk.Frame(self, padding=(14, 0, 14, 12))
        rodape.pack(fill=tk.X)
        ttk.Label(
            rodape,
            text="Dica: use as barras de rolagem para consultar toda a observação sem reduzir as colunas.",
            foreground="#555555",
        ).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(50, self._tentar_maximizar)

    def _tentar_maximizar(self) -> None:
        try:
            self.state("zoomed")
        except tk.TclError:
            pass


class _JanelaBaseLegalSimplificada(tk.Toplevel):
    """Resumo das evidências oficiais sem expor o cadastro técnico completo."""

    def __init__(self, parent: tk.Misc, resultado: Dict[str, Any], parecer: Any = None) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Base Legal e Fontes Oficiais")
        dimensionar_janela(self, 1020, 720, 760, 520)
        self.transient(parent)
        self.resultado = resultado or {}
        self.parecer = parecer
        self.urls: Dict[str, str] = {}
        self.detalhes: Dict[str, str] = {}

        cabecalho = tk.Frame(self, bg="#1F4E78", height=72)
        cabecalho.pack(fill=tk.X)
        tk.Label(
            cabecalho,
            text="Base Legal e Fontes Oficiais",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(11, 0))
        tk.Label(
            cabecalho,
            text="O FiscalPro separa o que foi confirmado oficialmente do que ainda precisa de revisão.",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20)

        corpo = ttk.Frame(self, padding=14)
        corpo.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(
            corpo,
            columns=("item", "situacao", "fonte", "atualizacao"),
            show="headings",
            height=8,
        )
        for coluna, titulo, largura in (
            ("item", "Informação", 150),
            ("situacao", "Situação", 230),
            ("fonte", "Fonte oficial", 300),
            ("atualizacao", "Atualização", 150),
        ):
            self.tree.heading(coluna, text=titulo)
            self.tree.column(coluna, width=largura, stretch=coluna in {"situacao", "fonte"})
        self.tree.pack(fill=tk.X)
        self.tree.bind("<<TreeviewSelect>>", self._mostrar_detalhes)

        ttk.Label(corpo, text="Detalhes", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(14, 4))
        self.texto = tk.Text(corpo, wrap=tk.WORD, height=15, padx=8, pady=8, font=("Segoe UI", 9))
        self.texto.pack(fill=tk.BOTH, expand=True)

        rodape = ttk.Frame(self, padding=(14, 0, 14, 12))
        rodape.pack(fill=tk.X)
        ttk.Button(rodape, text="Abrir fonte oficial", command=self._abrir_fonte).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

        self._preencher()
        self.bind("<Escape>", lambda _e: self.destroy())

    def _fonte(self, codigo: str) -> Dict[str, Any]:
        return dict((self.resultado.get("fontes_por_codigo") or {}).get(codigo) or {})

    @staticmethod
    def _data_fonte(fonte: Dict[str, Any]) -> str:
        texto = str(fonte.get("atualizado_em") or "").strip()
        if not texto:
            return "Não sincronizada"
        try:
            return datetime.fromisoformat(texto).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return texto

    def _adicionar(
        self,
        chave: str,
        item: str,
        situacao: str,
        codigo_fonte: str,
        detalhes: str,
        *,
        nome_fonte: str = "",
        url_fonte: str = "",
    ) -> None:
        fonte = self._fonte(codigo_fonte)
        nome = nome_fonte or fonte.get("nome") or fonte.get("orgao") or codigo_fonte
        atualizacao = self._data_fonte(fonte) if fonte else "Regra estruturada"
        iid = self.tree.insert("", tk.END, iid=chave, values=(item, situacao, nome, atualizacao))
        self.urls[iid] = str(url_fonte or fonte.get("url") or "")
        self.tree.set(iid, "situacao", situacao)
        self.detalhes[iid] = detalhes

    def _preencher(self) -> None:
        ncm_ok = bool(self.resultado.get("ncm_confirmado"))
        self._adicionar(
            "ncm",
            "NCM e descrição",
            "CONFIRMADO" if ncm_ok else "NÃO CONFIRMADO",
            "RFB_NCM",
            (
                f"NCM {self.resultado.get('ncm', '')}.\n"
                f"Descrição oficial: {self.resultado.get('descricao_oficial') or 'não localizada'}.\n\n"
                "A tabela oficial confirma a existência e a descrição do código, mas não define sozinha "
                "a tributação completa da operação."
            ),
        )

        ipi_ok = bool(self.resultado.get("ipi_confirmado"))
        tipi_itens = self.resultado.get("tipi") or []
        detalhe_ipi = [
            f"IPI principal: {ConsultaOficialService.texto_ipi(self.resultado)}.",
            "A alíquota foi obtida da TIPI oficial sincronizada.",
        ]
        if len(tipi_itens) > 1:
            detalhe_ipi.append(
                f"Existem {len(tipi_itens)} enquadramentos/EX TIPI para este NCM; confira a descrição do produto."
            )
        self._adicionar(
            "ipi",
            "IPI",
            ConsultaOficialService.texto_ipi(self.resultado) if ipi_ok else "NÃO SINCRONIZADO",
            "RFB_TIPI",
            "\n".join(detalhe_ipi),
        )

        normas = self.resultado.get("normas_oficiais") or []
        texto_normas = "\n".join(
            f"• {item.get('tipo_norma', '')} {item.get('numero_norma', '')} — "
            f"{item.get('artigo_item', '')} — {item.get('assunto') or item.get('descricao') or ''}"
            for item in normas
        )
        st_mg = ConsultaOficialService.st_contextual(self.resultado)
        icms_ctx = ConsultaOficialService.icms_contextual(self.resultado)
        uf_st = str(st_mg.get("uf") or icms_ctx.get("uf") or "MG").strip().upper()
        st_situacao = str(st_mg.get("status") or "NÃO SINCRONIZADO")
        mva_st = st_mg.get("mva_aplicada")
        if mva_st is None:
            mva_st = st_mg.get("mva_original")
        mva_texto = (f"{float(mva_st):.2f}%".replace(".", ",") if mva_st is not None else "não informada")
        detalhe_st = [
            str(st_mg.get("observacao") or f"Atualize/revise a cobertura oficial de {uf_st}."),
            "",
            f"CEST: {st_mg.get('cest') or 'não localizado'}.",
            f"NCM legal: {st_mg.get('ncm_legal') or 'não localizado'}.",
            f"Descrição legal: {st_mg.get('descricao_legal') or 'não localizada'}.",
            f"Âmbito: {st_mg.get('ambito') or 'não informado'}.",
            f"MVA original: {mva_texto}.",
            f"Aplicação/responsabilidade: {st_mg.get('responsabilidade') or st_mg.get('aplicacao_operacao') or 'revisar'}.",
            f"Fundamento: {st_mg.get('fundamento_legal') or st_mg.get('fundamento') or 'legislação estadual estruturada'}.",
        ]
        self._adicionar(
            "icms",
            "ICMS",
            "BASE LEGAL VINCULADA" if normas else "ALÍQUOTA A REVISAR",
            f"SEFA_{uf_st}",
            (
                "A alíquota interna de ICMS pode depender de exceção, redução de base, benefício ou regime especial.\n\n"
                + ("Normas oficiais vinculadas:\n" + texto_normas if normas else
                   "O FiscalPro confirma o enquadramento nos segmentos oficiais de ICMS-ST já sincronizados. A confirmação automática "
                   "da alíquota própria de ICMS será tratada separadamente.")
            ),
        )
        fonte_st_url = str(st_mg.get("fonte_url") or "").strip()
        # Motores estaduais podem guardar mais de uma fonte separada por "|".
        # O botão abre a fonte estadual principal; as demais continuam descritas
        # no fundamento/observação da regra.
        fonte_st_principal = fonte_st_url.split("|")[0].strip() if fonte_st_url else ""
        codigo_st = str(st_mg.get("fonte_codigo") or "").strip()
        if not codigo_st:
            codigo_st = "SEF_MG_ST" if uf_st == "MG" else f"SEFA_{uf_st}"
        rotulo_st_base_legal = f"ICMS-ST {uf_st} — CEST e MVA"
        if (
            st_mg.get("antecipacao_percentual") is not None
            and not bool(st_mg.get("confirmado"))
        ):
            rotulo_st_base_legal = f"Antecipação ICMS {uf_st} — CEST e regra"
        self._adicionar(
            "st",
            rotulo_st_base_legal,
            st_situacao,
            codigo_st,
            "\n".join(detalhe_st),
            nome_fonte=str(st_mg.get("fonte_nome") or ""),
            url_fonte=fonte_st_principal,
        )
        piscofins = dict(self.resultado.get("piscofins_nacional") or {})
        piscofins_mono = dict(self.resultado.get("piscofins_monofasico") or {})
        exibicao_pis = ConsultaOficialService.piscofins_para_exibicao(self.resultado)
        if exibicao_pis.get("confirmado"):
            situacao_pis = (
                f"CONFIRMADO — CST {exibicao_pis.get('cst_pis') or '-'} / "
                f"{float(exibicao_pis.get('aliquota_pis') or 0.0):.2f}%"
            ).replace(".", ",")
        elif exibicao_pis.get("sugerido"):
            situacao_pis = (
                f"SUGESTÃO — CST {exibicao_pis.get('cst_pis') or '-'} / "
                f"{float(exibicao_pis.get('aliquota_pis') or 0.0):.2f}%"
            ).replace(".", ",")
        else:
            situacao_pis = str(exibicao_pis.get("status") or "REVISÃO NECESSÁRIA")
        detalhe_pis = [
            str(exibicao_pis.get("observacao") or "O tratamento depende do produto e da operação."),
            "",
            f"Status nacional: {piscofins.get('status') or 'não confirmado'}.",
            f"Regime de apuração: {piscofins.get('regime_apuracao') or 'não informado'}.",
            f"Fundamento: {piscofins.get('fundamento') or piscofins_mono.get('fundamento') or 'revisar'} — "
            f"{piscofins.get('artigo') or piscofins_mono.get('artigo') or 'revisar'}.",
            (
                "A ausência nos Anexos I e II da Lei nº 10.485/2002 não significa NCM inexistente; "
                "o motor continua para a regra nacional padrão do regime quando houver contexto suficiente."
            ),
        ]
        codigo_fonte_pis = (
            "PLANALTO_L10485"
            if bool(piscofins_mono.get("confirmado")) or bool(exibicao_pis.get("condicional_ex_tipi"))
            else "RFB_PISCOFINS"
        )
        self._adicionar(
            "piscofins",
            "PIS e COFINS",
            situacao_pis,
            codigo_fonte_pis,
            "\n".join(detalhe_pis),
        )

        primeiro = self.tree.get_children()[0]
        self.tree.selection_set(primeiro)
        self.tree.focus(primeiro)
        self._mostrar_detalhes()

    def _mostrar_detalhes(self, _evento=None) -> None:
        selecionado = self.tree.selection()
        if not selecionado:
            return
        detalhe = self.detalhes.get(selecionado[0], "Sem detalhes.")
        self.texto.configure(state=tk.NORMAL)
        self.texto.delete("1.0", tk.END)
        self.texto.insert("1.0", detalhe)
        self.texto.configure(state=tk.DISABLED)

    def _abrir_fonte(self) -> None:
        selecionado = self.tree.selection()
        url = self.urls.get(selecionado[0], "") if selecionado else ""
        if not url:
            messagebox.showinfo("FiscalPro", "A fonte oficial ainda não possui link cadastrado.", parent=self)
            return
        webbrowser.open_new_tab(url)


class JanelaFichaTributaria(tk.Toplevel):
    """Ficha Inteligente Simplificada — Sprint 13.7.

    A tela principal mostra somente o contexto necessário e o resultado fiscal
    essencial. Cadastros, versionamento, legislação e Reforma Tributária
    permanecem disponíveis no botão de detalhes técnicos.
    """

    def __init__(
        self,
        master=None,
        ficha: Optional[FichaTributaria] = None,
        contexto: Optional[Dict[str, Any]] = None,
        ncm: str = "",
    ) -> None:
        super().__init__(master)
        self.ficha_inicial = ficha
        self.contexto_inicial = dict(contexto or {})
        self.dados_ficha: Dict[str, Any] = {}
        self.parecer = None
        self.ncm_atual = ""
        # 17.8.115 — mantém a descrição real pesquisada para o motor de ST.
        # Antes, após resolver o NCM, a tela descartava o texto digitado e
        # consultava apenas a descrição genérica do catálogo NCM.
        self.descricao_consulta_atual = ""

        self.title("FiscalPro — Ficha Inteligente Simplificada")
        dimensionar_janela(self, 1240, 840, 880, 580)

        pesquisa_inicial = ncm or (ficha.ncm if ficha else "")
        self.pesquisa_var = tk.StringVar(value=pesquisa_inicial)
        empresa_inicial = self.contexto_inicial.get("empresa") or "Todas as empresas"
        empresa_especifica = empresa_inicial not in {"", "Todas as empresas"}
        regime_inicial = (
            EmpresasRegimesService.resolver_regime(
                empresa_inicial, self.contexto_inicial.get("regime") or ""
            )
            if empresa_especifica
            else ""
        )
        self.empresa_var = tk.StringVar(value=empresa_inicial)
        self.operacao_var = tk.StringVar(value=self.contexto_inicial.get("operacao") or "SAÍDA")
        self.regime_var = tk.StringVar(
            value=regime_inicial if empresa_especifica else "SELECIONE UMA EMPRESA"
        )
        self.regime_info_var = tk.StringVar(
            value=(
                EmpresasRegimesService.descricao_regime(empresa_inicial, regime_inicial)
                if empresa_especifica
                else "Selecione uma empresa para definir o regime e calcular PIS/COFINS."
            )
        )
        self.contexto_st_var = tk.StringVar(value="ICMS-ST: aguardando análise.")
        self.uf_origem_var = tk.StringVar(value=self.contexto_inicial.get("uf_origem") or "MG")
        self.uf_destino_var = tk.StringVar(
            value=self.contexto_inicial.get("uf_destino") or self.contexto_inicial.get("uf") or "MG"
        )
        self.origem_mercadoria_var = tk.StringVar(
            value=self.contexto_inicial.get("origem_mercadoria") or "NÃO INFORMADA"
        )
        self.finalidade_automotiva_var = tk.StringVar(
            value=self.contexto_inicial.get("finalidade_automotiva")
            or "NÃO INFORMADA — MANTER CONDICIONAL"
        )
        self.status_var = tk.StringVar(value="Informe o NCM ou a descrição do produto e clique em Analisar.")
        self.resultado_status_var = tk.StringVar(value="AGUARDANDO ANÁLISE")
        self.identificacao_var = tk.StringVar(value="Nenhum produto analisado.")
        self.descricao_var = tk.StringVar(value="A Ficha mostrará somente CFOP e tributos essenciais.")
        self.resumo_revisao_var = tk.StringVar(
            value="Faça a análise para o FiscalPro separar o que está confirmado do que ainda precisa de conferência."
        )
        self.resumo_cards_vars = {
            "piscofins": (tk.StringVar(value="Aguardando"), tk.StringVar(value="PIS e COFINS")),
            "st": (tk.StringVar(value="Aguardando"), tk.StringVar(value="ICMS-ST / CEST / MVA")),
            "icms_cfop": (tk.StringVar(value="Aguardando"), tk.StringVar(value="ICMS próprio e CFOP")),
            "ipi": (tk.StringVar(value="Aguardando"), tk.StringVar(value="TIPI x operação")),
            "seguranca": (tk.StringVar(value="Aguardando"), tk.StringVar(value="Segurança geral")),
        }
        self.resumo_cards_widgets: Dict[str, Dict[str, tk.Widget]] = {}

        self._criar_interface()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.entry_pesquisa.bind("<Return>", lambda _e: self.analisar())
        self.entry_pesquisa.bind("<KP_Enter>", lambda _e: self.analisar())

        if pesquisa_inicial.strip():
            self.after(120, self.analisar)

    # ------------------------------------------------------------------
    # Interface simplificada
    # ------------------------------------------------------------------
    def _criar_card_resumo(self, master: tk.Misc, chave: str, titulo: str, coluna: int) -> None:
        card = tk.Frame(
            master,
            bg="#FFFFFF",
            highlightthickness=1,
            highlightbackground="#DCE5EF",
            padx=9,
            pady=6,
        )
        card.grid(row=0, column=coluna, sticky="nsew", padx=4, pady=3)
        barra = tk.Frame(card, bg="#94A3B8", height=3)
        barra.pack(fill=tk.X, pady=(0, 5))
        tk.Label(
            card, text=titulo, bg="#FFFFFF", fg="#64748B",
            font=("Segoe UI", 8, "bold"), anchor="w"
        ).pack(fill=tk.X)
        valor_var, detalhe_var = self.resumo_cards_vars[chave]
        valor = tk.Label(
            card, textvariable=valor_var, bg="#FFFFFF", fg="#1E293B",
            font=("Segoe UI", 10, "bold"), anchor="w", justify=tk.LEFT, wraplength=215
        )
        valor.pack(fill=tk.X, pady=(2, 1))
        tk.Label(
            card, textvariable=detalhe_var, bg="#FFFFFF", fg="#64748B",
            font=("Segoe UI", 8), anchor="w", justify=tk.LEFT, wraplength=215
        ).pack(fill=tk.X)
        self.resumo_cards_widgets[chave] = {"barra": barra, "valor": valor}

    def _atualizar_card_resumo(self, chave: str, valor: str, detalhe: str, estado: str = "info") -> None:
        valor_var, detalhe_var = self.resumo_cards_vars[chave]
        valor_var.set(valor)
        detalhe_var.set(detalhe)
        cores = {
            "confirmado": ("#2E7D32", "#1F6B24"),
            "revisar": ("#E59A13", "#8A5B00"),
            "manual": ("#2563A8", "#1D4F8C"),
            "erro": ("#C83E4D", "#9F2533"),
            "info": ("#94A3B8", "#1E293B"),
        }
        barra_cor, texto_cor = cores.get(estado, cores["info"])
        widgets = self.resumo_cards_widgets.get(chave) or {}
        if widgets.get("barra") is not None:
            widgets["barra"].configure(bg=barra_cor)
        if widgets.get("valor") is not None:
            widgets["valor"].configure(fg=texto_cor)

    def _criar_interface(self) -> None:
        # 17.8.30: a tela pode ser aberta já com uma empresa específica
        # pela Central Tributária. Recalcula este estado aqui, no próprio
        # escopo da construção da interface, para não depender de variável
        # local do __init__ e evitar a janela ficar montada pela metade.
        empresa_atual = self.empresa_var.get().strip()
        empresa_especifica = empresa_atual not in {"", "Todas as empresas"}

        tela_baixa = self.winfo_screenheight() <= 820

        # 17.8.71: o cabeçalho e o formulário precisam deixar uma área útil
        # mínima para os cartões do resumo em notebooks de 1366x768.
        cabecalho = tk.Frame(self, bg="#1F4E78", height=62)
        cabecalho.pack(fill=tk.X)
        tk.Label(
            cabecalho,
            text="Ficha Inteligente Simplificada",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=20, pady=(7, 0))
        tk.Label(
            cabecalho,
            text="Pesquise, escolha a operação e veja a resposta fiscal sem excesso de campos. Digite o NCM e pressione Enter para analisar.",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=22)

        consulta = ttk.LabelFrame(self, text="1. Produto e operação", padding=(10, 7))
        consulta.pack(fill=tk.X, padx=14, pady=(8, 5))

        ttk.Label(consulta, text="NCM ou descrição do produto  •  Enter = analisar", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 2)
        )
        self.entry_pesquisa = ttk.Entry(consulta, textvariable=self.pesquisa_var, font=("Segoe UI", 11))
        self.entry_pesquisa.grid(row=1, column=0, columnspan=3, sticky="ew", padx=(0, 10))
        ttk.Button(consulta, text="🔎 ANALISAR TRIBUTAÇÃO", command=self.analisar).grid(
            row=1, column=3, sticky="ew", ipadx=8, ipady=2
        )

        ttk.Label(consulta, text="Empresa", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=(7, 2))
        self.combo_empresa = ttk.Combobox(
            consulta,
            textvariable=self.empresa_var,
            state="readonly",
            values=EmpresasRegimesService.listar_empresas(incluir_todas=True),
        )
        self.combo_empresa.grid(row=3, column=0, sticky="ew", padx=(0, 10))
        self.combo_empresa.bind("<<ComboboxSelected>>", self._empresa_alterada)

        ttk.Label(consulta, text="Operação", font=("Segoe UI", 9, "bold")).grid(row=2, column=1, sticky="w", pady=(7, 2))
        ttk.Combobox(
            consulta,
            textvariable=self.operacao_var,
            state="readonly",
            values=("ENTRADA", "SAÍDA", "DEVOLUÇÃO", "TRANSFERÊNCIA", "IMPORTAÇÃO", "EXPORTAÇÃO"),
        ).grid(row=3, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(consulta, text="Regime", font=("Segoe UI", 9, "bold")).grid(row=2, column=2, sticky="w", pady=(7, 2))
        self.combo_regime = ttk.Combobox(
            consulta,
            textvariable=self.regime_var,
            state="readonly" if empresa_especifica else "disabled",
            values=("SIMPLES NACIONAL", "LUCRO PRESUMIDO", "LUCRO REAL", "MEI", "OUTRO"),
        )
        self.combo_regime.grid(row=3, column=2, sticky="ew", padx=(0, 10))

        ttk.Label(consulta, text="Origem da mercadoria", font=("Segoe UI", 9, "bold")).grid(row=2, column=3, sticky="w", pady=(7, 2))
        ttk.Combobox(
            consulta,
            textvariable=self.origem_mercadoria_var,
            state="readonly",
            values=("NÃO INFORMADA", "NACIONAL", "IMPORTADA"),
        ).grid(row=3, column=3, sticky="ew")

        ttk.Label(consulta, text="UF de origem", font=("Segoe UI", 9, "bold")).grid(row=4, column=0, sticky="w", pady=(7, 2))
        ttk.Combobox(consulta, textvariable=self.uf_origem_var, state="readonly", values=_UFS[2:]).grid(
            row=5, column=0, sticky="ew", padx=(0, 10)
        )
        ttk.Label(consulta, text="UF de destino", font=("Segoe UI", 9, "bold")).grid(row=4, column=1, sticky="w", pady=(7, 2))
        ttk.Combobox(consulta, textvariable=self.uf_destino_var, state="readonly", values=_UFS[2:]).grid(
            row=5, column=1, sticky="ew", padx=(0, 10)
        )
        ttk.Label(
            consulta,
            text="Aplicação da peça (ICMS-ST e PIS/COFINS)",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=4, column=2, columnspan=2, sticky="w", pady=(7, 2))
        self.combo_finalidade_automotiva = ttk.Combobox(
            consulta,
            textvariable=self.finalidade_automotiva_var,
            state="readonly",
            values=(
                "NÃO INFORMADA — MANTER CONDICIONAL",
                "PEÇA/COMPONENTE/ACESSÓRIO DE MOTO",
                "NÃO É PEÇA AUTOMOTIVA",
            ),
        )
        self.combo_finalidade_automotiva.grid(
            row=5, column=2, columnspan=2, sticky="ew"
        )
        ttk.Label(
            consulta,
            textvariable=self.regime_info_var,
            foreground="#1F4E78",
            font=("Segoe UI", 8, "bold"),
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(5, 0))
        ttk.Label(
            consulta,
            textvariable=self.contexto_st_var,
            foreground="#555555",
            font=("Segoe UI", 8),
        ).grid(row=6, column=3, sticky="e", pady=(5, 0))

        for coluna in range(4):
            consulta.columnconfigure(coluna, weight=1)

        resultado = ttk.LabelFrame(self, text="2. Resultado tributário", padding=(12, 8))

        topo_resultado = ttk.Frame(resultado)
        topo_resultado.pack(fill=tk.X, pady=(0, 5))
        self.lbl_resultado_status = tk.Label(
            topo_resultado,
            textvariable=self.resultado_status_var,
            bg="#D9EAD3",
            fg="#274E13",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=3,
        )
        self.lbl_resultado_status.pack(side=tk.LEFT)
        ttk.Label(topo_resultado, textvariable=self.identificacao_var, font=("Segoe UI", 11, "bold")).pack(
            side=tk.LEFT, padx=12
        )

        ttk.Label(resultado, textvariable=self.descricao_var, wraplength=1040).pack(anchor="w", pady=(0, 5))

        abas_resultado = ttk.Notebook(resultado)
        abas_resultado.pack(fill=tk.BOTH, expand=True)
        aba_resumo = ttk.Frame(abas_resultado, padding=(6, 4))
        aba_detalhes = ttk.Frame(abas_resultado, padding=8)
        abas_resultado.add(aba_resumo, text="  Resumo da análise  ")
        abas_resultado.add(aba_detalhes, text="  Detalhes técnicos  ")

        cards = tk.Frame(aba_resumo, bg="#F3F6FA")
        cards.pack(fill=tk.X)
        for coluna in range(5):
            cards.columnconfigure(coluna, weight=1, uniform="resumo")
        self._criar_card_resumo(cards, "piscofins", "PIS / COFINS", 0)
        self._criar_card_resumo(cards, "st", "ICMS-ST", 1)
        self._criar_card_resumo(cards, "icms_cfop", "ICMS / CFOP", 2)
        self._criar_card_resumo(cards, "ipi", "IPI", 3)
        self._criar_card_resumo(cards, "seguranca", "SEGURANÇA", 4)

        revisar = tk.Frame(
            aba_resumo, bg="#FFF9E8", highlightthickness=1, highlightbackground="#F0D58A",
            padx=9, pady=5
        )
        revisar.pack(fill=tk.X, padx=4, pady=(5, 3))
        tk.Label(
            revisar, text="O que revisar antes de aplicar", bg="#FFF9E8", fg="#7F6000",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w")
        tk.Label(
            revisar, textvariable=self.resumo_revisao_var, bg="#FFF9E8", fg="#5F4B16",
            font=("Segoe UI", 9), justify=tk.LEFT, anchor="w", wraplength=1080
        ).pack(fill=tk.X, pady=(2, 0))

        dica = tk.Frame(aba_resumo, bg="#EAF2F8", padx=12, pady=9)
        if not tela_baixa:
            dica.pack(fill=tk.X, padx=5, pady=(0, 4))
        tk.Label(
            dica,
            text="Os cartões mostram a decisão principal. Abra “Detalhes técnicos” para ver observações, indicadores independentes e fundamentação completa.",
            bg="#EAF2F8", fg="#1F4E78", font=("Segoe UI", 9), justify=tk.LEFT, anchor="w", wraplength=1080
        ).pack(fill=tk.X)

        corpo = ttk.Panedwindow(aba_detalhes, orient=tk.HORIZONTAL)
        corpo.pack(fill=tk.BOTH, expand=True)

        quadro = ttk.Frame(corpo)
        explicacao = ttk.Frame(corpo)
        corpo.add(quadro, weight=3)
        corpo.add(explicacao, weight=2)

        self.tree_resultado = ttk.Treeview(
            quadro,
            columns=("campo", "resultado", "observacao"),
            show="headings",
            height=16,
        )
        self.tree_resultado.heading("campo", text="Campo")
        self.tree_resultado.heading("resultado", text="Resultado")
        self.tree_resultado.heading("observacao", text="Observação")
        self.tree_resultado.column("campo", width=150, stretch=False)
        self.tree_resultado.column("resultado", width=250)
        self.tree_resultado.column("observacao", width=310)
        barra_tree = ttk.Scrollbar(quadro, orient=tk.VERTICAL, command=self.tree_resultado.yview)
        self.tree_resultado.configure(yscrollcommand=barra_tree.set)
        self.tree_resultado.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        barra_tree.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(explicacao, text="Explicação e alertas", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.texto_explicacao = tk.Text(
            explicacao,
            wrap=tk.WORD,
            height=16,
            font=("Segoe UI", 9),
            padx=8,
            pady=8,
        )
        barra_texto = ttk.Scrollbar(explicacao, orient=tk.VERTICAL, command=self.texto_explicacao.yview)
        self.texto_explicacao.configure(yscrollcommand=barra_texto.set)
        self.texto_explicacao.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(5, 0))
        barra_texto.pack(side=tk.RIGHT, fill=tk.Y, pady=(5, 0))
        self.tree_resultado.bind("<Double-1>", lambda _e: self.abrir_detalhes_tecnicos_ampliados())
        self.texto_explicacao.bind("<Double-1>", lambda _e: self.abrir_detalhes_tecnicos_ampliados())
        self._definir_texto_explicacao(
            "A análise explicará por que a regra foi escolhida e indicará o que ainda precisa de conferência."
        )

        acoes = ttk.Frame(self, padding=(14, 4, 14, 8))
        ttk.Button(acoes, text="📚 Ver base legal", command=self.abrir_base_legal).pack(side=tk.LEFT)
        ttk.Button(acoes, text="🧮 Calcular ICMS-ST", command=self.abrir_calculadora_icms_st).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(acoes, text="📄 XML → Planilha ST", command=self.abrir_xml_icms_st).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(acoes, text="💾 Salvar ficha", command=self.salvar_ficha).pack(side=tk.LEFT, padx=(8, 0))
        self.botao_favorito = ttk.Button(acoes, text="☆ Favoritar NCM", command=self.alternar_favorito)
        self.botao_favorito.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_revisar_tributacao = ttk.Button(
            acoes,
            text="✏ Revisar / editar tributação",
            command=self.revisar_tributacao_manual,
            state=tk.DISABLED,
        )
        self.btn_revisar_tributacao.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            acoes,
            text="⛶ Ampliar detalhes",
            command=self.abrir_detalhes_tecnicos_ampliados,
        ).pack(side=tk.LEFT, padx=(8, 0))

        mais = ttk.Menubutton(acoes, text="Mais opções ▾")
        menu_mais = tk.Menu(mais, tearoff=False)
        menu_mais.add_command(label="Atualizar tabela ST/MG", command=self.atualizar_st_mg_oficial)
        menu_mais.add_command(label="Atualizar bases oficiais", command=self.atualizar_fontes_oficiais)
        menu_mais.add_separator()
        menu_mais.add_command(label="Comparar com SPED", command=self.comparar_com_sped)
        menu_mais.add_command(label="Gerar parecer", command=self.gerar_parecer)
        menu_mais.add_command(label="Ver detalhes tributários", command=self.abrir_detalhes)
        menu_mais.add_separator()
        menu_mais.add_command(label="Limpar consulta", command=self.limpar)
        mais.configure(menu=menu_mais)
        mais.pack(side=tk.RIGHT)

        barra_status = tk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            bg="#EAF2F8",
            fg="#1F1F1F",
            padx=12,
            pady=6,
        )
        # Rodapé reservado antes da área expansível. Assim os botões nunca
        # ficam escondidos quando a janela é maximizada ou tem pouca altura.
        barra_status.pack(fill=tk.X, side=tk.BOTTOM)
        acoes.pack(fill=tk.X, side=tk.BOTTOM)
        resultado.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 5))

    # ------------------------------------------------------------------
    # Consulta e decisão
    # ------------------------------------------------------------------
    def _empresa_alterada(self, _evento=None) -> None:
        empresa = self.empresa_var.get().strip()
        if empresa in {"", "Todas as empresas"}:
            self.regime_var.set("SELECIONE UMA EMPRESA")
            self.regime_info_var.set(
                "Selecione uma empresa para definir o regime e calcular PIS/COFINS."
            )
            self.combo_regime.configure(state="disabled")
            return

        perfil = EmpresasRegimesService.obter_perfil(empresa)
        if perfil is not None:
            self.regime_var.set(perfil.regime)
            self.combo_regime.configure(state="readonly")
            self.regime_info_var.set(
                EmpresasRegimesService.descricao_regime(empresa, perfil.regime)
            )
            return

        # Empresa sem perfil central: permite informar o regime manualmente.
        self.combo_regime.configure(state="readonly")
        regime_atual = self.regime_var.get().strip()
        if regime_atual == "SELECIONE UMA EMPRESA":
            regime_atual = ""
            self.regime_var.set("")
        self.regime_info_var.set(
            EmpresasRegimesService.descricao_regime(empresa, regime_atual)
            if regime_atual
            else "Empresa sem perfil fiscal central: selecione o regime antes de analisar."
        )

    @staticmethod
    def _mesclar_empresas(empresas_ficha: Iterable[str]) -> List[str]:
        saida = list(EmpresasRegimesService.listar_empresas(incluir_todas=True))
        vistos = {item.casefold() for item in saida}
        for nome in empresas_ficha:
            texto = str(nome or "").strip()
            if texto and texto.casefold() not in vistos:
                saida.append(texto)
                vistos.add(texto.casefold())
        return saida

    def alternar_favorito(self) -> None:
        if not self.ncm_atual:
            messagebox.showwarning("FiscalPro", "Analise um NCM antes de favoritar.", parent=self)
            return
        novo_status = not FichaTributariaRepository.eh_favorito(self.ncm_atual)
        FichaTributariaRepository.definir_favorito(self.ncm_atual, novo_status)
        if self.dados_ficha is not None:
            self.dados_ficha["favorito"] = novo_status
        FichaTributariaRepository.registrar_historico(
            self.ncm_atual,
            evento="FAVORITO" if novo_status else "FAVORITO REMOVIDO",
            campo="NCM favorito",
            valor_novo="Sim" if novo_status else "Não",
            origem="Ficha Inteligente Simplificada",
        )
        self._atualizar_botao_favorito()
        self.status_var.set(
            f"NCM {self.ncm_atual} adicionado aos favoritos." if novo_status
            else f"NCM {self.ncm_atual} removido dos favoritos."
        )

    def _atualizar_botao_favorito(self) -> None:
        if not hasattr(self, "botao_favorito"):
            return
        favorito = bool(self.ncm_atual and FichaTributariaRepository.eh_favorito(self.ncm_atual))
        self.botao_favorito.configure(
            text="★ Remover favorito" if favorito else "☆ Favoritar NCM"
        )

    def _resolver_ncm(self) -> str:
        termo = self.pesquisa_var.get().strip()
        if not termo:
            raise ValueError("Informe o NCM ou a descrição do produto.")

        digitos = "".join(c for c in termo if c.isdigit())
        if len(digitos) == 8 and not any(c.isalpha() for c in termo):
            return FichaTributariaRepository.normalizar_ncm(digitos)

        unicos = NCMDescricaoService.pesquisar(termo, limite=60)

        if not unicos:
            raise ValueError(
                "Nenhum NCM foi encontrado para essa descrição. Informe um pouco mais de detalhe "
                "sobre material/aplicação ou digite o NCM com 8 dígitos."
            )
        if len(unicos) == 1:
            return unicos[0][0]

        seletor = _SeletorNCM(self, unicos)
        self.wait_window(seletor)
        if not seletor.resultado:
            raise ValueError("A seleção do produto foi cancelada.")
        return seletor.resultado

    def _contexto(self) -> Dict[str, str]:
        empresa = self.empresa_var.get().strip()
        empresa_contexto = "" if empresa in {"", "Todas as empresas"} else empresa
        regime_informado = self.regime_var.get().strip()
        if regime_informado == "SELECIONE UMA EMPRESA":
            regime_informado = ""
        regime = EmpresasRegimesService.resolver_regime(empresa_contexto, regime_informado)
        if regime:
            self.regime_var.set(regime)
            self.regime_info_var.set(EmpresasRegimesService.descricao_regime(empresa_contexto, regime))
        return {
            "empresa": empresa_contexto,
            "regime": regime or self.regime_var.get().strip(),
            "operacao": self.operacao_var.get().strip(),
            "finalidade": "REVENDA",
            "uf_origem": self.uf_origem_var.get().strip(),
            "uf_destino": self.uf_destino_var.get().strip(),
            "contribuinte": "TODOS",
            "data_operacao": date.today().isoformat(),
            "origem_mercadoria": self.origem_mercadoria_var.get().strip(),
            "finalidade_automotiva": self.finalidade_automotiva_var.get().strip(),
        }

    def analisar(self) -> None:
        empresa_selecionada = self.empresa_var.get().strip()
        if empresa_selecionada in {"", "Todas as empresas"}:
            messagebox.showwarning(
                "FiscalPro",
                "Selecione uma empresa antes de analisar. O regime tributário e as alíquotas de PIS/COFINS dependem da empresa escolhida.",
                parent=self,
            )
            self.combo_empresa.focus_set()
            return

        termo_pesquisado = self.pesquisa_var.get().strip()
        try:
            ncm = self._resolver_ncm()
        except ValueError as erro:
            if "cancelada" not in str(erro).lower():
                messagebox.showwarning("FiscalPro", str(erro), parent=self)
            self.entry_pesquisa.focus_set()
            return

        self.status_var.set(f"Analisando o NCM {ncm}...")
        self.resultado_status_var.set("ANALISANDO")
        self.update_idletasks()

        try:
            empresa_selecionada = self.empresa_var.get().strip()
            empresa = "" if empresa_selecionada in {"", "Todas as empresas"} else empresa_selecionada
            self.dados_ficha = FichaTributariaRepository.carregar_ficha(ncm, empresa=empresa)
            dados_gerais_consulta = self.dados_ficha.get("dados_gerais", {})
            descricao_cadastro = str(dados_gerais_consulta.get("descricao") or "").strip()
            if any(c.isalpha() for c in termo_pesquisado):
                # A descrição digitada representa o produto concreto e é mais
                # adequada para testar aderência à descrição legal do CEST.
                self.descricao_consulta_atual = termo_pesquisado
            elif self.ncm_atual == ncm and self.descricao_consulta_atual:
                # Reanálise após mudar UF/aplicação: não perca a descrição que
                # originou a consulta só porque o campo já foi convertido em NCM.
                pass
            else:
                self.descricao_consulta_atual = descricao_cadastro
            self.consulta_oficial = ConsultaOficialService.consultar(
                ncm,
                contexto=self._contexto(),
                descricao=self.descricao_consulta_atual,
                ex_tipi=str(dados_gerais_consulta.get("ex_tipi") or ""),
            )
            self.ncm_atual = ncm
            self.pesquisa_var.set(ncm)

            empresas = self._mesclar_empresas(self.dados_ficha.get("empresas", []))
            self.combo_empresa.configure(values=empresas)
            if self.empresa_var.get() not in empresas:
                self.empresa_var.set("Todas as empresas")
            self._empresa_alterada()

            dados_gerais = self.dados_ficha.get("dados_gerais", {})
            if not dados_gerais.get("encontrado") and self.ficha_inicial and self.ficha_inicial.ncm == ncm:
                self.parecer = MotorParecer.gerar(self.ficha_inicial, self._contexto())
            else:
                self.parecer = MotorParecer.gerar(self.dados_ficha, self._contexto())

            self.parecer = ConsultaOficialService.aplicar_fontes_ao_parecer(
                self.parecer, self.consulta_oficial
            )
            self._preencher_resultado()
            self.btn_revisar_tributacao.configure(state=tk.NORMAL)
            self._atualizar_botao_favorito()
            FichaTributariaRepository.registrar_consulta_recente(
                ncm=ncm,
                descricao=str(getattr(self.parecer, "descricao", "") or dados_gerais.get("descricao") or ""),
                empresa=self.empresa_var.get().strip(),
                regime=self.regime_var.get().strip(),
                operacao=self.operacao_var.get().strip(),
                uf_origem=self.uf_origem_var.get().strip(),
                uf_destino=self.uf_destino_var.get().strip(),
            )
            self.status_var.set(f"Análise do NCM {ncm} concluída.")
        except Exception as erro:
            self.resultado_status_var.set("ERRO NA ANÁLISE")
            self.lbl_resultado_status.configure(bg="#F4CCCC", fg="#990000")
            self.status_var.set("Não foi possível concluir a análise.")
            messagebox.showerror("FiscalPro", f"Erro ao analisar a tributação:\n{erro}", parent=self)

    def _preencher_resultado(self) -> None:
        if self.parecer is None:
            return
        for item in self.tree_resultado.get_children():
            self.tree_resultado.delete(item)

        p = self.parecer
        t = p.tributacao_atual
        gerais = p.dados_gerais
        revisao_manual = bool(t.get("Revisão manual"))
        ncm_oficial = bool(self.consulta_oficial.get("ncm_confirmado"))
        revisao_exibicao = ConsultaOficialService.revisao_para_exibicao(
            self.consulta_oficial, p, t, self._contexto()
        )
        precisa_revisar = bool(revisao_exibicao.get("precisa_revisar"))

        if revisao_manual:
            self.resultado_status_var.set("ANÁLISE CONCLUÍDA — REGRA MANUAL")
            self.lbl_resultado_status.configure(bg="#D9EAF7", fg="#134F5C")
        elif precisa_revisar:
            motivos = str(revisao_exibicao.get("texto_curto") or "PONTOS INDICADOS")
            self.resultado_status_var.set(f"ANÁLISE CONCLUÍDA — REVISAR: {motivos}")
            self.lbl_resultado_status.configure(bg="#FFF2CC", fg="#7F6000")
        else:
            self.resultado_status_var.set("ANÁLISE CONCLUÍDA — CONFIRMADA")
            self.lbl_resultado_status.configure(bg="#D9EAD3", fg="#274E13")

        cest_base = t.get("CEST") if revisao_manual and self._texto(t.get("CEST")) != "Não informado" else gerais.get("CEST")
        self.descricao_var.set(
            self.descricao_consulta_atual or p.descricao or "Descrição não cadastrada"
        )

        ipi_oficial = ConsultaOficialService.texto_ipi(self.consulta_oficial)
        piscofins_oficial = dict(self.consulta_oficial.get("piscofins_nacional") or {})
        piscofins_mono = dict(self.consulta_oficial.get("piscofins_monofasico") or {})
        monofasico_excluido = bool(piscofins_mono.get("exclusao_confirmada"))
        destinacao_monofasico = str(piscofins_mono.get("destinacao_identificada") or "").strip()
        piscofins_exibicao = ConsultaOficialService.piscofins_para_exibicao(
            self.consulta_oficial, t
        )
        icms_exibicao = ConsultaOficialService.icms_para_exibicao(
            self.consulta_oficial, t
        )
        piscofins_confirmado = bool(piscofins_exibicao.get("confirmado"))
        st_oficial = ConsultaOficialService.st_contextual(self.consulta_oficial)
        icms_oficial = ConsultaOficialService.icms_contextual(self.consulta_oficial)

        # A rota exibida na ficha deve refletir SEMPRE o que está selecionado
        # nos campos da própria tela. Não reutilize rótulos de uma consulta
        # anterior nem derive o destino do motor de ST para montar o texto
        # "origem→destino". O motor continua sendo a fonte dos valores; estes
        # dois campos são a fonte do rótulo da rota consultada.
        contexto_atual = self._contexto()
        uf_origem_exibicao = str(
            self.uf_origem_var.get() or contexto_atual.get("uf_origem") or "-"
        ).strip().upper()
        uf_destino_exibicao = str(
            self.uf_destino_var.get() or contexto_atual.get("uf_destino") or "MG"
        ).strip().upper()
        uf_icms = str(
            st_oficial.get("uf") or icms_oficial.get("uf") or uf_destino_exibicao
        ).strip().upper()
        st_encontrado = bool(st_oficial.get("encontrado"))
        st_confirmado = bool(st_oficial.get("confirmado"))
        st_decisao_confirmada = bool(st_oficial.get("decisao_confirmada"))
        decisao_st = str(st_oficial.get("decisao_st") or "").strip().upper()
        st_nao_aplicavel = bool(st_oficial.get("nao_aplicavel")) or decisao_st == "NAO"
        # 17.8.76 — alguns motores estaduais antigos confirmam a ST por
        # `confirmado=True` + `decisao_st=SIM`, sem preencher o campo
        # auxiliar `decisao_confirmada`. Para a interface, os dois formatos
        # representam a mesma decisão fiscal confirmada.
        st_resultado_confirmado = self._st_confirmado_para_exibicao(st_oficial)
        st_condicional = decisao_st == "CONDICIONAL"
        st_somente_sugerido = st_condicional and not st_encontrado
        cest_sugerido = str(st_oficial.get("cest_sugerido") or "").strip()
        mva_sugerida = st_oficial.get("mva_sugerida")

        # 17.8.74 — o cabeçalho deve distinguir CEST confirmado de CEST apenas
        # sugerido pelo enquadramento residual. Assim o Resumo e os Detalhes
        # Técnicos não parecem discordar entre si.
        cest_confirmado = str(cest_base or "").strip()
        cest_confirmado_texto = self._texto(cest_confirmado) if cest_confirmado else "Não informado"
        if not revisao_manual and st_nao_aplicavel and not cest_confirmado:
            cest_exibicao = "NÃO APLICÁVEL"
        elif (
            not revisao_manual
            and st_somente_sugerido
            and cest_sugerido
            and cest_confirmado_texto in {"Não informado", "Não informada", "Não localizada"}
        ):
            cest_exibicao = f"{self._formatar_cest_exibicao(cest_sugerido)} (possível)"
        else:
            cest_exibicao = self._formatar_cest_exibicao(cest_confirmado)
        sufixo_manual = "  •  ALTERAÇÃO MANUAL" if revisao_manual else ""
        self.identificacao_var.set(f"NCM {p.ncm}  •  CEST {cest_exibicao}{sufixo_manual}")

        # O aviso de contexto deve refletir o resultado atual e nunca manter
        # a mensagem genérica "NCM não listado" quando o próprio motor já
        # confirmou um enquadramento de ICMS-ST.
        if revisao_manual:
            self.contexto_st_var.set("ICMS-ST: regra manual aplicada.")
        elif st_nao_aplicavel:
            aplicabilidade_st = str(st_oficial.get("aplicabilidade_segmento") or "").strip().upper()
            if aplicabilidade_st in {
                "NCM_FORA_ANEXO_VII_PARTE_2",
                "NCM_AUSENTE_BASE_OFICIAL_COMPLETA",
            }:
                atualizado = str(st_oficial.get("base_st_atualizada_em") or "").strip()
                sufixo_base = f" • base sincronizada {atualizado[:10]}" if atualizado else ""
                self.contexto_st_var.set(
                    f"ICMS-ST {uf_icms}: NÃO — NCM fora da Parte 2 do Anexo VII{sufixo_base}."
                )
            else:
                self.contexto_st_var.set(
                    f"ICMS-ST {uf_icms}: NÃO aplicável ao produto pela descrição legal."
                )
        elif st_resultado_confirmado:
            cest_status = self._formatar_cest_exibicao(st_oficial.get("cest") or cest_confirmado)
            self.contexto_st_var.set(
                f"ICMS-ST {uf_icms} confirmado • CEST {cest_status}"
            )
        elif st_somente_sugerido:
            if not bool(st_oficial.get("base_st_completa")):
                self.contexto_st_var.set(
                    "Base ST/MG incompleta • Mais opções → Atualizar tabela ST/MG."
                )
            else:
                self.contexto_st_var.set("NCM sem enquadramento nominal: ICMS-ST condicional.")
        elif st_encontrado:
            self.contexto_st_var.set(f"ICMS-ST {uf_icms} localizado • revisar contexto da operação.")
        else:
            self.contexto_st_var.set("ICMS-ST condicional: confirmar enquadramento.")

        modelo_st = str(st_oficial.get("st_modelo_calculo") or "").strip()
        carga_liquida_st = st_oficial.get("carga_liquida_st")
        antecipacao_percentual = st_oficial.get("antecipacao_percentual")
        mva_st = st_oficial.get("mva_aplicada")
        if mva_st is None:
            mva_st = st_oficial.get("mva_original")
        mva_st_texto = (
            f"{float(mva_st):.2f}%".replace(".", ",") if mva_st is not None else "Não informada"
        )
        st_manual = str(t.get("ICMS-ST") or "").strip() if revisao_manual else ""
        cest_manual = str(t.get("CEST") or "").strip() if revisao_manual else ""
        mva_manual = self._numero(t.get("MVA ST")) if revisao_manual else None
        if mva_manual == 0:
            mva_manual = None
        mva_manual_texto = self._percentual(mva_manual) if mva_manual is not None else "Não informada"
        observacao_piscofins = str(
            piscofins_exibicao.get("observacao")
            or "Revisar o enquadramento do produto e da operação."
        )
        pisco_condicional_ex = bool(piscofins_exibicao.get("condicional_ex_tipi"))
        ex_validos_pisco = list(piscofins_exibicao.get("ex_tipi_validos") or [])
        ex_texto_pisco = ", ".join(ex_validos_pisco) or "EX aplicável"
        if pisco_condicional_ex:
            texto_pis = f"CONDICIONAL • EX {ex_texto_pisco} → CST 04 • 0,00%"
            texto_cofins = f"CONDICIONAL • EX {ex_texto_pisco} → CST 04 • 0,00%"
        else:
            texto_pis = self._tributo_com_cst(
                piscofins_exibicao.get("cst_pis"), piscofins_exibicao.get("aliquota_pis")
            )
            texto_cofins = self._tributo_com_cst(
                piscofins_exibicao.get("cst_cofins"), piscofins_exibicao.get("aliquota_cofins")
            )
            if piscofins_exibicao.get("sugerido"):
                texto_pis = "SUG. " + texto_pis
                texto_cofins = "SUG. " + texto_cofins

        cst_icms_exibicao = str(icms_exibicao.get("cst") or "").strip()
        if icms_exibicao.get("cst_definido") and cst_icms_exibicao:
            texto_icms = self._tributo_com_cst(
                cst_icms_exibicao, icms_exibicao.get("aliquota")
            )
        else:
            texto_icms = (
                "CST a definir conforme operação  •  "
                + self._percentual(icms_exibicao.get("aliquota"))
            )
        observacao_icms = str(
            icms_exibicao.get("observacao")
            or "Revise o CST/CSOSN conforme o contexto real da operação."
        )
        ipi_exibicao = ConsultaOficialService.ipi_para_exibicao(
            self.consulta_oficial, t, self._contexto()
        )
        cfop_exibicao = ConsultaOficialService.cfop_para_exibicao(
            self.consulta_oficial, self._contexto(), t
        )
        indicador_piscofins = IndicadorSegurancaTributaria.piscofins(piscofins_oficial)
        indicador_icms_proprio = IndicadorSegurancaTributaria.icms_proprio_uf(icms_oficial, uf_icms)
        indicador_icms_st = IndicadorSegurancaTributaria.icms_st_uf(st_oficial, uf_icms)
        indicador_geral = IndicadorSegurancaTributaria.geral(p)

        # Resumo visual da Central Tributária: decisão primeiro, detalhes depois.
        status_pisco = str(piscofins_exibicao.get("status") or "").strip()
        if piscofins_confirmado and "MONOFÁSICO" in status_pisco.upper():
            valor_pisco = "Monofásico • 0% / 0%"
        elif monofasico_excluido:
            valor_pisco = "NÃO MONOFÁSICO • aplicação em moto"
        elif pisco_condicional_ex:
            valor_pisco = "CONDICIONAL • confirmar EX TIPI"
        else:
            valor_pisco = (
                f"PIS {self._percentual(piscofins_exibicao.get('aliquota_pis'))} • "
                f"COFINS {self._percentual(piscofins_exibicao.get('aliquota_cofins'))}"
            )
        if pisco_condicional_ex:
            detalhe_pisco = f"EX {ex_texto_pisco} → CST 04 / 04 • 0% / 0%"
        elif monofasico_excluido:
            detalhe_pisco = (
                f"PIS {self._percentual(piscofins_exibicao.get('aliquota_pis'))} • "
                f"COFINS {self._percentual(piscofins_exibicao.get('aliquota_cofins'))} • "
                f"CST {piscofins_exibicao.get('cst_pis') or '-'} / "
                f"{piscofins_exibicao.get('cst_cofins') or '-'} • regra do regime"
            )
        else:
            detalhe_pisco = (
                f"CST {piscofins_exibicao.get('cst_pis') or '-'} / "
                f"{piscofins_exibicao.get('cst_cofins') or '-'}"
            )
        if status_pisco:
            detalhe_pisco += f" • {status_pisco}"
        self._atualizar_card_resumo(
            "piscofins", valor_pisco, detalhe_pisco,
            "manual" if revisao_manual else ("confirmado" if piscofins_confirmado else "revisar"),
        )

        if revisao_manual and st_manual:
            valor_st = f"{st_manual} • MVA {mva_manual_texto}"
            detalhe_st = f"CEST {cest_manual or 'não informado'} • regra manual"
            estado_st = "manual"
        elif st_nao_aplicavel:
            aplicabilidade_st = str(st_oficial.get("aplicabilidade_segmento") or "").strip().upper()
            if aplicabilidade_st in {
                "NCM_FORA_ANEXO_VII_PARTE_2",
                "NCM_AUSENTE_BASE_OFICIAL_COMPLETA",
            }:
                valor_st = "NÃO • fora da tabela ST/MG"
            else:
                valor_st = "NÃO • enquadramento rejeitado"
            detalhe_st = str(
                st_oficial.get("status")
                or "A mercadoria não se enquadra na regra de ICMS-ST consultada."
            )
            estado_st = "confirmado"
        elif st_confirmado and st_resultado_confirmado:
            valor_st = f"SIM • MVA {mva_st_texto}"
            detalhe_st = (
                f"CEST {self._formatar_cest_exibicao(st_oficial.get('cest'))} • confirmado em {uf_icms}"
            )
            estado_st = "confirmado"
        elif st_encontrado and antecipacao_percentual is not None:
            valor_st = f"REVISAR • Antecipação {self._percentual(antecipacao_percentual)}"
            detalhe_st = modelo_st or str(st_oficial.get("antecipacao_status") or st_oficial.get("status") or "Antecipação estadual")
            estado_st = "revisar"
        elif st_encontrado and carga_liquida_st is not None:
            valor_st = f"REVISAR • Carga líquida {self._percentual(carga_liquida_st)}"
            detalhe_st = modelo_st or str(st_oficial.get("status") or "Regra local condicional")
            estado_st = "revisar"
        elif st_encontrado and mva_st is not None:
            valor_st = f"REVISAR • MVA {mva_st_texto}"
            detalhe_st = modelo_st or str(st_oficial.get("status") or "MVA identificada; responsabilidade a confirmar")
            estado_st = "revisar"
        elif st_somente_sugerido:
            valor_st = "CONDICIONAL • confirmar finalidade"
            sugestoes = []
            if cest_sugerido:
                sugestoes.append(f"CEST possível {self._formatar_cest_exibicao(cest_sugerido)}")
            if mva_sugerida is not None:
                sugestoes.append(
                    f"MVA possível {float(mva_sugerida):.2f}%".replace(".", ",")
                )
            detalhe_st = " • ".join(sugestoes) or str(
                st_oficial.get("status") or "Revisão necessária"
            )
            estado_st = "revisar"
        else:
            valor_st = str(st_oficial.get("status") or "Revisar enquadramento")
            detalhe_st = str(st_oficial.get("observacao") or "ICMS-ST ainda não confirmado para o contexto.")
            estado_st = "revisar"
        self._atualizar_card_resumo("st", valor_st, detalhe_st, estado_st)

        motivos_revisao = [str(x).upper() for x in (revisao_exibicao.get("motivos") or [])]
        revisa_icms_cfop = any(x in {"ICMS", "CFOP", "REGRA LOCAL"} for x in motivos_revisao)
        valor_icms_cfop = (
            f"{self._percentual(icms_exibicao.get('aliquota'))} • "
            f"CFOP {cfop_exibicao.get('valor') or 'a definir'}"
        )
        detalhe_icms_cfop = (
            f"CST {cst_icms_exibicao}" if icms_exibicao.get("cst_definido") and cst_icms_exibicao
            else "CST a definir conforme a operação"
        )
        self._atualizar_card_resumo(
            "icms_cfop", valor_icms_cfop, detalhe_icms_cfop,
            "manual" if revisao_manual else ("revisar" if revisa_icms_cfop else "confirmado"),
        )

        tipi_ref = str(ipi_exibicao.get("tipi_referencia") or ipi_oficial or "Não informado")
        tratamento_ipi = str(ipi_exibicao.get("tratamento_operacao") or "Não informado")
        revisa_ipi = bool(ipi_exibicao.get("revisar_operacao"))
        self._atualizar_card_resumo(
            "ipi", f"TIPI {tipi_ref}", f"Operação: {tratamento_ipi}",
            "manual" if revisao_manual else ("revisar" if revisa_ipi else "confirmado"),
        )

        estado_geral = "manual" if revisao_manual else ("revisar" if precisa_revisar else "confirmado")
        detalhe_geral = (
            "Há pontos condicionais antes de aplicar." if precisa_revisar and not revisao_manual
            else ("Regra manual preservada." if revisao_manual else "Análise sem pendências críticas identificadas.")
        )
        self._atualizar_card_resumo(
            "seguranca", indicador_geral.resultado, detalhe_geral, estado_geral
        )

        if precisa_revisar and not revisao_manual:
            motivos = list(revisao_exibicao.get("motivos") or [])
            detalhes = list(revisao_exibicao.get("detalhes") or [])
            pares = []
            for indice, motivo in enumerate(motivos[:5]):
                detalhe = str(detalhes[indice] if indice < len(detalhes) else "").strip()
                pares.append(f"{motivo}: {detalhe}" if detalhe else str(motivo))
            self.resumo_revisao_var.set("  •  ".join(pares) or "Revise os pontos indicados no status da análise.")
        elif revisao_manual:
            self.resumo_revisao_var.set(
                "Esta ficha usa uma regra manual salva. Compare com as fontes oficiais antes de alterar o cadastro."
            )
        else:
            self.resumo_revisao_var.set(
                "Nenhuma pendência crítica foi identificada para os tributos exibidos. A base legal continua disponível para conferência."
            )

        fonte_regra_bruta = str(t.get("Fonte da regra") or "").strip()
        fonte_regra_exibicao = self._texto(fonte_regra_bruta)
        if (
            not revisao_manual
            and (
                not fonte_regra_bruta
                or fonte_regra_exibicao in {"Não informado", "Não informada", "Não localizada"}
            )
        ):
            fonte_regra_exibicao = str(st_oficial.get("fonte_nome") or "").strip()
            if not fonte_regra_exibicao:
                fonte_regra_exibicao = str(st_oficial.get("fonte_url") or "").split("|")[0].strip() or "Não informada"

        regra_aplicada_exibicao = self._texto(t.get("Regra aplicada"))
        aderencia_regra_exibicao = self._texto(t.get("Aderência ao contexto"))
        if not revisao_manual and regra_aplicada_exibicao in {"Não informado", "Não localizada"}:
            regra_aplicada_exibicao = str(
                st_oficial.get("regra_aplicada")
                or st_oficial.get("st_modelo_calculo")
                or st_oficial.get("status")
                or "Não localizada"
            ).strip()
            fundamento_contextual = str(st_oficial.get("fundamento_legal") or "").strip()
            responsabilidade_contextual = str(st_oficial.get("responsabilidade") or "").strip()
            partes_aderencia = [x for x in (fundamento_contextual, responsabilidade_contextual) if x]
            if partes_aderencia:
                aderencia_regra_exibicao = "  •  ".join(partes_aderencia)

        linhas = [
            (
                "NCM oficial",
                "Confirmado" if ncm_oficial else "Não confirmado",
                "Receita Federal / Siscomex — tabela NCM vigente.",
            ),
            (
                "TIPI — referência do NCM",
                str(ipi_exibicao.get("tipi_referencia") or ipi_oficial),
                str(ipi_exibicao.get("observacao_tipi") or ""),
            ),
            (
                "CFOP sugerido",
                str(cfop_exibicao.get("valor") or "Não informado"),
                str(cfop_exibicao.get("observacao") or "Revise o contexto da operação."),
            ),
            (
                "ICMS",
                texto_icms,
                f"{observacao_icms}  •  FCP: {self._percentual(t.get('FCP'))}",
            ),
            (
                (
                    f"ICMS interestadual {uf_origem_exibicao}→{uf_destino_exibicao}"
                    if uf_origem_exibicao != uf_destino_exibicao
                    else f"ICMS interno {uf_destino_exibicao}"
                ),
                (
                    f"{float(icms_oficial.get('aliquota_nominal')):.2f}%".replace(".", ",")
                    if icms_oficial.get("aliquota_nominal") is not None
                    else "Não analisado"
                ),
                str(icms_oficial.get("aliquota_status") or "Informe o contexto da operação."),
            ),
            (
                f"ICMS interno {uf_icms}",
                (
                    f"{float(icms_oficial.get('aliquota_interna_destino')):.2f}%".replace(".", ",")
                    if icms_oficial.get("aliquota_interna_destino") is not None
                    else (
                        f"{float(icms_oficial.get('aliquota_nominal')):.2f}%".replace(".", ",")
                        if str(self._contexto().get('uf_origem') or '').strip().upper() == uf_icms
                        and icms_oficial.get("aliquota_nominal") is not None
                        else "Não analisado"
                    )
                ),
                str(icms_oficial.get("aliquota_interna_status") or "Alíquota interna ainda não estruturada para este contexto."),
            ),
            (
                f"ICMS-ST {uf_icms}",
                (
                    (
                        f"{st_manual or 'VERIFICAR'}  •  CEST {cest_manual or 'Não informado'}  •  MVA {mva_manual_texto}"
                        if revisao_manual
                        else (
                            f"SIM  •  CEST {st_oficial.get('cest')}  •  MVA {mva_st_texto}"
                            if st_confirmado
                            else str(st_oficial.get("status") or "Não sincronizado")
                        )
                    )
                ),
                (
                    "ALTERAÇÃO MANUAL salva pelo usuário; o resultado oficial permanece disponível para comparação e não sobrescreve esta regra."
                    if revisao_manual
                    else str(st_oficial.get("aplicacao_operacao") or st_oficial.get("observacao") or "Revisar.")
                ),
            ),
            (
                f"MVA-base {uf_icms}",
                (
                    f"{float(st_oficial.get('mva_original')):.2f}%".replace(".", ",")
                    if st_oficial.get("mva_original") is not None
                    else (
                        (f"Não confirmada • possível {float(mva_sugerida):.2f}%".replace(".", ","))
                        if st_somente_sugerido and mva_sugerida is not None
                        else "Não informada"
                    )
                ),
                (
                    "Margem-base da regra estadual estruturada; não confundir com a MVA efetivamente aplicada à operação."
                    if st_oficial.get("mva_original") is not None
                    else (
                        "A MVA exibida como possível é apenas a hipótese residual automotiva; só se torna MVA-base confirmada após validar a finalidade do produto."
                        if st_somente_sugerido and mva_sugerida is not None
                        else "MVA-base não disponível para este enquadramento."
                    )
                ),
            ),
            (
                f"MVA aplicada {uf_icms}",
                (
                    f"{float(st_oficial.get('mva_aplicada')):.2f}%".replace(".", ",")
                    if st_oficial.get("mva_aplicada") is not None
                    else (
                        "Não calculada — confirmar finalidade"
                        if st_somente_sugerido and mva_sugerida is not None
                        else "Não informada"
                    )
                ),
                (
                    (str(st_oficial.get("mva_tipo") or "MVA da regra estadual") + "  •  " +
                     str(st_oficial.get("observacao") or "Revise as condições da regra estadual antes de aplicar."))
                    if st_oficial.get("mva_aplicada") is not None
                    else (
                        "A MVA possível não é aplicada ao cálculo enquanto o enquadramento residual e a finalidade automotiva não estiverem confirmados."
                        if st_somente_sugerido and mva_sugerida is not None
                        else str(st_oficial.get("observacao") or "Revise as condições da regra estadual antes de aplicar.")
                    )
                ),
            ),
            (
                f"FCP {uf_icms}",
                (
                    f"{float(((self.consulta_oficial or {}).get('icms_uf') or {}).get('fcp')):.2f}%".replace(".", ",")
                    if ((self.consulta_oficial or {}).get('icms_uf') or {}).get("fcp") is not None else "Não informado"
                ),
                (
                    str(((self.consulta_oficial or {}).get('icms_uf') or {}).get("fcp_status") or
                        "FCP ainda não confirmado para este contexto.")
                ),
            ),
            (
                "PIS/COFINS monofásico",
                (
                    f"NÃO — EXCLUSÃO CONFIRMADA • {destinacao_monofasico}"
                    if monofasico_excluido
                    else str(piscofins_mono.get("status") or "Não analisado")
                ),
                str(
                    piscofins_mono.get("observacao")
                    or "O enquadramento monofásico depende do NCM, da descrição legal e da aplicação do produto."
                ),
            ),
            ("PIS", texto_pis, observacao_piscofins),
            ("COFINS", texto_cofins, observacao_piscofins),
            (
                "IPI — tratamento da operação",
                str(ipi_exibicao.get("tratamento_operacao") or "Não informado"),
                str(ipi_exibicao.get("observacao_operacao") or ""),
            ),
            ("Benefício", self._texto(t.get("Benefício/Regime especial")), "Isenção, redução ou regime especial cadastrado."),
            (
                "Origem da regra",
                "ALTERAÇÃO MANUAL" if revisao_manual else fonte_regra_exibicao,
                "Regra manual é preservada em novas consultas; motores oficiais apenas sinalizam divergências." if revisao_manual else "Fonte oficial/contextual efetivamente usada pelo motor estadual.",
            ),
            ("Regra aplicada", regra_aplicada_exibicao, aderencia_regra_exibicao),
            (indicador_piscofins.campo, indicador_piscofins.resultado, indicador_piscofins.observacao),
            (
                indicador_icms_proprio.campo,
                indicador_icms_proprio.resultado,
                indicador_icms_proprio.observacao,
            ),
            (
                indicador_icms_st.campo,
                indicador_icms_st.resultado,
                indicador_icms_st.observacao,
            ),
            (indicador_geral.campo, indicador_geral.resultado, indicador_geral.observacao),
        ]
        if st_somente_sugerido and cest_sugerido:
            indice_cest_possivel = next(
                (i for i, linha in enumerate(linhas) if str(linha[0]).startswith("MVA-base")),
                len(linhas),
            )
            linhas[indice_cest_possivel:indice_cest_possivel] = [
                (
                    f"CEST possível {uf_icms}",
                    self._formatar_cest_exibicao(cest_sugerido),
                    "Sugestão residual condicionada à confirmação de que o item é peça, componente ou acessório automotivo. Não aplicar como CEST confirmado antes dessa validação.",
                )
            ]

        if modelo_st:
            indice_modelo = next(
                (i for i, linha in enumerate(linhas) if str(linha[0]).startswith("MVA-base")),
                len(linhas),
            )
            linhas[indice_modelo:indice_modelo] = [
                (
                    f"Modelo de cálculo ST/entrada {uf_icms}",
                    modelo_st,
                    str(st_oficial.get("status") or "Regra estadual condicionada ao contexto da operação."),
                ),
                (
                    f"Antecipação/Agregação {uf_icms}",
                    (self._percentual(antecipacao_percentual) if antecipacao_percentual is not None else "Não informada"),
                    str(st_oficial.get("antecipacao_status") or "Não se aplica antecipação estruturada neste enquadramento."),
                ),
                (
                    f"Carga líquida ST {uf_icms}",
                    (self._percentual(carga_liquida_st) if carga_liquida_st is not None else "Não informada"),
                    str(st_oficial.get("carga_liquida_status") or "Não se aplica carga líquida neste enquadramento."),
                ),
            ]

        # Evita duplicar "ICMS interno UF" quando origem e destino são iguais,
        # preservando a aba e a janela ampliada dos Detalhes técnicos.
        linhas_sem_duplicidade = []
        campos_adicionados = set()
        for linha in linhas:
            campo = str(linha[0])
            if campo in campos_adicionados:
                continue
            campos_adicionados.add(campo)
            linhas_sem_duplicidade.append(linha)

        for linha in linhas_sem_duplicidade:
            self.tree_resultado.insert("", tk.END, values=linha)

        partes = [p.resumo_executivo]
        if self.origem_mercadoria_var.get() != "NÃO INFORMADA":
            partes.append(f"Origem da mercadoria informada: {self.origem_mercadoria_var.get()}.")
        if p.conclusoes:
            partes.extend(["", "Conclusões:", *[f"• {item}" for item in p.conclusoes[:6]]])
        if precisa_revisar and not revisao_manual:
            partes.extend(["", "Revisar antes de aplicar:"])
            partes.extend(
                f"• {rotulo}: {detalhe}"
                for rotulo, detalhe in zip(
                    revisao_exibicao.get("motivos", []),
                    revisao_exibicao.get("detalhes", []),
                )
            )
        if p.alertas or p.pendencias:
            partes.extend(["", "Pontos adicionais para conferir:"])
            partes.extend(f"• {item}" for item in [*p.alertas[:5], *p.pendencias[:5]])

        partes.extend(["", "Verificação oficial:"])
        partes.append(
            "• NCM confirmado na tabela oficial da Receita Federal."
            if ncm_oficial else
            "• O NCM não foi confirmado na cópia oficial sincronizada. Atualize as bases oficiais."
        )
        if self.consulta_oficial.get("ipi_confirmado"):
            partes.append(
                f"• TIPI: referência do NCM {ipi_exibicao.get('tipi_referencia') or ipi_oficial}. "
                "Essa alíquota não é, sozinha, o IPI devido/destacado na operação."
            )
            partes.append(
                f"• IPI da operação: {ipi_exibicao.get('tratamento_operacao') or 'não informado'}. "
                "Confira a condição do estabelecimento e o enquadramento da operação."
            )
        else:
            partes.append("• A TIPI oficial ainda não foi sincronizada neste computador.")
        if cfop_exibicao.get("valor") and cfop_exibicao.get("valor") != "Não informado":
            partes.append(
                f"• CFOP: {cfop_exibicao.get('valor')} — {cfop_exibicao.get('observacao')}"
            )
        if piscofins_confirmado:
            partes.append(
                f"• PIS e COFINS: {piscofins_exibicao.get('status') or 'CONFIRMADO'} — "
                f"{texto_pis}; {texto_cofins}."
            )
        elif piscofins_exibicao.get("sugerido"):
            partes.append(
                f"• PIS e COFINS: {piscofins_exibicao.get('status') or 'SUGESTÃO CONDICIONAL'} — "
                f"{texto_pis}; {texto_cofins}. Confirmar exceções antes de aplicar."
            )
        else:
            partes.append(
                f"• PIS e COFINS: {piscofins_exibicao.get('status') or 'REVISÃO NECESSÁRIA'} — "
                f"{piscofins_exibicao.get('observacao') or 'sem confirmação automática.'}"
            )
        if icms_oficial.get("aliquota_nominal") is not None:
            partes.append(
                f"• ICMS próprio {uf_icms}: alíquota da operação "
                f"{self._percentual(icms_oficial.get('aliquota_nominal'))} — "
                f"{icms_oficial.get('aliquota_status') or 'análise oficial'}. "
                + (
                    "CST/CSOSN a definir conforme a operação, origem da mercadoria, regime e posição na ST."
                    if not icms_exibicao.get("cst_definido")
                    else f"CST/CSOSN exibido conforme cadastro local: {icms_exibicao.get('cst')}."
                )
            )
        if st_encontrado:
            partes.append(
                f"• ICMS-ST {uf_icms}: {st_oficial.get('status')} — CEST {st_oficial.get('cest')}, "
                f"MVA original {mva_st_texto}, âmbito {st_oficial.get('ambito')}."
            )
            if st_oficial.get("observacao"):
                partes.append(f"• Atenção ST: {st_oficial.get('observacao')}")
        else:
            partes.append(
                f"• ICMS-ST {uf_icms}: {st_oficial.get('status') or 'CONDICIONAL — REVISAR'}."
            )
            if st_oficial.get("cest_sugerido"):
                partes.append(
                    f"• Possível enquadramento residual: CEST {st_oficial.get('cest_sugerido')}"
                    f" e MVA original {self._percentual(st_oficial.get('mva_sugerida'))},"
                    " condicionado à confirmação de que o produto é peça, componente ou acessório de motocicleta."
                )
            if st_oficial.get("observacao"):
                partes.append(f"• Atenção ST: {st_oficial.get('observacao')}")
        if not self.consulta_oficial.get("normas_oficiais"):
            partes.append("• A alíquota própria de ICMS ainda precisa de confirmação legal específica.")
        self._definir_texto_explicacao("\n".join(partes))

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def abrir_calculadora_icms_st(self) -> None:
        """Abre a memória de cálculo usando o enquadramento oficial já analisado."""
        destino = str(self._contexto().get("uf_destino") or "MG").strip().upper()
        if destino != "MG":
            messagebox.showinfo(
                "FiscalPro",
                f"A cobertura ICMS-ST/{destino} já aparece na Ficha, mas a memória de cálculo detalhada "
                "deste botão ainda é específica de Minas Gerais.\n\n"
                f"Para {destino}, use a MVA e a responsabilidade exibidas na Ficha e revise a base de cálculo "
                "da operação antes de escriturar.",
                parent=self,
            )
            return
        if not self.ncm_atual or self.parecer is None:
            self.analisar()
        if not self.ncm_atual or self.parecer is None:
            return

        st_mg = dict((self.consulta_oficial or {}).get("icms_st_mg") or {})
        if not st_mg.get("encontrado"):
            messagebox.showwarning(
                "FiscalPro",
                "O NCM ainda não foi localizado nos segmentos sincronizados de ICMS-ST/MG.\n\n"
                "Atualize as bases oficiais ou confira o enquadramento antes de calcular.",
                parent=self,
            )
            return
        if st_mg.get("mva_original") is None:
            messagebox.showwarning(
                "FiscalPro",
                "A MVA oficial não foi reconhecida para este enquadramento.",
                parent=self,
            )
            return

        tributacao = dict(getattr(self.parecer, "tributacao_atual", {}) or {})
        aliquota_interna = tributacao.get("ICMS") or 18
        JanelaCalculoICMSSTMG(
            self,
            ncm=self.ncm_atual,
            descricao=str(getattr(self.parecer, "descricao", "") or ""),
            enquadramento_st=st_mg,
            contexto=self._contexto(),
            aliquota_interna_sugerida=aliquota_interna,
        )

    def abrir_xml_icms_st(self) -> None:
        """Abre o módulo completo XML → cálculo por item → planilha."""
        JanelaXMLICMSST(self)

    def abrir_base_legal(self) -> None:
        if not self.ncm_atual:
            self.analisar()
        if not self.ncm_atual:
            return
        if not self.consulta_oficial:
            try:
                gerais = self.dados_ficha.get("dados_gerais", {})
                self.consulta_oficial = ConsultaOficialService.consultar(
                    self.ncm_atual, contexto=self._contexto(),
                    descricao=self.descricao_consulta_atual or str(gerais.get("descricao") or ""),
                    ex_tipi=str(gerais.get("ex_tipi") or ""),
                )
            except Exception as erro:
                messagebox.showerror("FiscalPro", f"Não foi possível consultar as fontes oficiais:\n{erro}", parent=self)
                return
        _JanelaBaseLegalSimplificada(self, self.consulta_oficial, self.parecer)

    def atualizar_st_mg_oficial(self) -> None:
        """Sincroniza somente a Parte 2 do Anexo VII/MG sem baixar NCM/TIPI."""
        self.status_var.set("Atualizando a tabela completa de ICMS-ST/MG na SEF/MG...")
        self.update_idletasks()

        def executar() -> None:
            resultado = AtualizadorFontesOficiais(timeout=60).atualizar_st_mg_completa()
            self.after(0, lambda: finalizar(resultado))

        def finalizar(resultado) -> None:
            if resultado.status != "SUCESSO":
                self.status_var.set("Falha ao atualizar a tabela ST/MG; a base anterior foi preservada.")
                messagebox.showerror(
                    "FiscalPro",
                    resultado.mensagem + "\n\nA base ST/MG anterior foi preservada.",
                    parent=self,
                )
                return

            cobertura = BaseOficialRepository.resumo_st_mg()
            self.status_var.set(
                f"ST/MG atualizada: {int(cobertura.get('registros') or 0)} registros, "
                f"{int(cobertura.get('segmentos') or 0)} segmentos • base completa."
            )
            detalhes = "\n".join(resultado.detalhes or [])
            messagebox.showinfo(
                "FiscalPro",
                "Tabela ST/MG atualizada com sucesso.\n\n"
                + resultado.mensagem
                + ("\n\n" + detalhes if detalhes else ""),
                parent=self,
            )
            if self.ncm_atual:
                gerais = self.dados_ficha.get("dados_gerais", {})
                self.consulta_oficial = ConsultaOficialService.consultar(
                    self.ncm_atual,
                    contexto=self._contexto(),
                    descricao=self.descricao_consulta_atual or str(gerais.get("descricao") or ""),
                    ex_tipi=str(gerais.get("ex_tipi") or ""),
                )
                self._renderizar_resultado()

        threading.Thread(target=executar, daemon=True).start()

    def atualizar_fontes_oficiais(self) -> None:
        self.status_var.set("Atualizando NCM, TIPI e ICMS-ST/MG nas fontes oficiais...")
        self.update_idletasks()

        def executar() -> None:
            resultado = AtualizadorFontesOficiais().atualizar_todas()
            self.after(0, lambda: finalizar(resultado))

        def finalizar(resultado) -> None:
            if resultado.status == "ERRO":
                self.status_var.set("Não foi possível atualizar as bases oficiais.")
                messagebox.showerror(
                    "FiscalPro",
                    resultado.mensagem + "\n\n" + "\n".join(resultado.detalhes),
                    parent=self,
                )
                return
            titulo = "Atualização concluída" if resultado.status == "SUCESSO" else "Atualização parcial"
            self.status_var.set(resultado.mensagem)
            messagebox.showinfo(
                "FiscalPro",
                titulo + "\n\n" + resultado.mensagem + "\n\n" + "\n".join(resultado.detalhes),
                parent=self,
            )
            if self.ncm_atual:
                gerais = self.dados_ficha.get("dados_gerais", {})
                self.consulta_oficial = ConsultaOficialService.consultar(
                    self.ncm_atual, contexto=self._contexto(),
                    descricao=self.descricao_consulta_atual or str(gerais.get("descricao") or ""),
                    ex_tipi=str(gerais.get("ex_tipi") or ""),
                )
                self.parecer = ConsultaOficialService.aplicar_fontes_ao_parecer(
                    self.parecer, self.consulta_oficial
                )
                self._preencher_resultado()

        threading.Thread(target=executar, daemon=True).start()

    @staticmethod
    def _codigo_exato_para_revisao(valor: Any, tamanho: int) -> str:
        digitos = "".join(c for c in str(valor or "") if c.isdigit())
        return digitos if len(digitos) == tamanho else ""

    def _dados_iniciais_revisao_manual(self) -> Dict[str, Any]:
        if self.parecer is None:
            return {}
        t = dict(self.parecer.tributacao_atual or {})
        contexto = self._contexto()
        st = ConsultaOficialService.st_contextual(self.consulta_oficial)
        pisco = ConsultaOficialService.piscofins_para_exibicao(self.consulta_oficial, t)
        icms = ConsultaOficialService.icms_para_exibicao(self.consulta_oficial, t)
        cfop = ConsultaOficialService.cfop_para_exibicao(self.consulta_oficial, contexto, t)
        ipi_principal = dict(self.consulta_oficial.get("ipi_principal") or {})

        cfop_local = self._codigo_exato_para_revisao(t.get("CFOP"), 4)
        if not cfop_local:
            cfop_local = self._codigo_exato_para_revisao(cfop.get("valor"), 4)

        cest = self._codigo_exato_para_revisao(t.get("CEST"), 7)
        if not cest:
            cest = self._codigo_exato_para_revisao(st.get("cest"), 7)
        if not cest:
            cest = self._codigo_exato_para_revisao(self.parecer.dados_gerais.get("CEST"), 7)

        st_atual = str(t.get("ICMS-ST") or "").strip().upper()
        if st_atual not in {"SIM", "NÃO", "NAO", "VERIFICAR"}:
            st_atual = "SIM" if st.get("confirmado") else "VERIFICAR"
        if st_atual == "NAO":
            st_atual = "NÃO"

        mva = self._numero(t.get("MVA ST"))
        if not mva:
            mva = self._numero(st.get("mva_original"))

        ipi = self._numero(t.get("IPI"))
        if (ipi is None or ipi == 0) and ipi_principal.get("aliquota") is not None:
            ipi = self._numero(ipi_principal.get("aliquota"))

        cst_icms = self._codigo_exato_para_revisao(icms.get("cst") or t.get("CST/CSOSN ICMS"), 2)
        if not cst_icms:
            cst_icms = self._codigo_exato_para_revisao(icms.get("cst") or t.get("CST/CSOSN ICMS"), 3)

        return {
            "empresa": contexto.get("empresa") or "",
            "uf_origem": contexto.get("uf_origem") or "",
            "uf_destino": contexto.get("uf_destino") or "",
            "regime": contexto.get("regime") or "",
            "operacao": contexto.get("operacao") or "",
            "finalidade": contexto.get("finalidade") or "REVENDA",
            "contribuinte": contexto.get("contribuinte") or "TODOS",
            "vigencia_inicio": date.today().strftime("%d/%m/%Y"),
            "vigencia_fim": "",
            "status": "VIGENTE",
            "cfop": cfop_local,
            "cest": cest,
            "cst_icms": cst_icms,
            "icms": icms.get("aliquota") if icms.get("aliquota") is not None else t.get("ICMS"),
            "icms_st": st_atual,
            "mva_st": mva if mva is not None else "",
            "fcp": t.get("FCP"),
            "cst_pis": self._codigo_exato_para_revisao(pisco.get("cst_pis"), 2),
            "aliquota_pis": pisco.get("aliquota_pis"),
            "cst_cofins": self._codigo_exato_para_revisao(pisco.get("cst_cofins"), 2),
            "aliquota_cofins": pisco.get("aliquota_cofins"),
            "cst_ipi": self._codigo_exato_para_revisao(t.get("CST IPI"), 2),
            "ipi": ipi if ipi is not None else "",
            "beneficio": "" if self._texto(t.get("Benefício/Regime especial")) == "Não informado" else t.get("Benefício/Regime especial"),
            "fonte": "ALTERAÇÃO MANUAL — USUÁRIO",
            "confiabilidade": "95",
            "observacoes": (
                "Revisão manual criada pela Ficha Inteligente Simplificada. "
                "Conferir a base legal antes da escrituração definitiva."
            ),
            "revisao_manual": 1,
        }

    def revisar_tributacao_manual(self) -> None:
        if self.parecer is None or not self.ncm_atual:
            messagebox.showwarning(
                "FiscalPro",
                "Analise um NCM antes de revisar a tributação.",
                parent=self,
            )
            return

        t = dict(self.parecer.tributacao_atual or {})
        tipo_regra = str(t.get("Tipo da regra") or "").strip().lower()
        try:
            id_atual = int(t.get("ID da regra")) if str(t.get("ID da regra") or "").strip() else None
        except (TypeError, ValueError):
            id_atual = None

        editar_id = id_atual if tipo_regra == "tributacao_atual" else None
        if editar_id:
            inicial = FichaTributariaRepository.buscar_tributacao_atual_por_id(editar_id) or self._dados_iniciais_revisao_manual()
            titulo = "Revisar / editar tributação — regra atual"
            nova_regra = False
        else:
            inicial = self._dados_iniciais_revisao_manual()
            titulo = "Revisar / editar tributação — nova regra manual"
            nova_regra = True

        inicial["revisao_manual"] = 1
        fonte_atual = str(inicial.get("fonte") or "").strip()
        if "ALTERAÇÃO MANUAL" not in fonte_atual.upper():
            inicial["fonte"] = "ALTERAÇÃO MANUAL — USUÁRIO"
        if not str(inicial.get("confiabilidade") or "").strip():
            inicial["confiabilidade"] = "95"

        def salvar(dados: Dict[str, Any]) -> None:
            dados["revisao_manual"] = 1
            fonte_informada = str(dados.get("fonte") or "").strip()
            if "ALTERAÇÃO MANUAL" not in fonte_informada.upper():
                dados["fonte"] = (
                    "ALTERAÇÃO MANUAL — USUÁRIO"
                    + (f" | {fonte_informada}" if fonte_informada else "")
                )
            observacoes = str(dados.get("observacoes") or "").strip()
            marca = "ALTERAÇÃO MANUAL VALIDADA PELO USUÁRIO."
            if marca not in observacoes.upper():
                dados["observacoes"] = f"{marca} {observacoes}".strip()

            if editar_id:
                dados.pop("_encerrar_anterior", None)
                registro_id = FichaTributariaRepository.salvar_tributacao_atual(
                    dados,
                    registro_id=editar_id,
                    encerrar_anterior=False,
                )
            else:
                registro_id = FichaTributariaRepository.salvar_tributacao_atual(
                    dados,
                    encerrar_anterior=bool(dados.pop("_encerrar_anterior", True)),
                )

            FichaTributariaRepository.registrar_historico(
                self.ncm_atual,
                evento="REVISÃO MANUAL SALVA",
                campo="Tributação da operação",
                valor_novo=(
                    f"CFOP {dados.get('cfop') or '-'} | CEST {dados.get('cest') or '-'} | "
                    f"ICMS-ST {dados.get('icms_st') or '-'} | MVA {dados.get('mva_st') or '-'}"
                ),
                origem="Ficha Inteligente Simplificada",
                motivo=f"Regra manual {registro_id}",
            )
            self.status_var.set(f"Regra manual {registro_id} salva. Reanalisando o NCM...")
            self.analisar()
            messagebox.showinfo(
                "FiscalPro",
                "Revisão manual salva com sucesso.\n\n"
                "Nas próximas consultas, essa regra será preservada. As bases oficiais "
                "continuam sendo consultadas apenas para comparação e alertas de divergência.",
                parent=self,
            )

        _FormularioTributacaoAtual(
            self,
            titulo,
            self.ncm_atual,
            inicial,
            salvar,
            nova_regra,
        )

    def salvar_ficha(self) -> None:
        if self.parecer is None:
            self.analisar()
        if self.parecer is None:
            return
        try:
            historico_id = HistoricoParecerRepository.salvar(self.parecer)
            FichaTributariaRepository.definir_favorito(self.parecer.ncm, True)
            FichaTributariaRepository.registrar_historico(
                self.parecer.ncm,
                evento="FICHA SIMPLIFICADA SALVA",
                campo="Contexto analisado",
                valor_novo=(
                    f"{self.operacao_var.get()} | {self.uf_origem_var.get()} → {self.uf_destino_var.get()} | "
                    f"{self.regime_var.get()}"
                ),
                origem="Ficha Inteligente Simplificada",
                motivo=f"Parecer histórico {historico_id}",
            )
            self.status_var.set(f"Ficha salva no histórico com o código {historico_id}.")
            messagebox.showinfo(
                "FiscalPro",
                f"Ficha salva no histórico e adicionada aos favoritos.\nCódigo: {historico_id}",
                parent=self,
            )
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível salvar a ficha:\n{erro}", parent=self)

    def gerar_parecer(self) -> None:
        if self.parecer is None:
            self.analisar()
        if self.parecer is not None:
            _JanelaParecerSimplificado(self, self.parecer)

    def abrir_detalhes_tecnicos_ampliados(self) -> None:
        if not self.tree_resultado.get_children() and self.parecer is None:
            self.analisar()
        linhas = []
        for item in self.tree_resultado.get_children():
            valores = tuple(str(valor) for valor in self.tree_resultado.item(item, "values"))
            linhas.append((
                valores[0] if len(valores) > 0 else "",
                valores[1] if len(valores) > 1 else "",
                valores[2] if len(valores) > 2 else "",
            ))
        explicacao = self.texto_explicacao.get("1.0", "end-1c").strip()
        ncm = self.ncm_atual or "".join(c for c in self.pesquisa_var.get() if c.isdigit()) or "NCM não informado"
        rota = f"{self.uf_origem_var.get().strip()} → {self.uf_destino_var.get().strip()}"
        _JanelaDetalhesTecnicosAmpliados(
            self,
            titulo=f"NCM {ncm} • {rota}",
            linhas=linhas,
            explicacao_texto=explicacao,
        )

    def abrir_detalhes(self) -> None:
        ncm = self.ncm_atual or "".join(c for c in self.pesquisa_var.get() if c.isdigit())
        _JanelaFichaTributariaAvancada(
            self,
            ficha=self.ficha_inicial,
            contexto=self._contexto(),
            ncm=ncm,
        )

    def comparar_com_sped(self) -> None:
        try:
            from src.ui.janela_sped_inteligente import JanelaSPEDInteligente

            JanelaSPEDInteligente(self)
            self.status_var.set(
                "SPED Inteligente aberto. Selecione o arquivo e use 'Cruzar Ficha Tributária'."
            )
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível abrir o SPED Inteligente:\n{erro}", parent=self)

    def limpar(self) -> None:
        self.pesquisa_var.set("")
        self.ncm_atual = ""
        self.dados_ficha = {}
        self.parecer = None
        self.consulta_oficial = {}
        self.resultado_status_var.set("AGUARDANDO ANÁLISE")
        self.lbl_resultado_status.configure(bg="#D9EAD3", fg="#274E13")
        self.identificacao_var.set("Nenhum produto analisado.")
        self.descricao_var.set("A Ficha mostrará somente CFOP e tributos essenciais.")
        self.contexto_st_var.set("ICMS-ST: aguardando análise.")
        for item in self.tree_resultado.get_children():
            self.tree_resultado.delete(item)
        self._definir_texto_explicacao(
            "A análise explicará por que a regra foi escolhida e indicará o que ainda precisa de conferência."
        )
        if hasattr(self, "btn_revisar_tributacao"):
            self.btn_revisar_tributacao.configure(state=tk.DISABLED)
        self.status_var.set("Informe o NCM ou a descrição do produto e clique em Analisar.")
        self.entry_pesquisa.focus_set()

    # ------------------------------------------------------------------
    # Formatação
    # ------------------------------------------------------------------
    def _definir_texto_explicacao(self, texto: str) -> None:
        self.texto_explicacao.configure(state=tk.NORMAL)
        self.texto_explicacao.delete("1.0", tk.END)
        self.texto_explicacao.insert("1.0", texto)
        self.texto_explicacao.configure(state=tk.DISABLED)

    @staticmethod
    def _texto(valor: Any) -> str:
        texto = str(valor or "").strip()
        return texto if texto and texto not in {"-", "None"} else "Não informado"

    @staticmethod
    def _st_confirmado_para_exibicao(st_oficial: Dict[str, Any]) -> bool:
        decisao = str((st_oficial or {}).get("decisao_st") or "").strip().upper()
        return bool(
            (st_oficial or {}).get("confirmado")
            and ((st_oficial or {}).get("decisao_confirmada") or decisao == "SIM")
        )

    @staticmethod
    def _formatar_cest_exibicao(valor: Any) -> str:
        texto = str(valor or "").strip()
        if not texto or texto in {"-", "None", "Não informado", "Não informada"}:
            return "Não informado"
        digitos = "".join(c for c in texto if c.isdigit())
        if digitos and len(digitos) < 7:
            digitos = digitos.zfill(7)
        if len(digitos) == 7:
            return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:]}"
        return texto

    @staticmethod
    def _numero(valor: Any) -> Optional[float]:
        if valor in (None, "", "Não informado"):
            return None
        try:
            return float(str(valor).replace("%", "").replace(".", "").replace(",", ".")) if "," in str(valor) else float(valor)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _percentual(cls, valor: Any) -> str:
        numero = cls._numero(valor)
        if numero is None:
            return "Não informado"
        return f"{numero:.2f}%".replace(".", ",")

    @classmethod
    def _tributo_com_cst(cls, cst: Any, aliquota: Any) -> str:
        return f"CST {cls._texto(cst)}  •  {cls._percentual(aliquota)}"
