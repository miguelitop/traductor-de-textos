"""
Traduce el contenido textual de un documento HTML preservando todas las etiquetas,
atributos, imágenes y enlaces.

Flujo:
  1. extraer_nodos_texto()  → lista de nodos de texto NavigableString
  2. traducir_chunks() (externo) sobre los textos extraídos
  3. aplicar_traducciones_html() → reinyecta las traducciones en el árbol BeautifulSoup
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag, ProcessingInstruction

# Etiquetas cuyo contenido no se traduce
_ETIQUETAS_SKIP = {
    "script", "style", "code", "pre", "kbd", "samp", "var",
    "math", "svg",
}


def _en_etiqueta_skip(nodo: NavigableString) -> bool:
    """Devuelve True si el nodo está dentro de una etiqueta que no se traduce."""
    padre = nodo.parent
    while padre:
        if isinstance(padre, Tag) and padre.name in _ETIQUETAS_SKIP:
            return True
        padre = padre.parent
    return False


def extraer_nodos_texto(soup: BeautifulSoup) -> list[NavigableString]:
    """Devuelve todos los nodos de texto traducibles del árbol."""
    nodos = []
    for nodo in soup.find_all(string=True):
        if not isinstance(nodo, NavigableString):
            continue
        # Saltar processing instructions (<?xml ...?>) y nodos huérfanos del documento
        if isinstance(nodo, ProcessingInstruction):
            continue
        if nodo.parent is None or nodo.parent.name == '[document]':
            continue
        if _en_etiqueta_skip(nodo):
            continue
        texto = nodo.strip()
        if not texto:
            continue
        nodos.append(nodo)
    return nodos


def aplicar_traducciones_html(nodos: list[NavigableString],
                               traducciones: list[str]) -> None:
    """Reemplaza el texto de cada nodo con su traducción correspondiente.
    Preserva el espaciado original alrededor del texto.
    """
    for nodo, traduccion in zip(nodos, traducciones):
        original = str(nodo)
        # Detectar espaciado inicial/final y preservarlo
        lstrip = original[: len(original) - len(original.lstrip())]
        rstrip = original[len(original.rstrip()):]
        nodo.replace_with(lstrip + traduccion + rstrip)


def parsear_html(contenido: str | bytes) -> BeautifulSoup:
    return BeautifulSoup(contenido, "html.parser")


def serializar_html(soup: BeautifulSoup) -> str:
    return str(soup)


# Elementos XHTML que deben ser self-closing
_VOID_ELEMENTS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img',
    'input', 'link', 'meta', 'param', 'source', 'track', 'wbr',
}


_XML_DECL = '<?xml version="1.0" encoding="utf-8"?>'
_XHTML_NS = 'xmlns="http://www.w3.org/1999/xhtml"'


def serializar_xhtml(soup: BeautifulSoup) -> str:
    """Serializa el árbol como XHTML válido (para contenido EPUB).

    BeautifulSoup con html.parser produce void elements sin cierre (<br>).
    EPUB requiere XHTML donde estos deben ser self-closing (<br/>).
    También asegura declaración XML y namespace XHTML requeridos por lectores
    como Adobe Digital Editions.
    """
    html = str(soup)
    for tag in _VOID_ELEMENTS:
        html = re.sub(rf'<({tag}\b[^>]*?)(?<!/)\s*>', r'<\1/>', html)

    # Asegurar namespace XHTML en <html>
    if '<html' in html and _XHTML_NS not in html:
        html = html.replace('<html', f'<html {_XHTML_NS}', 1)

    # Asegurar declaración XML al inicio
    if not html.lstrip().startswith('<?xml'):
        html = _XML_DECL + '\n' + html

    return html
