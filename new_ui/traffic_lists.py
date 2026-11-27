# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/traffic_lists.py
"""
Lists of the Traffic section of the new interface (S165).

---

Listados de la sección Tráfico de la nueva interfaz (S165, invasora
sobre H11), al nivel de Empresa, Personal y Centros de gasto: el
planning de las grúas (servicios, cargas y nombres), los envíos a los
gruistas, los albaranes de grúa, las obras y los clientes. Mismo motor
que el resto (new_ui/lists.py: ListDef, Col, Extra), con el bloque
común de filtros, columnas, orden por cabecera, ventanas y exportar.
"""
from django.db.models import Count, Q
from django.urls import reverse

from new_ui.lists import (
    Col, Extra, ListDef, fmt_date, fmt_datetime, person_name, short,
)


def _yes(value):
    return "Sí" if value else ""


def _person_or_null(path):
    """
    Common person filters, keeping the rows without a worker.
    ---
    Filtro por personas (estado, empresa, grupo, sección) que no quita
    las filas sin gruista reconocido: también hay que verlas.
    """
    def apply(qs, ids):
        return qs.filter(Q(**{path + "__in": ids})
                         | Q(**{path + "__isnull": True}))
    return apply


def _row_sheet(tab):
    base = reverse("new_ui:row_sheet")
    return lambda r: "%s?s=tra&t=%s&pk=%s" % (base, tab, r.pk)


def _open_action(definition, label="Abrir"):
    """
    Row menu «Abrir» (three dots and right click) = clicking the row.
    ---
    «Abrir» en el menú de la fila (tres puntos y botón derecho): lo
    mismo que pulsarla; se añade a lo que ya tuviera la fila.
    """
    from urllib.parse import quote

    previous = definition.actions

    def actions(row):
        url = definition.row_url(row)
        return [(label, "bi-box-arrow-up-right", "#nui-open:%s:%s" % (
            quote(url, safe=""), quote(definition.row_title, safe="")))
        ] + list(previous(row))
    definition.actions = actions
    return definition


def _choices(qs, field):
    """Distinct non-empty values of a field, as filter options."""
    return [(v, v) for v in qs.exclude(**{field: ""}).order_by(
        field).values_list(field, flat=True).distinct()[:200]]


# ------------------------------------------------------------- servicios
def _service_time(r):
    if r.planned_time:
        return r.planned_time.strftime("%H:%M")
    return r.raw_time


def _service_person(r):
    if r.person_id:
        return person_name(r.person)
    if r.raw_person:
        return "%s (sin reconocer)" % r.raw_person
    return "Sin gruista"


def _service_actions(r):
    url = reverse("new_ui:traffic_send")
    actions = []
    if r.kind == r.KIND_SERVICE and not r.removed_from_planning:
        actions.append(("Enviar ubicación y hora", "bi-whatsapp",
                        "#nui-post:%s:selected=%d" % (
                            url.replace(":", "%3A"), r.pk)))
    return actions


