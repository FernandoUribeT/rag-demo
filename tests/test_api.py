"""Pruebas de la API HTTP."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ModeloQueRepiteElContexto, PasarelaFalsa
from rag_demo.api import Servicios, crear_app
from rag_demo.creditos import LibroEnMemoria, Otorgamiento
from rag_demo.pipeline import SIN_CONTEXTO, BaseDeConocimiento

CORPUS = Path(__file__).resolve().parent.parent / "corpus"


@pytest.fixture
def libro() -> LibroEnMemoria:
    libro = LibroEnMemoria()
    libro.otorgar(Otorgamiento(cliente="ana", creditos=5, evento_id="seed"))
    return libro


@pytest.fixture
def pasarela_api() -> PasarelaFalsa:
    return PasarelaFalsa()


@pytest.fixture
def cliente(embedder, libro, pasarela_api) -> TestClient:
    base = BaseDeConocimiento(embedder)
    base.cargar_carpeta(CORPUS)
    return TestClient(
        crear_app(
            Servicios(
                base=base,
                modelo=ModeloQueRepiteElContexto(),
                libro=libro,
                pasarela=pasarela_api,
            )
        )
    )


ANA = {"X-Cliente": "ana"}


def test_salud_reporta_cuantos_fragmentos_hay(cliente):
    cuerpo = cliente.get("/api/salud").json()
    assert cuerpo["estado"] == "ok"
    assert cuerpo["fragmentos"] > 0


def test_responde_una_pregunta_del_corpus(cliente):
    r = cliente.post("/api/preguntar", json={"pregunta": "clave del catalogo carta porte"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["abstuvo"] is False
    assert cuerpo["fuentes"]


def test_cada_fuente_trae_lo_necesario_para_mostrarla(cliente):
    cuerpo = cliente.post(
        "/api/preguntar", json={"pregunta": "vigencia del expediente proveedor"}
    ).json()
    fuente = cuerpo["fuentes"][0]
    assert set(fuente) == {"id", "documento", "similitud", "extracto"}
    assert 0.0 <= fuente["similitud"] <= 1.0


def test_se_abstiene_ante_una_pregunta_sin_relacion(cliente):
    cuerpo = cliente.post("/api/preguntar", json={"pregunta": "receta de pizza"}).json()
    assert cuerpo["abstuvo"] is True
    assert cuerpo["texto"] == SIN_CONTEXTO
    assert cuerpo["fuentes"] == []


def test_una_pregunta_vacia_se_rechaza(cliente):
    assert cliente.post("/api/preguntar", json={"pregunta": ""}).status_code == 422


def test_una_k_fuera_de_rango_se_rechaza(cliente):
    assert cliente.post(
        "/api/preguntar", json={"pregunta": "algo", "k": 999}
    ).status_code == 422


def test_el_extracto_va_acotado(cliente):
    """La interfaz muestra de dónde salió la respuesta, no el fragmento entero."""
    cuerpo = cliente.post("/api/preguntar", json={"pregunta": "carta porte clave"}).json()
    assert all(len(f["extracto"]) <= 240 for f in cuerpo["fuentes"])


def test_subir_un_documento_devuelve_202(cliente):
    """202 y no 200: fue aceptado, pero todavía no está indexado."""
    r = cliente.post(
        "/api/documentos",
        json={"nombre": "nuevo", "contenido": "Un texto sobre traslados."},
        headers=ANA,
    )
    assert r.status_code == 202
    assert r.json()["estado"] == "encolado"


def test_un_documento_sin_nombre_se_rechaza(cliente):
    assert cliente.post(
        "/api/documentos", json={"nombre": "", "contenido": "algo"}, headers=ANA
    ).status_code == 422


# ── Créditos ─────────────────────────────────────────────────────────────────

def test_subir_un_documento_cobra_un_credito(cliente, libro):
    antes = libro.saldo("ana")
    cliente.post(
        "/api/documentos", json={"nombre": "a", "contenido": "texto"}, headers=ANA
    )
    assert libro.saldo("ana") == antes - 1


def test_sin_saldo_responde_402(cliente):
    """402 Payment Required: la petición es válida, lo que falta es saldo."""
    r = cliente.post(
        "/api/documentos",
        json={"nombre": "a", "contenido": "texto"},
        headers={"X-Cliente": "sin-creditos"},
    )
    assert r.status_code == 402


def test_sin_saldo_no_se_encola_nada(cliente):
    """Cobrar después de encolar dejaría al worker indexando algo no pagado."""
    r = cliente.post(
        "/api/documentos",
        json={"nombre": "a", "contenido": "texto"},
        headers={"X-Cliente": "sin-creditos"},
    )
    assert r.status_code == 402
    # La cola quedó intacta: el 402 ocurrió antes de aceptar el documento.
    assert cliente.get("/api/saldo", headers={"X-Cliente": "sin-creditos"}).json()[
        "creditos"
    ] == 0


def test_consulta_el_saldo(cliente):
    assert cliente.get("/api/saldo", headers=ANA).json()["creditos"] == 5


# ── Pagos ────────────────────────────────────────────────────────────────────

def test_crear_checkout_devuelve_una_url(cliente):
    r = cliente.post("/api/checkout", json={"paquete": "creditos_50"}, headers=ANA)
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://")


def test_un_paquete_inventado_se_rechaza(cliente):
    r = cliente.post("/api/checkout", json={"paquete": "gratis"}, headers=ANA)
    assert r.status_code == 422


def test_el_webhook_con_firma_invalida_se_rechaza(cliente):
    """El endpoint es público: la firma es lo único que separa a Stripe de
    cualquiera que mande un POST diciendo que un cliente pagó."""
    r = cliente.post(
        "/api/webhooks/stripe",
        content=b'{"type":"checkout.session.completed"}',
        headers={"Stripe-Signature": "falsa"},
    )
    assert r.status_code == 400


def test_el_webhook_de_un_pago_otorga_creditos(cliente, libro, pasarela_api):
    cuerpo, firma = pasarela_api.firmar(
        {
            "id": "evt_100",
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
    r = cliente.post(
        "/api/webhooks/stripe", content=cuerpo, headers={"Stripe-Signature": firma}
    )
    assert r.json()["estado"] == "otorgado"
    assert libro.saldo("ana") == 55


def test_el_reintento_del_webhook_no_duplica_creditos(cliente, libro, pasarela_api):
    """Stripe reenvía hasta recibir 2xx; el segundo envío debe ser inofensivo."""
    cuerpo, firma = pasarela_api.firmar(
        {
            "id": "evt_101",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "payment_status": "paid",
                    "client_reference_id": "ana",
                    "metadata": {"creditos": "10"},
                }
            },
        }
    )
    cabeceras = {"Stripe-Signature": firma}
    cliente.post("/api/webhooks/stripe", content=cuerpo, headers=cabeceras)
    r = cliente.post("/api/webhooks/stripe", content=cuerpo, headers=cabeceras)

    assert r.json()["estado"] == "duplicado"
    assert libro.saldo("ana") == 15


def test_un_evento_que_no_aplica_responde_200(cliente, pasarela_api):
    """200 y no error: si respondiéramos 4xx, Stripe reintentaría para siempre
    un evento que nunca vamos a procesar."""
    cuerpo, firma = pasarela_api.firmar(
        {"id": "evt_x", "type": "customer.created", "data": {"object": {}}}
    )
    r = cliente.post(
        "/api/webhooks/stripe", content=cuerpo, headers={"Stripe-Signature": firma}
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "ignorado"
