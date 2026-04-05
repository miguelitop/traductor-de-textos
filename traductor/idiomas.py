"""
Lista de idiomas soportados y selector interactivo con búsqueda incremental.

Uso:
    from .idiomas import seleccionar_idioma, IDIOMAS, idioma_por_codigo

    codigo = seleccionar_idioma("Idioma de origen")  # → "en"
    nombre = idioma_por_codigo("en")                  # → "English / Inglés"
"""

from __future__ import annotations

import sys

# (código, nombre inglés, nombre nativo/español)
IDIOMAS: list[tuple[str, str, str]] = [
    ("ar", "Arabic", "Árabe"),
    ("bg", "Bulgarian", "Búlgaro"),
    ("ca", "Catalan", "Catalán"),
    ("cs", "Czech", "Checo"),
    ("da", "Danish", "Danés"),
    ("de", "German", "Alemán"),
    ("el", "Greek", "Griego"),
    ("en", "English", "Inglés"),
    ("es", "Spanish", "Español"),
    ("et", "Estonian", "Estonio"),
    ("fa", "Persian", "Persa"),
    ("fi", "Finnish", "Finlandés"),
    ("fr", "French", "Francés"),
    ("he", "Hebrew", "Hebreo"),
    ("hi", "Hindi", "Hindi"),
    ("hr", "Croatian", "Croata"),
    ("hu", "Hungarian", "Húngaro"),
    ("id", "Indonesian", "Indonesio"),
    ("it", "Italian", "Italiano"),
    ("ja", "Japanese", "Japonés"),
    ("ko", "Korean", "Coreano"),
    ("lt", "Lithuanian", "Lituano"),
    ("lv", "Latvian", "Letón"),
    ("ms", "Malay", "Malayo"),
    ("nl", "Dutch", "Holandés"),
    ("no", "Norwegian", "Noruego"),
    ("pl", "Polish", "Polaco"),
    ("pt", "Portuguese", "Portugués"),
    ("ro", "Romanian", "Rumano"),
    ("ru", "Russian", "Ruso"),
    ("sk", "Slovak", "Eslovaco"),
    ("sl", "Slovenian", "Esloveno"),
    ("sr", "Serbian", "Serbio"),
    ("sv", "Swedish", "Sueco"),
    ("th", "Thai", "Tailandés"),
    ("tr", "Turkish", "Turco"),
    ("uk", "Ukrainian", "Ucraniano"),
    ("vi", "Vietnamese", "Vietnamita"),
    ("zh", "Chinese", "Chino"),
]

_IDIOMAS_POR_CODIGO = {codigo: (en, es) for codigo, en, es in IDIOMAS}


def idioma_por_codigo(codigo: str) -> str:
    """Retorna 'English / Inglés' dado 'en'. Lanza KeyError si no existe."""
    en, es = _IDIOMAS_POR_CODIGO[codigo]
    return f"{en} / {es}"


def _filtrar(query: str) -> list[tuple[str, str, str]]:
    """Filtra idiomas que matcheen el query en código, nombre inglés o español."""
    q = query.lower()
    return [(c, en, es) for c, en, es in IDIOMAS
            if q in c.lower() or q in en.lower() or q in es.lower()]


def _selector_curses(titulo: str, default: str | None) -> str:
    """Selector interactivo con curses: teclear filtra, flechas navegan, Enter selecciona."""
    import curses

    def _run(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)

        query = ""
        seleccion = 0
        filtrados = _filtrar(query)

        # Pre-seleccionar el default
        if default:
            for i, (c, _, _) in enumerate(filtrados):
                if c == default:
                    seleccion = i
                    break

        while True:
            stdscr.clear()
            alto, ancho = stdscr.getmaxyx()
            lineas_visibles = alto - 4

            stdscr.addstr(0, 0, f" {titulo}", curses.A_BOLD)
            stdscr.addstr(1, 0, f" Buscar: {query}▏")

            if not filtrados:
                stdscr.addstr(3, 2, "(sin resultados)", curses.A_DIM)
            else:
                seleccion = max(0, min(seleccion, len(filtrados) - 1))

                # Scroll: mantener selección visible
                if seleccion < lineas_visibles // 2:
                    offset = 0
                else:
                    offset = seleccion - lineas_visibles // 2
                offset = max(0, min(offset, len(filtrados) - lineas_visibles))

                for i in range(offset, min(offset + lineas_visibles, len(filtrados))):
                    fila = 3 + (i - offset)
                    codigo, en, es = filtrados[i]
                    texto = f"  {codigo}  {en} / {es}"
                    if len(texto) > ancho - 1:
                        texto = texto[:ancho - 1]
                    if i == seleccion:
                        stdscr.addstr(fila, 0, texto, curses.color_pair(1))
                    else:
                        stdscr.addstr(fila, 0, texto)

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                seleccion = max(0, seleccion - 1)
            elif key == curses.KEY_DOWN:
                seleccion = min(len(filtrados) - 1, seleccion + 1)
            elif key in (curses.KEY_ENTER, 10, 13):
                if filtrados:
                    return filtrados[seleccion][0]
            elif key == 27:  # Escape
                return default or ""
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                query = query[:-1]
                filtrados = _filtrar(query)
                seleccion = 0
            elif 32 <= key <= 126:
                query += chr(key)
                filtrados = _filtrar(query)
                seleccion = 0

    return curses.wrapper(_run)


def seleccionar_idioma(titulo: str, default: str | None = None) -> str:
    """Muestra un selector interactivo de idiomas.

    Si la terminal no es interactiva, usa el default o pide input simple.
    """
    if default and default in _IDIOMAS_POR_CODIGO:
        default_label = idioma_por_codigo(default)
    else:
        default_label = None

    # Si no es terminal interactiva, input simple
    if not sys.stdin.isatty():
        if default:
            return default
        codigo = input(f"{titulo} (código de 2 letras): ").strip().lower()
        if codigo not in _IDIOMAS_POR_CODIGO:
            print(f"Código '{codigo}' no reconocido.")
            sys.exit(1)
        return codigo

    try:
        return _selector_curses(titulo, default)
    except Exception:
        # Fallback si curses falla
        if default:
            resp = input(f"{titulo} [{default} - {default_label}]: ").strip().lower()
            return resp if resp and resp in _IDIOMAS_POR_CODIGO else default
        codigo = input(f"{titulo} (código de 2 letras): ").strip().lower()
        if codigo not in _IDIOMAS_POR_CODIGO:
            print(f"Código '{codigo}' no reconocido.")
            sys.exit(1)
        return codigo
