# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/export_formats.py
"""
Excel, PDF or print from the same export (S148).

---

Excel, PDF o impresión desde la misma exportación (S148). Miguel Ángel:
"sería conveniente tener una impresión y exportación a PDF en todas
las vistas donde ya exportamos a Excel". Cada exportación sigue
construyendo su libro de Excel igual que antes; al final, en vez de
devolverlo tal cual, llama a `workbook_response`, que según el
parámetro `export_format` (xlsx por defecto) devuelve:

- xlsx: el .xlsx de siempre.
- pdf: el mismo contenido como tabla en un PDF (A4 apaisado,
  WeasyPrint), una sección por hoja.
- print: la misma tabla como página que abre el diálogo de imprimir.

Así las columnas, filtros y plantillas de cada exportación valen igual
para los tres formatos, sin duplicar ninguna consulta.
"""
import datetime
import html
import io

from django.http import HttpResponse

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
# S153: "html" = página interactiva (panel/export_html.py).
FORMATS = ("xlsx", "pdf", "print", "html")


def export_format(request):
    """
    The format asked for (GET or POST "export_format"), xlsx by default.
    ---
    Formato pedido (GET o POST "export_format"); xlsx por defecto.
    """
    value = (request.GET.get("export_format")
             or request.POST.get("export_format") or "xlsx").lower()
    return value if value in FORMATS else "xlsx"


def _cell_text(value):
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        if value.time() == datetime.time(0, 0):
            return value.strftime("%d/%m/%Y")
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M")
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return ("%.2f" % value).replace(".", ",")
    return str(value)


def _used_bounds(sheet):
    """Last row and column with any value (ignores styled empty cells)."""
    last_row = last_col = 0
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value not in (None, ""):
                last_row = max(last_row, cell.row)
                last_col = max(last_col, cell.column)
    return last_row, last_col


def _sheet_html(sheet):
    last_row, last_col = _used_bounds(sheet)
    if not last_row:
        return ""
    spans, covered = {}, set()
    for merged in sheet.merged_cells.ranges:
        spans[(merged.min_row, merged.min_col)] = (
            merged.max_row - merged.min_row + 1,
            merged.max_col - merged.min_col + 1,
        )
        for r in range(merged.min_row, merged.max_row + 1):
            for c in range(merged.min_col, merged.max_col + 1):
                if (r, c) != (merged.min_row, merged.min_col):
                    covered.add((r, c))
    header_rows = 1 if sheet.freeze_panes == "A2" else 0
    parts = ["<table>"]
    for r in range(1, last_row + 1):
        if r == 1 and header_rows:
            parts.append("<thead>")
        cells = []
        for c in range(1, last_col + 1):
            if (r, c) in covered:
                continue
            cell = sheet.cell(row=r, column=c)
            tag = "th" if r <= header_rows else "td"
            attrs = ""
            rowspan, colspan = spans.get((r, c), (1, 1))
            if rowspan > 1:
                attrs += ' rowspan="%d"' % rowspan
            if colspan > 1:
                attrs += ' colspan="%d"' % colspan
            if tag == "td" and cell.font is not None and cell.font.bold:
                attrs += ' class="b"'
            cells.append("<%s%s>%s</%s>" % (
                tag, attrs, html.escape(_cell_text(cell.value)), tag))
        parts.append("<tr>%s</tr>" % "".join(cells))
        if r == 1 and header_rows:
            parts.append("</thead><tbody>")
    parts.append("</tbody></table>" if header_rows else "</table>")
    return "".join(parts)


_STYLE = """
@page { size: A4 landscape; margin: 10mm;
        @bottom-right { content: counter(page) " / " counter(pages);
                        font-size: 7pt; color: #666; } }
body { font-family: Helvetica, Arial, sans-serif; font-size: 7.5pt;
       color: #111; margin: 0; }
h1 { font-size: 11pt; margin: 0 0 2mm; }
h2 { font-size: 9pt; margin: 4mm 0 1.5mm; }
.meta { color: #666; font-size: 7pt; margin-bottom: 2mm; }
table { border-collapse: collapse; width: 100%; margin-bottom: 4mm; }
th, td { border: 0.4pt solid #999; padding: 1mm 1.2mm; text-align: left;
         vertical-align: top; }
th { background: #e9ecef; font-weight: bold; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
td.b { font-weight: bold; }
.toolbar { padding: 8px; background: #f1f3f5; margin-bottom: 8px;
           font-size: 10pt; }
@media print { .toolbar { display: none; } }
"""


def workbook_html(workbook, title, printable=False):
    """
    The workbook as one HTML page: a table per sheet.
    ---
    El libro como una página HTML: una tabla por hoja (con el nombre
    de la hoja si hay más de una).
    """
    sections = []
    several = len(workbook.worksheets) > 1
    for sheet in workbook.worksheets:
        table = _sheet_html(sheet)
        if not table:
            continue
        if several:
            sections.append("<h2>%s</h2>" % html.escape(sheet.title))
        sections.append(table)
    if not sections:
        sections.append("<p>Sin datos.</p>")
    toolbar = script = ""
    if printable:
        toolbar = ('<div class="toolbar">Vista de impresión. '
                   '<button onclick="window.print()">Imprimir</button></div>')
        script = "<script>window.addEventListener('load', function () " \
                 "{ window.print(); });</script>"
    generated = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    return (
        "<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        "<title>%s</title><style>%s</style></head><body>%s"
        "<h1>%s</h1><div class=\"meta\">Generado el %s</div>%s%s"
        "</body></html>"
    ) % (html.escape(title), _STYLE, toolbar, html.escape(title), generated,
         "".join(sections), script)


def workbook_response(request, workbook, filename):
    """
    The export in the format asked for: xlsx, pdf or print.

    `filename` is the .xlsx name the export used until now.
    ---
    La exportación en el formato pedido. `filename`: el nombre .xlsx de
    siempre (el PDF lleva el mismo con .pdf).
    """
    stem = filename[:-5] if filename.lower().endswith(".xlsx") else filename
    fmt = export_format(request)
    if fmt == "xlsx":
        from panel.xlsx_style import colorize_workbook

        # S153: todas las exportaciones a Excel van con colores.
        colorize_workbook(workbook)
        buffer = io.BytesIO()
        workbook.save(buffer)
        response = HttpResponse(
            buffer.getvalue(), content_type=XLSX_CONTENT_TYPE)
        response["Content-Disposition"] = (
            'attachment; filename="%s.xlsx"' % stem)
        return response
    title = stem.replace("_", " ")
    if fmt == "html":
        return html_download(workbook, stem)
    page = workbook_html(workbook, title, printable=(fmt == "print"))
    if fmt == "print":
        return HttpResponse(page)
    from weasyprint import HTML

    response = HttpResponse(
        HTML(string=page).write_pdf(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="%s.pdf"' % stem
    return response


def html_download(workbook, stem):
    """
    The workbook as an interactive .html download (S153).
    ---
    El libro como descarga .html interactiva (S153).
    """
    from panel.export_html import workbook_interactive_html

    response = HttpResponse(
        workbook_interactive_html(workbook, stem.replace("_", " ")),
        content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="%s.html"' % stem
    return response
