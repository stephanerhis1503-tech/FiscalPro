
"""
=========================================
FiscalPro
Versão: 0.6.1
Sprint 6 - Interface Moderna
=========================================
"""

from tkinter import *
from tkinter import filedialog, messagebox
from tkinter import ttk
import os

from src.leitor_sped import LeitorSPED
from src.analisador import AnalisadorSPED
from src.formatador import FormatadorAuditoria

pasta_xml = ""

def formatar_data(data):
    if len(data) == 8:
        return f"{data[:2]}/{data[2:4]}/{data[4:]}"
    return data

def atualizar_status(texto):
    lbl_status.config(text=texto)

def selecionar_pasta_xml():
    global pasta_xml
    pasta = filedialog.askdirectory(title="Selecione a pasta dos XML dos CT-e")
    if pasta:
        pasta_xml = pasta
        lbl_xml.config(text=f"XML: {pasta}")
        atualizar_status("Pasta XML selecionada.")
        messagebox.showinfo("FiscalPro", "Pasta dos XML selecionada com sucesso!")

def abrir_sped():
    arquivo = filedialog.askopenfilename(
        title="Selecione o arquivo SPED",
        filetypes=[("Arquivo SPED","*.txt"),("Todos os arquivos","*.*")]
    )

    if not arquivo:
        return

    try:
        atualizar_status("Lendo arquivo SPED...")

        leitor = LeitorSPED(arquivo)
        leitor.carregar()

        analisador = AnalisadorSPED(leitor.linhas)
        resultado = analisador.analisar()

        registro = leitor.obter_registro_0000()

        empresa = "Não encontrada"
        periodo = "Não encontrado"

        if registro:
            empresa = registro[6]
            periodo = f"{formatar_data(registro[4])} até {formatar_data(registro[5])}"

        lbl_empresa.config(text=f"Empresa: {empresa}")
        lbl_periodo.config(text=f"Período: {periodo}")
        lbl_sped.config(text=f"SPED: {os.path.basename(arquivo)}")

        texto = FormatadorAuditoria.montar_resumo(
            empresa,
            periodo,
            leitor,
            resultado
        )

        txt_resultado.config(state="normal")
        txt_resultado.delete("1.0", END)
        txt_resultado.insert(END, texto)
        txt_resultado.config(state="disabled")

        atualizar_status("Auditoria concluída com sucesso.")

    except Exception as erro:
        atualizar_status("Erro durante a auditoria.")
        messagebox.showerror("Erro", str(erro))


janela = Tk()
janela.title("FiscalPro v0.6.1")
janela.geometry("1000x720")
janela.configure(bg="#f2f4f7")
janela.resizable(False, False)

style = ttk.Style()
try:
    style.theme_use("clam")
except:
    pass

topo = Frame(janela, bg="#0b5ed7", height=80)
topo.pack(fill=X)

Label(
    topo,
    text="FiscalPro",
    bg="#0b5ed7",
    fg="white",
    font=("Segoe UI",22,"bold")
).pack(pady=(10,0))

Label(
    topo,
    text="Assistente Fiscal Inteligente",
    bg="#0b5ed7",
    fg="white",
    font=("Segoe UI",10)
).pack()

frame_info = ttk.LabelFrame(janela,text="Informações")
frame_info.pack(fill=X,padx=15,pady=10)

lbl_empresa = ttk.Label(frame_info,text="Empresa: -")
lbl_empresa.grid(row=0,column=0,sticky="w",padx=10,pady=5)

lbl_periodo = ttk.Label(frame_info,text="Período: -")
lbl_periodo.grid(row=1,column=0,sticky="w",padx=10,pady=5)

lbl_sped = ttk.Label(frame_info,text="SPED: Nenhum arquivo")
lbl_sped.grid(row=2,column=0,sticky="w",padx=10,pady=5)

lbl_xml = ttk.Label(frame_info,text="XML: Nenhuma pasta")
lbl_xml.grid(row=3,column=0,sticky="w",padx=10,pady=5)

frame_botoes = ttk.Frame(janela)
frame_botoes.pack(pady=5)

ttk.Button(frame_botoes,text="📂 Abrir SPED",command=abrir_sped).grid(row=0,column=0,padx=8)
ttk.Button(frame_botoes,text="📁 Selecionar XML",command=selecionar_pasta_xml).grid(row=0,column=1,padx=8)

frame_resultado = ttk.LabelFrame(janela,text="Resultado da Auditoria")
frame_resultado.pack(fill=BOTH,expand=True,padx=15,pady=10)

scroll = ttk.Scrollbar(frame_resultado)
scroll.pack(side=RIGHT,fill=Y)

txt_resultado = Text(
    frame_resultado,
    font=("Consolas",11),
    wrap=WORD,
    yscrollcommand=scroll.set
)
txt_resultado.pack(side=LEFT,fill=BOTH,expand=True)
scroll.config(command=txt_resultado.yview)

txt_resultado.insert(END,"Selecione um arquivo SPED para iniciar a auditoria.")
txt_resultado.config(state="disabled")

barra = Frame(janela,bg="#e9ecef",height=28)
barra.pack(fill=X,side=BOTTOM)

lbl_status = Label(
    barra,
    text="Pronto.",
    bg="#e9ecef",
    anchor="w"
)
lbl_status.pack(fill=X,padx=10)

janela.mainloop()
