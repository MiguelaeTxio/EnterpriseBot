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
        Column("familia", "Familia", 16, lambda a: a.family,
               sort="family", css="fleet-col-w90"),
        Column("descripcion", "Descripción", 34, lambda a: a.brand_model,
               sort="brand_model", short_label="Descripción / Marca-Modelo"),
        Column("tipo", "Tipo", 26, lambda a: a.type_name,
               sort="type_name", css="fleet-col-w100"),
        Column("matricula", "Matrícula", 14, lambda a: a.plate,
               sort="plate", css="fleet-col-w90"),
        Column("documentos", "Documentos", 11,
               lambda a: getattr(a, "doc_count", None), summed=True,
               sort="doc_count", css="text-center fleet-col-w90",
               short_label="Docs."),
        Column("contadores", "Contadores", 22, _counters,
               css="text-center fleet-col-w70", short_label="Contad."),
        Column("requisito", "Requisito de documentación", 26,
               lambda a: ", ".join(sorted(
                   req.name for req in a.document_requirements.all())),
               sort="requirement", css="fleet-col-w100"),
        Column("estado", "Estado", 10,
               lambda a: "Activo" if a.is_active else "Inactivo",
               sort="is_active", css="text-center fleet-col-w70"),
        Column("usos", "Usos (líneas de parte)", 12,
               lambda a: getattr(a, "use_count", None), summed=True,
               sort="use_count", css="text-center fleet-col-w55",
               short_label="Usos"),
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
    # S153: el código (con su foto y enlace a la ficha) siempre delante.
    fixed=("codigo",),
))

# S153: columnas de Centros de gasto con celda propia en
# panel/fleet/_table_fragment.html; el resto sale como texto.
FLEET_RICH = (
    "familia", "descripcion", "tipo", "matricula", "documentos",
    "contadores", "requisito", "estado", "usos",
)


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

# S149 (sesión invasora): entrega de nóminas (PayslipItem decorados por
# panel/views_payslips._decorate). Solo datos del listado: nunca el
# contenido de la nómina, que es confidencial.
PAYSLIPS = register(Screen(
    key="payslips",
    label="Entrega de nóminas",
    columns=(
        Column("entrega", "Entrega", 10, lambda i: "#%s" % i.batch_id),
        Column("subida", "Subida", 16, lambda i: _local(i.batch.created_at),
               "DD/MM/YYYY HH:MM"),
        Column("carpeta", "Carpeta", 22, lambda i: i.batch.folder_name),
        Column("archivo", "Archivo", 30, lambda i: i.original_name),
        Column("paginas", "Páginas", 9, lambda i: i.pages_label),
        Column("trabajador", "Trabajador", 32, lambda i: i.person_label),
        Column("dni", "DNI/NIE leído", 13, lambda i: i.dni_found),
        Column("mes", "Mes", 18, lambda i: i.period_label),
        Column("movil", "Móvil", 15, lambda i: i.phone_label),
        Column("estado", "Estado", 18, lambda i: i.get_status_display()),
        Column("enviada", "Enviada", 16, lambda i: _local(i.sent_at),
               "DD/MM/YYYY HH:MM"),
        Column("nota", "Nota", 50, lambda i: i.note),
    ),
    panel_columns=[
        "entrega", "subida", "archivo", "paginas", "trabajador", "dni",
        "mes", "movil", "estado", "enviada", "nota",
    ],
))


# S153: equipos (un vehículo y una persona), pestaña Equipos.
CREWS = register(Screen(
    key="crews",
    label="Equipos",
    columns=(
        Column("codigo", "Código", 12, lambda r: r["crew"].machine.code),
        Column("centro", "Centro de gasto", 34, lambda r: r["machine"]),
        Column("matricula", "Matrícula", 14,
               lambda r: r["crew"].machine.plate),
        Column("persona", "Persona", 32, lambda r: r["person"]),
        Column("telefono", "Teléfono", 15, lambda r: r["phone"]),
        Column("telefono_emergencia", "Teléfono de emergencia", 15,
               lambda r: r["crew"].person.phone_emergency),
        Column("contacto_emergencia", "Contacto de emergencia", 26,
               lambda r: r["crew"].person.emergency_contact),
        Column("desde", "Desde", 12, lambda r: r["crew"].date_start, DATE),
        Column("hasta", "Hasta", 12, lambda r: r["crew"].date_end, DATE),
        Column("nota", "Nota", 40, lambda r: r["crew"].notes),
    ),
    panel_columns=[
        "codigo", "centro", "matricula", "persona", "telefono", "desde",
        "hasta",
    ],
))


