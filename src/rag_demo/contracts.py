"""Contratos de las dos piezas que dependen de un modelo.

Todo lo demás del sistema —trocear, indexar, buscar, armar el prompt— es
determinista y se prueba sin red. Solo estas dos operaciones necesitan un
modelo detrás, así que se aíslan aquí como protocolos.

Esa frontera es la decisión de diseño central del proyecto: permite ejecutar
la suite completa en CI, sin claves ni servidor, y cambiar de proveedor sin
tocar la lógica de recuperación.
"""

from __future__ import annotations

from typing import Protocol, Sequence


class Embedder(Protocol):
    """Convierte texto en un vector."""

    @property
    def dimensions(self) -> int:
        """Longitud de los vectores que produce."""
        ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Devuelve un vector por cada texto, en el mismo orden."""
        ...


class LanguageModel(Protocol):
    """Genera una respuesta a partir de un prompt."""

    def complete(self, prompt: str) -> str:
        ...
