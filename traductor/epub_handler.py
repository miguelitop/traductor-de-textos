"""
Traduce un archivo EPUB preservando estructura, imágenes, estilos y enlaces.

Flujo normal:
  1. abrir_epub()            → EbookLib Book
  2. extraer_capitulos()     → lista de CapituloEPUB
  3. (externo) traducir textos de cada capítulo con html_handler + translator
  4. guardar_epub()          → escribe el EPUB traducido

Flujo con revisión:
  1-3. Igual que arriba
  4. exportar_revision()     → carpeta con HTMLs navegables + manifiesto
  5. (usuario revisa/corrige los HTMLs)
  6. importar_revision()     → lee HTMLs corregidos y los inyecta en el EPUB
  7. guardar_epub()
"""

from __future__ import annotations

import json
import posixpath
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import ebooklib
from ebooklib import epub
from bs4 import NavigableString, Tag

from .html_handler import (extraer_nodos_texto, aplicar_traducciones_html, parsear_html,
                           serializar_xhtml, extraer_pagebreaks, reinsertar_pagebreaks,
                           corregir_bibliorefs)


@dataclass
class CapituloEPUB:
    """Representa un capítulo/documento HTML dentro del EPUB."""
    item: epub.EpubHtml
    nodos: list[NavigableString] = field(default_factory=list)
    # soup se guarda aquí para poder serializar después
    soup: object = None
    # pagebreaks extraídos para reinsertar después de traducir
    pagebreaks: list = field(default_factory=list)


def abrir_epub(ruta: Path) -> epub.EpubBook:
    return epub.read_epub(str(ruta), options={'ignore_ncx': False})


def extraer_capitulos(book: epub.EpubBook) -> list[CapituloEPUB]:
    """Extrae todos los capítulos HTML del EPUB y sus nodos de texto traducibles."""
    capitulos = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = parsear_html(item.get_content())
        # Corregir citas bibliográficas mal formateadas
        corregir_bibliorefs(soup)
        # Extraer spans pagebreak antes de extraer texto para que no
        # rompan nodos de texto en fragmentos que se traducen mal
        pagebreaks = extraer_pagebreaks(soup)
        nodos = extraer_nodos_texto(soup)
        if not nodos:
            continue
        capitulos.append(CapituloEPUB(item=item, nodos=nodos, soup=soup,
                                       pagebreaks=pagebreaks))
    return capitulos


def aplicar_traducciones_epub(capitulo: CapituloEPUB,
                               traducciones: list[str]) -> tuple[str, bytes]:
    """Aplica traducciones al capítulo y retorna (item_name, xhtml_bytes)."""
    aplicar_traducciones_html(capitulo.nodos, traducciones)
    if capitulo.pagebreaks:
        reinsertar_pagebreaks(capitulo.pagebreaks)
    xhtml = serializar_xhtml(capitulo.soup)
    return capitulo.item.get_name(), xhtml.encode("utf-8")


def guardar_epub(ruta_origen: Path, ruta_salida: Path,
                 contenidos: dict[str, bytes] | None = None) -> None:
    """Guarda el EPUB copiando el original y reemplazando solo los XHTML modificados.

    Evita usar epub.write_epub() que destruye <head>, <title>, atributos de <body>
    y corrompe el OPF.

    Args:
        ruta_origen: EPUB original (se usa como base).
        ruta_salida: Ruta donde guardar el EPUB resultante.
        contenidos: Mapa {item_name: bytes_xhtml} donde item_name es el nombre
                    relativo del item (ej: 'xhtml/c1.xhtml'). Se resuelve al path
                    completo dentro del ZIP (ej: 'OEBPS/xhtml/c1.xhtml').
    """
    if contenidos is None:
        contenidos = {}

    tmp = ruta_salida.with_suffix('.epub.tmp')
    with zipfile.ZipFile(str(ruta_origen), 'r') as zin, \
         zipfile.ZipFile(str(tmp), 'w') as zout:
        # Construir mapeo: path_en_zip → contenido nuevo
        nombres_zip = {info.filename for info in zin.infolist()}
        reemplazos = {}
        for item_name, data in contenidos.items():
            # Buscar el path completo en el ZIP que termine con el item_name
            for zip_name in nombres_zip:
                if zip_name == item_name or zip_name.endswith('/' + item_name):
                    reemplazos[zip_name] = data
                    break

        # EPUB spec: mimetype debe ser el primer entry, stored, sin extra field.
        # Adobe Digital Editions rechaza el EPUB si esto no se cumple.
        mime_info = zipfile.ZipInfo('mimetype')
        mime_info.compress_type = zipfile.ZIP_STORED
        mime_info.extra = b''
        zout.writestr(mime_info, b'application/epub+zip')

        for item in zin.infolist():
            if item.filename == 'mimetype':
                continue  # ya escrito arriba
            data = reemplazos.get(item.filename, zin.read(item.filename))
            zout.writestr(item, data)
    shutil.move(str(tmp), str(ruta_salida))


