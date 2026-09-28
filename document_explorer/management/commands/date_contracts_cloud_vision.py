# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/date_contracts_cloud_vision.py
"""
H30 (S122). Date the employment contracts (CONTRATO) of active workers
by reading the document with Cloud Vision, cross-checked against the
date in the file name.

---

H30 (S122). Fecha los contratos (CONTRATO) de trabajadores activos
leyendo el propio documento con Cloud Vision, cruzado con la fecha del
nombre del archivo. Origen: los periodos de contratación exigen un
contrato a ±15 días de cada alta, y un contrato sin fecha nunca se
empareja. Medido en S122: la fecha del nombre coincide con la leída
del documento (±15 días) en el 84 % de los contratos ya fechados, pero
no en el 16 % -- ni el nombre ni el OCR solos son fiables. Decisión de
Miguel Ángel: "por Google Cloud Vision desde PythonAnywhere", con la
regla cruzada (opción 3):

- Documento y nombre coinciden a ±15 días -> se escribe la fecha
  leída del documento (`issue_date` = inicio del contrato).
- Discrepan, el documento no da fecha o el nombre no la lleva -> NO se
  escribe nada; el contrato sale en la lista de revisión manual.

Alcances (`--scope`):
- `undated` (defecto): contratos sin fecha.
- `mismatched`: contratos ya fechados cuya fecha discrepa más de 15
  días de la del nombre -- se relee el documento; si la lectura nueva
  coincide con el nombre, se corrige; si no, a revisión.

Lector: `cloud_vision_service.extract_text_for_dates()` (texto
embebido del PDF, después Cloud Vision, con reintento en las páginas
3-4) -- NUNCA Tesseract en PythonAnywhere (decisión S102). El texto
leído se cachea en `ocr_text`. No retipa, no renombra, no mueve nada.

DRY-RUN POR DEFECTO. `--apply` escribe. `--log-file` obligatorio:
log propio en pantalla y en archivo a la vez.
"""
import re
from datetime import date, datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.employment_period_service import MATCH_WINDOW_DAYS
from document_explorer.models import DocumentIndexEntry, PersonIdentity

BUCKET = "cgs_grupo_alvarez"
_NAME_DATE_RE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")


def filename_date(name):
    """
    YYYYMMDD date embedded in a file name, or None.

    ---

    Fecha AAAAMMDD del nombre del archivo (convención canónica de la
    plataforma), o None si no la lleva o no es una fecha real.
    """
    match = _NAME_DATE_RE.search(name or "")
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def agrees(date_a, date_b):
    """
    True if both dates exist and are within the matching window.

    ---

    True si las dos fechas existen y están a ±15 días.
    """
    if date_a is None or date_b is None:
        return False
    return abs((date_a - date_b).days) <= MATCH_WINDOW_DAYS


class Command(BaseCommand):
    """
    Cross-checked dating of employment contracts.

    ---

    Fechado cruzado (documento + nombre) de contratos.
    """

    help = (
        "Fecha contratos de trabajadores activos con Cloud Vision, "
        "cruzado con la fecha del nombre (H30, S122)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--scope", choices=("undated", "mismatched"), default="undated",
        )
        parser.add_argument("--limit", type=int, default=40)
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(options)

    def _candidates(self, scope, limit):
        """
        Contracts of active workers in the requested scope.

        ---

        Contratos de trabajadores activos del alcance pedido.
        """
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        active_ids = list(
            PersonIdentity.objects.filter(
                is_active_employee=True,
            ).values_list("pk", flat=True),
        )
        base = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, domain_content_type=person_ct,
            domain_object_id__in=active_ids,
            document_type__code="CONTRATO",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).order_by("pk")
        if scope == "undated":
            return list(base.filter(issue_date__isnull=True)[:limit])
        mismatched = [
            entry for entry in base.filter(~Q(issue_date=None))
            if filename_date(entry.name) is not None
            and not agrees(filename_date(entry.name), entry.issue_date)
        ]
        return mismatched[:limit]

    def _run(self, options):
        from document_explorer.cloud_vision_service import (
            extract_text_for_dates,
        )
        from spare_parts.gcs_service import download_bytes

        apply_changes = options["apply"]
        scope = options["scope"]
        people = {
            p.pk: "%s %s, %s" % (
                p.first_surname, p.second_surname or "", p.given_name,
            )
            for p in PersonIdentity.objects.filter(is_active_employee=True)
        }
        entries = self._candidates(scope, options["limit"])
        self._log(
            "Inicio: contratos, alcance=%s, %s, %d candidato(s)."
            % (scope, "APLICANDO" if apply_changes else "DRY-RUN",
               len(entries))
        )
        written, confirmed, review = 0, 0, []
        for position, entry in enumerate(entries, start=1):
            name_date = filename_date(entry.name)
            label = "%d/%d pk=%d %s | %s" % (
                position, len(entries), entry.pk,
                people.get(entry.domain_object_id, "?"), entry.name,
            )
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                text, _expiry, doc_date, _other, pages = (
                    extract_text_for_dates(entry.name, data)
                )
            except Exception as exc:
                review.append((entry, name_date, None, "error de lectura"))
                self._log("%s -> ERROR leyendo: %s" % (label, exc))
                continue

            if agrees(doc_date, name_date):
                if entry.issue_date == doc_date:
                    confirmed += 1
                    self._log(
                        "%s -> ya correcta (%s)" % (label, doc_date),
                    )
                    continue
                written += 1
                self._log(
                    "%s -> %s: documento %s, nombre %s, antes %s "
                    "(páginas leídas: %d)"
                    % (label, "ESCRITA" if apply_changes else "se escribiría",
                       doc_date, name_date, entry.issue_date, pages)
                )
                if apply_changes:
                    entry.issue_date = doc_date
                    entry.ocr_text = text or entry.ocr_text
                    entry.save(update_fields=["issue_date", "ocr_text"])
                continue

            reason = (
                "el documento no da fecha" if doc_date is None
                else "el nombre no lleva fecha" if name_date is None
                else "documento y nombre discrepan"
            )
            review.append((entry, name_date, doc_date, reason))
            self._log(
                "%s -> A REVISIÓN: %s (documento %s, nombre %s, actual %s)"
                % (label, reason, doc_date, name_date, entry.issue_date)
            )
            if apply_changes and text:
                entry.ocr_text = text
                entry.save(update_fields=["ocr_text"])

        self._log("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log("  fechas %s: %d" % (
            "escritas" if apply_changes else "a escribir", written,
        ))
        self._log("  ya correctas: %d" % confirmed)
        self._log("  a revisión manual: %d" % len(review))
        for entry, name_date, doc_date, reason in review:
            self._log(
                "    pk=%d %s | %s | documento %s, nombre %s -- %s"
                % (entry.pk, people.get(entry.domain_object_id, "?"),
                   entry.name, doc_date, name_date, reason)
            )
