# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/machine_card_export.py
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
    return render_to_string("panel/machine_card/export.html", context)


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
