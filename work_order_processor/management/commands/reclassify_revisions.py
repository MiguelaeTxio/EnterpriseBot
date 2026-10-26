# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/reclassify_revisions.py
"""
H30 (S137). Re-run the task classification on the work order blocks that
may be a service (oil and filter change) and mark them REVISION.

---

H30 (S137). Miguel Ángel: la revisión (cambio de aceite y filtros) tiene
que estar clara en la clasificación. Hasta ahora no había tipo propio y
las revisiones quedaban repartidas entre Mantenimiento ("mantenimiento
general", "revisión general"...), Avería y bloques sin clasificar.

Este comando vuelve a pasar por Gemini (classify_task, con el prompt que
ya conoce el tipo REVISION) los bloques candidatos:
- su texto (descripción o notas) habla de revisión (con o sin tilde),
  aceite o filtros, o
- Gemini ya les puso una categoría libre de revisión o de mantenimiento
  preventivo.

Solo se cambia un bloque si Gemini dice ahora REVISION; el resto se
queda como estaba. Con --dry-run se llama a Gemini y se apunta qué
diría, sin guardar nada. Al final lista los bloques que son revisión
(máquina, fecha y texto): son el punto de partida para recuperar las
revisiones ya hechas.
"""
import time
from datetime import datetime
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q

from work_order_processor.models import WorkOrderEntryLine
from work_order_processor.services import classify_task

REVISION = "REVISION"
HEARTBEAT_EVERY = 10
TEXT_PATTERN = r"revisi|aceite|filtro"
FREE_PATTERN = r"revisi|preventiv"


class Command(BaseCommand):
    """
    Mark as REVISION the blocks Gemini now sees as a service.

    ---

    Marca como REVISION los bloques que Gemini ve ahora como revisión.
    """

    help = (
        "Vuelve a clasificar con Gemini los bloques de parte que pueden "
        "ser una revisión y los marca REVISION (H30, S137)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Llama a Gemini y apunta lo que diría, sin guardar.",
        )

    def _write(self, line):
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def _log(self, message):
        self._write(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _heartbeat(self, done, total, counters):
        """
        Progress line with ETA every few blocks.

        ---

        Línea de progreso con ETA cada pocos bloques.
        """
        if done % HEARTBEAT_EVERY and done != total:
            return
        elapsed = (datetime.now() - self._start).total_seconds()
        eta = (elapsed / done) * (total - done) if done else 0
        end = (datetime.now() + timedelta(seconds=eta)).strftime("%H:%M:%S")
        self._log(
            "Progreso: %d/%d bloques (%d%%) -- ETA %dm%02ds (fin aprox. "
            "%s) -- revision=%d, sin_cambio=%d, errores=%d"
            % (done, total, done * 100 // total, eta // 60, eta % 60, end,
               counters["revision"], counters["unchanged"],
               counters["errors"]))

    def _classify(self, line):
        """
        Call classify_task, retrying on Vertex AI 429; None on error.

        ---

        Llama a classify_task, con reintentos ante el 429 de Vertex AI
        (mismo contrato que backfill_task_types); None si falla.
        """
        for attempt in range(1, 4):
            try:
                return classify_task(
                    fault_description=line.fault_description or "",
                    repair_notes=line.repair_notes or "",
                )
            except Exception as exc:
                text = str(exc)
                if ("429" in text or "RESOURCE_EXHAUSTED" in text) and (
                        attempt < 3):
                    self._log("pk=%d: 429 de Vertex AI (intento %d de 3), "
                              "espero 60 s." % (line.pk, attempt))
                    time.sleep(60)
                    continue
                self._log("pk=%d: error de Gemini -- %s" % (line.pk, exc))
                return None
        return None

    def _save(self, line, result):
        """
        Store REVISION on the block and on its ticket, if any.

        ---

        Guarda REVISION en el bloque y, si lo tiene, en su ticket.
        """
        WorkOrderEntryLine.objects.filter(pk=line.pk).update(
            tipo_tarea=REVISION,
            task_category_free=result["task_category_free"],
            fault_category="",
            fault_subcategory="",
        )
        ticket = line.breakdown_ticket
        if ticket is not None:
            ticket.tipo_tarea = REVISION
            ticket.fault_category = ""
            ticket.task_category_free = result["task_category_free"]
            ticket.save(update_fields=[
                "tipo_tarea", "fault_category", "task_category_free"])

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        wanted = (Q(fault_description__iregex=TEXT_PATTERN) |
                  Q(repair_notes__iregex=TEXT_PATTERN) |
                  Q(task_category_free__iregex=FREE_PATTERN))
        candidates = WorkOrderEntryLine.objects.filter(wanted).exclude(
            tipo_tarea=REVISION).select_related(
            "entry", "machine_asset", "breakdown_ticket").order_by("id")
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._start = datetime.now()
            total = candidates.count()
            self._log("Inicio%s: %d bloques candidatos a revisión." % (
                " (DRY-RUN, no se guarda nada)" if dry_run else "", total))
            counters = {"revision": 0, "unchanged": 0, "errors": 0}
            found = []
            for done, line in enumerate(candidates.iterator(), start=1):
                result = self._classify(line)
                if result is None:
                    counters["errors"] += 1
                elif result["tipo_tarea"] == REVISION:
                    counters["revision"] += 1
                    found.append((line, result["task_category_free"]))
                    if not dry_run:
                        self._save(line, result)
                    self._log("pk=%d: %s -> REVISION (%s)%s" % (
                        line.pk, line.tipo_tarea or "sin clasificar",
                        result["task_category_free"],
                        "" if dry_run else ", guardado"))
                else:
                    counters["unchanged"] += 1
                    self._log("pk=%d: sigue %s (Gemini dice %s)" % (
                        line.pk, line.tipo_tarea or "sin clasificar",
                        result["tipo_tarea"] or "nada"))
                self._heartbeat(done, total, counters)
            self._write("")
            self._write("Bloques que son revisión (%d):" % len(found))
            self._write("máquina | fecha | qué se cambió | texto del parte")
            for line, what in found:
                code = (line.machine_asset.code if line.machine_asset
                        else line.machine_raw or "?")
                when = line.entry.work_date
                text = " / ".join(
                    part for part in (line.fault_description,
                                      line.repair_notes) if part)
                self._write("%s | %s | %s | %s" % (
                    code, when.strftime("%d/%m/%Y") if when else "?",
                    what, " ".join(text.split())[:200]))
            self._write("")
            self._write(
                "Resumen%s: %d bloques pasan a revisión, %d se quedan "
                "como estaban y %d con error de Gemini." % (
                    " (DRY-RUN)" if dry_run else "", counters["revision"],
                    counters["unchanged"], counters["errors"]))
            self._write("Fin.")
