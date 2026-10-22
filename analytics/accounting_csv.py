# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/analytics/accounting_csv.py
"""
Merge of accounting entry CSV files (Costes de operarios).

---

Unión de ficheros CSV de asientos contables (Miguel Ángel, S133, en
Costes de operarios): los ficheros van uno detrás de otro, la columna B
(número de asiento) se renumera correlativa teniendo en cuenta la
columna C (línea del asiento: cada asiento nuevo de un fichero sube un
número, y todas sus líneas comparten el mismo) y se borra la columna K
(la serie: A, C, H...) en los ficheros que la traen (14 columnas; los
ENTCAR ya vienen sin ella, con 13). Formato de salida igual que el de
entrada: separado por punto y coma, saltos de línea CRLF.
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
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            cols = line.split(";")
            if len(cols) <= COLUMN_C:
                raise MergeError(
                    "%s, fila %d: no tiene columnas B y C." % (name, line_no)
                )
            if cols[COLUMN_B] != previous:
                number += 1
                previous = cols[COLUMN_B]
            cols[COLUMN_B] = str(number)
            if len(cols) == COLUMNS_WITH_K:
                del cols[COLUMN_K]
            rows.append(";".join(cols))
    if not rows:
        raise MergeError("Los ficheros no tienen filas.")
    data = ("\r\n".join(rows) + "\r\n").encode(out_encoding)
    return data, len(rows), number