def _services_def():
    """
    Tráfico › Planning › Servicios: every row of the planning.

    ---

    Cada fila del planning (servicio o anotación) con su gruista,
    vehículo, empresa, lugar y hora tal cual, y cómo va su aviso.
    """
    from crane_albaranes.models import PlanningService

    def queryset(company):
        return PlanningService.objects.filter(company=company).select_related(
            "person", "machine", "client", "worksite")

    def changed(qs, value):
        return qs.filter(changed_after_notice=(value == "si"))

    def recognized(qs, value):
        if value == "si":
            return qs.filter(person__isnull=False)
        return qs.filter(person__isnull=True).exclude(raw_person="")

    def removed(qs, value):
        return qs.filter(removed_from_planning=(value == "si"))

    def contracted(company):
        return _choices(PlanningService.objects.filter(company=company),
                        "contracted_by")

    return ListDef(
        "Servicios", queryset, [
            Col("fecha", "Fecha", lambda r: fmt_date(r.day), "day",
                "text-nowrap"),
            Col("hora", "Hora", _service_time, "planned_time",
                "text-nowrap"),
            Col("persona", "Gruista", _service_person,
                "person__first_surname", entity=True),
            Col("como_viene", "Personal (planning)", lambda r: r.raw_person,
                "raw_person"),
            Col("vehiculo", "Vehículo", lambda r: r.machine.code
                if r.machine_id else r.raw_vehicle, "raw_vehicle",
                "text-nowrap"),
            Col("tons", "Tons", lambda r: r.tonnage, "tonnage"),
            Col("empresa", "Empresa", lambda r: r.raw_client, "raw_client"),
            Col("lugar", "Lugar de trabajo", lambda r: r.raw_place,
                "raw_place"),
            Col("obra", "Obra", lambda r: r.worksite.code
                if r.worksite_id else "", "worksite__code", "text-nowrap"),
            Col("observaciones", "Observaciones",
                lambda r: short(r.observations, 120), "observations"),
            Col("precio", "Precio", lambda r: r.price, "price"),
            Col("contratado", "Contratado", lambda r: r.contracted_by,
                "contracted_by"),
            Col("oferta", "Oferta económica", lambda r: r.offer_ref,
                "offer_ref"),
            Col("contacto", "Contacto", lambda r: r.contact, "contact"),
            Col("tipo", "Tipo", lambda r: r.get_kind_display(), "kind"),
            Col("aviso", "Aviso", lambda r: r.get_notice_status_display(),
                "notice_status"),
            Col("avisado", "Avisado", lambda r: fmt_datetime(r.notified_at),
                "notified_at", "text-nowrap"),
            Col("fallo", "Fallo del aviso", lambda r: r.notice_error,
                "notice_error"),
            Col("cambiado", "Cambiado después del aviso",
                lambda r: _yes(r.changed_after_notice),
                "changed_after_notice"),
            Col("quitado", "Quitado del planning",
                lambda r: _yes(r.removed_from_planning),
                "removed_from_planning"),
            Col("fila", "Fila del Excel", lambda r: r.position, "position",
                "text-end"),
        ],
        entity="person", entity_path="person",
        entity_filter=_person_or_null("person"),
        entity_of=lambda r: r.person,
        search=("raw_person", "raw_client", "raw_place", "raw_vehicle",
                "observations", "contact", "offer_ref", "contracted_by",
                "person__given_name", "person__first_surname"),
        date_field="day", default_order=("day", "position"),
        actions=_service_actions, row_url=_row_sheet("servicios"),
        row_title="Servicio del planning",
        default_cols=["fecha", "hora", "persona", "vehiculo", "tons",
                      "empresa", "lugar", "observaciones", "aviso",
                      "avisado", "cambiado"],
        col_templates={
            "Comercial": ["fecha", "persona", "empresa", "lugar", "precio",
                          "contratado", "oferta", "contacto"],
            "Avisos": ["fecha", "hora", "persona", "lugar", "aviso",
                       "avisado", "fallo", "cambiado", "quitado"],
        },
        extras=[
            Extra("cambios", "Cambiado después del aviso",
                  lambda company: [("si", "Cambiados (reenviar)"),
                                   ("no", "Sin cambios")], changed),
            Extra("reconocido", "Gruista",
                  lambda company: [("si", "Reconocido"),
                                   ("no", "Sin reconocer")], recognized),
            Extra("quitados", "Quitados del planning",
                  lambda company: [("no", "Solo los que siguen"),
                                   ("si", "Solo los quitados")], removed),
            Extra("contratado", "Contratado", contracted,
                  lambda qs, v: qs.filter(contracted_by=v)),
        ],
        note="Cada fila del planning de grúas. Pulsa una para verla "
             "entera. Las anotaciones (BAJA, vacaciones...) no se avisan.")


