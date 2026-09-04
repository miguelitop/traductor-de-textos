MODELO_DEFAULT = "translategemma:12b"
# El OCR de imágenes usa un modelo aparte: la rama de visión de translategemma
# no está instruction-tuned y transcribe mal (ver image_handler).
MODELO_VISION_DEFAULT = "qwen2.5vl:7b"
CHUNK_PALABRAS = 350
REINTENTOS_MAX = 3
PAUSA_ENTRE_CHUNKS = 0.3
FUENTE_DEFAULT = "Bookman Old Style"
TAMANO_FUENTE_DEFAULT = 11
