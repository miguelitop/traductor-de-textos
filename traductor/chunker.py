"""
Funciones para agrupar textos en chunks optimizando llamadas al traductor.
"""

from tqdm import tqdm

from .utils import contar_palabras_efectivas

SEPARADOR = "\n||||\n"


def agrupar_nodos(textos: list[str], max_palabras: int) -> list[list[int]]:
    """Agrupa índices de nodos en chunks que no superen max_palabras.
    Devuelve lista de grupos, donde cada grupo es una lista de índices.

    Usa contar_palabras_efectivas() para manejar correctamente idiomas sin
    espacios como chino, japonés y coreano (CJK).
    """
    grupos = []
    grupo_actual = []
    palabras_actual = 0

    for i, texto in enumerate(textos):
        palabras = contar_palabras_efectivas(texto)
        if palabras_actual + palabras > max_palabras and grupo_actual:
            grupos.append(grupo_actual)
            grupo_actual = [i]
            palabras_actual = palabras
        else:
            grupo_actual.append(i)
            palabras_actual += palabras

    if grupo_actual:
        grupos.append(grupo_actual)

    return grupos


def juntar_grupo(textos: list[str], indices: list[int]) -> str:
    """Une los textos de un grupo con el separador."""
    return SEPARADOR.join(textos[i] for i in indices)


def separar_grupo(traduccion: str, cantidad: int) -> list[str]:
    """Separa una traducción agrupada en sus partes individuales.

    Lanza ValueError si el modelo no respetó los separadores |||| y la
    discrepancia es grave (el fallback de replicar la última parte amplifica
    el error y produce docenas de párrafos repetidos).
    """
    partes = traduccion.split("||||")
    partes = [p.strip() for p in partes]
    if len(partes) != cantidad:
        tqdm.write(
            f"⚠️  separar_grupo: esperaba {cantidad} partes "
            f"pero se recibieron {len(partes)}. Verificar traducción."
        )
        # Si la discrepancia es pequeña (1-2 partes), usar fallback.
        # Si es grande, el modelo ignoró los separadores: propagar error
        # para que traducir_chunks reintente el chunk completo.
        if abs(len(partes) - cantidad) <= 2:
            if len(partes) < cantidad:
                partes.extend([partes[-1] if partes else ""] * (cantidad - len(partes)))
            else:
                partes = partes[:cantidad]
        else:
            raise ValueError(
                f"El modelo no respetó los separadores ||||: "
                f"se esperaban {cantidad} partes pero se recibieron {len(partes)}. "
                f"Reintentando chunk completo."
            )
    return partes
