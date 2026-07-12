"""
Funciones para agrupar textos en chunks optimizando llamadas al traductor.
"""

from tqdm import tqdm

SEPARADOR = "\n||||\n"


def agrupar_nodos(textos: list[str], max_palabras: int) -> list[list[int]]:
    """Agrupa índices de nodos en chunks que no superen max_palabras.
    Devuelve lista de grupos, donde cada grupo es una lista de índices.
    """
    grupos = []
    grupo_actual = []
    palabras_actual = 0

    for i, texto in enumerate(textos):
        palabras = len(texto.split())
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
    """Separa una traducción agrupada en sus partes individuales."""
    partes = traduccion.split("||||")
    partes = [p.strip() for p in partes]
    # Si el modelo no respetó los separadores, devolver lo que haya
    if len(partes) != cantidad:
        tqdm.write(
            f"⚠️  separar_grupo: esperaba {cantidad} partes "
            f"pero se recibieron {len(partes)}. Verificar traducción."
        )
        # Fallback: si hay menos partes, rellenar con la última;
        # si hay más, truncar
        if len(partes) < cantidad:
            partes.extend([partes[-1] if partes else ""] * (cantidad - len(partes)))
        else:
            partes = partes[:cantidad]
    return partes
