import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


@dataclass
class HyperlinkInfo:
    """Info de un hipervínculo dentro de un párrafo."""
    url: str
    r_id: str
    rPr: object = None


@dataclass
class UnidadTraducible:
    """Representa un párrafo traducible con referencia a sus runs originales."""
    texto: str
    parrafo: Paragraph
    traduccion: str = ""
    hyperlinks: dict = field(default_factory=dict)
    base_rPr: object = None


def _parrafo_tiene_imagen(parrafo: Paragraph) -> bool:
    """Detecta si un párrafo contiene imágenes inline."""
    for run in parrafo.runs:
        if run._element.findall(qn("w:drawing")):
            return True
        if run._element.findall(qn("w:pict")):
            return True
    return False


def _extraer_texto_con_links(parrafo: Paragraph) -> tuple[str, dict, object]:
    """Extrae texto del párrafo con marcadores «N:texto» para hipervínculos.

    Retorna (texto_con_marcadores, {indice: HyperlinkInfo}, rPr_base).
    """
    elem = parrafo._element
    link_map = {}
    link_counter = 0
    text_parts = []
    base_rPr = None

    for child in elem:
        if child.tag == qn("w:r"):
            for t_elem in child.findall(qn("w:t")):
                text_parts.append(t_elem.text or "")
            if base_rPr is None:
                rPr = child.find(qn("w:rPr"))
                if rPr is not None:
                    base_rPr = deepcopy(rPr)

        elif child.tag == qn("w:hyperlink"):
            link_counter += 1
            r_id = child.get(qn("r:id"), "")
            url = ""
            if r_id:
                try:
                    url = parrafo.part.rels[r_id].target_ref
                except (KeyError, AttributeError):
                    pass

            link_text = ""
            link_rPr = None
            for run_elem in child.findall(qn("w:r")):
                for t_elem in run_elem.findall(qn("w:t")):
                    link_text += t_elem.text or ""
                if link_rPr is None:
                    found = run_elem.find(qn("w:rPr"))
                    if found is not None:
                        link_rPr = deepcopy(found)

            link_map[link_counter] = HyperlinkInfo(
                url=url, r_id=r_id, rPr=link_rPr,
            )
            text_parts.append(f"\u00ab{link_counter}:{link_text}\u00bb")

    return "".join(text_parts).strip(), link_map, base_rPr


def _extraer_de_parrafos(parrafos: list[Paragraph]) -> list[UnidadTraducible]:
    """Extrae unidades traducibles de una lista de párrafos."""
    unidades = []
    for parrafo in parrafos:
        if _parrafo_tiene_imagen(parrafo):
            continue
        texto, links, base_rPr = _extraer_texto_con_links(parrafo)
        if not texto:
            continue
        unidades.append(UnidadTraducible(
            texto=texto, parrafo=parrafo,
            hyperlinks=links, base_rPr=base_rPr,
        ))
    return unidades


def extraer_unidades(ruta_docx: Path) -> tuple[Document, list[UnidadTraducible]]:
    """Abre un DOCX y extrae todas las unidades traducibles.
    Recorre párrafos del cuerpo principal y celdas de tablas.
    Devuelve (documento, lista_de_unidades).
    """
    doc = Document(str(ruta_docx))
    unidades = []

    # Párrafos del cuerpo
    unidades.extend(_extraer_de_parrafos(doc.paragraphs))

    # Tablas: cada celda tiene sus propios párrafos
    for tabla in doc.tables:
        for fila in tabla.rows:
            for celda in fila.cells:
                unidades.extend(_extraer_de_parrafos(celda.paragraphs))

    return doc, unidades


_LINK_PATTERN = re.compile(r"\u00ab(\d+):(.*?)\u00bb")


def _crear_run_element(texto: str, rPr: object = None) -> OxmlElement:
    """Crea un elemento w:r con texto y formato opcional."""
    run_el = OxmlElement("w:r")
    if rPr is not None:
        run_el.append(deepcopy(rPr))
    t_el = OxmlElement("w:t")
    t_el.text = texto
    t_el.set(qn("xml:space"), "preserve")
    run_el.append(t_el)
    return run_el


def _reconstruir_parrafo(parrafo: Paragraph, texto: str,
                         link_map: dict, base_rPr: object):
    """Reconstruye el XML del párrafo con hipervínculos preservados."""
    elem = parrafo._element

    # Limpiar todos los hijos excepto w:pPr (propiedades del párrafo)
    for child in list(elem):
        if child.tag != qn("w:pPr"):
            elem.remove(child)

    # Partir el texto en segmentos: [texto, num, link_texto, texto, ...]
    segments = _LINK_PATTERN.split(texto)

    for j in range(0, len(segments), 3):
        # Texto normal
        plain = segments[j]
        if plain:
            elem.append(_crear_run_element(plain, base_rPr))

        # Hipervínculo (si hay)
        if j + 2 < len(segments):
            link_idx = int(segments[j + 1])
            link_text = segments[j + 2]

            if link_idx in link_map:
                info = link_map[link_idx]
                hl_el = OxmlElement("w:hyperlink")
                if info.r_id:
                    hl_el.set(qn("r:id"), info.r_id)
                link_rPr = info.rPr if info.rPr is not None else base_rPr
                hl_el.append(_crear_run_element(link_text, link_rPr))
                elem.append(hl_el)
            else:
                # Fallback: insertar como texto normal
                elem.append(_crear_run_element(link_text, base_rPr))


def aplicar_traducciones(unidades: list[UnidadTraducible]):
    """Reescribe los párrafos con las traducciones, preservando hipervínculos."""
    for unidad in unidades:
        if not unidad.traduccion:
            continue

        parrafo = unidad.parrafo

        if unidad.hyperlinks:
            _reconstruir_parrafo(
                parrafo, unidad.traduccion,
                unidad.hyperlinks, unidad.base_rPr,
            )
        else:
            # Sin hipervínculos: lógica original (más segura, preserva formato)
            runs = parrafo.runs
            if not runs:
                continue
            runs[0].text = unidad.traduccion
            for run in runs[1:]:
                run.text = ""


def guardar_docx(doc: Document, ruta_salida: Path):
    """Guarda el documento DOCX."""
    doc.save(str(ruta_salida))
