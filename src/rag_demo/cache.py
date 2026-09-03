"""Caché de vectores.

Vectorizar es la operación cara del sistema: cada llamada cruza la red hacia el
modelo. Y se repite más de lo que parece — al reindexar un corpus, la mayoría
de los fragmentos no cambió, y la misma pregunta suele llegar varias veces.

`EmbedderConCache` envuelve a cualquier `Embedder` y consulta la caché antes de
llamar al modelo. El envuelto no se entera; es un decorador, y por eso funciona
igual con Ollama que con cualquier proveedor futuro.

La clave incluye el nombre del modelo: dos modelos distintos producen vectores
distintos e incomparables para el mismo texto. Omitir el modelo de la clave es
el error clásico que devuelve vectores de un modelo viejo tras un cambio.
"""

from __future__ import annotations

import hashlib
import json
from typing import Protocol, Sequence

from .contracts import Embedder


class CacheDeVectores(Protocol):
    """Almacén clave-valor para vectores ya calculados."""

    def obtener(self, clave: str) -> list[float] | None: ...

    def guardar(self, clave: str, vector: list[float]) -> None: ...


def clave_de(modelo: str, texto: str) -> str:
    """Clave estable para un par (modelo, texto).

    Se usa un hash y no el texto crudo porque un fragmento puede medir miles de
    caracteres, y porque así la clave no expone el contenido del documento a
    quien pueda listar las claves de Redis.
    """
    digest = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    return f"emb:{modelo}:{digest}"


class CacheEnMemoria:
    """Implementación de referencia; también es la que usan las pruebas."""

    def __init__(self) -> None:
        self._datos: dict[str, list[float]] = {}
        self.lecturas = 0
        self.aciertos = 0

    def obtener(self, clave: str) -> list[float] | None:
        self.lecturas += 1
        vector = self._datos.get(clave)
        if vector is not None:
            self.aciertos += 1
        return vector

    def guardar(self, clave: str, vector: list[float]) -> None:
        self._datos[clave] = vector


class CacheRedis:
    """Caché compartida entre procesos.

    Importa `redis` dentro del constructor a propósito: así el módulo se puede
    importar —y probar— en un entorno que no tiene la librería instalada, que
    es exactamente el caso de CI.
    """

    def __init__(self, url: str = "redis://127.0.0.1:6379/0", ttl: int = 604_800) -> None:
        import redis  # noqa: PLC0415

        self._cliente = redis.Redis.from_url(url, decode_responses=True)
        self._ttl = ttl

    def obtener(self, clave: str) -> list[float] | None:
        crudo = self._cliente.get(clave)
        if crudo is None:
            return None
        try:
            return json.loads(crudo)
        except json.JSONDecodeError:
            # Un valor corrupto se trata como ausencia: se recalcula y se
            # sobrescribe. Fallar aquí dejaría el sistema caído por un dato
            # de caché, que es justo lo que una caché no debe provocar.
            return None

    def guardar(self, clave: str, vector: list[float]) -> None:
        self._cliente.setex(clave, self._ttl, json.dumps(vector))


class EmbedderConCache:
    """Decorador: consulta la caché y solo pide al modelo lo que falta."""

    def __init__(self, envuelto: Embedder, cache: CacheDeVectores, modelo: str) -> None:
        self._envuelto = envuelto
        self._cache = cache
        self._modelo = modelo

    @property
    def dimensions(self) -> int:
        return self._envuelto.dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Devuelve los vectores en el orden recibido, pidiendo solo los ausentes.

        Un texto repetido dentro de la misma llamada se pide una sola vez: la
        deduplicación ocurre antes de tocar el modelo.
        """
        resultado: list[list[float] | None] = []
        faltantes: dict[str, list[int]] = {}

        for posicion, texto in enumerate(texts):
            vector = self._cache.obtener(clave_de(self._modelo, texto))
            resultado.append(vector)
            if vector is None:
                faltantes.setdefault(texto, []).append(posicion)

        if faltantes:
            textos = list(faltantes)
            nuevos = self._envuelto.embed(textos)
            if len(nuevos) != len(textos):
                raise RuntimeError("el embedder devolvió un número de vectores distinto")
            for texto, vector in zip(textos, nuevos):
                self._cache.guardar(clave_de(self._modelo, texto), vector)
                for posicion in faltantes[texto]:
                    resultado[posicion] = vector

        # Si alguna posición quedó sin vector, se falla aquí y no más adelante.
        # Filtrarlas devolvería una lista más corta que la de entrada, y el
        # error saldría lejos de su causa: al indexar, como "cada fragmento
        # necesita exactamente un vector", o al consultar, como un IndexError.
        sin_vector = [i for i, v in enumerate(resultado) if v is None]
        if sin_vector:
            raise RuntimeError(
                f"quedaron {len(sin_vector)} textos sin vector en las posiciones "
                f"{sin_vector[:5]}"
            )

        return [v for v in resultado if v is not None]
