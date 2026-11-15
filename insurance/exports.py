# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/exports.py
"""
Exports of an insurance report: HTML, Excel, PDF and Word.

---

Exportaciones de un informe de seguros. Las cuatro salen de los mismos
datos (`InsuranceReport.data`) y dicen lo mismo, en el orden pensado
para decidir la renovación (S152): resumen, cuándo vence la prima, lo
que hay que resolver antes de renovar, por aseguradora y por mediador, y
una sección por tipo de seguro con lo que vence antes arriba.
- HTML: página suelta que se abre sin internet (filtro por empresa y
  buscador), la misma que «Ver» en la pestaña.
- PDF: la misma página preparada para imprimir (weasyprint).
- Excel: Resumen, Seguros (agrupados por tipo, con colores por
  vencimiento), Avisos y Libro mayor; colores como el resto de
  exportaciones del panel.
- Word: el mismo informe en documento editable.
"""
import collections
import datetime
import io

from django.template.loader import render_to_string

from insurance import companies
from insurance.readings import CATEGORIES
from insurance.service import due_label

ALERT_CLASS = {
    "Vencido": "crit", "Doble seguro": "crit",
    "Sin recibo en el mayor": "warn", "Precio distinto": "warn",
    "Vehículo de baja": "warn", "Baja en la póliza": "info",
    "Aseguradora distinta": "info", "Sin precio": "info",
}
BUCKETS = (
    ("Vencidos o sin renovar", None, -1),
    ("En 30 días o menos", 0, 30),
    ("De 31 a 60 días", 31, 60),
    ("De 61 a 90 días", 61, 90),
    ("De 91 a 180 días", 91, 180),
    ("Más de 180 días", 181, 100000),
)
_OTHERS = ("salud", "credito")


def eur(value, decimals=2):
    """
    "1.234,56 €" ("" for None).
    ---
    Importe con formato español.
    """
    if value is None:
        return ""
    text = ("{:,.%df}" % decimals).format(value)
    return text.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _date(text):
    return datetime.date.fromisoformat(text) if text else None


def context(report):
    """
    Everything the HTML/PDF templates and the Word export need.
    ---
    Todo lo que necesitan las plantillas HTML/PDF y la exportación a
    Word, calculado una vez a partir de los datos del informe.
    """
    data = report.data or {}
    records = data.get("records", [])
    for record in records:
        record["due_date"] = _date(record["due"])
        record["urgency"] = _urgency(record)
        record["alert_items"] = [(a, ALERT_CLASS.get(a, "info"))
                                 for a in record["alerts"]]
        record["fleet_rows"] = [(name, premium, _date(due))
                                for name, premium, due in record["fleet"]]
    renewable = [r for r in records if r["category"] not in _OTHERS]
    base = sum(r["premium"] or 0 for r in renewable)
    others = sum(r["premium"] or 0 for r in records
                 if r["category"] in _OTHERS)
    buckets = []
    for label, low, high in BUCKETS:
        items = [r for r in renewable if r["days"] is not None and (
            (low is None and r["days"] < 0)
            or (low is not None and low <= r["days"] <= high))]
        buckets.append({"label": label, "count": len(items),
                        "premium": sum(r["premium"] or 0 for r in items)})
    no_date = [r for r in renewable if r["days"] is None]
    buckets.append({"label": "Sin fecha", "count": len(no_date),
                    "premium": sum(r["premium"] or 0 for r in no_date)})
    top = max((b["premium"] for b in buckets), default=0) or 1
    for bucket in buckets:
        bucket["width"] = round(100 * bucket["premium"] / top, 1)
    sections = []
    for key, label in CATEGORIES:
        items = [r for r in records if r["category"] == key]
        if not items:
            continue
        insurers = collections.Counter(r["insurer"] for r in items)
        sections.append({
            "key": key, "label": label, "records": items,
            "premium": sum(r["premium"] or 0 for r in items),
            "insurers": ", ".join("%s (%d)" % pair
                                  for pair in insurers.most_common()),
            "months": _months(items),
        })
    alerts = collections.OrderedDict()
    for name in ALERT_CLASS:
        hits = [r for r in records if name in r["alerts"]]
        if hits:
            alerts[name] = {"klass": ALERT_CLASS[name], "records": hits}
    return {
        "report": report,
        "title": report.title,
        "due_label": due_label(report),
        "generated": report.finished_at or report.created_at,
        "supervisor": _user_label(report.created_by),
        "today": _date(data.get("today")),
        "companies_label": ", ".join(
            companies.label(c) for c in data.get("companies") or []) or (
            "Todas las empresas"),
        "ledgers": data.get("ledgers", []),
        "records": records,
        "count": len(records),
        "base_premium": base,
        "other_premium": others,
        "soon_count": sum(1 for r in renewable if r["days"] is not None
                          and 0 <= r["days"] <= 60),
        "soon_premium": sum(r["premium"] or 0 for r in renewable
                            if r["days"] is not None
                            and 0 <= r["days"] <= 60),
        "overdue_count": sum(1 for r in records if "Vencido" in r["alerts"]),
        "alert_count": sum(1 for r in records if r["alerts"]),
        "buckets": buckets,
        "alerts": alerts,
        "by_insurer": _aggregate(renewable, "insurer", base),
        "by_broker": _aggregate(renewable, "broker", base),
        "sections": sections,
        "companies_present": sorted(
            {r["company_label"] for r in records},
            key=lambda n: companies.order(next(
                (c for c, l in companies.CHOICES if l == n), ""))),
        "ledger_lines": data.get("ledger_lines", []),
        "ledger_outside": [line for line in data.get("ledger_lines", [])
                           if not line["in_report"]],
    }


