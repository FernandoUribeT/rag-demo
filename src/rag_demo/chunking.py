"""Troceado de documentos.

Un documento entero es mala unidad de recuperación: si el usuario pregunta
por un detalle, recuperar veinte páginas mete ruido y gasta contexto. Trocear
demasiado fino es igual de malo, porque parte la idea a la mitad y ningún
fragmento llega completo.

Aquí se trocea por párrafo y se agrupan párrafos contiguos hasta un tamaño
objetivo, respetando el límite del párrafo. Así ningún fragmento corta una
oración por la mitad.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Un fragmento demasiado corto no tiene contexto suficiente para responder;
# uno demasiado largo diluye la señal al comparar vectores.
TAMANO_OBJETIVO = 600
TAMANO_MINIMO = 80


@dataclass(frozen=True)
class Fragmento:
    """Un trozo recuperable, con su origen para poder citarlo."""

    texto: str
    documento: str
    indice: int

    @property
    def id(self) -> str:
        return f"{self.documento}#{self.indice}"


def _parrafos(texto: str) -> list[str]:
    partes = re.split(r"\n\s*\n", texto.strip())
    return [re.sub(r"\s+", " ", p).strip() for p in partes if p.strip()]


def trocear(texto: str, documento: str) -> list[Fragmento]:
    """Divide un documento en fragmentos recuperables.

    Agrupa párrafos contiguos hasta acercarse al tamaño objetivo. Nunca parte
    un párrafo: es preferible un fragmento algo más largo que una idea
    truncada.
    """
    fragmentos: list[Fragmento] = []
    actual: list[str] = []
    largo = 0

    def cerrar() -> None:
        nonlocal actual, largo
        if not actual:
            return
        unido = " ".join(actual)
        # Un fragmento por debajo del mínimo se pega al anterior en lugar de
        # quedar suelto: solo, no responde nada.
        if len(unido) < TAMANO_MINIMO and fragmentos:
            previo = fragmentos[-1]
            fragmentos[-1] = Fragmento(
                texto=f"{previo.texto} {unido}",
                documento=previo.documento,
                indice=previo.indice,
            )
        else:
            fragmentos.append(
                Fragmento(texto=unido, documento=documento, indice=len(fragmentos))
            )
        actual = []
        largo = 0

    for parrafo in _parrafos(texto):
        if largo and largo + len(parrafo) > TAMANO_OBJETIVO:
            cerrar()
        actual.append(parrafo)
        largo += len(parrafo)

    cerrar()
    return fragmentos