_MANIFIESTO = "manifiesto.json"


def _reescribir_urls_para_revision(soup, item_name: str,
                                    mapa_item_a_cap: dict[str, str]) -> None:
    """Reescribe URLs en el HTML para que funcionen en la carpeta de revisión.

    Hace dos cosas:
    1. Resuelve paths relativos a recursos (imágenes, CSS) desde la raíz de la carpeta.
       Ej: '../Images/cover.jpg' (relativo a 'xhtml/') → 'images/cover.jpg'
    2. Remapea links entre capítulos a los nombres cap_XX.html.
       Ej: 'xhtml/c1.xhtml#f1.1' → 'cap_10.html#f1.1'
    """
    item_dir = str(PurePosixPath(item_name).parent)

    attrs_url = {'src', 'href', 'xlink:href'}
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        for attr in attrs_url:
            val = tag.get(attr)
            if not val or val.startswith(('http://', 'https://', 'data:', '#', 'mailto:')):
                continue

            # Separar fragmento (#anchor)
            if '#' in val:
                path_part, fragment = val.split('#', 1)
            else:
                path_part, fragment = val, None

            # Resolver a path absoluto dentro del EPUB
            if item_dir != '.':
                path_abs = posixpath.normpath(posixpath.join(item_dir, path_part))
            else:
                path_abs = posixpath.normpath(path_part)

            # Si apunta a otro capítulo, remapear a cap_XX.html
            if path_abs in mapa_item_a_cap:
                nuevo = mapa_item_a_cap[path_abs]
            else:
                nuevo = path_abs

            tag[attr] = f"{nuevo}#{fragment}" if fragment else nuevo


def _restaurar_urls_desde_revision(soup, item_name: str,
                                    mapa_cap_a_item: dict[str, str]) -> None:
    """Revierte la reescritura: de cap_XX.html y paths absolutos a relativos EPUB originales."""
    item_dir = str(PurePosixPath(item_name).parent)

    attrs_url = {'src', 'href', 'xlink:href'}
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        for attr in attrs_url:
            val = tag.get(attr)
            if not val or val.startswith(('http://', 'https://', 'data:', '#', 'mailto:')):
                continue

            if '#' in val:
                path_part, fragment = val.split('#', 1)
            else:
                path_part, fragment = val, None

            # Si es un cap_XX.html, remapear al item_name original
            if path_part in mapa_cap_a_item:
                path_abs = mapa_cap_a_item[path_part]
            else:
                path_abs = path_part

            # Convertir a path relativo desde el directorio del item
            if item_dir != '.':
                relativo = posixpath.relpath(path_abs, item_dir)
            else:
                relativo = path_abs

            tag[attr] = f"{relativo}#{fragment}" if fragment else relativo


def _exportar_recursos(book: epub.EpubBook, dir_revision: Path) -> None:
    """Copia imágenes, CSS, fuentes y otros recursos del EPUB a la carpeta de revisión.

    Mantiene la estructura de directorios interna del EPUB para que los links
    relativos en los HTMLs sigan funcionando.
    """
    tipos_recurso = (
        ebooklib.ITEM_IMAGE, ebooklib.ITEM_STYLE, ebooklib.ITEM_FONT,
        ebooklib.ITEM_COVER, ebooklib.ITEM_VECTOR,
    )
    for tipo in tipos_recurso:
        for item in book.get_items_of_type(tipo):
            ruta_destino = dir_revision / item.get_name()
            ruta_destino.parent.mkdir(parents=True, exist_ok=True)
            ruta_destino.write_bytes(item.get_content())


