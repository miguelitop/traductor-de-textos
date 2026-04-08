#!/usr/bin/env python3
"""
Traduce documentos entre idiomas usando Ollama.
Soporta DOCX (preservando formato), PDF, RTF, DOC, ODT (vía LibreOffice),
EPUB (nativo, preservando imágenes y estilos) y HTML.

Uso:
    python traductor-eng-sp.py libro.docx                          # selector interactivo de idiomas
    python traductor-eng-sp.py libro.epub --de-idioma en --a-idioma es  # inglés → español directo
    python traductor-eng-sp.py libro.pdf --de-idioma fr --a-idioma de  # francés → alemán
"""

import argparse
import shutil
import sys
import tempfile
from datetime import datetime
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

from .config import (MODELO_DEFAULT, CHUNK_PALABRAS, PAUSA_ENTRE_CHUNKS,
                     FUENTE_DEFAULT, TAMANO_FUENTE_DEFAULT)
from .chunker import dividir_en_chunks
from .converter import convertir_a_docx, convertir_con_calibre
from .docx_handler import (extraer_unidades, aplicar_traducciones, aplicar_fuente,
                           guardar_docx)
from .epub_handler import (abrir_epub, extraer_capitulos, aplicar_traducciones_epub, guardar_epub,
                           exportar_revision, importar_revision)
from .html_handler import (parsear_html, extraer_nodos_texto, aplicar_traducciones_html,
                            serializar_html, agrupar_nodos, juntar_grupo, separar_grupo)
from .idiomas import seleccionar_idioma, idioma_por_codigo, _IDIOMAS_POR_CODIGO
from .translator import traducir_chunks

FORMATOS_SOPORTADOS = {".docx", ".pdf", ".rtf", ".doc", ".odt", ".epub", ".html", ".htm"}


def _imprimir_duracion(inicio: datetime):
    """Imprime fecha/hora de fin y duración del proceso."""
    fin = datetime.now()
    duracion = fin - inicio
    horas, resto = divmod(int(duracion.total_seconds()), 3600)
    minutos, segundos = divmod(resto, 60)
    partes = []
    if horas:
        partes.append(f"{horas}h")
    if minutos:
        partes.append(f"{minutos}m")
    partes.append(f"{segundos}s")
    print(f"⏱️  Fin:    {fin.strftime('%Y-%m-%d %H:%M:%S')}  (duración: {' '.join(partes)})")


def guardar_reporte_sospechosos(ruta_salida: Path, sospechosos: list[dict]) -> Path | None:
    """Guarda un reporte de traducciones sospechosas junto al archivo de salida.
    Devuelve la ruta del reporte o None si no hay sospechosos.
    """
    if not sospechosos:
        return None
    ruta_reporte = ruta_salida.with_name(ruta_salida.stem + "_sospechosos.txt")
    lineas = [f"Reporte de traducciones sospechosas — {ruta_salida.name}", "=" * 60, ""]
    for s in sospechosos:
        ref = s.get("referencia", f"Chunk {s['chunk']}")
        lineas.append(f"👁️  {ref}")
        lineas.append(f"   Anomalías: {', '.join(s['anomalias'])}")
        lineas.append(f"   Original:    {s['original']}...")
        lineas.append(f"   Traducción:  {s['traduccion']}...")
        lineas.append("")
    lineas.append(f"Total: {len(sospechosos)} bloque(s) sospechoso(s)")
    ruta_reporte.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_reporte


def verificar_modelo(modelo: str, actualizar: bool = False):
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
    elif actualizar:
        print(f"🔄 Buscando actualizaciones para '{modelo}'...")
        hubo_descarga = False
        for progreso in ollama.pull(modelo, stream=True):
            status = progreso.get("status", "")
            total = progreso.get("total")
            completed = progreso.get("completed")
            if status.startswith("pulling") and total and completed is not None and completed < total:
                hubo_descarga = True
        if hubo_descarga:
            print(f"   ✅ Modelo '{modelo}' actualizado a la última versión.")
        else:
            print(f"   ✅ '{modelo}' ya está en la última versión.")


