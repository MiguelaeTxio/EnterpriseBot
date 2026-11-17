# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/machine_workshop_reviews.py
"""
H23 (S154, invasora). "Revisiones" list of a crane's workshop.

---

H23 (S154, invasora). Pestaña "Revisiones" del taller de una grúa A/H
(directriz 4.24, mismo formato que Libros historial): las revisiones
técnicas periódicas leídas de los escaneos y las reconstruidas (registro
original extraviado), con los huecos de más de seis meses sin revisión a
la vista. Un hueco se cubre buscando la revisión en su libro y
escaneándola; solo si se perdió de verdad se reconstruye, y la
reconstrucción no vale hasta la firma digital del PC de Yolanda.
"""
import datetime
from dataclasses import dataclass

from fleet import logbook_service
from panel.machine_workshop import (
    _matches, _sort_rows, _words, parse_date, parse_sort,
)

REVIEW_FILTER_KEYS = (
    "search", "state", "origin", "date_from", "date_to", "sort",
)
STATE_REVIEWS = "reviews"
STATE_GAPS = "gaps"
ORIGIN_SCANNED = "scanned"
ORIGIN_PENDING = "pending"
ORIGIN_SIGNING = "signing"
ORIGIN_SIGNED = "signed"
ORIGIN_CHOICES = (
    (ORIGIN_SCANNED, "Libro escaneado"),
    (ORIGIN_PENDING, "Reconstruida, pendiente de firma"),
    (ORIGIN_SIGNING, "Reconstruida, en la cola de firma"),
    (ORIGIN_SIGNED, "Reconstruida y firmada digitalmente"),
)
ORIGIN_LABELS = dict(ORIGIN_CHOICES)

REVIEW_COLUMNS = (
    ("date", "Fecha", False),
    ("concept", "Concepto", False),
    ("entity", "Empresa mantenedora", False),
    ("result", "Resultado", False),
    ("next", "Próxima revisión", False),
    ("origin", "Origen", False),
    ("signed", "Firma", False),
)

_DATE_MIN = datetime.date.min


@dataclass
class ReviewRow:
    """
    One review, or one gap without reviews.

    ---

    Una revisión (escaneada o firmada) o un hueco sin revisiones.
    """

    key: str = ""
    label: str = ""
    is_gap: bool = False
    date: datetime.date = None
    gap_end: datetime.date = None
    gap_days: int = 0
    concept: str = ""
    entity: str = ""
    result: str = ""
    next_date: datetime.date = None
    origin: str = ""
    origin_label: str = ""
    signature_note: str = ""
    created_by_pk: int = None
    haystack: str = ""


def _row_from_entry(entry):
    if not entry.is_reconstructed:
        origin = ORIGIN_SCANNED
    else:
        origin = logbook_service.reconstruction_state(entry)
    row = ReviewRow(
        key="r%d" % entry.pk,
        date=entry.entry_date,
        concept=entry.concept,
        entity=entry.entity,
        result=entry.result,
        next_date=entry.next_date,
        origin=origin,
        origin_label=ORIGIN_LABELS[origin],
        signature_note=getattr(entry, "signature_note", ""),
        created_by_pk=(
            entry.created_by_id if entry.is_reconstructed else None),
    )
    row.label = "%s · %s" % (
        row.date.strftime("%d/%m/%Y") if row.date else "sin fecha",
        row.origin_label,
    )
    row.haystack = " ".join([
        row.concept, row.entity, row.result, row.origin_label,
        row.signature_note,
    ]).lower()
    return row


def _row_from_gap(gap):
    return ReviewRow(
        key="",
        is_gap=True,
        date=gap["start"],
        gap_end=gap["end"],
        gap_days=gap["days"],
        origin_label="Sin revisión anotada",
        haystack="hueco sin revisión",
    )


REVIEW_SORTABLE = {
    "date": lambda r: r.date or _DATE_MIN,
    "concept": lambda r: r.concept.lower(),
    "entity": lambda r: r.entity.lower(),
    "result": lambda r: r.result.lower(),
    "next": lambda r: r.next_date or _DATE_MIN,
    "origin": lambda r: r.origin_label,
}
REVIEW_DEFAULT_ORDER = (("date", True),)


def build_review_rows(machine, params, only_keys=None):
    """
    Rows of the reviews list (reviews and gaps), filtered and sorted.

    ---

    Filas del listado de revisiones (revisiones y huecos) con filtros y
    orden. Con `only_keys` (mostrar solo la selección) se ignoran los
    filtros y no salen huecos.
    """
    entries = logbook_service.review_rows(machine)
    gaps = logbook_service.review_gaps(entries)
    rows = [_row_from_entry(entry) for entry in entries]
    if only_keys is not None:
        rows = [row for row in rows if row.key in only_keys]
    else:
        rows += [_row_from_gap(gap) for gap in gaps]
        state = params.get("state") or ""
        if state == STATE_REVIEWS:
            rows = [row for row in rows if not row.is_gap]
        elif state == STATE_GAPS:
            rows = [row for row in rows if row.is_gap]
        elif state == "none":
            rows = []
        origin = params.get("origin") or ""
        if origin in ORIGIN_LABELS:
            rows = [row for row in rows if row.origin == origin]
        date_from = parse_date(params.get("date_from"))
        date_to = parse_date(params.get("date_to"))
        if date_from:
            rows = [
                row for row in rows
                if (row.gap_end or row.date or _DATE_MIN) >= date_from
            ]
        if date_to:
            rows = [row for row in rows if row.date and row.date <= date_to]
        words = _words(params.get("search"))
        if words:
            rows = [row for row in rows if _matches(words, row.haystack)]
    return _sort_rows(
        rows, parse_sort(params.get("sort"), REVIEW_SORTABLE),
        REVIEW_SORTABLE, REVIEW_DEFAULT_ORDER,
    )


def review_totals(rows):
    """
    Totals of the listed rows.

    ---

    Totales de lo listado: revisiones, reconstruidas y huecos.
    """
    return {
        "count": sum(1 for row in rows if not row.is_gap),
        "rebuilt": sum(
            1 for row in rows
            if row.origin in (ORIGIN_PENDING, ORIGIN_SIGNING, ORIGIN_SIGNED)
        ),
        "gaps": sum(1 for row in rows if row.is_gap),
    }
