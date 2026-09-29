# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/redate_boilerplate_documents.py
"""
H30 (S123). Re-date documents whose stored date is a known form
boilerplate date, by reading them again with the current engine.

---

H30 (S123). Vuelve a fechar los documentos cuya fecha guardada es una
fecha de plantilla del impreso, leyéndolos otra vez con el motor
actual. Origen: el Modelo 145 de Miguel Ángel (id 43990) estaba fechado
el 01/01/2013 ("...vivienda habitual antes del 1 de enero de 2013",
condición del impreso de la AEAT), más de una década antes de su
primera alta. Medido en S123: 81 de los 86 Modelos 145 fechados antes
del primer alta de su persona llevan justo esa fecha.

El motor actual ya descarta esas fechas de condición (patrón "antes
del" en date_verification_service, S123) y lee la página renderizada
cuando la capa de texto de un formulario rellenable no trae los
valores (cloud_vision_service, S123). Este comando lo aplica a lo ya
guardado:

- Selección: tipos `--type` (uno o varios) con `issue_date` igual a
  alguna `--wrong-date`, no borrados.
- Lectura: el archivo real de GCS con `extract_text_for_dates()`
  (texto embebido, página renderizada con Cloud Vision, páginas 3-4) --
  NUNCA la fecha del nombre del archivo, que se puso a partir de la
  fecha mala y la repetiría.
- Fecha nueva: la de emisión leída; si no hay, una única fecha sin
  contexto (mismo criterio que la subida desde la ficha); si tampoco,
  SIN FECHA -- mejor sin fecha que una fecha falsa.
- Se escriben `issue_date` y `ocr_text`. No retipa, no renombra (los
  nombres siguen llevando la fecha antigua), no mueve nada.

DRY-RUN POR DEFECTO. `--apply` escribe. `--log-file` obligatorio: log
propio en pantalla y en archivo a la vez.
"""
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError

from document_explorer.models import DocumentIndexEntry

BUCKET = "cgs_grupo_alvarez"


class Command(BaseCommand):
    """
    Re-date documents stored with a boilerplate date.

    ---

    Vuelve a fechar documentos guardados con una fecha de plantilla.
    """

    help = (
        "Relee y vuelve a fechar documentos con una fecha de plantilla "
        "(H30, S123). Dry-run por defecto; --apply escribe."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--type", action="append", required=True, dest="types",
            help="Código de tipo (repetible), p. ej. MOD_145.",
        )
        parser.add_argument(
            "--wrong-date", action="append", required=True,
            dest="wrong_dates",
            help="Fecha de plantilla AAAA-MM-DD (repetible).",
        )
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=200)
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
        try:
            wrong_dates = [
                date.fromisoformat(value) for value in options["wrong_dates"]
            ]
        except ValueError as exc:
            raise CommandError("Fecha con formato inválido: %s" % exc)
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(
                options["types"], wrong_dates, options["apply"],
                options["limit"],
            )

    def _run(self, types, wrong_dates, apply, limit):
        from document_explorer.cloud_vision_service import (
            extract_text_for_dates,
        )
        from spare_parts.gcs_service import download_bytes

        mode = "APPLY" if apply else "DRY-RUN"
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__code__in=types, issue_date__in=wrong_dates,
        ).select_related("document_type").order_by("id")[:limit])
        self._log(
            "Inicio (%s): tipos %s, fechas %s -- %d documento(s)."
            % (mode, ",".join(types),
               ",".join(d.isoformat() for d in wrong_dates), len(entries))
        )

        counts = {"fechado": 0, "sin_fecha": 0, "error": 0}
        for position, entry in enumerate(entries, start=1):
            prefix = "%d/%d id=%d %s" % (
                position, len(entries), entry.pk, entry.name,
            )
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                text, _expiry, issue, other, pages = (
                    extract_text_for_dates(entry.name, data)
                )
            except Exception as exc:  # noqa: BLE001 -- se registra y sigue
                counts["error"] += 1
                self._log("%s -- ERROR al leer: %s" % (prefix, exc))
                continue

            new_date = issue or (other[0] if len(other) == 1 else None)
            counts["fechado" if new_date else "sin_fecha"] += 1
            self._log(
                "%s -- %s -> %s (páginas leídas: %d)"
                % (prefix, entry.issue_date.isoformat(),
                   new_date.isoformat() if new_date else "SIN FECHA", pages)
            )
            if apply:
                entry.issue_date = new_date
                entry.ocr_text = text or entry.ocr_text
                entry.save(update_fields=["issue_date", "ocr_text"])

        self._log(
            "Fin (%s): %d con fecha nueva, %d sin fecha, %d con error."
            % (mode, counts["fechado"], counts["sin_fecha"], counts["error"])
        )