# ---------------------------------------------------------------- cargas
def _imports_def():
    """
    Tráfico › Planning › Cargas: the planning loads and their problems.
    ---
    Las cargas del planning: rango de días, cuántos servicios nuevos,
    cambiados y quitados, y lo que no se pudo reconocer.
    """
    from crane_albaranes.models import PlanningImport

    def queryset(company):
        return PlanningImport.objects.filter(company=company).select_related(
            "uploaded_by__user")

    def by(r):
        cu = r.uploaded_by
        return getattr(getattr(cu, "user", None), "username", "") if cu \
            else ""

    return ListDef(
        "Cargas", queryset, [
            Col("cargado", "Cargado", lambda r: fmt_datetime(r.created_at),
                "created_at", "text-nowrap"),
            Col("archivo", "Archivo", lambda r: r.file_name, "file_name"),
            Col("desde", "Desde", lambda r: fmt_date(r.date_from),
                "date_from", "text-nowrap"),
            Col("hasta", "Hasta", lambda r: fmt_date(r.date_to), "date_to",
                "text-nowrap"),
            Col("dias", "Días", lambda r: r.days_loaded, "days_loaded",
                "text-end"),
            Col("filas", "Filas", lambda r: r.rows_total, "rows_total",
                "text-end"),
            Col("nuevos", "Nuevos", lambda r: r.rows_created,
                "rows_created", "text-end"),
            Col("cambiados", "Cambiados", lambda r: r.rows_updated,
                "rows_updated", "text-end"),
            Col("quitados", "Quitados", lambda r: r.rows_removed,
                "rows_removed", "text-end"),
            Col("problemas", "Avisos", lambda r: len(r.problems or []),
                "", "text-end"),
            Col("por", "Cargado por", by),
        ],
        search=("file_name",), date_field="created_at",
        date_is_datetime=True, default_order=("-created_at",),
        row_url=lambda r: reverse("new_ui:traffic_import_sheet",
                                  args=[r.pk]),
        row_title="Carga del planning",
        note="Pulsa una carga para ver lo que no se pudo reconocer.")


# ---------------------------------------------------------------- nombres
def _prepare_names(model, with_rows):
    """
    ListDef.prepare of a names list: why each one is not assigned.
    ---
    Por qué no se asigna solo cada nombre (con las mismas reglas que al
    cargar, y con su propia lista) y, en el planning, cuántas filas
    trae.
    """
    def prepare(rows):
        from crane_albaranes.models import PlanningService
        from crane_albaranes.traffic import NameResolver, plain

        if not rows:
            return
        counts = {}
        if with_rows:
            for raw, n in PlanningService.objects.filter(
                    company_id=rows[0].company_id).exclude(
                    raw_person="").values_list("raw_person").annotate(
                    n=Count("pk")):
                key = plain(raw)
                counts[key] = counts.get(key, 0) + n
        resolver = None
        for row in rows:
            row.nui_rows = counts.get(row.key, 0)
            row.nui_why = ""
            if row.person_id and not row.person.is_active_employee:
                row.nui_why = "asignado a un trabajador de baja"
            elif not row.person_id and not row.not_a_worker:
                resolver = resolver or NameResolver(row.company, model)
                dates = (row.seen_from, row.seen_to) if row.seen_from \
                    and row.seen_to else None
                row.nui_why = resolver.resolve(row.text, dates)[1].replace(
                    "«%s» " % row.text, "")
    return prepare


def _name_person(r):
    """Worker of a planning name, «(de baja)» if no longer active."""
    if not r.person_id:
        return ""
    label = person_name(r.person)
    if not r.person.is_active_employee:
        label += " (de baja)"
    return label


def _name_state(r):
    if r.person_id:
        return "Trabajador"
    if r.not_a_worker:
        return "No es un trabajador"
    return "Sin asignar"


