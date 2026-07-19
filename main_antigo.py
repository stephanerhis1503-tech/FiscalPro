"""
FiscalPro
Versão 0.6.2
"""

from tkinter import *
from tkinter import filedialog, messagebox, ttk
import os

from src.leitor_sped import LeitorSPED
from src.analisador import AnalisadorSPED
from src.formatador import FormatadorAuditoria
from src.ui.cards import Card

pasta_xml = ""


def formatar_data(data):
    return f"{data[:2]}/{data[2:4]}/{data[4:]}" if len(data) == 8 else data


def atualizar_status(texto):
    lbl_status.config(text=texto)


def selecionar_pasta_xml():
    global pasta_xml
    pasta = filedialog.askdirectory(title="Selecione a pasta dos XML")
    if pasta:
        pasta_xml = pasta
        lbl_xml.config(text=f"XML: {pasta}")


def abrir_sped():
    arquivo = filedialog.askopenfilename(
        filetypes=[("Arquivo SPED", "*.txt")]
    )

    if not arquivo:
        return

    try:

        atualizar_status("Lendo SPED...")

        leitor = LeitorSPED(arquivo)

        leitor.carregar()

        analisador = AnalisadorSPED(leitor.linhas)

        resultado = analisador.analisar()

        reg = leitor.obter_registro_0000()

        if reg:

            lbl_empresa.config(text=f"Empresa: {reg[6]}")

            lbl_periodo.config(
                text=f"Período: {formatar_data(reg[4])} até {formatar_data(reg[5])}"
            )

        lbl_sped.config(
            text=f"SPED: {os.path.basename(arquivo)}"
        )

        card_registros.atualizar(len(leitor.linhas))

        erros = resultado.get("erros", []) if isinstance(resultado, dict) else []

        avisos = resultado.get("avisos", []) if isinstance(resultado, dict) else []

        card_erros.atualizar(len(erros))

        card_avisos.atualizar(len(avisos))

        if pasta_xml and os.path.isdir(pasta_xml):

            card_xml.atualizar(

                len(

                    [

                        f

                        for f in os.listdir(pasta_xml)

                        if f.lower().endswith(".xml")

                    ]

                )

            )

        texto = FormatadorAuditoria.montar_resumo(

            lbl_empresa.cget("text").replace("Empresa: ", ""),

            lbl_periodo.cget("text").replace("Período: ", ""),

            leitor,

            resultado

        )

        txt_resultado.config(state="normal")

        txt_resultado.delete("1.0", END)

        txt_resultado.insert(END, texto)

        txt_resultado.config(state="disabled")

        atualizar_status("Concluído.")

    except Exception as e:

        messagebox.showerror("Erro", str(e))

        atualizar_status("Erro.")


def corrigir_sped():

    if not pasta_xml:

        messagebox.showwarning(

            "FiscalPro",

            "Selecione a pasta dos XML primeiro."

        )

        return

    messagebox.showinfo(

        "FiscalPro",

        "Botão Corrigir SPED funcionando!"

    )


janela = Tk()

janela.title("FiscalPro v0.6.2")

janela.geometry("1000x720")

janela.configure(bg="#f2f4f7")


topo = Frame(janela, bg="#0b5ed7", height=80)

topo.pack(fill=X)

Label(

    topo,

    text="FiscalPro",

    bg="#0b5ed7",

    fg="white",

    font=("Segoe UI", 22, "bold")

).pack(pady=(10, 0))

Label(

    topo,

    text="Assistente Fiscal Inteligente",

    bg="#0b5ed7",

    fg="white"

).pack()


frame_dashboard = ttk.Frame(janela)

frame_dashboard.pack(fill=X, padx=15, pady=10)

card_registros = Card(frame_dashboard, "Registros")

card_registros.grid(row=0, column=0, padx=8)

card_erros = Card(frame_dashboard, "Erros")

card_erros.grid(row=0, column=1, padx=8)

card_avisos = Card(frame_dashboard, "Avisos")

card_avisos.grid(row=0, column=2, padx=8)

card_xml = Card(frame_dashboard, "XML")

card_xml.grid(row=0, column=3, padx=8)


frame_info = ttk.LabelFrame(

    janela,

    text="Informações"

)

frame_info.pack(fill=X, padx=15, pady=10)

lbl_empresa = ttk.Label(frame_info, text="Empresa: -")

lbl_empresa.grid(row=0, column=0, sticky="w", padx=10, pady=5)

lbl_periodo = ttk.Label(frame_info, text="Período: -")

lbl_periodo.grid(row=1, column=0, sticky="w", padx=10, pady=5)

lbl_sped = ttk.Label(frame_info, text="SPED: -")

lbl_sped.grid(row=2, column=0, sticky="w", padx=10, pady=5)

lbl_xml = ttk.Label(frame_info, text="XML: -")

lbl_xml.grid(row=3, column=0, sticky="w", padx=10, pady=5)


fb = ttk.Frame(janela)

fb.pack()

ttk.Button(

    fb,

    text="Abrir SPED",

    command=abrir_sped

).grid(row=0, column=0, padx=5)

ttk.Button(

    fb,

    text="Selecionar XML",

    command=selecionar_pasta_xml

).grid(row=0, column=1, padx=5)

ttk.Button(

    fb,

    text="Corrigir SPED",

    command=corrigir_sped

).grid(row=0, column=2, padx=5)


fr = ttk.LabelFrame(

    janela,

    text="Resultado"

)

fr.pack(fill=BOTH, expand=True, padx=15, pady=10)

txt_resultado = Text(fr, wrap=WORD)

txt_resultado.pack(fill=BOTH, expand=True)


barra = Frame(

    janela,

    bg="#e9ecef"

)

barra.pack(fill=X, side=BOTTOM)

lbl_status = Label(

    barra,

    text="Pronto.",

    bg="#e9ecef"

)

lbl_status.pack(anchor="w", padx=10)


janela.mainloop()