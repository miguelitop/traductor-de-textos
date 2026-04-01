import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph


@dataclass
class HyperlinkInfo:
    """Info de un hipervínculo dentro de un párrafo."""
    url: str
    r_id: str
    anchor: str = ""
    rPr: object = None


@dataclass
class NotaInfo:
    """Info de una referencia a nota al pie o final."""
    tipo: str  # "footnote" o "endnote"
    nota_id: str
    rPr: object = None


@dataclass
class UnidadTraducible:
    """Representa un párrafo traducible con referencia a sus runs originales."""
    texto: str
    parrafo: Paragraph
    traduccion: str = ""
    hyperlinks: dict = field(default_factory=dict)
    notas: dict = field(default_factory=dict)
    base_rPr: object = None


def _parrafo_tiene_imagen(parrafo: Paragraph) -> bool:
    """Detecta si un párrafo contiene imágenes inline."""
    for run in parrafo.runs:
        if run._element.findall(qn("w:drawing")):
            return True
        if run._element.findall(qn("w:pict")):
            return True
    return False


def _extraer_texto_con_links(parrafo: Paragraph) -> tuple[str, dict, dict, object]:
    """Extrae texto del párrafo con marcadores para hipervínculos y notas.

    Marcadores: «N:texto» para links, «FN:id» / «EN:id» para notas.
    Retorna (texto_con_marcadores, {indice: HyperlinkInfo}, {indice: NotaInfo}, rPr_base).
    """
    elem = parrafo._element
    link_map = {}
    nota_map = {}
    link_counter = 0
    nota_counter = 0
    text_parts = []
    base_rPr = None

    for child in elem:
        if child.tag == qn("w:r"):
            # Verificar si el run contiene una referencia a nota
            fn_ref = child.find(qn("w:footnoteReference"))
            en_ref = child.find(qn("w:endnoteReference"))
            if fn_ref is not None or en_ref is not None:
                ref_elem = fn_ref if fn_ref is not None else en_ref
                tipo = "footnote" if fn_ref is not None else "endnote"
                nota_id = ref_elem.get(qn("w:id"), "")
                nota_counter += 1
                nota_rPr = child.find(qn("w:rPr"))
                nota_map[nota_counter] = NotaInfo(
                    tipo=tipo, nota_id=nota_id,
                    rPr=deepcopy(nota_rPr) if nota_rPr is not None else None,
                )
                prefijo = "FN" if tipo == "footnote" else "EN"
                text_parts.append(f"\u00ab{prefijo}:{nota_counter}\u00bb")
            else:
                for t_elem in child.findall(qn("w:t")):
                    text_parts.append(t_elem.text or "")
            if base_rPr is None:
                rPr = child.find(qn("w:rPr"))
                if rPr is not None:
                    base_rPr = deepcopy(rPr)

        elif child.tag == qn("w:hyperlink"):
            link_counter += 1
            r_id = child.get(qn("r:id"), "")
            anchor = child.get(qn("w:anchor"), "")
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
                url=url, r_id=r_id, anchor=anchor, rPr=link_rPr,
            )
            text_parts.append(f"\u00ab{link_counter}:{link_text}\u00bb")

    return "".join(text_parts).strip(), link_map, nota_map, base_rPr


