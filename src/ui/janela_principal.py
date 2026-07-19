"""
=========================================
FiscalPro
Janela Principal
Versão 0.7.0
=========================================
"""

from tkinter import *
from tkinter import ttk

from .estilos import *
from .componentes import *
from .dashboard import Dashboard
from .painel_info import PainelInfo
from .janela_consulta_ncm import JanelaConsultaNCM

import os
import traceback

from tkinter import filedialog, messagebox

from src.leitor_sped import LeitorSPED
from src.analisador import AnalisadorSPED
from src.formatador import FormatadorAuditoria
from src.motor_correcao import MotorCorrecao


class JanelaPrincipal:

    def __init__(self):

        self.janela = Tk()

        self.janela.title("FiscalPro v0.7.0")

        self.janela.geometry("1100x720")

        self.janela.configure(bg=COR_FUNDO)

        self.janela.resizable(False, False)

        # Dados do projeto
        self.pasta_xml = ""
        self.arquivo_sped = ""
        self.linhas_sped = []

        print("Métodos da classe:", [m for m in dir(self) if not m.startswith("_")])

        self.criar_interface()

    def criar_interface(self):

        self.criar_cabecalho()

        self.criar_abas()

    def criar_cabecalho(self):

        frame = Frame(
            self.janela,
            bg=COR_PRIMARIA,
            height=80
        )

        frame.pack(fill=X)

        titulo = criar_titulo(
            frame,
            "FiscalPro"
        )

        titulo.pack(anchor="w", padx=20)

        subtitulo = criar_subtitulo(
            frame,
            "Assistente Fiscal Inteligente"
        )

        subtitulo.pack(anchor="w", padx=22)
    
    def criar_abas(self):

        self.notebook = ttk.Notebook(self.janela)

        self.notebook.pack(
            fill=BOTH,
            expand=True,
            padx=10,
            pady=10
        )

        self.aba_sped = Frame(self.notebook)

        self.aba_tributacao = Frame(self.notebook)

        self.aba_correcoes = Frame(self.notebook)

        self.aba_relatorios = Frame(self.notebook)

        self.notebook.add(
            self.aba_sped,
            text="📄 SPED"
        )

        self.notebook.add(
            self.aba_tributacao,
            text="📚 Tributação"
        )

        self.notebook.add(
            self.aba_correcoes,
            text="🤖 Correções"
        )

        self.notebook.add(
            self.aba_relatorios,
         text="📊 Relatórios"
        )

        self.criar_painel_sped()
        self.criar_painel_correcoes()

    def criar_painel_sped(self):

        self.dashboard = Dashboard(self.aba_sped)

        self.painel_info = PainelInfo(self.aba_sped)

        self.criar_botoes(self.aba_sped)

        self.criar_resultado()

    def criar_painel_correcoes(self):

        frame = ttk.LabelFrame(
            self.aba_correcoes,
            text="Correções Realizadas"
        )

        frame.pack(
            fill=BOTH,
            expand=True,
            padx=15,
            pady=10
        )

        self.txt_correcoes = Text(
            frame,
            wrap=WORD
        )

        self.txt_correcoes.pack(
            fill=BOTH,
            expand=True
        )
   
    def criar_botoes(self, master):

        frame = Frame(
            master,
            bg=COR_FUNDO
        )

        frame.pack(fill=X, padx=15, pady=10)

        ttk.Button(
            frame,
            text="📂 Abrir SPED",
            command=self.abrir_sped
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            frame,
            text="📁 Selecionar XML",
            command=self.selecionar_xml
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            frame,
            text="🔧 Corrigir SPED",
            command=self.corrigir_sped
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            frame,
            text="📚 Consulta Tributária",
            command=self.abrir_consulta_tributaria
        ).pack(side=LEFT, padx=5)

    def criar_resultado(self):

        frame = ttk.LabelFrame(
            self.aba_sped,
            text="Resultado"
        )

        frame.pack(
            fill=BOTH,
            expand=True,
            padx=15,
            pady=10
        )

        self.txt_resultado = Text(
            frame,
            wrap=WORD
        )

        self.txt_resultado.pack(
            fill=BOTH,
            expand=True
        )

    def abrir_sped(self):

        arquivo = filedialog.askopenfilename(

            title="Selecione o arquivo SPED",

            filetypes=[("Arquivo SPED", "*.txt")]

        )

        if not arquivo:
            return
        
        try:

            self.arquivo_sped = arquivo

            leitor = LeitorSPED(arquivo)

            leitor.carregar()

            # Guarda o SPED carregado para reutilizar na correção
            self.leitor = leitor
            self.linhas_sped = leitor.linhas

            analisador = AnalisadorSPED(leitor.linhas)

            resultado = analisador.analisar()

            registro = leitor.obter_registro_0000()

            empresa = "-"
            periodo = "-"

            if registro:

                empresa = registro[6]

                periodo = f"{registro[4]} até {registro[5]}"

            self.dashboard.atualizar(

                leitor.total_linhas(),

                len(resultado["auditoria_c170"]["erros"]),

                0,

                0

            )

            self.painel_info.atualizar(

                empresa,

                periodo,

                os.path.basename(arquivo),

                "-"

            )

            relatorio = FormatadorAuditoria.montar_resumo(

                empresa,

                periodo,

                leitor,

                resultado

            )

            self.txt_resultado.delete("1.0", END)

            self.txt_resultado.insert(

                END,

                relatorio

            )

        except Exception as erro:

            traceback.print_exc()

            messagebox.showerror(
                "FiscalPro",
                str(erro)
            )

    def selecionar_xml(self):

        pasta = filedialog.askdirectory(
            title="Selecione a pasta dos XML"
        )

        if not pasta:
            return

        self.pasta_xml = pasta

        self.painel_info.lbl_xml.config(
            text=f"XML: {pasta}"
        )

        messagebox.showinfo(
            "FiscalPro",
            "Pasta dos XML selecionada com sucesso!"
        )

    def corrigir_sped(self):
        
        if not self.linhas_sped:
            messagebox.showwarning(
                "FiscalPro",
                "Abra um arquivo SPED primeiro."
            )
            return

        if not self.pasta_xml:
            messagebox.showwarning(
                "FiscalPro",
                "Selecione a pasta dos XML."
            )
            return

        try:

            motor = MotorCorrecao()

            resultado = motor.executar(
                self.linhas_sped,
                self.pasta_xml
            )

            arquivo = motor.salvar_sped(
                resultado["linhas"],
                self.arquivo_sped
            )
        
            self.txt_correcoes.delete("1.0", END)

            self.txt_correcoes.insert(
                END,
                "RELATÓRIO DE CORREÇÕES\n"
            )

            self.txt_correcoes.insert(
                END,
                "=" * 60 + "\n\n"
            )

            self.txt_correcoes.insert(
                END,
                f"XML lidos: {resultado['xml_lidos']}\n"
            )

            self.txt_correcoes.insert(
                END,
                f"CT-e corrigidos: {resultado['corrigidos']}\n"
            )

            self.txt_correcoes.insert(
                END,
                f"Não encontrados: {resultado['nao_encontrados']}\n\n"
            )

            for item in resultado["relatorio"]:

                self.txt_correcoes.insert(
                    END,
                    f"CT-e {item['numero']}\n"
                )

                self.txt_correcoes.insert(
                    END,
                    f"Antes : {item['antes']}\n"
                )

                self.txt_correcoes.insert(
                    END,
                    f"Depois: {item['depois']}\n"
                )

                self.txt_correcoes.insert(
                    END,
                    "-" * 60 + "\n"
                )

            messagebox.showinfo(
                "FiscalPro",
                f"""Correção concluída!

            CT-e corrigidos: {resultado['corrigidos']}
            Não encontrados: {resultado['nao_encontrados']}

            Arquivo salvo em:

            {arquivo}
            """
            )

        except Exception as erro:

            messagebox.showerror(
                "FiscalPro",
                str(erro)
            )

    def abrir_consulta_tributaria(self):

        JanelaConsultaNCM(self.janela)
        
    def atualizar_info(self,
                       empresa,
                       periodo,
                       sped,
                       xml):

        self.painel_info.atualizar(
            empresa,
            periodo,
            sped,
            xml
        )

    def executar(self):

        self.janela.mainloop()