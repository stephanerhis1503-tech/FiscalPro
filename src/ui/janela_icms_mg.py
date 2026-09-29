"""Tela do Motor ICMS/MG — Sprint 16.6."""

from __future__ import annotations

from datetime import date
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.atualizador_fontes_oficiais import AtualizadorFontesOficiais
from src.services.icms_mg_nacional_service import ICMSMGNacionalService
from src.ui.layout_responsivo import dimensionar_janela
from src.ui.janela_difal_fcp import JanelaDIFALFCP


UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
)


class JanelaICMSMG(tk.Toplevel):
    def __init__(self, master=None, ncm: str = "", descricao: str = ""):
        super().__init__(master)
        self.title("Base ICMS/MG — Alíquota, ST e benefícios")
        dimensionar_janela(self, 980, 790, 760, 590)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        formulario = ttk.LabelFrame(self, text="Contexto da operação", padding=12)
        formulario.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        for coluna in (1, 3, 5):
            formulario.grid_columnconfigure(coluna, weight=1)

        ttk.Label(formulario, text="NCM").grid(row=0, column=0, sticky="w")
        self.var_ncm = tk.StringVar(value=ncm)
        ttk.Entry(formulario, textvariable=self.var_ncm, width=18).grid(
            row=0, column=1, sticky="ew", padx=(7, 14)
        )

        ttk.Label(formulario, text="UF origem").grid(row=0, column=2, sticky="w")
        self.var_origem = tk.StringVar(value="MG")
        ttk.Combobox(
            formulario, textvariable=self.var_origem, values=UFS, state="readonly", width=7
        ).grid(row=0, column=3, sticky="ew", padx=(7, 14))

        ttk.Label(formulario, text="UF destino").grid(row=0, column=4, sticky="w")
        self.var_destino = tk.StringVar(value="MG")
        ttk.Combobox(
            formulario, textvariable=self.var_destino, values=UFS, state="readonly", width=7
        ).grid(row=0, column=5, sticky="ew", padx=(7, 0))

        ttk.Label(formulario, text="Descrição do produto").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        self.var_descricao = tk.StringVar(value=descricao)
        ttk.Entry(formulario, textvariable=self.var_descricao).grid(
            row=1, column=1, columnspan=5, sticky="ew", padx=(7, 0), pady=(8, 0)
        )

        ttk.Label(formulario, text="Operação").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        self.var_operacao = tk.StringVar(value="Venda")
        ttk.Combobox(
            formulario,
            textvariable=self.var_operacao,
            state="readonly",
            values=("Venda", "Revenda", "Entrada", "Devolução", "Transferência", "Remessa"),
        ).grid(row=2, column=1, sticky="ew", padx=(7, 14), pady=(8, 0))

        ttk.Label(formulario, text="Finalidade").grid(
            row=2, column=2, sticky="w", pady=(8, 0)
        )
        self.var_finalidade = tk.StringVar(value="Revenda")
        ttk.Combobox(
            formulario,
            textvariable=self.var_finalidade,
            state="readonly",
            values=("Revenda", "Industrialização", "Uso e consumo", "Ativo imobilizado"),
        ).grid(row=2, column=3, sticky="ew", padx=(7, 14), pady=(8, 0))

        ttk.Label(formulario, text="Perfil remetente").grid(
            row=2, column=4, sticky="w", pady=(8, 0)
        )
        self.var_perfil = tk.StringVar(value="Comerciante")
        ttk.Combobox(
            formulario,
            textvariable=self.var_perfil,
            state="readonly",
            values=("Comerciante", "Fabricante", "Importador", "Fabricante/Importador"),
        ).grid(row=2, column=5, sticky="ew", padx=(7, 0), pady=(8, 0))

        ttk.Label(formulario, text="Data da operação").grid(
            row=3, column=0, sticky="w", pady=(8, 0)
        )
        self.var_data = tk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        ttk.Entry(formulario, textvariable=self.var_data).grid(
            row=3, column=1, sticky="ew", padx=(7, 14), pady=(8, 0)
        )

        opcoes = ttk.Frame(formulario)
        opcoes.grid(row=3, column=2, columnspan=4, sticky="w", pady=(8, 0))
        self.var_consumidor_final = tk.BooleanVar(value=False)
        self.var_importada = tk.BooleanVar(value=False)
        self.var_excecao_importada = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opcoes, text="Consumidor final", variable=self.var_consumidor_final
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            opcoes, text="Mercadoria importada / conteúdo > 40%", variable=self.var_importada
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            opcoes, text="Exceção legal à alíquota de 4%", variable=self.var_excecao_importada
        ).pack(side=tk.LEFT, padx=(12, 0))

        acoes = ttk.Frame(self)
        acoes.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        for coluna in range(4):
            acoes.grid_columnconfigure(coluna, weight=1, uniform="icms")
        ttk.Button(acoes, text="Analisar ICMS/MG", command=self.analisar).grid(
            row=0, column=0, sticky="ew"
        )
        self.botao_atualizar = ttk.Button(
            acoes, text="Sincronizar tabela oficial ST/MG", command=self.atualizar_cobertura
        )
        self.botao_atualizar.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(acoes, text="Calcular DIFAL/FCP", command=self.abrir_difal_fcp).grid(
            row=0, column=2, sticky="ew", padx=(8, 0)
        )
        ttk.Button(acoes, text="Fechar", command=self.destroy).grid(
            row=0, column=3, sticky="ew", padx=(8, 0)
        )

        cobertura = BaseOficialRepository.resumo_st_mg()
        self.status = ttk.Label(
            self,
            text=self._texto_cobertura(cobertura),
            anchor="w",
        )
        self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 7))

        quadro = ttk.LabelFrame(self, text="Resultado rastreável", padding=8)
        quadro.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 14))
        quadro.grid_rowconfigure(0, weight=1)
        quadro.grid_columnconfigure(0, weight=1)
        self.resultado = tk.Text(
            quadro, wrap=tk.WORD, font=("Consolas", 10), padx=10, pady=10
        )
        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.resultado.yview)
        self.resultado.configure(yscrollcommand=barra.set)
        self.resultado.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")

        if ncm:
            self.after(100, self.analisar)

    @staticmethod
    def _percentual(valor) -> str:
        if valor is None:
            return "-"
        return f"{float(valor):.2f}%".replace(".", ",")

    @staticmethod
    def _texto_cobertura(cobertura) -> str:
        registros = int(cobertura.get("registros") or 0)
        segmentos = int(cobertura.get("segmentos") or 0)
        completa = bool(cobertura.get("base_completa")) and int(cobertura.get("versao_schema") or 0) >= 3
        data = str(cobertura.get("sincronizado_em") or cobertura.get("atualizado_em") or "").strip()
        selo = "BASE COMPLETA" if completa else "BASE PARCIAL — sincronize para concluir ausências"
        sufixo = f" • sincronizada em {data[:10]}" if data else ""
        return (
            f"ST/MG: {selo} • {registros:,} registros nominais em {segmentos} segmentos{sufixo}."
        ).replace(",", ".")

    def analisar(self):
        ncm = self.var_ncm.get().strip()
        if not ncm:
            messagebox.showwarning("FiscalPro", "Informe o NCM.")
            return
        try:
            resultado = ICMSMGNacionalService.analisar(
                ncm,
                contexto={
                    "uf_origem": self.var_origem.get(),
                    "uf_destino": self.var_destino.get(),
                    "operacao": self.var_operacao.get(),
                    "finalidade": self.var_finalidade.get(),
                    "perfil_remetente": self.var_perfil.get(),
                    "consumidor_final": self.var_consumidor_final.get(),
                    "mercadoria_importada": self.var_importada.get(),
                    "excecao_aliquota_importacao": self.var_excecao_importada.get(),
                    "data_operacao": self.var_data.get(),
                },
                descricao=self.var_descricao.get(),
            )
        except ValueError as exc:
            messagebox.showwarning("FiscalPro", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("FiscalPro", f"Não foi possível analisar o ICMS: {exc}")
            return

        linhas = [
            "=================================================",
            "MOTOR ICMS/MG — BASE OFICIAL ST/MG 17.8.119",
            "=================================================",
            f"NCM: {resultado.get('ncm', '')}",
            f"Data: {resultado.get('data_operacao', '')}",
            f"Tipo de operação: {resultado.get('tipo_operacao', '')}",
            f"Status geral: {resultado.get('status', '')}",
            "",
            "ALÍQUOTA NOMINAL",
            "-----------------",
            f"Alíquota: {self._percentual(resultado.get('aliquota_nominal'))}",
            f"Status: {resultado.get('aliquota_status') or '-'}",
            f"Confirmação específica: {'SIM' if resultado.get('aliquota_confirmada') else 'NÃO'}",
            f"Confiança: {self._percentual(resultado.get('confiabilidade_aliquota'))}",
            f"Fundamento: {resultado.get('fundamento_aliquota') or '-'}",
            f"Fonte: {resultado.get('fonte_aliquota') or '-'}",
            "",
            "ICMS-ST / MG",
            "------------",
            f"Status: {resultado.get('st_status') or '-'}",
            f"Confirmado: {'SIM' if resultado.get('st_confirmado') else 'NÃO'}",
            f"CEST: {resultado.get('cest') or '-'}",
            f"Segmento: {resultado.get('segmento_st') or '-'}",
            f"MVA original: {self._percentual(resultado.get('mva_original'))}",
            f"MVA/regra textual: {resultado.get('mva_texto_st') or '-'}",
            f"Âmbito: {resultado.get('ambito_st') or '-'}",
            f"Aplicação: {resultado.get('aplicacao_st') or '-'}",
            f"Observação ST: {resultado.get('observacao_st') or '-'}",
            "",
            "BENEFÍCIO FISCAL RECONHECIDO",
            "-----------------------------",
            f"Status: {resultado.get('beneficio_status') or '-'}",
            f"Benefício: {resultado.get('beneficio') or '-'}",
            f"Redução de base: {self._percentual(resultado.get('reducao_base_percentual'))}",
            f"Fundamento: {resultado.get('fundamento_beneficio') or '-'}",
            f"Fonte: {resultado.get('fonte_beneficio') or '-'}",
            "",
            "COBERTURA E AVISOS",
            "------------------",
            (
                f"Tabela instalada: {int(resultado.get('cobertura_st_registros') or 0):,} registros "
                f"em {int(resultado.get('cobertura_st_segmentos') or 0)} segmentos."
            ).replace(",", "."),
            (
                "Selo da base: COMPLETA"
                if resultado.get("cobertura_st_completa") and int(resultado.get("cobertura_st_versao_schema") or 0) >= 3
                else "Selo da base: PARCIAL — sincronização integral necessária para concluir ausência nominal"
            ),
            f"Sincronização: {resultado.get('cobertura_st_atualizada_em') or '-'}",
            f"Referência: {resultado.get('cobertura_st_referencia') or '-'}",
            resultado.get("observacao") or "-",
            "",
            "Ausência nominal só confirma NÃO ST com a base completa sincronizada e após avaliar regras residuais sem NCM.",
            "Alíquotas condicionais e benefícios dependentes de fatos não são gravados automaticamente.",
        ]
        self.resultado.delete("1.0", tk.END)
        self.resultado.insert(tk.END, "\n".join(linhas))

    def abrir_difal_fcp(self):
        JanelaDIFALFCP(
            self,
            ncm=self.var_ncm.get().strip(),
            descricao=self.var_descricao.get().strip(),
            uf_origem=self.var_origem.get(),
            uf_destino=self.var_destino.get(),
        )

    def atualizar_cobertura(self):
        self.botao_atualizar.config(state=tk.DISABLED)
        self.status.config(text="Baixando e conferindo a Parte 2 do Anexo VII de Minas Gerais...")

        def executar():
            resultado = AtualizadorFontesOficiais(timeout=60).atualizar_st_mg_completa()
            self.after(0, lambda: self._finalizar_atualizacao(resultado))

        threading.Thread(target=executar, daemon=True).start()

    def _finalizar_atualizacao(self, resultado):
        self.botao_atualizar.config(state=tk.NORMAL)
        cobertura = BaseOficialRepository.resumo_st_mg()
        self.status.config(text=self._texto_cobertura(cobertura))
        if resultado.status == "SUCESSO":
            complemento = "\n\n" + "\n".join(resultado.detalhes) if resultado.detalhes else ""
            messagebox.showinfo("FiscalPro", resultado.mensagem + complemento)
            self.analisar()
        else:
            messagebox.showerror(
                "FiscalPro",
                resultado.mensagem + "\n\nA cobertura anterior foi preservada.",
            )
