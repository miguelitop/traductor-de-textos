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
```

## Notas

- La traduccion se ejecuta completamente en local via Ollama, sin enviar datos a servicios externos.
- Los archivos DOCX preservan el formato original (negrita, cursiva, tablas, etc.).
- Los archivos EPUB preservan imagenes, estilos y estructura de capitulos.
- Para HTML, las imagenes se redimensionan al 75% del ancho de pagina en el DOCX resultante.
- Al mover o renombrar la carpeta del proyecto, hay que recrear el `venv` (`python3 -m venv venv`).
