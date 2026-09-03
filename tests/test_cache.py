"""Pruebas de la caché de vectores."""

import pytest

from conftest import EmbedderDeterminista
from rag_demo.cache import CacheEnMemoria, EmbedderConCache, clave_de


class EmbedderQueCuenta(EmbedderDeterminista):
    """Cuenta cuántos textos llegaron realmente al modelo."""

    def __init__(self) -> None:
        self.textos_pedidos: list[str] = []

    def embed(self, texts):
        self.textos_pedidos.extend(texts)
        return super().embed(texts)


@pytest.fixture
def modelo_contado() -> EmbedderQueCuenta:
    return EmbedderQueCuenta()


@pytest.fixture
def cache() -> CacheEnMemoria:
    return CacheEnMemoria()


def test_la_clave_cambia_con_el_modelo():
    """Dos modelos producen vectores incomparables para el mismo texto."""
    assert clave_de("bge-m3", "hola") != clave_de("otro-modelo", "hola")


def test_la_clave_es_estable_para_el_mismo_par():
    assert clave_de("bge-m3", "hola") == clave_de("bge-m3", "hola")


def test_la_clave_no_expone_el_texto():
    """Quien liste las claves de Redis no debe poder leer los documentos."""
    assert "secreto" not in clave_de("bge-m3", "documento secreto")


def test_la_primera_llamada_va_al_modelo(modelo_contado, cache):
    con_cache = EmbedderConCache(modelo_contado, cache, "bge-m3")
    con_cache.embed(["carta porte"])
    assert modelo_contado.textos_pedidos == ["carta porte"]


def test_la_segunda_llamada_no_va_al_modelo(modelo_contado, cache):
    con_cache = EmbedderConCache(modelo_contado, cache, "bge-m3")
    con_cache.embed(["carta porte"])
    con_cache.embed(["carta porte"])
    assert modelo_contado.textos_pedidos == ["carta porte"]


def test_el_vector_cacheado_es_igual_al_original(modelo_contado, cache):
    con_cache = EmbedderConCache(modelo_contado, cache, "bge-m3")
    primero = con_cache.embed(["expediente"])
    segundo = con_cache.embed(["expediente"])
    assert primero == segundo


def test_solo_pide_los_textos_que_faltan(modelo_contado, cache):
    con_cache = EmbedderConCache(modelo_contado, cache, "bge-m3")
    con_cache.embed(["uno"])
    modelo_contado.textos_pedidos.clear()

    con_cache.embed(["uno", "dos"])
    assert modelo_contado.textos_pedidos == ["dos"]


def test_un_texto_repetido_en_la_misma_llamada_se_pide_una_vez(modelo_contado, cache):
    con_cache = EmbedderConCache(modelo_contado, cache, "bge-m3")
    con_cache.embed(["igual", "igual", "igual"])
    assert modelo_contado.textos_pedidos == ["igual"]


def test_conserva_el_orden_recibido(modelo_contado, cache):
    con_cache = EmbedderConCache(modelo_contado, cache, "bge-m3")
    con_cache.embed(["b"])           # queda cacheado
    modelo_contado.textos_pedidos.clear()

    esperado = EmbedderDeterminista().embed(["a", "b", "c"])
    assert con_cache.embed(["a", "b", "c"]) == esperado


def test_devuelve_un_vector_por_cada_texto(modelo_contado, cache):
    con_cache = EmbedderConCache(modelo_contado, cache, "bge-m3")
    assert len(con_cache.embed(["a", "b", "c"])) == 3


def test_una_lista_vacia_no_toca_el_modelo(modelo_contado, cache):
    con_cache = EmbedderConCache(modelo_contado, cache, "bge-m3")
    assert con_cache.embed([]) == []
    assert modelo_contado.textos_pedidos == []


def test_cambiar_de_modelo_invalida_lo_cacheado(modelo_contado, cache):
    """Tras cambiar de modelo no se deben servir vectores del anterior."""
    EmbedderConCache(modelo_contado, cache, "modelo-viejo").embed(["texto"])
    modelo_contado.textos_pedidos.clear()

    EmbedderConCache(modelo_contado, cache, "modelo-nuevo").embed(["texto"])
    assert modelo_contado.textos_pedidos == ["texto"]


def test_expone_las_dimensiones_del_envuelto(modelo_contado, cache):
    con_cache = EmbedderConCache(modelo_contado, cache, "bge-m3")
    assert con_cache.dimensions == modelo_contado.dimensions


class EmbedderQueDevuelveNone(EmbedderDeterminista):
    """Simula un proveedor defectuoso que entrega un hueco en la lista."""

    def embed(self, texts):
        vectores = super().embed(texts)
        if vectores:
            vectores[0] = None  # type: ignore[assignment]
        return vectores


def test_falla_fuerte_si_algun_texto_queda_sin_vector(cache):
    """Un hueco debe reventar aquí, no más adelante y lejos de su causa."""
    con_cache = EmbedderConCache(EmbedderQueDevuelveNone(), cache, "bge-m3")

    with pytest.raises(RuntimeError, match="sin vector"):
        con_cache.embed(["uno", "dos"])
