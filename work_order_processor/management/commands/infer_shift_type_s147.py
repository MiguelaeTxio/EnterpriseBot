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

Regla de Miguel Ángel (S147), solo en el periodo abierto (los
anteriores ya están pagados y no se tocan): con comida apuntada,
partida; sin comida (o 00:00 a 00:00), intensiva (en el periodo del
21/10 al 20/11 ninguna baja de 8 horas). Los que ya tienen la marca no
se tocan. Los que quedan sin dato (sin tareas con horas) se listan.

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

HEARTBEAT = 50


def infer_is_intensive(entry, lines):
    """
    True (intensive), False (split) or None (no timed task).
    ---
    Regla de Miguel Ángel (S147) para el periodo abierto: con comida
    apuntada (de inicio a fin, no 00:00 a 00:00), partida; sin comida,
    intensiva (en el periodo ninguna baja de 8 horas).
    """
    timed = [line for line in lines if line.hc and line.hf]
    if not timed:
        return None, "sin tareas con horas"
    if (
        entry.lunch_break_start and entry.lunch_break_end
        and entry.lunch_break_end > entry.lunch_break_start
    ):
        return False, "comida %s-%s" % (
            entry.lunch_break_start.strftime("%H:%M"),
            entry.lunch_break_end.strftime("%H:%M"))
    return True, "sin comida, de %s a %s" % (
        min(line.hc for line in timed).strftime("%H:%M"),
        max(line.hf for line in timed).strftime("%H:%M"))


class Command(BaseCommand):
    help = "S147: jornada intensiva/partida de los partes que no la tienen."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)
        parser.add_argument("--date-from", required=True,
                            help="Primer día del periodo (AAAA-MM-DD).")
        parser.add_argument("--date-to", required=True,
                            help="Último día del periodo (AAAA-MM-DD).")

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
                work_date__gte=options["date_from"],
                work_date__lte=options["date_to"],
            )
            .order_by("work_date", "pk")
        )
        lines_by_entry = {}
        for line in WorkOrderEntryLine.objects.filter(
            entry__in=entries,
        ).only("entry_id", "hc", "hf"):
            lines_by_entry.setdefault(line.entry_id, []).append(line)
        total = len(entries)
        _log("Partes digitales sin jornada del %s al %s: %d" % (
            options["date_from"], options["date_to"], total))
        counts = {True: 0, False: 0, None: 0}
        odd = []
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
            if value is None:
                odd.append("Parte %d (entrada %d, %s, %s): %s" % (
                    entry.work_order_id, entry.pk,
                    entry.work_date.strftime("%d/%m/%Y")
                    if entry.work_date else "sin fecha",
                    operator.user.username if operator else "sin operario",
                    why))
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
        _log_plain("  Sin dato (se dejan vacíos, para revisar): %d"
                   % counts[None])
        if odd:
            _log_plain("")
            _log_plain("PARA REVISAR (%d)" % len(odd))
            for number, line in enumerate(odd, start=1):
                _log_plain("  %d. %s" % (number, line))
        _log_plain("  %s" % ("Escritos." if apply
                             else "Nada escrito (simulación)."))
        log_file.close()
