# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/screen_export_catalog.py
"""
Column catalogues of the exportable screens (S148).

---

Catálogos de columnas de las pantallas con plantillas de exportación
comunes (panel/screen_exports.py). Cada pantalla: todas las columnas
que se pueden elegir y, en `panel_columns`, las de su tabla en el
panel, que forman la plantilla fija "Vista del panel".
"""
from panel.screen_exports import Column, Screen, register

DATE = "DD/MM/YYYY"


def _counters(asset):
    names = []
    if asset.has_odometer:
        names.append("Km")
    if asset.has_engine_hours:
        names.append("Horas motor")
    if asset.has_crane_hours:
        names.append("Horas grúa")
    return ", ".join(names)


def _short_company(asset):
    from fleet.views import _short_company_name

    return _short_company_name(asset.company_name)


# Centros de gasto. Los objetos son MachineAsset con doc_count y
# use_count puestos por la exportación (fleet.views).
FLEET = register(Screen(
    key="fleet",
    label="Centros de gasto",
    columns=(
        Column("codigo", "Código", 12, lambda a: a.code),
        Column("familia", "Familia", 16, lambda a: a.family),
        Column("descripcion", "Descripción", 34, lambda a: a.brand_model),
        Column("tipo", "Tipo", 26, lambda a: a.type_name),
        Column("matricula", "Matrícula", 14, lambda a: a.plate),
        Column("documentos", "Documentos", 11,
               lambda a: getattr(a, "doc_count", None), summed=True),
        Column("contadores", "Contadores", 22, _counters),
        Column("requisito", "Requisito de documentación", 26,
               lambda a: (a.document_requirement.name
                          if a.document_requirement_id else "")),
        Column("estado", "Estado", 10,
               lambda a: "Activo" if a.is_active else "Inactivo"),
        Column("usos", "Usos (líneas de parte)", 12,
               lambda a: getattr(a, "use_count", None), summed=True),
        Column("bastidor", "Nº de bastidor", 20,
               lambda a: a.chassis_number),
        Column("fecha_compra", "Fecha de compra", 12,
               lambda a: a.purchase_date, DATE),
        Column("km", "Km", 10, lambda a: a.mileage),
        Column("horas", "Horas", 10, lambda a: a.hours),
        Column("itv", "ITV", 12, lambda a: a.itv_date, DATE),
        Column("cita_itv", "Cita ITV", 12,
               lambda a: a.itv_next_appointment, DATE),
        Column("seguro", "Seguro", 24, lambda a: a.insurance_info),
        Column("oca", "OCA", 12, lambda a: a.oca_date, DATE),
        Column("empresa", "Empresa", 28, _short_company),
        Column("codigo_empresa", "Código de empresa", 10,
               lambda a: a.company_code),
        Column("observaciones", "Observaciones", 40, lambda a: a.notes),
    ),
    panel_columns=[
        "codigo", "familia", "descripcion", "tipo", "matricula",
        "documentos", "contadores", "requisito", "estado", "usos",
    ],
))


def _num(value):
    return float(value) if value is not None else None


def _hhmm(value):
    return value.strftime("%H:%M") if value else ""


def _schedule(row):
    if not (row.hc or row.hf):
        return ""
    return "%s–%s" % (_hhmm(row.hc) or "?", _hhmm(row.hf) or "?")


def _local(value):
    from django.utils import timezone

    return timezone.localtime(value).replace(tzinfo=None) if value else None


# Taller de una máquina: tareas de los partes (filas de
# panel/machine_workshop.build_task_rows).
WORKSHOP_TASKS = register(Screen(
    key="workshop_tasks",
    label="Taller: tareas de los partes",
    columns=(
        Column("fecha", "Fecha", 12, lambda r: r.work_date, DATE),
        Column("mecanico", "Mecánico", 28, lambda r: r.worker),
        Column("tipo", "Tipo", 16, lambda r: r.tipo_label),
        Column("clasificacion", "Clasificación", 20,
               lambda r: r.tipo_detail),
        Column("descripcion", "Avería / tarea", 48,
               lambda r: r.description),
        Column("reparacion", "Reparación", 40, lambda r: r.repair),
        Column("hc", "H.C.", 7, lambda r: _hhmm(r.hc)),
        Column("hf", "H.F.", 7, lambda r: _hhmm(r.hf)),
        Column("horario", "Horario", 13, _schedule),
        Column("jornada", "Jornada", 14, lambda r: r.shift_label),
        Column("h_ordinarias", "Horas ordinarias", 10,
               lambda r: _num(r.ordinary_hours), summed=True),
        Column("h_extra", "Horas extra", 9,
               lambda r: _num(r.extra_hours), summed=True),
        Column("h_festivas", "Horas festivas", 9,
               lambda r: _num(r.festive_hours), summed=True),
        Column("horas", "Horas", 8, lambda r: _num(r.hours), summed=True),
        Column("or", "O.R.", 10, lambda r: r.or_val),
        Column("ticket", "Ticket", 10, lambda r: r.ticket_code),
        Column("repuestos", "Repuestos", 10, lambda r: r.parts_count,
               summed=True),
        Column("importe", "Importe repuestos (€)", 12,
               lambda r: _num(r.parts_cost), summed=True),
        Column("sin_precio", "Repuestos sin precio", 10,
               lambda r: r.parts_unpriced or None, summed=True),
        Column("albaranes", "Albaranes", 24,
               lambda r: r.delivery_notes_text),
    ),
    panel_columns=[
        "fecha", "mecanico", "tipo", "descripcion", "horario", "jornada",
        "h_ordinarias", "h_extra", "h_festivas", "horas", "repuestos",
        "importe", "albaranes", "ticket",
    ],
))

