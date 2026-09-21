# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/epi_delivery_document_service.py
"""
H31 (S113). Genera el documento PDF real de entrega de EPIs para una
persona -- reemplaza el proceso en papel real de la empresa (plantilla
con una X por EPI + firma) por un documento generado con la relación
exacta de EPIs que se le entregan a ESA persona en ESA entrega, en
prosa (nunca una X), dejando el hueco de firma en blanco para firma
física hasta que Docuten esté integrado (decisión explícita de Miguel
Ángel, S113 -- "el tema de la firma [...] lo dejamos aparcado").

Formato replicado de un documento real ya indexado en el sistema
(`EPIS 12-1-2021 JOSE LUIS ALVAREZ.docx`, tipo documental EPIS,
dominio PERSONAL) -- encabezado de empresa (CIF/dirección), datos de
la persona y categoría profesional, párrafo legal (Art. 29 Ley
31/1995, Art. 58.1 E.T.) y hueco de firma, verificado contra el
archivo real antes de escribir esta función, nunca inventado.

PyMuPDF puro, mismo criterio que `document_management.
pdf_merge_service.build_index_page` (sin reportlab, sin dependencia
nueva) -- paginación y ajuste de línea manuales.

---

Generates the real EPI-delivery PDF for one person -- see Spanish
docstring above for the full real-document context (S113).
"""
import io
import textwrap

import pymupdf

from document_explorer.models import CompanyFiscalProfile

_PAGE_WIDTH, _PAGE_HEIGHT = 595, 842  # A4 en puntos (72 dpi)
_MARGIN_TOP = 72
_MARGIN_BOTTOM = 56
_MARGIN_LEFT = 56
_LINE_HEIGHT = 15
_WRAP_WIDTH = 95

_LEGAL_PARAGRAPHS = [
    "Se me han entregado los equipos de protección individual arriba señalados.",
    (
        "Además se me ha informado, previamente al uso de los equipos, de "
        "los riesgos contra los que me protege, así como de las actividades "
        "u ocasiones en las que deben utilizarse. También se me ha "
        "informado de las instrucciones sobre la forma correcta de "
        "utilizarlos y mantenerlos."
    ),
    (
        "El trabajador deberá cumplir las obligaciones en materia de "
        "prevención de riesgos laborales las cuales se recogen en el Art. "
        "29 de la ley 31/1995 de lo contrario incurrirá en un "
        "incumplimiento laboral a los efectos previstos en el artículo "
        "58.1 del E.T.(R.D.1/1995) como son las siguientes:"
    ),
]

_LEGAL_BULLETS = [
    "Utilizar correctamente los equipos de protección individual.",
    (
        "Colocar el equipo de protección individual, después de su "
        "utilización en el lugar indicado para ello."
    ),
    (
        "Informar de inmediato a su superior jerárquico directo de su "
        "pérdida, defecto, anomalía o daño apreciado que a su juicio pueda "
        "entrañar una pérdida de su eficacia protectora."
    ),
]


def resolve_company_fiscal_profile(employer_company_text):
    """
    H31 (S113). Busca el `CompanyFiscalProfile` cuyo `name_aliases`
    contiene `employer_company_text` (comparación sin distinguir
    mayúsculas/minúsculas, espacios sobrantes ignorados). Devuelve
    `None` si no hay ninguno (texto vacío, o variante todavía sin
    confirmar por Miguel Ángel -- p. ej. "GRUALDI S.L") -- nunca
    adivina ni crea uno nuevo.
    """
    needle = (employer_company_text or "").strip().upper()
    if not needle:
        return None
    for profile in CompanyFiscalProfile.objects.all():
        aliases = {
            line.strip().upper()
            for line in profile.name_aliases.splitlines()
            if line.strip()
        }
        if needle in aliases:
            return profile
    return None


def build_epi_delivery_pdf_bytes(person, epi_labels, delivery_date, company_profile):
    """
    Construye el PDF de entrega -- una o más páginas A4. `epi_labels`
    ya viene resuelto por el llamador (los `EpiItemCatalog.label`
    realmente entregados en este lote, en el orden que se quiera
    mostrar). `company_profile` puede ser `None` (variante de empresa
    sin confirmar) -- en ese caso el documento se genera igual, sin
    las 3 líneas de encabezado de empresa.
    """
    doc = pymupdf.open()
    state = {"page": doc.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT), "y": _MARGIN_TOP}

    def ensure_space(extra=_LINE_HEIGHT):
        if state["y"] + extra > _PAGE_HEIGHT - _MARGIN_BOTTOM:
            state["page"] = doc.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
            state["y"] = _MARGIN_TOP

    def write_line(text, fontsize=10, bold=False, gap=None):
        ensure_space(_LINE_HEIGHT)
        state["page"].insert_text(
            (_MARGIN_LEFT, state["y"]), text, fontsize=fontsize,
            fontname="hebo" if bold else "helv",
        )
        state["y"] += gap if gap is not None else _LINE_HEIGHT * 1.3

    def blank_gap(factor=0.6):
        state["y"] += _LINE_HEIGHT * factor

    def write_paragraph(text, fontsize=10, width=_WRAP_WIDTH):
        for line in textwrap.wrap(text, width=width):
            write_line(line, fontsize=fontsize, gap=_LINE_HEIGHT * 1.15)
        blank_gap()

    if company_profile is not None:
        write_line("EMPRESA: %s" % company_profile.legal_name, bold=True)
        write_line("CIF: %s" % company_profile.tax_id)
        if company_profile.fiscal_address:
            write_line("DIRECCION: %s" % company_profile.fiscal_address)
        blank_gap()

    write_line("ENTREGA DE EPI'S", fontsize=14, bold=True)
    write_line("FECHA: %s" % delivery_date.strftime("%d/%m/%Y"))
    blank_gap()

    full_name = "%s %s, %s" % (
        person.first_surname, person.second_surname, person.given_name,
    )
    category_clause = (
        " y categoría profesional: %s," % person.professional_category
        if person.professional_category else ","
    )
    write_paragraph(
        "Se hace entrega a D./Dña. %s con D.N.I. %s%s los siguientes "
        "equipos de Protección Individual:" % (
            full_name, person.dni, category_clause,
        )
    )

    for label in epi_labels:
        write_line("- %s" % label, gap=_LINE_HEIGHT * 1.2)
    blank_gap()

    for paragraph in _LEGAL_PARAGRAPHS:
        write_paragraph(paragraph)

    for bullet in _LEGAL_BULLETS:
        wrapped = textwrap.wrap(bullet, width=_WRAP_WIDTH - 2)
        for i, line in enumerate(wrapped):
            prefix = "- " if i == 0 else "  "
            write_line(prefix + line, gap=_LINE_HEIGHT * 1.15)
    blank_gap(2)

    ensure_space(_LINE_HEIGHT * 3)
    write_line("Firma recibí del trabajador (EPIS)          Por la empresa:")
    write_line(
        "A fecha (%s)                                  Firma y Sello"
        % delivery_date.strftime("%d/%m/%Y")
    )

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    return output.getvalue()