# S153 (Miguel Ángel: "en la vista de revisiones falta la exportación
# porque necesito sacar un informe"). Revisiones del hub de
# Documentación: una fila por centro de gasto, con su plan, la última
# lectura y la última revisión y el estado de cada revisión. Los objetos
# son MachineAsset anotados por panel/views_service_tab._annotate_rows.
_SERVICE_STATE = {
    "OVERDUE": "Vencida", "UPCOMING": "Próxima", "OK": "Al día",
    "NO_RECORD": "Sin revisión anotada", "NO_READING": "Sin lectura",
}
_SERVICE_ORDER = ("OVERDUE", "UPCOMING", "NO_READING", "NO_RECORD", "OK")


def _service_situation(machine):
    states = [status.state for status in machine.service_statuses]
    for state in _SERVICE_ORDER:
        if state in states:
            return _SERVICE_STATE[state]
    return "Sin revisiones configuradas"


def _service_detail(machine):
    return "; ".join(
        "%s: %s" % (status.schedule.label, status.status_text)
        for status in machine.service_statuses
    )


def _last_value(attr, field_name):
    def getter(machine):
        row = getattr(machine, attr, None)
        return getattr(row, field_name, None) if row is not None else None
    return getter


def _record_value(field_name):
    def getter(machine):
        record = machine.last_record
        return getattr(record, field_name, None) if record else None
    return getter


def _status_of(machine, key):
    for status in machine.service_statuses:
        if status.schedule.key == key:
            return status
    return None


# S157 (Miguel Ángel: "saber qué revisiones tenemos constancia de que se
# han hecho, en qué fecha y con qué horas o kilómetros, y las que faltan
# para poder anotarlo a mano en un papel"). Por cada revisión del plan
# (horas, grúa, km): la última anotada (fecha y valor) y su situación;
# "No configurada" si la máquina no la tiene en el plan.
_SERVICE_KINDS = (
    ("HOURS", "horas", "Revisión por horas", "horas"),
    ("CRANE", "grua", "Revisión de grúa", "horas de grúa"),
    ("KM", "km", "Revisión por km", "km"),
)


def _kind_date(key):
    def getter(machine):
        status = _status_of(machine, key)
        record = status.last_record if status else None
        return record.service_date if record else None
    return getter


def _kind_value(key):
    def getter(machine):
        status = _status_of(machine, key)
        return status.last_value if status else None
    return getter


def _kind_state(key):
    def getter(machine):
        status = _status_of(machine, key)
        if status is None:
            return "No configurada"
        if status.last_record is None:
            if status.undated_value_record is not None:
                return "FALTA: revisión del %s sin %s anotadas" % (
                    status.undated_value_record.service_date.strftime(
                        "%d/%m/%Y"), "km" if key == "KM" else "horas")
            return "FALTA: sin revisión anotada"
        return _SERVICE_STATE.get(status.state, status.state)
    return getter


def _service_kind_columns():
    columns = []
    for key, slug, label, unit in _SERVICE_KINDS:
        columns += [
            Column("%s_fecha" % slug, "%s: fecha" % label, 12,
                   _kind_date(key), DATE),
            Column("%s_valor" % slug, "%s: %s" % (label, unit), 12,
                   _kind_value(key)),
            Column("%s_situacion" % slug, "%s: situación" % label, 24,
                   _kind_state(key)),
        ]
    return tuple(columns)


SERVICE_PAPER_COLUMNS = (
    "codigo", "descripcion", "matricula",
    "lectura_fecha", "lectura_horas", "lectura_horas_grua", "lectura_km",
    "horas_fecha", "horas_valor", "horas_situacion",
    "grua_fecha", "grua_valor", "grua_situacion",
    "km_fecha", "km_valor", "km_situacion",
    "a_mano_fecha", "a_mano_valor", "a_mano_notas",
)