# Taller de una máquina: averías (filas de
# panel/machine_workshop.build_ticket_rows).
WORKSHOP_TICKETS = register(Screen(
    key="workshop_tickets",
    label="Taller: averías",
    columns=(
        Column("ticket", "Ticket", 10, lambda r: r.code),
        Column("fecha", "Fecha", 16, lambda r: _local(r.created_at),
               "DD/MM/YYYY HH:MM"),
        Column("estado", "Estado", 14, lambda r: r.status_label),
        Column("urgencia", "Urgencia", 11, lambda r: r.urgency_label),
        Column("tipo", "Tipo", 16, lambda r: r.tipo_label),
        Column("averia", "Avería", 48, lambda r: r.summary),
        Column("asignado", "Asignado a", 24, lambda r: r.assigned),
        Column("cerrada", "Cerrada", 16, lambda r: _local(r.resolved_at),
               "DD/MM/YYYY HH:MM"),
        Column("tareas", "Tareas", 8, lambda r: r.task_count, summed=True),
        Column("h_ordinarias", "Horas ordinarias", 10,
               lambda r: _num(r.ordinary_hours), summed=True),
        Column("h_extra", "Horas extra", 9,
               lambda r: _num(r.extra_hours), summed=True),
        Column("h_festivas", "Horas festivas", 9,
               lambda r: _num(r.festive_hours), summed=True),
        Column("horas", "Horas", 8, lambda r: _num(r.hours), summed=True),
        Column("repuestos", "Repuestos", 10, lambda r: r.parts_count,
               summed=True),
        Column("importe", "Importe repuestos (€)", 12,
               lambda r: _num(r.parts_cost), summed=True),
        Column("sin_precio", "Repuestos sin precio", 10,
               lambda r: r.parts_unpriced or None, summed=True),
    ),
    panel_columns=[
        "ticket", "fecha", "estado", "urgencia", "tipo", "averia", "tareas",
        "h_ordinarias", "h_extra", "h_festivas", "horas", "importe",
        "cerrada",
    ],
))


def _clock_hour(attr, field_name):
    def getter(item):
        from panel.views_clock_events import _hour

        return _hour(getattr(item.shift, attr), field_name, item.shift.day)
    return getter


def _clock_place(attr):
    def getter(item):
        event = getattr(item.shift, attr)
        return (event.municipality or "") if event else ""
    return getter


def _clock_coordinates(attr):
    def getter(item):
        from panel.views_clock_events import _coordinates

        return _coordinates(getattr(item.shift, attr))
    return getter


def _late(item):
    shift = item.shift
    return (max(shift.late_minutes, 0)
            if shift.late_minutes is not None else None)


def _early(item):
    shift = item.shift
    return (max(shift.early_minutes, 0)
            if shift.early_minutes is not None else None)


# Fichajes: hoja "Jornadas". Cada elemento es una jornada (item.row, la
# fila del trabajador; item.shift, la jornada; item.day, la fecha que se
# escribe: solo en la primera jornada de cada día). DNI y nombre van
# siempre delante (o en el membrete si es un solo trabajador). "tipos"
# se abre en una columna de horas por cada tipo de fichaje.
# Excepción (Miguel Ángel, S148): aquí la "Vista del panel" es el Excel
# completo de antes, no la tabla corta de jornadas de la ficha: "que sea
# el Excel completo de antes, como una excepción [...] y a partir de ahí
# que cada uno se genere su propia plantilla".
CLOCK_DAYS = register(Screen(
    key="clock_days",
    label="Fichajes: jornadas",
    columns=(
        Column("fecha", "Fecha", 12, lambda i: i.day, DATE),
        Column("entrada", "Entrada", 9,
               _clock_hour("clock_in", "pressed_at"), "HH:MM"),
        Column("salida", "Salida", 9,
               _clock_hour("clock_out", "pressed_at"), "HH:MM"),
        Column("entrada_parte", "Entrada (parte)", 9,
               _clock_hour("clock_in", "rounded_at"), "HH:MM"),
        Column("salida_parte", "Salida (parte)", 9,
               _clock_hour("clock_out", "rounded_at"), "HH:MM"),
        Column("municipio_entrada", "Municipio entrada", 26,
               _clock_place("clock_in")),
        Column("municipio_salida", "Municipio salida", 26,
               _clock_place("clock_out")),
        Column("coordenadas_entrada", "Coordenadas entrada", 22,
               _clock_coordinates("clock_in")),
        Column("coordenadas_salida", "Coordenadas salida", 22,
               _clock_coordinates("clock_out")),
        Column("entrada_horario", "Entrada según horario", 10,
               lambda i: (i.shift.expected_start
                          if i.shift.late_minutes is not None else None),
               "HH:MM"),
        Column("minutos_tarde", "Minutos tarde", 9, _late),
        Column("salida_horario", "Salida según horario", 10,
               lambda i: (i.shift.expected_end
                          if i.shift.early_minutes is not None else None),
               "HH:MM"),
        Column("minutos_antes", "Minutos antes", 9, _early),
        Column("horas", "Horas", 8, lambda i: i.shift.duration_label),
        Column("incidencias", "Incidencias", 60,
               lambda i: "; ".join(i.shift.incidents)),
        Column("tipos", "Horas por tipo de fichaje", 14, lambda i: None),
    ),
    panel_columns=[
        "fecha", "entrada", "salida", "entrada_parte", "salida_parte",
        "municipio_entrada", "municipio_salida", "coordenadas_entrada",
        "coordenadas_salida", "entrada_horario", "minutos_tarde",
        "salida_horario", "minutos_antes", "horas", "incidencias", "tipos",
    ],
))
