from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


@dataclass
class UnidadTraducible:
    """Representa un párrafo traducible con referencia a sus runs originales."""
    texto: str
    parrafo: Paragraph
    traduccion: str = ""


def _parrafo_tiene_imagen(parrafo: Paragraph) -> bool:
    """Detecta si un párrafo contiene imágenes inline."""
    for run in parrafo.runs:
        if run._element.findall(qn("w:drawing")):
            return True
        if run._element.findall(qn("w:pict")):
            return True
    return False


def _extraer_de_parrafos(parrafos: list[Paragraph]) -> list[UnidadTraducible]:
    """Extrae unidades traducibles de una lista de párrafos."""
    unidades = []
    for parrafo in parrafos:
        texto = parrafo.text.strip()
        if not texto:
            continue
        if _parrafo_tiene_imagen(parrafo):
            continue
        unidades.append(UnidadTraducible(texto=texto, parrafo=parrafo))
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


def aplicar_traducciones(unidades: list[UnidadTraducible]):
    """Reescribe los párrafos con las traducciones, preservando el formato del primer run."""
    for unidad in unidades:
        if not unidad.traduccion:
            continue

        parrafo = unidad.parrafo
        runs = parrafo.runs

        if not runs:
            continue

        # Poner toda la traducción en el primer run
        runs[0].text = unidad.traduccion

        # Vaciar los demás runs (preserva sus elementos XML/formato pero sin texto)
        for run in runs[1:]:
            run.text = ""


def guardar_docx(doc: Document, ruta_salida: Path):
    """Guarda el documento DOCX."""
    doc.save(str(ruta_salida))
