# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/clock_export.py
"""
Clock-in record export (Excel), new interface.

---

Exportación del registro de jornada a Excel en la nueva interfaz (S163),
copiado de panel/views_clock_events.ClockEventsExportView con las
columnas de su «Vista del panel» (panel/screen_export_catalog.CLOCK_DAYS):
hojas «Trabajadores» (cada marcado, aunque no tenga fichajes),
«Jornadas» (una fila por jornada: hora real, la del parte, la del
horario, horas e incidencias, y horas por tipo), «Pulsaciones» (cada
pulsación tal como llegó, con su posición) y «Correcciones» (el
historial). Con un solo trabajador, sus datos van arriba como membrete.
"""
from types import SimpleNamespace

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar.clock_report import format_duration, reports_by_user
from hr_calendar.models import ClockType
from new_ui import clock_core
from new_ui.mixins import SuperuserRequiredMixin

DATE = "DD/MM/YYYY"


def _hour(event, field_name, day, seconds=False):
    """
    The time of a press field: a time on the row's day, else with date.

    ---

    La hora de un campo de la pulsación: una hora si cae en el día de
    la fila; si no, texto con su fecha («06:00 (18/10)»).
    """
    if event is None or getattr(event, field_name) is None:
        return None
    value = timezone.localtime(getattr(event, field_name))
    if value.date() == day:
        return value.time().replace(
            microsecond=0, second=value.second if seconds else 0)
    return value.strftime("%H:%M:%S (%d/%m)" if seconds else "%H:%M (%d/%m)")


def _coordinates(event):
    if event is None or event.latitude is None or event.longitude is None:
        return ""
    return "%s, %s" % (float(event.latitude), float(event.longitude))


def _place(event):
    return (event.municipality or "") if event else ""


def _late(shift):
    return (max(shift.late_minutes, 0)
            if shift.late_minutes is not None else None)


def _early(shift):
    return (max(shift.early_minutes, 0)
            if shift.early_minutes is not None else None)


# (clave, cabecera, ancho, valor(item), formato) -- las columnas de
# CLOCK_DAYS con sus claves (las de las plantillas de exportación que se
# guardan en panel.ScreenExportTemplate, pantalla "clock_days"); la
# «Vista del panel» es todas. "tipos" se abre en una columna por tipo.
DAY_COLUMNS = (
    ("fecha", "Fecha", 12, lambda i: i.day, DATE),
    ("entrada", "Entrada", 9, lambda i: _hour(i.shift.clock_in, "pressed_at",
                                   i.shift.day), "HH:MM"),
    ("salida", "Salida", 9, lambda i: _hour(i.shift.clock_out, "pressed_at",
                                  i.shift.day), "HH:MM"),
    ("entrada_parte", "Entrada (parte)", 9, lambda i: _hour(i.shift.clock_in, "rounded_at",
                                           i.shift.day), "HH:MM"),
    ("salida_parte", "Salida (parte)", 9, lambda i: _hour(i.shift.clock_out, "rounded_at",
                                          i.shift.day), "HH:MM"),
    ("municipio_entrada", "Municipio entrada", 26, lambda i: _place(i.shift.clock_in), None),
    ("municipio_salida", "Municipio salida", 26, lambda i: _place(i.shift.clock_out), None),
    ("coordenadas_entrada", "Coordenadas entrada", 22, lambda i: _coordinates(i.shift.clock_in),
     None),
    ("coordenadas_salida", "Coordenadas salida", 22, lambda i: _coordinates(i.shift.clock_out),
     None),
    ("entrada_horario", "Entrada según horario", 10, lambda i: (
        i.shift.expected_start if i.shift.late_minutes is not None
        else None), "HH:MM"),
    ("minutos_tarde", "Minutos tarde", 9, lambda i: _late(i.shift), None),
    ("salida_horario", "Salida según horario", 10, lambda i: (
        i.shift.expected_end if i.shift.early_minutes is not None
        else None), "HH:MM"),
    ("minutos_antes", "Minutos antes", 9, lambda i: _early(i.shift), None),
    ("horas", "Horas", 8, lambda i: i.shift.duration_label, None),
    ("incidencias", "Incidencias", 60, lambda i: "; ".join(i.shift.incidents), None),
    ("tipos", "tipos", 14, None, None),
)


def _label(person):
    surnames = " ".join(
        p for p in (person.first_surname, person.second_surname) if p)
    return "%s, %s" % (surnames, person.given_name)


