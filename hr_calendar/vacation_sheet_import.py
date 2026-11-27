# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/vacation_sheet_import.py
"""
Vacation periods from the cranes' vacation chart (S165).

---

Periodos de vacaciones desde el cuadrante de los gruistas (S165, sesión
invasora sobre H11), solo del año en curso: VACACIONES.xlsx, una hoja
por año («2024», «2025»,
«2026 »), bloques por mes (una fila con el mes, otra con los días 1..31
y debajo PERSONAL y un trabajador por fila) y una X en cada día de
vacaciones. Lo demás que traen las celdas (BAJA, ENFERMO, notas) no son
vacaciones y no se carga.

- Los nombres se reconocen como en el planning (crane_albaranes.traffic.
  NameResolver: tabla de Tráfico › Nombres, DNI, mote, palabras con
  abreviaturas e iniciales); los que no, se apuntan en esa tabla «Sin
  asignar» y se dicen.
- Cada racha de días seguidos con X es un periodo. Los días que ya
  están en un periodo registrado no se repiten (se puede cargar el
  cuadrante tantas veces como se quiera).
- Los periodos que empiezan hoy o después se registran como desde el
  panel (create_vacation_period, con su tarea fantasma). Los ya pasados
  se registran sin tarea fantasma: sus días ya tienen sus partes (y
  pueden estar liquidados); la tarea solo sirve para avisar antes de
  empezar.
- `dry_run`: solo cuenta lo que haría (los nombres sin reconocer sí
  quedan apuntados en Tráfico › Planning › Nombres para asignarlos).

Los datos son personales: el Excel no se guarda, solo los periodos.
"""
import datetime
import io
import logging
import re

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
HEADER_WORDS = ("personal",)


def _year(title):
    match = re.search(r"(20\d{2})", title or "")
    return int(match.group(1)) if match else None


def read_chart(data):
    """
    {name text: set of vacation dates} and [problems] of the chart.

    ---

    Lee el cuadrante (bytes): para cada nombre, los días marcados con X
    (también «x», «XXX»). Devuelve también los problemas (hojas sin año,
    bloques sin fila de días).
    """
    from openpyxl import load_workbook

    from crane_albaranes.traffic import plain

    workbook = load_workbook(io.BytesIO(data), data_only=True,
                             read_only=True)
    marks, problems = {}, []
    try:
        for sheet in workbook.worksheets:
            year = _year(sheet.title)
            if year is None:
                problems.append("Hoja «%s»: no se sabe de qué año es." %
                                sheet.title.strip())
                continue
            month, columns = None, {}
            for number, row in enumerate(sheet.iter_rows(
                    max_col=40, values_only=True), start=1):
                words = [plain(v) for v in row if isinstance(v, str)]
                found = next((MONTHS[w] for w in words if w in MONTHS),
                             None)
                if found:
                    month, columns = found, {}
                    continue
                numbers = {i: int(v) for i, v in enumerate(row)
                           if isinstance(v, (int, float))
                           and not isinstance(v, bool)
                           and float(v).is_integer() and 1 <= v <= 31}
                if month and len(numbers) >= 28 and not columns:
                    columns = numbers
                    continue
                name = row[0] if row else None
                if not (month and columns and isinstance(name, str)
                        and name.strip()
                        and plain(name) not in HEADER_WORDS):
                    continue
                for index, day in columns.items():
                    value = row[index] if index < len(row) else None
                    if not (isinstance(value, str) and re.fullmatch(
                            r"x+", value.strip().lower())):
                        continue
                    try:
                        date = datetime.date(year, month, day)
                    except ValueError:
                        problems.append(
                            "Hoja %s, fila %d: el %d no existe en ese "
                            "mes." % (year, number, day))
                        continue
                    marks.setdefault(" ".join(name.split()), set()).add(
                        date)
    finally:
        workbook.close()
    return marks, problems


def _runs(dates):
    """Consecutive runs of dates as [(start, end)]."""
    runs = []
    for date in sorted(dates):
        if runs and (date - runs[-1][1]).days == 1:
            runs[-1][1] = date
        else:
            runs.append([date, date])
    return [tuple(r) for r in runs]


