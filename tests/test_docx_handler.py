"""Tests para las funciones de docx_handler.py."""

from docx import Document

from traductor.docx_handler import (
    _tokens_intactos,
    _link_traducible,
    aplicar_traducciones,
    asignar_traducciones_links,
    desagrupar_formatos,
    mergear_parrafos,
    recolectar_links_traducibles,
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


# --- Traducción del texto visible de los hipervínculos ---


def test_link_traducible_prosa():
    """Texto con palabras: se traduce."""
    assert _link_traducible("the official report") is True
    assert _link_traducible("Fig. 3") is True


def test_link_traducible_descarta_urls_y_numeros():
    """URLs, dominios, mails y numeración de citas no se traducen."""
    for texto in ("https://example.com/a", "www.example.com", "example.com/doc",
                  "info@example.com", "[12]", "3.2", "  "):
        assert _link_traducible(texto) is False, texto


def test_recolectar_links_traducibles_filtra():
    """Solo se recolectan los links con texto traducible."""
    unidad = UnidadTraducible(
        texto="⟦1⟧ y ⟦2⟧",
        parrafo="mock",
        hyperlinks={
            1: HyperlinkInfo(url="https://a.com", r_id="r1", texto="ver el informe"),
            2: HyperlinkInfo(url="https://b.com", r_id="r2", texto="www.b.com"),
        },
    )
    links = recolectar_links_traducibles([unidad])
    assert [l.texto for l in links] == ["ver el informe"]


def test_asignar_traducciones_links_ok():
    """Una traducción válida se guarda y es la que se reinserta."""
    link = HyperlinkInfo(url="https://a.com", r_id="r1", texto="official report")
    assert asignar_traducciones_links([link], ["informe oficial"]) == 0
    assert link.texto_final == "informe oficial"


def test_asignar_traducciones_links_descarta_sospechosas():
    """Salidas que no parecen texto de link dejan el original."""
    casos = [
        "",
        "linea uno\nlinea dos",
        "[ERROR DE TRADUCCIÓN EN CHUNK 3]\n\noficial",
        "informe oficial, que en este contexto se refiere al documento publicado",
    ]
    for traduccion in casos:
        link = HyperlinkInfo(url="https://a.com", r_id="r1", texto="official report")
        assert asignar_traducciones_links([link], [traduccion]) == 1, traduccion
        assert link.texto_final == "official report"


def test_mergear_parrafos_renumera_tokens_y_fusiona_mapas():
    """Al mergear, los tokens del segundo párrafo se corren y sus links se conservan."""
    doc = Document()
    p1, p2 = doc.add_paragraph("a"), doc.add_paragraph("b")
    u1 = UnidadTraducible(
        texto="según ⟦1⟧ el estudio",
        parrafo=p1,
        hyperlinks={1: HyperlinkInfo(url="https://a.com", r_id="r1", texto="Smith")},
    )
    u2 = UnidadTraducible(
        texto="citado en ⟦1⟧ y ⟦2⟧",
        parrafo=p2,
        hyperlinks={1: HyperlinkInfo(url="https://b.com", r_id="r2", texto="Jones")},
        notas={2: NotaInfo(tipo="footnote", nota_id="7")},
    )

    resultado = mergear_parrafos([u1, u2])

    assert len(resultado) == 1
    unido = resultado[0]
    assert unido.texto == "según ⟦1⟧ el estudio citado en ⟦2⟧ y ⟦3⟧"
    assert unido.hyperlinks[1].r_id == "r1"
    assert unido.hyperlinks[2].r_id == "r2"
    assert unido.notas[3].nota_id == "7"

    unido.traduccion = unido.texto
    assert _tokens_intactos(unido) is True


# --- desagrupar_formatos ---------------------------------------------------

def _parrafo_con_runs(runs_spec):
    """Crea un párrafo con runs [(texto, negrita, idioma_o_None, hint_o_None)]."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document()
    p = doc.add_paragraph()
    for texto, negrita, lang, hint in runs_spec:
        run = p.add_run(texto)
        run.bold = negrita or None
        rPr = run._element.get_or_add_rPr()
        if lang:
            el = OxmlElement("w:lang")
            el.set(qn("w:val"), lang)
            rPr.append(el)
        if hint:
            el = OxmlElement("w:rFonts")
            el.set(qn("w:hint"), hint)
            rPr.insert(0, el)
    return p


def _unidad(p):
    return UnidadTraducible(texto=p.text, parrafo=p)


def test_desagrupar_ignora_atributos_invisibles():
    """Runs que difieren solo en w:lang / rFonts hint quedan en una sola unidad."""
    p = _parrafo_con_runs([
        ("Explanation of the ", True, None, None),
        ("Resolution of the Central Committee ", True, "zh-CN", "eastAsia"),
        ("concerning Persevering", True, "en-US", None),
    ])
    assert len(desagrupar_formatos([_unidad(p)])) == 1


def test_desagrupar_no_corta_a_mitad_de_palabra():
    """Si el cambio de formato cae a mitad de palabra no se desagrupa."""
    p = _parrafo_con_runs([
        ("on Certain Major Issues c", True, None, None),
        ("oncerning the matter at hand", False, None, None),
    ])
    assert len(desagrupar_formatos([_unidad(p)])) == 1


def test_desagrupar_no_fragmenta_en_pedazos_chicos():
    """Varios grupos de pocas palabras: se traduce el párrafo entero."""
    p = _parrafo_con_runs([
        ("Communist ", False, None, None),
        ("Party ", True, None, None),
        ("of China on certain issues", False, None, None),
    ])
    assert len(desagrupar_formatos([_unidad(p)])) == 1


def test_desagrupar_etiqueta_en_negrita_y_espacios():
    """Etiqueta en negrita + texto normal: se separa y se conserva el espacio."""
    p = _parrafo_con_runs([
        ("Note: ", True, None, None),
        ("this is the body of the paragraph", False, None, None),
    ])
    unidades = desagrupar_formatos([_unidad(p)])
    assert [u.texto for u in unidades] == ["Note:", "this is the body of the paragraph"]
    unidades[0].traduccion = "Nota:"
    unidades[1].traduccion = "este es el cuerpo del párrafo"
    aplicar_traducciones(unidades)
    assert p.text == "Nota: este es el cuerpo del párrafo"
    assert p.runs[0].bold is True
