import hashlib
import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import ollama
import concurrent.futures
from tqdm import tqdm

from .config import REINTENTOS_MAX
from .image_handler import traducir_imagen
from .utils import ollama_chat_timeout


def traducir_chunk(texto: str, modelo: str,
                   idioma_origen: str = "en", idioma_destino: str = "es",
                   nombre_origen: str = "English", nombre_destino: str = "Spanish") -> str:
    """Envía un chunk a Ollama y devuelve la traducción."""
    instruccion_links = ""
    if "\u27e6" in texto:
        instruccion_links = (
            "IMPORTANT: The text contains placeholder tokens like \u27e61\u27e7, \u27e62\u27e7, \u27e63\u27e7. "
            "Each token stands for a hyperlink or footnote. You MUST keep every token EXACTLY "
            "as-is (same brackets and number), in the same position relative to the surrounding words. "
            "Never translate, alter, space out, reorder, split, merge, or remove any token. "
        )
    instruccion_separador = ""
    if "||||" in texto:
        instruccion_separador = (
            "IMPORTANT: The text contains segment separators '||||'. "
            "You MUST preserve each '||||' separator exactly as-is in your translation. "
            "Translate each segment independently but keep the separators in place. "
        )
    prompt = (
        f"You are a professional {nombre_origen} ({idioma_origen}) to {nombre_destino} ({idioma_destino}) translator. "
        f"Your goal is to accurately convey the meaning and nuances of the original "
        f"{nombre_origen} text while adhering to {nombre_destino} grammar, vocabulary, and cultural sensitivities. "
        f"Produce only the {nombre_destino} translation, without any additional explanations or commentary. "
        f"{instruccion_links}"
        f"{instruccion_separador}"
        f"Please translate the following {nombre_origen} text into {nombre_destino}:\n\n\n"
        f"{texto}"
    )
    # Limitar tokens de salida al doble del input para cortar alucinaciones repetitivas
    palabras_entrada = len(texto.split())
    max_tokens = max(256, int(palabras_entrada * 2 * 1.3))

    response = ollama_chat_timeout(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
        options={"repeat_penalty": 1.3, "repeat_last_n": 128,
                 "num_predict": max_tokens},
    )
    resultado = response["message"]["content"].strip()

    # Limpiar meta-comentarios del modelo (ej: "Please provide the English text...")
    resultado = re.sub(
        r"\(Please provide the .{0,60}text[^)]*\.\)",
        "", resultado
    ).strip()

    # Detectar alucinación repetitiva
    palabras = resultado.split()
    if len(palabras) > 40:
        for n in (2, 3):
            ngramas = [" ".join(palabras[i:i+n]) for i in range(len(palabras) - n + 1)]
            conteos = Counter(ngramas)
            mas_comun, freq = conteos.most_common(1)[0]
            umbral = 0.15 if n == 3 else 0.10
            if freq > len(ngramas) * umbral:
                raise ValueError(
                    f"Repetición detectada ({freq}x '{mas_comun}'). "
                    f"Reintentando chunk."
                )

        # Detectar si la salida es absurdamente más larga que la entrada
        if len(palabras) > palabras_entrada * 4 and len(palabras) > 100:
            raise ValueError(
                f"Salida sospechosamente larga ({len(palabras)} palabras vs "
                f"{palabras_entrada} de entrada). Reintentando chunk."
            )

    return resultado


def _detectar_anomalias(original: str, traduccion: str) -> list[str]:
    """Detecta posibles anomalías en la traducción comparando con el original.
    Devuelve lista de descripciones de anomalías encontradas (vacía si no hay).
    """
    anomalias = []

    # Puntos suspensivos espurios
    if "..." in traduccion and "..." not in original and "…" not in original:
        anomalias.append("puntos suspensivos no presentes en el original")

    # Listas/explicaciones no solicitadas (bullets o markdown que no estaban en el original)
    patron_lista = r"(?:^\s*[\*\-•]\s+\*{0,2}\S|\*\s+\*{2}\S)"
    marcadores_lista = re.findall(patron_lista, traduccion, re.MULTILINE)
    marcadores_original = re.findall(patron_lista, original, re.MULTILINE)
    if len(marcadores_lista) >= 2 and not marcadores_original:
        anomalias.append("listas/explicaciones no presentes en el original")

    # Frases meta del modelo (variantes en español e inglés)
    patrones_meta = [
        r"se traduce como",
        r"por favor[,\s]+(proporciona|proporcione|provide)",
        r"no puedo traducir",
        r"texto (completo|que desea)",
        r"I cannot translate",
        r"I can'?t translate",
    ]
    for patron in patrones_meta:
        if re.search(patron, traduccion, re.IGNORECASE) and not re.search(patron, original, re.IGNORECASE):
            anomalias.append("posible meta-comentario del modelo")
            break

    return anomalias


