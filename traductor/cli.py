#!/usr/bin/env python3
"""
Traduce documentos de inglés a español usando Ollama + TranslateGemma.
Soporta DOCX (preservando formato), PDF, RTF, DOC, ODT (vía LibreOffice) y EPUB (vía Calibre).

Uso:
    python traductor-eng-sp.py libro.docx
    python traductor-eng-sp.py libro.pdf --modelo translategemma:12b
    python traductor-eng-sp.py libro.rtf --chunk-palabras 400 --salida mi_traduccion.docx
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

try:
    import ollama
except ImportError:
    print("❌ Falta instalar: pip install ollama")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("❌ Falta instalar: pip install tqdm")
    sys.exit(1)

from .config import MODELO_DEFAULT, CHUNK_PALABRAS, PAUSA_ENTRE_CHUNKS
from .chunker import dividir_en_chunks
from .converter import convertir_a_docx, convertir_con_calibre
from .docx_handler import extraer_unidades, aplicar_traducciones, guardar_docx
from .translator import traducir_chunks

FORMATOS_SOPORTADOS = {".docx", ".pdf", ".rtf", ".doc", ".odt", ".epub"}


def verificar_modelo(modelo: str):
    """Verifica que Ollama esté corriendo y el modelo disponible."""
    print(f"\n🔍 Verificando modelo '{modelo}' en Ollama...")
    try:
        modelos_disponibles = [m.model for m in ollama.list().models]
    except Exception:
        print("❌ No se puede conectar con Ollama. ¿Está corriendo? Probá: ollama serve")
        sys.exit(1)

    modelo_base = modelo.split(":")[0]
    if not any(modelo_base in m for m in modelos_disponibles):
        print(f"⚠️  Modelo '{modelo}' no encontrado localmente.")
        print(f"   Descargándolo ahora (puede tardar varios minutos)...")
        ollama.pull(modelo)


def main():
    parser = argparse.ArgumentParser(
        description="Traduce documentos de inglés a español usando Ollama + TranslateGemma"
    )
    parser.add_argument("entrada", help="Archivo de entrada (DOCX, PDF, RTF, DOC, ODT, EPUB)")
    parser.add_argument(
        "--modelo", default=MODELO_DEFAULT,
        help=f"Modelo Ollama a usar (default: {MODELO_DEFAULT})"
    )
    parser.add_argument(
        "--chunk-palabras", type=int, default=CHUNK_PALABRAS,
        help=f"Palabras por chunk (default: {CHUNK_PALABRAS})"
    )
    parser.add_argument(
        "--salida", default=None,
        help="Archivo DOCX de salida (default: <entrada>_es.docx)"
    )
    args = parser.parse_args()

    ruta_entrada = Path(args.entrada)
    if not ruta_entrada.exists():
        print(f"❌ Archivo no encontrado: {ruta_entrada}")
        sys.exit(1)

    ext = ruta_entrada.suffix.lower()
    if ext not in FORMATOS_SOPORTADOS:
        print(f"❌ Formato no soportado: {ext}")
        print(f"   Formatos válidos: {', '.join(sorted(FORMATOS_SOPORTADOS))}")
        sys.exit(1)

    ruta_salida = Path(args.salida) if args.salida else ruta_entrada.with_name(
        ruta_entrada.stem + "_es.docx"
    )

    verificar_modelo(args.modelo)

    # ── Obtener DOCX de trabajo ──
    dir_tmp = None
    if ext == ".docx":
        ruta_docx = ruta_entrada
    elif ext in (".epub", ".pdf"):
        dir_tmp = Path(tempfile.mkdtemp(prefix="traductor_"))
        ruta_docx = convertir_con_calibre(ruta_entrada, dir_tmp)
    else:
        dir_tmp = Path(tempfile.mkdtemp(prefix="traductor_"))
        ruta_docx = convertir_a_docx(ruta_entrada, dir_tmp)

    try:
        # ── Extraer unidades traducibles ──
        print(f"📖 Leyendo: {ruta_entrada.name}")
        doc, unidades = extraer_unidades(ruta_docx)

        if not unidades:
            print("❌ No se encontraron unidades de texto traducibles.")
            sys.exit(1)

        # ── Agrupar en chunks ──
        textos = [u.texto for u in unidades]
        texto_completo = "\n".join(textos)
        total_palabras = len(texto_completo.split())
        chunks = dividir_en_chunks(texto_completo, args.chunk_palabras)

        print(f"   {total_palabras:,} palabras → {len(chunks)} chunks de ~{args.chunk_palabras} palabras c/u")
        tiempo_estimado = len(chunks) * 10
        mins = tiempo_estimado // 60
        print(f"   Tiempo estimado: ~{mins} minutos\n")

        # ── Traducir chunks ──
        traducciones, errores = traducir_chunks(chunks, args.modelo, PAUSA_ENTRE_CHUNKS)

        # ── Redistribuir traducciones en las unidades originales ──
        texto_traducido = "\n".join(traducciones)
        parrafos_traducidos = [p.strip() for p in texto_traducido.split("\n") if p.strip()]

        # Mapear traducciones a unidades (1 a 1 por párrafo)
        for i, unidad in enumerate(unidades):
            if i < len(parrafos_traducidos):
                unidad.traduccion = parrafos_traducidos[i]
            else:
                unidad.traduccion = unidad.texto  # fallback: dejar original

        # ── Aplicar traducciones al documento y guardar ──
        aplicar_traducciones(unidades)
        guardar_docx(doc, ruta_salida)

        # ── Resumen final ──
        print(f"\n✅ Traducción completada.")
        print(f"   Guardado en: {ruta_salida}")
        print(f"   Unidades traducidas: {len(unidades)}")
        print(f"   Chunks procesados: {len(chunks) - len(errores)}/{len(chunks)}")
        if errores:
            print(f"   ⚠️  Chunks con error (revisar manualmente): {errores}")

    finally:
        # Limpiar archivos temporales
        if dir_tmp and dir_tmp.exists():
            shutil.rmtree(dir_tmp, ignore_errors=True)
