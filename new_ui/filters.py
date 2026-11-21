# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/filters.py
"""
Common filter block of the new interface: quick period and multi-sort.

---

Bloque común de filtros de la nueva interfaz (S163, directriz 4.27,
punto 4bis): el periodo rápido (día, semana, mes, año; periodo actual o
anterior; o desde/hasta) y el orden múltiple por cabecera. Lo usan
todas las secciones; cada una decide a qué fecha se aplica el periodo.
"""
import datetime

from django.utils import timezone

PERIOD_UNITS = (
    ("dia", "Día"), ("semana", "Semana"), ("mes", "Mes"), ("ano", "Año"),
)
PERIOD_WHICH = (("actual", "Periodo actual"), ("anterior", "Periodo anterior"))
MAX_SORT_KEYS = 4


def _parse_date(raw):
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def period_range(params):
    """
    (start, end) dates of the period filter, both inclusive, or None.

    ---

    Fechas (desde, hasta), ambas incluidas, del filtro de periodo:
    - "desde"/"hasta" escritas mandan sobre los botones;
    - si no, la unidad (día, semana, mes, año) y si es el periodo
      actual o el anterior;
    - sin nada: (None, None), sin filtro.
    """
    start = _parse_date(params.get("desde"))
    end = _parse_date(params.get("hasta"))
    if start or end:
        return start, end
    unit = params.get("periodo", "")
    if unit not in dict(PERIOD_UNITS):
        return None, None
    previous = params.get("cual") == "anterior"
    today = timezone.localdate()
    if unit == "dia":
        day = today - datetime.timedelta(days=1) if previous else today
        return day, day
    if unit == "semana":
        start = today - datetime.timedelta(days=today.weekday())
        if previous:
            start -= datetime.timedelta(days=7)
        return start, start + datetime.timedelta(days=6)
    if unit == "mes":
        start = today.replace(day=1)
        if previous:
            start = (start - datetime.timedelta(days=1)).replace(day=1)
        following = (start + datetime.timedelta(days=32)).replace(day=1)
        return start, following - datetime.timedelta(days=1)
    year = today.year - 1 if previous else today.year
    return datetime.date(year, 1, 1), datetime.date(year, 12, 31)


def period_context(params):
    """
    Template data for the period block (buttons, current values).

    ---

    Lo que pinta el bloque de periodo: los botones con el elegido
    marcado y las fechas escritas.
    """
    unit = params.get("periodo", "")
    which = params.get("cual", "actual") or "actual"
    start, end = period_range(params)
    return {
        "units": [{"key": k, "label": l, "on": k == unit}
                  for k, l in PERIOD_UNITS],
        "which": [{"key": k, "label": l, "on": k == which}
                  for k, l in PERIOD_WHICH],
        "unit": unit,
        "cual": which,
        "desde": params.get("desde", ""),
        "hasta": params.get("hasta", ""),
        "summary": (
            "%s – %s" % (start.strftime("%d/%m/%Y") if start else "…",
                         end.strftime("%d/%m/%Y") if end else "…")
            if start or end else "Sin límite de fechas"
        ),
    }


def parse_sort(raw, valid):
    """
    "key,-key" -> [(key, descending)] with valid keys only (max 4).

    ---

    "clave,-clave" -> [(clave, descendente)], solo claves válidas, sin
    repetir y como mucho cuatro.
    """
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in valid and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:MAX_SORT_KEYS]


def sort_headers(raw, columns):
    """
    Header data: label, next "sort" value on click, arrow and priority.

    ---

    Para cada columna (clave, texto, clave de orden o ""): el "sort"
    que envía un clic (la promueve a principal o invierte su sentido),
    la flecha y la prioridad (superíndice si hay varias).
    """
    valid = [c[2] for c in columns if c[2]]
    current = parse_sort(raw, valid)
    active = [k for k, _d in current]
    headers = []
    for key, label, sort_key in columns:
        item = {"key": key, "label": label, "sort": sort_key,
                "next": "", "arrow": "", "priority": ""}
        if sort_key:
            if sort_key in active:
                index = active.index(sort_key)
                desc = current[index][1]
                item["arrow"] = "down" if desc else "up"
                item["priority"] = index + 1 if len(current) > 1 else ""
                first = (sort_key, (not desc) if index == 0 else desc)
            else:
                first = (sort_key, False)
            keys = [first] + [(k, d) for k, d in current if k != sort_key]
            item["next"] = ",".join(
                ("-" if d else "") + k for k, d in keys[:MAX_SORT_KEYS])
        headers.append(item)
    return headers, current


def sort_rows(rows, current, getters, default_key):
    """
    Sort dict/object rows by [(key, desc)]; empty values always last.

    ---

    Ordena las filas por las claves pedidas (sin dato, siempre al
    final); sin orden elegido, por `default_key`.
    """
    rows = sorted(rows, key=getters[default_key])
    for key, desc in reversed(current):
        getter = getters[key]
        present = [r for r in rows if getter(r) not in (None, "")]
        empty = [r for r in rows if getter(r) in (None, "")]
        present.sort(key=getter, reverse=desc)
        rows = present + empty
    return rows
