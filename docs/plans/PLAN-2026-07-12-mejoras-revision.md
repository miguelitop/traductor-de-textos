# Plan de mejoras — revisión del 2026-07-12

Checklist de hallazgos ordenados por prioridad para implementar.

---

## 🔴 Alta prioridad

### 1. ✅ Bug: `aplicar_fuente` no recorre tablas anidadas

- **Archivo:** `traductor/docx_handler.py:423-429`
- **Problema:** `aplicar_fuente` itera `doc.tables` directo pero no entra a tablas dentro de celdas. `_recorrer_unidades` y `_recorrer_imagenes` sí lo hacen recursivamente. Si un DOCX tiene tablas anidadas, las celdas internas no reciben la fuente configurada con `--fuente` / `--tamano-fuente`.
- **Fix aplicado:** Se extrajo `_aplicar_fuente_recursivo(parrafos, tablas, ...)` con el mismo patrón recursivo que `_recorrer_unidades`. `aplicar_fuente` ahora delega en ella.

### 2. ✅ Performance: EPUB no agrupa nodos de texto en chunks

- **Archivo:** `traductor/cli.py:339-354`
- **Problema:** El path EPUB manda cada nodo de texto como chunk individual a Ollama (línea 344: `traducir_chunks(textos, ...)`), mientras que DOCX y HTML usan `agrupar_nodos` + `juntar_grupo`/`separar_grupo` para empaquetar varios nodos por llamada. Si un capítulo tiene 30 frases cortas, son 30 round-trips en vez de ~3-4.
- **Fix aplicado:** El loop EPUB ahora usa `agrupar_nodos` → `juntar_grupo` → `separar_grupo`, idéntico al path DOCX. Las traducciones se desagrupan con correspondencia 1:1 a los nodos originales.

---

## 🟡 Media prioridad

### 3. ✅ Código muerto: `chunker.py` no se usa

- **Archivo:** `traductor/chunker.py`
- **Problema:** El módulo exporta `dividir_en_chunks` pero nadie lo importa. El agrupamiento real se hace con `html_handler.agrupar_nodos`. Tener dos formas de chunking en el proyecto confunde.
- **Fix aplicado:** Se movieron `agrupar_nodos`, `juntar_grupo`, `separar_grupo` y `SEPARADOR` de `html_handler.py` a `chunker.py`. Se eliminó `dividir_en_chunks`. Los imports en `cli.py` se actualizaron.

### 4. ✅ Robustez: Sin timeout en llamadas a `ollama.chat`

- **Archivos:** `traductor/translator.py:45-50`, `traductor/image_handler.py:69-74`
- **Problema:** Si Ollama se cuelga o entra en un loop interno, el script queda bloqueado indefinidamente. No hay timeout en las llamadas.
- **Fix aplicado:** Se creó `_ollama_chat_timeout()` en ambos archivos con doble estrategia: (1) intenta `ollama.chat(..., timeout=180)` nativo, (2) si falla con `TypeError` (versión vieja de ollama), usa `ThreadPoolExecutor` con timeout 300s. Cualquier `TimeoutException` se convierte en `Exception` para que el bucle de reintentos de `traducir_chunks` lo maneje correctamente.

### 5. ✅ `separar_grupo`: fallback silencioso puede generar traducciones incorrectas

