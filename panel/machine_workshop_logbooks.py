# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/machine_workshop_logbooks.py
"""
H23 (S154, invasora). "Libros historial" list of a machine's workshop.

---

H23 (S154, invasora). Pestaña "Libros historial" del taller de una
máquina (junto a Partes de trabajo y Averías), con el mismo formato de
listado (directriz 4.24): los documentos LIBRO_HISTORIAL (escaneados y
generados por la plataforma) y ORDEN_TRABAJO_MANTENIMIENTO de la
máquina, vigentes e históricos (regla 8: nada se pierde de vista).
Miguel Ángel (S154): "una vista nueva en la que se vean los partes de
trabajo por una pestaña, en otra pestaña los libros de historial".
"""
import datetime
from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType

from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset, MachineLogbookSource
from panel.machine_workshop import (
    _matches, _sort_rows, _user_name, _words, parse_date, parse_sort,
)

LOGBOOK_TYPE_CODES = ("LIBRO_HISTORIAL", "ORDEN_TRABAJO_MANTENIMIENTO")
LOGBOOK_FILTER_KEYS = (
    "search", "state", "origin", "doc_type", "date_from", "date_to", "sort",
)
STATE_CURRENT = "current"
STATE_HISTORIC = "historic"
ORIGIN_GENERATED = "generated"
ORIGIN_SCANNED = "scanned"
ORIGIN_CHOICES = (
    (ORIGIN_GENERATED, "Generado por la plataforma"),
    (ORIGIN_SCANNED, "Escaneado o subido"),
)

# (clave, etiqueta, si se suma en la fila de totales) -- mismo formato
# que las columnas de Partes de trabajo y Averías.
LOGBOOK_COLUMNS = (
    ("type", "Tipo", False),
    ("date", "Fecha", False),
    ("name", "Archivo", False),
    ("origin", "Origen", False),
    ("state", "Estado", False),
    ("rows", "Filas leídas", True),
    ("by", "Generado por", False),
)

_DATE_MIN = datetime.date.min


@dataclass
class LogbookRow:
    """
    One logbook or maintenance-order document of the machine.

    ---

    Un documento de libro historial u orden de mantenimiento de la
    máquina, ya resuelto para la plantilla.
    """

    entry: DocumentIndexEntry
    source: MachineLogbookSource = None
    key: str = ""
    label: str = ""
    haystack: str = ""
    type_label: str = ""
    date: datetime.date = None
    origin_label: str = ""
    is_generated: bool = False
    is_current: bool = True
    rows_found: int = 0
    read_error: str = ""
    generated_by: str = ""

    def __post_init__(self):
        entry = self.entry
        self.key = "d%d" % entry.pk
        self.type_label = (
            entry.document_type.label if entry.document_type_id else ""
        )
        self.date = entry.issue_date or entry.expiry_date
        self.is_current = not entry.is_obsolete
        source = self.source
        self.is_generated = bool(
            source and source.kind == MachineLogbookSource.KIND_GENERATED
        )
        self.origin_label = (
            "Generado por la plataforma" if self.is_generated
            else "Escaneado o subido"
        )
        if source and not self.is_generated:
            self.rows_found = source.rows_found
            self.read_error = source.error
        if self.is_generated:
            self.generated_by = _user_name(source.created_by)
        self.label = "%s · %s" % (
            self.date.strftime("%d/%m/%Y") if self.date else "sin fecha",
            entry.name,
        )
        self.haystack = " ".join([
            entry.name, self.type_label, self.origin_label,
            self.generated_by,
        ]).lower()


LOGBOOK_SORTABLE = {
    "type": lambda r: r.type_label.lower(),
    "date": lambda r: r.date or _DATE_MIN,
    "name": lambda r: r.entry.name.lower(),
    "origin": lambda r: r.origin_label,
    "state": lambda r: r.is_current,
    "rows": lambda r: r.rows_found,
    "by": lambda r: r.generated_by.lower(),
}
LOGBOOK_DEFAULT_ORDER = (("date", True),)


