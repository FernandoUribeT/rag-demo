"""Almacenamiento del documento original.

El índice guarda vectores y fragmentos, no el archivo. Pero el archivo hay que
conservarlo: para reindexar cuando cambie el modelo de embeddings, para que el
usuario pueda descargar la fuente que se le citó, y porque el troceo de hoy no
es necesariamente el de mañana.

Se usa almacenamiento de objetos y no el sistema de archivos del servidor
porque el worker que indexa puede correr en otra máquina que la API que recibe
la carga. Con un disco local, ese diseño deja de funcionar en cuanto hay más de
un proceso.

MinIO habla el protocolo de S3, así que el mismo código funciona contra MinIO
en local y contra S3 en la nube sin cambiar nada más que la configuración.
"""

from __future__ import annotations

import hashlib
from typing import Protocol


class AlmacenDeDocumentos(Protocol):
    def guardar(self, clave: str, contenido: bytes, tipo: str = "text/markdown") -> str: ...

    def leer(self, clave: str) -> bytes: ...

    def existe(self, clave: str) -> bool: ...


def clave_de_documento(nombre: str, contenido: bytes) -> str:
    """Clave que incluye el hash del contenido.

    Subir dos veces el mismo archivo produce la misma clave, así que no se
    duplica. Y subir una versión corregida con el mismo nombre produce una
    clave distinta, así que no pisa la anterior: las dos quedan disponibles y
    se puede saber cuál fue la que se indexó.
    """
    digest = hashlib.sha256(contenido).hexdigest()[:16]
    return f"{nombre}/{digest}"


class AlmacenEnMemoria:
    """Implementación de referencia; también es la que usan las pruebas."""

    def __init__(self) -> None:
        self._objetos: dict[str, bytes] = {}

    def guardar(self, clave: str, contenido: bytes, tipo: str = "text/markdown") -> str:
        self._objetos[clave] = contenido
        return clave

    def leer(self, clave: str) -> bytes:
        if clave not in self._objetos:
            raise KeyError(clave)
        return self._objetos[clave]

    def existe(self, clave: str) -> bool:
        return clave in self._objetos


class AlmacenMinIO:
    """Almacén compatible con S3.

    La librería se importa dentro del constructor para que el módulo se pueda
    importar y probar donde no está instalada, que es el caso de CI.
    """

    def __init__(
        self,
        endpoint: str = "127.0.0.1:9000",
        bucket: str = "rag-demo",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        secure: bool = False,
    ) -> None:
        from minio import Minio  # noqa: PLC0415

        self._cliente = Minio(
            endpoint, access_key=access_key, secret_key=secret_key, secure=secure
        )
        self._bucket = bucket
        if not self._cliente.bucket_exists(bucket):
            self._cliente.make_bucket(bucket)

    def guardar(self, clave: str, contenido: bytes, tipo: str = "text/markdown") -> str:
        import io  # noqa: PLC0415

        self._cliente.put_object(
            self._bucket, clave, io.BytesIO(contenido), len(contenido), content_type=tipo
        )
        return clave

    def leer(self, clave: str) -> bytes:
        respuesta = self._cliente.get_object(self._bucket, clave)
        try:
            return respuesta.read()
        finally:
            # MinIO exige cerrar y liberar la conexión explícitamente; sin esto
            # el pool se agota tras unas cuantas lecturas.
            respuesta.close()
            respuesta.release_conn()

    def existe(self, clave: str) -> bool:
        from minio.error import S3Error  # noqa: PLC0415

        try:
            self._cliente.stat_object(self._bucket, clave)
            return True
        except S3Error:
            return False
