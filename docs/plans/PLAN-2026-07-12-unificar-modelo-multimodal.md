# Plan: Migración a TranslateGemma multimodal único — 2026-07-12

## Contexto

Actualmente el proyecto usa **dos modelos** Ollama:
- `translategemma:12b` para traducción de texto
- `qwen2.5vl:7b` para OCR + traducción de imágenes (`--traducir-imagenes`)

Google lanzó TranslateGemma multimodal que maneja texto e imágenes en **un solo modelo**. En Ollama, los tags `translategemma:12b` y `translategemma:27b` ya aceptan `images=[base64]` en la API chat. Esto permite:
- **RTX 3090**: usar `translategemma:27b` (~17 GB) con mejor calidad
- **MacBook 18GB**: usar solo `translategemma:12b` (~8 GB), eliminando la presión de 2 modelos

## Fases de implementación

### Fase 1: Extraer `_ollama_chat_timeout` compartido a `utils.py`

La función está duplicada en `translator.py` y `image_handler.py` (~40 líneas cada una). Se mueve a `utils.py` como `ollama_chat_timeout()` (pública, usada por múltiples módulos).

**Archivos:**
- `traductor/utils.py`: agregar `ollama_chat_timeout(*args, timeout_secs=180, fallback_timeout=300, **kwargs)`
- `traductor/translator.py`: eliminar duplicado, importar de `.utils`
- `traductor/image_handler.py`: eliminar duplicado, importar de `.utils`

### Fase 2: Simplificar `config.py`

Eliminar 3 constantes de visión:
- `MODELO_VISION_DEFAULT = "qwen2.5vl:7b"`
- `DIM_MIN_IMAGEN = 100`
- `SENTINEL_SIN_TEXTO = "[NO_TEXT]"`

`DIM_MIN_IMAGEN` pasa como constante local a `image_handler.py`. El archivo queda de 11 → 8 líneas.

### Fase 3: Simplificar `image_handler.py`

Cambios:
1. **Imports**: remover `DIM_MIN_IMAGEN, SENTINEL_SIN_TEXTO` de config, agregar `ollama_chat_timeout` de utils, agregar `DIM_MIN_IMAGEN = 100` como local
2. **`_construir_prompt()`** → reescribir: prompt simple bilingüe sin sentinel, sin reglas enumeradas. Si el modelo no encuentra texto, devuelve vacío.
3. **`_OPCIONES_VISION`** → eliminar dict. Pasar `temperature=0.1, num_predict=1024` inline en `_llamar_vision()`
4. **`_llamar_vision()`** → simplificar: usa `ollama_chat_timeout` de utils, `messages=[{..., images:[bytes]}]`, options inline
5. **`traducir_imagen()`** → eliminar chequeo de `SENTINEL_SIN_TEXTO`, reemplazar por `if not crudo.strip(): return None`. Mantener `_es_descartable`, `_es_repeticion_loop`, `_limpiar_resultado`, cache. Firma sigue igual: `(imagen_bytes, modelo, nombre_origen, nombre_destino, cache) -> str | None`
6. **`concurrent.futures`** → eliminar import (ya no se usa en este archivo)

### Fase 4: Cambiar captions DOCX de tabla → párrafo

El approach actual usa una tabla 1×2 con bordes invisibles (imagen arriba, caption abajo). En la práctica no funcionó bien (problemas de layout en distintos lectores DOCX).

**Nuevo approach:** insertar la traducción como un párrafo independiente después del párrafo de la imagen, sin tocar la imagen original. Mucho más simple y portable.

**Archivo:** `traductor/docx_handler.py`

Cambios:
1. **Eliminar** funciones helper de tabla (ya no se usan):
   - `_EMU_POR_DXA` (constante)
   - `_emu_a_dxa()`
   - `_crear_bordes_invisibles()`
   - `_crear_celda()`
   - `_crear_parrafo_caption()`
   - `_construir_tabla_imagen_caption()`
   (~80 líneas eliminadas)

