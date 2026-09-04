"""Pruebas del flujo completo: pregunta → recuperación → respuesta."""

from pathlib import Path

import pytest

from conftest import ModeloQueExplota
from rag_demo.pipeline import (
    SIN_CONTEXTO,
    BaseDeConocimiento,
    armar_prompt,
    responder,
)

CORPUS = Path(__file__).resolve().parent.parent / "corpus"


@pytest.fixture
def base(embedder) -> BaseDeConocimiento:
    b = BaseDeConocimiento(embedder)
    b.cargar_carpeta(CORPUS)
    return b


def test_carga_el_corpus_del_repositorio(base):
    assert len(base) > 0


def test_recupera_el_documento_correcto(base):
    coincidencias = base.recuperar("clave del catalogo para carta porte")
    assert coincidencias
    assert coincidencias[0].fragmento.documento == "carta-porte"


def test_una_pregunta_de_otro_tema_recupera_el_otro_documento(base):
    coincidencias = base.recuperar("vigencia del expediente del proveedor")
    assert coincidencias
    assert coincidencias[0].fragmento.documento == "expedientes"


def test_una_pregunta_sin_relacion_no_recupera_nada(base):
    assert base.recuperar("receta de pizza siciliana") == []


def test_una_pregunta_vacia_no_recupera_nada(base):
    assert base.recuperar("   ") == []


def test_se_abstiene_cuando_no_hay_contexto(base):
    """La regla central: sin contexto no se responde."""
    respuesta = responder("receta de pizza siciliana", base, ModeloQueExplota())
    assert respuesta.texto == SIN_CONTEXTO
    assert respuesta.abstuvo


def test_no_invoca_al_modelo_cuando_se_abstiene(base):
    """Además de correcto, ahorra la llamada más cara del flujo."""
    # ModeloQueExplota falla si se le llama; que la prueba pase es la afirmación.
    responder("tema totalmente ajeno al corpus", base, ModeloQueExplota())


def test_responde_y_reporta_sus_fuentes(base, modelo):
    respuesta = responder("clave del catalogo para carta porte", base, modelo)
    assert respuesta.texto == "respuesta generada"
    assert respuesta.fuentes
    assert not respuesta.abstuvo


def test_el_prompt_lleva_el_contexto_recuperado(base, modelo):
    responder("vigencia del expediente del proveedor", base, modelo)
    enviado = modelo.prompts[0]
    assert "vigencia" in enviado.lower()
    assert "Contexto:" in enviado


def test_el_prompt_instruye_no_inventar(base, modelo):
    responder("clave del catalogo", base, modelo)
    enviado = modelo.prompts[0]
    assert "únicamente el contexto" in enviado
    assert SIN_CONTEXTO in enviado


def test_el_prompt_incluye_identificadores_citables(base, modelo):
    responder("clave del catalogo", base, modelo)
    assert "[carta-porte#" in modelo.prompts[0]


def test_k_limita_cuantos_fragmentos_entran(base, modelo):
    respuesta = responder("expediente proveedor vigencia rfc", base, modelo, k=1)
    assert len(respuesta.fuentes) <= 1


def test_armar_prompt_sin_coincidencias_deja_el_contexto_vacio():
    prompt = armar_prompt("pregunta", [])
    assert "Contexto:\n\n" in prompt


def test_agregar_un_documento_vacio_no_altera_la_base(embedder):
    b = BaseDeConocimiento(embedder)
    assert b.agregar_documento("", "vacio") == []
    assert len(b) == 0


# ── Regresión: abstención del modelo pese a superar el umbral ────────────────

class ModeloQueSeAbstiene:
    """Devuelve el texto de abstención aunque se le haya dado contexto.

    Reproduce lo que ocurre con datos reales: un fragmento puede superar el
    umbral de similitud y aun así no contener la respuesta. El modelo lo nota y
    se niega; el sistema debe tratarlo como abstención, no como respuesta.
    """

    def complete(self, prompt: str) -> str:
        return SIN_CONTEXTO


def test_si_el_modelo_se_abstiene_no_se_reportan_fuentes(base):
    """Devolverlas presentaria como respaldo unos fragmentos que no respaldan
    nada, y la interfaz lo pintaria como si hubiera respondido."""
    respuesta = responder(
        "clave del catalogo para carta porte", base, ModeloQueSeAbstiene()
    )

    assert respuesta.texto == SIN_CONTEXTO
    assert respuesta.fuentes == []
    assert respuesta.abstuvo


def test_una_abstencion_del_modelo_se_normaliza_al_mensaje_estandar(base):
    """Aunque el modelo agregue texto alrededor, el resultado es el mensaje
    unico: la interfaz no deberia tener que interpretar variantes."""

    class ConRuido:
        def complete(self, prompt: str) -> str:
            return f"  {SIN_CONTEXTO}  \n"

    assert responder("carta porte", base, ConRuido()).texto == SIN_CONTEXTO
