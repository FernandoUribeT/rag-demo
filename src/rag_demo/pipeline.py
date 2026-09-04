"""El flujo completo: pregunta → recuperación → respuesta citada.

Esta es la pieza que responde la pregunta de negocio: un usuario manda una
consulta, el sistema busca en la información interna, y un modelo redacta la
respuesta usando solo lo que se recuperó.

La regla que gobierna todo el módulo: **si no hay contexto, no hay respuesta.**
Un sistema que inventa cuando no encuentra nada es peor que uno que dice que
no sabe, porque el usuario no tiene forma de distinguir una respuesta buena de
una inventada.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .chunking import Fragmento, trocear
from .contracts import Embedder, LanguageModel
from .store import Coincidencia, IndiceVectorial

SIN_CONTEXTO = (
    "No encontré información sobre eso en los documentos disponibles."
)

PLANTILLA = """Responde la pregunta usando únicamente el contexto que sigue.

Reglas:
- Si el contexto no contiene la respuesta, responde exactamente: {sin_contexto}
- No agregues información que no esté en el contexto.
- Cita entre corchetes el identificador del fragmento que usaste.

Contexto:
{contexto}

Pregunta: {pregunta}

Respuesta:"""


@dataclass(frozen=True)
class Respuesta:
    texto: str
    fuentes: list[Coincidencia]

    @property
    def abstuvo(self) -> bool:
        """True cuando el sistema decidió no responder por falta de contexto."""
        return not self.fuentes


class BaseDeConocimiento:
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._indice = IndiceVectorial()

    def __len__(self) -> int:
        return len(self._indice)

    def agregar_documento(self, texto: str, nombre: str) -> list[Fragmento]:
        fragmentos = trocear(texto, nombre)
        if not fragmentos:
            return []
        vectores = self._embedder.embed([f.texto for f in fragmentos])
        self._indice.agregar(fragmentos, vectores)
        return fragmentos

    def cargar_carpeta(self, carpeta: Path, patron: str = "*.md") -> int:
        documentos = sorted(carpeta.glob(patron))
        for ruta in documentos:
            self.agregar_documento(ruta.read_text(encoding="utf-8"), ruta.stem)
        return len(documentos)

    def recuperar(self, pregunta: str, k: int = 4) -> list[Coincidencia]:
        if not pregunta.strip():
            return []
        vector = self._embedder.embed([pregunta])[0]
        return self._indice.buscar(vector, k=k)


def armar_prompt(pregunta: str, coincidencias: list[Coincidencia]) -> str:
    contexto = "\n\n".join(
        f"[{c.fragmento.id}] {c.fragmento.texto}" for c in coincidencias
    )
    return PLANTILLA.format(
        sin_contexto=SIN_CONTEXTO, contexto=contexto, pregunta=pregunta
    )


def responder(
    pregunta: str,
    base: BaseDeConocimiento,
    modelo: LanguageModel,
    *,
    k: int = 4,
) -> Respuesta:
    """Recupera contexto y redacta la respuesta.

    Cuando la recuperación no encuentra nada por encima del umbral, el modelo
    ni siquiera se invoca: se abstiene de inmediato. Además de ser lo correcto,
    ahorra la llamada más cara del flujo.
    """
    coincidencias = base.recuperar(pregunta, k=k)
    if not coincidencias:
        return Respuesta(texto=SIN_CONTEXTO, fuentes=[])

    texto = modelo.complete(armar_prompt(pregunta, coincidencias)).strip()

    # El umbral filtra la mayor parte del ruido, pero no todo: un fragmento
    # puede superarlo y aun así no contener la respuesta. Cuando el modelo lo
    # detecta y se abstiene, se descartan las fuentes.
    #
    # Devolverlas sería presentar como respaldo unos fragmentos que no
    # respaldan nada, y la interfaz mostraría el resultado como si hubiera
    # respondido. Abstenerse es un resultado distinto de responder.
    if SIN_CONTEXTO in texto:
        return Respuesta(texto=SIN_CONTEXTO, fuentes=[])

    return Respuesta(texto=texto, fuentes=coincidencias)
