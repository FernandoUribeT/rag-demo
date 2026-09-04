"""Dobles de prueba para las dos piezas que dependen de un modelo.

Toda la lógica de recuperación se verifica sin red, sin claves y sin servidor.
Esa es la razón de que `Embedder` y `LanguageModel` sean protocolos: lo que en
producción es una llamada a Ollama, aquí es una función determinista de tres
líneas.

Una suite que necesita un modelo real no corre en CI, y una suite que no corre
en CI termina no corriendo nunca.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

import pytest

# Vocabulario fijo: cada palabra ocupa una posición del vector. Es una bolsa de
# palabras, no un modelo semántico — no entiende sinónimos, y no pretende
# hacerlo. Sirve para verificar que el índice ordena, umbraliza y se abstiene
# como debe, que es lo que estas pruebas comprueban.
VOCABULARIO = [
    "carta", "porte", "traslado", "mercancia", "clave", "catalogo",
    "expediente", "proveedor", "vigencia", "rfc", "constancia", "ocr",
    "cancelacion", "plazo", "banco", "domicilio",
]


def _tokens(texto: str) -> list[str]:
    limpio = (
        texto.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    return re.findall(r"[a-z]+", limpio)


class EmbedderDeterminista:
    """Bolsa de palabras normalizada sobre un vocabulario fijo."""

    @property
    def dimensions(self) -> int:
        return len(VOCABULARIO)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectores = []
        for texto in texts:
            cuenta = Counter(_tokens(texto))
            crudo = [float(cuenta.get(palabra, 0)) for palabra in VOCABULARIO]
            norma = math.sqrt(sum(v * v for v in crudo))
            vectores.append([v / norma for v in crudo] if norma else crudo)
        return vectores


class ModeloQueRepiteElContexto:
    """Devuelve el prompt recibido, para poder afirmar sobre lo que se le mandó."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "respuesta generada"


class ModeloQueExplota:
    """Falla si se le invoca. Verifica que la abstención evite la llamada."""

    def complete(self, prompt: str) -> str:  # pragma: no cover
        raise AssertionError("el modelo no debió invocarse sin contexto recuperado")


@pytest.fixture
def embedder() -> EmbedderDeterminista:
    return EmbedderDeterminista()


@pytest.fixture
def modelo() -> ModeloQueRepiteElContexto:
    return ModeloQueRepiteElContexto()


# ── Pasarela de pagos falsa ──────────────────────────────────────────────────

import hashlib
import hmac
import json

from rag_demo.pagos import (
    FirmaInvalida,
    PagoConfirmado,
    SesionDePago,
    creditos_de,
    precio_de,
)

SECRETO_DE_PRUEBA = "whsec_prueba"


class PasarelaFalsa:
    """Reproduce el contrato de Stripe sin salir a la red.

    Firma con HMAC-SHA256 igual que Stripe, para que la prueba de firma
    inválida verifique el mecanismo real y no una comparación de cadenas.
    """

    def __init__(self) -> None:
        self.ultimo_cobro: int | None = None

    def firmar(self, evento: dict) -> tuple[bytes, str]:
        cuerpo = json.dumps(evento).encode("utf-8")
        firma = hmac.new(
            SECRETO_DE_PRUEBA.encode(), cuerpo, hashlib.sha256
        ).hexdigest()
        return cuerpo, firma

    def crear_sesion(self, paquete: str, cliente: str) -> SesionDePago:
        creditos = creditos_de(paquete)      # valida contra el catálogo
        self.ultimo_cobro = precio_de(paquete)
        return SesionDePago(
            id=f"cs_test_{cliente}_{creditos}", url="https://checkout.stripe.test/x"
        )

    def leer_evento(self, cuerpo: bytes, firma: str) -> PagoConfirmado | None:
        esperada = hmac.new(
            SECRETO_DE_PRUEBA.encode(), cuerpo, hashlib.sha256
        ).hexdigest()
        # compare_digest y no ==: evita filtrar información por tiempo de
        # comparación, que es como se ataca una verificación de firma.
        if not hmac.compare_digest(esperada, firma):
            raise FirmaInvalida("la firma no corresponde al cuerpo")

        evento = json.loads(cuerpo)
        if evento.get("type") != "checkout.session.completed":
            return None

        sesion = evento["data"]["object"]
        if sesion.get("payment_status") != "paid":
            return None

        return PagoConfirmado(
            evento_id=evento["id"],
            cliente=sesion["client_reference_id"],
            creditos=int(sesion["metadata"]["creditos"]),
        )


@pytest.fixture
def pasarela() -> PasarelaFalsa:
    return PasarelaFalsa()
