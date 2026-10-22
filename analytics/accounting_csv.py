# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/analytics/accounting_csv.py
"""
Merge of accounting entry CSV files (Costes de operarios).

---

Unión de ficheros CSV de asientos contables (Miguel Ángel, S133, en
Costes de operarios): los ficheros van uno detrás de otro, la columna B
(número de asiento) se renumera correlativa teniendo en cuenta la
columna C (línea del asiento: cada vez que la columna C vuelve a
empezar, sube un número, y todas las líneas del asiento comparten el
mismo). Las filas mantienen su orden y la columna C no se toca. Se
borra la columna K (la serie: A, C, H...) en los ficheros que la traen
(14 columnas; los ENTCAR ya vienen sin ella, con 13). Formato de
salida igual que el de entrada: separado por punto y coma, saltos de
línea CRLF.
"""

COLUMN_B = 1
COLUMN_C = 2
COLUMN_K = 10
COLUMNS_WITH_K = 14
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


def _line_number(value):
    """
    Line number of column C, or None if it is not a number.

    ---

    Número de línea de la columna C, o None si no es un número.
    """
    try:
        return int(value.strip())
    except ValueError:
        return None


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
        previous_b = None
        previous_c = None
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            cols = line.split(";")
            if len(cols) <= COLUMN_C:
                raise MergeError(
                    "%s, fila %d: no tiene columnas B y C." % (name, line_no)
                )
            line_c = _line_number(cols[COLUMN_C])
            # A new entry starts when column C starts again (1, or not
            # greater than the previous line) or column B changes. The
            # rows keep their order; column C is never touched.
            # Empieza un asiento nuevo cuando la columna C vuelve a
            # empezar (1, o no mayor que la línea anterior) o cambia la
            # columna B. Las filas no cambian de orden y la columna C
            # no se toca.
            if (
                cols[COLUMN_B] != previous_b
                or line_c is None or previous_c is None
                or line_c <= previous_c
            ):
                number += 1
            previous_b = cols[COLUMN_B]
            previous_c = line_c
            cols[COLUMN_B] = str(number)
            if len(cols) == COLUMNS_WITH_K:
                del cols[COLUMN_K]
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
    quitan todas y se deja solo la última, al final, con su ORDEN
    siguiente. Devuelve el CSV en bytes, las filas de datos y las
    facturas.
    """
    header = None
    rows = []
    summary = None
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
            rows.append(";".join(cols))
    if not rows:
        raise MergeError("Los ficheros no tienen facturas.")
    lines = ([header] if header else []) + rows
    if summary is not None:
        summary[INVOICE_ORDER] = str(order + 1)
        lines.append(";".join(summary))
    data = ("\r\n".join(lines) + "\r\n").encode(out_encoding)
    return data, len(rows), invoices
