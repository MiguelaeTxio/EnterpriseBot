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
anteriores ya están pagados y no se tocan; los que ya tienen la marca
tampoco): con comida apuntada, partida; sin comida, la jornada de los
días de alrededor del mismo trabajador (si coinciden o solo hay uno).
"No he parado a comer" en una partida queda partida (no paró a comer).
Lo que no queda claro se deja vacío y se lista para revisarlo.

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
# Días de alrededor: como mucho una semana antes y una después.
NEIGHBOUR_DAYS = 7


def _has_lunch(entry):
    return bool(
        entry.lunch_break_start and entry.lunch_break_end
        and entry.lunch_break_end > entry.lunch_break_start
    )


def _known(entry):
    """
    The shift of an entry when it is sure: its stored mark or, with a
    lunch break, split. None otherwise.
    ---
    La jornada de un parte cuando es segura: la marca guardada o, con
    comida apuntada, partida.
    """
    if entry.is_intensive_shift is not None:
        return entry.is_intensive_shift
    if _has_lunch(entry):
        return False
    return None


def infer_is_intensive(entry, lines, neighbours):
    """
    True (intensive), False (split) or None (not sure), and why.
    ---
    Regla de Miguel Ángel (S147): con comida apuntada, partida. Sin
    comida, la jornada de los días de alrededor del mismo trabajador
    (el parte anterior y el siguiente con jornada segura, como mucho a
    una semana): si coinciden,
    o solo hay uno, esa; si no, sin dato. Así, "no he parado a comer"
    en una partida es partida (no paró a comer), y la marca sin comida
    de quien estaba en intensiva es intensiva.
    `neighbours`: (anterior, siguiente) de _known, o None.
    """
    timed = [line for line in lines if line.hc and line.hf]
    if not timed:
        return None, "sin tareas con horas"
    if _has_lunch(entry):
        return False, "comida %s-%s" % (
            entry.lunch_break_start.strftime("%H:%M"),
            entry.lunch_break_end.strftime("%H:%M"))
    span = "de %s a %s" % (
        min(line.hc for line in timed).strftime("%H:%M"),
        max(line.hf for line in timed).strftime("%H:%M"))
    before, after = neighbours
    sides = [v for v in (before, after) if v is not None]
    label = {True: "intensiva", False: "partida"}
    if not sides or len(set(sides)) > 1:
        return None, "sin comida, %s; días de alrededor: %s / %s" % (
            span, label.get(before, "?"), label.get(after, "?"))
    value = sides[0]
    why = "sin comida, %s; días de alrededor en %s" % (span, label[value])
    if not value and entry.no_lunch_break:
        why += " (no paró a comer)"
    return value, why


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
        # Jornada segura de todos los partes digitales de cada
        # trabajador (cualquier fecha), para mirar los días de alrededor.
        known_by_worker = {}
        for other in WorkOrderEntry.objects.select_related(
            "work_order",
        ).filter(
            work_order__source=WorkOrder.Source.DIGITAL,
            work_date__isnull=False,
        ).order_by("work_date", "pk"):
            value = _known(other)
            if value is not None:
                known_by_worker.setdefault(
                    other.work_order.uploaded_by_id, []).append(
                        (other.work_date, value))

        def _neighbours(entry):
            days = known_by_worker.get(entry.work_order.uploaded_by_id, [])
            window = datetime.timedelta(days=NEIGHBOUR_DAYS)
            before = [v for d, v in days
                      if entry.work_date - window <= d < entry.work_date]
            after = [v for d, v in days
                     if entry.work_date < d <= entry.work_date + window]
            return (before[-1] if before else None,
                    after[0] if after else None)

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
                entry, lines_by_entry.get(entry.pk, []), _neighbours(entry))
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
