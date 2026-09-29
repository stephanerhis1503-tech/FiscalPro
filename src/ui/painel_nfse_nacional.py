"""Painel integrado de NFS-e Nacional (ADN) do FiscalPro."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Canvas, Frame, Label, StringVar, BooleanVar, Entry
from tkinter import filedialog, messagebox, ttk

from src.nfse.adn_client import ErroADN
from src.nfse.servico import ServicoNFSeNacional

from .estilos import COR_BORDA, COR_CARD, COR_DESTAQUE, COR_FUNDO, COR_PRIMARIA, COR_TEXTO, COR_TEXTO_SUAVE, FONTE_NORMAL


class PainelNFSeNacional(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.servico = ServicoNFSeNacional()
        self.empresas = []
        self.registros = []
        self.empresa_id_edicao = None
        self._montar()
        self._carregar_empresas()
        self._consultar_local()

    @staticmethod
    def _data_iso(texto: str) -> str:
        texto = str(texto or "").strip()
        if not texto:
            return ""
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(texto, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        raise ValueError("Data inválida. Use DD/MM/AAAA.")

    @staticmethod
    def _moeda(v) -> str:
        return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _card(self, master):
        return Frame(master, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_BORDA)

    def _montar(self):
        cab = self._card(self)
        cab.pack(fill=X, padx=10, pady=(7, 6))
        Frame(cab, bg=COR_DESTAQUE, height=3).pack(fill=X)
        miolo = Frame(cab, bg=COR_CARD, padx=12, pady=8)
        miolo.pack(fill=X)
        Label(miolo, text="NFS-e Nacional • ADN", bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        Label(
            miolo,
            text="As empresas vêm do Cadastro Central. Configure aqui apenas certificado A1/ambiente, sincronize NFS-e e gere Excel ou XML em lote. A senha do certificado não é gravada.",
            bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=FONTE_NORMAL, justify=LEFT,
        ).pack(anchor="w", pady=(2, 0))

        corpo = ttk.Panedwindow(self, orient="horizontal")
        corpo.pack(fill=BOTH, expand=True, padx=10, pady=(0, 8))
        esquerda = ttk.Frame(corpo, style="Page.TFrame", width=390)
        direita = ttk.Frame(corpo, style="Page.TFrame")
        corpo.add(esquerda, weight=0)
        corpo.add(direita, weight=1)
        self._montar_empresas(esquerda)
        self._montar_consulta(direita)

    def _montar_empresas(self, master):
        # O formulário da NFS-e é mais alto que a área útil em telas de 768 px
        # (e também quando a escala do Windows está acima de 100%).  Mantemos
        # todos os campos acessíveis colocando SOMENTE o painel esquerdo em uma
        # área rolável. O painel de consulta à direita continua fixo.
        rolagem = Frame(master, bg=COR_FUNDO)
        rolagem.pack(fill=BOTH, expand=True, padx=(0, 5))

        canvas = Canvas(rolagem, bg=COR_FUNDO, highlightthickness=0, bd=0)
        barra_y = ttk.Scrollbar(rolagem, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=barra_y.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        barra_y.pack(side=RIGHT, fill=Y)

        conteudo = Frame(canvas, bg=COR_FUNDO)
        janela_canvas = canvas.create_window((0, 0), window=conteudo, anchor="nw")

        def atualizar_rolagem(_evt=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def ajustar_largura(evt):
            canvas.itemconfigure(janela_canvas, width=max(1, evt.width))

        def rolar_mouse(evt):
            delta = getattr(evt, "delta", 0)
            if delta:
                canvas.yview_scroll(-1 if delta > 0 else 1, "units")

        conteudo.bind("<Configure>", atualizar_rolagem)
        canvas.bind("<Configure>", ajustar_largura)
        # Ativa a roda apenas enquanto o mouse estiver sobre o painel esquerdo.
        conteudo.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", rolar_mouse))
        conteudo.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        card = self._card(conteudo)
        card.pack(fill=X, expand=True)
        Label(card, text="Empresas do Cadastro Central e certificado A1", bg=COR_CARD, fg=COR_TEXTO, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 6))

        lista_box = Frame(card, bg=COR_CARD)
        lista_box.pack(fill=X, padx=12)
        self.lista_empresas = ttk.Treeview(lista_box, columns=("cnpj", "nsu"), show="headings", height=5)
        self.lista_empresas.heading("cnpj", text="Empresa / CNPJ")
        self.lista_empresas.heading("nsu", text="Últ. NSU")
        self.lista_empresas.column("cnpj", width=255, anchor="w")
        self.lista_empresas.column("nsu", width=80, anchor="center")
        self.lista_empresas.pack(fill=X)
        self.lista_empresas.bind("<<TreeviewSelect>>", self._selecionar_empresa)

        form = Frame(card, bg=COR_CARD)
        form.pack(fill=X, padx=12, pady=(8, 0))
        self.var_nome = StringVar()
        self.var_cnpj = StringVar()
        self.var_cert = StringVar()
        self.var_senha = StringVar()
        self.var_ambiente = StringVar(value="PRODUCAO")
        for linha, (rotulo, var) in enumerate((("Nome da empresa", self.var_nome), ("CNPJ", self.var_cnpj))):
            Label(form, text=rotulo, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).grid(row=linha*2, column=0, columnspan=2, sticky="w", pady=(3, 2))
            ttk.Entry(form, textvariable=var, state="readonly").grid(row=linha*2+1, column=0, columnspan=2, sticky="ew")
        Label(form, text="Certificado A1 (.pfx/.p12)", bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).grid(row=4, column=0, columnspan=2, sticky="w", pady=(7, 2))
        ttk.Entry(form, textvariable=self.var_cert).grid(row=5, column=0, sticky="ew")
        ttk.Button(form, text="…", width=3, command=self._escolher_cert).grid(row=5, column=1, padx=(4, 0))
        Label(form, text="Senha do A1 (não será salva)", bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).grid(row=6, column=0, columnspan=2, sticky="w", pady=(7, 2))
        Entry(form, textvariable=self.var_senha, show="•", relief="solid", bd=1).grid(row=7, column=0, columnspan=2, sticky="ew", ipady=3)
        Label(form, text="Ambiente", bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).grid(row=8, column=0, sticky="w", pady=(7, 2))
        ttk.Combobox(form, textvariable=self.var_ambiente, values=("PRODUCAO", "HOMOLOGACAO"), state="readonly", width=15).grid(row=9, column=0, sticky="w")
        form.columnconfigure(0, weight=1)

        botoes = Frame(card, bg=COR_CARD)
        botoes.pack(fill=X, padx=12, pady=10)
        ttk.Button(botoes, text="Cadastro de empresas", command=self._abrir_cadastro_central, style="Secondary.TButton").pack(side=LEFT, expand=True, fill=X, padx=(0, 3))
        ttk.Button(botoes, text="Atualizar lista", command=self._atualizar_lista_central, style="Secondary.TButton").pack(side=LEFT, expand=True, fill=X, padx=3)
        ttk.Button(botoes, text="Salvar certificado", command=self._salvar, style="Primary.TButton").pack(side=LEFT, expand=True, fill=X, padx=(3, 0))

        ttk.Separator(card).pack(fill=X, padx=12, pady=(0, 8))
        self.var_status = StringVar(value="Selecione uma empresa do Cadastro Central e configure o certificado A1.")
        Label(card, textvariable=self.var_status, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8), wraplength=340, justify=LEFT).pack(anchor="w", padx=12, pady=(0, 8))
        ttk.Button(card, text="Validar certificado", command=self._validar_certificado, style="Secondary.TButton").pack(fill=X, padx=12, pady=(0, 5))
        ttk.Button(card, text="Testar conexão com ADN", command=self._testar_conexao, style="Secondary.TButton").pack(fill=X, padx=12, pady=5)
        ttk.Button(card, text="Sincronizar NFS-e agora", command=self._sincronizar, style="Accent.TButton").pack(fill=X, padx=12, pady=(5, 12))

    def _montar_consulta(self, master):
        filtros = self._card(master)
        filtros.pack(fill=X, padx=(5, 0), pady=(0, 6))
        top = Frame(filtros, bg=COR_CARD, padx=10, pady=8)
        top.pack(fill=X)
        self.var_empresa_filtro = StringVar(value="Todas as empresas")
        self.var_inicio = StringVar()
        self.var_fim = StringVar()
        self.var_direcao = StringVar(value="EMITIDA")
        self.var_busca = StringVar()
        self.combo_empresa_filtro = None
        campos = (("Empresa", self.var_empresa_filtro, 24), ("De", self.var_inicio, 12), ("Até", self.var_fim, 12), ("Tipo", self.var_direcao, 14), ("Buscar", self.var_busca, 24))
        for col, (rot, var, largura) in enumerate(campos):
            box = Frame(top, bg=COR_CARD)
            box.grid(row=0, column=col, sticky="ew", padx=(0, 6))
            Label(box, text=rot, bg=COR_CARD, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 8)).pack(anchor="w")
            if rot == "Tipo":
                ttk.Combobox(box, textvariable=var, values=("TODAS", "EMITIDA", "RECEBIDA", "INTERMEDIADA"), state="readonly", width=largura).pack(fill=X)
            elif rot == "Empresa":
                self.combo_empresa_filtro = ttk.Combobox(box, textvariable=var, values=("Todas as empresas",), state="readonly", width=largura)
                self.combo_empresa_filtro.pack(fill=X)
            else:
                ttk.Entry(box, textvariable=var, width=largura).pack(fill=X)
            top.columnconfigure(col, weight=2 if rot in {"Empresa", "Buscar"} else 1)
        ttk.Button(top, text="Consultar", command=self._consultar_local, style="Primary.TButton").grid(row=0, column=5, sticky="sew", padx=(2, 0))

        barra = Frame(master, bg=COR_FUNDO)
        barra.pack(fill=X, padx=(5, 0), pady=(0, 6))
        self.lbl_resumo = Label(barra, text="0 registro(s)", bg=COR_FUNDO, fg=COR_TEXTO_SUAVE, font=("Segoe UI", 9, "bold"))
        self.lbl_resumo.pack(side=LEFT)
        ttk.Button(barra, text="Exportar Excel", command=self._exportar_excel, style="Secondary.TButton").pack(side=RIGHT, padx=(5, 0))
        ttk.Button(barra, text="Exportar XMLs", command=self._exportar_xmls, style="Secondary.TButton").pack(side=RIGHT)

        grade_box = self._card(master)
        grade_box.pack(fill=BOTH, expand=True, padx=(5, 0))
        cols = ("empresa", "data", "numero", "cliente", "valor", "situacao", "nsu")
        self.grade = ttk.Treeview(grade_box, columns=cols, show="headings", selectmode="extended")
        titulos = {"empresa":"Empresa", "data":"Emissão", "numero":"NFS-e", "cliente":"Tomador / Prestador", "valor":"Valor", "situacao":"Situação", "nsu":"NSU"}
        larguras = {"empresa":155, "data":90, "numero":90, "cliente":260, "valor":110, "situacao":90, "nsu":80}
        for c in cols:
            self.grade.heading(c, text=titulos[c])
            self.grade.column(c, width=larguras[c], anchor="e" if c=="valor" else "w")
        sy = ttk.Scrollbar(grade_box, orient="vertical", command=self.grade.yview)
        sx = ttk.Scrollbar(grade_box, orient="horizontal", command=self.grade.xview)
        self.grade.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.grade.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        grade_box.rowconfigure(0, weight=1)
        grade_box.columnconfigure(0, weight=1)

    def _escolher_cert(self):
        arq = filedialog.askopenfilename(title="Selecione o certificado A1", filetypes=[("Certificado A1", "*.pfx *.p12"), ("Todos", "*.*")])
        if arq:
            self.var_cert.set(arq)

    def _abrir_cadastro_central(self):
        self.winfo_toplevel().event_generate("<<AbrirCadastroEmpresas>>", when="tail")

    def _atualizar_lista_central(self):
        atual = self.empresa_id_edicao
        self._carregar_empresas(selecionar=atual)
        self._consultar_local()
        if self.empresas:
            self.var_status.set("Lista atualizada a partir do Cadastro Central.")
        else:
            self.var_status.set("Nenhuma empresa com CNPJ disponível. Complete o CNPJ no Cadastro Central.")

    def _novo(self):
        # Mantido apenas por compatibilidade interna. A inclusão de empresa
        # agora é feita exclusivamente no Cadastro Central.
        self.empresa_id_edicao = None
        for var in (self.var_nome, self.var_cnpj, self.var_cert, self.var_senha):
            var.set("")
        self.var_ambiente.set("PRODUCAO")
        self.lista_empresas.selection_remove(self.lista_empresas.selection())

    def _salvar(self):
        if not self.empresa_id_edicao:
            messagebox.showwarning(
                "NFS-e Nacional",
                "Selecione uma empresa do Cadastro Central primeiro.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            eid = self.servico.salvar_empresa(
                nome=self.var_nome.get(), cnpj=self.var_cnpj.get(), certificado_path=self.var_cert.get(),
                ambiente=self.var_ambiente.get(), empresa_id=self.empresa_id_edicao,
            )
            self.empresa_id_edicao = eid
            self._carregar_empresas(selecionar=eid)
            self.var_status.set("Certificado/ambiente salvos. Nome e CNPJ continuam controlados pelo Cadastro Central.")
        except Exception as exc:
            messagebox.showerror("NFS-e Nacional", str(exc), parent=self.winfo_toplevel())

    def _excluir(self):
        messagebox.showinfo(
            "NFS-e Nacional",
            "A empresa não é excluída por este módulo. Use o Cadastro Central de Empresas; documentos e NSU permanecem preservados.",
            parent=self.winfo_toplevel(),
        )

    def _carregar_empresas(self, selecionar=None):
        self.empresas = self.servico.listar_empresas()
        self.empresa_filtro_map = {f"{e['nome']} • {e['cnpj']}": int(e['id']) for e in self.empresas}
        if getattr(self, "combo_empresa_filtro", None) is not None:
            valores = ("Todas as empresas", *self.empresa_filtro_map.keys())
            self.combo_empresa_filtro.configure(values=valores)
            if self.var_empresa_filtro.get() not in valores:
                self.var_empresa_filtro.set("Todas as empresas")
        self.lista_empresas.delete(*self.lista_empresas.get_children())
        alvo = None
        for e in self.empresas:
            iid = str(e["id"])
            self.lista_empresas.insert("", END, iid=iid, values=(f"{e['nome']}\n{e['cnpj']}", e.get("ultimo_nsu", 0)))
            if selecionar and int(e["id"]) == int(selecionar):
                alvo = iid
        if alvo:
            self.lista_empresas.selection_set(alvo)
            self.lista_empresas.see(alvo)
            self._selecionar_empresa()

    def _selecionar_empresa(self, _evt=None):
        sel = self.lista_empresas.selection()
        if not sel:
            return
        eid = int(sel[0])
        e = next((x for x in self.empresas if int(x["id"]) == eid), None)
        if not e:
            return
        self.empresa_id_edicao = eid
        self.var_nome.set(e["nome"])
        self.var_cnpj.set(e["cnpj"])
        self.var_cert.set(e.get("certificado_path") or "")
        self.var_senha.set("")
        self.var_ambiente.set(e.get("ambiente") or "PRODUCAO")
        self.var_status.set(f"Último NSU sincronizado: {e.get('ultimo_nsu', 0)}")

    def _requer_empresa_senha(self):
        if not self.empresa_id_edicao:
            raise ValueError("Selecione e salve uma empresa primeiro.")
        senha = self.var_senha.get()
        if not senha:
            raise ValueError("Digite a senha do certificado A1.")
        return senha

    def _validar_certificado(self):
        try:
            senha = self._requer_empresa_senha()
            info = self.servico.validar_certificado(self.var_cert.get(), senha)
            self.var_status.set(f"Certificado válido • {info.titular} • validade até {info.valido_ate}")
            messagebox.showinfo("Certificado A1", f"Titular: {info.titular}\nEmissor: {info.emissor}\nValidade: {info.valido_de} até {info.valido_ate}", parent=self.winfo_toplevel())
        except Exception as exc:
            messagebox.showerror("Certificado A1", str(exc), parent=self.winfo_toplevel())

    def _executar_thread(self, tarefa, ao_finalizar):
        def worker():
            try:
                resultado = tarefa()
                erro = None
            except Exception as exc:
                resultado, erro = None, exc
            self.after(0, lambda: ao_finalizar(resultado, erro))
        threading.Thread(target=worker, daemon=True).start()

    def _testar_conexao(self):
        try:
            senha = self._requer_empresa_senha()
        except Exception as exc:
            messagebox.showwarning("NFS-e Nacional", str(exc), parent=self.winfo_toplevel())
            return
        self.var_status.set("Testando conexão mTLS com o ADN…")
        self._executar_thread(
            lambda: self.servico.testar_conexao(self.empresa_id_edicao, senha),
            lambda r, e: self._fim_teste(r, e),
        )

    def _fim_teste(self, resultado, erro):
        if erro:
            self.var_status.set("Falha na conexão com o ADN.")
            messagebox.showerror("NFS-e Nacional", str(erro), parent=self.winfo_toplevel())
            return
        self.var_status.set(f"Conexão OK • Status ADN: {resultado['status'] or 'sem status'}")
        messagebox.showinfo("NFS-e Nacional", f"Conexão realizada com sucesso.\nStatus: {resultado['status']}\nDocumentos no retorno de teste: {resultado['quantidade']}", parent=self.winfo_toplevel())

    def _sincronizar(self):
        try:
            senha = self._requer_empresa_senha()
        except Exception as exc:
            messagebox.showwarning("NFS-e Nacional", str(exc), parent=self.winfo_toplevel())
            return
        self.var_status.set("Iniciando sincronização com o ADN…")
        eid = self.empresa_id_edicao
        self._executar_thread(
            lambda: self.servico.sincronizar(eid, senha, progresso=lambda txt: self.after(0, lambda t=txt: self.var_status.set(t))),
            lambda r, e: self._fim_sync(r, e),
        )

    def _fim_sync(self, resultado, erro):
        if erro:
            self.var_status.set("Sincronização interrompida.")
            messagebox.showerror("NFS-e Nacional", str(erro), parent=self.winfo_toplevel())
            return
        if resultado['processados'] == 0 and str(resultado.get('status') or '').upper() == 'NENHUM_DOCUMENTO_LOCALIZADO':
            self.var_status.set("Conexão OK • o ADN não encontrou documentos a partir do NSU consultado.")
            texto = (
                "Conexão com o ADN realizada normalmente.\n\n"
                "Nenhum documento foi localizado para este CNPJ a partir do NSU consultado.\n"
                "Isso não indica erro no certificado."
            )
        else:
            self.var_status.set(f"Sincronização concluída • {resultado['processados']} documento(s) • último NSU {resultado['ultimo_nsu']}")
            texto = f"Sincronização concluída.\nProcessados: {resultado['processados']}\nÚltimo NSU: {resultado['ultimo_nsu']}"
        self._carregar_empresas(selecionar=self.empresa_id_edicao)
        self._consultar_local()
        messagebox.showinfo("NFS-e Nacional", texto, parent=self.winfo_toplevel())

    def _consultar_local(self):
        try:
            inicio = self._data_iso(self.var_inicio.get()) if hasattr(self, "var_inicio") else ""
            fim = self._data_iso(self.var_fim.get()) if hasattr(self, "var_fim") else ""
            filtro_empresa = self.var_empresa_filtro.get() if hasattr(self, "var_empresa_filtro") else "Todas as empresas"
            if filtro_empresa != "Todas as empresas" and filtro_empresa in getattr(self, "empresa_filtro_map", {}):
                ids = [self.empresa_filtro_map[filtro_empresa]]
            else:
                ids = [int(e["id"]) for e in self.empresas] if self.empresas else []
            self.registros = self.servico.listar_documentos(
                empresa_ids=ids or None, inicio=inicio, fim=fim,
                direcao=self.var_direcao.get() if hasattr(self, "var_direcao") else "TODAS",
                busca=self.var_busca.get() if hasattr(self, "var_busca") else "",
            )
        except Exception as exc:
            messagebox.showerror("NFS-e Nacional", str(exc), parent=self.winfo_toplevel())
            return
        self.grade.delete(*self.grade.get_children())
        total = 0.0
        for idx, r in enumerate(self.registros):
            if r.get("direcao") == "EMITIDA":
                contraparte = r.get("tomador_nome") or r.get("tomador_doc")
            else:
                contraparte = r.get("prestador_nome") or r.get("prestador_doc")
            valor = float(r.get("valor_servico") or 0)
            total += valor if not r.get("tipo_evento") else 0
            self.grade.insert("", END, iid=str(idx), values=(r.get("empresa_nome"), r.get("data_emissao") or r.get("competencia"), r.get("numero_nfse"), contraparte, self._moeda(valor), r.get("situacao"), r.get("nsu")))
        self.lbl_resumo.config(text=f"{len(self.registros)} registro(s) • Total: {self._moeda(total)}")

    def _registros_exportacao(self):
        selecionados = self.grade.selection()
        if selecionados:
            return [self.registros[int(i)] for i in selecionados]
        return self.registros

    def _exportar_excel(self):
        regs = self._registros_exportacao()
        if not regs:
            messagebox.showwarning("NFS-e Nacional", "Não há registros para exportar.", parent=self.winfo_toplevel())
            return
        arq = filedialog.asksaveasfilename(title="Salvar relatório NFS-e", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], initialfile=f"Relatorio_NFSe_{datetime.now():%Y%m%d}.xlsx")
        if arq:
            destino = self.servico.exportar_excel(regs, arq)
            messagebox.showinfo("NFS-e Nacional", f"Relatório gerado:\n{destino}", parent=self.winfo_toplevel())

    def _exportar_xmls(self):
        regs = self._registros_exportacao()
        if not regs:
            messagebox.showwarning("NFS-e Nacional", "Não há registros para exportar.", parent=self.winfo_toplevel())
            return
        pasta = filedialog.askdirectory(title="Escolha a pasta para salvar os XMLs")
        if pasta:
            destino, total = self.servico.exportar_xmls(regs, pasta)
            messagebox.showinfo("NFS-e Nacional", f"{total} XML(s) salvo(s) em:\n{destino}", parent=self.winfo_toplevel())
