# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/ledger.py
"""
Reader of the "Listado Mayor Analítico" PDFs of account 625 (insurance
premiums) exported from the accounting program.

---

Lector de los PDF «Listado Mayor Analítico» de la cuenta 625 (primas de
seguros) que saca el programa de contabilidad. De cada apunte guarda el
proyecto (centro de gasto o grupo de gasto), la cuenta (la aseguradora),
la fecha, el «Documento» (la fecha hasta la que cubre el recibo), el
concepto y el importe (debe menos haber). El PDF trae columnas fijas, así
que los importes se asignan por su posición bajo «Debe», «Haber» y
«Saldo», nunca por el orden en la línea.
"""
import collections
import datetime
import re

import fitz  # PyMuPDF

from insurance import companies

_AMOUNT = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")
_DATE_DASH = re.compile(r"^\d{1,2}-\d{2}-\d{4}$")
_DATE_SLASH = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_PROJECT_CODE = re.compile(r"^[A-Z]{3}([A-Z])-?0*(\d{1,3})\b")
# Separación vertical máxima (puntos) para que dos palabras sean de la
# misma línea.
_LINE_TOLERANCE = 2.5
# Distancia máxima (puntos) del borde derecho de un importe al de su
# columna.
_COLUMN_TOLERANCE = 18


class LedgerError(Exception):
    """
    The PDF is not a readable 625 ledger.
    ---
    El PDF no es un libro mayor de la 625 que se pueda leer.
    """


def _amount(text):
    return float(text.replace(".", "").replace(",", "."))


def _lines(page):
    """
    Words of a page grouped in visual lines, top to bottom.
    ---
    Las palabras de la página agrupadas en líneas, de arriba abajo, y
    dentro de cada línea de izquierda a derecha.
    """
    words = sorted(page.get_text("words"), key=lambda w: (w[1] + w[3]) / 2)
    lines, current, current_y = [], [], None
    for word in words:
        middle = (word[1] + word[3]) / 2
        if current and abs(middle - current_y) > _LINE_TOLERANCE:
            lines.append(sorted(current, key=lambda w: w[0]))
            current = []
        if not current:
            current_y = middle
        current.append(word)
    if current:
        lines.append(sorted(current, key=lambda w: w[0]))
    return lines


def _cost_centre(code):
    """
    Cost-centre code of a ledger project ("ASIA-55.." -> "A55").
    ---
    Código de centro de gasto de un proyecto del mayor: la cuarta letra
    del prefijo y el número («ASIA-55..» -> «A55», «PLAZ-103.» ->
    «Z103», «CAMB-12» -> «B12»). "" si el proyecto no es de una máquina
    («COC0168DZ», «GENERALES»).
    """
    match = _PROJECT_CODE.match(code or "")
    if not match:
        return ""
    return "%s%02d" % (match.group(1), int(match.group(2)))


def parse(pdf_bytes):
    """
    Parse a 625 ledger PDF.

    Returns a dict: company (code or ""), company_text (header name),
    date_from / date_to (ISO, the period of the listing), printed_at
    (ISO), entries (list of dicts) and total (sum of the entries).
    ---
    Lee un PDF del mayor de la 625. Devuelve un dict con la empresa
    (código de insurance.companies o ""), el nombre de la cabecera, el
    periodo del listado, la fecha de impresión, los apuntes y su suma.
    Cada apunte: project, project_text, cost_centre, account,
    insurer_text, date, covered_until, concept, amount.
    """
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 -- PDF ilegible
        raise LedgerError("No se puede abrir el PDF: %s" % exc) from exc
    entries = []
    header = {"company_text": "", "date_from": "", "date_to": "",
              "printed_at": ""}
    project = project_text = account = insurer = ""
    columns = None
    with document:
        for page_number, page in enumerate(document):
            for words in _lines(page):
                texts = [w[4] for w in words]
                if page_number == 0 and not header["company_text"]:
                    if "Listado" in texts:
                        header["company_text"] = " ".join(
                            texts[:texts.index("Listado")])
                        continue
                _header_dates(texts, header)
                if texts[0] == "PROYECTO:" and len(texts) > 1:
                    project = texts[1]
                    project_text = " ".join(texts[2:]).strip()
                    continue
                if texts[0] == "Cuenta:" and len(texts) > 1:
                    account = texts[1]
                    insurer = " ".join(texts[2:]).strip()
                    continue
                if "Debe" in texts and "Haber" in texts and (
                        "Saldo" in texts):
                    columns = {w[4]: w[2] for w in words
                               if w[4] in ("Debe", "Haber", "Saldo")}
                    continue
                if not _DATE_DASH.match(texts[0]) or columns is None:
                    continue
                entries.append(_entry(words, columns, project,
                                      project_text, account, insurer))
    if not entries:
        raise LedgerError("El PDF no tiene apuntes de un libro mayor.")
    header["company"] = companies.detect(header["company_text"])
    header["entries"] = entries
    header["total"] = round(sum(e["amount"] for e in entries), 2)
    return header


