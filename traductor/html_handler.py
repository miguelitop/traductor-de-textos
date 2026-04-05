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
    "math", "svg", "head",
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


_SEPARADOR = "\n||||\n"


def agrupar_nodos(textos: list[str], max_palabras: int) -> list[list[int]]:
    """Agrupa índices de nodos en chunks que no superen max_palabras.
    Devuelve lista de grupos, donde cada grupo es una lista de índices.
    """
    grupos = []
    grupo_actual = []
    palabras_actual = 0

    for i, texto in enumerate(textos):
        palabras = len(texto.split())
        if palabras_actual + palabras > max_palabras and grupo_actual:
            grupos.append(grupo_actual)
            grupo_actual = [i]
            palabras_actual = palabras
        else:
            grupo_actual.append(i)
            palabras_actual += palabras

    if grupo_actual:
        grupos.append(grupo_actual)

    return grupos


def juntar_grupo(textos: list[str], indices: list[int]) -> str:
    """Une los textos de un grupo con el separador."""
    return _SEPARADOR.join(textos[i] for i in indices)


def separar_grupo(traduccion: str, cantidad: int) -> list[str]:
    """Separa una traducción agrupada en sus partes individuales."""
    partes = traduccion.split("||||")
    partes = [p.strip() for p in partes]
    # Si el modelo no respetó los separadores, devolver lo que haya
    if len(partes) != cantidad:
        # Fallback: si hay menos partes, rellenar con la última;
        # si hay más, truncar
        if len(partes) < cantidad:
            partes.extend([partes[-1] if partes else ""] * (cantidad - len(partes)))
        else:
            partes = partes[:cantidad]
    return partes


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