def _machine_entries(machine):
    """
    Live logbook and maintenance-order documents of the machine.

    ---

    Documentos vivos (no en papelera) de libro historial y orden de
    mantenimiento de la máquina.
    """
    return DocumentIndexEntry.objects.filter(
        domain_content_type=ContentType.objects.get_for_model(MachineAsset),
        domain_object_id=machine.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True,
        purged_at__isnull=True,
        document_type__code__in=LOGBOOK_TYPE_CODES,
    ).select_related(
        "document_type", "logbook_source__created_by__user",
    )


def _source_of(entry):
    try:
        return entry.logbook_source
    except MachineLogbookSource.DoesNotExist:
        return None


def build_logbook_rows(machine, params, only_keys=None):
    """
    Rows of the logbooks list with the filters and the order applied.

    ---

    Filas del listado de libros con los filtros y el orden aplicados.
    Con `only_keys` (mostrar solo la selección) se ignoran los filtros.
    """
    entries = _machine_entries(machine)
    if only_keys is not None:
        pks = [
            int(key[1:]) for key in only_keys
            if key[:1] == "d" and key[1:].isdigit()
        ]
        entries = entries.filter(pk__in=pks)
    rows = [LogbookRow(entry, _source_of(entry)) for entry in entries]
    if only_keys is None:
        state = params.get("state") or ""
        if state == STATE_CURRENT:
            rows = [row for row in rows if row.is_current]
        elif state == STATE_HISTORIC:
            rows = [row for row in rows if not row.is_current]
        elif state == "none":
            rows = []
        origin = params.get("origin") or ""
        if origin == ORIGIN_GENERATED:
            rows = [row for row in rows if row.is_generated]
        elif origin == ORIGIN_SCANNED:
            rows = [row for row in rows if not row.is_generated]
        doc_type = params.get("doc_type") or ""
        if doc_type in LOGBOOK_TYPE_CODES:
            rows = [
                row for row in rows
                if row.entry.document_type.code == doc_type
            ]
        date_from = parse_date(params.get("date_from"))
        date_to = parse_date(params.get("date_to"))
        if date_from:
            rows = [row for row in rows if row.date and row.date >= date_from]
        if date_to:
            rows = [row for row in rows if row.date and row.date <= date_to]
        words = _words(params.get("search"))
        if words:
            rows = [row for row in rows if _matches(words, row.haystack)]
    return _sort_rows(
        rows, parse_sort(params.get("sort"), LOGBOOK_SORTABLE),
        LOGBOOK_SORTABLE, LOGBOOK_DEFAULT_ORDER,
    )


def logbook_totals(rows):
    """
    Totals of the listed rows.

    ---

    Totales de lo listado: documentos, vigentes, generados y filas
    leídas de los escaneos.
    """
    return {
        "count": len(rows),
        "current": sum(1 for row in rows if row.is_current),
        "generated": sum(1 for row in rows if row.is_generated),
        "rows": sum(row.rows_found for row in rows),
    }


def logbook_type_options():
    """
    Document types of the "Tipo" filter.

    ---

    Tipos de documento del filtro "Tipo", con su etiqueta del catálogo.
    """
    from document_explorer.models import DocumentTypeCatalog

    labels = dict(
        DocumentTypeCatalog.objects.filter(
            code__in=LOGBOOK_TYPE_CODES,
        ).values_list("code", "label")
    )
    return [(code, labels.get(code, code)) for code in LOGBOOK_TYPE_CODES]


def selected_entries(machine, keys):
    """
    Live documents of the machine among the selected keys.

    ---

    Documentos vivos de la máquina entre las claves seleccionadas
    (d<pk>), para la descarga en ZIP.
    """
    pks = [
        int(key[1:]) for key in keys
        if key[:1] == "d" and key[1:].isdigit()
    ]
    return list(_machine_entries(machine).filter(pk__in=pks))
