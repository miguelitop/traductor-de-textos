from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _es_wsl() -> bool:
    """Detecta si estamos corriendo dentro de WSL."""
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


_PATRON_WIN = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_PATRON_WSL_MNT = re.compile(r"^/mnt/([a-zA-Z])/(.*)$")


def normalizar_path_entrada(ruta: str | None) -> str | None:
    """Normaliza una ruta para que funcione en el entorno actual.
    En WSL, convierte rutas estilo Windows (C:\\... o C:/...) a /mnt/c/...
    En Windows nativo, convierte rutas estilo WSL (/mnt/c/...) a C:\\...
    Si la ruta ya está en el formato correcto, la devuelve tal cual.
    """
    if not ruta:
        return ruta
    if _es_wsl():
        m = _PATRON_WIN.match(ruta)
        if m:
            letra = m.group(1).lower()
            resto = m.group(2).replace("\\", "/")
            return f"/mnt/{letra}/{resto}"
    elif platform.system() == "Windows":
        m = _PATRON_WSL_MNT.match(ruta)
        if m:
            letra = m.group(1).upper()
            resto = m.group(2).replace("/", "\\")
            return f"{letra}:\\{resto}"
    return ruta



def _es_exe_windows(ruta: str) -> bool:
    """Determina si un ejecutable es un .exe de Windows."""
    return ruta.lower().endswith(".exe")


def _ruta_para_exe(ruta: Path, exe_es_windows: bool) -> str:
    """Convierte una ruta al formato que necesita el ejecutable.
    Si estamos en WSL usando un .exe de Windows, convierte a ruta Windows.
    En cualquier otro caso, devuelve la ruta tal cual.
    """
    if not (_es_wsl() and exe_es_windows):
        return str(ruta)
    resultado = subprocess.run(
        ["wslpath", "-w", str(ruta)],
        capture_output=True, text=True,
    )
    if resultado.returncode == 0:
        return resultado.stdout.strip()
    return str(ruta)


def encontrar_calibre() -> str | None:
    """Busca el ejecutable ebook-convert de Calibre en el sistema."""
    ruta = shutil.which("ebook-convert")
    if ruta:
        return ruta
    if platform.system() == "Windows":
        rutas_fallback = [
            r"C:\Program Files\Calibre2\ebook-convert.exe",
            r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
        ]
    elif _es_wsl():
        rutas_fallback = [
            "/mnt/c/Program Files/Calibre2/ebook-convert.exe",
            "/mnt/c/Program Files (x86)/Calibre2/ebook-convert.exe",
        ]
    elif platform.system() == "Darwin":
        rutas_fallback = [
            "/Applications/calibre.app/Contents/MacOS/ebook-convert",
        ]
    else:
        rutas_fallback = []
    for ruta in rutas_fallback:
        if Path(ruta).exists():
            return ruta
    return None


def encontrar_libreoffice() -> str | None:
    """Busca el ejecutable de LibreOffice en el sistema."""
    for nombre in ("soffice", "libreoffice"):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    if platform.system() == "Windows":
        rutas_fallback = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
    elif _es_wsl():
        rutas_fallback = [
            "/mnt/c/Program Files/LibreOffice/program/soffice.exe",
            "/mnt/c/Program Files (x86)/LibreOffice/program/soffice.exe",
        ]
    elif platform.system() == "Darwin":
        rutas_fallback = [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        ]
    else:
        rutas_fallback = []
    for ruta in rutas_fallback:
        if Path(ruta).exists():
            return ruta
    return None


