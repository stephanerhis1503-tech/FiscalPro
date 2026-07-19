from src.repositorios.ncm_repository import NCMRepository


class MotorTributario:

    def consultar_ncm(self, ncm):

        produto = NCMRepository.buscar_por_ncm(ncm)

        if not produto:

            return {
                "encontrado": False
            }

        tributacao = NCMRepository.buscar_tributacao(ncm)

        reforma = NCMRepository.buscar_reforma(ncm)

        return {

            "encontrado": True,

            "produto": produto,

            "tributacao": tributacao,

            "reforma": reforma

        }