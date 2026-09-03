"""Pruebas de la API HTTP."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ModeloQueRepiteElContexto
from rag_demo.api import Servicios, crear_app
from rag_demo.pipeline import SIN_CONTEXTO, BaseDeConocimiento

CORPUS = Path(__file__).resolve().parent.parent / "corpus"


@pytest.fixture
def cliente(embedder) -> TestClient:
    base = BaseDeConocimiento(embedder)
    base.cargar_carpeta(CORPUS)
    return TestClient(crear_app(Servicios(base=base, modelo=ModeloQueRepiteElContexto())))


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
    )
    assert r.status_code == 202
    assert r.json()["estado"] == "encolado"


def test_un_documento_sin_nombre_se_rechaza(cliente):
    assert cliente.post(
        "/api/documentos", json={"nombre": "", "contenido": "algo"}
    ).status_code == 422
