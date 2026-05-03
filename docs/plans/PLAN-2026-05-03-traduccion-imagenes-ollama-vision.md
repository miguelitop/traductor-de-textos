# Plan: Traducción de texto en imágenes vía Ollama-vision (caption debajo)

**Fecha:** 2026-05-03
**Proyecto:** traductor
**Estado:** Pendiente

## Contexto

Actualmente el traductor procesa texto en DOCX, EPUB y HTML, pero **ignora todo texto que esté embebido en imágenes** (capturas de pantalla, infografías, diagramas, portadas, etc.). El objetivo es detectar texto dentro de las imágenes del documento, traducirlo, y mostrar la traducción al lector.

## Estrategia: Opción B (caption debajo de la imagen)

En vez de modificar las imágenes (lo cual implica OCR con bounding boxes + inpainting + redibujado de texto, todo frágil), insertamos un **caption con la traducción** debajo de cada imagen que contenga texto. Más simple, robusto y reversible.

Para OCR + traducción usamos **un modelo de visión vía Ollama** (ej. `qwen2.5vl:7b`, `llama3.2-vision:11b`, o `gemma3` con visión). Una sola llamada por imagen: OCR + traducción combinados, mejor calidad que Tesseract en imágenes con texto estilizado o fondos complejos, y sin agregar dependencias del sistema (ya tenemos Ollama corriendo).

```
imagen → Ollama-vision (OCR+traducción) → caption con la traducción debajo de la imagen
```

Si la imagen no tiene texto, el modelo devuelve cadena vacía (o un sentinel) y no se inserta caption.

## Decisiones de diseño

1. **Caption ajustado al ancho y posición de la imagen.** No tocamos los bytes de las imágenes. Insertamos un caption envuelto en un contenedor que **toma el ancho y la alineación de la imagen que describe** (no a todo el ancho de página). Esto preserva el original, es accesible (lectores de pantalla lo leen), y mantiene la presentación visual coherente.
   - **HTML/EPUB:** `<figure>` con `display: table` + `<figcaption>` con `caption-side: bottom`. El `display:table` hace que el contenedor se ajuste automáticamente al ancho de la imagen; CSS estándar, soportado por todos los lectores modernos. Si la imagen ya está dentro de un `<figure>`, solo agregamos `<figcaption>`; si está suelta, la envolvemos. Se preservan estilos de alineación originales (centrado, float left/right) copiándolos del `<img>` al wrapper.
   - **DOCX:** tabla de 1×2 con bordes invisibles, ancho fijo igual al de la imagen (sacado de `inline_shape.width` en EMU), alineación copiada del párrafo original. Es el mismo mecanismo que Word usa internamente al "Insertar título" sobre una imagen — sobrevive a edición posterior y se renderiza consistente entre lectores.

2. **Un solo modelo de visión multipropósito.** No usamos `translategemma` para esta etapa (no acepta imágenes). El modelo de visión hace OCR + traducción en un solo prompt. Esto desacopla la traducción de imágenes del flujo de chunks de texto.

3. **Cache por hash de imagen.** Muchos EPUBs reutilizan imágenes (logo editorial, ornamentos, ilustraciones repetidas). Hasheamos los bytes y cacheamos la traducción dentro de la corrida para no re-procesar.

4. **Opt-in por flag.** La traducción de imágenes es lenta (varios segundos por imagen). Se activa con `--traducir-imagenes`. Por defecto desactivada para no alterar el comportamiento actual.

5. **Sentinel "sin texto".** El prompt instruye al modelo a responder exactamente `[NO_TEXT]` si la imagen no contiene texto traducible (íconos decorativos, fotos sin texto, ornamentos). Si la respuesta empieza con ese sentinel, no se inserta caption.

6. **Filtros previos baratos.** Antes de mandar a Ollama, descartar imágenes muy pequeñas (`< 100x100 px`), formatos vectoriales puros sin rasterizar (SVG → caso aparte, ver más abajo), y duplicados ya cacheados. Reduce llamadas innecesarias.

## Arquitectura

### Módulo nuevo: `traductor/image_handler.py`

```python
# API pública
def traducir_imagen(
    imagen_bytes: bytes,
    modelo_vision: str,
    nombre_origen: str,
    nombre_destino: str,
    cache: dict[str, str],
) -> str | None:
    """Devuelve la traducción del texto en la imagen, o None si no tiene texto.
    Usa cache[hash(bytes)] para deduplicar.
    """

def formatear_caption(traduccion: str) -> str:
    """Envuelve la traducción con un prefijo identificable.
    Ej: '[Texto en imagen traducido] ...'"""
```

Internamente:

- `_hash_imagen(bytes) -> str` — sha256 truncado.
- `_filtrar_descartable(bytes) -> bool` — abre con PIL, descarta si dimensiones < umbral.
- `_prompt_vision(nombre_origen, nombre_destino) -> str` — prompt que instruye OCR+traducción y el sentinel `[NO_TEXT]`.
- `_llamar_ollama_vision(imagen_bytes, modelo, prompt) -> str` — usa `ollama.chat` con `images=[bytes]`.

