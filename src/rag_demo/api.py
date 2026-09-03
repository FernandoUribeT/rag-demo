"""API HTTP del servicio.

Expone la consulta y la ingesta para que las consuma una interfaz web. La
lógica vive en pipeline.py e ingesta.py; esto es solo el borde HTTP.

Las dependencias se resuelven por inyección (`Depends`) y no como variables de
módulo, para que las pruebas puedan sustituirlas por dobles sin levantar Ollama
ni ningún servicio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ingesta import Cola, ColaEnMemoria, aceptar
from .pipeline import BaseDeConocimiento, responder
from .storage import AlmacenDeDocumentos, AlmacenEnMemoria


@dataclass
class Servicios:
    """Lo que la API necesita para trabajar. Las pruebas lo reemplazan entero."""

    base: BaseDeConocimiento
    modelo: Any
    almacen: AlmacenDeDocumentos = field(default_factory=AlmacenEnMemoria)
    cola: Cola = field(default_factory=ColaEnMemoria)


class PreguntaEntrante(BaseModel):
    pregunta: str = Field(min_length=1, max_length=2_000)
    k: int = Field(default=4, ge=1, le=20)


class FuenteSaliente(BaseModel):
    id: str
    documento: str
    similitud: float
    extracto: str


class RespuestaSaliente(BaseModel):
    texto: str
    abstuvo: bool
    fuentes: list[FuenteSaliente]


class DocumentoEntrante(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    contenido: str = Field(min_length=1)


def crear_app(servicios: Servicios, *, origenes: list[str] | None = None) -> FastAPI:
    app = FastAPI(title="rag-demo", version="0.1.0")

    # CORS restringido a los orígenes declarados. Un comodín aquí dejaría que
    # cualquier sitio consulte esta API desde el navegador de un usuario.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origenes or ["http://localhost:4200"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def obtener_servicios() -> Servicios:
        return servicios

    @app.get("/api/salud")
    def salud(s: Servicios = Depends(obtener_servicios)) -> dict[str, Any]:
        return {"estado": "ok", "fragmentos": len(s.base)}

    @app.post("/api/preguntar", response_model=RespuestaSaliente)
    def preguntar(
        entrada: PreguntaEntrante, s: Servicios = Depends(obtener_servicios)
    ) -> RespuestaSaliente:
        if not entrada.pregunta.strip():
            raise HTTPException(status_code=422, detail="la pregunta viene vacía")

        respuesta = responder(entrada.pregunta, s.base, s.modelo, k=entrada.k)
        return RespuestaSaliente(
            texto=respuesta.texto,
            abstuvo=respuesta.abstuvo,
            fuentes=[
                FuenteSaliente(
                    id=c.fragmento.id,
                    documento=c.fragmento.documento,
                    similitud=round(c.similitud, 4),
                    # Se manda un extracto y no el fragmento entero: la interfaz
                    # solo necesita mostrar de dónde salió la respuesta.
                    extracto=c.fragmento.texto[:240],
                )
                for c in respuesta.fuentes
            ],
        )

    @app.post("/api/documentos", status_code=202)
    def subir_documento(
        entrada: DocumentoEntrante, s: Servicios = Depends(obtener_servicios)
    ) -> dict[str, str]:
        """Acepta el documento y encola su indexado.

        Devuelve 202 y no 200 a propósito: el documento fue aceptado, pero
        todavía no está indexado. Responder 200 daría a entender que ya se
        puede consultar, y no es cierto hasta que el worker lo procese.
        """
        trabajo = aceptar(
            entrada.contenido.encode("utf-8"),
            entrada.nombre,
            almacen=s.almacen,
            cola=s.cola,
        )
        return {"clave": trabajo.clave, "estado": "encolado"}

    return app