def _letterhead(row, date_from, date_to, sheets):
    """
    One-worker Excel: name, DNI, company and period on top of each sheet.

    ---

    Excel de un solo trabajador: en cada hoja se quitan las columnas DNI
    y nombre y se ponen arriba, como membrete, con la empresa y el
    periodo.
    """
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    person = row.person
    lines = [
        ("Registro de jornada", ""),
        ("Trabajador", row.label),
        ("DNI/NIE", person.dni),
        ("Empresa", person.employer_legal_name or ""),
        ("Periodo", "%s – %s" % (date_from.strftime("%d/%m/%Y"),
                                 date_to.strftime("%d/%m/%Y"))),
    ]
    for sheet, headers in sheets:
        sheet.delete_cols(1, 2)
        sheet.insert_rows(1, amount=len(lines) + 1)
        for index, (label, value) in enumerate(lines, start=1):
            sheet.cell(row=index, column=1, value=label).font = Font(
                bold=True, size=13 if index == 1 else 11)
            if value:
                sheet.cell(row=index, column=2, value=value)
        sheet.freeze_panes = "A%d" % (len(lines) + 3)
        for index, (_header, width) in enumerate(headers[2:], start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width


def build_workbook(company, people, date_from, date_to, columns=None):
    """
    The clock-in record workbook of `people` in the range.

    ---

    El libro del registro de jornada de estas personas en el intervalo,
    con las columnas de «Jornadas» indicadas (sin ellas, todas).
    """
    columns = columns or DAY_COLUMNS
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    from hr_calendar.clock_geocode import fill_missing

    ids = [p.company_user_id for p in people if p.company_user_id]
    reports = reports_by_user(company, ids, date_from, date_to) if ids else {}
    empty = clock_core._EmptyReport()
    rows = sorted([
        SimpleNamespace(person=p, label=_label(p),
                        report=reports.get(p.company_user_id) or empty)
        for p in people], key=lambda r: r.label.lower())
    book = Workbook()
    workers = book.active
    workers.title = "Trabajadores"
    worker_headers = [("DNI", 12), ("Apellidos y nombre", 34),
                      ("Usuario del panel", 10), ("Fichajes", 9),
                      ("Incidencias", 10), ("Horas", 10)]
    workers.append([h for h, _w in worker_headers])
    for row in rows:
        workers.append([
            row.person.dni, row.label,
            "Sí" if row.person.company_user_id else "No",
            len(row.report.events), row.report.incident_count,
            row.report.total_label])
    type_names = [(t.name, t.counts_as_work)
                  for t in ClockType.objects.filter(company=company)]
    days = book.create_sheet("Jornadas")
    day_headers = [("DNI", 12), ("Apellidos y nombre", 34)]
    for key, header, width, _get, _fmt in columns:
        if key == "tipos":
            day_headers += [("%s%s" % (name, "" if counts
                                       else " (no cuenta)"), 14)
                            for name, counts in type_names]
        else:
            day_headers.append((header, width))
    days.append([h for h, _w in day_headers])
    presses = book.create_sheet("Pulsaciones")
    press_headers = [
        ("DNI", 12), ("Apellidos y nombre", 34), ("Tipo", 9),
        ("Fecha", 12), ("Hora de la pulsación", 10),
        ("Hora redondeada (parte)", 10), ("Hora de llegada", 16),
        ("Retraso (min)", 9), ("Municipio", 28), ("Latitud", 11),
        ("Longitud", 11), ("Precisión (m)", 9), ("Sin GPS porque", 24),
        ("Cómo se envió", 34), ("Navegador", 40), ("Tipo de fichaje", 20),
    ]
    presses.append([h for h, _w in press_headers])
    fill_missing([e for row in rows for e in row.report.events], limit=80)
    for row in rows:
        last_day = None
        for shift in row.report.shifts:
            shown = shift.day if shift.day != last_day else None
            last_day = shift.day
            item = SimpleNamespace(shift=shift, day=shown)
            values = [row.person.dni, row.label]
            for key, _header, _width, get, _fmt in columns:
                if key == "tipos":
                    values += [format_duration(shift.type_seconds[name])
                               if name in shift.type_seconds else ""
                               for name, _counts in type_names]
                else:
                    values.append(get(item))
            days.append(values)
        last_day = None
        for event in row.report.events:
            pressed = timezone.localtime(event.pressed_at)
            shown = pressed.date() if pressed.date() != last_day else None
            last_day = pressed.date()
            presses.append([
                row.person.dni, row.label, event.get_kind_display(), shown,
                pressed.time().replace(microsecond=0),
                _hour(event, "rounded_at", pressed.date()),
                _hour(event, "received_at", pressed.date(), True),
                round(event.delay_seconds / 60), event.municipality or "",
                float(event.latitude) if event.latitude is not None
                else None,
                float(event.longitude) if event.longitude is not None
                else None,
                event.accuracy_m, event.gps_error,
                event.get_sent_by_display(), event.user_agent,
                event.clock_type.name if event.clock_type_id else "",
            ])
    fixes = book.create_sheet("Correcciones")
    fix_headers = [
        ("DNI", 12), ("Apellidos y nombre", 34), ("Corrección", 24),
        ("Tipo anterior", 10), ("Hora anterior", 17), ("Tipo nuevo", 10),
        ("Hora nueva", 17), ("Motivo", 60), ("Corregido por", 28),
        ("Fecha de la corrección", 17), ("Tipo de fichaje anterior", 20),
        ("Tipo de fichaje nuevo", 20),
    ]
    fixes.append([h for h, _w in fix_headers])
    stamp = "%d/%m/%Y %H:%M"
    for row in rows:
        if not row.person.company_user_id:
            continue
        for fix in reversed(clock_core._corrections_in_range(
                row.person.company_user_id, date_from, date_to)):
            fixes.append([
                row.person.dni, row.label, fix.get_action_display(),
                fix.get_old_kind_display(),
                timezone.localtime(fix.old_pressed_at).strftime(stamp)
                if fix.old_pressed_at else "",
                fix.get_new_kind_display(),
                timezone.localtime(fix.new_pressed_at).strftime(stamp)
                if fix.new_pressed_at else "",
                fix.reason, clock_core._user_label(fix.corrected_by),
                timezone.localtime(fix.corrected_at).strftime(stamp),
                fix.old_clock_type.name if fix.old_clock_type else "",
                fix.new_clock_type.name if fix.new_clock_type else "",
            ])
    for sheet, headers in ((workers, worker_headers), (days, day_headers),
                           (presses, press_headers), (fixes, fix_headers)):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        for index, (_header, width) in enumerate(headers):
            sheet.column_dimensions[get_column_letter(index + 1)].width = (
                width)
    index = 3
    for key, _header, _width, _get, fmt in columns:
        if key == "tipos":
            index += len(type_names)
            continue
        if fmt:
            for cell in days[get_column_letter(index)][1:]:
                cell.number_format = fmt
        index += 1
    for cell in presses["D"][1:]:
        cell.number_format = DATE
    for cell in presses["E"][1:]:
        cell.number_format = "HH:MM:SS"
    for cell in presses["F"][1:]:
        cell.number_format = "HH:MM"
    for cell in presses["G"][1:]:
        cell.number_format = "HH:MM:SS"
    if len(rows) == 1:
        _letterhead(rows[0], date_from, date_to, (
            (days, day_headers), (presses, press_headers),
            (fixes, fix_headers)))
    return book


_BY_KEY = {c[0]: c for c in DAY_COLUMNS}


def chosen_columns(request):
    """
    The «Jornadas» columns of the export, in order (all if none marked).

    ---

    Las columnas marcadas de «Jornadas», en el orden de la plantilla
    elegida (new_ui/screen_templates.py, pantalla «clock_days»).
    """
    from new_ui.screen_templates import chosen_keys

    return [_BY_KEY[k] for k in chosen_keys(request, "clock_days")]


class ClockExportView(SuperuserRequiredMixin, View):
    """
    POST: the clock-in record of the marked (or the open) workers.

    ---

    POST: Excel del registro de jornada de las personas marcadas (o de
    la abierta) en el intervalo indicado (sin fechas, el mes en curso).
    """

    def post(self, request):
        import io

        from new_ui.views_clock import _period

        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        if not ids and (request.POST.get("person_pk") or "").isdigit():
            ids = [request.POST["person_pk"]]
        people = list(PersonIdentity.objects.select_related(
            "company_user").filter(pk__in=ids))
        if not people:
            return JsonResponse({"ok": False, "message": "Marca a las "
                                 "personas o abre una."}, status=400)
        date_from, date_to = _period(request.POST)
        book = build_workbook(request.user.company_user.company, people,
                              date_from, date_to, chosen_columns(request))
        buffer = io.BytesIO()
        book.save(buffer)
        response = HttpResponse(
            buffer.getvalue(), content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"))
        response["Content-Disposition"] = (
            'attachment; filename="fichajes_%s_%s.xlsx"' % (
                date_from.strftime("%Y%m%d"), date_to.strftime("%Y%m%d")))
        return response
