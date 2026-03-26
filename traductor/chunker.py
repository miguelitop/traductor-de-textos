def dividir_en_chunks(texto: str, max_palabras: int) -> list[str]:
    """
    Divide el texto en chunks respetando límites de párrafo.
    Nunca corta a la mitad de un párrafo si hay otro párrafo disponible.
    """
    parrafos = [p.strip() for p in texto.split("\n") if p.strip()]
    chunks = []
    chunk_actual = []
    palabras_actual = 0

    for parrafo in parrafos:
        palabras_parrafo = len(parrafo.split())
        if palabras_actual + palabras_parrafo > max_palabras and chunk_actual:
            chunks.append("\n\n".join(chunk_actual))
            chunk_actual = [parrafo]
            palabras_actual = palabras_parrafo
        else:
            chunk_actual.append(parrafo)
            palabras_actual += palabras_parrafo

    if chunk_actual:
        chunks.append("\n\n".join(chunk_actual))

    return chunks
