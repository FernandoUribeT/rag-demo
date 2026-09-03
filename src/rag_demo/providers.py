"""Implementaciones reales de los contratos, contra Ollama.

Se eligió Ollama porque corre en local: el corpus nunca sale de la máquina.
Para documentos internos de una empresa —contratos, procedimientos,
expedientes— esa diferencia suele ser el requisito que decide, no una
preferencia técnica.

Cambiar a OpenAI, Gemini o Claude es escribir otra clase con estos dos
métodos. Nada del resto del sistema se entera.
"""

from __future__ import annotations

from typing import Sequence

import httpx

OLLAMA = "http://127.0.0.1:11434"

# bge-m3 es multilingüe, lo que importa cuando el corpus está en español y la
# pregunta puede llegar en cualquiera de los dos idiomas.
MODELO_EMBEDDING = "bge-m3"
MODELO_LENGUAJE = "llama3.1:8b"

TIEMPO_LIMITE = 120.0


class OllamaEmbedder:
    def __init__(
        self,
        modelo: str = MODELO_EMBEDDING,
        base_url: str = OLLAMA,
        dimensions: int = 1024,
    ) -> None:
        self._modelo = modelo
        self._base_url = base_url.rstrip("/")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        respuesta = httpx.post(
            f"{self._base_url}/api/embed",
            json={"model": self._modelo, "input": list(texts)},
            timeout=TIEMPO_LIMITE,
        )
        respuesta.raise_for_status()
        vectores = respuesta.json().get("embeddings")
        if not isinstance(vectores, list) or len(vectores) != len(texts):
            raise RuntimeError("Ollama devolvió un número de vectores distinto al pedido")
        return vectores


class OllamaLanguageModel:
    def __init__(
        self, modelo: str = MODELO_LENGUAJE, base_url: str = OLLAMA
    ) -> None:
        self._modelo = modelo
        self._base_url = base_url.rstrip("/")

    def complete(self, prompt: str) -> str:
        respuesta = httpx.post(
            f"{self._base_url}/api/generate",
            json={
                "model": self._modelo,
                "prompt": prompt,
                "stream": False,
                # Temperatura baja: en un sistema que debe ceñirse al contexto,
                # la creatividad es exactamente el defecto que se quiere evitar.
                "options": {"temperature": 0.1},
            },
            timeout=TIEMPO_LIMITE,
        )
        respuesta.raise_for_status()
        return respuesta.json().get("response", "")
