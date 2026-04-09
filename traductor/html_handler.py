"""
Traduce el contenido textual de un documento HTML preservando todas las etiquetas,
atributos, imágenes y enlaces.

Flujo:
  1. extraer_pagebreaks()   → extrae spans pagebreak que rompen texto, mergea nodos
  2. extraer_nodos_texto()  → lista de nodos de texto NavigableString
  3. traducir_chunks() (externo) sobre los textos extraídos
  4. aplicar_traducciones_html() → reinyecta las traducciones en el árbol BeautifulSoup
  5. reinsertar_pagebreaks() → devuelve los spans pagebreak a su posición proporcional
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
        if isinstance(padre, Tag):
            # Comparar sin prefijo de namespace (ej: "mml:math" → "math")
            nombre = padre.name.split(":")[-1] if ":" in padre.name else padre.name
            if nombre in _ETIQUETAS_SKIP:
                return True
        padre = padre.parent
    return False


def corregir_bibliorefs(soup: BeautifulSoup) -> None:
    """Corrige la estructura de citas bibliográficas mal formateadas en EPUB.

    Problema típico:
        .<a role="doc-biblioref">Harrison, 1997.</a>).
    Corrección:
        (<a role="doc-biblioref">Harrison, 1997</a>).

    Aplica tres correcciones:
    1. Punto antes del primer <a> del grupo → " ("
    2. Punto final dentro del texto de cada <a> → eliminado
    3. Números de página entre paréntesis propios .(p. X) → , p. X
    """
    for a_tag in soup.find_all("a", attrs={"role": "doc-biblioref"}):
        # --- Fix 2: quitar punto final del texto dentro del <a> ---
        if a_tag.string:
            nuevo = re.sub(r"\.\s*$", "", a_tag.string)
            if nuevo != a_tag.string:
                a_tag.string.replace_with(NavigableString(nuevo))

        # --- Fix 1: punto antes del <a> → " (" (inicio de grupo de citas) ---
        # Entre refs del mismo grupo el texto es "; ", "pp. X; ", etc. (nunca
        # termina en "."), así que un "." final indica inicio de cita nueva.
        prev = a_tag.previous_sibling
        if isinstance(prev, NavigableString) and str(prev).endswith("."):
            prev.replace_with(NavigableString(str(prev)[:-1] + " ("))

        # --- Fix 3: números de página entre paréntesis propios ---
        next_sib = a_tag.next_sibling
        if isinstance(next_sib, NavigableString):
            texto = str(next_sib)
            # .(p. 38) → , p. 38  |  .(pp. 8–9) → , pp. 8–9  |  .(pág. 5) → , pág. 5
            texto_nuevo = re.sub(r"\.?\((pp?\.)\s*([^)]+)\)", r", \1 \2", texto)
            texto_nuevo = re.sub(r"\.?\((págs?\.)\s*([^)]+)\)", r", \1 \2", texto_nuevo)
            if texto_nuevo != texto:
                next_sib.replace_with(NavigableString(texto_nuevo))


def extraer_pagebreaks(soup: BeautifulSoup) -> list[tuple]:
    """Extrae spans epub:type=pagebreak que rompen texto dentro de párrafos.

    Estos spans generan dos NavigableString separados que se traducen mal
    como fragmentos independientes.  Esta función los extrae del DOM,
    mergea los nodos de texto adyacentes y guarda la información necesaria
    para reinsertarlos después de la traducción.

    Returns:
        Lista de (span_element, parent_tag, proporción_posición).
        La proporción indica dónde estaba el span relativo al texto mergeado.
        Para reinsertar, procesar en orden inverso con reinsertar_pagebreaks().
    """
    guardados = []
    for span in soup.find_all("span", attrs={"role": "doc-pagebreak"}):
        parent = span.parent
        if parent is None:
            continue

        prev_sib = span.previous_sibling
        next_sib = span.next_sibling

        # Solo procesar si el span está entre dos nodos de texto
        if not (isinstance(prev_sib, NavigableString)
                and isinstance(next_sib, NavigableString)):
            continue

        # Proporción: dónde estaba el span dentro del texto combinado
        len_antes = len(str(prev_sib))
        len_total = len_antes + len(str(next_sib))
        proporcion = len_antes / len_total if len_total > 0 else 0.5

        # Extraer span y mergear los dos nodos de texto
        span.extract()
        texto_mergeado = str(prev_sib) + str(next_sib)
        next_sib.extract()
        prev_sib.replace_with(NavigableString(texto_mergeado))

        guardados.append((span, parent, proporcion))

    return guardados


def reinsertar_pagebreaks(guardados: list[tuple]) -> None:
    """Reinserta spans pagebreak después de la traducción.

    Divide el texto traducido en la misma proporción donde estaba el span
    originalmente, buscando el espacio más cercano para no cortar palabras.
    Debe llamarse con la lista de guardados en orden inverso al de extracción
    (se revierte internamente).
    """
    for span, parent, proporcion in reversed(guardados):
        # Buscar el primer nodo de texto con contenido en el padre
        nodo_texto = None
        for child in parent.children:
            if isinstance(child, NavigableString) and child.strip():
                nodo_texto = child
                break

        if nodo_texto is None:
            parent.append(span)
            continue

        texto = str(nodo_texto)
        pos = int(len(texto) * proporcion)

        # Buscar el espacio más cercano para no cortar palabras
        espacio_antes = texto.rfind(" ", 0, pos)
        espacio_despues = texto.find(" ", pos)

        if espacio_antes == -1 and espacio_despues == -1:
            punto_corte = pos
        elif espacio_antes == -1:
            punto_corte = espacio_despues
        elif espacio_despues == -1:
            punto_corte = espacio_antes
        else:
            punto_corte = (espacio_antes
                           if (pos - espacio_antes) <= (espacio_despues - pos)
                           else espacio_despues)

        parte1 = texto[:punto_corte]
        parte2 = texto[punto_corte:]

        # Reemplazar nodo de texto con parte1 + span + parte2
        nodo_texto.replace_with(NavigableString(parte1))
        # Localizar parte1 en el parent para insertar después
        for child in parent.children:
            if isinstance(child, NavigableString) and str(child) == parte1:
                child.insert_after(NavigableString(parte2))
                child.insert_after(span)
                break


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
