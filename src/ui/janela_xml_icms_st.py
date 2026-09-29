"""Tela direta para importar NF-e XML, calcular e conferir ICMS-ST/MG."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional

from src.services.exportador_xml_icms_st_xlsx import ExportadorXMLICMSSTXLSX
from src.ui.layout_responsivo import FrameRolavel, dimensionar_janela
from src.services.xml_icms_st_service import (
    APLICABILIDADE_7318_CONSTRUCAO,
    APLICABILIDADE_7318_EXCLUSIVO_AUTOMOTIVO,
    APLICABILIDADE_7318_PENDENTE,
    NotaFiscalXML,
    XMLICMSSTService,
)


_UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")

_ROTULOS_7318 = {
    APLICABILIDADE_7318_PENDENTE: "Revisar antes de calcular",
    APLICABILIDADE_7318_CONSTRUCAO: "Passível de uso na construção/congêneres — calcular ST",
    APLICABILIDADE_7318_EXCLUSIVO_AUTOMOTIVO: "Uso exclusivamente automotivo — não aplicar ST do segmento 10",
}
_CODIGOS_7318_POR_ROTULO = {rotulo: codigo for codigo, rotulo in _ROTULOS_7318.items()}

_ROTULOS_FINALIDADE_AUTO = {
    "NAO_INFORMADA": "Não informada — manter condicional",
    "AUTOPECA_CONFIRMADA": "Peça/componente/acessório de moto",
    "NAO_AUTOMOTIVA": "Não é peça automotiva",
}
_CODIGOS_FINALIDADE_AUTO_POR_ROTULO = {
    rotulo: codigo for codigo, rotulo in _ROTULOS_FINALIDADE_AUTO.items()
}


def _numero_br(valor: Any, casas: int = 2) -> str:
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0
    return f"{numero:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _moeda(valor: Any) -> str:
    return f"R$ {_numero_br(valor)}"


def _parse_numero(texto: str) -> float:
    valor = str(texto or "").strip().replace(" ", "")
    if not valor:
        raise ValueError("valor vazio")
    if "," in valor and "." in valor:
        valor = valor.replace(".", "").replace(",", ".")
    elif "," in valor:
        valor = valor.replace(",", ".")
    return float(valor)


class _JanelaEditarItem(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        item: Dict[str, Any],
        ajuste: Dict[str, Any],
        ao_salvar,
    ) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Ajustar item do XML")
        dimensionar_janela(self, 740, 720, 620, 540, maximizar_em_tela_baixa=False)
        self.transient(parent)
        self.grab_set()
        self.ao_salvar = ao_salvar
        self.item = item
        self.vars: Dict[str, tk.StringVar] = {}
        self.aplicabilidade_7318_var: Optional[tk.StringVar] = None
        self.finalidade_automotiva_var: Optional[tk.StringVar] = None

        cabecalho = tk.Frame(self, bg="#1F4E78")
        cabecalho.pack(fill=tk.X)
        tk.Label(
            cabecalho,
            text=f"Item {item.get('numero_item')} — NCM {item.get('ncm')}",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(10, 0))
        tk.Label(
            cabecalho,
            text=str(item.get("descricao") or ""),
            bg="#1F4E78",
            fg="white",
            wraplength=560,
            justify=tk.LEFT,
        ).pack(anchor="w", padx=17, pady=(2, 10))

        # O conteúdo da ficha pode ultrapassar a altura útil do monitor,
        # especialmente com escala do Windows acima de 100%. Mantemos o
        # rodapé (Salvar/Cancelar) sempre visível e rolamos apenas o formulário.
        area_rolavel = FrameRolavel(self, background="#F3F6FA")
        area_rolavel.pack(fill=tk.BOTH, expand=True, padx=14, pady=(14, 8))

        form = ttk.LabelFrame(
            area_rolavel.interno,
            text="Preencha somente o que precisar corrigir",
            padding=14,
        )
        form.pack(fill=tk.X, expand=True)

        campos = [
            ("MVA original %", "mva_original"),
            ("Alíquota interestadual %", "aliquota_interestadual"),
            ("Alíquota interna MG %", "aliquota_interna"),
            ("FCP-ST %", "aliquota_fcp"),
            ("ICMS próprio a deduzir", "icms_proprio"),
        ]
        for linha, (rotulo, chave) in enumerate(campos):
            ttk.Label(form, text=rotulo, font=("Segoe UI", 9, "bold")).grid(
                row=linha, column=0, sticky="w", padx=(0, 10), pady=8
            )
            var = tk.StringVar(value=str(ajuste.get(chave, "")).replace(".", ","))
            self.vars[chave] = var
            ttk.Entry(form, textvariable=var, justify=tk.RIGHT, width=22).grid(
                row=linha, column=1, sticky="ew", pady=8
            )
        form.columnconfigure(1, weight=1)

        linha_aviso = len(campos)
        ttk.Separator(form, orient=tk.HORIZONTAL).grid(
            row=linha_aviso, column=0, columnspan=2, sticky="ew", pady=(10, 12)
        )
        linha_aviso += 1
        ttk.Label(form, text="Finalidade para ICMS-ST", font=("Segoe UI", 9, "bold")).grid(
            row=linha_aviso, column=0, sticky="w", padx=(0, 10), pady=8
        )
        finalidade_atual = str(ajuste.get("finalidade_automotiva") or "NAO_INFORMADA")
        self.finalidade_automotiva_var = tk.StringVar(
            value=_ROTULOS_FINALIDADE_AUTO.get(finalidade_atual, _ROTULOS_FINALIDADE_AUTO["NAO_INFORMADA"])
        )
        ttk.Combobox(
            form, textvariable=self.finalidade_automotiva_var,
            values=tuple(_CODIGOS_FINALIDADE_AUTO_POR_ROTULO), state="readonly", width=48,
        ).grid(row=linha_aviso, column=1, sticky="ew", pady=8)
        linha_aviso += 1
        ttk.Label(
            form,
            text="O FiscalPro reconhece descrições objetivas de peças de moto. Use este campo somente para confirmar ou corrigir a finalidade do item.",
            foreground="#7F6000", wraplength=560, justify=tk.LEFT,
        ).grid(row=linha_aviso, column=0, columnspan=2, sticky="w", pady=(2, 8))
        linha_aviso += 1

        if str(item.get("ncm") or "").startswith("7318"):
            ttk.Separator(form, orient=tk.HORIZONTAL).grid(
                row=linha_aviso, column=0, columnspan=2, sticky="ew", pady=(10, 12)
            )
            linha_aviso += 1
            ttk.Label(
                form, text="Aplicabilidade do NCM 7318", font=("Segoe UI", 9, "bold")
            ).grid(row=linha_aviso, column=0, sticky="w", padx=(0, 10), pady=8)
            codigo_atual = str(ajuste.get("aplicabilidade_7318") or APLICABILIDADE_7318_PENDENTE)
            self.aplicabilidade_7318_var = tk.StringVar(
                value=_ROTULOS_7318.get(codigo_atual, _ROTULOS_7318[APLICABILIDADE_7318_PENDENTE])
            )
            ttk.Combobox(
                form,
                textvariable=self.aplicabilidade_7318_var,
                values=tuple(_CODIGOS_7318_POR_ROTULO),
                state="readonly",
                width=54,
            ).grid(row=linha_aviso, column=1, sticky="ew", pady=8)
            linha_aviso += 1
            ttk.Label(
                form,
                text=(
                    "Para o NCM 7318, a legislação mineira exige conferir a compatibilidade com o segmento 10. "
                    "Marque uso exclusivamente automotivo somente quando houver suporte técnico para essa condição."
                ),
                foreground="#7F6000",
                wraplength=600,
                justify=tk.LEFT,
            ).grid(row=linha_aviso, column=0, columnspan=2, sticky="w", pady=(2, 8))
            linha_aviso += 1

        ttk.Label(
            form,
            text=(
                "A MVA oficial continua sendo usada quando este campo fica vazio. "
                "O valor informado aqui vale somente para este item e ficará identificado na planilha."
            ),
            foreground="#7F6000",
            wraplength=540,
            justify=tk.LEFT,
        ).grid(row=linha_aviso, column=0, columnspan=2, sticky="w", pady=(12, 0))

        rodape = ttk.Frame(self, padding=(14, 6, 14, 14))
        rodape.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Separator(rodape, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 10))
        ttk.Button(rodape, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        botao_salvar = ttk.Button(rodape, text="Salvar e recalcular", command=self._salvar)
        botao_salvar.pack(side=tk.RIGHT)

        # Atalhos úteis quando a janela está em tela pequena ou com escala alta.
        self.bind("<Control-s>", lambda _e: (self._salvar(), "break")[1])
        self.bind("<Escape>", lambda _e: self.destroy())

    def _salvar(self) -> None:
        dados = {}
        for chave, var in self.vars.items():
            valor = var.get().strip()
            if valor:
                try:
                    dados[chave] = _parse_numero(valor)
                except ValueError:
                    messagebox.showwarning("FiscalPro", f"Valor inválido no campo: {chave}.", parent=self)
                    return
        if self.aplicabilidade_7318_var is not None:
            dados["aplicabilidade_7318"] = _CODIGOS_7318_POR_ROTULO.get(
                self.aplicabilidade_7318_var.get(), APLICABILIDADE_7318_PENDENTE
            )
        if self.finalidade_automotiva_var is not None:
            dados["finalidade_automotiva"] = _CODIGOS_FINALIDADE_AUTO_POR_ROTULO.get(
                self.finalidade_automotiva_var.get(), "NAO_INFORMADA"
            )
        self.ao_salvar(dados)
        self.destroy()


class JanelaXMLICMSST(tk.Toplevel):
    """Módulo visível XML → ICMS-ST → Excel."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("FiscalPro — Importar XML, calcular e conferir ICMS-ST/MG")
        dimensionar_janela(self, 1360, 860, 960, 600)
        self.transient(parent)

        self.nota: Optional[NotaFiscalXML] = None
        self.resultado: Dict[str, Any] = {}
        self.ajustes: Dict[int, Dict[str, Any]] = {}
        self.caminho_xml = tk.StringVar(value="Nenhum XML importado.")
        self.uf_origem_var = tk.StringVar(value="MG")
        self.uf_destino_var = tk.StringVar(value="MG")
        self.aliquota_interna_var = tk.StringVar(value="18,00")
        self.aliquota_inter_var = tk.StringVar(value="")
        self.fcp_var = tk.StringVar(value="0,00")
        self.remetente_simples_var = tk.BooleanVar(value=False)
        self.mva_ajustada_var = tk.BooleanVar(value=True)
        self.deduzir_icms_inter_var = tk.BooleanVar(value=True)
        self.info_simples_var = tk.StringVar(
            value="A dedução é só da memória do ICMS-ST; não cria crédito escritural. Alíquota vazia = sugestão 12%/4% por item."
        )
        self.status_var = tk.StringVar(value="Importe uma NF-e XML para começar.")
        self.resumo_var = tk.StringVar(value="Itens: 0  •  ST no XML: R$ 0,00  •  ST calculado: R$ 0,00")

        self._montar()
        self.bind("<Escape>", lambda _e: self.destroy())

    def _montar(self) -> None:
        cabecalho = tk.Frame(self, bg="#1F4E78")
        cabecalho.pack(fill=tk.X)
        tk.Label(
            cabecalho,
            text="Importar XML, calcular e conferir ICMS-ST/MG",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(10, 0))
        tk.Label(
            cabecalho,
            text="O FiscalPro lê o XML, calcula o ST e compara com o valor informado pelo fornecedor.",
            bg="#1F4E78",
            fg="white",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=(2, 10))

        barra_status = tk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            bg="#EAF2F8",
            fg="#1F1F1F",
            padx=12,
            pady=6,
        )
        barra_status.pack(fill=tk.X, side=tk.BOTTOM)

        rodape = ttk.Frame(self, padding=(12, 5, 12, 10))
        rodape.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(rodape, text="📂 Importar XML", command=self.importar_xml).pack(side=tk.LEFT)
        ttk.Button(rodape, text="🔄 Recalcular", command=self.recalcular).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(rodape, text="✏ Ajustar item", command=self.editar_item).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(
            rodape,
            text="📊 GERAR PLANILHA",
            command=self.gerar_planilha,
        ).pack(side=tk.RIGHT, padx=(0, 8), ipadx=10, ipady=3)

        conteudo = ttk.Frame(self, padding=12)
        conteudo.pack(fill=tk.BOTH, expand=True)

        origem = ttk.LabelFrame(conteudo, text="1. XML e dados da operação", padding=10)
        origem.pack(fill=tk.X)
        ttk.Label(origem, textvariable=self.caminho_xml, wraplength=1120).grid(
            row=0, column=0, columnspan=8, sticky="w", pady=(0, 8)
        )

        campos = [
            ("UF origem", self.uf_origem_var, _UFS, 0),
            ("UF destino", self.uf_destino_var, _UFS, 1),
        ]
        for rotulo, var, valores, coluna in campos:
            ttk.Label(origem, text=rotulo, font=("Segoe UI", 9, "bold")).grid(
                row=1, column=coluna * 2, sticky="w", padx=(0, 5)
            )
            ttk.Combobox(origem, textvariable=var, values=valores, state="readonly", width=8).grid(
                row=1, column=coluna * 2 + 1, sticky="w", padx=(0, 14)
            )

        ttk.Label(origem, text="Alíquota interna MG", font=("Segoe UI", 9, "bold")).grid(row=1, column=4, sticky="w")
        ttk.Entry(origem, textvariable=self.aliquota_interna_var, width=10, justify=tk.RIGHT).grid(
            row=1, column=5, sticky="w", padx=(5, 14)
        )
        ttk.Label(origem, text="Alíquota interestadual", font=("Segoe UI", 9, "bold")).grid(row=1, column=6, sticky="w")
        ttk.Entry(origem, textvariable=self.aliquota_inter_var, width=10, justify=tk.RIGHT).grid(
            row=1, column=7, sticky="w", padx=(5, 14)
        )
        ttk.Label(origem, text="FCP-ST", font=("Segoe UI", 9, "bold")).grid(row=1, column=8, sticky="w")
        ttk.Entry(origem, textvariable=self.fcp_var, width=9, justify=tk.RIGHT).grid(row=1, column=9, sticky="w", padx=(5, 0))

        opcoes = ttk.Frame(origem)
        opcoes.grid(row=2, column=0, columnspan=10, sticky="w", pady=(9, 0))
        self.chk_mva_ajustada = ttk.Checkbutton(
            opcoes,
            text="Aplicar MVA ajustada quando cabível (desmarque para MVA original)",
            variable=self.mva_ajustada_var,
        )
        self.chk_mva_ajustada.pack(side=tk.LEFT)
        ttk.Checkbutton(
            opcoes,
            text="Remetente do Simples Nacional",
            variable=self.remetente_simples_var,
            command=self._atualizar_opcoes_simples,
        ).pack(side=tk.LEFT, padx=(18, 0))

        opcoes2 = ttk.Frame(origem)
        opcoes2.grid(row=3, column=0, columnspan=10, sticky="w", pady=(5, 0))
        self.chk_deducao_icms = ttk.Checkbutton(
            opcoes2,
            text="Deduzir ICMS da operação própria pela alíquota aplicável quando o XML vier sem vICMS (automático no Simples)",
            variable=self.deduzir_icms_inter_var,
        )
        self.chk_deducao_icms.pack(side=tk.LEFT)
        ttk.Label(
            opcoes2,
            textvariable=self.info_simples_var,
            foreground="#7F6000",
        ).pack(side=tk.LEFT, padx=(12, 0))
        self._atualizar_opcoes_simples()

        lista = ttk.LabelFrame(conteudo, text="2. Itens, cálculo e conferência do XML", padding=8)
        lista.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        ttk.Label(
            lista, textvariable=self.resumo_var, font=("Segoe UI", 10, "bold"),
            justify=tk.LEFT, wraplength=1160
        ).pack(anchor="w", pady=(0, 7))

        area_tree = ttk.Frame(lista)
        area_tree.pack(fill=tk.BOTH, expand=True)
        # A grade mostra apenas o que é necessário para decidir. A memória completa
        # continua disponível no ajuste do item e na planilha exportada.
        colunas = (
            "item", "codigo", "ncm", "produto", "cest", "com_ipi",
            "mva_usada", "deducao_icms", "st_calc", "st_xml", "diferenca", "conferencia",
        )
        self.tree = ttk.Treeview(area_tree, columns=colunas, show="headings", height=16)
        titulos = {
            "item": "Item", "codigo": "Código", "ncm": "NCM", "produto": "Produto",
            "cest": "CEST", "com_ipi": "Item + IPI", "mva_usada": "MVA usada",
            "deducao_icms": "Dedução ICMS", "st_calc": "ST calculado",
            "st_xml": "ST no XML", "diferenca": "Diferença", "conferencia": "Situação",
        }
        larguras = {
            "item": 45, "codigo": 95, "ncm": 82, "produto": 310, "cest": 95,
            "com_ipi": 105, "mva_usada": 100, "deducao_icms": 110, "st_calc": 105,
            "st_xml": 105, "diferenca": 100, "conferencia": 235,
        }
        for coluna in colunas:
            self.tree.heading(coluna, text=titulos[coluna])
            self.tree.column(coluna, width=larguras[coluna], minwidth=45, stretch=coluna in {"produto", "conferencia"})

        barra_y = ttk.Scrollbar(area_tree, orient=tk.VERTICAL, command=self.tree.yview)
        barra_x = ttk.Scrollbar(area_tree, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        area_tree.rowconfigure(0, weight=1)
        area_tree.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _e: self.editar_item())
        self.tree.tag_configure("correto", background="#E2F0D9")
        self.tree.tag_configure("atencao", background="#FFF2CC")
        self.tree.tag_configure("divergente", background="#F4CCCC")
        self.tree.tag_configure("revisar", background="#FCE5CD")

    @staticmethod
    def _valor_manual(texto: str, nome: str, permitir_vazio: bool = False) -> Optional[float]:
        valor = texto.strip()
        if not valor and permitir_vazio:
            return None
        try:
            return _parse_numero(valor)
        except ValueError as erro:
            raise ValueError(f"{nome} inválida.") from erro

    def _atualizar_opcoes_simples(self) -> None:
        """Mantém a tela coerente com a regra mineira para remetente do Simples.

        No Simples Nacional, o art. 20, § 6º do Anexo VII afasta a MVA ajustada
        interestadual e o art. 22, § 1º determina a dedução da operação própria
        pela alíquota aplicável. O usuário ainda pode ajustar o valor por item.
        """
        simples = bool(self.remetente_simples_var.get())
        if simples:
            self.mva_ajustada_var.set(False)
            self.deduzir_icms_inter_var.set(True)
            if hasattr(self, "chk_mva_ajustada"):
                self.chk_mva_ajustada.state(["disabled"])
            if hasattr(self, "chk_deducao_icms"):
                self.chk_deducao_icms.state(["disabled"])
            self.info_simples_var.set(
                "Simples Nacional: usa MVA original e deduz a operação própria pela alíquota interna/interestadual. "
                "A dedução é só da memória do ICMS-ST; não cria crédito escritural."
            )
        else:
            self.mva_ajustada_var.set(True)
            if hasattr(self, "chk_mva_ajustada"):
                self.chk_mva_ajustada.state(["!disabled"])
            if hasattr(self, "chk_deducao_icms"):
                self.chk_deducao_icms.state(["!disabled"])
            self.info_simples_var.set(
                "A dedução é só da memória do ICMS-ST; não cria crédito escritural. Alíquota vazia = sugestão 12%/4% por item."
            )

    def importar_xml(self) -> None:
        arquivo = filedialog.askopenfilename(
            parent=self,
            title="Selecione a NF-e XML",
            filetypes=[("NF-e XML", "*.xml"), ("Todos os arquivos", "*.*")],
        )
        if not arquivo:
            return
        try:
            self.nota = XMLICMSSTService.ler_xml(arquivo)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível importar o XML:\n{erro}", parent=self)
            return

        self.ajustes.clear()
        self.caminho_xml.set(
            f"NF-e {self.nota.numero}/{self.nota.serie} — {self.nota.emitente_nome} — {Path(arquivo).name}"
        )
        if self.nota.uf_origem in _UFS:
            self.uf_origem_var.set(self.nota.uf_origem)
        if self.nota.uf_destino in _UFS:
            self.uf_destino_var.set(self.nota.uf_destino)
        self.remetente_simples_var.set(self.nota.regime_emitente.startswith("SIMPLES"))
        self._atualizar_opcoes_simples()
        self._classificar_itens_7318_ao_importar()
        self.status_var.set(f"XML importado com {len(self.nota.itens)} item(ns). Calculando...")
        self.recalcular()

    def _classificar_itens_7318_ao_importar(self) -> None:
        if self.nota is None:
            return
        itens_7318 = [item for item in self.nota.itens if str(item.ncm).startswith("7318")]
        if not itens_7318:
            return

        resposta = messagebox.askyesnocancel(
            "FiscalPro — Parafusos e itens NCM 7318",
            f"A nota possui {len(itens_7318)} item(ns) no NCM 7318.\n\n"
            "Esses produtos são passíveis de uso como materiais de construção ou congêneres?\n\n"
            "SIM: aplicar CEST 10.058.00 e MVA de 50%, quando o âmbito da operação permitir.\n"
            "NÃO: considerar uso exclusivamente automotivo e não aplicar a ST do segmento 10.\n"
            "CANCELAR: deixar os itens marcados para revisão individual.",
            parent=self,
        )
        if resposta is True:
            codigo = APLICABILIDADE_7318_CONSTRUCAO
        elif resposta is False:
            codigo = APLICABILIDADE_7318_EXCLUSIVO_AUTOMOTIVO
        else:
            codigo = APLICABILIDADE_7318_PENDENTE

        for item in itens_7318:
            self.ajustes.setdefault(item.numero_item, {})["aplicabilidade_7318"] = codigo

    def recalcular(self) -> None:
        if self.nota is None:
            messagebox.showwarning("FiscalPro", "Importe uma NF-e XML primeiro.", parent=self)
            return
        try:
            alq_interna = self._valor_manual(self.aliquota_interna_var.get(), "Alíquota interna")
            alq_inter = self._valor_manual(self.aliquota_inter_var.get(), "Alíquota interestadual", permitir_vazio=True)
            fcp = self._valor_manual(self.fcp_var.get(), "FCP-ST")
            self.resultado = XMLICMSSTService.calcular_nota(
                self.nota,
                uf_origem=self.uf_origem_var.get(),
                uf_destino=self.uf_destino_var.get(),
                aliquota_interna=alq_interna,
                aliquota_interestadual=alq_inter,
                aliquota_fcp=fcp,
                remetente_simples=self.remetente_simples_var.get(),
                aplicar_mva_ajustada=self.mva_ajustada_var.get(),
                deduzir_icms_inter_sem_destaque=self.deduzir_icms_inter_var.get(),
                ajustes=self.ajustes,
            )
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
            return
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível calcular os itens:\n{erro}", parent=self)
            return
        self._preencher_tree()

    def _preencher_tree(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for resultado_item in self.resultado.get("itens", []):
            item = resultado_item.get("item") or {}
            numero = int(item.get("numero_item") or 0)
            mva_aj = resultado_item.get("mva_ajustada")
            conferencia = str(resultado_item.get("conferencia_status") or "REVISAR")
            if conferencia == "CORRETO":
                tag = "correto"
            elif conferencia in {
                "ST NÃO DESTACADO",
                "ST RETIDO ANTERIORMENTE — REVISAR",
                "NÃO APLICÁVEL — USO EXCLUSIVO AUTOMOTIVO",
            }:
                tag = "atencao"
            elif conferencia in {"VALOR MENOR QUE O CALCULADO", "VALOR MAIOR QUE O CALCULADO"}:
                tag = "divergente"
            else:
                tag = "revisar"
            self.tree.insert(
                "",
                tk.END,
                iid=f"item_{numero}",
                tags=(tag,),
                values=(
                    numero,
                    item.get("codigo", ""),
                    item.get("ncm", ""),
                    item.get("descricao", ""),
                    resultado_item.get("cest", ""),
                    _moeda(resultado_item.get("valor_total_com_ipi")),
                    (
                        f"{_numero_br(resultado_item.get('mva_utilizada'))}% "
                        f"({'AJ.' if str(resultado_item.get('tipo_mva') or '').upper() == 'MVA AJUSTADA' else 'ORIG.'})"
                        if resultado_item.get("mva_utilizada") is not None else "—"
                    ),
                    _moeda(resultado_item.get("icms_proprio_deduzir", resultado_item.get("icms_proprio"))),
                    _moeda(resultado_item.get("icms_st")),
                    _moeda(resultado_item.get("icms_st_xml")),
                    _moeda(resultado_item.get("diferenca_st")),
                    conferencia,
                ),
            )
        resumo = self.resultado.get("resumo") or {}
        self.resumo_var.set(
            f"Itens: {resumo.get('quantidade_itens', 0)}  •  Corretos: {resumo.get('itens_corretos', 0)}  •  "
            f"Pendentes fiscais: {resumo.get('itens_pendentes', 0)}  •  ST não destacado: {resumo.get('itens_st_nao_destacado', 0)}  •  "
            f"Dedução automática: {resumo.get('itens_deducao_automatica', resumo.get('itens_deducao_interestadual', 0))}\n"
            f"ST no XML: {_moeda(resumo.get('total_icms_st_xml'))}  •  "
            f"ST calculado: {_moeda(resumo.get('total_icms_st'))}  •  "
            f"Diferença (calculado - XML): {_moeda(resumo.get('diferenca_total_st'))}"
        )
        self.status_var.set(
            "Conferência concluída. Duplo clique mostra os detalhes; a planilha exportada mantém a memória completa."
        )

    def editar_item(self) -> None:
        if self.nota is None:
            messagebox.showwarning("FiscalPro", "Importe uma NF-e XML primeiro.", parent=self)
            return
        selecionados = self.tree.selection()
        if not selecionados:
            messagebox.showwarning("FiscalPro", "Selecione um item da tabela.", parent=self)
            return
        try:
            numero = int(selecionados[0].split("_")[-1])
        except ValueError:
            return
        item = next((i.para_dict() for i in self.nota.itens if i.numero_item == numero), None)
        if item is None:
            return

        atual = dict(self.ajustes.get(numero, {}))
        # Preenche a janela com os dados efetivamente usados, facilitando ajustes pequenos.
        calc = next(
            (r for r in self.resultado.get("itens", []) if int((r.get("item") or {}).get("numero_item") or 0) == numero),
            {},
        )
        for chave in (
            "mva_original", "aliquota_interestadual", "aliquota_interna",
            "aliquota_fcp", "icms_proprio", "aplicabilidade_7318", "finalidade_automotiva",
        ):
            if chave not in atual and calc.get(chave) not in (None, ""):
                atual[chave] = calc.get(chave)

        def salvar(dados: Dict[str, Any]) -> None:
            self.ajustes[numero] = dados
            self.recalcular()
            self.status_var.set(f"Item {numero} ajustado e recalculado.")

        _JanelaEditarItem(self, item=item, ajuste=atual, ao_salvar=salvar)

    def gerar_planilha(self) -> None:
        if not self.resultado:
            self.recalcular()
        if not self.resultado or self.nota is None:
            return

        nome = f"NFe_{self.nota.numero or 'XML'}_ICMS_ST_MG.xlsx"
        caminho = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar planilha do cálculo de ICMS-ST",
            defaultextension=".xlsx",
            initialfile=nome,
            filetypes=[("Planilha Excel", "*.xlsx")],
        )
        if not caminho:
            return
        try:
            arquivo = ExportadorXMLICMSSTXLSX.exportar(self.resultado, caminho)
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível gerar a planilha:\n{erro}", parent=self)
            return
        self.status_var.set(f"Planilha gerada: {arquivo}")
        messagebox.showinfo(
            "FiscalPro",
            "Planilha gerada com sucesso.\n\n"
            "Ela contém Valor do item + IPI, ST informado no XML, ST calculado, diferença, situação, classificação do NCM 7318 e fonte oficial.",
            parent=self,
        )
