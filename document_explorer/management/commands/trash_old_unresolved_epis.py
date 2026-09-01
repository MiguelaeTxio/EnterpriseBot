# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/trash_old_unresolved_epis.py
"""
H30 (S82) -- Miguel Angel, verbatim: "los EPIs que se hayan entregado
hace mas de cinco anos, que esten dentro de estos 300 y pico que
tenemos que faltan, pues no complicarnos y enviarlos a la papelera."

Entre los EPIS activos, ya leidos (ocr_text cacheado) pero sin
resolver del todo (SIN DNI, SIN ITEMS, SIN FECHA, DNI sin
PersonIdentity), esta pasada decide la antiguedad con la mejor fecha
disponible -- la fecha real de entrega si el texto la trae (misma
logica que reprocess_epis_from_cache), y si no, el ano suelto de 4
digitos que casi todos estos documentos llevan en el propio nombre de
archivo ("EPIS 2009 ...") -- y manda a la papelera (deleted_at,
nunca borrado real de GCS, 4.12) los que tengan 5 anos o mas de
antiguedad. Nunca inventa la fecha: si no hay ningun ano localizable
ni por contenido ni por nombre, el documento queda tal cual, fuera de
esta pasada.

DRY-RUN POR DEFECTO. Con --apply escribe deleted_at/deleted_by de
verdad.
"""
import datetime
import re

from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.models import DocumentIndexEntry

# Duplicado a proposito de reprocess_epis_from_cache.py -- misma
# logica verificada hoy, nunca se comparte modulo con el script de la
# VM (sin Django instalado alli).
_CONTENT_DATE_RE = re.compile(
    r"(?:A\s+fecha|FECHA)\s*[:.(]?\s*(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{2,4})",
    re.IGNORECASE,
)
_FILENAME_DATE_RE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{2,4})")
_LOOSE_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

ANIOS_ANTIGUEDAD = 5


def _build_date(day, month, year):
    year = int(year)
    if year < 100:
        year += 2000
    hoy = datetime.date.today()
    if not (2005 <= year <= hoy.year):
        return None
    try:
        return datetime.date(year, int(month), int(day))
    except ValueError:
        return None


def _best_year(entry):
    """Devuelve (anio, origen) -- fecha real de contenido/nombre si
    existe (mas fiable), si no el ano suelto del nombre de archivo
    (menos fiable, pero suficiente para decidir antiguedad)."""
    match = _FILENAME_DATE_RE.search(entry.name)
    if match:
        d = _build_date(*match.groups())
        if d:
            return d.year, "fecha en nombre de archivo"
    match = _CONTENT_DATE_RE.search(entry.ocr_text or "")
    if match:
        d = _build_date(*match.groups())
        if d:
            return d.year, "fecha en contenido"
    match = _LOOSE_YEAR_RE.search(entry.name)
    if match:
        return int(match.group(0)), "año suelto en nombre de archivo"
    return None, None


class Command(BaseCommand):
    help = (
        "H30 (S82) -- manda a la papelera los EPIS activos, ya "
        "leidos pero sin resolver, cuya mejor fecha disponible tenga "
        "%d anos o mas. Dry-run por defecto, usar --apply."
        % ANIOS_ANTIGUEDAD
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        corte = datetime.date.today().year - ANIOS_ANTIGUEDAD

        qs = DocumentIndexEntry.objects.filter(
            document_type__code="EPIS",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        ).exclude(ocr_text__in=["", None])

        stats = {"antiguos_papelera": 0, "sin_anio_localizable": 0, "recientes_sin_tocar": 0}

        for entry in qs.iterator():
            anio, origen = _best_year(entry)
            if anio is None:
                stats["sin_anio_localizable"] += 1
                continue
            if anio > corte:
                stats["recientes_sin_tocar"] += 1
                continue

            stats["antiguos_papelera"] += 1
            self.stdout.write(
                "%s  id=%d  año=%d (%s)  [%s]"
                % (
                    "APLICADO" if apply_changes else "CANDIDATO",
                    entry.pk, anio, origen, entry.name,
                )
            )
            if apply_changes:
                trash_dossier_entry(entry)

        self.stdout.write("=== RESUMEN (%s, corte año <= %d) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito", corte,
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
