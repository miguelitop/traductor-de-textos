"""Tests para las funciones de docx_handler.py."""

from traductor.docx_handler import (
    _tokens_intactos,
    UnidadTraducible,
    HyperlinkInfo,
    NotaInfo,
)


def test_tokens_intactos_correctos():
    """Tokens esperados y encontrados coinciden: True."""
    unidad = UnidadTraducible(
        texto="dummy",
        parrafo="mock",
        traduccion="texto ⟦1⟧ con enlace y nota ⟦2⟧",
        hyperlinks={1: HyperlinkInfo(url="https://example.com", r_id="r1")},
        notas={2: NotaInfo(tipo="footnote", nota_id="1")},
    )
    assert _tokens_intactos(unidad) is True


def test_tokens_intactos_faltante():
    """Falta un token esperado en la traducción: False."""
    unidad = UnidadTraducible(
        texto="dummy",
        parrafo="mock",
        traduccion="texto ⟦1⟧ sin la nota",
        hyperlinks={1: HyperlinkInfo(url="https://example.com", r_id="r1")},
        notas={2: NotaInfo(tipo="footnote", nota_id="1")},
    )
    assert _tokens_intactos(unidad) is False


def test_tokens_intactos_sobrante():
    """Aparece un token no esperado en la traducción: False."""
    unidad = UnidadTraducible(
        texto="dummy",
        parrafo="mock",
        traduccion="texto ⟦1⟧ con ⟦2⟧ y extra ⟦3⟧",
        hyperlinks={1: HyperlinkInfo(url="https://example.com", r_id="r1")},
        notas={2: NotaInfo(tipo="footnote", nota_id="1")},
    )
    assert _tokens_intactos(unidad) is False


def test_tokens_intactos_sin_tokens():
    """Sin tokens esperados ni en la traducción: True."""
    unidad = UnidadTraducible(
        texto="dummy",
        parrafo="mock",
        traduccion="texto plano sin tokens",
    )
    assert _tokens_intactos(unidad) is True


def test_tokens_intactos_solo_hyperlinks():
    """Solo hyperlinks, sin notas: True si coinciden."""
    unidad = UnidadTraducible(
        texto="dummy",
        parrafo="mock",
        traduccion="enlace ⟦1⟧ y otro ⟦2⟧",
        hyperlinks={
            1: HyperlinkInfo(url="https://a.com", r_id="r1"),
            2: HyperlinkInfo(url="https://b.com", r_id="r2"),
        },
    )
    assert _tokens_intactos(unidad) is True
