"""Cards do painel principal do FiscalPro."""

from tkinter import Frame, Label

from .estilos import COR_BORDA, COR_CARD, COR_PRIMARIA, COR_TEXTO, COR_TEXTO_SUAVE


class Card(Frame):
    def __init__(self, master, titulo, valor="0", destaque=COR_PRIMARIA):
        super().__init__(
            master,
            bg=COR_CARD,
            bd=0,
            highlightthickness=1,
            highlightbackground=COR_BORDA,
            padx=0,
            pady=0,
        )

        self._barra = Frame(self, bg=destaque, width=5)
        self._barra.pack(side="left", fill="y")

        conteudo = Frame(self, bg=COR_CARD, padx=12, pady=8)
        conteudo.pack(side="left", fill="both", expand=True)

        self.lbl_titulo = Label(
            conteudo,
            text=titulo,
            bg=COR_CARD,
            fg=COR_TEXTO_SUAVE,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        self.lbl_titulo.pack(fill="x")

        self.lbl_valor = Label(
            conteudo,
            text=valor,
            bg=COR_CARD,
            fg=COR_TEXTO,
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        )
        self.lbl_valor.pack(fill="x", pady=(1, 0))

    def atualizar(self, valor):
        self.lbl_valor.config(text=str(valor))