def _user_label(company_user):
    if company_user is None:
        return ""
    user = company_user.user
    return user.get_full_name() or user.username


def _urgency(record):
    if "Vencido" in record["alerts"]:
        return "u0"
    days = record["days"]
    if days is None:
        return "u9"
    if days < 0:
        return "u0"
    if days <= 30:
        return "u1"
    if days <= 60:
        return "u2"
    return "u3"


def _months(items):
    """
    The section's rows with a month separator before each new month.
    ---
    Las filas de la sección con un separador por mes (mes, número de
    seguros y prima del mes).
    """
    rows, current = [], object()
    names = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre",
             "Diciembre")
    for record in items:
        due = record["due_date"]
        month = (due.year, due.month) if due else None
        if month != current:
            current = month
            same = [r for r in items if (
                (r["due_date"].year, r["due_date"].month)
                if r["due_date"] else None) == month]
            rows.append({
                "separator": True,
                "label": ("%s de %s" % (names[month[1] - 1], month[0])
                          if month else "Sin fecha"),
                "count": len(same),
                "premium": sum(r["premium"] or 0 for r in same),
            })
        rows.append({"separator": False, "record": record})
    return rows


def _aggregate(records, field, base):
    totals = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for record in records:
        if not record["premium"]:
            continue
        item = totals[record[field]]
        item[0] += 1
        item[1] += record["premium"]
        if record["days"] is not None and record["days"] <= 90:
            item[2] += record["premium"]
    result = []
    for name, (count, premium, soon) in sorted(
            totals.items(), key=lambda pair: -pair[1][1]):
        result.append({
            "name": name, "count": count, "premium": premium,
            "share": round(100 * premium / base, 1) if base else 0,
            "soon": soon,
        })
    return result


# ----------------------------------------------------------------------
# HTML y PDF
# ----------------------------------------------------------------------

def html(report):
    """
    The standalone HTML page (bytes).
    ---
    La página HTML suelta del informe.
    """
    return render_to_string("insurance/report.html",
                            {**context(report), "printable": False}
                            ).encode("utf-8")


def pdf(report):
    """
    The report as PDF (weasyprint), landscape A4.
    ---
    El informe en PDF, A4 apaisado.
    """
    from weasyprint import HTML

    page = render_to_string("insurance/report.html",
                            {**context(report), "printable": True})
    return HTML(string=page).write_pdf()


# ----------------------------------------------------------------------
# Excel
# ----------------------------------------------------------------------

_FILL = {"u0": "F8CBAD", "u1": "FCE4D6", "u2": "FFF2CC", "u3": None,
         "u9": "EDEDED"}