SERVICE = register(Screen(
    key="service_tab",
    label="Revisiones",
    columns=(
        Column("codigo", "Código", 12, lambda m: m.code),
        Column("familia", "Familia", 16, lambda m: m.family),
        Column("descripcion", "Descripción", 30, lambda m: m.brand_model),
        Column("tipo", "Tipo", 22, lambda m: m.type_name),
        Column("matricula", "Matrícula", 12, lambda m: m.plate),
        Column("empresa", "Empresa", 26, _short_company),
        Column("activo", "Estado", 10,
               lambda m: "Activo" if m.is_active else "Inactivo"),
        Column("cada_horas", "Revisión cada (horas)", 12,
               lambda m: m.service_hours_interval),
        Column("cada_horas_grua", "Revisión cada (horas de grúa)", 14,
               lambda m: m.service_crane_hours_interval),
        Column("cada_km", "Revisión cada (km)", 12,
               lambda m: m.service_every_km),
        Column("lectura_fecha", "Última lectura", 12,
               lambda m: m.last_reading_date, DATE),
        Column("lectura_km", "Km (última lectura)", 12,
               _last_value("last_km", "km")),
        Column("lectura_horas", "Horas (última lectura)", 12,
               _last_value("last_hours", "hours")),
        Column("lectura_horas_grua", "Horas de grúa (última lectura)", 14,
               _last_value("last_crane_hours", "crane_hours")),
        Column("revision_fecha", "Última revisión", 12,
               _record_value("service_date"), DATE),
        Column("revision_horas", "Horas (última revisión)", 12,
               _record_value("hours")),
        Column("revision_horas_grua", "Horas de grúa (última revisión)", 14,
               _record_value("crane_hours")),
        Column("revision_km", "Km (última revisión)", 12,
               _record_value("km")),
        Column("revision_notas", "Observaciones (última revisión)", 30,
               _record_value("notes")),
        Column("situacion", "Situación", 18, _service_situation),
        Column("estado_revisiones", "Estado de cada revisión", 60,
               _service_detail),
    ) + _service_kind_columns() + (
        # S157: casillas vacías para anotar a mano sobre el papel.
        Column("a_mano_fecha", "Fecha (a mano)", 14, lambda m: None),
        Column("a_mano_valor", "Horas / km (a mano)", 16, lambda m: None),
        Column("a_mano_notas", "Observaciones (a mano)", 30,
               lambda m: None),
    ),
    panel_columns=[
        "codigo", "familia", "descripcion", "matricula", "cada_horas",
        "cada_horas_grua", "cada_km", "lectura_fecha", "lectura_km",
        "lectura_horas", "lectura_horas_grua", "revision_fecha",
        "situacion", "estado_revisiones",
    ],
))



# S157 (Miguel Ángel: en «Columnas» de Personal y Repostajes, las
# columnas que hoy solo salen al exportar, como en Centros de gasto).
# Listado de Personal: las columnas de siempre (con celda propia en
# panel/documentation_h30/_personal_results.html y las mismas claves
# que ya tenía guardadas cada usuario) y, detrás, las de la exportación
# (panel/views_personal_export.py), que salen como texto. Los objetos
# son PersonIdentity preparados por _person_list_page.
def _personal_columns():
    from panel.views_personal_export import PERSONAL_EXPORT_COLUMNS

    by_key = {c[0]: c for c in PERSONAL_EXPORT_COLUMNS}
    own = (
        Column("dni", "DNI", 12, by_key["dni"][3]),
        Column("hire_date", "Alta", 12, by_key["fecha_alta"][3],
               DATE, sort="hire_date"),
        Column("doc_count", "Documentos", 10, by_key["documentos"][3],
               sort="doc_count"),
        Column("requirement", "Requisitos de documentación", 26,
               by_key["requisito"][3], sort="requirement_name"),
        Column("onboarding", "Alta en el fichaje", 22,
               by_key["alta_fichaje"][3], sort="onboarding"),
        Column("section", "Sección", 22, by_key["seccion"][3],
               sort="section"),
        Column("schedule", "Horario", 22, by_key["horario"][3],
               sort="schedule"),
    )
    extra = tuple(
        Column(key, label, width, getter, DATE if is_date else None)
        for key, label, width, getter, is_date in PERSONAL_EXPORT_COLUMNS
        if key in PERSONAL_EXTRA
    )
    return own + extra


# Columnas de la exportación que el listado no tenía (misma clave en
# el listado y en la exportación), en el orden de la exportación.
PERSONAL_EXTRA = (
    "primer_apellido", "segundo_apellido", "nombre", "fecha_nacimiento",
    "empresa", "estado", "fecha_baja", "categoria", "estado_requisito",
    "telefono", "telefono_2", "contacto_emergencia", "telefono_emergencia",
    "email", "direccion", "codigo_postal", "poblacion", "provincia",
    "num_ss", "cad_dni", "cad_carnet", "cad_gruista", "cad_cap",
    "cad_tacografo", "reconocimiento", "usuario_panel",
)
PERSONAL = register(Screen(
    key="personal",
    label="Personal",
    columns=_personal_columns(),
    panel_columns=[
        "dni", "hire_date", "doc_count", "requirement", "onboarding",
        "section", "schedule",
    ],
))
PERSONAL_RICH = (
    "dni", "hire_date", "doc_count", "requirement", "onboarding",
    "section", "schedule",
)


def _price(row):
    price = row.get("price")
    return float(price) if price is not None else None


