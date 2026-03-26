import shutil
import subprocess
import sys
from pathlib import Path


def encontrar_libreoffice() -> str | None:
    """Busca el ejecutable de LibreOffice en el sistema."""
    for nombre in ("soffice", "libreoffice"):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    # Rutas comunes en Windows (accesibles desde WSL)
    rutas_windows = [
        "/mnt/c/Program Files/LibreOffice/program/soffice.exe",
        "/mnt/c/Program Files (x86)/LibreOffice/program/soffice.exe",
    ]
    for ruta in rutas_windows:
        if Path(ruta).exists():
            return ruta
    return None


def convertir_a_docx(ruta: Path, dir_tmp: Path) -> Path:
    """Convierte un archivo a DOCX usando LibreOffice headless.
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

    print(f"🔄 Convirtiendo {ruta.name} a DOCX con LibreOffice...")
    resultado = subprocess.run(
        [soffice, "--headless", "--convert-to", "docx", "--outdir", str(dir_tmp), str(ruta)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if resultado.returncode != 0:
        print(f"❌ Error al convertir: {resultado.stderr}")
        sys.exit(1)

    docx_salida = dir_tmp / (ruta.stem + ".docx")
    if not docx_salida.exists():
        print(f"❌ No se generó el archivo DOCX esperado: {docx_salida}")
        print(f"   Salida de LibreOffice: {resultado.stdout}")
        sys.exit(1)

    print(f"   Convertido a: {docx_salida.name}")
    return docx_salida
