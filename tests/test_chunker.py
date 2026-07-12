"""Tests para las funciones de chunker.py."""

from traductor.chunker import separar_grupo, agrupar_nodos


# ─── separar_grupo ──────────────────────────────────────────────────────────────


def test_separar_grupo_feliz():
    """Caso feliz: cantidad exacta de partes."""
    resultado = separar_grupo("a |||| b |||| c", 3)
    assert resultado == ["a", "b", "c"]


def test_separar_grupo_menos_partes():
    """Menos partes de las esperadas: rellena con la última."""
    resultado = separar_grupo("a |||| b", 3)
    assert resultado == ["a", "b", "b"]


def test_separar_grupo_mas_partes():
    """Más partes de las esperadas: trunca."""
    resultado = separar_grupo("a |||| b |||| c |||| d", 2)
    assert resultado == ["a", "b"]


def test_separar_grupo_vacio():
    """Texto vacío: devuelve lista con string vacío."""
    resultado = separar_grupo("", 1)
    assert resultado == [""]


def test_separar_grupo_whitespace():
    """Whitespace alrededor de los separadores se elimina."""
    resultado = separar_grupo("  foo  ||||  bar  ||||  baz  ", 3)
    assert resultado == ["foo", "bar", "baz"]


# ─── agrupar_nodos ──────────────────────────────────────────────────────────────


def test_agrupar_nodos_textos_cortos():
    """Varios textos cortos que caben en un solo grupo."""
    textos = ["hola", "mundo", "foo"]
    resultado = agrupar_nodos(textos, 10)
    assert resultado == [[0, 1, 2]]


def test_agrupar_nodos_exceden_maximo():
    """Textos que exceden max_palabras se agrupan por separado."""
    textos = ["una frase larga de varias palabras", "corta", "otra frase larga aqui"]
    resultado = agrupar_nodos(textos, 3)
    # "una frase larga de varias palabras" = 6 palabras → grupo [0]
    # "corta" = 1 palabra → grupo [1] (6 + 1 > 3)
    # "otra frase larga aqui" = 4 palabras → grupo [2] (1 + 4 > 3)
    assert resultado == [[0], [1], [2]]


def test_agrupar_nodos_vacio():
    """Lista vacía: devuelve lista vacía."""
    resultado = agrupar_nodos([], 10)
    assert resultado == []