- **Archivo:** `traductor/chunker.py` (movida desde `html_handler.py` en #3)
- **Problema:** Cuando el modelo no respeta los separadores `||||` y la cantidad de partes no coincide, la función rellena duplicando la última parte (`partes.extend([partes[-1]] * ...)`) o trunca. Esto genera párrafos duplicados (fantasma) o pérdida de contenido sin que el usuario lo sepa.
- **Fix aplicado:** Se agregó `tqdm.write(...)` con warning visible cuando `len(partes) != cantidad`. El fallback de relleno/truncamiento se mantiene, pero ahora el usuario sabe que ocurrió.

### 6. ✅ EPUB: `_construir_resolver_recurso` recorre todos los items del book

- **Archivo:** `traductor/epub_handler.py:85-108`
- **Problema:** `_construir_resolver_recurso` llama a `book.get_item_with_href(ruta_abs)` para resolver cada imagen. Esto hace un scan lineal de los items del book por cada imagen. En EPUBs con cientos de recursos, puede ser lento.
- **Fix aplicado:** Se construye un diccionario `{href_normalizado: item}` una sola vez en `extraer_imagenes_epub` y se pasa a la closure. Búsqueda O(1) en vez de O(M) por imagen. Complejidad total pasa de O(N×M) a O(N+M).

---

## 🔵 Baja prioridad

### 7. ✅ Sin capacidad de resume para traducciones largas

- **Archivo:** `traductor/translator.py:117-165`
- **Problema:** Si una traducción de 200 chunks se interrumpe en el chunk 150 (error de red, Ctrl+C, Ollama se cae), hay que empezar de cero. No hay checkpointing.
- **Fix aplicado:** `traducir_chunks` acepta `ruta_cache` opcional. Cada chunk se cachea por hash SHA-256 en un JSON (`<salida>.docx.cache.json`). Al re-ejecutar, carga el caché y salta chunks ya traducidos. Se limpia al terminar exitosamente. Escritura atómica vía `.tmp` + `os.replace()`.

### 8. ✅ Sin tests automatizados

- **Problema:** El proyecto no tiene tests. Las funciones más delicadas (manipulación de XML, separadores, tokens, regex de bibliografía) no tienen cobertura.
- **Fix aplicado:** Se crearon 3 archivos de test con 21 tests en total:
  - `tests/test_chunker.py` — 8 tests para `separar_grupo` y `agrupar_nodos`
  - `tests/test_translator.py` — 8 tests para `_detectar_anomalias`
  - `tests/test_docx_handler.py` — 5 tests para `_tokens_intactos`
  - Todos pasan (`21 passed in 0.43s`). Sin mocks de Ollama — solo funciones puras.

---

## 🟢 Menor / mantenibilidad

### 9. ✅ Resolver de imágenes HTML está inline en `cli.py`

- **Archivo:** `traductor/cli.py:410-417`
- **Problema:** La función `_resolver_html` está definida como closure inline en `main()`. Es el único lugar donde el CLI conoce detalles de resolución de imágenes del filesystem.
- **Fix aplicado:** Se creó `crear_resolver_filesystem(base_dir)` en `html_handler.py`. La closure inline en `cli.py` se reemplazó por una llamada a esta función.

### 10. ✅ Dos serializadores con nombres poco claros

- **Archivo:** `traductor/html_handler.py:283-284` y `392-412`
- **Problema:** `serializar_html` es simplemente `str(soup)` y se usa para HTML→DOCX. `serializar_xhtml` hace muchas más cosas (void elements, declaración XML, namespace) y se usa para EPUB. Los nombres no comunican cuándo usar cada uno.
- **Fix aplicado:** Se eliminó `serializar_html` (era solo `str(soup)`) y su único caller en `cli.py` se reemplazó por `str(soup)` directo. `serializar_xhtml` se mantiene con su nombre para EPUB.

### 11. ✅ `from collections import Counter` dentro de una función

- **Archivo:** `traductor/image_handler.py:83`
- **Problema:** `Counter` se importa dentro de `_es_repeticion_loop`. Ya está importado a nivel módulo en `translator.py`. Conviene moverlo al tope de `image_handler.py`.
- **Fix aplicado:** Se movió `from collections import Counter` al tope del archivo y se eliminó el import interno en `_es_repeticion_loop`.

### 12. ✅ `requirements.txt` no pinea versiones

- **Archivo:** `requirements.txt`
- **Problema:** Sin versiones fijas, un `pip install` futuro puede traer breaking changes.
- **Fix aplicado:** Se agregaron versiones mínimas: `beautifulsoup4>=4.9`, `ebooklib>=0.18`, `ollama>=0.1.0`, `Pillow>=9.0`, `python-docx>=0.8.11`, `tqdm>=4.60`, `pytest>=7.0`.

### 13. ✅ `setup-ollama-perf.sh` es solo macOS

- **Archivo:** `setup-ollama-perf.sh`
- **Problema:** Usa `launchctl`, `osascript`, `brew services`. El proyecto también se usa en Windows y WSL según el README y `converter.py`.
- **Fix aplicado:** Se agregó advertencia al inicio del script indicando que es solo macOS. Se agregaron instrucciones equivalentes comentadas para Windows nativo (`setx`) y WSL/Linux (`export` en `.bashrc`).

### 14. ✅ `_es_wsl` y helpers de path solo en `converter.py`

- **Archivo:** `traductor/converter.py:11-46`
- **Problema:** La detección WSL y normalización de paths está acoplada a `converter.py`. Si otra parte del código necesita resolver paths entre Windows y WSL, no puede.
- **Fix aplicado:** Se creó `traductor/utils.py` con `_es_wsl`, `normalizar_path_entrada`, `_es_exe_windows`, `_ruta_para_exe` y las regex compiladas. `converter.py` y `cli.py` importan desde `utils`.

---

## Orden sugerido de implementación

1. #3 — Mover chunking a `chunker.py` (refactor previo limpio)
2. #2 — EPUB agrupe nodos en chunks (mayor ganancia de performance)
3. #1 — Bug de fuente en tablas anidadas
4. #4 — Timeout en llamadas a Ollama
5. #5 — Warning en fallback de `separar_grupo`
6. #6 — Optimizar resolución de recursos EPUB
7. #9, #10, #11, #14 — Limpieza de código
8. #12, #13 — Configuración y scripts
9. #7 — Resume / checkpointing
10. #8 — Tests