def xlsx(report):
    """
    The report as an Excel workbook with colours (bytes).
    ---
    El informe en Excel, con colores (directriz S153: todas las
    exportaciones a Excel van con colores).
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    ctx = context(report)
    workbook = Workbook()
    font = Font(name="Arial", size=10)
    bold = Font(name="Arial", size=10, bold=True)
    white = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    title_font = Font(name="Arial", size=14, bold=True)
    head_fill = PatternFill("solid", fgColor="1F3A5F")
    section_fill = PatternFill("solid", fgColor="D9E1F2")
    month_fill = PatternFill("solid", fgColor="F2F2F2")
    thin = Side(style="thin", color="D0D0D0")
    border = Border(bottom=thin)
    money = '#,##0.00 €'
    day_format = "DD/MM/YYYY"

    def header(sheet, row, names, widths):
        for column, (name, width) in enumerate(zip(names, widths), 1):
            cell = sheet.cell(row, column, name)
            cell.font, cell.fill = white, head_fill
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            sheet.column_dimensions[get_column_letter(column)].width = width
        sheet.freeze_panes = sheet.cell(row + 1, 1)

    # Resumen
    sheet = workbook.active
    sheet.title = "Resumen"
    sheet["A1"] = ctx["title"]
    sheet["A1"].font = title_font
    sheet["A2"] = "Vencimiento: %s · %s · Supervisor: %s · %s" % (
        ctx["due_label"], ctx["companies_label"], ctx["supervisor"],
        ctx["generated"].strftime("%d/%m/%Y %H:%M"))
    sheet["A2"].font = Font(name="Arial", size=9, italic=True)
    row = 4
    for label, value in (
            ("Seguros en el informe", ctx["count"]),
            ("Prima anual de los seguros renovables", ctx["base_premium"]),
            ("Salud, crédito y otros cargos periódicos",
             ctx["other_premium"]),
            ("Vencen en los próximos 60 días", ctx["soon_count"]),
            ("Prima de lo que vence en 60 días", ctx["soon_premium"]),
            ("Vencidos o sin renovar", ctx["overdue_count"]),
            ("Seguros con algún aviso", ctx["alert_count"])):
        sheet.cell(row, 1, label).font = font
        cell = sheet.cell(row, 2, value)
        cell.font = bold
        if isinstance(value, float):
            cell.number_format = money
        row += 1
    row += 1
    header(sheet, row, ["Cuándo vence", "Seguros", "Prima anual"],
           [44, 14, 18])
    for bucket in ctx["buckets"]:
        row += 1
        sheet.cell(row, 1, bucket["label"]).font = font
        sheet.cell(row, 2, bucket["count"]).font = font
        cell = sheet.cell(row, 3, bucket["premium"])
        cell.font, cell.number_format = font, money
    for title, items in (("Aseguradora", ctx["by_insurer"]),
                         ("Mediador", ctx["by_broker"])):
        row += 2
        for column, name in enumerate(
                [title, "Seguros", "Prima anual", "% del total",
                 "Vence en 90 días"], 1):
            cell = sheet.cell(row, column, name)
            cell.font, cell.fill = white, head_fill
        for item in items:
            row += 1
            values = [item["name"], item["count"], item["premium"],
                      item["share"] / 100, item["soon"]]
            for column, value in enumerate(values, 1):
                cell = sheet.cell(row, column, value)
                cell.font = font
                if column in (3, 5):
                    cell.number_format = money
                if column == 4:
                    cell.number_format = "0.0%"
    sheet.column_dimensions["D"].width = 12
    sheet.column_dimensions["E"].width = 18

    # Seguros
    sheet = workbook.create_sheet("Seguros")
    names = ["Vence", "Días", "Empresa", "Seguro / vehículo", "Aseguradora",
             "Mediador", "Póliza", "Prima anual", "Fuente de la prima",
             "Último recibo", "Pago", "Año anterior", "Variación",
             "Avisos", "Notas"]
    header(sheet, 1, names, [12, 7, 22, 40, 18, 16, 20, 14, 12, 13, 11,
                             13, 10, 28, 70])
    row = 1
    for section in ctx["sections"]:
        row += 1
        sheet.cell(row, 1, "%s · %d seguros" % (
            section["label"], len(section["records"]))).font = bold
        cell = sheet.cell(row, 8, section["premium"])
        cell.font, cell.number_format = bold, money
        for column in range(1, len(names) + 1):
            sheet.cell(row, column).fill = section_fill
        for item in section["months"]:
            row += 1
            if item["separator"]:
                sheet.cell(row, 1, "%s · %d" % (item["label"],
                                                item["count"])).font = bold
                cell = sheet.cell(row, 8, item["premium"])
                cell.font, cell.number_format = bold, money
                for column in range(1, len(names) + 1):
                    sheet.cell(row, column).fill = month_fill
                sheet.row_dimensions[row].outlineLevel = 1
                continue
            record = item["record"]
            values = [
                record["due_date"], record["days"], record["company_label"],
                record["object"], record["insurer"], record["broker"],
                record["policy"], record["premium"],
                record["premium_source"], record["receipt"],
                record["frequency"], record["previous"],
                (record["change"] / 100) if record["change"] is not None
                else None,
                ", ".join(record["alerts"]),
                " ".join(record["comments"] + (
                    ["Flota: " + "; ".join(
                        "%s %s" % (name, eur(premium))
                        for name, premium, _due in record["fleet_rows"])]
                    if record["fleet_rows"] else [])),
            ]
            fill = _FILL[record["urgency"]]
            for column, value in enumerate(values, 1):
                cell = sheet.cell(row, column, value)
                cell.font = bold if column == 8 else font
                cell.border = border
                cell.alignment = Alignment(vertical="top",
                                           wrap_text=column in (4, 15))
                if column == 1:
                    cell.number_format = day_format
                if column in (8, 10, 12):
                    cell.number_format = money
                if column == 13:
                    cell.number_format = "+0.0%;-0.0%"
                if fill:
                    cell.fill = PatternFill("solid", fgColor=fill)
            sheet.row_dimensions[row].outlineLevel = 2
    sheet.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(names)), row)

    # Avisos
    sheet = workbook.create_sheet("Avisos")
    header(sheet, 1, ["Aviso", "Vence", "Empresa", "Seguro / vehículo",
                      "Aseguradora", "Prima anual", "Detalle"],
           [22, 12, 22, 40, 18, 14, 90])
    row = 1
    colors = {"crit": "F8CBAD", "warn": "FFF2CC", "info": "DDEBF7"}
    for name, item in ctx["alerts"].items():
        for record in item["records"]:
            row += 1
            values = [name, record["due_date"], record["company_label"],
                      record["object"], record["insurer"],
                      record["premium"], " ".join(record["comments"])]
            for column, value in enumerate(values, 1):
                cell = sheet.cell(row, column, value)
                cell.font = font
                cell.alignment = Alignment(vertical="top",
                                           wrap_text=column in (4, 7))
                if column == 2:
                    cell.number_format = day_format
                if column == 6:
                    cell.number_format = money
            sheet.cell(row, 1).fill = PatternFill(
                "solid", fgColor=colors[item["klass"]])
    sheet.auto_filter.ref = "A1:G%d" % max(row, 1)

    # Libro mayor
    if ctx["ledger_lines"]:
        sheet = workbook.create_sheet("Libro mayor")
        header(sheet, 1, ["Empresa", "Proyecto", "Descripción del proyecto",
                          "Aseguradora", "Fecha", "Cubre hasta", "Concepto",
                          "Importe", "En el informe"],
               [22, 12, 30, 20, 12, 12, 40, 13, 13])
        for row, line in enumerate(ctx["ledger_lines"], 2):
            values = [line["company_label"], line["project"],
                      line["project_text"], line["insurer"],
                      _date(line["date"]), _date(line["covered_until"]),
                      line["concept"], line["amount"],
                      "Sí" if line["in_report"] else "No (fuera de fechas)"]
            for column, value in enumerate(values, 1):
                cell = sheet.cell(row, column, value)
                cell.font = font
                if column in (5, 6):
                    cell.number_format = day_format
                if column == 8:
                    cell.number_format = money
        sheet.auto_filter.ref = "A1:I%d" % (len(ctx["ledger_lines"]) + 1)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ----------------------------------------------------------------------
# Word
# ----------------------------------------------------------------------

def docx(report):
    """
    The report as a Word document (bytes), landscape.
    ---
    El informe en Word, apaisado: resumen, avisos y una tabla por tipo
    de seguro.
    """
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    ctx = context(report)
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = (section.page_height,
                                               section.page_width)
    for side in ("left_margin", "right_margin", "top_margin",
                 "bottom_margin"):
        setattr(section, side, Cm(1.5))
    style = document.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(9)

    def shade(cell, color):
        properties = cell._tc.get_or_add_tcPr()
        fill = OxmlElement("w:shd")
        fill.set(qn("w:val"), "clear")
        fill.set(qn("w:color"), "auto")
        fill.set(qn("w:fill"), color)
        properties.append(fill)

    def table(headers, rows, widths, fills=None):
        grid = document.add_table(rows=1, cols=len(headers))
        grid.style = "Table Grid"
        for column, name in enumerate(headers):
            cell = grid.rows[0].cells[column]
            cell.text = name
            run = cell.paragraphs[0].runs[0]
            run.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            shade(cell, "1F3A5F")
        for position, values in enumerate(rows):
            cells = grid.add_row().cells
            for column, value in enumerate(values):
                cells[column].text = str(value if value is not None else "")
                if fills and fills[position]:
                    shade(cells[column], fills[position])
        for column, width in enumerate(widths):
            for row in grid.rows:
                row.cells[column].width = Cm(width)
        return grid

    document.add_heading(ctx["title"], level=0)
    document.add_paragraph(
        "Vencimiento: %s · %s · Supervisor: %s · %s" % (
            ctx["due_label"], ctx["companies_label"], ctx["supervisor"],
            ctx["generated"].strftime("%d/%m/%Y %H:%M")))
    document.add_heading("Resumen", level=1)
    table(["Dato", "Valor"], [
        ("Seguros en el informe", ctx["count"]),
        ("Prima anual de los seguros renovables",
         eur(ctx["base_premium"])),
        ("Salud, crédito y otros cargos periódicos",
         eur(ctx["other_premium"])),
        ("Vencen en los próximos 60 días", "%d (%s)" % (
            ctx["soon_count"], eur(ctx["soon_premium"]))),
        ("Vencidos o sin renovar", ctx["overdue_count"]),
        ("Seguros con algún aviso", ctx["alert_count"]),
    ], [10, 8])
    document.add_heading("Cuándo vence la prima", level=2)
    table(["Plazo", "Seguros", "Prima anual"],
          [(b["label"], b["count"], eur(b["premium"]))
           for b in ctx["buckets"]], [8, 3, 5])
    if ctx["alerts"]:
        document.add_heading("Antes de renovar", level=1)
        colors = {"crit": "F8CBAD", "warn": "FFF2CC", "info": "DDEBF7"}
        rows, fills = [], []
        for name, item in ctx["alerts"].items():
            for record in item["records"]:
                rows.append((name, record["due_date"].strftime("%d/%m/%Y")
                             if record["due_date"] else "",
                             record["company_label"], record["object"],
                             record["insurer"],
                             " ".join(record["comments"])))
                fills.append(colors[item["klass"]])
        table(["Aviso", "Vence", "Empresa", "Seguro", "Aseguradora",
               "Detalle"], rows, [3.5, 2.2, 3.5, 5.5, 3, 8.5], fills)
    document.add_heading("Por aseguradora", level=2)
    table(["Aseguradora", "Seguros", "Prima anual", "% del total",
           "Vence en 90 días"],
          [(i["name"], i["count"], eur(i["premium"]),
            "%.1f %%" % i["share"], eur(i["soon"]))
           for i in ctx["by_insurer"]], [6, 2.5, 4, 3, 4])
    document.add_heading("Por mediador", level=2)
    table(["Mediador", "Seguros", "Prima anual", "% del total",
           "Vence en 90 días"],
          [(i["name"], i["count"], eur(i["premium"]),
            "%.1f %%" % i["share"], eur(i["soon"]))
           for i in ctx["by_broker"]], [6, 2.5, 4, 3, 4])
    fills_by_urgency = {"u0": "F8CBAD", "u1": "FCE4D6", "u2": "FFF2CC",
                        "u3": None, "u9": None}
    for part in ctx["sections"]:
        document.add_page_break()
        document.add_heading("%s · %d seguros · %s al año" % (
            part["label"], len(part["records"]), eur(part["premium"])),
            level=1)
        rows, fills = [], []
        for record in part["records"]:
            change = ""
            if record["change"] is not None:
                change = "%s (%+.1f %%)" % (
                    eur(record["previous"]), record["change"])
            rows.append((
                record["due_date"].strftime("%d/%m/%Y")
                if record["due_date"] else "Sin fecha",
                record["company_label"], record["object"],
                record["insurer"], record["broker"], record["policy"],
                eur(record["premium"]) or "sin precio", change,
                ", ".join(record["alerts"])))
            fills.append(fills_by_urgency[record["urgency"]])
        table(["Vence", "Empresa", "Seguro / vehículo", "Aseguradora",
               "Mediador", "Póliza", "Prima anual", "Año anterior",
               "Avisos"], rows,
              [2.2, 3, 6, 2.6, 2.6, 3, 2.6, 3, 3.5], fills)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


EXPORTERS = {
    "html": (html, "text/html; charset=utf-8", "html"),
    "xlsx": (xlsx, "application/vnd.openxmlformats-officedocument."
             "spreadsheetml.sheet", "xlsx"),
    "pdf": (pdf, "application/pdf", "pdf"),
    "docx": (docx, "application/vnd.openxmlformats-officedocument."
             "wordprocessingml.document", "docx"),
}