def _extraer_de_parrafos(parrafos: list[Paragraph]) -> list[UnidadTraducible]:
    """Extrae unidades traducibles de una lista de párrafos."""
    unidades = []
    for parrafo in parrafos:
        if _parrafo_tiene_imagen(parrafo):
            continue
        texto, links, notas, base_rPr = _extraer_texto_con_links(parrafo)
        if not texto:
            continue
        unidades.append(UnidadTraducible(
            texto=texto, parrafo=parrafo,
            hyperlinks=links, notas=notas, base_rPr=base_rPr,
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
_NOTA_PATTERN = re.compile(r"\u00ab(FN|EN):(\d+)\u00bb")
# Patrón que encuentra cualquier marcador (link o nota)
_CUALQUIER_MARCADOR = re.compile(r"\u00ab(?:\d+:.*?|(?:FN|EN):\d+)\u00bb")


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


def _crear_run_nota(info: NotaInfo) -> OxmlElement:
    """Crea un elemento w:r con referencia a nota al pie o final."""
    run_el = OxmlElement("w:r")
    if info.rPr is not None:
        run_el.append(deepcopy(info.rPr))
    tag = "w:footnoteReference" if info.tipo == "footnote" else "w:endnoteReference"
    ref_el = OxmlElement(tag)
    ref_el.set(qn("w:id"), info.nota_id)
    run_el.append(ref_el)
    return run_el


def _aplicar_estilo_link(run_el: OxmlElement):
    """Aplica color azul y subrayado a un run de hipervínculo."""
    rPr = run_el.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        run_el.insert(0, rPr)

    # Color azul estándar de hyperlinks
    color_el = rPr.find(qn("w:color"))
    if color_el is None:
        color_el = OxmlElement("w:color")
        rPr.append(color_el)
    color_el.set(qn("w:val"), "0000FF")

    # Subrayado simple
    u_el = rPr.find(qn("w:u"))
    if u_el is None:
        u_el = OxmlElement("w:u")
        rPr.append(u_el)
    u_el.set(qn("w:val"), "single")


def _reconstruir_parrafo(parrafo: Paragraph, texto: str,
                         link_map: dict, nota_map: dict,
                         base_rPr: object):
    """Reconstruye el XML del párrafo con hipervínculos y notas preservados."""
    elem = parrafo._element

    # Limpiar todos los hijos excepto w:pPr (propiedades del párrafo)
    for child in list(elem):
        if child.tag != qn("w:pPr"):
            elem.remove(child)

    # Procesar texto: partir por marcadores y reconstruir secuencialmente
    last_end = 0
    for match in _CUALQUIER_MARCADOR.finditer(texto):
        # Texto plano antes del marcador
        plain = texto[last_end:match.start()]
        if plain:
            elem.append(_crear_run_element(plain, base_rPr))
        last_end = match.end()

        marcador = match.group()

        # ¿Es un link?
        link_match = _LINK_PATTERN.match(marcador)
        if link_match:
            link_idx = int(link_match.group(1))
            link_text = link_match.group(2)
            if link_idx in link_map:
                info = link_map[link_idx]
                hl_el = OxmlElement("w:hyperlink")
                if info.r_id:
                    hl_el.set(qn("r:id"), info.r_id)
                if info.anchor:
                    hl_el.set(qn("w:anchor"), info.anchor)
                link_rPr = info.rPr if info.rPr is not None else base_rPr
                link_run = _crear_run_element(link_text, link_rPr)
                _aplicar_estilo_link(link_run)
                hl_el.append(link_run)
                elem.append(hl_el)
            else:
                elem.append(_crear_run_element(link_text, base_rPr))
            continue

        # ¿Es una nota?
        nota_match = _NOTA_PATTERN.match(marcador)
        if nota_match:
            nota_idx = int(nota_match.group(2))
            if nota_idx in nota_map:
                elem.append(_crear_run_nota(nota_map[nota_idx]))

    # Texto plano restante después del último marcador
    if last_end < len(texto):
        remaining = texto[last_end:]
        if remaining:
            elem.append(_crear_run_element(remaining, base_rPr))


def aplicar_traducciones(unidades: list[UnidadTraducible]):
    """Reescribe los párrafos con las traducciones, preservando hipervínculos y notas."""
    for unidad in unidades:
        if not unidad.traduccion:
            continue

        parrafo = unidad.parrafo

        if unidad.hyperlinks or unidad.notas:
            _reconstruir_parrafo(
                parrafo, unidad.traduccion,
                unidad.hyperlinks, unidad.notas, unidad.base_rPr,
            )
        else:
            # Sin hipervínculos ni notas: lógica original (más segura, preserva formato)
            runs = parrafo.runs
            if not runs:
                continue
            runs[0].text = unidad.traduccion
            for run in runs[1:]:
                run.text = ""


def _aplicar_fuente_parrafos(parrafos: list[Paragraph], nombre_fuente: str,
                             tamano: int):
    """Aplica fuente y tamaño a todos los runs de una lista de párrafos."""
    for parrafo in parrafos:
        for run in parrafo.runs:
            run.font.name = nombre_fuente
            run.font.size = Pt(tamano)


def aplicar_fuente(doc: Document, nombre_fuente: str, tamano: int):
    """Aplica fuente y tamaño a todo el documento (cuerpo + tablas)."""
    _aplicar_fuente_parrafos(doc.paragraphs, nombre_fuente, tamano)
    for tabla in doc.tables:
        for fila in tabla.rows:
            for celda in fila.cells:
                _aplicar_fuente_parrafos(celda.paragraphs, nombre_fuente, tamano)


def guardar_docx(doc: Document, ruta_salida: Path):
    """Guarda el documento DOCX."""
    doc.save(str(ruta_salida))
