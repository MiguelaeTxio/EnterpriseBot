# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/analytics/accounting_csv.py
"""
Merge of accounting CSV files (Herramientas de contabilidad).

---

Unión de ficheros CSV contables (Miguel Ángel, S133, Herramientas de
contabilidad).

Asientos (`merge`): los ficheros van uno detrás de otro y la columna B
(número de asiento) se renumera correlativa: cada asiento de un fichero
(su número original de la columna B) recibe un número nuevo, y todas
sus líneas comparten el mismo. La columna C (línea del asiento) se
renumera 1, 2, 3... dentro de cada asiento, en el orden en que vienen
las filas, que no se mueven (incidencia real S133: en los ficheros de
Jerónimo la C viene 2, 1 o 3, 1, 2 y su programa contable da error si
no va 1, 2, 3). La columna K queda vacía, sin datos, pero la columna
existe (Miguel Ángel, S133: "debe existir la columna, pero totalmente
vacía"). Formato de
salida igual que el de entrada: punto y coma, saltos de línea CRLF.
"""

COLUMN_B = 1
COLUMN_C = 2
COLUMN_K = 10
ENCODINGS = ("utf-8", "cp1252")


class MergeError(Exception):
    """
    A file that cannot be merged, with the reason for the user.

    ---

    Fichero que no se puede unir, con el motivo para el usuario.
    """


def _decode(name, data):
    """
    Text of a file, in UTF-8 or Windows encoding.

    ---

    Texto del fichero, en UTF-8 o en la codificación de Windows.
    """
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise MergeError("%s: codificación no reconocida." % name)


def merge(files):
    """
    Merge the files in order. Returns (bytes, rows, entries).

    ---

    Une los ficheros en el orden dado (`files`: lista de (nombre,
    bytes)). Devuelve el CSV unido en bytes, el número de filas y el de
    asientos. Lanza MergeError si una fila no tiene la forma esperada.
    """
    rows = []
    number = 0
    out_encoding = "utf-8"
    for name, data in files:
        text, encoding = _decode(name, data)
        if encoding != "utf-8":
            out_encoding = encoding
        previous = None
        line_in_entry = 0
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            cols = line.split(";")
            if len(cols) <= COLUMN_K:
                raise MergeError(
                    "%s, fila %d: no llega a la columna K." % (name, line_no)
                )
            # A new entry when the original entry number (B) changes.
            # Asiento nuevo cuando cambia el número original (B).
            if cols[COLUMN_B] != previous:
                number += 1
                previous = cols[COLUMN_B]
                line_in_entry = 0
            line_in_entry += 1
            cols[COLUMN_B] = str(number)
            cols[COLUMN_C] = str(line_in_entry)
            cols[COLUMN_K] = ""
            rows.append(";".join(cols))
    if not rows:
        raise MergeError("Los ficheros no tienen filas.")
    data = ("\r\n".join(rows) + "\r\n").encode(out_encoding)
    return data, len(rows), number


# ---------------------------------------------------------------------------
# Invoices (SERIE-n-FACT): Miguel Ángel, S133.
# Facturas (SERIE-n-FACT).
# ---------------------------------------------------------------------------

INVOICE_ORDER = 0       # A: ORDEN
INVOICE_ACCOUNT = 1     # B: CUENTA
INVOICE_COUNTER = 5     # F: ASIENTO (contador de facturas)
INVOICE_NUMBER = 6      # G: Factura (a su derecha)
# Amount columns added up in the final summary line.
# Columnas de importe que se suman en la línea resumen final.
INVOICE_SUMS = (8, 11, 13)  # I: BASE, L: CUOTA, N: TOTAL


def _amount(text):
    """
    Decimal of an amount with point or comma, or 0.

    ---

    Decimal de un importe con punto o coma decimal ("-1859.60" o
    "-30.610,22"), o 0 si está vacío.
    """
    from decimal import Decimal, InvalidOperation

    text = (text or "").strip()
    if not text:
        return Decimal("0")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def _spanish(value):
    """
    Amount in the format of the summary lines: -30.610,22.

    ---

    Importe con el formato de las líneas resumen: -30.610,22.
    """
    text = "{:,.2f}".format(value)
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _is_header(cols):
    """
    Whether the row is the header (ORDEN;CUENTA;...).

    ---

    Si la fila es la cabecera (ORDEN;CUENTA;...).
    """
    return cols[INVOICE_ORDER].strip().upper() == "ORDEN"


def _is_summary(cols):
    """
    Whether the row is the summary line of a file.

    ---

    Si la fila es la línea resumen del fichero: sin cuenta ni factura
    (0), solo con los totales.
    """
    return (
        cols[INVOICE_ACCOUNT].strip() == "0"
        and cols[INVOICE_NUMBER].strip() in ("0", "")
    )


def merge_invoices(files):
    """
    Merge invoice files in order. Returns (bytes, rows, invoices).

    ---

    Une ficheros de facturas en el orden dado (`files`: lista de
    (nombre, bytes)). La cabecera queda una sola vez, arriba. La columna
    A (ORDEN) queda con números naturales correlativos. La columna F
    (contador de facturas) sube uno cada vez que cambia la factura de la
    columna G, a su derecha; las líneas de una misma factura repiten el
    número (1, 2, 3, 3...). Cada fichero trae una línea resumen: se
    quitan todas y se deja solo una al final, con su ORDEN siguiente y
    con BASE, CUOTA y TOTAL sumados de TODAS las facturas (Jerónimo,
    S133: "faltaría el sumatorio de todas las facturas [...] está
    copiando el sumatorio del último fichero"). Devuelve el CSV en
    bytes, las filas de datos y las facturas.
    """
    header = None
    rows = []
    summary = None
    totals = {column: _amount("") for column in INVOICE_SUMS}
    order = 0
    invoices = 0
    previous_invoice = None
    out_encoding = "utf-8"
    for name, data in files:
        text, encoding = _decode(name, data)
        if encoding != "utf-8":
            out_encoding = encoding
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            cols = line.split(";")
            if len(cols) <= INVOICE_NUMBER:
                raise MergeError(
                    "%s, fila %d: no tiene las columnas de factura."
                    % (name, line_no)
                )
            if _is_header(cols):
                header = header or line
                continue
            if _is_summary(cols):
                summary = cols
                continue
            order += 1
            cols[INVOICE_ORDER] = str(order)
            if cols[INVOICE_NUMBER] != previous_invoice:
                invoices += 1
                previous_invoice = cols[INVOICE_NUMBER]
            cols[INVOICE_COUNTER] = str(invoices)
            for column in INVOICE_SUMS:
                if column < len(cols):
                    totals[column] += _amount(cols[column])
            rows.append(";".join(cols))
    if not rows:
        raise MergeError("Los ficheros no tienen facturas.")
    lines = ([header] if header else []) + rows
    if summary is not None:
        summary[INVOICE_ORDER] = str(order + 1)
        for column, total in totals.items():
            if column < len(summary):
                summary[column] = _spanish(total)
        lines.append(";".join(summary))
    data = ("\r\n".join(lines) + "\r\n").encode(out_encoding)
    return data, len(rows), invoices