def _guardar_cache(cache: dict[str, str], ruta_cache: Path) -> None:
    """Guarda el caché a disco con escritura atómica."""
    tmp = ruta_cache.with_suffix(ruta_cache.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        os.replace(str(tmp), str(ruta_cache))
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def traducir_chunks(chunks: list[str], modelo: str, pausa: float,
                    idioma_origen: str = "en", idioma_destino: str = "es",
                    nombre_origen: str = "English", nombre_destino: str = "Spanish",
                    ruta_cache: Optional[Path] = None,
                    ) -> tuple[list[str], list[int], list[dict]]:
    """Traduce una lista de chunks con barra de progreso y reintentos.
    Devuelve (traducciones, lista_de_chunks_con_error, chunks_sospechosos).
    Cada sospechoso es un dict con: chunk, original, traduccion, anomalias.
    """
    # ── Cargar caché si existe ──
    cache: dict[str, str] = {}
    if ruta_cache and ruta_cache.exists():
        try:
            with ruta_cache.open("r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache:
                tqdm.write(f"💾 Caché encontrado: {len(cache)} chunks ya traducidos")
                resp = input("   ¿Borrar y empezar de cero? [s/N]: ").strip().lower()
                if resp == "s":
                    cache = {}
                    try:
                        ruta_cache.unlink()
                    except Exception:
                        pass
        except Exception as e:
            tqdm.write(f"⚠️  No se pudo cargar el caché ({e}), empezando desde cero.")

    traducciones = []
    errores = []
    sospechosos = []

    with tqdm(total=len(chunks), unit="chunk", desc="Traduciendo",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} chunks [{elapsed}<{remaining}]") as barra:
        for i, chunk in enumerate(chunks):
            # ── Verificar caché ──
            hash_chunk = hashlib.sha256(chunk.encode()).hexdigest()
            if hash_chunk in cache:
                traducciones.append(cache[hash_chunk])
                barra.update(1)
                continue

            exito = False
            for intento in range(1, REINTENTOS_MAX + 1):
                try:
                    traduccion = traducir_chunk(chunk, modelo,
                                                idioma_origen, idioma_destino,
                                                nombre_origen, nombre_destino)
                    traducciones.append(traduccion)
                    exito = True

                    # Detectar anomalías en la traducción
                    anomalias = _detectar_anomalias(chunk, traduccion)
                    if anomalias:
                        sospechosos.append({
                            "chunk": i + 1,
                            "original": chunk[:120],
                            "traduccion": traduccion[:120],
                            "anomalias": anomalias,
                        })
                        tqdm.write(f"👁️  Chunk {i+1}: {', '.join(anomalias)}")

                    break
                except Exception as e:
                    if intento < REINTENTOS_MAX:
                        tqdm.write(f"⚠️  Chunk {i+1} error (intento {intento}): {e}. Reintentando...")
                        time.sleep(2)
                    else:
                        tqdm.write(f"❌ Chunk {i+1} falló tras {REINTENTOS_MAX} intentos. Se omite.")
                        traducciones.append(f"[ERROR DE TRADUCCIÓN EN CHUNK {i+1}]\n\n{chunk}")
                        errores.append(i + 1)

            # ── Persistir en caché ──
            if exito and ruta_cache:
                cache[hash_chunk] = traducciones[-1]
                _guardar_cache(cache, ruta_cache)

            barra.update(1)
            time.sleep(pausa)

    return traducciones, errores, sospechosos


def traducir_imagenes(imagenes: list, modelo: str,
                      nombre_origen: str = "English",
                      nombre_destino: str = "Spanish") -> tuple[int, int, int]:
    """Traduce in-place el texto embebido en una lista de imágenes.

    Cada elemento de `imagenes` debe ser un objeto con atributos:
      - imagen_bytes: bytes
      - traduccion: str | None  (se setea con la traducción o se deja None)

    Cachea por hash de bytes para no procesar duplicados.
    Devuelve (procesadas_con_texto, sin_texto, errores).
    """
    if not imagenes:
        return 0, 0, 0

    cache: dict[str, str | None] = {}
    con_texto = 0
    sin_texto = 0
    errores = 0

    with tqdm(total=len(imagenes), unit="img", desc="Imágenes",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} imgs [{elapsed}<{remaining}]") as barra:
        for i, img in enumerate(imagenes, 1):
            for intento in range(1, REINTENTOS_MAX + 1):
                try:
                    resultado = traducir_imagen(
                        img.imagen_bytes, modelo,
                        nombre_origen, nombre_destino, cache,
                    )
                    img.traduccion = resultado
                    if resultado is None:
                        sin_texto += 1
                    else:
                        con_texto += 1
                    break
                except Exception as e:
                    if intento < REINTENTOS_MAX:
                        tqdm.write(f"⚠️  Imagen {i} error (intento {intento}): {e}. Reintentando...")
                        time.sleep(2)
                    else:
                        tqdm.write(f"❌ Imagen {i} falló tras {REINTENTOS_MAX} intentos. Se omite.")
                        img.traduccion = None
                        errores += 1
            barra.update(1)

    return con_texto, sin_texto, errores
