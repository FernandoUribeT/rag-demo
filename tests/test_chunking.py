"""Pruebas del troceado."""

from rag_demo.chunking import TAMANO_OBJETIVO, trocear


def test_un_documento_vacio_no_produce_fragmentos():
    assert trocear("", "doc") == []
    assert trocear("   \n\n  ", "doc") == []


def test_un_parrafo_corto_queda_en_un_solo_fragmento():
    fragmentos = trocear("Una sola idea corta pero suficiente.", "doc")
    assert len(fragmentos) == 1
    assert fragmentos[0].texto == "Una sola idea corta pero suficiente."


def test_cada_fragmento_conserva_su_origen():
    fragmentos = trocear("Primero.\n\nSegundo.", "carta-porte")
    assert all(f.documento == "carta-porte" for f in fragmentos)
    assert fragmentos[0].id == "carta-porte#0"


def test_un_documento_largo_se_parte_en_varios_fragmentos():
    parrafo = "palabra " * 60
    fragmentos = trocear("\n\n".join([parrafo] * 6), "doc")
    assert len(fragmentos) > 1


def test_ningun_fragmento_parte_un_parrafo_por_la_mitad():
    """El fragmento puede pasarse del objetivo, pero nunca corta una idea."""
    parrafos = ["Idea numero uno completa.", "Idea numero dos completa."]
    fragmentos = trocear("\n\n".join(parrafos), "doc")
    unido = " ".join(f.texto for f in fragmentos)
    for parrafo in parrafos:
        assert parrafo in unido


def test_un_fragmento_muy_corto_se_pega_al_anterior():
    """Un residuo suelto no responde nada; pertenece al fragmento previo."""
    largo = "contenido " * 80
    fragmentos = trocear(f"{largo}\n\nSi.", "doc")
    assert fragmentos[-1].texto.endswith("Si.")


def test_los_indices_son_consecutivos_desde_cero():
    parrafo = "palabra " * 60
    fragmentos = trocear("\n\n".join([parrafo] * 6), "doc")
    assert [f.indice for f in fragmentos] == list(range(len(fragmentos)))


def test_el_espacio_en_blanco_se_normaliza():
    fragmentos = trocear("Texto   con\n saltos    raros.", "doc")
    assert fragmentos[0].texto == "Texto con saltos raros."
