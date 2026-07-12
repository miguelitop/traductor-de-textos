"""Tests para las funciones de translator.py."""

from traductor.translator import _detectar_anomalias


def test_detectar_anomalias_normal():
    """Texto normal sin anomalías: devuelve lista vacía."""
    resultado = _detectar_anomalias("Hello world", "Hola mundo")
    assert resultado == []


def test_detectar_anomalias_puntos_suspensivos_espurios():
    """Puntos suspensivos en la traducción pero no en el original: detecta."""
    resultado = _detectar_anomalias("Hello", "Hola...")
    assert resultado == ["puntos suspensivos no presentes en el original"]


def test_detectar_anomalias_puntos_en_ambos():
    """Puntos suspensivos en original y traducción: no detecta."""
    resultado = _detectar_anomalias("Hello...", "Hola...")
    assert resultado == []


def test_detectar_anomalias_puntos_con_ellipsis_unicode():
    """Puntos suspensivos unicode (…) en original: no detecta."""
    resultado = _detectar_anomalias("Hello…", "Hola...")
    assert resultado == []


def test_detectar_anomalias_listas_no_solicitadas():
    """Bullet points en traducción sin estar en original: detecta."""
    original = "Normal text"
    traduccion = "* First item\n* Second item"
    resultado = _detectar_anomalias(original, traduccion)
    assert resultado == ["listas/explicaciones no presentes en el original"]


def test_detectar_anomalias_sin_falso_positivo_listas():
    """Bullet points en ambos (original y traducción): no detecta."""
    original = "* First item\n* Second item"
    traduccion = "* Primer elemento\n* Segundo elemento"
    resultado = _detectar_anomalias(original, traduccion)
    assert resultado == []


def test_detectar_anomalias_meta_comentario():
    """Meta-comentario del modelo 'no puedo traducir': detecta."""
    resultado = _detectar_anomalias("Hello", "Lo siento, no puedo traducir esto")
    assert resultado == ["posible meta-comentario del modelo"]


def test_detectar_anomalias_meta_comentario_ingles():
    """Meta-comentario en inglés 'I cannot translate': detecta."""
    resultado = _detectar_anomalias("Hola", "I cannot translate this text")
    assert resultado == ["posible meta-comentario del modelo"]