def _covered(person):
    """Dates already inside a registered period of the person."""
    from hr_calendar.models import VacationPeriod

    days = set()
    for start, end in VacationPeriod.objects.filter(
            person=person).values_list("date_start", "date_end"):
        for offset in range((end - start).days + 1):
            days.add(start + datetime.timedelta(offset))
    return days


def _register_past(person, company, created_by, start, end):
    """
    Register a past period without its ghost task.
    ---
    Registra un periodo ya pasado sin tarea fantasma: se crea sin cuenta
    de panel (VacationPeriod.save no genera la tarea) y después se le
    pone la suya, como al registrarlo desde el panel.
    """
    from hr_calendar.models import VacationPeriod

    period = VacationPeriod.objects.create(
        person=person, company=company, operator=None,
        created_by=created_by, date_start=start, date_end=end)
    if person.company_user_id:
        VacationPeriod.objects.filter(pk=period.pk).update(
            operator_id=person.company_user_id)
    return period


def import_chart(company, uploaded, created_by=None, dry_run=False):
    """
    Load the vacation chart; return a summary dict.

    ---

    Carga el cuadrante de vacaciones. Devuelve un resumen: trabajadores
    reconocidos, periodos nuevos (y cuántos ya pasados, sin tarea
    fantasma), días que ya estaban, nombres sin reconocer y problemas.
    Con `dry_run`, no guarda nada.
    """
    from crane_albaranes.traffic import NameResolver, remember_unknown
    from hr_calendar.services import create_vacation_period

    from crane_albaranes.models import PlanningName

    today = timezone.localdate()
    marks, problems = read_chart(uploaded.read())
    # Solo el año en curso (Miguel Ángel, S165: «estamos en 2026 y nos da
    # igual lo que pasara en 2025 o 2024»): las hojas de otros años no
    # se cargan.
    marks = {text: {d for d in dates if d.year == today.year}
             for text, dates in marks.items()}
    marks = {text: dates for text, dates in marks.items() if dates}
    # Y fuera de Nombres lo apuntado solo de otros años que nadie asignó.
    PlanningName.objects.filter(
        company=company, person__isnull=True, not_a_worker=False,
        updated_by__isnull=True, seen_to__lt=datetime.date(
            today.year, 1, 1)).delete()
    if not marks:
        raise ValueError("El Excel no trae ninguna X de vacaciones de %d."
                         % today.year)
    people = NameResolver(company)
    summary = {"people": 0, "periods": 0, "past": 0, "days": 0,
               "already": 0, "unknown": [], "problems": problems,
               "errors": []}
    by_person = {}
    spans = {text: (min(dates), max(dates)) for text, dates in marks.items()}
    for text, dates in marks.items():
        person, why = people.resolve(text, spans[text])
        if person is None:
            if not people.is_ignored(text):
                summary["unknown"].append(text)
            continue
        by_person.setdefault(person, set()).update(dates)
    for person, dates in by_person.items():
        pending = dates - _covered(person)
        summary["already"] += len(dates) - len(pending)
        runs = _runs(pending)
        if not runs:
            continue
        summary["people"] += 1
        for start, end in runs:
            summary["periods"] += 1
            summary["days"] += (end - start).days + 1
            if start < today:
                summary["past"] += 1
            if dry_run:
                continue
            try:
                with transaction.atomic():
                    if start < today:
                        _register_past(person, company, created_by, start,
                                       end)
                    else:
                        create_vacation_period(person, company, created_by,
                                               start, end)
            except Exception as exc:  # noqa: BLE001 -- se informa
                logger.exception("# [VACACIONES CUADRANTE] %s %s-%s",
                                 person.pk, start, end)
                summary["errors"].append("%s %s a %s: %s" % (
                    person.given_name, start.strftime("%d/%m/%Y"),
                    end.strftime("%d/%m/%Y"), exc))
    # También al comprobar: solo se apuntan los nombres por asignar (no
    # las vacaciones), para poder asignarlos antes de cargar.
    remember_unknown(company, {t: spans[t] for t in marks
                               if not people.is_ignored(t)}, people)
    logger.info(
        "# [VACACIONES CUADRANTE] %s%d periodos (%d pasados) de %d "
        "trabajadores, %d días; %d ya estaban; %d nombres sin reconocer.",
        "PRUEBA: " if dry_run else "", summary["periods"], summary["past"],
        summary["people"], summary["days"], summary["already"],
        len(summary["unknown"]))
    return summary
