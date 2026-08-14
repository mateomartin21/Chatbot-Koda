"""Punto unico de entrada al dominio de planes.

Anadir una distancia nueva (un ultra, un 3K) es una clase mas y una linea en este
diccionario: cero cambios en el resto del sistema (Open/Closed).
"""

from app.domain.training.modelos import Distancia
from app.domain.training.strategy import EstrategiaPlan, Plan5K, Plan10K, Plan21K, Plan42K

_ESTRATEGIAS: dict[Distancia, type[EstrategiaPlan]] = {
    Distancia.K5: Plan5K,
    Distancia.K10: Plan10K,
    Distancia.K21: Plan21K,
    Distancia.K42: Plan42K,
}


def estrategia_para(distancia: Distancia) -> EstrategiaPlan:
    return _ESTRATEGIAS[distancia]()
