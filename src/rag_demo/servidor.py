"""Punto de entrada del servidor.

    uv run uvicorn rag_demo.servidor:app --reload

Arma la aplicación leyendo la configuración del entorno. Las claves nunca van
en el código: se leen de variables de entorno, que es lo que permite tener unas
en desarrollo y otras en producción sin tocar un solo archivo.

Si faltan las claves de Stripe, el servidor arranca igual pero sin pagos. Es
deliberado: se puede levantar todo lo demás para desarrollar sin necesitar una
cuenta de Stripe.
"""

from __future__ import annotations

import os
from pathlib import Path

from .api import Servicios, crear_app
from .pipeline import BaseDeConocimiento
from .providers import OllamaEmbedder, OllamaLanguageModel

CORPUS = Path(__file__).resolve().parent.parent.parent / "corpus"


def _pasarela():
    """Devuelve la pasarela real, o None si no hay claves configuradas."""
    clave = os.getenv("STRIPE_SECRET_KEY", "")
    secreto = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not clave or not secreto:
        return None

    # Se importa aquí para no exigir la librería cuando los pagos están apagados.
    from .pagos import PasarelaStripe

    return PasarelaStripe(
        clave_secreta=clave,
        secreto_webhook=secreto,
        url_exito=os.getenv("URL_EXITO", "http://localhost:4200/pago/exito"),
        url_cancelado=os.getenv("URL_CANCELADO", "http://localhost:4200/pago/cancelado"),
    )


def crear() -> object:
    base = BaseDeConocimiento(OllamaEmbedder())
    if CORPUS.is_dir():
        base.cargar_carpeta(CORPUS)

    return crear_app(
        Servicios(
            base=base,
            modelo=OllamaLanguageModel(),
            pasarela=_pasarela(),
        ),
        origenes=os.getenv("ORIGENES_PERMITIDOS", "http://localhost:4200").split(","),
    )


app = crear()
