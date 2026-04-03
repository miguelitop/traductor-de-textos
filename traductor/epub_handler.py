"""
Traduce un archivo EPUB preservando estructura, imágenes, estilos y enlaces.

Flujo:
  1. abrir_epub()            → EbookLib Book
  2. extraer_capitulos()     → lista de CapituloEPUB
  3. (externo) traducir textos de cada capítulo con html_handler + translator
  4. guardar_epub()          → escribe el EPUB traducido
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import NavigableString

from .html_handler import extraer_nodos_texto, aplicar_traducciones_html, parsear_html, serializar_xhtml


@dataclass
class CapituloEPUB:
    """Representa un capítulo/documento HTML dentro del EPUB."""
    item: epub.EpubHtml
    nodos: list[NavigableString] = field(default_factory=list)
    # soup se guarda aquí para poder serializar después
    soup: object = None


def abrir_epub(ruta: Path) -> epub.EpubBook:
    return epub.read_epub(str(ruta), options={'ignore_ncx': False})


def extraer_capitulos(book: epub.EpubBook) -> list[CapituloEPUB]:
    """Extrae todos los capítulos HTML del EPUB y sus nodos de texto traducibles."""
    capitulos = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = parsear_html(item.get_content())
        nodos = extraer_nodos_texto(soup)
        if not nodos:
            continue
        capitulos.append(CapituloEPUB(item=item, nodos=nodos, soup=soup))
    return capitulos


def aplicar_traducciones_epub(capitulo: CapituloEPUB,
                               traducciones: list[str]) -> None:
    """Aplica traducciones al capítulo y actualiza el contenido del item."""
    aplicar_traducciones_html(capitulo.nodos, traducciones)
    capitulo.item.set_content(serializar_xhtml(capitulo.soup).encode("utf-8"))


def guardar_epub(book: epub.EpubBook, ruta_salida: Path) -> None:
    epub.write_epub(str(ruta_salida), book)
