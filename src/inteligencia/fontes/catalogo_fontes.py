from src.inteligencia.fontes.receita_federal import ReceitaFederal
from src.inteligencia.fontes.confaz import Confaz
from src.inteligencia.fontes.sefaz_mg import SefazMG
from src.inteligencia.fontes.reforma import ReformaTributaria


class CatalogoFontes:

    @staticmethod
    def listar():

        return [

            ReceitaFederal(),

            Confaz(),

            SefazMG(),

            ReformaTributaria()

        ]