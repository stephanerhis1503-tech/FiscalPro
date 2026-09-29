"""Janela simples para cálculo assistido de MVA e ICMS-ST/MG."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from decimal import Decimal
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional

from src.services.calculadora_icms_st_mg_service import CalculadoraICMSSTMGService
from src.ui.layout_responsivo import dimensionar_janela


def _numero_br(valor: Any, casas: int = 2) -> str:
    try:
        numero = Decimal(str(valor))
    except Exception:
        return str(valor or "")
    return f"{numero:.{casas}f}".replace(".", ",")


def _moeda_br(valor: Any) -> str:
    try:
        numero = Decimal(str(valor))
    except Exception:
        numero = Decimal("0")
    texto = f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


class JanelaCalculoICMSSTMG(tk.Toplevel):
    """Calculadora manual ligada ao enquadramento oficial da Ficha Inteligente."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        ncm: str,
        descricao: str,
        enquadramento_st: Dict[str, Any],
        contexto: Dict[str, Any],
        aliquota_interna_sugerida: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Cálculo de ICMS-ST/MG")
        dimensionar_janela(self, 920, 800, 720, 560)
        self.transient(parent)
        self.grab_set()

        self.ncm = ncm
        self.descricao = descricao
        self.st = dict(enquadramento_st or {})
        self.contexto = dict(contexto or {})
        self.resultado: Dict[str, Any] = {}
        self.vars: Dict[str, tk.StringVar] = {}

        origem = str(self.contexto.get("uf_origem") or "").upper()
        destino = str(self.contexto.get("uf_destino") or "MG").upper()
        origem_mercadoria = str(self.contexto.get("origem_mercadoria") or "").upper()
        interestadual = bool(origem and destino and origem != destino)
        aliquota_inter = "4,00" if interestadual and origem_mercadoria == "IMPORTADA" else (
            "12,00" if interestadual else _numero_br(aliquota_interna_sugerida or 18)
        )
        aliquota_intra = _numero_br(aliquota_interna_sugerida or 18)

        self.interestadual_var = tk.BooleanVar(value=interestadual)
        self.ajustar_mva_var = tk.BooleanVar(value=True)
        self.remetente_simples_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Preencha os valores da operação e clique em Calcular.")
        self.total_var = tk.StringVar(value="R$ 0,00")

        self._montar(
            mva=_numero_br(self.st.get("mva_original") or 0),
            aliquota_inter=aliquota_inter,
            aliquota_intra=aliquota_intra,
        )
        self.bind("<Escape>", lambda _e: self.destroy())

    def _campo(self, frame: ttk.Frame, linha: int, coluna: int, rotulo: str, chave: str, valor: str = "0,00") -> None:
        ttk.Label(frame, text=rotulo, font=("Segoe UI", 9, "bold")).grid(
            row=linha, column=coluna * 2, sticky="w", padx=(0, 6), pady=5
        )
        var = tk.StringVar(value=valor)
        self.vars[chave] = var
        ttk.Entry(frame, textvariable=var, width=18, justify=tk.RIGHT).grid(
            row=linha, column=coluna * 2 + 1, sticky="ew", padx=(0, 16), pady=5
        )
        frame.columnconfigure(coluna * 2 + 1, weight=1)

    def _montar(self, *, mva: str, aliquota_inter: str, aliquota_intra: str) -> None:
        cabecalho = tk.Frame(self, bg="#1F4E78")
        cabecalho.pack(fill=tk.X)
        tk.Label(
            cabecalho,
            text="Cálculo de ICMS-ST/MG",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(10, 0))
        tk.Label(
            cabecalho,
            text=f"NCM {self.ncm}  •  CEST {self.st.get('cest') or 'não informado'}  •  {self.descricao or 'Produto'}",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 9),
            wraplength=800,
            justify=tk.LEFT,
        ).pack(anchor="w", padx=20, pady=(2, 10))

        conteudo = ttk.Frame(self, padding=12)
        conteudo.pack(fill=tk.BOTH, expand=True)

        aviso = ttk.Label(
            conteudo,
            text=(
                "Use o valor dos produtos antes do desconto. O IPI, o frete, o seguro e os demais encargos "
                "serão somados à base de partida."
            ),
            foreground="#7F6000",
            wraplength=800,
            justify=tk.LEFT,
        )
        aviso.pack(fill=tk.X, pady=(0, 8))

        valores = ttk.LabelFrame(conteudo, text="1. Valores da operação", padding=10)
        valores.pack(fill=tk.X)
        self._campo(valores, 0, 0, "Valor dos produtos", "valor_mercadoria")
        self._campo(valores, 0, 1, "IPI", "ipi")
        self._campo(valores, 1, 0, "Frete", "frete")
        self._campo(valores, 1, 1, "Seguro", "seguro")
        self._campo(valores, 2, 0, "Outros encargos/tributos", "outros_encargos")
        self._campo(valores, 2, 1, "ICMS próprio a deduzir", "icms_proprio")

        indices = ttk.LabelFrame(conteudo, text="2. Índices do cálculo", padding=10)
        indices.pack(fill=tk.X, pady=(8, 0))
        self._campo(indices, 0, 0, "MVA original", "mva_original", mva)
        self._campo(indices, 0, 1, "Alíquota interna MG", "aliquota_interna", aliquota_intra)
        self._campo(indices, 1, 0, "Alíquota interestadual", "aliquota_interestadual", aliquota_inter)
        self._campo(indices, 1, 1, "FCP-ST (se aplicável)", "aliquota_fcp", "0,00")

        opcoes = ttk.Frame(indices)
        opcoes.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            opcoes,
            text="Operação interestadual",
            variable=self.interestadual_var,
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            opcoes,
            text="Aplicar MVA ajustada quando cabível",
            variable=self.ajustar_mva_var,
        ).pack(side=tk.LEFT, padx=(14, 0))
        ttk.Checkbutton(
            opcoes,
            text="Remetente do Simples Nacional",
            variable=self.remetente_simples_var,
        ).pack(side=tk.LEFT, padx=(14, 0))

        resultado = ttk.LabelFrame(conteudo, text="3. Resultado", padding=10)
        resultado.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        topo = ttk.Frame(resultado)
        topo.pack(fill=tk.X)
        ttk.Label(topo, text="Total ICMS-ST + FCP-ST", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Label(topo, textvariable=self.total_var, font=("Segoe UI", 15, "bold"), foreground="#1F4E78").pack(
            side=tk.RIGHT
        )

        self.tree = ttk.Treeview(
            resultado,
            columns=("campo", "valor"),
            show="headings",
            height=8,
        )
        self.tree.heading("campo", text="Memória")
        self.tree.heading("valor", text="Resultado")
        self.tree.column("campo", width=310)
        self.tree.column("valor", width=260)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        rodape = ttk.Frame(self, padding=(12, 4, 12, 10))
        rodape.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(rodape, text="📚 Abrir base legal", command=self._abrir_base_legal).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Copiar memória", command=self._copiar).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(rodape, text="🧮 CALCULAR", command=self.calcular).pack(side=tk.RIGHT, padx=(0, 8), ipadx=10)

        tk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            bg="#EAF2F8",
            padx=12,
            pady=5,
        ).pack(fill=tk.X, side=tk.BOTTOM)

    def calcular(self) -> None:
        try:
            self.resultado = CalculadoraICMSSTMGService.calcular(
                valor_mercadoria=self.vars["valor_mercadoria"].get(),
                frete=self.vars["frete"].get(),
                seguro=self.vars["seguro"].get(),
                ipi=self.vars["ipi"].get(),
                outros_encargos=self.vars["outros_encargos"].get(),
                mva_original=self.vars["mva_original"].get(),
                aliquota_interestadual=self.vars["aliquota_interestadual"].get(),
                aliquota_interna=self.vars["aliquota_interna"].get(),
                icms_proprio_deduzir=self.vars["icms_proprio"].get(),
                aliquota_fcp_st=self.vars["aliquota_fcp"].get(),
                operacao_interestadual=self.interestadual_var.get(),
                aplicar_mva_ajustada=self.ajustar_mva_var.get(),
                remetente_simples=self.remetente_simples_var.get(),
            )
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
            return
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível calcular o ICMS-ST:\n{erro}", parent=self)
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        mva_ajustada = self.resultado.get("mva_ajustada")
        linhas = [
            ("MVA original", f"{_numero_br(self.resultado.get('mva_original'))}%"),
            ("MVA ajustada", f"{_numero_br(mva_ajustada)}%" if mva_ajustada is not None else "Não aplicada"),
            ("MVA utilizada", f"{_numero_br(self.resultado.get('mva_utilizada'))}% — {self.resultado.get('tipo_mva') or ''}"),
            ("Valor dos produtos + IPI", _moeda_br(self.resultado.get("valor_total_com_ipi"))),
            ("Base de partida", _moeda_br(self.resultado.get("base_partida_st"))),
            ("Base de cálculo do ICMS-ST", _moeda_br(self.resultado.get("base_calculo_st"))),
            ("ICMS presumido", _moeda_br(self.resultado.get("icms_presumido"))),
            ("ICMS próprio a deduzir", _moeda_br(self.resultado.get("icms_proprio_deduzir"))),
            ("ICMS-ST", _moeda_br(self.resultado.get("icms_st"))),
            ("FCP-ST", _moeda_br(self.resultado.get("fcp_st"))),
        ]
        for linha in linhas:
            self.tree.insert("", tk.END, values=linha)

        self.total_var.set(_moeda_br(self.resultado.get("total_st_fcp")))
        observacoes = self.resultado.get("observacoes") or []
        self.status_var.set(observacoes[0] if observacoes else "Cálculo concluído. Confira os dados informados.")

    def _copiar(self) -> None:
        if not self.resultado:
            self.calcular()
        if not self.resultado:
            return
        texto = CalculadoraICMSSTMGService.memoria_texto(self.resultado)
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update()
        self.status_var.set("Memória de cálculo copiada.")

    def _abrir_base_legal(self) -> None:
        webbrowser.open_new_tab(
            str(self.resultado.get("fonte_url") if self.resultado else "")
            or "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/ricms2023/anexovii2023.pdf"
        )