def _header_dates(texts, header):
    """
    Period and print date of the listing, from the header lines.
    ---
    Periodo («Desde Fecha: 1-01-2026 … Hasta Fecha: 31-12-2026») y
    fecha de impresión («Fecha: 28-10-2026» junto a «Página»).
    """
    for position, text in enumerate(texts[:-1]):
        if text != "Fecha:" or not _DATE_DASH.match(texts[position + 1]):
            continue
        value = _iso(texts[position + 1])
        before = texts[position - 1] if position else ""
        if before == "Desde" and not header["date_from"]:
            header["date_from"] = value
        elif before == "Hasta" and not header["date_to"]:
            header["date_to"] = value
        elif before not in ("Desde", "Hasta") and (
                not header["printed_at"]):
            header["printed_at"] = value


def _iso(text):
    if _DATE_DASH.match(text):
        day, month, year = text.split("-")
    else:
        day, month, year = text.split("/")
    return datetime.date(int(year), int(month), int(day)).isoformat()


def _entry(words, columns, project, project_text, account, insurer):
    """
    One ledger line: date, covered-until, concept and debit - credit.
    ---
    Un apunte: fecha, «Documento» (fecha hasta la que cubre), concepto e
    importe (debe menos haber, por la columna de cada número).
    """
    date = _iso(words[0][4])
    rest = words[1:]
    covered_until = ""
    if rest and _DATE_SLASH.match(rest[0][4]):
        covered_until = _iso(rest[0][4])
        rest = rest[1:]
    concept, debit, credit = [], 0.0, 0.0
    for word in rest:
        text, right = word[4], word[2]
        if _AMOUNT.match(text):
            column = min(columns, key=lambda c: abs(columns[c] - right))
            if abs(columns[column] - right) <= _COLUMN_TOLERANCE:
                if column == "Debe":
                    debit += _amount(text)
                elif column == "Haber":
                    credit += _amount(text)
                continue
        if right < columns["Debe"] - 40:
            concept.append(text)
    concept_text = " ".join(concept)
    # El número de asiento, si sale pegado al concepto, no es concepto.
    concept_text = re.sub(r"\s+\d{1,3}(?:,\d{3})*$", "", concept_text)
    code = project.rstrip(".")
    return {
        "project": code,
        "project_text": project_text.strip("\\").replace("\\", " / "),
        "cost_centre": _cost_centre(code),
        "account": account,
        "insurer_text": insurer,
        "date": date,
        "covered_until": covered_until,
        "concept": concept_text.strip(),
        "amount": round(debit - credit, 2),
    }


def summary(entries):
    """
    Count and total per insurer text, for the upload confirmation.
    ---
    Número de apuntes e importe por aseguradora, para mostrar al subir.
    """
    totals = collections.OrderedDict()
    for entry in entries:
        item = totals.setdefault(entry["insurer_text"], [0, 0.0])
        item[0] += 1
        item[1] += entry["amount"]
    return [(name, n, round(total, 2)) for name, (n, total)
            in totals.items()]