2. **Simplificar `_crear_parrafo_caption`** → renombrar a `_crear_parrafo_caption(texto)` que devuelve un elemento `<w:p>` con:
   - Alineación: misma que la imagen original (`alineacion_jc`)
   - Estilo: cursiva, 9pt (18 half-points), color gris (#666666) para diferenciarlo del cuerpo
   - Un solo run con el texto traducido

3. **Reescribir `aplicar_captions_imagenes()`**:
   - Para cada imagen con traducción, crear el párrafo caption con `_crear_parrafo_caption(img.traduccion)`
   - Insertarlo **después** del párrafo de la imagen: `elem_p.addnext(caption_p)`
   - Ya no se reemplaza el run de la imagen ni se eliminan párrafos vacíos
   - La imagen original queda intacta en su párrafo

```python
def aplicar_captions_imagenes(imagenes: list[ImagenTraducible]) -> int:
    aplicados = 0
    for img in imagenes:
        if not img.traduccion:
            continue
        elem_p = img.parrafo._element
        caption_p = _crear_parrafo_caption(img.traduccion)
        elem_p.addnext(caption_p)
        aplicados += 1
    return aplicados
```

Ventajas sobre la tabla:
- Layout predecible en cualquier lector DOCX (Word, LibreOffice, Google Docs)
- La imagen no se toca — cero riesgo de corrupción
- El caption es un párrafo normal que se puede editar/borrar manualmente
- ~80 líneas menos de código

### Fase 5: Actualizar `translator.py`

1. **`_ollama_chat_timeout`** → eliminado (ya en utils)
2. **`traducir_imagenes()`**: renombrar parámetro `modelo_vision` → `modelo`
3. **Llamada interna**: pasar `modelo` en vez de `modelo_vision` a `traducir_imagen()`

### Fase 6: Actualizar `cli.py`

1. **Import**: remover `MODELO_VISION_DEFAULT` del import de config
2. **`--modelo-vision`**: eliminar flag (5 líneas de parser.add_argument)
3. **Modo `--actualizar-modelo` solo**: eliminar bloque de verificación de modelo de visión (~10 líneas)
4. **Flujo normal**: eliminar `verificar_modelo(args.modelo_vision, ...)` (1 línea)
5. **3 paths**: cambiar `traducir_imagenes(..., args.modelo_vision, ...)` → `traducir_imagenes(..., args.modelo, ...)` en DOCX, EPUB y HTML
6. **Help text**: actualizar descripción de `--traducir-imagenes`

### Fase 7: Actualizar `README.md`

1. **Instalación**: eliminar `ollama pull qwen2.5vl:7b`
2. **Tabla de opciones**: eliminar fila `--modelo-vision`
3. **Sección Mac RAM**: reescribir — ya no hay 2 modelos compitiendo
4. **Notas**: actualizar texto que referencia el modelo de visión
5. **Optimizar Ollama**: quitar referencias a "modelo de visión"

### Fase 8: Nuevo archivo de tests

`tests/test_image_handler.py`:
- `test_es_descartable_diminuta` — imagen < 100px → True
- `test_es_descartable_normal` — imagen normal → False  
- `test_es_descartable_bytes_invalidos` — bytes no-imagen → True
- `test_limpiar_resultado_sin_duplicados` — preserva orden
- `test_limpiar_resultado_con_duplicados` — elimina repetidas
- `test_limpiar_resultado_lineas_cortas` — preserva líneas ≤2 chars
- `test_limpiar_resultado_vacio` — string vacío → ""

### Fase 9: Actualizar `setup-ollama-perf.sh`

Cambiar comentario "modelo de visión" → "modelo de traducción" (cosmético).

## Archivos que NO requieren cambios

- `chunker.py`, `converter.py`, `epub_handler.py`, `html_handler.py`, `idiomas.py` — lógica de formato, agnóstica al modelo
- `docx_handler.py` — solo cambia `aplicar_captions_imagenes` (tabla → párrafo), el resto intacto
- `tests/test_chunker.py`, `tests/test_translator.py`, `tests/test_docx_handler.py` — tests existentes intactos
- `requirements.txt` — dependencias sin cambios

## Decisiones de diseño

1. **Timeout compartido**: se mueve a `utils.py`. Elimina 40 líneas duplicadas y es el momento justo para hacerlo (ambos archivos ya se tocan en esta migración).
2. **Prompt de imagen**: simple, sin sentinel `[NO_TEXT]`. Si el modelo no encuentra texto devuelve vacío → `_limpiar_resultado` lo convierte a `None`.
3. **`DIM_MIN_IMAGEN`**: constante local en `image_handler.py` (100px). No necesita estar en config porque es un umbral interno de implementación.
4. **Opciones de modelo**: imágenes usan `temperature=0.1, num_predict=1024` inline. Sin `repeat_penalty` (el modelo unificado lo maneja internamente).
5. **`--modelo-vision`**: eliminación limpia, sin deprecation. Los usuarios que lo pasen recibirán error de argparse.

## Verificación

```bash
python -m pytest tests/ -v          # todos los tests pasan
python traductor-de-textos.py --help  # sin --modelo-vision
python -c "import traductor"         # sin errores de import
grep -r "modelo_vision\|MODELO_VISION\|qwen\|SENTINEL_SIN_TEXTO" traductor/  # sin resultados
```
