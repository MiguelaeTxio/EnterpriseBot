# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/clock_calendar.py
"""
S163: copia de panel/clock_calendar.py para la nueva interfaz (sin
depender de ella).
---

Calendar view of one worker's clock-ins (H24, S144).

---

Vista de calendario de los fichajes de un trabajador (H24, S144).
Miguel Ángel: "echo de menos una vista de tipo calendario, que es muy
gráfica". Siempre los cuatro años de conservación del registro (art.
34.9 ET), completos, aunque no haya fichajes: el año actual arriba y,
dentro de cada año, de enero a diciembre (S144: "que se vea la vista
exactamente igual tanto si el trabajador lleva trabajando ya años como
si es una persona que llega nueva"). Cada día, una casilla de alto fijo
con su color: azul correcto, rojo con incidencias, gris anulado, blanco
sin fichajes; hoy, con borde grueso azul oscuro. La usan la página de
fichajes del trabajador (panel/views_clock_worker.py) y el detalle de
la ficha de Personal (panel/views_clock_events.py).
"""
import calendar
import datetime

from django.utils import timezone

YEARS = 4
MONTH_NAMES = (
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
    "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
WEEKDAY_NAMES = ("Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do")
DAY_OK = "ok"
DAY_ISSUES = "issues"
DAY_CANCELLED = "cancelled"
DAY_EMPTY = "empty"
# S143: incidencias visadas (amarillo) y hoy con la entrada fichada y sin
# salida (verde).
DAY_REVIEWED = "reviewed"
DAY_OPEN = "open"
# S149 (18/11): marcado para revisar después, en morado.
DAY_HOLD = "hold"


def calendar_range(today=None):
    """
    (1 January three years ago, today): the days the calendar shows data.
    ---
    (1 de enero de hace tres años, hoy): los días con datos del
    calendario (el año actual y los tres anteriores).
    """
    today = today or timezone.localdate()
    return datetime.date(today.year - YEARS + 1, 1, 1), today


def _hhmm(press):
    return press["time"].strftime("%H:%M") if press else "—"


def _hours(seconds):
    return "%d:%02d" % (seconds // 3600, seconds % 3600 // 60)


def _day_cell(day, shifts, today):
    """
    One day of the calendar with its shifts and its status.
    ---
    Un día del calendario con su estado, una sola línea de horas (la
    primera entrada y la última salida del día) y el total; el detalle
    de cada jornada, en el texto al pasar por encima.
    """
    worked = [s for s in shifts if not s.get("only_cancelled")]
    with_incidents = [s for s in worked if s.get("incidents")]
    if any(s.get("hold") and not s.get("review_manual") for s in worked):
        status = DAY_HOLD
    elif any(not s.get("reviewed") for s in with_incidents):
        status = DAY_ISSUES
    # S153: un día visado (casilla o corregido) en amarillo, tenga
    # incidencias o no.
    elif worked and all(s.get("reviewed") for s in worked):
        status = DAY_REVIEWED
    elif any(s.get("in_progress") for s in worked):
        status = DAY_OPEN
    elif worked:
        status = DAY_OK
    elif shifts:
        status = DAY_CANCELLED
    else:
        status = DAY_EMPTY
    lines = []
    seconds = 0
    for shift in worked:
        entry, exit_ = (shift.get("presses") or [None, None])
        lines.append("%s–%s" % (_hhmm(entry), _hhmm(exit_)))
        seconds += shift.get("seconds") or 0
    span = ""
    if worked:
        entries = [p for s in worked for p in (s.get("presses") or [])[:1]
                   if p]
        exits = [p for s in worked for p in (s.get("presses") or [])[1:]
                 if p]
        first = min(entries, key=lambda p: p["time"]) if entries else None
        last = max(exits, key=lambda p: p["time"]) if exits else None
        span = "%s–%s" % (_hhmm(first), _hhmm(last))
    incidents = [i for s in worked for i in s.get("incidents") or []]
    title = [day.strftime("%d/%m/%Y")]
    title += ["Jornada %s" % line for line in lines]
    title += incidents
    if status == DAY_CANCELLED:
        title.append("Día anulado")
    elif any(s.get("cancelled") for s in shifts):
        title.append("Con pulsaciones anuladas")
    return {
        "day": day,
        "weekend": day.weekday() >= 5,
        "today": day == today,
        "status": status,
        "span": span,
        "shift_count": len(worked),
        "hours": _hours(seconds) if seconds else "",
        "seconds": seconds,
        "incident_count": len(incidents),
        "title": "\n".join(title),
    }


def calendar_years(shifts, today=None):
    """
    The four years, current first, each with its twelve months.
    ---
    Los cuatro años (el actual arriba), cada uno con sus doce meses de
    enero a diciembre y sus semanas de lunes a domingo; totales de
    horas por mes y por año.
    """
    today = today or timezone.localdate()
    by_day = {}
    for shift in shifts:
        by_day.setdefault(shift["day"], []).append(shift)
    builder = calendar.Calendar(firstweekday=0)
    years = []
    for year in range(today.year, today.year - YEARS, -1):
        months = []
        year_seconds = 0
        for month in range(1, 13):
            weeks = []
            month_seconds = 0
            for week in builder.monthdatescalendar(year, month):
                cells = []
                for day in week:
                    if day.month != month:
                        cells.append(None)
                        continue
                    cell = _day_cell(day, by_day.get(day, []), today)
                    month_seconds += cell["seconds"]
                    cells.append(cell)
                weeks.append(cells)
            # Siempre seis semanas: todos los meses con el mismo alto.
            while len(weeks) < 6:
                weeks.append([None] * 7)
            months.append({
                "label": MONTH_NAMES[month],
                "weeks": weeks,
                "total": _hours(month_seconds),
            })
            year_seconds += month_seconds
        years.append({
            "year": year, "months": months, "total": _hours(year_seconds),
        })
    return {"years": years, "weekday_names": WEEKDAY_NAMES}
