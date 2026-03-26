# Plan: Traductor con preservación de formato (LibreOffice + python-docx)

**Fecha:** 2026-03-26
**Proyecto:** traductor
**Estado:** Pendiente

## Contexto

El script `traductor-eng-sp.py` traduce archivos RTF de inglés a español usando Ollama, pero **pierde todo el formato** al convertir a texto plano con `striprtf`. El objetivo es soportar múltiples formatos de entrada (PDF, RTF, DOC, DOCX) preservando formato: negritas, cursivas, hipervínculos, notas al pie, tablas, imágenes.

## Estrategia

**Pipeline unificado:**

```
Cualquier formato (PDF/RTF/DOC/ODT) → LibreOffice headless → DOCX
                                                                ↓
                                              python-docx (traducir preservando formato)
                                                                ↓
                                                          DOCX de salida
                                                                ↓ (opcional)
                                                    LibreOffice → PDF/formato original
```

- **LibreOffice headless** convierte cualquier formato a DOCX (un solo comando, probado, mantenido).
- **python-docx** itera sobre la estructura del DOCX (párrafos → runs), traduce solo el texto, preserva formato.
- Si la entrada ya es DOCX, se salta la conversión.
- Se elimina la dependencia de `striprtf`.

## Arquitectura modular

```
traductor/
  __init__.py
  cli.py              # Punto de entrada, argparse, detección de formato, orquestación
  config.py           # Constantes: MODELO_DEFAULT, CHUNK_PALABRAS, etc.
  translator.py       # traducir_chunk() con Ollama + reintentos
  chunker.py          # Dividir unidades traducibles en chunks
  converter.py        # Conversión de formatos vía LibreOffice headless
  docx_handler.py     # Extraer unidades traducibles del DOCX + reescribir con traducción
traductor-eng-sp.py   # Se mantiene como wrapper: from traductor.cli import main; main()
```

## Archivos a modificar/crear

| Archivo | Acción | Contenido |
|---------|--------|-----------|
| `traductor/__init__.py` | Crear | Vacío |
| `traductor/config.py` | Crear | Constantes extraídas de líneas 43-46 del script actual |
| `traductor/translator.py` | Crear | `traducir_chunk()` (líneas 89-103) + lógica de reintentos (líneas 204-217) |
| `traductor/chunker.py` | Crear | `dividir_en_chunks()` adaptada para trabajar con unidades traducibles |
| `traductor/converter.py` | Crear | `convertir_a_docx(ruta) -> Path` usando `soffice --headless --convert-to docx` |
| `traductor/docx_handler.py` | Crear | Extracción de párrafos/runs/tablas + reescritura preservando formato |
| `traductor/cli.py` | Crear | `main()` refactorizado: detecta formato, convierte si necesario, traduce, guarda |
| `traductor-eng-sp.py` | Modificar | Wrapper que importa y llama a `traductor.cli.main()` |

## Fases de implementación

### Fase 1: Modularizar (sin cambiar funcionalidad)
1. Crear estructura de paquete `traductor/`
2. Extraer `config.py`, `translator.py`, `chunker.py`
3. Crear `cli.py` con la lógica de `main()` actual
4. Mantener `rtf_to_text` temporalmente en cli.py
5. Verificar que funciona igual que antes con un RTF

### Fase 2: Soporte DOCX con python-docx
1. Crear `docx_handler.py`:
   - Recorrer `document.paragraphs` → para cada párrafo, concatenar texto de sus `runs`
   - Recorrer `document.tables` → `rows` → `cells` → `paragraphs` → `runs`
   - Detectar runs con imágenes (vía `run._element`) y saltarlos
   - Devolver lista de unidades traducibles (texto + referencia al párrafo)
2. Después de traducir, reescribir:
   - Poner traducción en el primer run del párrafo, vaciar los demás
   - Esto preserva el formato del primer run (conservador pero seguro)
3. Actualizar `cli.py` para usar docx_handler cuando la entrada es .docx

### Fase 3: Conversión con LibreOffice
1. Crear `converter.py`:
   - `convertir_a_docx(ruta: Path, dir_tmp: Path) -> Path`
   - Ejecuta: `soffice --headless --convert-to docx --outdir {dir_tmp} {ruta}`
   - Verifica que el DOCX de salida existe, maneja errores
   - Detecta si LibreOffice está instalado y da instrucciones si no
2. Actualizar `cli.py`:
   - Si la entrada NO es .docx → convertir primero → usar docx_handler
   - Limpiar archivos temporales al terminar
3. Eliminar dependencia de `striprtf`

### Fase 4: Preservación avanzada (futura)
- Formato a nivel de run individual (pedir marcadores al modelo)
- Hipervínculos vía XML (`paragraph._element`)
- Notas al pie vía `document.element`
- Headers/footers vía `document.sections`

## Dependencias

```
# Eliminar
striprtf

# Mantener
ollama
tqdm

# Agregar
python-docx>=1.1

# Sistema (ya suele estar instalado)
libreoffice
```

## Verificación

1. **Fase 1**: Correr `python traductor-eng-sp.py archivo.rtf` → debe producir el mismo resultado que antes
2. **Fase 2**: Correr con un .docx que tenga negritas, cursivas, tablas, imágenes → verificar que el DOCX de salida conserva formato
3. **Fase 3**: Correr con un .pdf → verificar que convierte a DOCX y traduce correctamente
4. Comparar visualmente entrada vs salida para validar preservación de formato
