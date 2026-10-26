# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/reclassify_revisions.py
"""
H30 (S137). Mark as REVISION the work order blocks whose own text says
they are a service (oil, filters, "revisión", "mantenimiento").

---

H30 (S137). Miguel Ángel: la revisión (cambio de aceite y filtros) tiene
que estar clara en la clasificación, y en este taller "mantenimiento" de
una máquina es lo mismo que revisión: se cambia el aceite y los filtros
que toquen. Hasta ahora no había tipo propio y las revisiones quedaban
repartidas entre Mantenimiento, Avería y bloques sin clasificar.

No usa Gemini (el primer intento, con Gemini, se cortó: el
"Mantenimiento" de Gemini es un cajón de sastre de limpiezas, traslados
y pintura). Manda lo que escribió el mecánico. Un bloque es revisión si:
- es de una máquina (no del activo PERSONAL ni sin máquina),
- su descripción o sus notas dicen revisión (con o sin tilde),
  mantenimiento, mnto, aceite o filtro,
- y no habla de una avería (fuga, pérdida, rotura, roto, avería) ni de
  una revisión médica, ni es uno de los literales especiales (limpieza
  del taller, vacaciones, formación, servicio, ITV).

Con --dry-run solo lista. Al final lista los bloques que son revisión
(máquina, fecha y texto) y los que se dejan fuera por hablar de avería,
para revisarlos a mano: son el punto de partida para recuperar las
revisiones ya hechas.
"""
import re
from datetime import datetime
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q

from work_order_processor.management.commands.seed_personal_asset import (
    PERSONAL_ASSET_CODE,
)
from work_order_processor.models import WorkOrderEntryLine

REVISION = "REVISION"
HEARTBEAT_EVERY = 25
SERVICE_PATTERN = r"revisi|mantenimiento|mnto|aceite|filtro"
FAULT_WORDS = re.compile(r"fuga|p[eé]rdida|rotura|\broto\b|aver[ií]a")
MEDICAL_WORDS = re.compile(r"m[eé]dic")
SPECIAL_LITERALS = (
    "Limpieza y mantenimiento", "Vacaciones", "Formación", "Servicio",
    "ITV",
)


def _text(line):
    """
    Description and notes of a block, joined, on one line.

    ---

    Descripción y notas del bloque, juntas y en una sola línea.
    """
    parts = (line.fault_description, line.repair_notes)
    return " ".join(" / ".join(p for p in parts if p).split())


def _what_changed(text):
    """
    Short label of what the service changed, from the block text.

    ---

    Etiqueta corta de lo que se cambió, sacada del texto del bloque.
    """
    low = text.lower()
    things = [name for word, name in (("aceite", "aceite"),
                                      ("filtro", "filtros"))
              if word in low]
    return "cambio de " + " y ".join(things) if things else "revisión"


class Command(BaseCommand):
    """
    Mark as REVISION the blocks whose text says they are a service.

    ---

    Marca como REVISION los bloques cuyo texto dice que son revisión.
    """

    help = (
        "Marca como REVISION los bloques de parte cuyo texto dice "
        "revisión, mantenimiento, aceite o filtro (H30, S137)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Solo lista, sin guardar nada.",
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
            "%s) -- revision=%d, averia=%d, fuera=%d"
            % (done, total, done * 100 // total, eta // 60, eta % 60, end,
               len(counters["revision"]), len(counters["fault"]),
               counters["out"]))

    def _save(self, line, what):
        """
        Store REVISION on the block and on its ticket, if any.

        ---

        Guarda REVISION en el bloque y, si lo tiene, en su ticket.
        """
        WorkOrderEntryLine.objects.filter(pk=line.pk).update(
            tipo_tarea=REVISION,
            task_category_free=what,
            fault_category="",
            fault_subcategory="",
        )
        ticket = line.breakdown_ticket
        if ticket is not None:
            ticket.tipo_tarea = REVISION
            ticket.fault_category = ""
            ticket.task_category_free = what
            ticket.save(update_fields=[
                "tipo_tarea", "fault_category", "task_category_free"])

    def _list(self, title, rows):
        """
        Write a list of blocks: machine, date, current type and text.

        ---

        Escribe una lista de bloques: máquina, fecha, tipo y texto.
        """
        self._write("")
        self._write("%s (%d):" % (title, len(rows)))
        self._write("bloque | máquina | fecha | tipo antes | texto")
        for line, text in rows:
            when = line.entry.work_date
            self._write("%d | %s | %s | %s | %s" % (
                line.pk, line.machine_asset.code,
                when.strftime("%d/%m/%Y") if when else "?",
                line.tipo_tarea or "sin clasificar", text[:200]))

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        wanted = (Q(fault_description__iregex=SERVICE_PATTERN) |
                  Q(repair_notes__iregex=SERVICE_PATTERN))
        candidates = WorkOrderEntryLine.objects.filter(
            wanted, machine_asset__isnull=False,
        ).exclude(machine_asset__code=PERSONAL_ASSET_CODE).exclude(
            tipo_tarea=REVISION).exclude(
            task_category_free__in=SPECIAL_LITERALS).select_related(
            "entry", "machine_asset", "breakdown_ticket").order_by(
            "machine_asset__code", "entry__work_date", "id")
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._start = datetime.now()
            total = candidates.count()
            self._log("Inicio%s: %d bloques de máquina que dicen revisión, "
                      "mantenimiento, aceite o filtro." % (
                          " (DRY-RUN, no se guarda nada)" if dry_run
                          else "", total))
            counters = {"revision": [], "fault": [], "out": 0}
            for done, line in enumerate(candidates.iterator(), start=1):
                text = _text(line)
                low = text.lower()
                if MEDICAL_WORDS.search(low):
                    counters["out"] += 1
                    self._log("bloque %d: fuera (revisión médica)."
                              % line.pk)
                elif FAULT_WORDS.search(low):
                    counters["fault"].append((line, text))
                    self._log("bloque %d: fuera (habla de avería)."
                              % line.pk)
                else:
                    counters["revision"].append((line, text))
                    if not dry_run:
                        self._save(line, _what_changed(text))
                    self._log("bloque %d: %s -> REVISION (%s)%s" % (
                        line.pk, line.tipo_tarea or "sin clasificar",
                        _what_changed(text),
                        "" if dry_run else ", guardado"))
                self._heartbeat(done, total, counters)
            self._list("Bloques que son revisión", counters["revision"])
            self._list("Fuera por hablar de avería (mirar a mano)",
                       counters["fault"])
            self._write("")
            self._write(
                "Resumen%s: %d bloques pasan a revisión, %d se dejan fuera "
                "por hablar de avería y %d por ser revisión médica." % (
                    " (DRY-RUN)" if dry_run else "",
                    len(counters["revision"]), len(counters["fault"]),
                    counters["out"]))
            self._write("Fin.")
