# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/export_html.py
"""
Interactive HTML export of a workbook (S153).

---

Exportación a HTML interactiva de un libro de Excel (S153). Miguel
Ángel: "en las exportaciones que sea posible, añadimos la exportación
a HTML que sea interactiva y muy atractiva visualmente."

`workbook_interactive_html` convierte el mismo libro que ya construye
cada exportación (mismas columnas, filtros y plantillas) en UNA página
autocontenida -- sin nada de internet: se abre con doble clic, se
manda por correo y funciona sin conexión -- con:

- una pestaña por hoja, título y fecha de generación;
- búsqueda en todas las columnas y un filtro por columna;
- orden al pulsar la cabecera (números y fechas como tales);
- recuento de filas y suma de las columnas numéricas de lo que se ve;
- mostrar u ocultar columnas, modo oscuro, imprimir y descargar lo
  filtrado en CSV.

La cabecera de cada hoja es la fila con más celdas rellenas entre las
10 primeras (lo de encima son títulos); las filas que empiezan por
"Total" van al pie.
"""
import datetime
import json

_SCAN_ROWS = 10


def _filled_count(row):
    return sum(1 for cell in row if cell.value not in (None, ""))


def _text(value):
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
    if isinstance(value, (int, float)):
        number = float(value)
        if number.is_integer():
            text = "{:,.0f}".format(number)
        else:
            text = "{:,.2f}".format(number)
        return text.replace(",", "\x00").replace(".", ",").replace(
            "\x00", ".")
    return str(value)


def _key(value):
    """Sort key: number for numbers and dates, text otherwise."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, datetime.datetime):
        return value.timestamp()
    if isinstance(value, datetime.date):
        return datetime.datetime(
            value.year, value.month, value.day).timestamp()
    if isinstance(value, datetime.time):
        return value.hour * 3600 + value.minute * 60 + value.second
    return None


def _sheet_data(sheet):
    rows = [list(row) for row in sheet.iter_rows()]
    rows = [row for row in rows if _filled_count(row)]
    if not rows:
        return None
    header_index, best = 0, 0
    for index, row in enumerate(rows[:_SCAN_ROWS]):
        count = _filled_count(row)
        if count > best:
            header_index, best = index, count
    header = rows[header_index]
    last_col = max(
        cell.column for cell in header if cell.value not in (None, ""))
    for row in rows[header_index + 1:]:
        for cell in row:
            if cell.value not in (None, ""):
                last_col = max(last_col, cell.column)
    titles = [
        " ".join(_text(c.value) for c in row if c.value not in (None, ""))
        for row in rows[:header_index]
    ]
    columns = []
    for col in range(last_col):
        label = _text(header[col].value) if col < len(header) else ""
        columns.append({"label": label or "Columna %d" % (col + 1)})
    body, totals = [], []
    numeric = [True] * last_col
    seen = [False] * last_col
    for row in rows[header_index + 1:]:
        values = [row[col].value if col < len(row) else None
                  for col in range(last_col)]
        first = next((v for v in values if v not in (None, "")), None)
        if isinstance(first, str) and first.strip().upper().startswith(
                "TOTAL"):
            totals.append([_text(v) for v in values])
            continue
        cells = []
        for col, value in enumerate(values):
            if value not in (None, ""):
                seen[col] = True
                if not isinstance(value, (int, float)) or isinstance(
                        value, bool):
                    numeric[col] = False
            key = _key(value)
            cells.append({"t": _text(value), "k": key}
                         if key is not None else {"t": _text(value)})
        body.append(cells)
    for col, column in enumerate(columns):
        column["num"] = bool(numeric[col] and seen[col])
    return {
        "name": sheet.title, "titles": titles, "columns": columns,
        "rows": body, "totals": totals,
    }


def workbook_interactive_html(workbook, title):
    """
    The workbook as one self-contained interactive HTML page.
    ---
    El libro como una página HTML interactiva y autocontenida.
    """
    sheets = [data for data in (_sheet_data(s) for s in workbook.worksheets)
              if data]
    payload = {
        "title": title,
        "generated": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "sheets": sheets,
    }
    from django.template.loader import render_to_string

    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return render_to_string("panel/export_interactive.html", {
        "title": title, "data_json": data,
    })
