"""Índice vectorial en memoria.

Guarda un vector por fragmento y responde cuáles se parecen más a la consulta,
por similitud coseno.

No usa una base vectorial dedicada a propósito. Para un corpus de este tamaño
—decenas o cientos de fragmentos— una matriz de numpy es más rápida que
cualquier servicio, y deja a la vista la operación que de otro modo quedaría
escondida detrás de una librería. Cuando el corpus deje de caber en memoria,
esta clase es la única pieza que hay que cambiar.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .chunking import Fragmento

# Por debajo de esto la coincidencia no es información, es ruido con forma de
# resultado. Se prefiere no responder a responder con un fragmento irrelevante.
SIMILITUD_MINIMA = 0.25


@dataclass(frozen=True)
class Coincidencia:
    fragmento: Fragmento
    similitud: float


def _normalizar(matriz: np.ndarray) -> np.ndarray:
    """Lleva cada fila a norma 1 para que el producto punto sea el coseno.

    Una fila de ceros dejaría una división por cero; se le pone norma 1 para
    que su producto punto quede en 0 y simplemente nunca coincida.
    """
    normas = np.linalg.norm(matriz, axis=1, keepdims=True)
    normas[normas == 0] = 1.0
    return matriz / normas


class IndiceVectorial:
    def __init__(self) -> None:
        self._fragmentos: list[Fragmento] = []
        self._vectores: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self._fragmentos)

    @property
    def dimensiones(self) -> int | None:
        return None if self._vectores is None else int(self._vectores.shape[1])

    def agregar(self, fragmentos: list[Fragmento], vectores: list[list[float]]) -> None:
        if len(fragmentos) != len(vectores):
            raise ValueError("cada fragmento necesita exactamente un vector")
        if not fragmentos:
            return

        nuevos = np.asarray(vectores, dtype=np.float32)
        if nuevos.ndim != 2:
            raise ValueError("los vectores deben formar una matriz de dos dimensiones")
        if not np.isfinite(nuevos).all():
            raise ValueError("los vectores no pueden traer NaN ni infinitos")

        # Mezclar vectores de dimensiones distintas produce comparaciones sin
        # sentido en lugar de un error: se rechaza aquí, donde aún se puede
        # señalar la causa.
        if self._vectores is not None and nuevos.shape[1] != self._vectores.shape[1]:
            raise ValueError(
                f"dimensión {nuevos.shape[1]} incompatible con el índice "
                f"({self._vectores.shape[1]})"
            )

        nuevos = _normalizar(nuevos)
        self._vectores = (
            nuevos if self._vectores is None else np.vstack([self._vectores, nuevos])
        )
        self._fragmentos.extend(fragmentos)

    def buscar(self, consulta: list[float], k: int = 4) -> list[Coincidencia]:
        """Devuelve los k fragmentos más parecidos que superen el umbral.

        Devuelve menos de k —o ninguno— cuando no hay coincidencias por encima
        del umbral. Rellenar hasta k con lo mejor disponible es lo que hace que
        un sistema RAG conteste con seguridad usando fragmentos que no vienen
        al caso.
        """
        if self._vectores is None or k <= 0:
            return []

        vector = np.asarray([consulta], dtype=np.float32)
        if vector.shape[1] != self._vectores.shape[1]:
            raise ValueError("la consulta no tiene la dimensión del índice")
        if not np.isfinite(vector).all():
            raise ValueError("la consulta no puede traer NaN ni infinitos")

        similitudes = (_normalizar(vector) @ self._vectores.T)[0]
        orden = np.argsort(-similitudes)[:k]

        return [
            Coincidencia(fragmento=self._fragmentos[i], similitud=float(similitudes[i]))
            for i in orden
            if similitudes[i] >= SIMILITUD_MINIMA
        ]
