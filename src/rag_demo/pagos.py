"""Frontera con Stripe.

Dos operaciones y nada más: crear una sesión de pago, y verificar que un
webhook viene de verdad de Stripe. Todo lo que decide qué pasa después vive en
creditos.py, que no sabe que Stripe existe.

Tres reglas que gobiernan este módulo, y las tres son de seguridad:

1. **El precio lo pone el servidor, nunca el cliente.** Si el navegador manda
   cuánto cuesta, cualquiera edita la petición y compra por un centavo. Aquí el
   comprador solo elige un identificador de paquete; el precio se busca en el
   catálogo del servidor.

2. **Un webhook sin firma válida se rechaza.** El endpoint es público: cualquiera
   puede mandarle un POST diciendo "este cliente pagó". La firma es lo único que
   distingue a Stripe de un impostor.

3. **Los créditos se otorgan en el webhook, no en la página de éxito.** La URL de
   éxito la puede abrir el usuario a mano, sin haber pagado nunca. El webhook lo
   manda Stripe cuando el cobro se confirmó de verdad.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Catálogo del servidor. El comprador elige una clave, no un precio.
PAQUETES: dict[str, tuple[int, int]] = {
    # clave: (créditos, precio en centavos de USD)
    "creditos_10": (10, 900),
    "creditos_50": (50, 3_900),
    "creditos_200": (200, 12_900),
}


class PaqueteDesconocido(ValueError):
    """La clave de paquete no está en el catálogo del servidor."""


class FirmaInvalida(ValueError):
    """El webhook no viene de Stripe, o llegó alterado."""


@dataclass(frozen=True)
class SesionDePago:
    id: str
    url: str


@dataclass(frozen=True)
class PagoConfirmado:
    """Lo mínimo que hace falta para otorgar créditos."""

    evento_id: str
    cliente: str
    creditos: int


class PasarelaDePagos(Protocol):
    def crear_sesion(self, paquete: str, cliente: str) -> SesionDePago: ...

    def leer_evento(self, cuerpo: bytes, firma: str) -> PagoConfirmado | None:
        """Verifica la firma y devuelve el pago, o None si el evento no aplica.

        Levanta FirmaInvalida cuando la firma no cuadra. Devolver None es
        distinto de fallar: Stripe manda decenas de tipos de evento y la
        mayoría no interesa aquí.
        """
        ...


def creditos_de(paquete: str) -> int:
    if paquete not in PAQUETES:
        raise PaqueteDesconocido(paquete)
    return PAQUETES[paquete][0]


def precio_de(paquete: str) -> int:
    if paquete not in PAQUETES:
        raise PaqueteDesconocido(paquete)
    return PAQUETES[paquete][1]


class PasarelaStripe:
    """Implementación real.

    La librería se importa en el constructor para que el módulo se pueda
    importar y probar donde `stripe` no está instalado, que es el caso de CI.
    """

    def __init__(
        self,
        clave_secreta: str,
        secreto_webhook: str,
        url_exito: str = "http://localhost:4200/pago/exito",
        url_cancelado: str = "http://localhost:4200/pago/cancelado",
    ) -> None:
        import stripe  # noqa: PLC0415

        if not clave_secreta or not secreto_webhook:
            raise ValueError("faltan las claves de Stripe")

        self._stripe = stripe
        self._stripe.api_key = clave_secreta
        self._secreto_webhook = secreto_webhook
        self._url_exito = url_exito
        self._url_cancelado = url_cancelado

    def crear_sesion(self, paquete: str, cliente: str) -> SesionDePago:
        creditos = creditos_de(paquete)   # valida contra el catálogo del servidor
        precio = precio_de(paquete)

        sesion = self._stripe.checkout.Session.create(
            mode="payment",
            success_url=self._url_exito,
            cancel_url=self._url_cancelado,
            client_reference_id=cliente,
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": precio,
                        "product_data": {"name": f"{creditos} créditos de indexado"},
                    },
                }
            ],
            # Viaja de ida y vuelta: Stripe lo devuelve en el webhook, así no
            # hace falta consultar de nuevo qué se compró.
            metadata={"paquete": paquete, "creditos": str(creditos)},
        )
        return SesionDePago(id=sesion.id, url=sesion.url)

    def leer_evento(self, cuerpo: bytes, firma: str) -> PagoConfirmado | None:
        try:
            evento = self._stripe.Webhook.construct_event(
                cuerpo, firma, self._secreto_webhook
            )
        except Exception as exc:  # firma inválida o cuerpo alterado
            raise FirmaInvalida(str(exc)) from exc

        if evento["type"] != "checkout.session.completed":
            return None

        sesion = evento["data"]["object"]

        # Una sesión completada no siempre está pagada: puede quedar pendiente
        # con métodos asíncronos. Otorgar aquí regalaría créditos sin cobro.
        if sesion.get("payment_status") != "paid":
            return None

        return PagoConfirmado(
            evento_id=evento["id"],
            cliente=sesion["client_reference_id"],
            creditos=int(sesion["metadata"]["creditos"]),
        )
