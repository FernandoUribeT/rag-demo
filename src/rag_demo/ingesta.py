"""Ingesta de documentos: guardar, encolar, indexar.

Trocear y vectorizar un documento largo tarda. Hacerlo dentro de la petición
deja al usuario esperando y, si el proceso muere a la mitad, el documento queda
indexado por partes sin que nadie se entere.

El flujo se parte en dos:

    aceptar()   guarda el archivo y encola el trabajo. Responde de inmediato.
    procesar()  lo ejecuta un worker aparte: lee, trocea, vectoriza, indexa.

Así la carga es rápida, el trabajo pesado es reintentable, y se puede escalar
el indexado agregando workers sin tocar la API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .pipeline import BaseDeConocimiento
from .storage import AlmacenDeDocumentos, clave_de_documento


@dataclass(frozen=True)
class TrabajoDeIndexado:
    """Lo que viaja por la cola: una referencia, nunca el documento entero."""

    clave: str
    nombre: str

    def serializar(self) -> bytes:
        return json.dumps({"clave": self.clave, "nombre": self.nombre}).encode("utf-8")

    @staticmethod
    def deserializar(crudo: bytes) -> "TrabajoDeIndexado":
        datos = json.loads(crudo)
        if not isinstance(datos, dict):
            raise ValueError("el mensaje no es un objeto")
        clave, nombre = datos.get("clave"), datos.get("nombre")
        if not isinstance(clave, str) or not isinstance(nombre, str):
            raise ValueError("al mensaje le faltan campos obligatorios")
        if not clave or not nombre:
            raise ValueError("los campos del mensaje no pueden ir vacíos")
        return TrabajoDeIndexado(clave=clave, nombre=nombre)


class Cola(Protocol):
    def publicar(self, mensaje: bytes) -> None: ...

    def consumir(self) -> bytes | None:
        """Devuelve el siguiente mensaje, o None si no hay ninguno."""
        ...


class ColaEnMemoria:
    """Implementación de referencia; también es la que usan las pruebas."""

    def __init__(self) -> None:
        self._mensajes: list[bytes] = []

    def __len__(self) -> int:
        return len(self._mensajes)

    def publicar(self, mensaje: bytes) -> None:
        self._mensajes.append(mensaje)

    def consumir(self) -> bytes | None:
        return self._mensajes.pop(0) if self._mensajes else None


def aceptar(
    contenido: bytes,
    nombre: str,
    *,
    almacen: AlmacenDeDocumentos,
    cola: Cola,
) -> TrabajoDeIndexado:
    """Guarda el documento y encola su indexado. No vectoriza nada aquí.

    El mensaje lleva la clave del objeto, no el documento. Un documento grande
    dentro de la cola la convierte en un almacén improvisado, con sus límites
    de tamaño y sin forma de releerlo después.
    """
    if not nombre.strip():
        raise ValueError("el documento necesita un nombre")

    clave = clave_de_documento(nombre.strip(), contenido)
    almacen.guardar(clave, contenido)

    trabajo = TrabajoDeIndexado(clave=clave, nombre=nombre.strip())
    cola.publicar(trabajo.serializar())
    return trabajo


def procesar(
    trabajo: TrabajoDeIndexado,
    *,
    almacen: AlmacenDeDocumentos,
    base: BaseDeConocimiento,
) -> int:
    """Indexa un documento ya guardado. Devuelve cuántos fragmentos generó.

    Es idempotente por diseño: la clave incluye el hash del contenido, así que
    reprocesar el mismo trabajo produce exactamente los mismos fragmentos. Eso
    importa porque una cola garantiza *al menos una* entrega, no exactamente
    una: un mensaje se puede repetir y el sistema debe tolerarlo.
    """
    contenido = almacen.leer(trabajo.clave)
    fragmentos = base.agregar_documento(contenido.decode("utf-8"), trabajo.nombre)
    return len(fragmentos)


def drenar(
    *,
    cola: Cola,
    almacen: AlmacenDeDocumentos,
    base: BaseDeConocimiento,
    maximo: int = 100,
) -> int:
    """Procesa los trabajos pendientes. Devuelve cuántos documentos indexó.

    El tope evita que un worker se quede atrapado indefinidamente si algo sigue
    publicando más rápido de lo que él consume.
    """
    procesados = 0
    while procesados < maximo:
        crudo = cola.consumir()
        if crudo is None:
            break
        procesar(
            TrabajoDeIndexado.deserializar(crudo), almacen=almacen, base=base
        )
        procesados += 1
    return procesados
