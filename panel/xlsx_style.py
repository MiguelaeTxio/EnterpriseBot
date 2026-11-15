# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/xlsx_style.py
"""
Colours for the Excel exports (S153).

---

Colores de las exportaciones a Excel (S153). Miguel Ángel: "todas las
exportaciones a excel, exceptuando las herramientas de contabilidad,
deben ir con colores para hacerlas más legibles."

`colorize_workbook` da a cada hoja el mismo aspecto:
- la cabecera (la fila con más celdas rellenas entre las 10 primeras)
  en azul oscuro con letra blanca en negrita, centrada;
- las filas de encima de la cabecera (títulos) en negrita azul;
- las filas de datos en bandas alternas, con un borde fino gris;
- las filas de total (empiezan por "Total") en azul claro y negrita;
- la cabecera fija y con filtro, si la hoja no los tenía ya.

Una hoja que ya trae colores propios (algún relleno puesto por su
exportación, p. ej. los partes de trabajo o las plantillas de saldos)
no se toca: ya tiene su diseño. Las herramientas de contabilidad
(analytics/views_accounting.py) exportan CSV y no pasan por aquí.
"""
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, color="1F4E78", size=12)
BAND_FILL = PatternFill("solid", fgColor="EEF3FA")
TOTAL_FILL = PatternFill("solid", fgColor="D9E2F3")
_THIN = Side(style="thin", color="C9D3E0")
CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
HEADER_ALIGNMENT = Alignment(
    horizontal="center", vertical="center", wrap_text=True)
# Más celdas que esto: solo cabecera y totales, sin bandas ni bordes.
MAX_STYLED_CELLS = 200000
_SCAN_ROWS = 10


def _has_own_colors(sheet):
    for row in sheet.iter_rows(max_row=min(sheet.max_row, 200)):
        for cell in row:
            if cell.fill is not None and cell.fill.fill_type:
                return True
    return False


def _filled(row):
    return [cell for cell in row if cell.value not in (None, "")]


def _header_row(sheet):
    best, best_count = None, 1
    for index, row in enumerate(sheet.iter_rows(
            max_row=min(sheet.max_row, _SCAN_ROWS)), start=1):
        count = len(_filled(row))
        if count > best_count:
            best, best_count = index, count
    return best


def _is_total(row):
    filled = _filled(row)
    return bool(filled) and isinstance(filled[0].value, str) and \
        filled[0].value.strip().upper().startswith("TOTAL")


def colorize_sheet(sheet):
    """
    Header, bands and totals on one sheet (see module docstring).
    ---
    Cabecera, bandas y totales de una hoja; no toca la que ya tiene
    colores propios.
    """
    if sheet.max_row < 1 or _has_own_colors(sheet):
        return
    header = _header_row(sheet)
    if header is None:
        return
    last_col = max(
        cell.column for cell in _filled(sheet[header]))
    for row in sheet.iter_rows(min_row=1, max_row=header - 1,
                               max_col=last_col):
        for cell in row:
            if cell.value not in (None, ""):
                cell.font = TITLE_FONT
    for cell in sheet[header][:last_col]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGNMENT
        cell.border = CELL_BORDER
    banded = (sheet.max_row - header) * last_col <= MAX_STYLED_CELLS
    last_data = header
    for offset, row in enumerate(sheet.iter_rows(
            min_row=header + 1, max_row=sheet.max_row, max_col=last_col)):
        if not _filled(row):
            continue
        if _is_total(row):
            for cell in row:
                cell.fill = TOTAL_FILL
                cell.font = Font(bold=True)
                cell.border = CELL_BORDER
            continue
        last_data = row[0].row
        if not banded:
            continue
        for cell in row:
            if offset % 2:
                cell.fill = BAND_FILL
            cell.border = CELL_BORDER
    if sheet.freeze_panes is None:
        sheet.freeze_panes = "A%d" % (header + 1)
    if not sheet.auto_filter.ref and last_col >= 2 and last_data > header:
        sheet.auto_filter.ref = "A%d:%s%d" % (
            header, get_column_letter(last_col), last_data)


def colorize_workbook(workbook):
    """
    Colours every sheet of the workbook; returns it.
    ---
    Da color a todas las hojas del libro y lo devuelve.
    """
    for sheet in workbook.worksheets:
        colorize_sheet(sheet)
    return workbook