def names_def(kind="tra"):
    """
    Names list: Tráfico › Planning › Nombres or the vacation chart's.

    ---

    Cómo viene escrito cada trabajador y quién es. Dos listas separadas
    (S165: «lo que se suba a tráfico quede como tráfico, y lo que se
    suba a vacaciones quede como vacaciones»): `tra`, la del planning de
    grúas (Tráfico › Planning › Nombres); `vac`, la del cuadrante de
    vacaciones (Personal › Vacaciones › Nombres del cuadrante). Los que
    no se reconocen solos salen «Sin asignar»: se asignan una vez y vale
    para siempre.
    """
    if kind == "vac":
        from hr_calendar.models import VacationChartName as model
        sheet = "new_ui:vacation_name_sheet"
        title = "Nombre del cuadrante"
        note = ("Cómo viene escrito cada trabajador en el cuadrante de "
                "vacaciones. Pulsa uno para decir quién es (o que no es un "
                "trabajador).")
    else:
        from crane_albaranes.models import PlanningName as model
        sheet = "new_ui:traffic_name_sheet"
        title = "Nombre del planning"
        note = ("Cómo viene escrito cada trabajador en el planning de "
                "grúas. Pulsa uno para decir quién es (o que no es un "
                "trabajador).")

    def queryset(company):
        return model.objects.filter(company=company).select_related(
            "person", "updated_by__user")

    def state(qs, value):
        if value == "trabajador":
            return qs.filter(person__isnull=False)
        if value == "no":
            return qs.filter(not_a_worker=True)
        return qs.filter(person__isnull=True, not_a_worker=False)

    cols = [
        Col("como_viene", "Como viene", lambda r: r.text, "text"),
        Col("persona", "Trabajador", _name_person,
            "person__first_surname", entity=True),
        Col("estado", "Estado", _name_state, "not_a_worker"),
        Col("motivo", "Por qué no se asigna solo",
            lambda r: getattr(r, "nui_why", "")),
        Col("aparece", "Aparece", lambda r: "%s – %s" % (
            fmt_date(r.seen_from), fmt_date(r.seen_to))
            if r.seen_from else "", "seen_from", "text-nowrap"),
    ]
    if kind == "tra":
        cols.append(Col("filas", "Filas del planning",
                        lambda r: getattr(r, "nui_rows", ""), "",
                        "text-end"))
    cols += [
        Col("por", "Asignado por", lambda r: getattr(getattr(
            r.updated_by, "user", None), "username", "")
            if r.updated_by_id else ""),
        Col("cuando", "Asignado", lambda r: fmt_datetime(r.updated_at)
            if r.person_id or r.not_a_worker else "", "updated_at",
            "text-nowrap"),
    ]
    return ListDef(
        "Nombres del cuadrante" if kind == "vac" else "Nombres", queryset,
        cols, entity="person", entity_path="person",
        entity_filter=_person_or_null("person"),
        entity_of=lambda r: r.person,
        search=("text", "person__given_name", "person__first_surname"),
        default_order=("person_id", "not_a_worker", "text"),
        prepare=_prepare_names(model, kind == "tra"),
        row_url=lambda r: reverse(sheet, args=[r.pk]), row_title=title,
        extras=[Extra("estado", "Estado", lambda company: [
            ("sin", "Sin asignar"), ("trabajador", "Trabajador"),
            ("no", "No es un trabajador")], state)],
        note=note)


# ----------------------------------------------------------------- envíos
def _notices_def():
    """
    Tráfico › Envíos: every WhatsApp sent to a crane operator.
    ---
    Cada WhatsApp enviado a un gruista: a quién, qué se le dijo, si
    Twilio lo aceptó y si le llegó o lo leyó.
    """
    from crane_albaranes.models import PlanningNotice

    def queryset(company):
        return PlanningNotice.objects.filter(company=company).select_related(
            "person", "service", "sent_by__user")

    def status(qs, value):
        if value == "sin":
            return qs.filter(whatsapp_status="")
        return qs.filter(whatsapp_status=value)

    def ok(qs, value):
        return qs.filter(ok=(value == "si"))

    return ListDef(
        "Envíos", queryset, [
            Col("enviado", "Enviado", lambda r: fmt_datetime(r.sent_at),
                "sent_at", "text-nowrap"),
            Col("persona", "Gruista", lambda r: person_name(r.person),
                "person__first_surname", entity=True),
            Col("dia", "Día del servicio", lambda r: fmt_date(r.day), "day",
                "text-nowrap"),
            Col("movil", "Móvil", lambda r: r.phone, "phone"),
            Col("mensaje", "Mensaje", lambda r: short(r.text, 120), "text"),
            Col("aceptado", "Aceptado", lambda r: "Sí" if r.ok else "No",
                "ok"),
            Col("estado", "Estado del WhatsApp", lambda r: r.status_label,
                "whatsapp_status"),
            Col("estado_a", "Estado a las",
                lambda r: fmt_datetime(r.whatsapp_status_at),
                "whatsapp_status_at", "text-nowrap"),
            Col("como", "Cómo salió", lambda r: (
                "Texto libre" if r.sent_as_text else "Plantilla")
                if r.ok else "", "sent_as_text"),
            Col("fallo", "Fallo", lambda r: r.error, "error"),
            Col("por", "Enviado por", lambda r: getattr(getattr(
                r.sent_by, "user", None), "username", "")
                if r.sent_by_id else ""),
        ],
        entity="person", entity_path="person",
        entity_filter=_person_or_null("person"),
        entity_of=lambda r: r.person,
        search=("phone", "text", "error", "person__given_name",
                "person__first_surname"),
        date_field="sent_at", date_is_datetime=True,
        default_order=("-sent_at",), row_url=_row_sheet("envios"),
        row_title="Envío al gruista",
        extras=[
            Extra("aceptado", "Aceptado por Twilio", lambda company: [
                ("si", "Aceptados"), ("no", "Fallidos")], ok),
            Extra("estado", "Estado del WhatsApp", lambda company: [
                ("sin", "Sin informe"), ("sent", "Enviado"),
                ("delivered", "Entregado"), ("read", "Leído"),
                ("undelivered", "No entregado"), ("failed", "Fallido")],
                status),
        ],
        note="Solo se envía la ubicación de la obra y la hora, hasta que "
             "la dirección ordene implantar el albarán digital.")


