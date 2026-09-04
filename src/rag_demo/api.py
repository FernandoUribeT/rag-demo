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

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .creditos import LibroDeCreditos, LibroEnMemoria, Otorgamiento, SaldoInsuficiente
from .ingesta import Cola, ColaEnMemoria, aceptar
from .pagos import FirmaInvalida, PaqueteDesconocido, PasarelaDePagos
from .pipeline import BaseDeConocimiento, responder
from .storage import AlmacenDeDocumentos, AlmacenEnMemoria


@dataclass
class Servicios:
    """Lo que la API necesita para trabajar. Las pruebas lo reemplazan entero."""

    base: BaseDeConocimiento
    modelo: Any
    almacen: AlmacenDeDocumentos = field(default_factory=AlmacenEnMemoria)
    cola: Cola = field(default_factory=ColaEnMemoria)
    libro: LibroDeCreditos = field(default_factory=LibroEnMemoria)
    pasarela: PasarelaDePagos | None = None


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


class CompraEntrante(BaseModel):
    # El comprador elige una clave del catálogo, nunca un precio.
    paquete: str = Field(min_length=1, max_length=64)


# Indexar un documento cuesta cómputo; este es su precio en créditos.
CREDITOS_POR_DOCUMENTO = 1


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
        entrada: DocumentoEntrante,
        cliente: str = Header(alias="X-Cliente"),
        s: Servicios = Depends(obtener_servicios),
    ) -> dict[str, str]:
        """Cobra créditos, acepta el documento y encola su indexado.

        Devuelve 202 y no 200 a propósito: el documento fue aceptado, pero
        todavía no está indexado. Responder 200 daría a entender que ya se
        puede consultar, y no es cierto hasta que el worker lo procese.

        El cobro va ANTES de encolar. Al revés, un saldo insuficiente dejaría
        el trabajo en la cola y el worker indexaría algo que nadie pagó.
        """
        try:
            restante = s.libro.consumir(cliente, CREDITOS_POR_DOCUMENTO)
        except SaldoInsuficiente as exc:
            # 402 Payment Required: el cliente está autenticado y la petición es
            # válida; lo único que falta es saldo.
            raise HTTPException(status_code=402, detail=str(exc)) from exc

        trabajo = aceptar(
            entrada.contenido.encode("utf-8"),
            entrada.nombre,
            almacen=s.almacen,
            cola=s.cola,
        )
        return {
            "clave": trabajo.clave,
            "estado": "encolado",
            "creditos_restantes": str(restante),
        }

    @app.get("/api/saldo")
    def saldo(
        cliente: str = Header(alias="X-Cliente"),
        s: Servicios = Depends(obtener_servicios),
    ) -> dict[str, int]:
        return {"creditos": s.libro.saldo(cliente)}

    @app.post("/api/checkout")
    def crear_checkout(
        entrada: CompraEntrante,
        cliente: str = Header(alias="X-Cliente"),
        s: Servicios = Depends(obtener_servicios),
    ) -> dict[str, str]:
        """Crea la sesión de pago. El precio sale del catálogo del servidor."""
        if s.pasarela is None:
            raise HTTPException(status_code=503, detail="pagos no configurados")
        try:
            sesion = s.pasarela.crear_sesion(entrada.paquete, cliente)
        except PaqueteDesconocido as exc:
            raise HTTPException(status_code=422, detail="paquete desconocido") from exc
        return {"id": sesion.id, "url": sesion.url}

    @app.post("/api/webhooks/stripe")
    async def webhook_stripe(
        peticion: Request,
        stripe_signature: str = Header(alias="Stripe-Signature"),
        s: Servicios = Depends(obtener_servicios),
    ) -> dict[str, str]:
        """Otorga los créditos cuando el cobro se confirmó.

        Aquí y no en la página de éxito: esa URL la puede abrir cualquiera a
        mano, sin haber pagado. Este webhook lo manda Stripe.

        Se lee el cuerpo crudo con await peticion.body() porque la firma se
        calcula sobre los bytes exactos: dejar que FastAPI lo convierta a JSON
        y volverlo a serializar cambia el contenido y rompe la verificación.
        """
        if s.pasarela is None:
            raise HTTPException(status_code=503, detail="pagos no configurados")

        cuerpo = await peticion.body()
        try:
            pago = s.pasarela.leer_evento(cuerpo, stripe_signature)
        except FirmaInvalida as exc:
            raise HTTPException(status_code=400, detail="firma inválida") from exc

        if pago is None:
            # Evento que no aplica. Se responde 200 para que Stripe no reintente
            # algo que nunca vamos a procesar.
            return {"estado": "ignorado"}

        aplicado = s.libro.otorgar(
            Otorgamiento(
                cliente=pago.cliente,
                creditos=pago.creditos,
                evento_id=pago.evento_id,
            )
        )
        return {"estado": "otorgado" if aplicado else "duplicado"}

    return app
