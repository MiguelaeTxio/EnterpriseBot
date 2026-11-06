# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/infer_shift_type_s147.py
"""
H24 (S147). Fill the shift type of the digital partes that lack it,
inferred from their tasks.

---

H24 (S147). Rellena "jornada intensiva / partida" de los partes
digitales que no la tienen (WorkOrderEntry.is_intensive_shift nulo),
deducida de sus tareas (Miguel Ángel: "rellenarlo según se infiera de
las tareas"). Desde S141 no se guardaba por un fallo (shift.py pedía
work_order.work_date).

Regla:
- Partida: el parte tiene comida (sin "no paró a comer") con tareas
  antes y después de ella, o hay un hueco de al menos 30 minutos entre
  dos tareas seguidas.
- Intensiva: tareas seguidas, sin ese hueco.
- Sin tareas con horas: se deja vacío.

DRY-RUN POR DEFECTO; `--apply` escribe. Log propio en `--log-file`,
pantalla y archivo a la vez.
"""
import datetime

from django.core.management.base import BaseCommand

from work_order_processor.models import (
    WorkOrder,
    WorkOrderEntry,
    WorkOrderEntryLine,
)

MIN_SPLIT_GAP_MINUTES = 30
HEARTBEAT = 50


def _minutes(value):
    return value.hour * 60 + value.minute


def infer_is_intensive(entry, lines):
    """
    True (intensive), False (split) or None (no timed task), from the
    parte's tasks.
    ---
    True (intensiva), False (partida) o None (sin tareas con horas),
    según las tareas del parte.
    """
    timed = sorted(
        (line for line in lines if line.hc and line.hf),
        key=lambda line: line.hc,
    )
    if not timed:
        return None, "sin tareas con horas"
    if (
        not entry.no_lunch_break and entry.lunch_break_start
        and entry.lunch_break_end
        and entry.lunch_break_end > entry.lunch_break_start
        and any(line.hf <= entry.lunch_break_start for line in timed)
        and any(line.hc >= entry.lunch_break_end for line in timed)
    ):
        return False, "comida %s-%s con tareas antes y después" % (
            entry.lunch_break_start.strftime("%H:%M"),
            entry.lunch_break_end.strftime("%H:%M"))
    end = timed[0].hf
    for line in timed[1:]:
        gap = _minutes(line.hc) - _minutes(end)
        if gap >= MIN_SPLIT_GAP_MINUTES:
            return False, "hueco de %d min entre tareas (%s-%s)" % (
                gap, end.strftime("%H:%M"), line.hc.strftime("%H:%M"))
        if line.hf > end:
            end = line.hf
    return True, "tareas seguidas de %s a %s" % (
        timed[0].hc.strftime("%H:%M"), end.strftime("%H:%M"))


class Command(BaseCommand):
    help = "S147: jornada intensiva/partida de los partes que no la tienen."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def handle(self, *args, **options):
        log_file = open(options["log_file"], "a", encoding="utf-8")

        def _log(text):
            line = "[%s] %s" % (
                datetime.datetime.now().strftime("%H:%M:%S"), text)
            print(line, flush=True)
            log_file.write(line + "\n")
            log_file.flush()

        def _log_plain(text):
            print(text, flush=True)
            log_file.write(text + "\n")
            log_file.flush()

        apply = options["apply"]
        _log("Jornada de los partes digitales (S147) -- %s" % (
            "APLICANDO" if apply
            else "SIMULACIÓN (sin --apply no se escribe)"))
        entries = list(
            WorkOrderEntry.objects.select_related("work_order__uploaded_by")
            .filter(
                work_order__source=WorkOrder.Source.DIGITAL,
                is_intensive_shift__isnull=True,
            )
            .order_by("work_date", "pk")
        )
        lines_by_entry = {}
        for line in WorkOrderEntryLine.objects.filter(
            entry__in=entries,
        ).only("entry_id", "hc", "hf"):
            lines_by_entry.setdefault(line.entry_id, []).append(line)
        total = len(entries)
        _log("Partes digitales sin jornada: %d" % total)
        counts = {True: 0, False: 0, None: 0}
        start_time = datetime.datetime.now()
        for done, entry in enumerate(entries, start=1):
            value, why = infer_is_intensive(
                entry, lines_by_entry.get(entry.pk, []))
            counts[value] += 1
            label = {True: "INTENSIVA", False: "PARTIDA",
                     None: "SIN DATO"}[value]
            operator = entry.work_order.uploaded_by
            _log("Parte %d (entrada %d, %s, %s): %s -- %s" % (
                entry.work_order_id, entry.pk,
                entry.work_date.strftime("%d/%m/%Y")
                if entry.work_date else "sin fecha",
                operator.user.username if operator else "sin operario",
                label, why))
            if apply and value is not None:
                WorkOrderEntry.objects.filter(pk=entry.pk).update(
                    is_intensive_shift=value)
            if done % HEARTBEAT == 0 and done < total:
                elapsed = (datetime.datetime.now() - start_time)
                eta = elapsed.total_seconds() / done * (total - done)
                end_at = datetime.datetime.now() + datetime.timedelta(
                    seconds=eta)
                _log("Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. "
                     "%s) -- intensivas %d, partidas %d, sin dato %d" % (
                         done, total, done * 100 // total, eta // 60,
                         eta % 60, end_at.strftime("%H:%M:%S"),
                         counts[True], counts[False], counts[None]))
        _log_plain("")
        _log_plain("RESUMEN")
        _log_plain("  Partes revisados: %d" % total)
        _log_plain("  Intensiva: %d" % counts[True])
        _log_plain("  Partida: %d" % counts[False])
        _log_plain("  Sin tareas con horas (se dejan vacíos): %d"
                   % counts[None])
        _log_plain("  %s" % ("Escritos." if apply
                             else "Nada escrito (simulación)."))
        log_file.close()
