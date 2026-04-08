import re
import time
from collections import Counter

import ollama
from tqdm import tqdm

from .config import REINTENTOS_MAX


def traducir_chunk(texto: str, modelo: str,
                   idioma_origen: str = "en", idioma_destino: str = "es",
                   nombre_origen: str = "English", nombre_destino: str = "Spanish") -> str:
    """Envía un chunk a Ollama y devuelve la traducción."""
    instruccion_links = ""
    if "\u00ab" in texto and "\u00bb" in texto:
        instruccion_links = (
            "IMPORTANT: The text contains hyperlink markers in the format \u00abN:text\u00bb. "
            "You MUST preserve these markers exactly, translating only the text between "
            f"the colon and the closing \u00bb. Never remove, reorder, or alter the marker numbers. "
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

    response = ollama.chat(
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


def traducir_chunks(chunks: list[str], modelo: str, pausa: float,
                    idioma_origen: str = "en", idioma_destino: str = "es",
                    nombre_origen: str = "English", nombre_destino: str = "Spanish",
                    ) -> tuple[list[str], list[int], list[dict]]:
    """Traduce una lista de chunks con barra de progreso y reintentos.
    Devuelve (traducciones, lista_de_chunks_con_error, chunks_sospechosos).
    Cada sospechoso es un dict con: chunk, original, traduccion, anomalias.
    """
    traducciones = []
    errores = []
    sospechosos = []

    with tqdm(total=len(chunks), unit="chunk", desc="Traduciendo",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} chunks [{elapsed}<{remaining}]") as barra:
        for i, chunk in enumerate(chunks):
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

            barra.update(1)
            time.sleep(pausa)

    return traducciones, errores, sospechosos
