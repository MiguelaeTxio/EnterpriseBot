# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/machine_card.py
"""
Export of a cost centre's technical card: JPG, PNG, PDF, Word, HTML.

---

Exportación de la tarjeta técnica de un centro de gasto (S163, sesión
invasora de UX). Miguel Ángel: "Esa tarjeta técnica, un botón exportar
con opciones jpg, png, pdf, word, html".

Una sola fuente: los apartados de `card_sections`
(panel/views_machine_menu.py), los mismos que pinta la ventana.
- html: página independiente (panel/machine_card/export.html).
- pdf: esa página con WeasyPrint (A4 vertical).
- png / jpg: la primera página del PDF rasterizada con PyMuPDF a
  200 ppp y recortada a la tarjeta (Pillow; jpg calidad 92).
- docx: python-docx, un título y una tabla por apartado.
"""

# S163: copia de panel/machine_card_export.py y de las funciones de la
# tarjeta técnica de panel/views_machine_menu.py (EXPORT_CHOICES,
# machine_title, card_sections) para la nueva interfaz.

import io

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

FORMATS = {
    "html": "text/html; charset=utf-8",
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
}
RASTER_DPI = 200


def _context(machine, title, sections):
    return {
        "machine": machine,
        "title": title,
        "sections": sections,
        "specs_source": machine.specs_source,
        "specs_read_at": machine.specs_read_at,
        "generated_at": timezone.localtime(),
    }


def _html(context):
    return render_to_string("new_ui/machine_card_export.html", context)


def _pdf(context):
    from weasyprint import HTML

    return HTML(string=_html(context)).write_pdf()


def _raster(context, fmt):
    import fitz
    from PIL import Image

    from PIL import ImageOps

    document = fitz.open(stream=_pdf(context), filetype="pdf")
    try:
        pixmap = document[0].get_pixmap(dpi=RASTER_DPI)
        image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
    finally:
        document.close()
    # Solo la tarjeta, sin el resto de la hoja en blanco (margen 40 px).
    box = ImageOps.invert(image.convert("L")).getbbox()
    if box:
        image = image.crop((
            max(box[0] - 40, 0), max(box[1] - 40, 0),
            min(box[2] + 40, image.width), min(box[3] + 40, image.height),
        ))
    buffer = io.BytesIO()
    if fmt == "png":
        image.save(buffer, "PNG")
    else:
        image.save(buffer, "JPEG", quality=92)
    return buffer.getvalue()


def _docx(context):
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.add_heading(context["title"], level=1)
    paragraph = document.add_paragraph("Tarjeta técnica")
    paragraph.runs[0].italic = True
    for section_title, rows in context["sections"]:
        document.add_heading(section_title, level=2)
        table = document.add_table(rows=0, cols=2)
        table.style = "Light Grid Accent 1"
        for label, value in rows:
            cells = table.add_row().cells
            cells[0].text = str(label)
            cells[1].text = str(value)
            for cell in cells:
                for run in cell.paragraphs[0].runs:
                    run.font.size = Pt(10)
    note = []
    if context["specs_read_at"]:
        note.append("Datos leídos el %s" % timezone.localtime(
            context["specs_read_at"]).strftime("%d/%m/%Y"))
    if context["specs_source"]:
        note.append("de: %s" % context["specs_source"][:300])
    if note:
        document.add_paragraph(" ".join(note)).runs[0].font.size = Pt(8)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def card_export_response(machine, title, sections, fmt):
    """
    HttpResponse with the card in the requested format (download).

    ---

    La tarjeta en el formato pedido, como descarga con el código de la
    máquina en el nombre del archivo.
    """
    context = _context(machine, title, sections)
    if fmt == "html":
        content = _html(context).encode("utf-8")
    elif fmt == "pdf":
        content = _pdf(context)
    elif fmt in ("png", "jpg"):
        content = _raster(context, fmt)
    else:
        content = _docx(context)
    response = HttpResponse(content, content_type=FORMATS[fmt])
    stem = "tarjeta_tecnica_%s" % (machine.code or machine.pk)
    response["Content-Disposition"] = 'attachment; filename="%s.%s"' % (
        stem.replace('"', ""), fmt)
    return response


# ---- Copia de panel/views_machine_menu.py ----
EXPORT_CHOICES = (
    ("pdf", "PDF", "bi-filetype-pdf"),
    ("docx", "Word", "bi-filetype-docx"),
    ("html", "HTML", "bi-filetype-html"),
    ("png", "Imagen PNG", "bi-filetype-png"),
    ("jpg", "Imagen JPG", "bi-filetype-jpg"),
)


def machine_title(machine):
    """
    "A59 · LIEBHERR LTM 1230-5.1 · 1234ABC" for headers.
    ---
    Rótulo corto del centro de gasto para cabeceras.
    """
    return " · ".join(
        part for part in (machine.code, machine.brand_model, machine.plate)
        if part
    )


def _metres(value_mm):
    if value_mm is None:
        return ""
    return ("%.2f" % (value_mm / 1000)).replace(".", ",") + " m"


def _number(value, unit=""):
    if value is None or value == "":
        return ""
    text = ("%.2f" % value).rstrip("0").rstrip(".").replace(".", ",")
    return text + (" " + unit if unit else "")


def card_sections(machine):
    """
    [(title, [(label, value)])] of the technical card (empty values out).
    ---
    Los apartados de la tarjeta técnica, solo con los datos que tiene
    la máquina. Todo resuelto aquí; la plantilla solo pinta.
    """
    mma = machine.max_authorized_mass_kg
    identification = [
        ("Marca y modelo", machine.brand_model),
        ("Tipo", machine.type_name),
        ("Familia", machine.family),
        ("Matrícula", machine.plate),
        ("Nº de bastidor", machine.chassis_number),
        ("Nº de serie de la grúa", machine.crane_serial_number),
        ("Año de fabricación", machine.manufacture_year or ""),
        ("Primera matriculación", (
            machine.first_registration_date.strftime("%d/%m/%Y")
            if machine.first_registration_date else "")),
        ("Categoría ITV", machine.itv_category),
        ("Empresa", machine.company_name),
        ("Estado", "Activo" if machine.is_active else "Inactivo"),
    ]
    elevation = [
        ("Capacidad de elevación", _number(machine.capacity_tonnes, "t")),
        ("Capacidad máxima (según libro)", machine.max_capacity),
        ("Momento de carga", _number(machine.capacity_tm, "t·m")),
    ]
    weights = [
        ("Masa máxima autorizada", (
            "%s (%s kg)" % (_number(mma / 1000, "t"),
                            "{:,}".format(mma).replace(",", "."))
            if mma else "")),
        ("Masa", (
            "{:,} kg".format(machine.mass_kg).replace(",", ".")
            if machine.mass_kg else "")),
        ("Número de ejes", machine.axle_count or ""),
        ("Masa por eje", machine.axle_mass),
        ("Largo", _metres(machine.length_mm)),
        ("Ancho", _metres(machine.width_mm)),
        ("Alto", _metres(machine.height_mm)),
    ]
    owner = [
        ("Primer propietario", machine.first_owner_name),
        ("NIF/CIF", machine.first_owner_tax_id),
        ("Domicilio", machine.first_owner_address),
        ("C.P. y población", machine.first_owner_city),
    ]
    sections = []
    for title, rows in (
        ("Identificación", identification),
        ("Elevación", elevation),
        ("Pesos y dimensiones", weights),
        ("Titularidad inicial", owner),
    ):
        rows = [(label, value) for label, value in rows if value != ""
                and value is not None]
        if rows:
            sections.append((title, rows))
    return sections
