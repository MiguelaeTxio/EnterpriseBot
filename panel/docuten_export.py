# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/docuten_export.py
"""
H30 (S124), roadmap item 4. Builds the files Yolanda uploads by hand to
Docuten for a mass certified signature of one circular.

---

H30 (S124), punto 4 de la hoja de ruta. Prepara los archivos que
Yolanda sube a mano a Docuten para la firma certificada masiva de una
circular (solo las marcadas `requires_signature`; canal WhatsApp, firma
OTP, decisiones de Miguel Ángel). Tres archivos sueltos, nunca un ZIP:

- PDF de la circular YA con campos rellenables (Miguel Ángel: "las
  plantillas tienen que salir con los campos que cambian ya
  directamente"): cada variable que cambia por trabajador (sus datos,
  y la empresa y el administrador de SU empresa) es un campo de
  formulario con nombre fijo (`FIELD_MAP`). La obra y la fecha son las
  mismas para todo el envío y se escriben ya en el PDF.
- CSV de envío masivo según la guía oficial de Docuten ("Cómo incluir
  metadatos en un proceso de firma"): UTF-8, `;`, sin cabecera, una
  línea por trabajador: Nombre;Email;NIF;Móvil;OTP;S;es;WhatsApp y un
  metadato `campo=valor` por cada campo del PDF (rellenan los campos
  de la plantilla que se llaman igual).
- Hoja de pasos para Yolanda, con quién queda fuera y por qué.

Solo lectura de datos: no crea documentos ni acuses.
"""
import re

from django.utils import timezone

from document_explorer import naming_service

SIGNATURE_TYPE = "OTP"
SIGNER_ROLE = "S"
LANGUAGE = "es"
CHANNEL = "WhatsApp"
FILE_KINDS = ("pdf", "csv", "pasos")

# Variable de la circular -> (campo del PDF/CSV, ancho del campo en pt).
FIELD_MAP = {
    "trabajador.nombre_completo": ("nombre", 190),
    "trabajador.dni": ("dni", 80),
    "trabajador.num_seguridad_social": ("nss", 100),
    "trabajador.puesto": ("puesto", 150),
    "empresa.razon_social": ("empresa", 190),
    "empresa.cif": ("cif", 80),
    "empresa.direccion_fiscal": ("direccion_empresa", 230),
    "administrador.nombre_completo": ("administrador", 190),
    "administrador.dni": ("dni_administrador", 80),
}
_COMPANY_FIELDS = {"empresa", "cif", "direccion_empresa"}
_ADMIN_FIELDS = {"administrador", "dni_administrador"}
_OBRA_TOKEN_RE = re.compile(r"\{\{obra\.[a-z_]+\}\}")
_PENDING_TOKEN_RE = re.compile(r"\{\{[^}]+\}\}")
_MARKER = "ZZFLD%sZZ"


class DocutenExportError(Exception):
    """
    The circular cannot be prepared as requested.

    ---

    La circular no se puede preparar tal como se ha pedido.
    """


def full_name(person):
    """
    Given name and surnames, single-spaced.

    ---

    Nombre y apellidos con un solo espacio entre partes.
    """
    return " ".join(
        part for part in (
            person.given_name, person.first_surname, person.second_surname,
        ) if part
    )


