"""
Traduce texto embebido en imágenes usando dos modelos vía Ollama.

Se hace en dos pasos, con un modelo distinto en cada uno:
  1. OCR: un modelo de visión (`modelo_vision`) transcribe el texto visible,
     sin traducir.
  2. Traducción: el texto transcripto pasa por traducir_chunk() con el modelo
     de traducción, el mismo camino que traduce el cuerpo del documento.

Por qué dos modelos y no uno
----------------------------
translategemma es un fine-tune de traducción de texto: su rama de visión no
pasó por ese fine-tune ni por instruction-tuning, y no sirve para OCR. Medido
sobre una imagen sintética trivial (título + 3 etiquetas + fuente, negro sobre
blanco), translategemma:12b transcribió sólo 2 de 5 elementos; qwen2.5vl:7b,
los 5. Sobre imágenes densas reales el modo de falla es peor: en vez de leer la
imagen devuelve el prompt de OCR palabra por palabra, y el paso 2 lo traduce
obedientemente, produciendo captions que son las instrucciones en español.

De ahí las dos defensas de este módulo: usar un modelo de visión de verdad, y
filtrar el eco del prompt por si aparece igual (_filtrar_eco_prompt).

API pública:
  - traducir_imagen(bytes, modelo, modelo_vision, ...)  → str | None
    (None = sin texto / descartable)
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
    """Instrucciones de transcripción. Van como system, no junto a la imagen.

    Se mandan aparte del turno del usuario justamente para que el modelo no las
    confunda con contenido a transcribir. Corto a propósito: cuanto menos texto
    haya en el prompt, menos hay para que el modelo devuelva como eco.
    """
    return (
        "Transcribe the text visible in this image, exactly as written, "
        "one line per distinct text element. "
        "Do not translate, explain or comment. "
        "If there is no readable text, respond with nothing."
    )


PROMPT_USUARIO_OCR = "Transcribe the text in this image."


def _llamar_vision(imagen_bytes: bytes, modelo: str, prompt: str) -> str:
    """Una llamada a Ollama-vision. Devuelve el texto crudo del modelo."""
    response = ollama_chat_timeout(
        model=modelo,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": PROMPT_USUARIO_OCR,
             "images": [imagen_bytes]},
        ],
        options={"temperature": 0.1, "num_predict": 1024},
    )
    return response["message"]["content"].strip()


def _normalizar(texto: str) -> str:
    """Minúsculas, sin puntuación y con espacios colapsados, para comparar."""
    return re.sub(r"[^a-z0-9áéíóúñü ]", "", texto.lower()).strip()


def _frases_prompt() -> list[str]:
    """Las frases del prompt de OCR, normalizadas, para detectar el eco."""
    crudo = _construir_prompt_ocr() + " " + PROMPT_USUARIO_OCR
    frases = [_normalizar(f) for f in re.split(r"[.\n]", crudo)]
    return [f for f in frases if len(f) >= 15]


def _ngramas(texto_normalizado: str, n: int = 5) -> set[str]:
    """Todos los n-gramas de palabras de un texto ya normalizado."""
    palabras = texto_normalizado.split()
    return {" ".join(palabras[i:i + n]) for i in range(len(palabras) - n + 1)}


def _es_eco_del_prompt(linea: str) -> bool:
    """True si la línea es el prompt de OCR devuelto como si fuera contenido.

    El modelo de visión, cuando no puede leer la imagen, a veces repite las
    instrucciones en vez de transcribir. Comparamos por n-gramas de 5 palabras
    y no por igualdad, porque el eco casi nunca vuelve limpio: llega cortado a
    mitad de frase por num_predict, o con una etiqueta inventada delante
    ("Text: One line per distinct text element"), y en los dos casos deja de
    ser subcadena del prompt.

    Cinco palabras seguidas es un umbral seguro: ninguna etiqueta real de un
    gráfico coincide en cinco palabras consecutivas con una instrucción.
    Las colas muy cortas ("If the") se atrapan aparte, por prefijo.
    """
    n = _normalizar(linea)
    if not n:
        return False
    n_prompt = _normalizar(_construir_prompt_ocr() + " " + PROMPT_USUARIO_OCR)
    if _ngramas(n) & _ngramas(n_prompt):
        return True
    if len(n) >= 12 and n in n_prompt:
        return True
    # Umbral 6: corto para atrapar colas truncadas como "if the", largo para no
    # tocar etiquetas legítimas de un gráfico ("US", "Asia", "2024").
    if len(n) >= 6 and any(f.startswith(n) for f in _frases_prompt()):
        return True
    return False


def _filtrar_eco_prompt(texto: str) -> str:
    """Saca de la transcripción las líneas que son eco del prompt."""
    return "\n".join(l for l in texto.splitlines() if not _es_eco_del_prompt(l))


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


def traducir_imagen(imagen_bytes: bytes, modelo: str, modelo_vision: str,
                    idioma_origen: str = "en",
                    idioma_destino: str = "es",
                    nombre_origen: str = "English",
                    nombre_destino: str = "Spanish",
                    cache: dict[str, str | None] | None = None,
                    ) -> str | None:
    """Traduce el texto embebido en una imagen: primero OCR, después traducción.

    `modelo_vision` hace el OCR; `modelo` traduce el resultado. Son distintos a
    propósito (ver el docstring del módulo).

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

    crudo = _llamar_vision(imagen_bytes, modelo_vision, _construir_prompt_ocr())

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

    # Primero el eco del prompt: hay que sacarlo ANTES de deduplicar, porque las
    # copias truncadas no son idénticas entre sí y _limpiar_resultado() no las ve
    # como duplicados. Después deduplicamos, que es donde el modelo repite
    # (mismo título una vez por panel del gráfico, por ejemplo).
    transcripcion = _limpiar_resultado(_filtrar_eco_prompt(crudo))
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


