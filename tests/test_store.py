"""Pruebas del índice vectorial."""

import numpy as np
import pytest

from rag_demo.chunking import Fragmento
from rag_demo.store import SIMILITUD_MINIMA, IndiceVectorial


def frag(texto: str, i: int = 0) -> Fragmento:
    return Fragmento(texto=texto, documento="doc", indice=i)


def test_un_indice_vacio_no_devuelve_nada():
    assert IndiceVectorial().buscar([1.0, 0.0]) == []


def test_recupera_el_fragmento_mas_parecido_primero():
    indice = IndiceVectorial()
    indice.agregar(
        [frag("a", 0), frag("b", 1)],
        [[1.0, 0.0], [0.0, 1.0]],
    )
    resultado = indice.buscar([0.9, 0.1], k=2)
    assert resultado[0].fragmento.texto == "a"


def test_descarta_lo_que_no_llega_al_umbral():
    """Un fragmento irrelevante no debe colarse solo por ser lo mejor que hay."""
    indice = IndiceVectorial()
    indice.agregar([frag("sin relacion")], [[0.0, 1.0]])
    assert indice.buscar([1.0, 0.0], k=4) == []


def test_devuelve_menos_de_k_en_lugar_de_rellenar():
    indice = IndiceVectorial()
    indice.agregar(
        [frag("a", 0), frag("b", 1)],
        [[1.0, 0.0], [0.0, 1.0]],
    )
    resultado = indice.buscar([1.0, 0.0], k=4)
    assert len(resultado) == 1


def test_la_similitud_reportada_es_el_coseno():
    indice = IndiceVectorial()
    indice.agregar([frag("a")], [[1.0, 0.0]])
    resultado = indice.buscar([1.0, 0.0], k=1)
    assert resultado[0].similitud == pytest.approx(1.0)


def test_la_magnitud_del_vector_no_altera_el_orden():
    """El coseno mide dirección; un vector diez veces más largo no gana por eso."""
    indice = IndiceVectorial()
    indice.agregar(
        [frag("corto", 0), frag("largo", 1)],
        [[1.0, 0.0], [0.0, 10.0]],
    )
    resultado = indice.buscar([1.0, 0.0], k=2)
    assert resultado[0].fragmento.texto == "corto"


def test_un_vector_de_ceros_no_rompe_la_division():
    indice = IndiceVectorial()
    indice.agregar([frag("vacio")], [[0.0, 0.0]])
    assert indice.buscar([1.0, 0.0], k=1) == []


def test_rechaza_mezclar_dimensiones_distintas():
    indice = IndiceVectorial()
    indice.agregar([frag("a")], [[1.0, 0.0]])
    with pytest.raises(ValueError, match="incompatible"):
        indice.agregar([frag("b", 1)], [[1.0, 0.0, 0.0]])


def test_rechaza_una_consulta_con_otra_dimension():
    indice = IndiceVectorial()
    indice.agregar([frag("a")], [[1.0, 0.0]])
    with pytest.raises(ValueError, match="dimensión"):
        indice.buscar([1.0, 0.0, 0.0])


def test_rechaza_vectores_con_nan():
    indice = IndiceVectorial()
    with pytest.raises(ValueError, match="NaN"):
        indice.agregar([frag("a")], [[float("nan"), 0.0]])


def test_rechaza_un_numero_de_vectores_distinto_al_de_fragmentos():
    indice = IndiceVectorial()
    with pytest.raises(ValueError, match="exactamente un vector"):
        indice.agregar([frag("a"), frag("b", 1)], [[1.0, 0.0]])


def test_agregar_en_dos_tandas_conserva_lo_anterior():
    indice = IndiceVectorial()
    indice.agregar([frag("a", 0)], [[1.0, 0.0]])
    indice.agregar([frag("b", 1)], [[0.9, 0.1]])
    assert len(indice) == 2
    assert len(indice.buscar([1.0, 0.0], k=2)) == 2


def test_k_en_cero_no_devuelve_nada():
    indice = IndiceVectorial()
    indice.agregar([frag("a")], [[1.0, 0.0]])
    assert indice.buscar([1.0, 0.0], k=0) == []
