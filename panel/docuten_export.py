# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/docuten_export.py
"""
H30 (S124), roadmap item 4. Builds the material Yolanda uploads by hand
to Docuten for a mass signature of one circular.

---

H30 (S124), punto 4 de la hoja de ruta. Prepara el material que
Yolanda sube a mano a Docuten para firmar una circular en envío masivo
(decisiones de Miguel Ángel: canal WhatsApp, firma OTP):

- PDF genérico de la circular (mismo render con membrete que "Generar
  documento"), con los huecos del trabajador en blanco para situar ahí
  los campos editables `nombre` y `dni`.
- CSV de envío masivo según la guía oficial de Docuten ("Cómo incluir
  metadatos en un proceso de firma"): UTF-8, separador `;`, sin
  cabecera, una línea por persona: Nombre;Email;NIF;Móvil;OTP;S;es;
  WhatsApp y los metadatos `nombre=` y `dni=` (rellenan los campos de
  la plantilla editable que se llamen igual).
- Hoja de pasos para Yolanda, con quién queda fuera y por qué.

Solo lectura de datos: no crea documentos ni acuses.
"""
import io
import re
import zipfile

from django.utils import timezone

from document_explorer import naming_service

SIGNATURE_TYPE = "OTP"
SIGNER_ROLE = "S"
LANGUAGE = "es"
CHANNEL = "WhatsApp"
WORKER_BLANK = "______________________________"
_WORKER_TOKENS = ("{{trabajador.nombre_completo}}", "{{trabajador.dni}}")
_PENDING_TOKEN_RE = re.compile(r"\{\{[^}]+\}\}")


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


def build_csv(people):
    """
    Return (csv_text, included, excluded).

    ---

    Devuelve (texto CSV, incluidas, excluidas). `excluded` es una lista
    de (persona, motivo); sin móvil válido no hay envío por WhatsApp.
    """
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
        name = _clean(full_name(person))
        dni = _clean(person.dni)
        lines.append(";".join([
            name, _clean(person.email), dni, mobile, SIGNATURE_TYPE,
            SIGNER_ROLE, LANGUAGE, CHANNEL,
            "nombre=%s" % name, "dni=%s" % dni,
        ]))
        included.append(person)
    return "\r\n".join(lines) + "\r\n", included, excluded


def render_circular_html(document_type):
    """
    Generic circular HTML with blank worker fields.

    ---

    HTML genérico de la circular: mismo membrete y formato que
    "Generar documento", con fecha de hoy y los datos del trabajador
    en blanco (ahí van los campos editables de la plantilla).
    """
    from panel.views_circulars_h31 import (
        _get_letterhead_logo_data_uri, _render_document_variables,
        is_letter_format,
    )

    body = _render_document_variables(document_type.content_html)
    for token in _WORKER_TOKENS:
        body = body.replace(token, WORKER_BLANK)
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


def build_steps_text(document_type, included, excluded, pdf_name, csv_name,
                     pending_tokens):
    """
    Step sheet for Yolanda.

    ---

    Hoja de pasos para Yolanda: crear la plantilla editable (una vez
    por circular), el envío masivo con el CSV, y quién queda fuera.
    """
    no_email = [person for person in included if not person.email]
    lines = [
        "PREPARACIÓN DE ENVÍO MASIVO EN DOCUTEN",
        "Circular: %s" % document_type.label,
        "Generado: %s" % timezone.localtime().strftime("%d/%m/%Y %H:%M"),
        "Personas en el CSV: %d -- fuera: %d" % (
            len(included), len(excluded),
        ),
        "",
        "Contenido de este ZIP:",
        "  - %s: la circular, con el nombre y el DNI del trabajador en "
        "blanco." % pdf_name,
        "  - %s: una línea por trabajador (firma OTP, aviso por "
        "WhatsApp)." % csv_name,
        "  - Este documento.",
        "",
        "PASO 1 -- Crear la plantilla editable (solo la primera vez para "
        "esta circular)",
        "  1. Abre %s con Adobe Acrobat Pro (el programa que recomienda "
        "Docuten)." % pdf_name,
        "  2. Herramientas > Preparar formulario. Borra los campos que "
        "Acrobat proponga solo.",
        "  3. Añade un campo de texto sobre la raya del nombre y llámalo "
        "exactamente: nombre",
        "  4. Añade otro campo de texto sobre la raya del DNI y llámalo "
        "exactamente: dni",
        "     (en minúsculas, sin tildes ni espacios: tienen que llamarse "
        "igual que en el CSV).",
        "  5. Guarda el PDF.",
        "  6. En Docuten: Administrar > Plantillas PDF > Añadir. Código y "
        "Descripción: el nombre de la circular. Seleccionar fichero: el "
        "PDF guardado.",
        "  7. Docuten reconoce los campos nombre y dni. Márcalos como "
        "obligatorios y guarda.",
        "",
        "PASO 2 -- Envío masivo",
        "  1. En Docuten: Enviar documento > Seleccionar plantilla > elige "
        "la plantilla del paso 1.",
        "  2. Pon un título (por ejemplo, el nombre de la circular).",
        "  3. Pulsa Crear firma desde archivo > Examinar > elige %s."
        % csv_name,
        "  4. Revisa la tabla de procesos detectados: no debe marcar "
        "ningún error.",
        "  5. Guardar > Enviar. Cada trabajador recibe su propio proceso "
        "con su nombre y su DNI ya puestos.",
        "",
    ]
    if pending_tokens:
        lines += [
            "AVISO: la circular lleva datos sin rellenar que no son del "
            "trabajador (%s). Revísala antes de crear la plantilla."
            % ", ".join(sorted(pending_tokens)),
            "",
        ]
    lines.append("QUIÉN QUEDA FUERA DEL CSV (%d)" % len(excluded))
    if excluded:
        for person, reason in excluded:
            lines.append("  - %s (DNI %s): %s" % (
                full_name(person), person.dni, reason,
            ))
        lines.append(
            "  Para incluirles, añade su móvil en su ficha y vuelve a "
            "preparar el envío."
        )
    else:
        lines.append("  Nadie.")
    lines += ["", "SIN EMAIL EN SU FICHA (%d)" % len(no_email)]
    if no_email:
        for person in no_email:
            lines.append("  - %s (DNI %s)" % (full_name(person), person.dni))
        lines.append(
            "  La guía de Docuten marca el email como obligatorio. Si la "
            "tabla del paso 2 da error en estas líneas, añade su email en "
            "la ficha y vuelve a preparar el envío."
        )
    else:
        lines.append("  Nadie.")
    return "\r\n".join(lines) + "\r\n"


def build_zip(document_type, people):
    """
    Return (zip_bytes, included, excluded).

    ---

    Devuelve (bytes del ZIP, incluidas, excluidas).
    """
    import weasyprint

    base = naming_service._sanitize_token(document_type.label) or "CIRCULAR"
    pdf_name = "%s.pdf" % base
    csv_name = "%s_DOCUTEN.csv" % base
    html = render_circular_html(document_type)
    pending_tokens = set(_PENDING_TOKEN_RE.findall(html))
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()
    csv_text, included, excluded = build_csv(people)
    steps = build_steps_text(
        document_type, included, excluded, pdf_name, csv_name,
        pending_tokens,
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(pdf_name, pdf_bytes)
        archive.writestr(csv_name, csv_text.encode("utf-8-sig"))
        archive.writestr("PASOS_DOCUTEN.txt", steps.encode("utf-8-sig"))
    return buffer.getvalue(), included, excluded