# Listado de Repostajes (vista de suministros): las columnas de siempre
# (celda propia en panel/refuels/_table.html) y, detrás, las de la
# exportación que no tenía. Los objetos son los diccionarios de
# panel/views_refuels._row. Fecha y hora van siempre delante (fijas en
# la tabla, fuera de la configuración).
REFUELS = register(Screen(
    key="refuels",
    label="Repostajes",
    columns=(
        Column("machine", "Centro de gasto", 14,
               lambda r: r["machine"].code if r["machine"] else "",
               sort="machine"),
        Column("vehicle", "Vehículo (GasoGes)", 18,
               lambda r: r["vehicle_label"], sort="vehicle"),
        Column("driver", "Quién repostó", 32, lambda r: r["driver"],
               sort="driver"),
        Column("value", "KM tecleado", 12, lambda r: r["value"],
               sort="value", css="text-end"),
        Column("litres", "Litros", 9, lambda r: r["litres"],
               sort="litres", css="text-end"),
        Column("status", "Estado", 24, lambda r: r["status"],
               sort="status"),
        Column("unit", "Unidad", 11, lambda r: r["unit"]),
        Column("reason", "Motivo", 48, lambda r: r["note"]),
        Column("plate", "Matrícula (GasoGes)", 16, lambda r: r["plate"]),
        Column("name", "Nombre (GasoGes)", 28, lambda r: r["vehicle_name"]),
        Column("price", "Precio", 9, _price, css="text-end"),
        Column("hours", "Horas sin anotar", 20, lambda r: r["hours_issue"]),
    ),
    panel_columns=[
        "machine", "vehicle", "driver", "value", "litres", "status",
        "unit", "reason",
    ],
))
REFUELS_RICH = (
    "machine", "vehicle", "driver", "value", "litres", "status", "unit",
    "reason",
)


def _naive(value):
    """Hora local sin zona, como la espera Excel."""
    from django.utils import timezone
    return timezone.localtime(value).replace(tzinfo=None) if value else None


# S149 (Miguel Ángel, 20/11): informe del alta en el fichaje (quién la
# tiene enviada, recibida, leída y no ficha). Filas de
# panel/clock_onboarding_report.build_rows.
CLOCK_ONBOARDING = register(Screen(
    key="clock_onboarding",
    label="Informe del alta en el fichaje",
    columns=(
        Column("trabajador", "Trabajador", 34, lambda r: r["label"]),
        Column("dni", "DNI", 12, lambda r: r["dni"]),
        Column("seccion", "Sección", 18, lambda r: r["section"]),
        Column("telefono", "Teléfono", 15, lambda r: r["phone"]),
        Column("usuario", "Usuario del panel", 22, lambda r: r["username"]),
        Column("situacion", "Situación", 34, lambda r: r["state_label"]),
        Column("alta", "Alta enviada", 16,
               lambda r: _naive(r["first_sent"]), "DD/MM/YYYY HH:MM"),
        Column("envios", "Envíos", 8, lambda r: r["sends"]),
        Column("reenvio", "Último reenvío", 16,
               lambda r: _naive(r["last_sent"]), "DD/MM/YYYY HH:MM"),
        Column("whatsapp", "WhatsApp", 20,
               lambda r: r["whatsapp"]),
        Column("whatsapp_fecha", "Estado del WhatsApp", 16,
               lambda r: _naive(r["whatsapp_at"]), "DD/MM/YYYY HH:MM"),
        Column("abierta", "Abrió la circular", 16,
               lambda r: _naive(r["opened"]), "DD/MM/YYYY HH:MM"),
        Column("acceso", "Último acceso al panel", 16,
               lambda r: _naive(r["last_login"]), "DD/MM/YYYY HH:MM"),
        Column("primer_fichaje", "Primer fichaje", 16,
               lambda r: _naive(r["first_clock"]), "DD/MM/YYYY HH:MM"),
        Column("ultimo_fichaje", "Último fichaje", 16,
               lambda r: _naive(r["last_clock"]), "DD/MM/YYYY HH:MM"),
        Column("dias_alta", "Días sin fichar desde el alta", 12,
               lambda r: r["days_since_first"]),
        Column("dias_reenvio", "Días sin fichar desde el reenvío", 12,
               lambda r: r["days_since_resend"]),
        Column("dias_fichaje", "Días desde el último fichaje", 12,
               lambda r: r["days_since_clock"]),
        Column("ficha", "Ficha (ajuste)", 10,
               lambda r: "" if r["clocks"] is None
               else "Sí" if r["clocks"] else "No"),
    ),
    panel_columns=[
        "trabajador", "seccion", "situacion", "alta", "envios", "reenvio",
        "whatsapp", "abierta", "acceso", "ultimo_fichaje", "dias_alta",
        "dias_reenvio", "dias_fichaje",
    ],
))
