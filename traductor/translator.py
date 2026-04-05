import time

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
    prompt = (
        f"You are a professional {nombre_origen} ({idioma_origen}) to {nombre_destino} ({idioma_destino}) translator. "
        f"Your goal is to accurately convey the meaning and nuances of the original "
        f"{nombre_origen} text while adhering to {nombre_destino} grammar, vocabulary, and cultural sensitivities. "
        f"Produce only the {nombre_destino} translation, without any additional explanations or commentary. "
        f"{instruccion_links}"
        f"Please translate the following {nombre_origen} text into {nombre_destino}:\n\n\n"
        f"{texto}"
    )
    response = ollama.chat(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
    )
    return response["message"]["content"].strip()


def traducir_chunks(chunks: list[str], modelo: str, pausa: float,
                    idioma_origen: str = "en", idioma_destino: str = "es",
                    nombre_origen: str = "English", nombre_destino: str = "Spanish",
                    ) -> tuple[list[str], list[int]]:
    """Traduce una lista de chunks con barra de progreso y reintentos.
    Devuelve (traducciones, lista_de_chunks_con_error).
    """
    traducciones = []
    errores = []

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

    return traducciones, errores
