"""Janela de comparação de cenários tributários — FiscalPro 17.8.37."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict

from src.services.comparador_cenarios_tributarios_service import (
    ComparadorCenariosTributariosService,
)
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.ui.layout_responsivo import dimensionar_janela


_UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
)
_OPERACOES = ("ENTRADA", "SAÍDA", "DEVOLUÇÃO", "TRANSFERÊNCIA", "IMPORTAÇÃO", "EXPORTAÇÃO")


class JanelaCompararCenariosTributarios(tk.Toplevel):
    """Compara o mesmo NCM em dois contextos sem criar lógica fiscal paralela."""

    def __init__(
        self,
        master=None,
        ncm: str = "",
        contexto_base: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(master)
        self.title("FiscalPro — Comparar Cenários Tributários")
        dimensionar_janela(self, 1260, 820, 940, 620)
        self.contexto_base = dict(contexto_base or {})
        self.resultado: Dict[str, Any] | None = None
        self._resultado_completo = None

        self.ncm_var = tk.StringVar(value=str(ncm or ""))
        self.resumo_var = tk.StringVar(value="Configure os dois cenários e clique em Comparar.")
        self.identificacao_var = tk.StringVar(value="Nenhum NCM comparado.")
        self.somente_diferencas_var = tk.BooleanVar(value=False)

        empresa_a = str(self.contexto_base.get("empresa") or "").strip()
        if empresa_a == "Todas as empresas":
            empresa_a = ""
        empresa_b = ""
        if empresa_a:
            empresa_b = "Mega Motos Trilha" if empresa_a != "Mega Motos Trilha" else "Mega Motos Comércio"

        self.a_empresa = tk.StringVar(value=empresa_a)
        self.a_operacao = tk.StringVar(value=str(self.contexto_base.get("operacao") or "SAÍDA"))
        self.a_uf_origem = tk.StringVar(value=str(self.contexto_base.get("uf_origem") or "MG"))
        self.a_uf_destino = tk.StringVar(value=str(self.contexto_base.get("uf_destino") or "MG"))
        self.a_regime_info = tk.StringVar(value="Selecione a empresa do cenário A.")

        self.b_empresa = tk.StringVar(value=empresa_b)
        self.b_operacao = tk.StringVar(value=str(self.contexto_base.get("operacao") or "SAÍDA"))
        self.b_uf_origem = tk.StringVar(value=str(self.contexto_base.get("uf_origem") or "MG"))
        self.b_uf_destino = tk.StringVar(value=str(self.contexto_base.get("uf_destino") or "MG"))
        self.b_regime_info = tk.StringVar(value="Selecione a empresa do cenário B.")

        self._criar_interface()
        self._atualizar_regime("A")
        self._atualizar_regime("B")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.entry_ncm.bind("<Return>", lambda _e: self.comparar())
        self.entry_ncm.bind("<KP_Enter>", lambda _e: self.comparar())
        self.entry_ncm.bind("<KeyRelease>", lambda e: None if e.keysym in ("Return", "KP_Enter") else self._marcar_comparacao_desatualizada())
        if self.ncm_var.get().strip() and self.a_empresa.get().strip() and self.b_empresa.get().strip():
            self.after(140, self.comparar)

    def _criar_interface(self) -> None:
        cabecalho = tk.Frame(self, bg="#245A85", padx=18, pady=12)
        cabecalho.pack(fill=tk.X)
        tk.Label(
            cabecalho,
            text="Comparar Cenários Tributários",
            bg="#245A85",
            fg="white",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            cabecalho,
            text="Veja lado a lado o que muda por empresa, regime e rota — usando os mesmos motores da Ficha Inteligente.",
            bg="#245A85",
            fg="#E7F0F7",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

        corpo = ttk.Frame(self, padding=12)
        corpo.pack(fill=tk.BOTH, expand=True)

        pesquisa = ttk.LabelFrame(corpo, text="Produto", padding=10)
        pesquisa.pack(fill=tk.X)
        pesquisa.columnconfigure(0, weight=1)
        ttk.Label(pesquisa, text="NCM (8 dígitos)").grid(row=0, column=0, sticky="w", pady=(0, 3))
        self.entry_ncm = ttk.Entry(pesquisa, textvariable=self.ncm_var, font=("Segoe UI", 11))
        self.entry_ncm.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(pesquisa, text="COMPARAR CENÁRIOS", command=self.comparar).grid(row=1, column=1, sticky="ew")

        cenarios = ttk.Frame(corpo)
        cenarios.pack(fill=tk.X, pady=(10, 8))
        cenarios.columnconfigure(0, weight=1, uniform="cenario")
        cenarios.columnconfigure(1, weight=1, uniform="cenario")
        self._criar_cenario(cenarios, "A", 0, self.a_empresa, self.a_operacao, self.a_uf_origem, self.a_uf_destino, self.a_regime_info)
        self._criar_cenario(cenarios, "B", 1, self.b_empresa, self.b_operacao, self.b_uf_origem, self.b_uf_destino, self.b_regime_info)

        cab_resultado = tk.Frame(corpo, bg="#F3F6FA", highlightthickness=1, highlightbackground="#DCE5EF", padx=12, pady=8)
        cab_resultado.pack(fill=tk.X, pady=(0, 6))
        tk.Label(cab_resultado, textvariable=self.identificacao_var, bg="#F3F6FA", fg="#173B5E", font=("Segoe UI", 11, "bold"), anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Checkbutton(
            cab_resultado,
            text="Mostrar somente diferenças",
            variable=self.somente_diferencas_var,
            command=self._renderizar_resultado,
        ).pack(side=tk.RIGHT)

        destaques = tk.Frame(
            corpo,
            bg="#FFFFFF",
            highlightthickness=1,
            highlightbackground="#DCE5EF",
            padx=10,
            pady=8,
        )
        destaques.pack(fill=tk.X, pady=(0, 7))
        tk.Label(
            destaques,
            text="Destaques da comparação",
            bg="#FFFFFF",
            fg="#173B5E",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 6))
        self.destaques_frame = tk.Frame(destaques, bg="#FFFFFF")
        self.destaques_frame.pack(fill=tk.X)
        self._renderizar_destaques()

        resumo_inteligente = tk.Frame(
            corpo,
            bg="#F7FAFD",
            highlightthickness=1,
            highlightbackground="#BFD2E4",
            padx=11,
            pady=8,
        )
        resumo_inteligente.pack(fill=tk.X, pady=(0, 7))
        topo_resumo = tk.Frame(resumo_inteligente, bg="#F7FAFD")
        topo_resumo.pack(fill=tk.X, pady=(0, 5))
        tk.Label(
            topo_resumo,
            text="Resumo inteligente da comparação",
            bg="#F7FAFD",
            fg="#173B5E",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT)
        self.resumo_badge_var = tk.StringVar(value="LEITURA ORIENTATIVA")
        tk.Label(
            topo_resumo,
            textvariable=self.resumo_badge_var,
            bg="#D9E9F5",
            fg="#173B5E",
            font=("Segoe UI", 7, "bold"),
            padx=7,
            pady=2,
        ).pack(side=tk.RIGHT)
        self.resumo_inteligente_frame = tk.Frame(resumo_inteligente, bg="#F7FAFD")
        self.resumo_inteligente_frame.pack(fill=tk.X)
        self._renderizar_resumo_inteligente()

        ttk.Label(corpo, text="Detalhes comparativos", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        tabela_frame = ttk.Frame(corpo)
        tabela_frame.pack(fill=tk.BOTH, expand=True)
        tabela_frame.rowconfigure(0, weight=1)
        tabela_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tabela_frame,
            columns=("campo", "cenario_a", "cenario_b", "status"),
            show="headings",
            height=6,
        )
        self.tree.heading("campo", text="Campo")
        self.tree.heading("cenario_a", text="Cenário A")
        self.tree.heading("cenario_b", text="Cenário B")
        self.tree.heading("status", text="Comparação")
        self.tree.column("campo", width=150, minwidth=120, anchor="w")
        self.tree.column("cenario_a", width=390, minwidth=250, anchor="w")
        self.tree.column("cenario_b", width=390, minwidth=250, anchor="w")
        self.tree.column("status", width=105, minwidth=90, anchor="center")
        barra = ttk.Scrollbar(tabela_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("diferente", background="#FFF3CD", foreground="#6B5200")
        self.tree.tag_configure("igual", background="#F3FAF4", foreground="#255B2B")

        resumo = tk.Frame(corpo, bg="#EAF2F8", highlightthickness=1, highlightbackground="#C9DCEA", padx=12, pady=9)
        resumo.pack(fill=tk.X, pady=(8, 0))
        tk.Label(resumo, textvariable=self.resumo_var, bg="#EAF2F8", fg="#173B5E", font=("Segoe UI", 9, "bold"), anchor="w", justify=tk.LEFT, wraplength=1100).pack(fill=tk.X)

        rodape = ttk.Frame(self, padding=(12, 0, 12, 12))
        rodape.pack(fill=tk.X)
        ttk.Label(
            rodape,
            text="Escolha 'USAR ESTE CENÁRIO' no quadro A ou B para levar o resultado direto à Ficha Inteligente.",
            foreground="#64748B",
        ).pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

    def _criar_cenario(self, master, letra, coluna, empresa_var, operacao_var, ufo_var, ufd_var, regime_var) -> None:
        cor = "#173B5E" if letra == "A" else "#5B4B8A"
        quadro = tk.Frame(master, bg="#FFFFFF", highlightthickness=1, highlightbackground="#D7E0EA", padx=12, pady=10)
        quadro.grid(row=0, column=coluna, sticky="nsew", padx=(0, 6) if coluna == 0 else (6, 0))
        tk.Frame(quadro, bg=cor, height=4).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 7))
        tk.Label(quadro, text=f"CENÁRIO {letra}", bg="#FFFFFF", fg=cor, font=("Segoe UI", 11, "bold")).grid(row=1, column=0, columnspan=4, sticky="w")

        campos = (
            ("Empresa", empresa_var, EmpresasRegimesService.listar_empresas()),
            ("Operação", operacao_var, _OPERACOES),
            ("UF origem", ufo_var, _UFS),
            ("UF destino", ufd_var, _UFS),
        )
        for indice, (rotulo, variavel, valores) in enumerate(campos):
            tk.Label(quadro, text=rotulo, bg="#FFFFFF", fg="#64748B", font=("Segoe UI", 8)).grid(row=2, column=indice, sticky="w", pady=(8, 3))
            combo = ttk.Combobox(quadro, textvariable=variavel, values=valores, state="readonly")
            combo.grid(row=3, column=indice, sticky="ew", padx=(0, 6 if indice < 3 else 0))
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _e, lado=letra, eh_empresa=(indice == 0): self._cenario_alterado(lado, eh_empresa),
            )
            quadro.columnconfigure(indice, weight=1)
        tk.Label(quadro, textvariable=regime_var, bg="#FFFFFF", fg=cor, font=("Segoe UI", 8, "bold"), anchor="w").grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        botao = tk.Button(
            quadro,
            text="USAR ESTE CENÁRIO",
            command=lambda lado=letra: self._abrir_ficha(lado),
            state=tk.DISABLED,
            bg=cor,
            fg="white",
            activebackground=cor,
            activeforeground="white",
            disabledforeground="#D8E1E8",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=5,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        botao.grid(row=4, column=3, sticky="e", pady=(8, 0))
        if letra == "A":
            self.btn_usar_a = botao
        else:
            self.btn_usar_b = botao

    def _atualizar_regime(self, lado: str) -> None:
        empresa_var = self.a_empresa if lado == "A" else self.b_empresa
        info_var = self.a_regime_info if lado == "A" else self.b_regime_info
        empresa = empresa_var.get().strip()
        regime = EmpresasRegimesService.resolver_regime(empresa, "")
        info_var.set(
            EmpresasRegimesService.descricao_regime(empresa, regime)
            if regime else f"Selecione a empresa do cenário {lado}."
        )

    def _cenario_alterado(self, lado: str, eh_empresa: bool = False) -> None:
        if eh_empresa:
            self._atualizar_regime(lado)
        self._marcar_comparacao_desatualizada()

    def _marcar_comparacao_desatualizada(self) -> None:
        """Invalida imediatamente qualquer resultado que não corresponda mais aos campos visíveis."""
        if not self.resultado:
            return

        # Segurança visual: nunca mantenha na tela valores calculados para um
        # cenário anterior depois que NCM/empresa/operação/UF forem alterados.
        self.resultado = None
        self._resultado_completo = None
        self.btn_usar_a.configure(state=tk.DISABLED)
        self.btn_usar_b.configure(state=tk.DISABLED)
        self.identificacao_var.set("Configuração alterada — compare novamente.")
        self.resumo_var.set(
            "Os campos do cenário mudaram. O resultado anterior foi limpo para evitar leitura ou uso de dados desatualizados. Compare novamente antes de usar um dos cenários."
        )
        self._renderizar_destaques()
        render_resumo = getattr(self, "_renderizar_resumo_inteligente", None)
        if callable(render_resumo):
            render_resumo()
        self._renderizar_resultado()

    @staticmethod
    def _encurtar_card(valor: Any, limite: int = 145) -> str:
        texto = " ".join(str(valor or "Não informado").split())
        if len(texto) <= limite:
            return texto
        return texto[: limite - 1].rstrip() + "…"

    def _renderizar_destaques(self) -> None:
        if not hasattr(self, "destaques_frame"):
            return
        for filho in self.destaques_frame.winfo_children():
            filho.destroy()

        if not self.resultado:
            tk.Label(
                self.destaques_frame,
                text="As principais diferenças aparecerão aqui em cartões depois da comparação.",
                bg="#FFFFFF",
                fg="#64748B",
                font=("Segoe UI", 8),
            ).pack(anchor="w")
            return

        diferentes = [linha for linha in (self.resultado.get("linhas") or []) if linha.diferente]
        if not diferentes:
            card = tk.Frame(
                self.destaques_frame,
                bg="#F0F9F2",
                highlightthickness=1,
                highlightbackground="#B9DDBF",
                padx=12,
                pady=9,
            )
            card.pack(fill=tk.X)
            tk.Label(card, text="✓ CENÁRIOS EQUIVALENTES", bg="#F0F9F2", fg="#236B2C", font=("Segoe UI", 9, "bold")).pack(anchor="w")
            tk.Label(card, text="Nenhuma diferença principal foi encontrada nos campos comparados.", bg="#F0F9F2", fg="#365B3B", font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))
            return

        self.destaques_frame.columnconfigure(0, weight=1, uniform="destaque")
        self.destaques_frame.columnconfigure(1, weight=1, uniform="destaque")
        for indice, linha in enumerate(diferentes[:4]):
            card = tk.Frame(
                self.destaques_frame,
                bg="#FFF8E6",
                highlightthickness=1,
                highlightbackground="#E9C75C",
                padx=10,
                pady=8,
            )
            card.grid(row=indice // 2, column=indice % 2, sticky="nsew", padx=(0, 5) if indice % 2 == 0 else (5, 0), pady=(0, 6))
            topo = tk.Frame(card, bg="#FFF8E6")
            topo.pack(fill=tk.X)
            tk.Label(topo, text=linha.campo.upper(), bg="#FFF8E6", fg="#6B5200", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
            tk.Label(topo, text="MUDOU", bg="#F3D37A", fg="#5C4700", font=("Segoe UI", 7, "bold"), padx=6, pady=1).pack(side=tk.RIGHT)
            tk.Label(card, text=f"A  {self._encurtar_card(linha.valor_a)}", bg="#FFF8E6", fg="#173B5E", font=("Segoe UI", 8, "bold"), anchor="w", justify=tk.LEFT, wraplength=520).pack(fill=tk.X, pady=(5, 1))
            tk.Label(card, text=f"B  {self._encurtar_card(linha.valor_b)}", bg="#FFF8E6", fg="#5B4B8A", font=("Segoe UI", 8, "bold"), anchor="w", justify=tk.LEFT, wraplength=520).pack(fill=tk.X)

        if len(diferentes) > 4:
            tk.Label(
                self.destaques_frame,
                text=f"+ {len(diferentes) - 4} outra(s) diferença(s) — veja todos os detalhes na tabela abaixo.",
                bg="#FFFFFF",
                fg="#8A6A00",
                font=("Segoe UI", 8, "italic"),
            ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 1))

    @staticmethod
    def _separar_item_resumo(texto: Any) -> tuple[str, str]:
        valor = " ".join(str(texto or "").split()).strip()
        if ":" not in valor:
            return "", valor
        titulo, conteudo = valor.split(":", 1)
        return titulo.strip(), conteudo.strip()

    def _criar_mini_card_resumo(
        self,
        master,
        *,
        titulo: str,
        texto: str,
        coluna: int,
        linha: int,
        cor: str,
        fundo: str,
        borda: str,
        columnspan: int = 1,
        wraplength: int = 360,
    ) -> None:
        card = tk.Frame(
            master,
            bg=fundo,
            highlightthickness=1,
            highlightbackground=borda,
            padx=10,
            pady=8,
        )
        card.grid(
            row=linha,
            column=coluna,
            columnspan=columnspan,
            sticky="nsew",
            padx=(0, 5) if coluna == 0 else (5, 0),
            pady=(0, 6) if linha == 0 else (0, 0),
        )
        tk.Frame(card, bg=cor, height=3).pack(fill=tk.X, pady=(0, 6))
        tk.Label(
            card,
            text=titulo.upper(),
            bg=fundo,
            fg=cor,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            card,
            text=texto or "Sem diferença principal identificada.",
            bg=fundo,
            fg="#294B67",
            font=("Segoe UI", 8),
            anchor="w",
            justify=tk.LEFT,
            wraplength=wraplength,
        ).pack(fill=tk.X, pady=(4, 0))

    def _renderizar_resumo_inteligente(self) -> None:
        if not hasattr(self, "resumo_inteligente_frame"):
            return
        for filho in self.resumo_inteligente_frame.winfo_children():
            filho.destroy()

        if not self.resultado:
            self.resumo_badge_var.set("LEITURA ORIENTATIVA")
            tk.Label(
                self.resumo_inteligente_frame,
                text="Compare os cenários para o FiscalPro resumir as diferenças sem escolher automaticamente um 'melhor' tratamento fiscal.",
                bg="#F7FAFD",
                fg="#64748B",
                font=("Segoe UI", 8),
                anchor="w",
                justify=tk.LEFT,
            ).pack(fill=tk.X)
            return

        resumo = dict(self.resultado.get("resumo_inteligente") or {})
        self.resumo_badge_var.set(str(resumo.get("badge") or "SEM VENCEDOR AUTOMÁTICO"))
        itens = list(resumo.get("itens") or [])

        grupos = {
            "pis": [],
            "icms": [],
            "st": [],
            "pendencias": [],
        }
        for item in itens:
            titulo, conteudo = self._separar_item_resumo(item)
            chave = titulo.casefold()
            texto_card = conteudo or str(item or "").strip()
            if "pis/cofins" in chave:
                grupos["pis"].append(texto_card)
            elif "icms-st" in chave or "icms st" in chave:
                grupos["st"].append(texto_card)
            elif "icms próprio" in chave or chave == "icms":
                grupos["icms"].append(texto_card)
            else:
                prefixo = f"{titulo}: " if titulo else ""
                grupos["pendencias"].append(prefixo + texto_card)

        grade = tk.Frame(self.resumo_inteligente_frame, bg="#F7FAFD")
        grade.pack(fill=tk.X)
        for coluna in range(3):
            grade.columnconfigure(coluna, weight=1, uniform="resumo")

        self._criar_mini_card_resumo(
            grade,
            titulo="PIS / COFINS",
            texto=" ".join(grupos["pis"]) or "Sem diferença principal entre os cenários.",
            coluna=0, linha=0,
            cor="#0F766E", fundo="#F0FDFA", borda="#99D8CF", wraplength=345,
        )
        self._criar_mini_card_resumo(
            grade,
            titulo="ICMS",
            texto=" ".join(grupos["icms"]) or "Sem diferença principal entre os cenários.",
            coluna=1, linha=0,
            cor="#1D4ED8", fundo="#EFF6FF", borda="#B9D0F8", wraplength=345,
        )
        self._criar_mini_card_resumo(
            grade,
            titulo="ICMS-ST",
            texto=" ".join(grupos["st"]) or "Sem diferença principal entre os cenários.",
            coluna=2, linha=0,
            cor="#15803D", fundo="#F0FDF4", borda="#B6E0C2", wraplength=345,
        )

        pendencias = " ".join(grupos["pendencias"]) or "Nenhuma pendência adicional foi resumida."
        self._criar_mini_card_resumo(
            grade,
            titulo="Pendências e segurança",
            texto=pendencias,
            coluna=0, linha=1, columnspan=1,
            cor="#B45309", fundo="#FFFBEB", borda="#F1D59C", wraplength=345,
        )

        conclusao = str(resumo.get("conclusao") or "").strip()
        self._criar_mini_card_resumo(
            grade,
            titulo="Conclusão",
            texto=conclusao or "Leitura orientativa concluída sem vencedor automático.",
            coluna=1, linha=1, columnspan=2,
            cor="#5B4B8A", fundo="#F7F4FB", borda="#CEC5DF", wraplength=735,
        )

    def _contexto(self, lado: str) -> Dict[str, Any]:
        if lado == "A":
            empresa, operacao, ufo, ufd = self.a_empresa, self.a_operacao, self.a_uf_origem, self.a_uf_destino
        else:
            empresa, operacao, ufo, ufd = self.b_empresa, self.b_operacao, self.b_uf_origem, self.b_uf_destino
        nome_empresa = empresa.get().strip()
        return {
            "empresa": nome_empresa,
            "regime": EmpresasRegimesService.resolver_regime(nome_empresa, ""),
            "operacao": operacao.get().strip(),
            "uf_origem": ufo.get().strip(),
            "uf_destino": ufd.get().strip(),
            "finalidade": "REVENDA",
            "contribuinte": "TODOS",
            "origem_mercadoria": "NÃO INFORMADA",
        }

    def comparar(self) -> None:
        ncm = self.ncm_var.get().strip()
        if not self.a_empresa.get().strip() or not self.b_empresa.get().strip():
            messagebox.showwarning("FiscalPro", "Selecione uma empresa nos cenários A e B antes de comparar.", parent=self)
            return
        try:
            self._resultado_completo = ComparadorCenariosTributariosService.comparar(
                ncm, self._contexto("A"), self._contexto("B")
            )
        except ValueError as erro:
            messagebox.showwarning("FiscalPro", str(erro), parent=self)
            return
        except Exception as erro:
            messagebox.showerror("FiscalPro", f"Não foi possível comparar os cenários:\n{erro}", parent=self)
            return

        self.resultado = self._resultado_completo
        descricao = self.resultado.get("descricao") or "Descrição não cadastrada"
        self.identificacao_var.set(f"NCM {self.resultado['ncm']}  •  {descricao}")
        total = int(self.resultado.get("total_diferencas") or 0)
        if total:
            campos = " • ".join(self.resultado.get("campos_diferentes") or [])
            self.resumo_var.set(f"{total} diferença(s) principal(is) encontrada(s): {campos}.")
        else:
            self.resumo_var.set("Nenhuma diferença foi encontrada nos campos principais dos dois cenários.")
        self.btn_usar_a.configure(state=tk.NORMAL)
        self.btn_usar_b.configure(state=tk.NORMAL)
        self._renderizar_destaques()
        self._renderizar_resumo_inteligente()
        self._renderizar_resultado()

    def _renderizar_resultado(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        if not self.resultado:
            return
        somente = bool(self.somente_diferencas_var.get())
        for linha in self.resultado.get("linhas") or []:
            if somente and not linha.diferente:
                continue
            self.tree.insert(
                "", tk.END,
                values=(
                    linha.campo,
                    linha.valor_a,
                    linha.valor_b,
                    "MUDOU" if linha.diferente else "IGUAL",
                ),
                tags=("diferente" if linha.diferente else "igual",),
            )

    def _abrir_ficha(self, lado: str) -> None:
        if not self.resultado:
            return
        cenario = self.resultado["cenario_a" if lado == "A" else "cenario_b"]
        from src.ui.janela_ficha_tributaria import JanelaFichaTributaria
        JanelaFichaTributaria(
            self,
            contexto=dict(cenario.get("contexto") or {}),
            ncm=str(cenario.get("ncm") or ""),
        )
