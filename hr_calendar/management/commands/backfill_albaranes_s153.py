# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/backfill_albaranes_s153.py
"""
Backfill the work delivery notes already uploaded (S149) before S153.

---

S153 (Miguel Ángel: "Sube los albaranes de trabajo que haya en el
servidor al cubo [...] también con los que ya estaban [...] es
necesario extraer los datos"). Para cada archivo de albaranes ya
cargado:
1. Si no está en el cubo, lo sube a <carpeta del trabajador>/ALBARANES
   DE TRABAJO/ (albaran_check.archive_in_bucket) y lo anota en todos
   los albaranes que salieron de él.
2. Si no tiene la copia digital completa, la saca con Gemini
   (albaran_full.store_full).
Sin --apply solo cuenta lo que haría. Log propio, pantalla y archivo a
la vez, con progreso y ETA (com-standards 0bis/0ter).
"""
import datetime
import os
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    """
    Upload old work albaranes to the bucket and extract all their data.
    ---
    Sube al cubo los albaranes de trabajo ya cargados y saca sus datos.
    """

    help = "Sube al cubo los albaranes de trabajo y extrae todos sus datos."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        line = "[%s] %s" % (timezone.localtime().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def _plain(self, text):
        print(text, flush=True)
        self._out.write(text + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._run(options["apply"])

    def _run(self, apply):
        from hr_calendar.albaran_check import (
            AlbaranError, archive_in_bucket, mime_of, staged_bytes,
        )
        from hr_calendar.albaran_full import store_full
        from hr_calendar.models import AlbaranSheet

        files = defaultdict(list)
        for sheet in AlbaranSheet.objects.select_related(
                "batch__person").order_by("staged_path", "position"):
            files[(sheet.batch_id, sheet.staged_path)].append(sheet)
        total = len(files)
        self._log("Albaranes de trabajo: %d archivos, %d albaranes (%s)" % (
            total, sum(len(v) for v in files.values()),
            "APLICANDO" if apply else "simulación, sin cambios"))
        start = datetime.datetime.now()
        counts = defaultdict(int)
        for index, ((_batch, path), sheets) in enumerate(files.items(), 1):
            first = sheets[0]
            label = "%s (%s, %d albarán/es)" % (
                first.original_name, first.person or first.batch.person,
                len(sheets))
            # S149: un albarán sin trabajador (carga de varios) no va al cubo.
            need_bucket = not first.bucket_blob and bool(
                first.person_id or first.batch.person_id)
            need_full = any(s.full_read_at is None for s in sheets
                            if s.status == AlbaranSheet.Status.READ)
            if not need_bucket and not need_full:
                counts["ya completos"] += 1
                continue
            try:
                data = staged_bytes(first)
            except (OSError, AlbaranError) as exc:
                self._plain("  ✗ %s: no está en el servidor (%s)" % (
                    label, exc))
                counts["sin archivo en el servidor"] += 1
                continue
            mime = mime_of(data)
            if need_bucket:
                if apply:
                    try:
                        blob = archive_in_bucket(
                            first.batch, first.original_name, data, mime,
                            os.path.splitext(path)[1].lstrip(".") or "pdf",
                            person=first.person or first.batch.person)
                    except AlbaranError as exc:
                        self._plain("  ✗ %s: %s" % (label, exc))
                        counts["error al subir al cubo"] += 1
                        continue
                    AlbaranSheet.objects.filter(
                        pk__in=[s.pk for s in sheets]).update(
                        bucket_blob=blob)
                    self._plain("  ↑ %s -> %s" % (label, blob))
                counts["subidos al cubo"] += 1
            if need_full:
                read = [s for s in sheets
                        if s.status == AlbaranSheet.Status.READ]
                if apply:
                    try:
                        saved = store_full(read, data, mime)
                    except Exception as exc:  # noqa: BLE001
                        self._plain("  ✗ %s: sin datos completos (%s)" % (
                            label, exc))
                        counts["error al extraer"] += 1
                        continue
                    self._plain("  ✓ %s: %d copia(s) completa(s)" % (
                        label, saved))
                    counts["albaranes con datos completos"] += saved
                else:
                    counts["albaranes con datos completos"] += len(read)
            if index % 5 == 0 or index == total:
                elapsed = (datetime.datetime.now() - start).total_seconds()
                left = elapsed / index * (total - index)
                end = datetime.datetime.now() + datetime.timedelta(
                    seconds=left)
                self._log("Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin "
                          "aprox. %s)" % (
                              index, total, 100 * index // total,
                              left // 60, left % 60,
                              end.strftime("%H:%M:%S")))
        self._plain("")
        self._plain("RESUMEN")
        for key in sorted(counts):
            self._plain("  %s: %d" % (key, counts[key]))
        if not apply:
            self._plain("Simulación: no se ha cambiado nada.")
