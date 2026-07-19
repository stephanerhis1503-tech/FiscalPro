from abc import ABC, abstractmethod


class FonteBase(ABC):

    @abstractmethod
    def pesquisar(self, consulta):
        """
        Pesquisa uma fonte oficial.
        Deve retornar uma FichaTributaria ou None.
        """
        pass