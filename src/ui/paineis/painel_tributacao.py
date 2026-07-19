from tkinter import *


class PainelTributacao(Frame):

    def __init__(self, master):

        super().__init__(master)

        self.pack(fill=BOTH, expand=True)

        self.criar_interface()

    def criar_interface(self):

        Label(
            self,
            text="Consulta Tributária",
            font=("Segoe UI", 14, "bold")
        ).pack(pady=10)

        frame = Frame(self)

        frame.pack()

        Label(frame, text="NCM").grid(row=0, column=0)

        self.ed_ncm = Entry(frame, width=20)

        self.ed_ncm.grid(row=0, column=1, padx=5)

        Button(
            frame,
            text="Consultar",
            command=self.consultar
        ).grid(row=0, column=2)

        self.resultado = Text(
            self,
            height=20,
            width=90
        )

        self.resultado.pack(
            pady=10,
            padx=10
        )

    def consultar(self):

        self.resultado.delete(
            "1.0",
            END
        )

        self.resultado.insert(
            END,
            "Consulta funcionando!\n"
        )

        self.resultado.insert(
            END,
            f"NCM informado: {self.ed_ncm.get()}"
        )