# -------------------------------------------------------------- albaranes
def _albaranes_def():
    """
    Tráfico › Albaranes: the digital crane albaranes.
    ---
    Los albaranes de trabajo digitales de las grúas (H11, S162).
    """
    from crane_albaranes.models import CraneAlbaran

    def queryset(company):
        return CraneAlbaran.objects.filter(company=company).select_related(
            "person", "worksite", "machine")

    return ListDef(
        "Albaranes", queryset, [
            Col("numero", "Nº", lambda r: r.number, "number",
                "text-nowrap"),
            Col("fecha", "Fecha", lambda r: fmt_date(r.day), "day",
                "text-nowrap"),
            Col("persona", "Gruista", lambda r: person_name(r.person),
                "person__first_surname", entity=True),
            Col("cliente", "Cliente", lambda r: r.client_name,
                "client_name"),
            Col("obra", "Obra", lambda r: r.worksite.name
                if r.worksite_id else r.work_place, "worksite__name"),
            Col("maquina", "Máquina", lambda r: r.machine.code
                if r.machine_id else "", "machine__code", "text-nowrap"),
            Col("estado", "Estado", lambda r: r.get_status_display(),
                "status"),
            Col("origen", "Origen", lambda r: r.get_origin_display(),
                "origin"),
            Col("horas", "Horas", lambda r: r.hours_worked or "",
                "hours_worked", "text-end"),
            Col("entregado_a", "Entregado a", lambda r: r.delivered_to,
                "delivered_to"),
            Col("entregado", "Entregado", lambda r: fmt_datetime(
                r.delivered_at), "delivered_at", "text-nowrap"),
        ],
        entity="person", entity_path="person",
        entity_filter=_person_or_null("person"),
        entity_of=lambda r: r.person,
        search=("number", "client_name", "work_place",
                "person__given_name", "person__first_surname"),
        date_field="day", default_order=("-day", "-number"),
        row_url=_row_sheet("albaranes"), row_title="Albarán de grúa",
        note="Los albaranes digitales (aún sin implantar: de momento al "
             "gruista solo le llega la ubicación y la hora).")


