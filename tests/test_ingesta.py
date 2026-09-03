"""Pruebas del flujo de ingesta: guardar, encolar, indexar."""

import pytest

from rag_demo.ingesta import (
    ColaEnMemoria,
    TrabajoDeIndexado,
    aceptar,
    drenar,
    procesar,
)
from rag_demo.pipeline import BaseDeConocimiento
from rag_demo.storage import AlmacenEnMemoria, clave_de_documento

DOC = "Un párrafo sobre expedientes de proveedores y su vigencia.".encode("utf-8")


@pytest.fixture
def almacen() -> AlmacenEnMemoria:
    return AlmacenEnMemoria()


@pytest.fixture
def cola() -> ColaEnMemoria:
    return ColaEnMemoria()


@pytest.fixture
def base(embedder) -> BaseDeConocimiento:
    return BaseDeConocimiento(embedder)


# ── Claves de documento ──────────────────────────────────────────────────────

def test_el_mismo_contenido_produce_la_misma_clave():
    assert clave_de_documento("doc", b"igual") == clave_de_documento("doc", b"igual")


def test_contenido_distinto_no_pisa_al_anterior():
    """Subir una version corregida con el mismo nombre no borra la previa."""
    assert clave_de_documento("doc", b"v1") != clave_de_documento("doc", b"v2")


# ── Aceptar ──────────────────────────────────────────────────────────────────

def test_aceptar_guarda_el_documento(almacen, cola):
    trabajo = aceptar(DOC, "expedientes", almacen=almacen, cola=cola)
    assert almacen.existe(trabajo.clave)
    assert almacen.leer(trabajo.clave) == DOC


def test_aceptar_encola_un_trabajo(almacen, cola):
    aceptar(DOC, "expedientes", almacen=almacen, cola=cola)
    assert len(cola) == 1


def test_aceptar_no_indexa_todavia(almacen, cola, base):
    """La carga responde rápido: vectorizar es trabajo del worker."""
    aceptar(DOC, "expedientes", almacen=almacen, cola=cola)
    assert len(base) == 0


def test_aceptar_rechaza_un_nombre_vacio(almacen, cola):
    with pytest.raises(ValueError, match="nombre"):
        aceptar(DOC, "   ", almacen=almacen, cola=cola)


def test_el_mensaje_lleva_la_referencia_y_no_el_documento(almacen, cola):
    """Un documento dentro de la cola la convierte en un almacén improvisado."""
    aceptar(DOC, "expedientes", almacen=almacen, cola=cola)
    assert b"proveedores" not in cola.consumir()


# ── Serializacion del mensaje ────────────────────────────────────────────────

def test_el_trabajo_sobrevive_el_viaje_por_la_cola():
    original = TrabajoDeIndexado(clave="doc/abc123", nombre="doc")
    assert TrabajoDeIndexado.deserializar(original.serializar()) == original


@pytest.mark.parametrize(
    "crudo",
    [
        b'{"clave": "solo-clave"}',
        b'{"nombre": "solo-nombre"}',
        b'{"clave": "", "nombre": "doc"}',
        b'{"clave": 1, "nombre": "doc"}',
        b'["no", "es", "objeto"]',
    ],
)
def test_un_mensaje_malformado_se_rechaza(crudo):
    with pytest.raises(ValueError):
        TrabajoDeIndexado.deserializar(crudo)


# ── Procesar ─────────────────────────────────────────────────────────────────

def test_procesar_indexa_el_documento(almacen, cola, base):
    trabajo = aceptar(DOC, "expedientes", almacen=almacen, cola=cola)
    assert procesar(trabajo, almacen=almacen, base=base) > 0
    assert len(base) > 0


def test_lo_indexado_se_puede_recuperar(almacen, cola, base):
    trabajo = aceptar(DOC, "expedientes", almacen=almacen, cola=cola)
    procesar(trabajo, almacen=almacen, base=base)
    assert base.recuperar("vigencia del expediente")


def test_procesar_un_documento_ausente_falla_claro(almacen, base):
    with pytest.raises(KeyError):
        procesar(
            TrabajoDeIndexado(clave="no/existe", nombre="x"),
            almacen=almacen,
            base=base,
        )


# ── Drenar ───────────────────────────────────────────────────────────────────

def test_drenar_procesa_todo_lo_pendiente(almacen, cola, base):
    aceptar(b"Primero sobre carta porte.", "uno", almacen=almacen, cola=cola)
    aceptar(b"Segundo sobre expedientes.", "dos", almacen=almacen, cola=cola)
    assert drenar(cola=cola, almacen=almacen, base=base) == 2
    assert len(cola) == 0


def test_drenar_una_cola_vacia_no_hace_nada(almacen, cola, base):
    assert drenar(cola=cola, almacen=almacen, base=base) == 0


def test_drenar_respeta_su_tope(almacen, cola, base):
    """Un worker no debe quedarse atrapado si publican más rápido de lo que consume."""
    for i in range(5):
        aceptar(f"Documento numero {i} sobre carta porte.".encode(), f"d{i}",
                almacen=almacen, cola=cola)
    assert drenar(cola=cola, almacen=almacen, base=base, maximo=2) == 2
    assert len(cola) == 3