def convertir_a_docx(ruta: Path, dir_tmp: Path) -> Path:
    """Convierte un archivo a DOCX usando LibreOffice headless.
    Copia el archivo a un temporal con nombre limpio para evitar problemas
    con caracteres especiales (punto y coma, etc.) en la ruta.
    Devuelve la ruta al DOCX generado.
    """
    soffice = encontrar_libreoffice()
    if not soffice:
        print("❌ LibreOffice no encontrado.")
        print("   Instalalo con:")
        print("     Ubuntu/Debian: sudo apt install libreoffice")
        print("     Windows: https://www.libreoffice.org/download/")
        sys.exit(1)

    dir_tmp.mkdir(parents=True, exist_ok=True)

    # Copiar a nombre limpio para evitar problemas con caracteres especiales
    nombre_limpio = "entrada" + ruta.suffix
    ruta_limpia = dir_tmp / nombre_limpio
    shutil.copy2(ruta, ruta_limpia)

    # Si soffice es de Windows (corriendo desde WSL), convertir paths
    soffice_win = _es_exe_windows(soffice)
    arg_outdir = _ruta_para_exe(dir_tmp, soffice_win)
    arg_entrada = _ruta_para_exe(ruta_limpia, soffice_win)

    print(f"🔄 Convirtiendo {ruta.name} a DOCX con LibreOffice...")
    cmd = [soffice, "--headless"]
    # HTML necesita infilter explícito para abrirse como Writer y no como Web document
    if ruta.suffix.lower() in (".html", ".htm"):
        cmd.append('--infilter=HTML (StarWriter)')
    cmd.extend(["--convert-to", "docx", "--outdir", arg_outdir, arg_entrada])
    resultado = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if resultado.returncode != 0:
        print(f"❌ Error al convertir: {resultado.stderr}")
        sys.exit(1)

    docx_salida = dir_tmp / "entrada.docx"
    if not docx_salida.exists():
        # Buscar cualquier .docx generado como fallback
        docx_files = list(dir_tmp.glob("*.docx"))
        if docx_files:
            docx_salida = docx_files[0]
        else:
            print(f"❌ No se generó el archivo DOCX esperado.")
            print(f"   stdout: {resultado.stdout}")
            print(f"   stderr: {resultado.stderr}")
            print(f"   returncode: {resultado.returncode}")
            print(f"   Directorio temporal: {dir_tmp}")
            print(f"   Contenido: {list(dir_tmp.iterdir())}")
            sys.exit(1)

    print(f"   Convertido a DOCX exitosamente.")
    return docx_salida


def convertir_con_calibre(ruta: Path, dir_tmp: Path) -> Path:
    """Convierte un archivo (EPUB, PDF, etc.) a DOCX usando Calibre (ebook-convert).
    Devuelve la ruta al DOCX generado.
    """
    ebook_convert = encontrar_calibre()
    if not ebook_convert:
        print("❌ Calibre (ebook-convert) no encontrado.")
        print("   Instalalo desde: https://calibre-ebook.com/download")
        sys.exit(1)

    dir_tmp.mkdir(parents=True, exist_ok=True)

    # Copiar a nombre limpio para evitar problemas con caracteres especiales
    nombre_limpio = "entrada" + ruta.suffix
    ruta_limpia = dir_tmp / nombre_limpio
    shutil.copy2(ruta, ruta_limpia)

    docx_salida = dir_tmp / "entrada.docx"

    # Si ebook-convert es de Windows (corriendo desde WSL), convertir paths
    es_win = _es_exe_windows(ebook_convert)
    arg_entrada = _ruta_para_exe(ruta_limpia, es_win)
    arg_salida = _ruta_para_exe(docx_salida, es_win)

    print(f"🔄 Convirtiendo {ruta.name} a DOCX con Calibre...")
    resultado = subprocess.run(
        [ebook_convert, arg_entrada, arg_salida],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if resultado.returncode != 0:
        print(f"❌ Error al convertir: {resultado.stderr}")
        sys.exit(1)

    if not docx_salida.exists():
        print(f"❌ No se generó el archivo DOCX esperado.")
        print(f"   Salida de Calibre: {resultado.stdout}")
        sys.exit(1)

    print(f"   Convertido a DOCX exitosamente.")
    return docx_salida
