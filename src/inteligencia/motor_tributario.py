from src.repositorios.tributacao_repository import TributacaoRepository

from src.inteligencia.regras.regra_icms import RegraICMS
from src.inteligencia.regras.regra_cfop import RegraCFOP
from src.inteligencia.regras.regra_st import RegraST
from src.inteligencia.regras.regra_piscofins import RegraPISCOFINS
from src.inteligencia.regras.regra_reforma import RegraReforma

from src.inteligencia.pesquisador import Pesquisador



class MotorTributario:

    def consultar(self, consulta):

        print(">>> MOTOR INICIADO <<<")

        ficha = TributacaoRepository.buscar_ficha(consulta.ncm)

        if ficha:

            print("✅ Ficha encontrada.")

            ficha = self.aplicar_regras(ficha, consulta)

            return ficha

        print("⚠ NCM não encontrado.")

        pesquisador = Pesquisador()

        return pesquisador.buscar(consulta)
    
    def aplicar_regras(self, ficha, consulta):

        ficha = RegraICMS.aplicar(ficha, consulta)
        ficha = RegraCFOP.aplicar(ficha, consulta)
        ficha = RegraST.aplicar(ficha, consulta)
        ficha = RegraPISCOFINS.aplicar(ficha, consulta)
        ficha = RegraReforma.aplicar(ficha, consulta)

        return ficha