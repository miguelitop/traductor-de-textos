import platform
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath


def _es_wsl() -> bool:
    """Detecta si estamos corriendo dentro de WSL."""
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _es_soffice_windows(ruta_soffice: str) -> bool:
    """Determina si el ejecutable de soffice es un .exe de Windows."""
    return ruta_soffice.lower().endswith(".exe")


def _ruta_para_soffice(ruta: Path, soffice_es_windows: bool) -> str:
    """Convierte una ruta al formato que necesita soffice.
    Si estamos en WSL usando soffice de Windows, convierte a ruta Windows.
    En cualquier otro caso, devuelve la ruta tal cual.
    """
    if not (_es_wsl() and soffice_es_windows):
        return str(ruta)
    resultado = subprocess.run(
        ["wslpath", "-w", str(ruta)],
        capture_output=True, text=True,
    )
    if resultado.returncode == 0:
        return resultado.stdout.strip()
    return str(ruta)


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
    soffice_win = _es_soffice_windows(soffice)
    arg_outdir = _ruta_para_soffice(dir_tmp, soffice_win)
    arg_entrada = _ruta_para_soffice(ruta_limpia, soffice_win)

    print(f"🔄 Convirtiendo {ruta.name} a DOCX con LibreOffice...")
    resultado = subprocess.run(
        [soffice, "--headless", "--convert-to", "docx", "--outdir", arg_outdir, arg_entrada],
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
            print(f"   Salida de LibreOffice: {resultado.stdout}")
            sys.exit(1)

    print(f"   Convertido a DOCX exitosamente.")
    return docx_salida