### Config nuevo en `traductor/config.py`

```python
MODELO_VISION_DEFAULT = "qwen2.5vl:7b"   # o el que decidamos tras probar
DIM_MIN_IMAGEN = 100                      # px mínimos por lado
PREFIJO_CAPTION = "[Texto en imagen]"     # marcador en caption
SENTINEL_SIN_TEXTO = "[NO_TEXT]"
```

### Cambios en handlers

#### `docx_handler.py`

Hoy `_parrafo_tiene_imagen()` ya detecta párrafos con imágenes inline pero los **salta** (línea 123). Hay que:

1. Modificar el flujo de `extraer_unidades()`: en vez de ignorar el párrafo con imagen, recorrer sus runs y, por cada `w:drawing`/`w:pict`, extraer el `r:embed` → resolver al `relationship` → leer `image_part.blob` (bytes de la imagen). También leer `inline_shape.width` (EMU) y la alineación del párrafo padre.
2. Crear una nueva dataclass `ImagenTraducible(parrafo, imagen_bytes, hash, ancho_emu, alineacion, anclada, traduccion=None)`.
3. En `aplicar_traducciones()`, para cada imagen con traducción:
   - Si es **inline**: envolver imagen + caption en una tabla de 1×2 con bordes invisibles, `tblW` igual al ancho de la imagen, alineación de tabla = alineación original, y mover la imagen a la primera celda. Caption en la segunda celda.
   - Si es **anclada** (no inline): fallback a párrafo después con sangrías aproximadas (ver casos borde) y registrar en log.
4. Estilo del caption: párrafo con `style="Caption"` si existe en el doc, sino itálica + tamaño 90%.

Helpers nuevos:
- `_extraer_imagenes_de_parrafo(parrafo) -> list[ImagenTraducible]`
- `_envolver_imagen_en_tabla_caption(parrafo, imagen_run, ancho_emu, alineacion, texto_caption)` — construye la tabla 1×2, mueve el run de la imagen a la primera celda, agrega caption en la segunda.
- `_insertar_caption_aproximado(parrafo, ancho_emu, alineacion, texto_caption)` — fallback para imágenes ancladas: párrafo después con sangrías izquierda/derecha calculadas para emular el ancho.

#### `epub_handler.py` + `html_handler.py`

Los EPUBs y HTMLs trabajan con BeautifulSoup. La lógica es paralela:

1. Después de `extraer_nodos_texto()`, hacer un pase nuevo: `extraer_imagenes_html(soup, resolver_recurso) -> list[ImagenHTML]`.
2. Para cada `<img>` o `<image>` (SVG): resolver el `src`/`xlink:href` a bytes (en EPUB vía `book.get_item_with_href()`, en HTML standalone vía path relativo al archivo).
3. Insertar caption envuelto para que tome el ancho y alineación de la imagen:
   - Si la imagen **no está dentro de un `<figure>`**: envolverla en `<figure style="display: table; margin: 0 auto;">` (o con `float` si la imagen tiene `float`/`align`) y agregar `<figcaption class="img-caption" style="caption-side: bottom; text-align: center;">[Texto en imagen] ...traducción...</figcaption>`. Copiar al wrapper los estilos de alineación relevantes (`text-align`, `float`, `margin`) del contexto de la imagen.
   - Si la imagen **ya está dentro de un `<figure>` sin `<figcaption>`**: solo agregar `<figcaption>`.
   - Si el `<figure>` **ya tiene `<figcaption>`**: agregar nuestro `<figcaption class="img-caption-translated">` adicional con el prefijo `[Texto en imagen]` para distinguirlo del caption original.
4. Marcar el caption insertado con un atributo `data-translated-caption="1"` para que en re-corridas se skipee en `extraer_nodos_texto()`.

Helpers nuevos en `html_handler.py`:
- `extraer_imagenes_html(soup, resolver_recurso) -> list[ImagenHTML]` — donde `resolver_recurso` es un callable que dado un href devuelve bytes (cada handler le pasa el suyo).
- `envolver_imagen_con_caption(img_tag, texto_caption)` — maneja los tres casos (sin figure / con figure sin caption / con figure con caption) y aplica `display:table` + estilos de alineación.

#### Caso SVG

SVG con `<text>` adentro **no** necesita Ollama-vision: es texto traducible directo. Esto cae en el flujo normal de `extraer_nodos_texto()` si lo destildamos de `_ETIQUETAS_SKIP` (hoy `svg` está en skip por defecto). Decisión: **fuera de scope de este plan** — dejarlo en skip y documentar. SVG con texto se trata en un plan futuro.

SVG rasterizado (referenciado por `<img src="x.svg">`): rasterizamos con `cairosvg` o equivalente antes de mandar a Ollama. Si `cairosvg` no está, lo skipeamos con warning. Decisión inicial: **skipear SVGs**, agregar soporte solo si aparece como necesidad real.

### Cambios en `cli.py`

