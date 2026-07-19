from tkinter import ttk

def criar_botao(master, texto, comando):

    return ttk.Button(
        master,
        text=texto,
        command=comando
    )


def criar_entry(master):

    return ttk.Entry(master)