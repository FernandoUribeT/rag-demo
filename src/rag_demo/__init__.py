"""RAG demo: pregunta → recuperación sobre documentos internos → respuesta citada."""

from .chunking import Fragmento, trocear
from .contracts import Embedder, LanguageModel
from .pipeline import (
    SIN_CONTEXTO,
    BaseDeConocimiento,
    Respuesta,
    armar_prompt,
    responder,
)
from .store import Coincidencia, IndiceVectorial

__all__ = [
    "BaseDeConocimiento",
    "Coincidencia",
    "Embedder",
    "Fragmento",
    "IndiceVectorial",
    "LanguageModel",
    "Respuesta",
    "SIN_CONTEXTO",
    "armar_prompt",
    "responder",
    "trocear",
]
