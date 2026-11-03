# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/clock_calendar.py
"""
Calendar view of one worker's clock-ins (H24, S144).

---

Vista de calendario de los fichajes de un trabajador (H24, S144).
Miguel Ángel: "echo de menos una vista de tipo calendario, que es muy
gráfica". Un mes por bloque, semanas de lunes a domingo; cada día con
sus jornadas (entrada, salida y horas) y un color: correcto, con
incidencias, anulado o sin fichajes. La usan la página de fichajes del
trabajador (panel/views_clock_worker.py) y el detalle de la ficha de
Personal (panel/views_clock_events.py).
"""
import calendar

from django.utils import timezone

MONTH_NAMES = (
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
    "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
WEEKDAY_NAMES = ("Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do")
DAY_OK = "ok"
DAY_ISSUES = "issues"
DAY_CANCELLED = "cancelled"
DAY_EMPTY = "empty"


def _hhmm(press):
    return press["time"].strftime("%H:%M") if press else "—"


def _day_cell(day, shifts, date_from, date_to, today):
    """
    One day of the calendar with its shifts and its status.
    ---
    Un día del calendario con sus jornadas y su estado.
    """
    worked = [s for s in shifts if not s.get("only_cancelled")]
    if any(s.get("incidents") for s in worked):
        status = DAY_ISSUES
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
    incidents = [i for s in worked for i in s.get("incidents") or []]
    title = [day.strftime("%d/%m/%Y")]
    title += ["Jornada %s" % line for line in lines]
    title += incidents
    if status == DAY_CANCELLED:
        title.append("Día anulado")
    elif any(s.get("cancelled") for s in shifts):
        title.append("Con pulsaciones anuladas")
    hours = ""
    if seconds:
        hours = "%d:%02d" % (seconds // 3600, seconds % 3600 // 60)
    return {
        "day": day,
        "in_range": date_from <= day <= date_to,
        "weekend": day.weekday() >= 5,
        "today": day == today,
        "status": status,
        "lines": lines,
        "hours": hours,
        "incident_count": len(incidents),
        "title": "\n".join(title),
    }


def calendar_months(shifts, date_from, date_to):
    """
    Months of the range (newest first), each a list of weeks of 7 days.
    ---
    Los meses del intervalo (el más reciente arriba), cada uno con sus
    semanas de lunes a domingo. Los días fuera del intervalo salen
    vacíos y atenuados.
    """
    by_day = {}
    for shift in shifts:
        by_day.setdefault(shift["day"], []).append(shift)
    today = timezone.localdate()
    builder = calendar.Calendar(firstweekday=0)
    months = []
    year, month = date_from.year, date_from.month
    while (year, month) <= (date_to.year, date_to.month):
        weeks = []
        total = 0
        for week in builder.monthdatescalendar(year, month):
            cells = []
            for day in week:
                if day.month != month:
                    cells.append(None)
                    continue
                cell = _day_cell(day, by_day.get(day, []), date_from,
                                 date_to, today)
                cells.append(cell)
                if cell["in_range"]:
                    total += sum(s.get("seconds") or 0
                                 for s in by_day.get(day, [])
                                 if not s.get("only_cancelled"))
            weeks.append(cells)
        months.append({
            "label": "%s %d" % (MONTH_NAMES[month], year),
            "weeks": weeks,
            "total": "%d:%02d" % (total // 3600, total % 3600 // 60),
        })
        month += 1
        if month > 12:
            year, month = year + 1, 1
    months.reverse()
    return {"months": months, "weekday_names": WEEKDAY_NAMES}
