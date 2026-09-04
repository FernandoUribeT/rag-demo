"""Pruebas de la frontera de pagos.

Se prueba contra una pasarela falsa: no sale ninguna petición a Stripe y no
hace falta ninguna clave. Lo que se verifica es la lógica que rodea al cobro,
que es donde están los defectos caros.
"""

import pytest

from rag_demo.creditos import LibroEnMemoria, Otorgamiento
from rag_demo.pagos import (
    PAQUETES,
    FirmaInvalida,
    PagoConfirmado,
    PaqueteDesconocido,
    creditos_de,
    precio_de,
)


# ── Catálogo del servidor ────────────────────────────────────────────────────

def test_el_catalogo_define_creditos_y_precio():
    assert creditos_de("creditos_10") == 10
    assert precio_de("creditos_10") == 900


def test_un_paquete_inventado_se_rechaza():
    """El comprador elige una clave; si no está en el catálogo, no hay venta."""
    with pytest.raises(PaqueteDesconocido):
        creditos_de("creditos_gratis")


def test_ningun_paquete_tiene_precio_cero():
    """Un precio en cero seria una compra gratuita disfrazada de compra."""
    assert all(precio > 0 for _, precio in PAQUETES.values())


def test_comprar_mas_credito_cuesta_menos_por_credito():
    """El descuento por volumen debe existir y debe ir en la dirección correcta."""
    unitarios = [precio / creditos for creditos, precio in PAQUETES.values()]
    assert unitarios == sorted(unitarios, reverse=True)


# ── Webhook: de pago confirmado a créditos ───────────────────────────────────

def aplicar(libro: LibroEnMemoria, pago: PagoConfirmado) -> bool:
    return libro.otorgar(
        Otorgamiento(
            cliente=pago.cliente, creditos=pago.creditos, evento_id=pago.evento_id
        )
    )


def test_un_pago_confirmado_otorga_sus_creditos():
    libro = LibroEnMemoria()
    aplicar(libro, PagoConfirmado(evento_id="evt_1", cliente="ana", creditos=50))
    assert libro.saldo("ana") == 50


def test_el_reintento_de_stripe_no_duplica_los_creditos():
    """Stripe reenvía el mismo evento hasta recibir 2xx; debe ser inofensivo."""
    libro = LibroEnMemoria()
    pago = PagoConfirmado(evento_id="evt_1", cliente="ana", creditos=50)

    aplicar(libro, pago)
    aplicar(libro, pago)
    aplicar(libro, pago)

    assert libro.saldo("ana") == 50


# ── Firma y eventos, contra la pasarela falsa ────────────────────────────────

def test_una_firma_invalida_se_rechaza(pasarela):
    """El endpoint del webhook es público: la firma es lo único que separa a
    Stripe de cualquiera que mande un POST diciendo 'este cliente pagó'."""
    with pytest.raises(FirmaInvalida):
        pasarela.leer_evento(b'{"type":"checkout.session.completed"}', "firma-falsa")


def test_un_evento_de_otro_tipo_se_ignora(pasarela):
    """Stripe manda decenas de tipos; ignorar no es fallar."""
    cuerpo, firma = pasarela.firmar(
        {"id": "evt_9", "type": "customer.created", "data": {"object": {}}}
    )
    assert pasarela.leer_evento(cuerpo, firma) is None


def test_una_sesion_completada_pero_no_pagada_se_ignora(pasarela):
    """Con métodos asíncronos la sesión se completa antes de que entre el
    dinero. Otorgar aquí regalaría créditos sin cobro."""
    cuerpo, firma = pasarela.firmar(
        {
            "id": "evt_2",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "payment_status": "unpaid",
                    "client_reference_id": "ana",
                    "metadata": {"creditos": "50"},
                }
            },
        }
    )
    assert pasarela.leer_evento(cuerpo, firma) is None


def test_una_sesion_pagada_devuelve_el_pago(pasarela):
    cuerpo, firma = pasarela.firmar(
        {
            "id": "evt_3",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "payment_status": "paid",
                    "client_reference_id": "ana",
                    "metadata": {"creditos": "50"},
                }
            },
        }
    )
    pago = pasarela.leer_evento(cuerpo, firma)
    assert pago == PagoConfirmado(evento_id="evt_3", cliente="ana", creditos=50)


def test_el_precio_no_lo_decide_el_comprador(pasarela):
    """Se pide un paquete por su clave; el precio sale del catálogo del servidor."""
    sesion = pasarela.crear_sesion("creditos_50", "ana")
    assert pasarela.ultimo_cobro == precio_de("creditos_50")


def test_no_se_puede_crear_una_sesion_de_un_paquete_inventado(pasarela):
    with pytest.raises(PaqueteDesconocido):
        pasarela.crear_sesion("creditos_gratis", "ana")