def exportar_revision(book: epub.EpubBook, capitulos: list[CapituloEPUB],
                       dir_revision: Path) -> None:
    """Exporta los capítulos traducidos como HTMLs navegables + manifiesto.

    Crea:
      dir_revision/
        index.html          ← índice con links a cada capítulo
        manifiesto.json     ← mapeo archivo → item EPUB
        cap_01.html ... cap_NN.html
        Images/             ← imágenes copiadas del EPUB
        Styles/             ← CSS copiados del EPUB
    """
    dir_revision.mkdir(parents=True, exist_ok=True)

    # Copiar imágenes, CSS, fuentes para que los links funcionen
    _exportar_recursos(book, dir_revision)

    # Construir mapa item_name → cap_XX.html para remapear links entre capítulos
    mapa_item_a_cap = {}
    for i, capitulo in enumerate(capitulos, 1):
        mapa_item_a_cap[capitulo.item.get_name()] = f"cap_{i:02d}.html"

    # También incluir items DOCUMENT que no tienen texto (no están en capitulos)
    # para que links a ellos también se resuelvan
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        if item.get_name() not in mapa_item_a_cap:
            mapa_item_a_cap[item.get_name()] = item.get_name()

    manifiesto = []
    enlaces_index = []

    for i, capitulo in enumerate(capitulos, 1):
        nombre_archivo = f"cap_{i:02d}.html"
        # Reescribir URLs: recursos relativos → absolutos, links entre caps → cap_XX.html
        _reescribir_urls_para_revision(capitulo.soup, capitulo.item.get_name(), mapa_item_a_cap)
        contenido = serializar_xhtml(capitulo.soup)
        # Restaurar URLs para no modificar el soup original (mapeo inverso)
        mapa_cap_a_item = {v: k for k, v in mapa_item_a_cap.items()}
        _restaurar_urls_desde_revision(capitulo.soup, capitulo.item.get_name(), mapa_cap_a_item)
        (dir_revision / nombre_archivo).write_text(contenido, encoding="utf-8")

        # Título: intentar extraer del <title> o <h1>, sino usar nombre del item
        titulo = None
        if capitulo.soup.title and capitulo.soup.title.string:
            titulo = capitulo.soup.title.string.strip()
        if not titulo:
            h1 = capitulo.soup.find("h1")
            if h1:
                titulo = h1.get_text(strip=True)
        if not titulo:
            titulo = capitulo.item.get_name()

        manifiesto.append({
            "archivo": nombre_archivo,
            "item_name": capitulo.item.get_name(),
            "titulo": titulo,
        })
        enlaces_index.append(f'    <li><a href="{nombre_archivo}">{titulo}</a></li>')

    # Guardar manifiesto
    (dir_revision / _MANIFIESTO).write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Generar index.html
    titulo_libro = book.get_metadata("DC", "title")
    titulo_str = titulo_libro[0][0] if titulo_libro else "EPUB"
    index_html = (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'/>\n"
        f"<title>Revisión — {titulo_str}</title>\n"
        "<style>body{font-family:sans-serif;max-width:700px;margin:2em auto}"
        "li{margin:0.3em 0}a{color:#0066cc}</style>\n"
        "</head><body>\n"
        f"<h1>Revisión: {titulo_str}</h1>\n"
        f"<p>{len(capitulos)} capítulos traducidos</p>\n"
        "<ol>\n" + "\n".join(enlaces_index) + "\n</ol>\n"
        "</body></html>"
    )
    (dir_revision / "index.html").write_text(index_html, encoding="utf-8")


def importar_revision(ruta_epub: Path,
                      dir_revision: Path) -> dict[str, bytes]:
    """Lee HTMLs corregidos y retorna mapa {item_name: xhtml_bytes} para guardar_epub.

    Usa el manifiesto.json para mapear cada archivo de vuelta al item EPUB correcto.
    Lee el XHTML original del EPUB para preservar el <head> y solo reemplazar el <body>.
    """
    ruta_manifiesto = dir_revision / _MANIFIESTO
    if not ruta_manifiesto.exists():
        raise FileNotFoundError(
            f"No se encontró {_MANIFIESTO} en {dir_revision}. "
            "¿Es una carpeta generada con --revisar?"
        )

    manifiesto = json.loads(ruta_manifiesto.read_text(encoding="utf-8"))

    # Construir mapa cap_XX.html → item_name para restaurar links entre capítulos
    mapa_cap_a_item = {e["archivo"]: e["item_name"] for e in manifiesto}

    # Leer los XHTML originales del EPUB para preservar el <head>
    originales = {}
    with zipfile.ZipFile(str(ruta_epub), 'r') as z:
        for name in z.namelist():
            if name.endswith(('.xhtml', '.html')):
                originales[name] = z.read(name)

    contenidos = {}
    aplicados = 0
    for entrada in manifiesto:
        archivo = entrada["archivo"]
        item_name = entrada["item_name"]

        ruta_html = dir_revision / archivo
        if not ruta_html.exists():
            print(f"   ⚠️  {archivo} no encontrado, se omite")
            continue

        contenido_rev = ruta_html.read_text(encoding="utf-8")
        # Re-parsear y restaurar links cap_XX→item_name y paths absolutos→relativos
        soup_rev = parsear_html(contenido_rev)
        _restaurar_urls_desde_revision(soup_rev, item_name, mapa_cap_a_item)

        # Buscar el XHTML original para preservar el <head>
        xhtml_original = None
        for zip_name, data in originales.items():
            if zip_name == item_name or zip_name.endswith('/' + item_name):
                xhtml_original = data
                break

        if xhtml_original:
            soup_orig = parsear_html(xhtml_original)
            # Reemplazar solo el <body> del original con el traducido
            body_orig = soup_orig.find('body')
            body_rev = soup_rev.find('body')
            if body_orig and body_rev:
                # Preservar atributos del <body> original (epub:type, id, etc.)
                body_orig.clear()
                for child in list(body_rev.children):
                    body_orig.append(child.extract())
                resultado = serializar_xhtml(soup_orig)
            else:
                resultado = serializar_xhtml(soup_rev)
        else:
            resultado = serializar_xhtml(soup_rev)

        contenidos[item_name] = resultado.encode("utf-8")
        aplicados += 1

    print(f"   {aplicados}/{len(manifiesto)} capítulos aplicados desde revisión")
    return contenidos
