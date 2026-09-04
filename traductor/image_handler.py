"""
Traduce texto embebido en imágenes usando un modelo de visión vía Ollama.

Se hace en dos pasos, no en uno:
  1. Llamada de visión que sólo transcribe el texto visible, sin traducir.
  2. El texto transcripto pasa por traducir_chunk(), el mismo camino que traduce
     el cuerpo del documento.

Pedirle a la vez OCR y traducción hacía que el modelo transcribiera sin traducir
—translategemma es un fine-tune de traducción de texto, su rama de visión no pasó
por ese fine-tune— y los captions salían en el idioma de origen.

API pública:
  - traducir_imagen(bytes, ...)  → str | None    (None = sin texto / descartable)
"""
from __future__ import annotations

import hashlib
import io
import re
from collections import Counter

import ollama
from PIL import Image

from .utils import ollama_chat_timeout

DIM_MIN_IMAGEN = 100  # px mínimos por lado para considerar una imagen


def _hash_imagen(imagen_bytes: bytes) -> str:
    """Hash corto de los bytes para deduplicar imágenes repetidas."""
    return hashlib.sha256(imagen_bytes).hexdigest()[:16]


def _es_descartable(imagen_bytes: bytes) -> bool:
    """True si la imagen es muy chica o no se puede abrir como bitmap."""
    try:
        img = Image.open(io.BytesIO(imagen_bytes))
        w, h = img.size
    except Exception:
        return True
    return w < DIM_MIN_IMAGEN or h < DIM_MIN_IMAGEN


def _construir_prompt_ocr() -> str:
    """Prompt de transcripción. La traducción se hace después, en un paso aparte."""
    return (
        "Transcribe every piece of text visible in this image, exactly as written. "
        "Include titles, labels, axis names, legends, captions and footnotes. "
        "One line per distinct text element. Do not translate, explain or comment. "
        "If the image contains NO readable text, respond with an empty string."
    )


def _llamar_vision(imagen_bytes: bytes, modelo: str, prompt: str) -> str:
    """Una llamada a Ollama-vision. Devuelve el texto crudo del modelo."""
    response = ollama_chat_timeout(
        model=modelo,
        messages=[{"role": "user", "content": prompt, "images": [imagen_bytes]}],
        options={"temperature": 0.1, "num_predict": 1024},
    )
    return response["message"]["content"].strip()


def _es_repeticion_loop(texto: str) -> bool:
    """Detecta si la salida es una línea repetida muchísimas veces (alucinación)."""
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    if len(lineas) < 6:
        return False
    # Si la línea más común es >70% del total, es loop
    mas_comun, freq = Counter(lineas).most_common(1)[0]
    return freq / len(lineas) > 0.7


def _limpiar_resultado(texto: str) -> str:
    """Quita líneas duplicadas (consecutivas o no) y limpia espacios al borde.

    El modelo a veces transcribe el mismo título o etiqueta dos veces (una vez
    por panel del gráfico, por ejemplo). Mantenemos la primera ocurrencia de
    cada línea no-trivial y descartamos repeticiones posteriores.
    Las líneas muy cortas (≤2 chars) se preservan tal cual: pueden ser
    elementos de layout legítimos (años sueltos, números de eje).
    """
    lineas = [l.rstrip() for l in texto.splitlines()]
    salida = []
    vistas: set[str] = set()
    for l in lineas:
        clave = l.strip()
        if not clave:
            # Permitir líneas vacías para preservar separación visual
            if salida and salida[-1].strip():
                salida.append(l)
            continue
        if len(clave) <= 2:
            salida.append(l)
            continue
        if clave in vistas:
            continue
        vistas.add(clave)
        salida.append(l)
    # Eliminar líneas vacías al inicio y final
    while salida and not salida[0].strip():
        salida.pop(0)
    while salida and not salida[-1].strip():
        salida.pop()
    return "\n".join(salida)


def traducir_imagen(imagen_bytes: bytes, modelo: str,
                    idioma_origen: str = "en",
                    idioma_destino: str = "es",
                    nombre_origen: str = "English",
                    nombre_destino: str = "Spanish",
                    cache: dict[str, str | None] | None = None,
                    ) -> str | None:
    """Traduce el texto embebido en una imagen: primero OCR, después traducción.

    Devuelve:
      - str con la traducción (sin prefijo) si la imagen tiene texto
      - None si la imagen no tiene texto, es muy chica, o el modelo falla por loop

    Si se pasa `cache`, se memoriza el resultado por hash de bytes.
    """
    # Import diferido: translator importa este módulo, hacerlo arriba sería circular.
    from .translator import traducir_chunk

    if _es_descartable(imagen_bytes):
        return None

    h = _hash_imagen(imagen_bytes)
    if cache is not None and h in cache:
        return cache[h]

    crudo = _llamar_vision(imagen_bytes, modelo, _construir_prompt_ocr())

    # Resultado vacío → sin texto
    if not crudo.strip():
        if cache is not None:
            cache[h] = None
        return None

    # Detección de loop alucinado pese a las opciones anti-repetición
    if _es_repeticion_loop(crudo):
        if cache is not None:
            cache[h] = None
        return None

    # Deduplicamos sobre la transcripción, que es donde el modelo repite
    # (mismo título una vez por panel del gráfico, por ejemplo).
    transcripcion = _limpiar_resultado(crudo)
    if not transcripcion:
        if cache is not None:
            cache[h] = None
        return None

    resultado = traducir_chunk(
        transcripcion, modelo,
        idioma_origen, idioma_destino,
        nombre_origen, nombre_destino,
        texto_tabular=True,
    ).strip()

    # traducir_chunk no revisa repeticiones en modo tabular; lo hacemos acá con
    # el criterio que sí sirve para imágenes (línea entera repetida).
    if not resultado or _es_repeticion_loop(resultado):
        if cache is not None:
            cache[h] = None
        return None

    if cache is not None:
        cache[h] = resultado
    return resultado


