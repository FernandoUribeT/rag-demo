"""Pruebas del libro de créditos."""

import pytest

from rag_demo.creditos import LibroEnMemoria, Otorgamiento, SaldoInsuficiente


@pytest.fixture
def libro() -> LibroEnMemoria:
    return LibroEnMemoria()


def test_un_cliente_nuevo_arranca_en_cero(libro):
    assert libro.saldo("ana") == 0


def test_otorgar_suma_al_saldo(libro):
    libro.otorgar(Otorgamiento(cliente="ana", creditos=10, evento_id="evt_1"))
    assert libro.saldo("ana") == 10


def test_el_mismo_evento_dos_veces_solo_otorga_una(libro):
    """Stripe reintenta hasta recibir 2xx y puede repetir un evento por diseño.

    Sin esta guarda, un reintento regala créditos: se paga una vez y se recibe
    dos.
    """
    pago = Otorgamiento(cliente="ana", creditos=10, evento_id="evt_1")

    assert libro.otorgar(pago) is True
    assert libro.otorgar(pago) is False
    assert libro.saldo("ana") == 10


def test_dos_pagos_distintos_sí_se_acumulan(libro):
    libro.otorgar(Otorgamiento(cliente="ana", creditos=10, evento_id="evt_1"))
    libro.otorgar(Otorgamiento(cliente="ana", creditos=50, evento_id="evt_2"))
    assert libro.saldo("ana") == 60


def test_los_saldos_no_se_mezclan_entre_clientes(libro):
    libro.otorgar(Otorgamiento(cliente="ana", creditos=10, evento_id="evt_1"))
    libro.otorgar(Otorgamiento(cliente="beto", creditos=5, evento_id="evt_2"))
    assert libro.saldo("ana") == 10
    assert libro.saldo("beto") == 5


def test_un_evento_repetido_no_afecta_a_otro_cliente(libro):
    """La idempotencia va por evento, no por cliente."""
    libro.otorgar(Otorgamiento(cliente="ana", creditos=10, evento_id="evt_1"))
    libro.otorgar(Otorgamiento(cliente="beto", creditos=10, evento_id="evt_1"))
    assert libro.saldo("beto") == 0


@pytest.mark.parametrize("cantidad", [0, -5])
def test_rechaza_otorgar_una_cantidad_no_positiva(libro, cantidad):
    with pytest.raises(ValueError, match="positivos"):
        libro.otorgar(Otorgamiento(cliente="ana", creditos=cantidad, evento_id="evt_1"))


def test_rechaza_otorgar_sin_id_de_evento(libro):
    """Sin id no hay idempotencia posible, así que no se acepta."""
    with pytest.raises(ValueError, match="id de evento"):
        libro.otorgar(Otorgamiento(cliente="ana", creditos=10, evento_id=""))


def test_consumir_descuenta_y_devuelve_el_restante(libro):
    libro.otorgar(Otorgamiento(cliente="ana", creditos=10, evento_id="evt_1"))
    assert libro.consumir("ana", 3) == 7
    assert libro.saldo("ana") == 7


def test_consumir_exactamente_el_saldo_lo_deja_en_cero(libro):
    libro.otorgar(Otorgamiento(cliente="ana", creditos=10, evento_id="evt_1"))
    assert libro.consumir("ana", 10) == 0


def test_no_se_puede_consumir_mas_de_lo_que_hay(libro):
    libro.otorgar(Otorgamiento(cliente="ana", creditos=5, evento_id="evt_1"))
    with pytest.raises(SaldoInsuficiente):
        libro.consumir("ana", 6)


def test_un_consumo_rechazado_no_altera_el_saldo(libro):
    """Fallar a medias sería peor que fallar: el saldo debe quedar intacto."""
    libro.otorgar(Otorgamiento(cliente="ana", creditos=5, evento_id="evt_1"))
    with pytest.raises(SaldoInsuficiente):
        libro.consumir("ana", 6)
    assert libro.saldo("ana") == 5


def test_un_cliente_sin_creditos_no_puede_consumir(libro):
    with pytest.raises(SaldoInsuficiente):
        libro.consumir("desconocido", 1)


@pytest.mark.parametrize("cantidad", [0, -1])
def test_rechaza_consumir_una_cantidad_no_positiva(libro, cantidad):
    with pytest.raises(ValueError, match="positivos"):
        libro.consumir("ana", cantidad)