1. Nuevo flag: `--traducir-imagenes` (default: False).
2. Nuevo flag: `--modelo-vision MODELO` (default: `MODELO_VISION_DEFAULT`).
3. Si `--traducir-imagenes`, después del flujo normal de traducción de texto:
   - Para cada handler, llamar a `traducir_imagenes_<formato>(unidades_imagen, modelo_vision, ...)`.
   - Mostrar barra de progreso `tqdm` separada para imágenes.
   - Loguear por cada imagen: hash truncado, dimensiones, ✅ traducido / ⏭️ sin texto / ❌ error.
4. En `--actualizar-modelo`, también verificar el modelo de visión si `--traducir-imagenes` está activo.

### Cambios en `translator.py`

Función nueva paralela a `traducir_chunks` pero para imágenes:

```python
def traducir_imagenes(
    imagenes: list[ImagenTraducible],
    modelo_vision: str,
    idioma_origen: str, idioma_destino: str,
    nombre_origen: str, nombre_destino: str,
) -> None:
    """Traduce in-place. Setea imagen.traduccion. Cachea por hash."""
```

Comparte el patrón de reintentos / barra de progreso con `traducir_chunks`. Reusamos `tqdm` y `REINTENTOS_MAX`.

## Prompt de visión

```
You are a professional {nombre_origen} to {nombre_destino} translator.
Look at the attached image and:
1. If the image contains NO readable text, respond with exactly: [NO_TEXT]
2. If the image contains text, transcribe it and translate it to {nombre_destino}.
   Output ONLY the translation, no explanations, no original text, no quotes.
   Preserve line breaks if they convey meaning (e.g., distinct labels in a diagram).

Image follows.
```

## Cambios en dependencias

`requirements.txt`:
- Agregar `Pillow` (para abrir imágenes y validar dimensiones).

`README.md`:
- Documentar el nuevo flag.
- Listar el modelo de visión recomendado y comando `ollama pull qwen2.5vl:7b`.
- Aclarar que la traducción de imágenes es opt-in y agrega tiempo significativo.

## Plan de implementación (orden sugerido)

1. **Spike de modelo de visión.** Probar `qwen2.5vl:7b` y `llama3.2-vision:11b` con 3-4 imágenes representativas (texto limpio, texto estilizado, foto sin texto, infografía). Elegir el que mejor balance dé. *Salida: decisión de modelo + ajustes al prompt.*
2. **`image_handler.py`** con la API pública y el caso de no-imagen / sentinel.
3. **Integración DOCX** (es el formato más simple para empezar — sin árbol HTML, sin paths externos).
4. **Integración EPUB** (tiene resolver de recursos vía `book`).
5. **Integración HTML** (resolver paths relativos al archivo).
6. **Flag CLI + barra de progreso + log.**
7. **Cache + filtros (dimensiones mínimas).**
8. **README + ejemplos.**

Cada paso queda probado manualmente con un archivo de muestra antes de pasar al siguiente.

## Casos borde a considerar

- **Imágenes en headers/footers de DOCX** — fuera de scope inicial, documentar.
- **Imágenes ancladas (no inline) en DOCX** — no están en el flujo del párrafo, así que la tabla 1×2 no aplica. Fallback: párrafo después con sangrías izquierda/derecha calculadas a partir de `ancho_pagina - ancho_imagen` para aproximar visualmente la posición. Documentar como limitación; fidelidad pixel-perfect requiere text-box anclado (ver Fuera de Scope).
- **Imágenes dentro de tablas** — `extraer_unidades()` ya recorre celdas; el handler de imágenes debe hacerlo también.
- **Imágenes referenciadas con URL externa (`http://...`)** — skipear con warning.
- **Captions duplicados en re-corridas** — si el archivo ya fue procesado y se vuelve a correr, el `[Texto en imagen]` previo se traduciría como texto. Mitigación: marcar el párrafo/elemento del caption con un atributo (`data-translated-caption="1"` en HTML, `style` específico en DOCX) y skipearlo en `extraer_unidades` y `extraer_nodos_texto`.
- **Imagen de portada del EPUB** (`ebooklib.ITEM_COVER`) — no está en el flujo de capítulos. Decidir si traducirla y dónde insertar el caption. Default: skipear, no rompe nada y rara vez tiene texto traducible útil.
- **Modelo de visión no instalado** — al activar el flag, verificar disponibilidad antes de procesar y fallar temprano con mensaje claro y comando `ollama pull` sugerido.

## Métricas de éxito

- Un EPUB con 10 imágenes con texto se procesa sin errores.
- Las imágenes sin texto no generan caption (sentinel funcionando).
- Imágenes duplicadas (mismo hash) solo gastan una llamada al modelo.
- El comportamiento por defecto (sin `--traducir-imagenes`) es idéntico al actual.

## Fuera de scope (planes futuros)

- Opción A (overlay sobre la imagen con inpainting + redibujado).
- Soporte para SVG con `<text>` traducible.
- Traducción de imágenes en headers/footers DOCX.
- Cache persistente entre corridas (en disco).
- Text-box anclado en DOCX para fidelidad pixel-perfect con imágenes ancladas (manipulando `wp:anchor` con coordenadas absolutas) — frágil entre lectores no-Word, solo si el fallback de sangrías resulta insuficiente.