# ------------------------------------------------------- obras y clientes
def _worksites_def():
    """
    Tráfico › Obras: the worksites (created from the planning too).
    ---
    Las obras: las de siempre y las que se dan de alta solas al cargar
    el planning (sin coordenadas: el mapa del aviso solo va cuando se
    ponen).
    """
    from worksites.models import Worksite

    def queryset(company):
        return Worksite.objects.select_related("client").annotate(
            nui_services=Count("planning_services", distinct=True))

    def coords(qs, value):
        has = Q(latitude__isnull=False, longitude__isnull=False)
        return qs.filter(has) if value == "si" else qs.exclude(has)

    def active(qs, value):
        return qs.filter(is_active=(value == "si"))

    return ListDef(
        "Obras", queryset, [
            Col("codigo", "Código", lambda r: r.code, "code",
                "text-nowrap"),
            Col("nombre", "Obra", lambda r: r.name, "name"),
            Col("cliente", "Cliente", lambda r: r.client_label,
                "client__name"),
            Col("ubicacion", "Ubicación", lambda r: r.address, "address"),
            Col("localidad", "Localidad", lambda r: r.locality, "locality"),
            Col("provincia", "Provincia", lambda r: r.province, "province"),
            Col("mapa", "Coordenadas", lambda r: "Sí" if r.latitude
                is not None and r.longitude is not None else "", "latitude"),
            Col("servicios", "Servicios", lambda r: r.nui_services,
                "nui_services", "text-end"),
            Col("contacto", "Contacto", lambda r: " ".join(
                p for p in (r.contact_name, r.contact_phone) if p),
                "contact_name"),
            Col("activa", "Activa", lambda r: "Sí" if r.is_active else "No",
                "is_active"),
            Col("notas", "Notas", lambda r: short(r.notes, 80), "notes"),
        ],
        search=("code", "name", "client__name", "client_name", "address",
                "locality", "project_number"),
        default_order=("name",),
        row_url=lambda r: reverse("new_ui:traffic_worksite_sheet",
                                  args=[r.pk]),
        row_title="Obra",
        default_cols=["codigo", "nombre", "cliente", "ubicacion",
                      "localidad", "mapa", "servicios", "activa"],
        extras=[
            Extra("mapa", "Coordenadas", lambda company: [
                ("si", "Con coordenadas"), ("no", "Sin coordenadas")],
                coords),
            Extra("activa", "Activa", lambda company: [
                ("si", "Activas"), ("no", "Finalizadas")], active),
        ],
        note="Pulsa una obra para modificarla y ponerle la ubicación y las "
             "coordenadas (sin ellas el aviso al gruista va sin mapa).")


def _clients_def():
    """
    Tráfico › Clientes.
    ---
    Los clientes (EMPRESA del planning), con sus obras y servicios.
    """
    from worksites.models import Client

    def queryset(company):
        return Client.objects.annotate(
            nui_sites=Count("worksites", distinct=True),
            nui_services=Count("planning_services", distinct=True))

    def active(qs, value):
        return qs.filter(is_active=(value == "si"))

    return ListDef(
        "Clientes", queryset, [
            Col("nombre", "Cliente", lambda r: r.name, "name"),
            Col("nif", "N.I.F.", lambda r: r.tax_id, "tax_id",
                "text-nowrap"),
            Col("localidad", "Localidad", lambda r: r.locality, "locality"),
            Col("provincia", "Provincia", lambda r: r.province, "province"),
            Col("telefono", "Teléfono", lambda r: r.phone, "phone"),
            Col("correo", "Correo", lambda r: r.email, "email"),
            Col("obras", "Obras", lambda r: r.nui_sites, "nui_sites",
                "text-end"),
            Col("servicios", "Servicios", lambda r: r.nui_services,
                "nui_services", "text-end"),
            Col("activo", "Activo", lambda r: "Sí" if r.is_active else "No",
                "is_active"),
        ],
        search=("name", "tax_id", "locality", "email"),
        default_order=("name",),
        row_url=lambda r: reverse("new_ui:traffic_client_sheet",
                                  args=[r.pk]),
        row_title="Cliente",
        extras=[Extra("activo", "Activo", lambda company: [
            ("si", "Activos"), ("no", "De baja")], active)],
        note="Pulsa un cliente para modificarlo. Si uno sale repetido por "
             "una errata del planning, márcalos y únelos en Acciones.")


def traffic_lists():
    """
    {tab: ListDef} of the Traffic section.
    ---
    Los listados de Tráfico, por su clave.
    """
    lists = {
        "servicios": _services_def(),
        "cargas": _imports_def(),
        "nombres": names_def("tra"),
        "envios": _notices_def(),
        "albaranes": _albaranes_def(),
        "obras": _worksites_def(),
        "clientes": _clients_def(),
    }
    for definition in lists.values():
        _open_action(definition)
    return lists