def normalize_mobile(raw):
    """
    Return the 9-digit mobile number, or None if it is not one.

    ---

    Devuelve el móvil de 9 dígitos (sin espacios ni prefijo +34/0034),
    o None si no lo es. Así se guarda en la ficha (65 de 76 activos en
    S124); lo que no encaja se deja fuera, nunca se adivina.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("34"):
        digits = digits[2:]
    elif len(digits) == 13 and digits.startswith("0034"):
        digits = digits[4:]
    return digits if len(digits) == 9 else None


def _clean(value):
    """
    Remove CSV separators and line breaks from a field.

    ---

    Quita separadores `;` y saltos de línea de un campo.
    """
    return re.sub(r"[;\r\n]+", " ", value or "").strip()


def used_fields(content_html):
    """
    Fields of FIELD_MAP used by the circular, in FIELD_MAP order.

    ---

    Campos de `FIELD_MAP` que usa la circular, en orden fijo.
    """
    return [
        field for token, (field, _width) in FIELD_MAP.items()
        if "{{%s}}" % token in content_html
    ]


def uses_worksite(content_html):
    """
    Whether the circular has any {{obra.*}} variable.

    ---

    Si la circular lleva alguna variable de obra.
    """
    return bool(_OBRA_TOKEN_RE.search(content_html))


def _person_values(person):
    """
    Return (values, reason): field values for one worker, or why not.

    ---

    Devuelve (valores, motivo): el valor de cada campo para un
    trabajador, o por qué no se puede (empresa sin identificar...).
    """
    from document_explorer.epi_delivery_document_service import (
        resolve_company_fiscal_profile,
    )

    profile = resolve_company_fiscal_profile(person.employer_company)
    admin = profile.administrator if profile else None
    values = {
        "nombre": full_name(person),
        "dni": person.dni,
        "nss": person.ss_affiliation_number,
        "puesto": person.professional_category,
        "empresa": profile.legal_name if profile else "",
        "cif": profile.tax_id if profile else "",
        "direccion_empresa": profile.fiscal_address if profile else "",
        "administrador": full_name(admin) if admin else "",
        "dni_administrador": admin.dni if admin else "",
    }
    return values, profile, admin


def build_csv(people, fields):
    """
    Return (csv_text, included, excluded).

    ---

    Devuelve (texto CSV, incluidas, excluidas). `excluded` es una lista
    de (persona, motivo): sin móvil válido no hay envío por WhatsApp, y
    sin empresa/administrador identificados no se pueden rellenar sus
    campos.
    """
    needs_company = bool(_COMPANY_FIELDS.intersection(fields))
    needs_admin = bool(_ADMIN_FIELDS.intersection(fields))
    lines, included, excluded = [], [], []
    for person in people:
        mobile = normalize_mobile(person.phone)
        if not (person.phone or "").strip():
            excluded.append((person, "sin móvil"))
            continue
        if mobile is None:
            excluded.append((
                person, "móvil no válido (%s)" % person.phone.strip(),
            ))
            continue
        values, profile, admin = _person_values(person)
        if (needs_company or needs_admin) and profile is None:
            excluded.append((
                person, "empresa sin identificar (%s)" % (
                    person.employer_company or "vacía",
                ),
            ))
            continue
        if needs_admin and admin is None:
            excluded.append((
                person, "la empresa %s no tiene administrador"
                % profile.legal_name,
            ))
            continue
        name = _clean(values["nombre"])
        dni = _clean(person.dni)
        line = [
            name, _clean(person.email), dni, mobile, SIGNATURE_TYPE,
            SIGNER_ROLE, LANGUAGE, CHANNEL,
        ]
        line += ["%s=%s" % (field, _clean(values[field])) for field in fields]
        lines.append(";".join(line))
        included.append((person, values))
    return "\r\n".join(lines) + "\r\n", included, excluded


def render_circular_html(document_type, worksite=None):
    """
    Circular HTML with a marker where each worker field goes.

    ---

    HTML de la circular con el mismo membrete y formato que "Generar
    documento": fecha de hoy y obra elegida ya escritas, y un marcador
    en cada sitio donde va un campo del trabajador (`build_pdf` lo
    convierte en campo rellenable).
    """
    from panel.views_circulars_h31 import (
        _get_letterhead_logo_data_uri, _render_document_variables,
        is_letter_format,
    )

    body = _render_document_variables(
        document_type.content_html, worksite=worksite,
    )
    for token, (field, width) in FIELD_MAP.items():
        body = body.replace(
            "{{%s}}" % token,
            '<span style="display:inline-block;min-width:%dpt;">%s</span>'
            % (width, _MARKER % field),
        )
    letter_format = is_letter_format(document_type.content_html)
    logo = _get_letterhead_logo_data_uri() if letter_format else None
    logo_html = (
        '<div style="text-align:center;margin-bottom:12px;">'
        '<img src="%s" style="max-height:70px;"></div>' % logo
        if logo else ""
    )
    heading = "" if letter_format else "<h1>%s</h1>" % document_type.label
    return (
        "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
        "<style>"
        "body{font-family:Arial,sans-serif;font-size:11pt;margin:2.5cm 2cm}"
        "h1{font-size:14pt;margin-bottom:18px}"
        "</style></head><body>%s%s%s</body></html>"
    ) % (logo_html, heading, body)


def build_pdf(html):
    """
    Render the HTML and turn every marker into a fillable text field.

    ---

    Renderiza el HTML (WeasyPrint) y cambia cada marcador por un campo
    de texto rellenable con el nombre del campo (PyMuPDF): el marcador
    se borra y el campo queda encima, del ancho reservado en el HTML.
    Un campo repetido (el nombre en el texto y en la firma) lleva el
    mismo nombre en todos sus sitios, así Docuten lo rellena igual.
    """
    import fitz
    import weasyprint

    doc = fitz.open(
        stream=weasyprint.HTML(string=html).write_pdf(), filetype="pdf",
    )
    widths = {field: width for field, width in FIELD_MAP.values()}
    placements = []
    for page in doc:
        for field in widths:
            for rect in page.search_for(_MARKER % field):
                placements.append((page.number, field, rect))
                page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions()
    for page_number, field, rect in placements:
        page = doc[page_number]
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = field
        widget.rect = fitz.Rect(
            rect.x0, rect.y0 - 1,
            min(rect.x0 + widths[field], page.rect.width - 20), rect.y1 + 1,
        )
        widget.text_fontsize = 10
        widget.field_value = ""
        page.add_widget(widget)
    return doc.tobytes()


def build_steps_text(document_type, fields, included, excluded, pdf_name,
                     csv_name, worksite, pending_tokens):
    """
    Step sheet for Yolanda.

    ---

    Hoja de pasos para Yolanda: subir la plantilla (una vez por
    circular), el envío masivo con el CSV, y quién queda fuera.
    """
    no_email = [person for person, _values in included if not person.email]
    empty = [
        (person, field) for person, values in included for field in fields
        if not (values[field] or "").strip()
    ]
    lines = [
        "PREPARACIÓN DE FIRMA CERTIFICADA EN DOCUTEN",
        "Circular: %s" % document_type.label,
        "Generado: %s" % timezone.localtime().strftime("%d/%m/%Y %H:%M"),
    ]
    if worksite is not None:
        lines.append("Obra: %s" % worksite.name)
    lines += [
        "Trabajadores en el CSV: %d -- fuera: %d" % (
            len(included), len(excluded),
        ),
        "Campos rellenables del PDF: %s" % (", ".join(fields) or "ninguno"),
        "",
        "Archivos descargados junto a este:",
        "  - %s: la circular, con los campos del trabajador ya puestos."
        % pdf_name,
        "  - %s: una línea por trabajador (firma OTP, aviso por "
        "WhatsApp)." % csv_name,
        "",
        "PASO 1 -- Subir la plantilla (solo la primera vez para esta "
        "circular)",
        "  1. En Docuten: Administrar > Plantillas PDF > Añadir.",
        "  2. Código y Descripción: %s." % document_type.label,
        "  3. Seleccionar fichero: %s. Docuten reconoce solo los campos "
        "(%s)." % (pdf_name, ", ".join(fields) or "ninguno"),
        "  4. Marca esos campos como obligatorios y guarda.",
        "  Si la circular cambia (texto u obra), vuelve a subir el PDF "
        "nuevo.",
        "",
        "PASO 2 -- Envío masivo",
        "  1. En Docuten: Enviar documento > Seleccionar plantilla > elige "
        "la del paso 1.",
        "  2. Pon un título (por ejemplo, el nombre de la circular).",
        "  3. Crear firma desde archivo > Examinar > elige %s." % csv_name,
        "  4. Revisa la tabla de procesos detectados: no debe marcar "
        "ningún error.",
        "  5. Guardar > Enviar. Cada trabajador recibe su propio proceso "
        "con sus datos ya puestos.",
        "",
    ]
    if pending_tokens:
        lines += [
            "AVISO: la circular lleva datos sin rellenar (%s). Revísala "
            "antes de subirla." % ", ".join(sorted(pending_tokens)),
            "",
        ]
    lines.append("QUIÉN QUEDA FUERA DEL CSV (%d)" % len(excluded))
    for person, reason in excluded:
        lines.append("  - %s (DNI %s): %s" % (
            full_name(person), person.dni, reason,
        ))
    if not excluded:
        lines.append("  Nadie.")
    lines += ["", "DATOS VACÍOS EN LA FICHA (%d)" % len(empty)]
    for person, field in empty:
        lines.append("  - %s: %s" % (full_name(person), field))
    if not empty:
        lines.append("  Ninguno.")
    lines += ["", "SIN EMAIL EN SU FICHA (%d)" % len(no_email)]
    for person in no_email:
        lines.append("  - %s (DNI %s)" % (full_name(person), person.dni))
    if no_email:
        lines.append(
            "  La guía de Docuten marca el email como obligatorio. Si la "
            "tabla del paso 2 da error en estas líneas, añade su email en "
            "la ficha y vuelve a preparar el envío."
        )
    else:
        lines.append("  Nadie.")
    return "\r\n".join(lines) + "\r\n"


def build_file(document_type, people, kind, worksite=None):
    """
    Return (filename, bytes, content_type, included, excluded).

    ---

    Devuelve UNO de los tres archivos, suelto (Miguel Ángel no quiere
    un ZIP que Yolanda tenga que descomprimir): `pdf`, `csv` o `pasos`.
    Lanza `DocutenExportError` si la circular usa obra y no se ha
    elegido ninguna.
    """
    content = document_type.content_html
    if uses_worksite(content) and worksite is None:
        raise DocutenExportError(
            "Esta circular lleva datos de obra: elige la obra."
        )
    fields = used_fields(content)
    suffix = "_%s" % naming_service._sanitize_token(worksite.name) \
        if worksite is not None else ""
    base = (
        naming_service._sanitize_token(document_type.label) or "CIRCULAR"
    ) + suffix
    pdf_name = "%s.pdf" % base
    csv_name = "%s_DOCUTEN.csv" % base
    csv_text, included, excluded = build_csv(people, fields)
    if kind == "csv":
        return (
            csv_name, csv_text.encode("utf-8-sig"), "text/csv",
            included, excluded,
        )
    html = render_circular_html(document_type, worksite=worksite)
    if kind == "pdf":
        return pdf_name, build_pdf(html), "application/pdf", included, \
            excluded
    steps = build_steps_text(
        document_type, fields, included, excluded, pdf_name, csv_name,
        worksite, set(_PENDING_TOKEN_RE.findall(html)),
    )
    return (
        "PASOS_DOCUTEN_%s.txt" % base, steps.encode("utf-8-sig"),
        "text/plain; charset=utf-8", included, excluded,
    )
