# Traductor de textos

Traduce documentos entre idiomas usando [Ollama](https://ollama.com/) con el modelo [TranslateGemma](https://ollama.com/library/translategemma) de forma local y privada.

## Formatos soportados

| Formato | Entrada | Salida |
|---------|---------|--------|
| DOCX | directo | DOCX (preserva formato) |
| PDF | via Calibre | DOCX |
| RTF, DOC, ODT | via LibreOffice | DOCX |
| EPUB | nativo | EPUB (preserva imágenes y estilos) |
| HTML | nativo | DOCX (via LibreOffice) |

## Requisitos

- **Python 3.10+**
- **[Ollama](https://ollama.com/)** corriendo localmente (`ollama serve`)
- **[LibreOffice](https://www.libreoffice.org/)** (para convertir RTF/DOC/ODT/HTML a DOCX)
- **[Calibre](https://calibre-ebook.com/)** (solo para PDF)

## Instalacion

```bash
# Clonar el repositorio
git clone <url-del-repo>
cd traductor-de-textos

# Crear entorno virtual e instalar dependencias
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Descargar el modelo de traduccion (primera vez)
ollama pull translategemma:12b
```

## Uso

```bash
# Activar el entorno virtual
source venv/bin/activate

# Uso basico (selector interactivo de idiomas)
python traductor-de-textos.py documento.docx

# Especificar idiomas directamente
python traductor-de-textos.py libro.epub --de-idioma en --a-idioma es

# Traducir una pagina web descargada a DOCX
python traductor-de-textos.py pagina.html --de-idioma en --a-idioma es
```

## Opciones

| Opcion | Descripcion |
|--------|-------------|
| `--de-idioma CODIGO` | Idioma de origen (codigo de 2 letras, ej: `en`). Sin esto, muestra selector interactivo |
| `--a-idioma CODIGO` | Idioma de destino (codigo de 2 letras, ej: `es`). Sin esto, muestra selector interactivo |
| `--modelo MODELO` | Modelo Ollama a usar (default: `translategemma:12b`) |
| `--chunk-palabras N` | Palabras por chunk (default: `350`) |
| `--salida ARCHIVO` | Archivo de salida (default: `<entrada>_<idioma>.<ext>`) |
| `--fuente NOMBRE` | Fuente para el DOCX de salida (default: conservar original) |
| `--tamano-fuente N` | Tamano de fuente en puntos (default: conservar original) |
| `--actualizar-modelo` | Verificar si hay una version mas nueva del modelo en Ollama |
| `--revisar` | EPUB: exportar capitulos traducidos como HTML para revision manual |
| `--desde-revision CARPETA` | EPUB: generar EPUB final desde HTMLs corregidos manualmente |
| `--traducir-imagenes` | Tambien traducir el texto dentro de las imagenes (OCR + traduccion en un solo paso). Agrega la traduccion como caption debajo de cada imagen con texto. |

## Ejemplos

```bash
# Traducir PDF de frances a aleman
python traductor-de-textos.py paper.pdf --de-idioma fr --a-idioma de

# Traducir EPUB y exportar para revision
python traductor-de-textos.py novela.epub --de-idioma en --a-idioma es --revisar

# Aplicar correcciones manuales al EPUB
python traductor-de-textos.py novela.epub --desde-revision novela_revision

# Solo verificar/actualizar el modelo sin traducir
python traductor-de-textos.py --actualizar-modelo

# Usar un modelo diferente
python traductor-de-textos.py documento.docx --modelo gemma3:12b

# Traducir tambien el texto que aparece dentro de las imagenes
python traductor-de-textos.py informe.docx --de-idioma en --a-idioma es --traducir-imagenes
```

## Optimizar Ollama (opcional)

Para acelerar la inferencia y reducir el consumo de memoria, conviene activar Flash Attention y la cuantizacion del KV cache a nivel del servidor de Ollama. Aplica al modelo de traduccion.

Si se lanza Ollama desde terminal con `ollama serve`, agregar a `~/.zshrc`:

```bash
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
export OLLAMA_KEEP_ALIVE=30m
```

Despues, `source ~/.zshrc` y reiniciar `ollama serve`.

Si se usa la app de Ollama (icono en la barra de menu) en lugar de `ollama serve`, las mismas variables se setean con `launchctl setenv NOMBRE valor` y luego salir/volver a abrir la app. Se pierden al reiniciar la Mac; para que sean permanentes, agregarlas a un LaunchAgent.

Que hace cada una:

- `OLLAMA_FLASH_ATTENTION=1` — atencion mas eficiente en memoria; mejora notable en contextos largos (modelo de vision).
- `OLLAMA_KV_CACHE_TYPE=q8_0` — cuantiza el KV cache a 8 bits y libera ~50% de memoria. Solo tiene efecto si Flash Attention esta activo. Critico en Macs con RAM justa cuando se usan los dos modelos a la vez.
- `OLLAMA_KEEP_ALIVE=30m` — mantiene el modelo cargado en memoria entre llamadas. Sin esto, Ollama puede descargarlo y recargarlo, agregando 10-30 s de pausa por switch.

Para verificar que se aplicaron, en `~/.ollama/logs/server.log` deberia figurar `flash_attention = 1` al cargar el modelo.

### Macs con poca RAM

Con 16-18 GB de RAM, `translategemma:12b` (~8 GB) deja margen suficiente para el sistema y otras aplicaciones. Si se necesita aún más holgura, usar la variante de 4B:

```bash
ollama pull translategemma:4b
python traductor-de-textos.py informe.docx --modelo translategemma:4b --traducir-imagenes
```

## Notas

- La traduccion se ejecuta completamente en local via Ollama, sin enviar datos a servicios externos.
- Los archivos DOCX preservan el formato original (negrita, cursiva, tablas, etc.).
- Los archivos EPUB preservan imagenes, estilos y estructura de capitulos.
- Para HTML, las imagenes se redimensionan al 75% del ancho de pagina en el DOCX resultante.
- Al mover o renombrar la carpeta del proyecto, hay que recrear el `venv` (`python3 -m venv venv`).
- `--traducir-imagenes` agrega ~3-5 segundos por imagen. Usa el mismo modelo de traduccion que el texto. El caption se inserta debajo de cada imagen, ajustado a su ancho y alineacion. Algunas imagenes con texto fino (graficos de linea con etiquetas chicas) pueden no ser detectadas — en ese caso no se agrega caption.
