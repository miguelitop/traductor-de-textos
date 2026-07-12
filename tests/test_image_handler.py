"""Tests para las funciones de image_handler.py."""

import io

from PIL import Image

from traductor.image_handler import (
    _construir_prompt,
    _es_descartable,
    _limpiar_resultado,
)


# ---------------------------------------------------------------------------
# Helper para generar imágenes PNG en memoria
# ---------------------------------------------------------------------------

def _crear_imagen_png(ancho: int, alto: int) -> bytes:
    """Crea una imagen PNG en memoria del tamaño dado."""
    img = Image.new("RGB", (ancho, alto), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# _es_descartable
# ---------------------------------------------------------------------------

def test_es_descartable_diminuta():
    """Imagen de 50x50 (< 100px) debe ser descartable."""
    assert _es_descartable(_crear_imagen_png(50, 50)) is True


def test_es_descartable_normal():
    """Imagen de 200x200 debe ser válida."""
    assert _es_descartable(_crear_imagen_png(200, 200)) is False


def test_es_descartable_bytes_invalidos():
    """Bytes que no son una imagen deben ser descartables."""
    assert _es_descartable(b"esto no es una imagen") is True


# ---------------------------------------------------------------------------
# _limpiar_resultado
# ---------------------------------------------------------------------------

def test_limpiar_resultado_sin_duplicados():
    """Sin líneas duplicadas: se preservan todas en el mismo orden."""
    resultado = _limpiar_resultado("linea1\nlinea2\nlinea3")
    assert resultado == "linea1\nlinea2\nlinea3"


def test_limpiar_resultado_con_duplicados():
    """Líneas duplicadas: solo se conserva la primera ocurrencia."""
    resultado = _limpiar_resultado("hola\nmundo\nhola")
    assert resultado == "hola\nmundo"


def test_limpiar_resultado_lineas_cortas():
    """Líneas de ≤2 chars se preservan aunque estén duplicadas."""
    resultado = _limpiar_resultado("a\nxy\nlargo")
    assert resultado == "a\nxy\nlargo"


def test_limpiar_resultado_vacio():
    """Cadena vacía devuelve cadena vacía."""
    resultado = _limpiar_resultado("")
    assert resultado == ""


# ---------------------------------------------------------------------------
# _construir_prompt
# ---------------------------------------------------------------------------

def test_construir_prompt_contiene_idiomas():
    """El prompt debe contener los nombres de idioma pasados."""
    prompt = _construir_prompt("English", "Spanish")
    assert "English" in prompt
    assert "Spanish" in prompt


def test_construir_prompt_sin_sentinel():
    """El prompt no debe contener el sentinel [NO_TEXT]."""
    prompt = _construir_prompt("English", "Spanish")
    assert "[NO_TEXT]" not in prompt