def main():
    parser = argparse.ArgumentParser(
        description="Traduce documentos entre idiomas usando Ollama"
    )
    parser.add_argument("entrada", nargs="?", default=None,
                        help="Archivo de entrada (DOCX, PDF, RTF, DOC, ODT, EPUB)")
    parser.add_argument(
        "--de-idioma", default=None, metavar="CÓDIGO",
        help="Idioma de origen (código de 2 letras, ej: en). Si se omite, selector interactivo"
    )
    parser.add_argument(
        "--a-idioma", default=None, metavar="CÓDIGO",
        help="Idioma de destino (código de 2 letras, ej: es). Si se omite, selector interactivo"
    )
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
        help="Archivo de salida (default: <entrada>_<destino>.<ext>)"
    )
    parser.add_argument(
        "--fuente", default=None,
        help=f"Fuente para el documento de salida (default: conservar original, ej: '{FUENTE_DEFAULT}')"
    )
    parser.add_argument(
        "--tamano-fuente", type=int, default=None,
        help=f"Tamaño de fuente en puntos (default: conservar original, ej: {TAMANO_FUENTE_DEFAULT})"
    )
    parser.add_argument(
        "--revisar", action="store_true",
        help="EPUB: exportar capítulos traducidos como HTMLs navegables para revisión manual"
    )
    parser.add_argument(
        "--desde-revision", default=None, metavar="CARPETA",
        help="EPUB: generar EPUB final usando HTMLs corregidos de una carpeta de revisión"
    )
    parser.add_argument(
        "--actualizar-modelo", action="store_true",
        help="Verificar si hay una versión más nueva del modelo en el registro de Ollama"
    )
    args = parser.parse_args()

    # Modo solo actualización de modelo (sin archivo de entrada)
    if args.actualizar_modelo and not args.entrada:
        verificar_modelo(args.modelo, actualizar=True)
        return

    if not args.entrada:
        parser.error("se requiere un archivo de entrada (o usar --actualizar-modelo solo)")

    ruta_entrada = Path(args.entrada)
    if not ruta_entrada.exists():
        print(f"❌ Archivo no encontrado: {ruta_entrada}")
        sys.exit(1)

    ext = ruta_entrada.suffix.lower()
    if ext not in FORMATOS_SOPORTADOS:
        print(f"❌ Formato no soportado: {ext}")
        print(f"   Formatos válidos: {', '.join(sorted(FORMATOS_SOPORTADOS))}")
        sys.exit(1)

    if (args.revisar or args.desde_revision) and ext != ".epub":
        print("❌ --revisar y --desde-revision solo funcionan con archivos EPUB.")
        sys.exit(1)

    # ── Rama --desde-revision (no necesita traducir) ──
    if args.desde_revision:
        dir_revision = Path(args.desde_revision)
        if not dir_revision.is_dir():
            print(f"❌ Carpeta no encontrada: {dir_revision}")
            sys.exit(1)

        ruta_salida = Path(args.salida) if args.salida else ruta_entrada.with_name(
            ruta_entrada.stem + "_traducido.epub"
        )

        print(f"📖 Leyendo EPUB original: {ruta_entrada.name}")

        print(f"📝 Aplicando revisión desde: {dir_revision}")
        contenidos = importar_revision(ruta_entrada, dir_revision)

        guardar_epub(ruta_entrada, ruta_salida, contenidos)
        print(f"\n✅ EPUB generado desde revisión.")
        print(f"   Guardado en: {ruta_salida}")
        return

    # ── Selección de idiomas ──
    # Validar códigos si se pasaron por CLI
    for arg_name, arg_val in [("--de-idioma", args.de_idioma), ("--a-idioma", args.a_idioma)]:
        if arg_val and arg_val not in _IDIOMAS_POR_CODIGO:
            print(f"❌ Código de idioma '{arg_val}' no reconocido para {arg_name}")
            sys.exit(1)

    idioma_origen = args.de_idioma or seleccionar_idioma("Idioma de origen:", default="en")
    idioma_destino = args.a_idioma or seleccionar_idioma("Idioma de destino:", default="es")

    if idioma_origen == idioma_destino:
        print("❌ El idioma de origen y destino no pueden ser el mismo.")
        sys.exit(1)

    nombre_origen = _IDIOMAS_POR_CODIGO[idioma_origen][0]  # nombre en inglés
    nombre_destino = _IDIOMAS_POR_CODIGO[idioma_destino][0]
    print(f"\n🌐 {idioma_por_codigo(idioma_origen)} → {idioma_por_codigo(idioma_destino)}")

    # Extensión de salida según formato
    if ext in (".epub",):
        ext_salida = f"_{idioma_destino}.epub"
    elif ext in (".html", ".htm"):
        ext_salida = f"_{idioma_destino}.docx"
    else:
        ext_salida = f"_{idioma_destino}.docx"

    ruta_salida = Path(args.salida) if args.salida else ruta_entrada.with_name(
        ruta_entrada.stem + ext_salida
    )

    inicio = datetime.now()
    print(f"\n⏱️  Inicio: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")

    verificar_modelo(args.modelo, actualizar=args.actualizar_modelo)

    print(f"📖 Leyendo: {ruta_entrada.name}")

    # ── Rama EPUB ──
    if ext == ".epub":
        book = abrir_epub(ruta_entrada)
        capitulos = extraer_capitulos(book)

        if not capitulos:
            print("❌ No se encontraron capítulos traducibles en el EPUB.")
            sys.exit(1)

        total_nodos = sum(len(c.nodos) for c in capitulos)
        total_palabras = sum(
            len(nodo.strip().split()) for c in capitulos for nodo in c.nodos
        )
        print(f"   {len(capitulos)} capítulos, {total_nodos} bloques de texto, {total_palabras:,} palabras")

        errores_total = []
        sospechosos_total = []
        nodos_traducidos = 0
        contenidos_epub = {}

        for i, capitulo in enumerate(capitulos, 1):
            textos = [str(nodo).strip() for nodo in capitulo.nodos]
            print(f"\n   Capítulo {i}/{len(capitulos)}: {len(textos)} bloques de texto")

            # Traducir cada nodo como chunk independiente → correspondencia 1:1 garantizada
            traducciones_nodos, errores, sospechosos_cap = traducir_chunks(textos, args.modelo, PAUSA_ENTRE_CHUNKS,
                                                            idioma_origen, idioma_destino,
                                                            nombre_origen, nombre_destino)
            errores_total.extend(errores)
            for s in sospechosos_cap:
                s["referencia"] = f"Capítulo {i}, bloque {s['chunk']}"
            sospechosos_total.extend(sospechosos_cap)

            item_name, xhtml_bytes = aplicar_traducciones_epub(capitulo, traducciones_nodos)
            contenidos_epub[item_name] = xhtml_bytes
            nodos_traducidos += len(capitulo.nodos)

        if args.revisar:
            dir_revision = ruta_entrada.with_name(ruta_entrada.stem + "_revision")
            exportar_revision(book, capitulos, dir_revision)
            print(f"\n✅ Revisión exportada.")
            print(f"   Carpeta: {dir_revision}")
            print(f"   Abrí {dir_revision / 'index.html'} en el navegador para revisar.")
            print(f"   Cuando estés conforme, corré:")
            print(f"     python traductor-eng-sp.py {ruta_entrada.name} --desde-revision {dir_revision.name}")
        else:
            guardar_epub(ruta_entrada, ruta_salida, contenidos_epub)
            print(f"\n✅ Traducción completada.")
            print(f"   Guardado en: {ruta_salida}")

        print(f"   Capítulos: {len(capitulos)}, bloques traducidos: {nodos_traducidos}")
        if errores_total:
            print(f"   ⚠️  Chunks con error: {errores_total}")
        ruta_reporte = guardar_reporte_sospechosos(ruta_salida, sospechosos_total)
        if ruta_reporte:
            print(f"   👁️  {len(sospechosos_total)} bloque(s) con posible anomalía → {ruta_reporte.name}")
        _imprimir_duracion(inicio)
        return

    # ── Rama HTML ──
    if ext in (".html", ".htm"):
        contenido = ruta_entrada.read_bytes()
        soup = parsear_html(contenido)
        nodos = extraer_nodos_texto(soup)

        if not nodos:
            print("❌ No se encontró texto traducible en el HTML.")
            sys.exit(1)

        textos = [str(n).strip() for n in nodos]
        total_palabras = sum(len(t.split()) for t in textos)

        # Agrupar nodos en chunks para reducir llamadas a Ollama
        grupos = agrupar_nodos(textos, args.chunk_palabras)
        print(f"   {total_palabras:,} palabras, {len(textos)} bloques → {len(grupos)} chunks")

        chunks_agrupados = [juntar_grupo(textos, g) for g in grupos]
        traducciones_chunks, errores, sospechosos = traducir_chunks(chunks_agrupados, args.modelo, PAUSA_ENTRE_CHUNKS,
                                                            idioma_origen, idioma_destino,
                                                            nombre_origen, nombre_destino)

        # Desagrupar traducciones para recuperar correspondencia 1:1 con nodos
        traducciones_nodos = []
        for traduccion, grupo in zip(traducciones_chunks, grupos):
            traducciones_nodos.extend(separar_grupo(traduccion, len(grupo)))

        aplicar_traducciones_html(nodos, traducciones_nodos)

        # Limitar tamaño de imágenes para que no desborden la página en DOCX
        style_tag = soup.new_tag("style")
        style_tag.string = "img { max-width: 75%; height: auto; }"
        if soup.head:
            soup.head.append(style_tag)
        elif soup.html:
            head_tag = soup.new_tag("head")
            head_tag.append(style_tag)
            soup.html.insert(0, head_tag)

        # Guardar HTML traducido junto al original (para que los paths relativos
        # a imágenes/CSS de la carpeta asociada sigan funcionando) y convertir a DOCX.
        ruta_html_tmp = ruta_entrada.parent / (ruta_entrada.stem + f"_tmp_{idioma_destino}.html")
        try:
            ruta_html_tmp.write_text(serializar_html(soup), encoding="utf-8")

            dir_tmp = Path(tempfile.mkdtemp(prefix="traductor_"))
            ruta_docx = convertir_a_docx(ruta_html_tmp, dir_tmp)

            ruta_salida = Path(args.salida) if args.salida else ruta_entrada.with_name(
                ruta_entrada.stem + f"_{idioma_destino}.docx"
            )
            shutil.copy2(ruta_docx, ruta_salida)

            print(f"\n✅ Traducción completada.")
            print(f"   Guardado en: {ruta_salida}")
            if errores:
                print(f"   ⚠️  Chunks con error: {errores}")
            ruta_reporte = guardar_reporte_sospechosos(ruta_salida, sospechosos)
            if ruta_reporte:
                print(f"   👁️  {len(sospechosos)} chunk(s) con posible anomalía → {ruta_reporte.name}")
            _imprimir_duracion(inicio)
        finally:
            if ruta_html_tmp.exists():
                ruta_html_tmp.unlink()
            if dir_tmp.exists():
                shutil.rmtree(dir_tmp, ignore_errors=True)
        return

    # ── Rama DOCX / PDF / otros (vía conversión) ──
    dir_tmp = None
    if ext == ".docx":
        ruta_docx = ruta_entrada
    elif ext == ".pdf":
        dir_tmp = Path(tempfile.mkdtemp(prefix="traductor_"))
        ruta_docx = convertir_con_calibre(ruta_entrada, dir_tmp)
    else:
        dir_tmp = Path(tempfile.mkdtemp(prefix="traductor_"))
        ruta_docx = convertir_a_docx(ruta_entrada, dir_tmp)

    try:
        doc, unidades = extraer_unidades(ruta_docx)

        if not unidades:
            print("❌ No se encontraron unidades de texto traducibles.")
            sys.exit(1)

        textos = [u.texto for u in unidades]
        texto_completo = "\n".join(textos)
        total_palabras = len(texto_completo.split())
        chunks = dividir_en_chunks(texto_completo, args.chunk_palabras)

        print(f"   {total_palabras:,} palabras → {len(chunks)} chunks de ~{args.chunk_palabras} palabras c/u")
        tiempo_estimado = len(chunks) * 10
        mins = tiempo_estimado // 60
        print(f"   Tiempo estimado: ~{mins} minutos\n")

        traducciones, errores, sospechosos = traducir_chunks(chunks, args.modelo, PAUSA_ENTRE_CHUNKS,
                                                    idioma_origen, idioma_destino,
                                                    nombre_origen, nombre_destino)

        texto_traducido = "\n".join(traducciones)
        parrafos_traducidos = [p.strip() for p in texto_traducido.split("\n") if p.strip()]

        for i, unidad in enumerate(unidades):
            if i < len(parrafos_traducidos):
                unidad.traduccion = parrafos_traducidos[i]
            else:
                unidad.traduccion = unidad.texto

        aplicar_traducciones(unidades)
        if args.fuente or args.tamano_fuente:
            fuente = args.fuente or FUENTE_DEFAULT
            tamano = args.tamano_fuente or TAMANO_FUENTE_DEFAULT
            aplicar_fuente(doc, fuente, tamano)
        guardar_docx(doc, ruta_salida)

        print(f"\n✅ Traducción completada.")
        print(f"   Guardado en: {ruta_salida}")
        print(f"   Unidades traducidas: {len(unidades)}")
        print(f"   Chunks procesados: {len(chunks) - len(errores)}/{len(chunks)}")
        if errores:
            print(f"   ⚠️  Chunks con error (revisar manualmente): {errores}")
        ruta_reporte = guardar_reporte_sospechosos(ruta_salida, sospechosos)
        if ruta_reporte:
            print(f"   👁️  {len(sospechosos)} chunk(s) con posible anomalía → {ruta_reporte.name}")
        _imprimir_duracion(inicio)

    finally:
        if dir_tmp and dir_tmp.exists():
            shutil.rmtree(dir_tmp, ignore_errors=True)
