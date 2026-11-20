# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/listing.py
"""
Multi-key sort shared by the three lists of the Cranes page (H11, S162).

---

Orden múltiple con prioridad (directriz 4.24, punto 2) de los tres
listados de la página Grúas: el mismo que Equipos (panel/views_crews.py)
pero con las columnas de cada listado como parámetro.
"""

MAX_SORT_KEYS = 4


def csv_param(request, key, default):
    """
    Comma list from GET, or the default when absent.
    ---
    Lista separada por comas del GET; si no viene, la de por defecto.
    """
    if key in request.GET:
        return [v for v in request.GET.get(key, "").split(",") if v]
    return list(default)


def parse_sort(raw, columns):
    """
    "key,-key" -> [(key, desc)], only valid keys, at most four.
    ---
    "clave,-clave" -> [(clave, descendente)], solo claves válidas.
    """
    valid = {key for key, _label in columns}
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in valid and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:MAX_SORT_KEYS]


def sort_controls(raw, columns):
    """
    Header links: promote a column, flip the main one.
    ---
    Enlaces de cabecera: una columna pasa a criterio principal; la
    principal invierte su sentido.
    """
    sort_keys = parse_sort(raw, columns)
    active = [key for key, _desc in sort_keys]
    result = []
    for key, label in columns:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(sort_keys) > 1 else ""
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        result.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(("-" if d else "") + k
                             for k, d in new_keys[:MAX_SORT_KEYS]),
        })
    return {
        "sort_columns": result,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(("-" if d else "") + k
                                 for k, d in sort_keys),
    }


def sort_rows(rows, sort_keys):
    """
    Stable sort by several keys; empty values last.
    ---
    Orden estable por varias claves; los vacíos al final.
    """
    for key, desc in reversed(sort_keys):
        present = [r for r in rows if r["sort"].get(key) is not None]
        missing = [r for r in rows if r["sort"].get(key) is None]
        rows = sorted(present, key=lambda r: r["sort"][key],
                      reverse=desc) + missing
    return rows
