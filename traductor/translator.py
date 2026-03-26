import time

import ollama
from tqdm import tqdm

from .config import REINTENTOS_MAX


def traducir_chunk(texto: str, modelo: str) -> str:
    """Envía un chunk a Ollama y devuelve la traducción."""
    prompt = (
        "You are a professional English (en) to Spanish (es) translator. "
        "Your goal is to accurately convey the meaning and nuances of the original "
        "English text while adhering to Spanish grammar, vocabulary, and cultural sensitivities. "
        "Produce only the Spanish translation, without any additional explanations or commentary. "
        "Please translate the following English text into Spanish:\n\n\n"
        f"{texto}"
    )
    response = ollama.chat(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
    )
    return response["message"]["content"].strip()


def traducir_chunks(chunks: list[str], modelo: str, pausa: float) -> tuple[list[str], list[int]]:
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
                    traduccion = traducir_chunk(chunk, modelo)
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
