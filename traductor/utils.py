"""
Utilidades de sistema y rutas: detección de WSL, normalización de paths
Windows ↔ WSL, y helpers para ejecutables entre sistemas.
"""
from __future__ import annotations

import platform
import re
import subprocess
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
