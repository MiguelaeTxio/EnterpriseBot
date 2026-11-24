# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/lists.py
"""
List engine of the new interface: one definition per list tab.

---

Motor de listados de la nueva interfaz (S163, sesión invasora de UX).
Miguel Ángel: "Termina todo". Cada pestaña de Documentos, Personal y
Centros de gasto es una definición (`ListDef`): de qué modelo salen sus
filas, sus columnas, en qué campos busca, a qué fecha se aplica el
periodo y cómo llega a su persona o máquina. Todo lo demás es común y
sale de aquí: el bloque común de filtros (Buscar · Periodo · Estado ·
Empresa · Grupo · Familia/Sección, directriz 4.27 4bis), la vista de
una sola máquina o persona (`scope`), el orden múltiple por cabecera
(en la base de datos, sin dato siempre al final), las columnas visibles
y el límite de filas pintadas.

Las reglas de Personal son las de su pestaña de siempre
(panel/views_documentation_h30._apply_personal_filters): activos = en el
Excel de plantilla; inactivos = el resto; empresas agrupadas por
COMPANY_FILTER_CHOICES. Los grupos son los grupos de selección de
siempre (panel/person_groups).
"""
import contextvars
import datetime
from types import SimpleNamespace

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import F, OuterRef, Q, Subquery
from django.urls import reverse
from django.utils import timezone

from new_ui.filters import parse_sort, period_range

ROW_LIMIT = 1000
BUCKET = "cgs_grupo_alvarez"


# ------------------------------------------------------------ utilidades
def fmt_date(value):
    return value.strftime("%d/%m/%Y") if value else ""


def fmt_datetime(value):
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d/%m/%Y %H:%M")


def fmt_num(value, decimals=2):
    if value in (None, ""):
        return ""
    text = ("%.*f" % (decimals, value)).rstrip("0").rstrip(".")
    return text.replace(".", ",")


def disp(obj, field):
    """Texto de un campo con opciones (o su valor tal cual)."""
    method = getattr(obj, "get_%s_display" % field, None)
    return method() if callable(method) else getattr(obj, field, "")


def short(text, size=80):
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= size else text[:size - 1] + "…"


def person_name(person):
    if person is None:
        return ""
    return " ".join(p for p in (person.given_name, person.first_surname,
                                person.second_surname) if p).strip() \
        or person.dni or "#%s" % person.pk


def short_company(machine):
    from new_ui.docs_core import short_company_name as _short_company_name

    return _short_company_name(machine.company_name)


def machine_label(machine):
    return machine.code if machine else ""


class Col:
    """
    One column: key, header, value(row) -> text, ORM order path, css.

    ---

    Una columna: clave, cabecera, valor que se pinta (y se exporta),
    campo por el que ordena la base de datos ("" = no ordenable) y
    clase CSS. `entity` marca la columna que lleva a la persona o
    máquina de la fila (botón derecho, ver sus listados).
    """

    def __init__(self, key, label, value, order="", css="", entity=False):
        self.key = key
        self.label = label
        self.value = value
        self.order = order
        self.css = css
        self.entity = entity


class Extra:
    """
    One own filter of a list tab ("Filtros de <pestaña>").

    ---

    Un filtro propio de una pestaña de listado (S163): `options(company)`
    da [(valor, texto)]; `apply(qs, valor)` lo aplica en la consulta o,
    si no sale de la BD (`post=True`), `keep(fila, valor)` decide fila a
    fila después de `ListDef.prepare` (p. ej. el estado real de un
    documento).
    """

    def __init__(self, key, label, options, apply=None, keep=None):
        self.key = key
        self.label = label
        self.options = options
        self.apply = apply
        self.keep = keep
        self.post = keep is not None


def extra_param(tab, extra):
    return "x_%s_%s" % (tab, extra.key)


def extras_for(definition, company):
    """
    Own filters of a tab: the declared ones plus one per choice column.

    ---

    Los filtros propios de una pestaña: los declarados en la definición
    (`extras`) y, además, uno por cada columna que ordena por un campo
    con opciones fijas (estado, urgencia, entrada/salida...) o por el
    rótulo de un catálogo (motivo de ausencia, tipo de documento...),
    con esas mismas opciones. Así ninguna pestaña se queda sin ellos.
    """
    out = list(definition.extras)
    taken = {extra.key for extra in out}
    model = definition.queryset(company).model
    for col in definition.columns:
        if col.entity or not col.order or col.key in taken:
            continue
        parts = col.order.split("__")
        try:
            field = model._meta.get_field(parts[0])
        except Exception:
            continue
        if len(parts) == 1 and getattr(field, "choices", None):
            choices = [(str(v), str(t)) for v, t in field.flatchoices]
            out.append(Extra(
                col.key, col.label, lambda company, c=choices: c,
                lambda qs, value, f=parts[0]: qs.filter(**{f: value})))
            taken.add(col.key)
        elif (len(parts) == 2 and field.is_relation and field.many_to_one
              and parts[1] in ("label", "name")):
            related = field.related_model

            def options(company, related=related, attr=parts[1]):
                return [(str(pk), str(text)) for pk, text in
                        related.objects.order_by(attr).values_list(
                            "pk", attr)[:300]]
            out.append(Extra(
                col.key, col.label, options,
                lambda qs, value, f=parts[0]: qs.filter(**{f + "_id": value})
                if value.isdigit() else qs))
            taken.add(col.key)
    return out


def apply_extras(definition, company, qs, params, tab):
    """
    Apply the tab's own filters; return (qs, [(extra, value)] for later).

    ---

    Aplica los filtros propios de la pestaña que tengan valor; devuelve
    la consulta y los que se deciden después, fila a fila.
    """
    post = []
    for extra in extras_for(definition, company):
        value = params.get(extra_param(tab, extra), "")
        if not value:
            continue
        if extra.post:
            post.append((extra, value))
        elif extra.apply:
            qs = extra.apply(qs, value)
    return qs, post


def materialize(definition, qs, post, limit, state_first=False):
    """
    Rows to paint or export and the real total, own filters applied.

    ---

    Las filas que se pintan o exportan y el total real: con filtros que
    se deciden fila a fila, se cargan todas, se preparan, se filtran y
    se cuenta; sin ellos, el total sale de la BD y solo se carga el
    tramo. `state_first`: vigentes primero (sin orden elegido).
    """
    if post:
        objects = list(qs)
        if definition.prepare and objects:
            definition.prepare(objects)
        objects = [o for o in objects
                   if all(extra.keep(o, value) for extra, value in post)]
        total = len(objects)
    else:
        total = qs.count()
        objects = list(qs[:limit])
        if definition.prepare and objects and state_first:
            definition.prepare(objects)
    if state_first:
        objects.sort(key=lambda o: not getattr(o, "nui_current", True))
    return objects[:limit], total


class ListDef:
    """
    Definition of one list tab (see module docstring).

    ---

    Definición de una pestaña de listado:
    - `queryset(company)`: filas base de la empresa.
    - `entity`: "person", "machine" o None; `entity_path`: campo que
      lleva de la fila a su persona/máquina ("" = la fila lo es);
      `entity_filter(qs, ids)` cuando no hay un campo directo.
    - `entity_of(row)`: la persona/máquina de una fila (para pintar).
    - `search`: campos donde busca "Buscar"; `date_field` (+
      `date_is_datetime`): a qué fecha se aplica el periodo.
    - `columns`, `default_order`, `actions(row)` (menú de tres puntos).
    """

    def __init__(self, label, queryset, columns, entity=None,
                 entity_path="", entity_filter=None, entity_of=None,
                 search=(), date_field="", date_is_datetime=False,
                 default_order=("-pk",), actions=None, note="",
                 scope_filter=None, prepare=None, extras=(),
                 default_cols=None, col_templates=None,
                 period_annotate=None, row_url=None, totals=None,
                 row_title="Parte"):
        self.label = label
        # S163 (23/11): period_annotate(qs, desde, hasta) añade a una
        # lista de trabajadores sus datos del periodo (repostajes,
        # partes...) como columnas que se pueden ordenar.
        self.period_annotate = period_annotate
        # S163 (23/11): row_url(fila) -> lo que se abre en el visor al
        # pulsar la fila (p. ej. el documento del parte).
        self.row_url = row_url
        # Título del visor al abrir una fila (S163, 24/11).
        self.row_title = row_title
        # S163 (23/11): totals(qs) -> {clave de columna: texto}: la fila
        # TOTAL fija abajo, de todo lo filtrado (no solo lo pintado).
        self.totals = totals
        # S163 (23/11): columnas que se ven si el usuario no ha elegido
        # (None: todas) y plantillas de columnas de serie {nombre: claves}.
        self.default_cols = default_cols
        self.col_templates = col_templates or {}
        # Filtros propios declarados (además de los automáticos de
        # extras_for).
        self.extras = list(extras)
        # prepare(rows): completa las filas que se van a pintar o
        # exportar con lo que no sale de una consulta (p. ej. qué
        # documento está vigente de verdad, _mark_current).
        self.prepare = prepare
        self.scope_filter = scope_filter
        self.queryset = queryset
        self.columns = columns
        self.entity = entity
        self.entity_path = entity_path
        self.entity_filter = entity_filter
        self.entity_of = entity_of or (lambda row: row if not entity_path
                                       else None)
        self.search = search
        self.date_field = date_field
        self.date_is_datetime = date_is_datetime
        self.default_order = default_order
        self.actions = actions or (lambda row: [])
        self.note = note


# ------------------------------------------------- personas y máquinas
def _company_filter_choices():
    from new_ui.docs_core import COMPANY_FILTER_CHOICES

    return COMPANY_FILTER_CHOICES


def persons_base():
    from document_explorer.models import PersonIdentity
    from hr_calendar.models import PersonSectionAssignment

    latest = PersonSectionAssignment.objects.filter(
        person=OuterRef("pk")).order_by("-valid_from", "-pk")
    return PersonIdentity.objects.annotate(
        current_section_id=Subquery(latest.values("section_id")[:1]),
        current_section_name=Subquery(latest.values("section__name")[:1]),
    )


def machines_base(company):
    from fleet.models import MachineAsset

    return MachineAsset.objects.filter(company=company)


def filter_options(section, company, editor=None):
    """
    Options of Empresa, Grupo and Familia/Sección for a section.

    ---

    Opciones del bloque común según la sección: en Centros de gasto,
    empresas y familias de las máquinas; en Personal y Documentos, las
    empresas agrupadas de Personal y las secciones (SIME).
    """
    from ivr_config.models import Section
    from new_ui.groups import (
        GROUP_FILTER_NONE, MACHINE_KIND, PERSON_KIND, group_filter_options,
    )

    if section == "cdg":
        machines = machines_base(company)
        companies = [(v, v) for v in sorted(set(
            machines.exclude(company_name="").values_list(
                "company_name", flat=True)))]
        families = [(v, v) for v in sorted(set(
            machines.exclude(family="").values_list("family", flat=True)))]
        kind = MACHINE_KIND
        family_label = "Familia"
    else:
        companies = [(slug, label) for slug, label, _raws
                     in _company_filter_choices()]
        families = [(str(pk), name) for pk, name in Section.objects.filter(
            company=company).order_by("name").values_list("pk", "name")]
        kind = PERSON_KIND
        family_label = "Sección"
    return {
        "companies": companies,
        "families": families,
        "family_label": family_label,
        "groups": group_filter_options(editor, kind),
        "group_none": GROUP_FILTER_NONE,
        "group_kind": kind,
    }


def entity_ids(kind, company, params):
    """
    Queryset of the person/machine pks that pass the common filters.

    ---

    Personas o máquinas que pasan Estado, Empresa, Grupo y
    Familia/Sección; None si ninguno de esos filtros está puesto.
    """
    from new_ui.groups import MACHINE_KIND, PERSON_KIND, filter_by_group

    state = params.get("estado", "1")
    company_value = params.get("empresa", "")
    group = params.get("grupo", "")
    family = params.get("seccion", "")
    if state == "todos" and not (company_value or group or family):
        return None
    if kind == "machine":
        qs = machines_base(company)
        if state == "1":
            qs = qs.filter(is_active=True)
        elif state == "0":
            qs = qs.filter(is_active=False)
        if company_value:
            qs = qs.filter(company_name=company_value)
        if family:
            qs = qs.filter(family=family)
        qs = filter_by_group(qs, group, MACHINE_KIND)
    else:
        qs = persons_base()
        if state == "1":
            qs = qs.filter(is_active_employee=True)
        elif state == "0":
            qs = qs.filter(Q(is_active_employee=False)
                           | Q(is_active_employee__isnull=True))
        if company_value:
            raws = dict((s, r) for s, _l, r in _company_filter_choices()).get(
                company_value)
            qs = qs.filter(employer_company__in=raws or ["__ninguna__"])
        if family.isdigit():
            qs = qs.filter(current_section_id=int(family))
        qs = filter_by_group(qs, group, PERSON_KIND)
    return qs.values("pk")


def _person_actions(person):
    # S163: la ficha de la persona es la pestaña "Ficha" de esta misma
    # vista ("Ver su ficha" en el menú de la fila); nada lleva ya a la
    # ficha antigua de acordeones.
    return []


def _machine_actions(machine):
    # S163: igual que _person_actions, con la ficha del centro de gasto.
    return []


def _doc_actions(entry):
    """
    Row actions of a document (Acciones › Esta fila, right click).

    ---

    Acciones de la fila de un documento: verlo, descargarlo con su
    nombre, ver el historial de su tipo (el propio listado, filtrado),
    subir su versión nueva y, en un PDF de una persona, separarlo
    (S163). Los "#nui-..." los resuelve new_ui.js.
    """
    from urllib.parse import quote

    view = reverse("new_ui:document_file", args=[entry.pk])
    actions = [
        ("Ver documento", "bi-file-earmark-text", view),
        ("Descargar", "bi-download", view + "?descargar=1"),
    ]
    subject = entry.domain_object
    if subject is None:
        return actions
    is_person = getattr(subject, "dni", None) is not None
    label = quote(person_name(subject) if is_person
                  else machine_label(subject), safe="")
    domain = "personal" if is_person else "machine"
    if entry.document_type_id:
        actions.append((
            "Historial de su tipo", "bi-clock-history",
            "#nui-doc-history:%d:%d:%s" % (
                subject.pk, entry.document_type_id, label)))
        actions.append((
            "Actualizar (versión nueva)", "bi-arrow-repeat",
            "#nui-doc-update:%s:%d:%s:%s:%s" % (
                domain, subject.pk, entry.document_type.code,
                quote(entry.document_type.label, safe=""), label)))
    if (is_person and not entry.is_confidential
            and (entry.name or "").lower().endswith(".pdf")):
        actions.append(("Separar páginas", "bi-scissors",
                        "#nui-doc-split:%d" % entry.pk))
    if is_person:
        from new_ui.views_photos import IMAGE_EXTENSIONS, is_photo_source

        action_url = quote(reverse("new_ui:person_photo_action",
                                   args=[subject.pk]), safe="")
        if (entry.name or "").lower().endswith(IMAGE_EXTENSIONS):
            actions.append(("Usar como foto", "bi-person-square",
                            "#nui-post:%s:action=use&entry=%d" % (
                                action_url, entry.pk)))
        if is_photo_source(entry):
            actions.append(("Sacar la foto de aquí", "bi-person-bounding-box",
                            "#nui-post:%s:action=extract&entry=%d" % (
                                action_url, entry.pk)))
    return actions


# S163 (23/11): el usuario de la petición (views._company_user), para las
# listas que dependen de quién mira.
CURRENT_USER = contextvars.ContextVar("nui_current_user", default=None)


# ------------------------------------------------------------ nóminas
def _vacation_rules_def():
    """
    Empresa › Vacaciones › Días de vacaciones: company and group rules.

    ---

    S163 (24/11): las reglas de la empresa y de cada grupo (los días
    propios de cada trabajador se ven en Personal › Vacaciones). Pulsar
    una la abre; una regla no se modifica: se crea otra con su fecha.
    """
    def in_force(company):
        today = datetime.date.today()
        found = {}
        for rule in apps.get_model("hr_calendar.VacationRule").objects \
                .filter(company_id=company, person__isnull=True,
                        section__isnull=True, valid_from__lte=today) \
                .order_by("valid_from").values("pk", "group_id"):
            found[rule["group_id"]] = rule["pk"]
        return set(found.values())

    def prepare(rows):
        live = in_force(rows[0].company_id) if rows else set()
        for row in rows:
            row.nui_in_force = row.pk in live
        return rows

    def carry(r):
        if not r.carry_over:
            return "No pasan"
        if r.carry_over_deadline_day:
            return "Pasan hasta el %s/%s" % (r.carry_over_deadline_day,
                                             r.carry_over_deadline_month)
        return "Pasan"

    return ListDef(
        "Días de vacaciones",
        lambda company: apps.get_model("hr_calendar.VacationRule")
        .objects.filter(company=company, person__isnull=True)
        .select_related("group__parent__parent", "section", "holiday_base"),
        [
            Col("para", "Para", lambda r: "Grupo «%s»" % r.group.path_label()
                if r.group_id else r.target_label(), "group__name"),
            Col("vigente", "Vigente", lambda r: "Sí"
                if getattr(r, "nui_in_force", False) else ""),
            Col("desde", "Desde", lambda r: fmt_date(r.valid_from),
                "valid_from", "text-nowrap"),
            Col("dias", "Días al año", lambda r: fmt_num(
                r.days_per_year, 1), "days_per_year",
                "text-end"),
            Col("tipo", "Tipo de días", lambda r: disp(r, "day_kind"),
                "day_kind"),
            Col("sobrantes", "Sobrantes", carry, "carry_over"),
            Col("festivos", "Festivos", lambda r: r.holiday_base.name
                if r.holiday_base_id else "La de su base",
                "holiday_base__name"),
        ],
        search=("group__name",), default_order=("group__name",
                                                "-valid_from"),
        actions=lambda r: [], prepare=prepare,
        row_url=lambda r: reverse("new_ui:vacation_rule_sheet",
                                  args=[r.pk]),
        row_title="Regla de vacaciones",
        note="Pulsa una regla para verla. Una regla no se modifica: "
             "se crea otra con su fecha («Nueva a partir de esta»). "
             "El periodo no se aplica a este listado.")


def _absence_types_def():
    """
    Empresa › Vacaciones › Tipos de ausencia.

    ---

    S163 (24/11): los tipos de ausencia de la empresa. Pulsar uno lo
    abre para modificarlo; no se borran, se desactivan.
    """
    return ListDef(
        "Tipos de ausencia",
        lambda company: apps.get_model("ivr_config.AbsenceCategory")
        .objects.filter(company=company),
        [
            Col("codigo", "Código", lambda r: r.code, "code"),
            Col("nombre", "Nombre", lambda r: r.label, "label"),
            Col("nota", "Con nota", lambda r: "Sí" if r.requires_note
                else "No", "requires_note"),
            Col("justificada", "Justificada", lambda r: "Sí"
                if r.is_justified else "No", "is_justified"),
            Col("activo", "Activo", lambda r: "Sí" if r.is_active
                else "No", "is_active"),
            Col("orden", "Orden", lambda r: str(r.order), "order",
                "text-end"),
        ],
        search=("code", "label"), default_order=("order", "label"),
        actions=lambda r: [],
        extras=[Extra("activo", "Activo", lambda company: [
            ("si", "Activos"), ("no", "Desactivados")],
            lambda qs, v: qs.filter(is_active=v == "si"))],
        row_url=lambda r: reverse("new_ui:absence_type_sheet",
                                  args=[r.pk]),
        row_title="Tipo de ausencia",
        note="Pulsa un tipo para modificarlo. No se borran: se "
             "desactivan. El periodo no se aplica a este listado.")


def _payslips_def():
    """
    Empresa › Nóminas: the payslips of the deliveries the user can see.

    ---

    Empresa › Nóminas (S163, 23/11; copia del listado de
    panel/views_payslips.py): solo las nóminas de las entregas que ve
    quien mira (las que subió, las compartidas con él o, con acceso a
    todas, todas: hr_calendar/payslip_access). Nunca el contenido de la
    nómina: solo los datos del listado.
    """
    from hr_calendar import payslip_access as access
    from hr_calendar import payslip_delivery as pd
    from hr_calendar.models import PayslipBatch, PayslipItem

    def queryset(company):
        user = CURRENT_USER.get()
        if user is None:
            return PayslipItem.objects.none()
        return PayslipItem.objects.filter(
            batch__in=access.visible_batches(user)).select_related(
            "batch", "person__company_user")

    def pages(r):
        if not r.page_to:
            return ""
        if r.page_from == r.page_to:
            return str(r.page_from)
        return "%s–%s" % (r.page_from, r.page_to)

    def phone(r):
        if not r.phone and r.person is not None:
            return pd.worker_phone(r.person) or ""
        return r.phone

    def batch_options(company):
        user = CURRENT_USER.get()
        if user is None:
            return []
        return [(str(b.pk), "%s · %s" % (
            timezone.localtime(b.created_at).strftime("%d/%m/%Y"),
            b.folder_name or "sin nombre"))
            for b in access.visible_batches(user).order_by("-created_at")]

    return ListDef(
        "Nóminas", queryset, [
            Col("entrega", "Entrega", lambda r: "%s · %s" % (
                timezone.localtime(r.batch.created_at).strftime("%d/%m/%Y"),
                r.batch.folder_name or ""), "batch__created_at"),
            Col("estado_entrega", "Estado de la entrega",
                lambda r: r.batch.get_status_display(), "batch__status"),
            Col("archivo", "Archivo", lambda r: r.original_name,
                "original_name"),
            Col("paginas", "Páginas", pages),
            Col("persona", "Trabajador", lambda r: person_name(r.person)
                if r.person_id else "Sin trabajador",
                "person__first_surname", entity=True),
            Col("dni", "DNI/NIE", lambda r: r.dni_found, "dni_found"),
            Col("mes", "Mes", lambda r: r.period_label, "period_end"),
            Col("movil", "Móvil", phone),
            Col("estado", "Estado", lambda r: r.get_status_display(),
                "status"),
            Col("enviada", "Enviada", lambda r: fmt_datetime(r.sent_at),
                "sent_at", "text-nowrap"),
        ],
        entity="person", entity_path="person",
        entity_of=lambda r: r.person,
        # Las que aún no tienen trabajador se ven siempre.
        entity_filter=lambda qs, ids: qs.filter(
            Q(person__in=ids) | Q(person__isnull=True)),
        search=("original_name", "dni_found", "period_label",
                "batch__folder_name", "person__first_surname",
                "person__given_name", "person__dni"),
        default_order=("-batch__created_at", "original_name", "page_from"),
        actions=lambda r: [],
        extras=[
            Extra("entrega", "Entrega", batch_options,
                  apply=lambda qs, v: qs.filter(batch_id=int(v))
                  if v.isdigit() else qs),
            Extra("estado", "Estado", lambda company: list(
                PayslipItem.Status.choices),
                  apply=lambda qs, v: qs.filter(status=v)),
        ],
        note="Solo las entregas que puedes ver. Elige la entrega en sus "
             "filtros para darle el visto bueno, enviarla o compartirla.")


# ------------------------------------------------------------ horarios
# S163: la empresa del listado de Horarios, para resolver el horario de
# cada trabajador (la fija el propio queryset al pedirse).
_SCHEDULE_COMPANY = contextvars.ContextVar("nui_schedule_company",
                                           default=None)


def _schedule_people(company):
    _SCHEDULE_COMPANY.set(company)
    return persons_base().select_related("company_user__workday_schedule")


def _prepare_schedules(people):
    """
    Attach to each worker their schedule, its origin and clock state.

    ---

    A cada trabajador, el horario que le toca, de dónde le viene y su
    estado de fichaje, todo de golpe (caché por petición).
    """
    from hr_calendar.clock_settings import worker_states
    from new_ui.schedule_core import (
        bulk_schedule_cache, resolve_person_schedule,
    )

    company = _SCHEDULE_COMPANY.get()
    states = worker_states(people)
    origins = {
        "intensive": "Jornada intensiva (verano)",
        "own": "Propio", "user": "De su usuario del panel",
        "section": "De la sección", "default": "Por defecto de la empresa",
        "none": "Sin horario",
    }
    hours = {}
    with bulk_schedule_cache(people, company):
        for person in people:
            schedule, (origin, section) = resolve_person_schedule(
                person, company)
            person.nui_schedule = schedule
            # Las horas de cada horario, una vez (no una por persona).
            key = schedule.pk if schedule else None
            if key not in hours:
                hours[key] = _schedule_summary(schedule)
            person.nui_hours = hours[key]
            person.nui_state = states[person.pk]
            label = origins.get(origin, "")
            if origin == "section" and section is not None:
                label = "De la sección %s" % section.name
            person.nui_origin = label
            person.nui_current = True


def _prepare_fichaje(people):
    """
    Schedules plus the clock-in onboarding report of each worker.

    ---

    S163 (23/11): la lista de Fichaje lleva también el informe de «Alta
    en el fichaje» (new_ui/onboarding_report.py), que antes era una
    vista aparte: a cada trabajador, su fila del informe o None si no se
    le ha enviado el alta.
    """
    from new_ui.onboarding_report import build_rows

    _prepare_schedules(people)
    rows = {}
    for company in {p.company for p in people if p.company_id}:
        rows.update({row["person"].pk: row for row in build_rows(company)})
    for person in people:
        person.nui_alta = rows.get(person.pk)


def _alta(field, kind=""):
    """Value of the onboarding row for a column (blank without alta)."""
    def value(person):
        row = getattr(person, "nui_alta", None)
        if row is None:
            return "Sin alta enviada" if field == "state_label" else ""
        raw = row.get(field)
        if raw is None:
            return ""
        return fmt_datetime(raw) if kind == "dt" else raw
    return value


def _alta_state(person, value):
    """Own filter «Alta en el fichaje» (onboarding situation)."""
    from new_ui.onboarding_report import not_clocking

    row = getattr(person, "nui_alta", None)
    if value == "sin":
        return row is None
    if row is None:
        return False
    if value == "no_fichan":
        return not_clocking(row)
    return row["state"] == value


def _alta_options(company):
    from new_ui.onboarding_report import STATES

    return ([("sin", "Sin alta enviada"),
             ("no_fichan", "Con alta, pero no fichan")]
            + [(key, label) for key, label, _badge in STATES])


ALTA_REPORT_COLS = [
    "nombre", "seccion", "situacion", "alta", "envios", "reenvio",
    "whatsapp", "abierta", "acceso", "ultimo_fichaje", "dias_alta",
    "dias_reenvio", "dias_fichaje",
]
FICHAJE_DEFAULT_COLS = [
    "nombre", "seccion", "horario", "origen", "horas", "ficha", "tipo",
    "avisos",
]


def _schedule_summary(schedule):
    if schedule is None:
        return ""
    from new_ui.views_schedules import days_summary

    return days_summary(schedule)


def _schedule_options(company):
    return [("none", "Sin horario")] + [
        (str(pk), label) for pk, label in apps.get_model(
            "ivr_config.WorkdaySchedule").objects.filter(
            company=company).order_by("label").values_list("pk", "label")]


def _clock_label(state):
    if state.must_clock:
        return "Sí"
    if state.starts_later:
        return "Desde el %s" % state.clocks_from.strftime("%d/%m/%Y")
    if not state.section_clocks:
        return "No (su sección ficha por otro sistema)"
    return "No"


def _clock_mode_label(state):
    if state.clock_mode:
        return dict(apps.get_model("hr_calendar.WorkerClockSetting")
                    .CLOCK_MODE_CHOICES).get(state.clock_mode, "")
    return "Por tipos (su sección)" if state.uses_types else (
        "Normal (su sección)")


# ----------------------------------------------------------------- EPIs
def _epi_sheets(epi):
    """Ids of the technical sheets of an EPI (documents linked to it)."""
    from document_explorer.models import DocumentIndexEntry

    return list(DocumentIndexEntry.objects.filter(
        domain_content_type=ContentType.objects.get_for_model(epi),
        domain_object_id=epi.pk, deleted_at__isnull=True,
        purged_at__isnull=True).values_list("pk", flat=True))


def _epi_delivery_actions(delivery):
    """
    Row actions of an EPI delivery.

    ---

    Acciones de una entrega de EPI: ver su documento de entrega y el
    historial de ese EPI de esa persona (el propio listado, filtrado).
    """
    from urllib.parse import quote

    actions = []
    if delivery.source_entry_id:
        actions.append(("Ver documento de entrega", "bi-file-earmark-text",
                        reverse("new_ui:document_file",
                                args=[delivery.source_entry_id])))
    if delivery.epi_id and delivery.person_id:
        actions.append(("Historial de este EPI", "bi-clock-history",
                        "#nui-epi-history:%d:%d:%s" % (
                            delivery.person_id, delivery.epi_id,
                            quote(person_name(delivery.person), safe=""))))
    return actions


# --------------------------------------------------------- documentos
def _documents(domain_model, family=None, expiring=False):
    def queryset(company):
        from document_explorer.models import DocumentIndexEntry

        ct = ContentType.objects.get_for_model(domain_model())
        qs = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            domain_content_type=ct, deleted_at__isnull=True,
            purged_at__isnull=True,
        ).select_related("document_type").prefetch_related("domain_object")
        if family:
            qs = qs.filter(document_type__family=family)
        if expiring:
            qs = qs.filter(
                is_obsolete=False, expiry_date__isnull=False,
                expiry_date__lte=timezone.localdate()
                + datetime.timedelta(days=30),
            )
        return qs
    return queryset


def _mark_current(entries):
    """
    Mark each document as current or not, exactly like the old ficha.

    ---

    Marca en cada documento (`nui_current`) si está vigente con la misma
    regla que la ficha de siempre (_split_current_obsolete, con el
    requisito de documentación de su persona o máquina): no basta con
    `is_obsolete`, que solo recoge las sustituciones ya escritas en BD.
    Miguel Ángel (S163): "3 contratos laborales, 3 contratos vigentes".
    Se calcula con todos los documentos de cada sujeto de las filas
    pintadas, no solo con los que se ven. En personas, además, los dos
    pasos de su ficha: los laborales de periodos de contratación
    anteriores y, en Laboral, solo el último de cada tipo.
    """
    from document_explorer.models import DocumentIndexEntry, PersonIdentity
    from document_explorer.required_documentation_service import (
        get_required_type_ids,
    )
    from new_ui.docs_core import (
        _keep_latest_laboral_per_type, _move_previous_period_documents,
        _person_employment_periods, _split_current_obsolete,
    )

    subjects = {}
    for entry in entries:
        if entry.document_type_id and entry.domain_object is not None:
            subjects.setdefault(
                (entry.domain_content_type_id, entry.domain_object_id),
                entry.domain_object)
    by_subject = {}
    by_ct = {}
    for ct_id, obj_id in subjects:
        by_ct.setdefault(ct_id, []).append(obj_id)
    for ct_id, ids in by_ct.items():
        siblings = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            domain_content_type_id=ct_id, domain_object_id__in=ids,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__isnull=False,
        ).select_related("document_type")
        for sibling in siblings:
            by_subject.setdefault(
                (ct_id, sibling.domain_object_id), []).append(sibling)
    # Requisitos de todos los sujetos en tres consultas (no dos por cada
    # uno): get_required_type_ids lee el prefetch.
    for ct_id, ids in by_ct.items():
        model = ContentType.objects.get_for_id(ct_id).model_class()
        for subject in model.objects.filter(pk__in=ids).prefetch_related(
                "document_requirements__required_document_types"):
            subjects[(ct_id, subject.pk)] = subject
    current = set()
    for key, subject in subjects.items():
        siblings = by_subject.get(key, [])
        kept, old = _split_current_obsolete(
            siblings, get_required_type_ids(subject))
        if isinstance(subject, PersonIdentity):
            employment = _person_employment_periods(subject, siblings)
            kept, old = _move_previous_period_documents(
                kept, old, employment["periods"])
            kept, old = _keep_latest_laboral_per_type(kept, old)
        current.update(e.pk for e in kept)
    for entry in entries:
        entry.nui_current = (entry.pk in current
                             if entry.document_type_id else
                             not entry.is_obsolete)


def _doc_state(entry):
    current = getattr(entry, "nui_current", not entry.is_obsolete)
    expired = bool(entry.expiry_date
                   and entry.expiry_date < timezone.localdate())
    if entry.is_obsolete or not current:
        # Fuera de vigencia: sustituido por otro más reciente o, si no
        # lo tiene, caducado sin sustituto.
        return "Caducado" if expired and not entry.is_obsolete \
            else "Sustituido"
    if entry.expiry_date:
        days = (entry.expiry_date - timezone.localdate()).days
        if days < 0:
            return "Caducado"
        if days <= 30:
            return "Caduca en %d días" % days
    return "Vigente"


def _family_label(entry, for_person):
    if not entry.document_type_id:
        return "Sin tipo"
    from document_explorer.models import DocumentTypeCatalog

    return DocumentTypeCatalog.family_label(entry.document_type.family,
                                            for_person=for_person)


def _person_model():
    from document_explorer.models import PersonIdentity

    return PersonIdentity


def _machine_model():
    from fleet.models import MachineAsset

    return MachineAsset


def _doc_columns(entity_label, entity_value, for_person):
    return [
        Col("entidad", entity_label, entity_value, entity=True),
        Col("tipo", "Tipo", lambda e: e.document_type.label
            if e.document_type_id else "Sin tipo", "document_type__label"),
        Col("familia", "Familia documental",
            lambda e: _family_label(e, for_person), "document_type__family"),
        Col("emision", "Emisión", lambda e: fmt_date(e.issue_date),
            "issue_date", "text-nowrap"),
        Col("caducidad", "Caducidad", lambda e: fmt_date(e.expiry_date),
            "expiry_date", "text-nowrap"),
        Col("estado", "Estado", _doc_state, "is_obsolete"),
        Col("entrada", "Entrada", lambda e: fmt_datetime(e.indexed_at),
            "indexed_at", "text-nowrap"),
        Col("archivo", "Archivo", lambda e: short(e.name, 60), "name"),
    ]


_DOC_STATES = (
    ("vigentes", "Vigentes"),
    ("por_caducar", "Caducan en 30 días"),
    ("caducados", "Caducados"),
    ("sustituidos", "Sustituidos"),
)


def _doc_state_keep(entry, value):
    state = _doc_state(entry)
    return {
        "vigentes": state == "Vigente" or state.startswith("Caduca en"),
        "por_caducar": state.startswith("Caduca en"),
        "caducados": state == "Caducado",
        "sustituidos": state == "Sustituido",
    }.get(value, True)


def _doc_family_options(for_person):
    from document_explorer.models import DocumentTypeCatalog

    return lambda company: [
        (code, DocumentTypeCatalog.family_label(code, for_person=for_person))
        for code, _label in DocumentTypeCatalog.FAMILY_CHOICES]


def _doc_def(label, domain, family=None, expiring=False):
    for_person = domain == "person"
    model = _person_model if for_person else _machine_model
    return ListDef(
        label, _documents(model, family, expiring),
        _doc_columns(
            "Persona" if for_person else "Código",
            (lambda e: person_name(e.domain_object)) if for_person
            else (lambda e: machine_label(e.domain_object)),
            for_person),
        entity=domain, entity_path="domain_object_id",
        entity_of=lambda e: e.domain_object,
        search=("name", "document_type__label", "ocr_text"),
        date_field="expiry_date" if expiring else "indexed_at",
        date_is_datetime=not expiring,
        default_order=("expiry_date",) if expiring
        else ("is_obsolete", "document_type__label", "-indexed_at"),
        actions=_doc_actions, prepare=_mark_current,
        extras=[
            Extra("estado", "Estado", lambda company: list(_DOC_STATES),
                  keep=_doc_state_keep),
        ] + ([] if family else [
            Extra("familia", "Familia documental",
                  _doc_family_options(for_person),
                  lambda qs, value: qs.filter(document_type__family=value)),
        ]),
        note=("Periodo: fecha de caducidad." if expiring
              else "Periodo: fecha de entrada del documento."),
    )


# -------------------------------------------------- centros de gasto
def _machine_general():
    return ListDef(
        "General", lambda company: machines_base(company),
        [
            Col("codigo", "Código", lambda m: m.code, "code", entity=True),
            Col("familia", "Familia", lambda m: m.family, "family"),
            Col("descripcion", "Marca y modelo", lambda m: m.brand_model,
                "brand_model"),
            Col("tipo", "Tipo", lambda m: m.type_name, "type_name"),
            Col("matricula", "Matrícula", lambda m: m.plate, "plate",
                "text-nowrap"),
            Col("empresa", "Empresa", short_company, "company_name"),
            Col("estado", "Estado",
                lambda m: "Activo" if m.is_active else "Inactivo",
                "is_active"),
            Col("itv", "ITV", lambda m: fmt_date(m.itv_date), "itv_date",
                "text-nowrap"),
            Col("horas", "Horas", lambda m: m.hours or "", "hours",
                "text-end"),
            Col("km", "Km", lambda m: m.mileage or "", "mileage",
                "text-end"),
        ],
        entity="machine",
        search=("code", "brand_model", "plate", "type_name",
                "chassis_number"),
        default_order=("code",), actions=_machine_actions,
        note="El periodo no se aplica a este listado.",
    )


def _dims(m):
    parts = [fmt_num(v / 1000) for v in (m.length_mm, m.width_mm,
                                         m.height_mm) if v]
    return " × ".join(parts)


def _machine_specs():
    def queryset(company):
        return machines_base(company).filter(
            Q(capacity_tonnes__isnull=False) | Q(capacity_tm__isnull=False)
            | Q(max_authorized_mass_kg__isnull=False)
            | Q(mass_kg__isnull=False))
    return ListDef(
        "Especificaciones", queryset,
        [
            Col("codigo", "Código", lambda m: m.code, "code", entity=True),
            Col("descripcion", "Marca y modelo", lambda m: m.brand_model,
                "brand_model"),
            Col("matricula", "Matrícula", lambda m: m.plate, "plate"),
            Col("capacidad", "Capacidad (t)",
                lambda m: fmt_num(m.capacity_tonnes), "capacity_tonnes",
                "text-end"),
            Col("momento", "Momento (t·m)", lambda m: fmt_num(m.capacity_tm),
                "capacity_tm", "text-end"),
            Col("mma", "MMA (t)", lambda m: fmt_num(
                m.max_authorized_mass_kg / 1000)
                if m.max_authorized_mass_kg else "",
                "max_authorized_mass_kg", "text-end"),
            Col("masa", "Masa (kg)", lambda m: m.mass_kg or "", "mass_kg",
                "text-end"),
            Col("ejes", "Ejes", lambda m: m.axle_count or "", "axle_count",
                "text-end"),
            Col("dimensiones", "Largo × ancho × alto (m)", _dims,
                "length_mm", "text-nowrap"),
            Col("anio", "Año", lambda m: m.manufacture_year or "",
                "manufacture_year", "text-end"),
        ],
        entity="machine", search=("code", "brand_model", "plate"),
        default_order=(F("capacity_tonnes").desc(nulls_last=True), "code"),
        actions=_machine_actions,
        note="El periodo no se aplica a este listado.",
    )


def _machine_fk_def(label, model_path, related, entity_path, columns,
                    date_field, date_is_datetime=False, search=(),
                    default_order=("-pk",), note=""):
    def queryset(company):
        from django.apps import apps

        model = apps.get_model(model_path)
        return model.objects.filter(
            **{entity_path + "__company": company}).select_related(*related)

    def entity_of(row):
        obj = row
        for part in entity_path.split("__"):
            obj = getattr(obj, part, None) if obj is not None else None
        return obj

    code = Col("codigo", "Código", lambda r: machine_label(entity_of(r)),
               entity_path + "__code", entity=True)
    return ListDef(
        label, queryset, [code] + columns, entity="machine",
        entity_path=entity_path, entity_of=entity_of,
        search=(entity_path + "__code",) + tuple(search),
        date_field=date_field, date_is_datetime=date_is_datetime,
        default_order=default_order,
        actions=lambda r: _machine_actions(entity_of(r)), note=note,
    )


def _open_assignments():
    from document_explorer.models import LiftingAccessoryAssignment

    return LiftingAccessoryAssignment.objects.filter(end_date__isnull=True)


def _accessories_def():
    """
    Lifting accessories with their current machine (if any).

    ---

    Los accesorios de elevación (como su pestaña de siempre), con la
    máquina de su asignación abierta si la tienen. Los filtros de máquina
    solo quitan los asignados a máquinas que no pasan el filtro (los no
    asignados se ven siempre); con una máquina sola, solo los suyos.
    """
    def queryset(company):
        from document_explorer.models import LiftingAccessory

        current = _open_assignments().filter(
            accessory=OuterRef("pk")).order_by("-start_date", "-pk")
        return LiftingAccessory.objects.filter(company=company).annotate(
            current_machine_id=Subquery(current.values("machine_id")[:1]),
            current_machine_code=Subquery(current.values("machine__code")[:1]),
        ).select_related("accessory_type", "model")

    def entity_filter(qs, ids):
        assigned_ok = _open_assignments().filter(
            machine__in=ids).values("accessory")
        assigned_any = _open_assignments().values("accessory")
        return qs.filter(Q(pk__in=assigned_ok) | ~Q(pk__in=assigned_any))

    def scope_filter(qs, pk):
        return qs.filter(pk__in=_open_assignments().filter(
            machine_id=pk).values("accessory"))

    def entity_of(row):
        if not row.current_machine_id:
            return None
        return SimpleNamespace(pk=row.current_machine_id,
                               code=row.current_machine_code)

    return ListDef(
        "Accesorios", queryset,
        [
            Col("codigo", "Máquina", lambda a: a.current_machine_code or
                "Sin asignar", "current_machine_code", entity=True),
            Col("identificador", "Identificador", lambda a: a.identifier,
                "identifier"),
            Col("tipo", "Tipo", lambda a: a.accessory_type.label
                if a.accessory_type_id else "", "accessory_type__label"),
            Col("descripcion", "Descripción", lambda a: short(
                a.description, 60), "description"),
            Col("carga", "Carga (kg)", lambda a: a.working_load_kg or "",
                "working_load_kg", "text-end"),
            Col("fabricante", "Fabricante", lambda a: a.manufacturer,
                "manufacturer"),
            Col("suministro", "Suministro", lambda a: fmt_date(
                a.supply_date), "supply_date", "text-nowrap"),
            Col("estado", "Estado", lambda a: "Activo" if a.is_active
                else "Baja", "is_active"),
        ],
        entity="machine", entity_filter=entity_filter,
        scope_filter=scope_filter, entity_of=entity_of,
        search=("identifier", "description", "manufacturer",
                "traceability"),
        date_field="supply_date", default_order=("identifier",),
        note="Periodo: fecha de suministro. Los no asignados se ven "
             "siempre.",
    )


def _cdg_lists():
    return {
        "general": _machine_general(),
        "documentos": _doc_def("Documentos", "machine"),
        "especificaciones": _machine_specs(),
        "avisos": _doc_def("Avisos", "machine", expiring=True),
        "revisiones": _machine_fk_def(
            "Revisiones", "fleet.MachineServiceRecord", ("machine",),
            "machine", [
                Col("fecha", "Fecha", lambda r: fmt_date(r.service_date),
                    "service_date", "text-nowrap"),
                Col("horas", "Horas", lambda r: r.hours or "", "hours",
                    "text-end"),
                Col("horas_grua", "Horas de grúa",
                    lambda r: r.crane_hours or "", "crane_hours", "text-end"),
                Col("km", "Km", lambda r: r.km or "", "km", "text-end"),
                Col("proxima", "Próxima (h / km)", lambda r: " / ".join(
                    str(v) for v in (r.next_service_hours, r.next_service_km)
                    if v)),
                Col("motor", "Motor", lambda r: r.engine, "engine"),
                Col("notas", "Notas", lambda r: short(r.notes), "notes"),
            ], "service_date", search=("notes",),
            default_order=("-service_date",),
            note="Periodo: fecha de la revisión."),
        # S163: lecturas de horas y km (antes, en la ficha).
        "lecturas": _machine_fk_def(
            "Lecturas", "fleet.MachineMeterReading", ("machine",),
            "machine", [
                Col("fecha", "Fecha", lambda r: fmt_date(r.reading_date),
                    "reading_date", "text-nowrap"),
                Col("horas", "Horas", lambda r: r.hours or "", "hours",
                    "text-end"),
                Col("horas_grua", "Horas de grúa",
                    lambda r: r.crane_hours or "", "crane_hours", "text-end"),
                Col("km", "Km", lambda r: r.km or "", "km", "text-end"),
                Col("origen", "Origen", lambda r: disp(r, "source")
                    if hasattr(r, "get_source_display") else r.source,
                    "source"),
            ], "reading_date", default_order=("-reading_date",),
            note="Periodo: fecha de la lectura."),
        "repostajes": _machine_fk_def(
            "Repostajes", "fleet.GasoGesSupply", ("vehicle__machine", "user"),
            "vehicle__machine", [
                Col("fecha", "Fecha", lambda r: fmt_datetime(r.supplied_at),
                    "supplied_at", "text-nowrap"),
                Col("vehiculo", "Vehículo (GasoGes)",
                    lambda r: r.vehicle.name or r.vehicle.plate,
                    "vehicle__name"),
                Col("litros", "Litros", lambda r: fmt_num(r.litres),
                    "litres", "text-end"),
                Col("precio", "Precio", lambda r: fmt_num(r.price, 3),
                    "price", "text-end"),
                Col("contador", "Contador", lambda r: r.meter_value or "",
                    "meter_value", "text-end"),
                Col("conductor", "Conductor",
                    lambda r: r.user.name if r.user_id else "",
                    "user__name"),
                Col("estado", "Estado", lambda r: r.status, "status"),
            ], "supplied_at", date_is_datetime=True,
            search=("vehicle__name", "vehicle__plate", "user__name"),
            default_order=("-supplied_at",),
            note="Periodo: fecha del repostaje."),
        "accesorios": _accessories_def(),
        "taller": _machine_fk_def(
            "Taller", "work_order_processor.WorkOrderEntryLine",
            ("machine_asset", "entry"), "machine_asset", [
                Col("fecha", "Fecha", lambda r: fmt_date(r.entry.work_date),
                    "entry__work_date", "text-nowrap"),
                Col("operario", "Operario", lambda r: r.entry.worker_name,
                    "entry__worker_name"),
                Col("tarea", "Tipo de tarea", lambda r: r.tipo_tarea,
                    "tipo_tarea"),
                Col("averia", "Avería", lambda r: short(r.fault_description),
                    "fault_description"),
                Col("reparacion", "Reparación", lambda r: short(
                    r.repair_notes), "repair_notes"),
                Col("horas", "Horas", lambda r: fmt_num(r.delta_hours),
                    "delta_hours", "text-end"),
            ], "entry__work_date",
            search=("fault_description", "repair_notes", "entry__worker_name"),
            default_order=("-entry__work_date",),
            note="Periodo: fecha del parte."),
        "averias": _machine_fk_def(
            "Averías", "chat.BreakdownTicket", ("assigned_to__user",),
            "machine", [
                Col("fecha", "Fecha", lambda r: fmt_datetime(r.created_at),
                    "created_at", "text-nowrap"),
                Col("averia", "Avería", lambda r: short(r.fault_summary, 80),
                    "fault_summary"),
                Col("donde", "Dónde", lambda r: short(
                    r.fault_location or r.location), "fault_location"),
                Col("urgencia", "Urgencia", lambda r: disp(r, "urgency"),
                    "urgency"),
                Col("estado", "Estado", lambda r: disp(r, "status"),
                    "status"),
                Col("asignada", "Asignada a", lambda r: (
                    r.assigned_to.user.get_full_name()
                    or r.assigned_to.user.username)
                    if r.assigned_to_id else "", "assigned_to__user__username"),
                Col("resuelta", "Resuelta", lambda r: fmt_datetime(
                    r.resolved_at), "resolved_at", "text-nowrap"),
            ], "created_at", date_is_datetime=True,
            search=("fault_summary", "fault_location", "location", "notes"),
            default_order=("-created_at",),
            note="Periodo: fecha del aviso de avería."),
        "libro": _machine_fk_def(
            "Libro historial", "fleet.MachineLogbookEntry", ("machine",),
            "machine", [
                Col("fecha", "Fecha", lambda r: fmt_date(r.entry_date),
                    "entry_date", "text-nowrap"),
                Col("seccion", "Apartado", lambda r: r.section, "section"),
                Col("tipo", "Tipo", lambda r: r.entry_type, "entry_type"),
                Col("concepto", "Concepto", lambda r: short(r.concept),
                    "concept"),
                Col("entidad", "Entidad", lambda r: r.entity, "entity"),
                Col("resultado", "Resultado", lambda r: r.result, "result"),
                Col("proxima", "Próxima", lambda r: fmt_date(r.next_date),
                    "next_date", "text-nowrap"),
                Col("firmada", "Firmada", lambda r: fmt_datetime(
                    r.signed_at), "signed_at", "text-nowrap"),
            ], "entry_date", search=("concept", "entity", "result"),
            default_order=("-entry_date",),
            note="Periodo: fecha de la anotación."),
        "equipos": _machine_fk_def(
            "Equipos", "fleet.Crew", ("machine", "person"), "machine", [
                Col("persona", "Persona", lambda r: person_name(r.person),
                    "person__first_surname"),
                Col("desde", "Desde", lambda r: fmt_date(r.date_start),
                    "date_start", "text-nowrap"),
                Col("hasta", "Hasta", lambda r: fmt_date(r.date_end)
                    or "Actual", "date_end", "text-nowrap"),
                Col("notas", "Notas", lambda r: short(r.notes), "notes"),
            ], "date_start",
            search=("person__given_name", "person__first_surname", "notes"),
            default_order=("-date_start",),
            note="Periodo: inicio del equipo."),
    }


# ------------------------------------------------------------ personal
def _person_general():
    return ListDef(
        "General", lambda company: persons_base(),
        [
            Col("nombre", "Nombre", person_name, "first_surname",
                entity=True),
            Col("dni", "DNI/NIE", lambda p: p.dni, "dni", "text-nowrap"),
            Col("empresa", "Empresa", lambda p: p.employer_company,
                "employer_company"),
            Col("categoria", "Categoría", lambda p: p.professional_category,
                "professional_category"),
            Col("seccion", "Sección (SIME)",
                lambda p: p.current_section_name or "",
                "current_section_name"),
            Col("telefono", "Teléfono", lambda p: p.phone, "phone",
                "text-nowrap"),
            Col("alta", "Alta", lambda p: fmt_date(p.hire_date),
                "hire_date", "text-nowrap"),
            Col("estado", "Estado", lambda p: "Activo"
                if p.is_active_employee else "Inactivo",
                "is_active_employee"),
        ],
        entity="person",
        search=("given_name", "first_surname", "second_surname", "dni",
                "phone", "email", "nickname"),
        default_order=("first_surname", "second_surname", "given_name"),
        actions=_person_actions,
        note="Periodo: fecha de alta.", date_field="hire_date",
    )


def _clock_event_actions(event):
    """
    Row actions of a press: its day in Jornadas (to see or correct it).

    ---

    Acciones de un fichaje: abrir la jornada de ese día de esa persona
    en Personal › Jornadas, donde se ve entera y se corrige.
    """
    from urllib.parse import quote

    from django.utils import timezone

    person = getattr(event.company_user, "person_identity", None) if (
        event.company_user_id) else None
    if person is None:
        return []
    day = timezone.localtime(event.pressed_at).date().isoformat()
    return [("Su jornada de ese día (ver y corregir)", "bi-calendar-day",
             "#nui-doc-jornada:%d:%s:%s" % (
                 person.pk, day, quote(person_name(person), safe="")))]


def _request_detail_text(row):
    """«Qué pide» de una solicitud (hr_calendar.worker_requests)."""
    from hr_calendar import worker_requests as wr

    return wr.detail_text(row)


def _request_actions(row):
    """
    Row actions of a worker request: manage it (in Acciones).

    ---

    Acciones de una solicitud: «Gestionar» (su detalle con sus acciones,
    en Acciones) y las de su persona.
    """
    from urllib.parse import quote

    url = reverse("new_ui:request_detail", args=[row.pk])
    return [("Gestionar", "bi-pencil-square",
             "#nui-doc-fragment:" + quote(url, safe=""))] + _person_actions(
        row.person)


def _person_fk_def(label, model_path, related, columns, date_field,
                   date_is_datetime=False, search=(),
                   default_order=("-pk",), entity_path="person", note="",
                   extra_filter=None, actions=None):
    def queryset(company):
        from django.apps import apps

        model = apps.get_model(model_path)
        qs = model.objects.select_related(entity_path, *related)
        return extra_filter(qs, company) if extra_filter else qs

    def entity_of(row):
        obj = row
        for part in entity_path.split("__"):
            obj = getattr(obj, part, None) if obj is not None else None
        return obj

    name = Col("persona", "Persona", lambda r: person_name(entity_of(r)),
               entity_path + "__first_surname", entity=True)
    return ListDef(
        label, queryset, [name] + columns, entity="person",
        entity_path=entity_path, entity_of=entity_of,
        search=(entity_path + "__given_name", entity_path + "__first_surname",
                entity_path + "__dni") + tuple(search),
        date_field=date_field, date_is_datetime=date_is_datetime,
        default_order=default_order,
        actions=actions or (lambda r: _person_actions(entity_of(r))),
        note=note,
    )


def _days(row):
    if row.date_start and row.date_end:
        return (row.date_end - row.date_start).days + 1
    return ""


def _partes_filter(qs, ids):
    from document_explorer.models import PersonIdentity

    return qs.filter(work_order__uploaded_by__in=PersonIdentity.objects.filter(
        pk__in=ids).values("company_user"))


def _partes_def():
    def queryset(company):
        from work_order_processor.models import WorkOrderEntry

        return WorkOrderEntry.objects.filter(
            work_order__company=company,
            work_order__uploaded_by__isnull=False,
        ).select_related("work_order__uploaded_by__person_identity")

    def entity_of(row):
        user = row.work_order.uploaded_by
        return getattr(user, "person_identity", None) if user else None

    return ListDef(
        "Partes", queryset,
        [
            Col("persona", "Persona", lambda r: person_name(entity_of(r))
                or r.worker_name, "worker_name", entity=True),
            Col("fecha", "Fecha", lambda r: fmt_date(r.work_date),
                "work_date", "text-nowrap"),
            Col("origen", "Origen", lambda r: disp(r.work_order, "source"),
                "work_order__source"),
            Col("comida", "Pausa de comida", lambda r: "No hizo"
                if r.no_lunch_break else " – ".join(
                    t.strftime("%H:%M") for t in (r.lunch_break_start,
                                                  r.lunch_break_end) if t)),
            Col("dieta", "Dieta", lambda r: "Sí" if r.has_diet else "",
                "has_diet"),
        ],
        entity="person", entity_filter=_partes_filter, entity_of=entity_of,
        search=("worker_name",), date_field="work_date",
        default_order=("-work_date",),
        actions=lambda r: _person_actions(entity_of(r)),
        row_url=lambda r: reverse("new_ui:parte_sheet",
                                  args=[r.work_order_id]),
        note=("Periodo: fecha del parte. Los partes en PDF antiguos siguen "
              "en la ficha actual del trabajador."),
    )


def _per_lists():
    from document_explorer.models import DocumentTypeCatalog

    return {
        "general": _person_general(),
        "documentos": _doc_def("Documentos", "person"),
        "laboral": _doc_def("Laboral", "person",
                            family=DocumentTypeCatalog.FAMILY_LABORAL),
        "partes": _partes_def(),
        "fichajes": _person_fk_def(
            "Fichajes", "hr_calendar.ClockEvent",
            ("clock_type", "company_user__person_identity"), [
                Col("hora", "Fecha y hora", lambda r: fmt_datetime(
                    r.pressed_at), "pressed_at", "text-nowrap"),
                Col("tipo", "Entrada / salida", lambda r: disp(r, "kind"),
                    "kind"),
                Col("fichaje", "Tipo de fichaje", lambda r: str(r.clock_type)
                    if r.clock_type_id else "", "clock_type__pk"),
                Col("municipio", "Municipio", lambda r: r.municipality,
                    "municipality"),
                Col("nota", "Nota", lambda r: short(r.worker_note),
                    "worker_note"),
            ], "pressed_at", date_is_datetime=True, search=("municipality",),
            default_order=("-pressed_at",),
            extra_filter=lambda qs, company: qs.filter(company=company),
            actions=_clock_event_actions,
            note="Periodo: hora del fichaje."),
        "repostajes": _person_fk_def(
            "Repostajes", "fleet.GasoGesSupply", ("vehicle__machine",), [
                Col("fecha", "Fecha", lambda r: fmt_datetime(r.supplied_at),
                    "supplied_at", "text-nowrap"),
                Col("vehiculo", "Vehículo", lambda r: (
                    r.vehicle.machine.code if r.vehicle.machine_id
                    else (r.vehicle.name or r.vehicle.plate)),
                    "vehicle__name"),
                Col("litros", "Litros", lambda r: fmt_num(r.litres),
                    "litres", "text-end"),
                Col("precio", "Precio", lambda r: fmt_num(r.price, 3),
                    "price", "text-end"),
                Col("contador", "Contador", lambda r: r.meter_value or "",
                    "meter_value", "text-end"),
                Col("estado", "Estado", lambda r: r.status, "status"),
            ], "supplied_at", date_is_datetime=True,
            search=("vehicle__name", "vehicle__plate"),
            default_order=("-supplied_at",), entity_path="user__person",
            extra_filter=lambda qs, company: qs.filter(
                user__person__isnull=False),
            note="Periodo: fecha del repostaje (los que hizo como "
                 "conductor en GasoGes)."),
        "vacaciones": _person_fk_def(
            "Vacaciones", "hr_calendar.VacationPeriod", (), [
                Col("desde", "Desde", lambda r: fmt_date(r.date_start),
                    "date_start", "text-nowrap"),
                Col("hasta", "Hasta", lambda r: fmt_date(r.date_end),
                    "date_end", "text-nowrap"),
                Col("dias", "Días", _days, "", "text-end"),
                Col("registrado", "Registrado", lambda r: fmt_datetime(
                    r.created_at), "created_at", "text-nowrap"),
            ], "date_start", default_order=("-date_start",),
            extra_filter=lambda qs, company: qs.filter(company=company),
            note="Periodo: inicio de las vacaciones."),
        "salud": _person_fk_def(
            "Salud", "hr_calendar.MedicalLeavePeriod", (), [
                Col("desde", "Desde", lambda r: fmt_date(r.date_start),
                    "date_start", "text-nowrap"),
                Col("hasta", "Hasta", lambda r: fmt_date(r.date_end)
                    or "Abierta", "date_end", "text-nowrap"),
                Col("dias", "Días", _days, "", "text-end"),
                Col("contingencia", "Contingencia",
                    lambda r: disp(r, "contingency_type"), "contingency_type"),
            ], "date_start", default_order=("-date_start",),
            note="Periodo: inicio de la baja."),
        "ausencias": _person_fk_def(
            "Ausencias", "hr_calendar.AbsencePeriod", ("category",), [
                Col("motivo", "Ausencia", lambda r: r.category.label
                    if r.category_id else "", "category__label"),
                Col("desde", "Desde", lambda r: fmt_date(r.date_start),
                    "date_start", "text-nowrap"),
                Col("hasta", "Hasta", lambda r: fmt_date(r.date_end),
                    "date_end", "text-nowrap"),
                Col("dias", "Días", _days, "", "text-end"),
                Col("nota", "Nota", lambda r: short(r.note), "note"),
            ], "date_start", search=("note", "category__label"),
            default_order=("-date_start",),
            extra_filter=lambda qs, company: qs.filter(company=company),
            note="Periodo: inicio de la ausencia."),
        "solicitudes": _person_fk_def(
            "Solicitudes", "hr_calendar.WorkerRequest", (), [
                Col("tipo", "Solicitud", lambda r: disp(r, "kind"),
                    "kind"),
                Col("estado", "Estado", lambda r: disp(r, "status"),
                    "status"),
                Col("desde", "Desde", lambda r: fmt_date(r.date_start),
                    "date_start", "text-nowrap"),
                Col("hasta", "Hasta", lambda r: fmt_date(r.date_end),
                    "date_end", "text-nowrap"),
                Col("que_pide", "Qué pide", _request_detail_text),
                Col("nota", "Nota", lambda r: short(r.note), "note"),
                Col("pedida", "Pedida", lambda r: fmt_datetime(r.created_at),
                    "created_at", "text-nowrap"),
                Col("resuelta", "Resuelta", lambda r: fmt_datetime(
                    r.resolved_at), "resolved_at", "text-nowrap"),
            ], "created_at", date_is_datetime=True, search=("note",),
            default_order=("-created_at",),
            extra_filter=lambda qs, company: qs.filter(company=company),
            actions=_request_actions,
            note="Periodo: fecha de la solicitud."),
        # S163: el horario que le toca a cada trabajador y de dónde le
        # viene (como la pestaña Horarios antigua), y cómo ficha.
        "horarios": ListDef(
            "Horarios", _schedule_people,
            [
                Col("nombre", "Persona", person_name, "first_surname",
                    entity=True),
                Col("seccion", "Sección", lambda p: p.nui_state.section_name),
                Col("horario", "Horario", lambda p: p.nui_schedule.label
                    if p.nui_schedule else "Sin horario"),
                Col("origen", "De dónde le viene", lambda p: p.nui_origin),
                Col("horas", "Horas", lambda p: p.nui_hours),
                Col("ficha", "Ficha", lambda p: _clock_label(p.nui_state)),
                Col("tipo", "Tipo de fichaje", lambda p: _clock_mode_label(
                    p.nui_state)),
                Col("avisos", "Recordatorios", lambda p: "Sí"
                    if p.nui_state.reminders else "No"),
                # S163 (23/11): el informe de «Alta en el fichaje».
                Col("dni", "DNI", lambda p: p.dni, "dni"),
                Col("telefono", "Teléfono", _alta("phone")),
                Col("usuario", "Usuario del panel", _alta("username")),
                Col("situacion", "Alta en el fichaje",
                    _alta("state_label")),
                Col("alta", "Alta enviada", _alta("first_sent", "dt")),
                Col("envios", "Envíos", _alta("sends"), "", "text-end"),
                Col("reenvio", "Último reenvío", _alta("last_sent", "dt")),
                Col("whatsapp", "WhatsApp", _alta("whatsapp")),
                Col("abierta", "Abrió la circular", _alta("opened", "dt")),
                Col("acceso", "Último acceso al panel",
                    _alta("last_login", "dt")),
                Col("primer_fichaje", "Primer fichaje",
                    _alta("first_clock", "dt")),
                Col("ultimo_fichaje", "Último fichaje",
                    _alta("last_clock", "dt")),
                Col("dias_alta", "Días sin fichar desde el alta",
                    _alta("days_since_first"), "", "text-end"),
                Col("dias_reenvio", "Días sin fichar desde el reenvío",
                    _alta("days_since_resend"), "", "text-end"),
                Col("dias_fichaje", "Días desde el último fichaje",
                    _alta("days_since_clock"), "", "text-end"),
            ],
            entity="person", search=("given_name", "first_surname", "dni"),
            default_order=("first_surname", "given_name"),
            actions=_person_actions, prepare=_prepare_fichaje,
            default_cols=FICHAJE_DEFAULT_COLS,
            col_templates={
                "Informe de alta en el fichaje": ALTA_REPORT_COLS,
            },
            extras=[
                Extra("alta", "Alta en el fichaje", _alta_options,
                      keep=_alta_state),
                Extra("horario", "Horario", _schedule_options,
                      keep=lambda p, v: (p.nui_schedule is None) if v ==
                      "none" else (p.nui_schedule is not None
                                   and str(p.nui_schedule.pk) == v)),
                Extra("ficha", "Ficha", lambda company: [
                    ("si", "Ficha con la plataforma"), ("no", "No ficha")],
                      keep=lambda p, v: p.nui_state.must_clock == (
                          v == "si")),
            ],
            note="El periodo no se aplica a este listado."),
        # S163: los horarios de la empresa (crear y modificar en Acciones).
        "lista_horarios": ListDef(
            "Lista de horarios",
            lambda company: apps.get_model(
                "ivr_config.WorkdaySchedule").objects.filter(
                company=company).prefetch_related("days"),
            [
                Col("nombre", "Horario", lambda r: r.label, "label"),
                Col("temporada", "Temporada", lambda r: disp(r, "season"),
                    "season"),
                Col("horas", "Horas", _schedule_summary),
                Col("defecto", "Por defecto", lambda r: "Sí"
                    if r.is_default else "", "is_default"),
                Col("tolerancia", "Tolerancia (min)",
                    lambda r: r.tolerance_minutes, "tolerance_minutes",
                    "text-end"),
                Col("trabajadores", "Trabajadores",
                    lambda r: r.worker_settings.count()
                    + r.assigned_users.count(), "", "text-end"),
            ],
            search=("label",), default_order=("label",),
            actions=lambda r: [("Modificar", "bi-pencil-square",
                                "#nui-edit:nui-schedule-form:%d" % r.pk)],
            note="El periodo no se aplica a este listado."),
        "tipos_fichaje": ListDef(
            "Tipos de fichaje",
            lambda company: apps.get_model(
                "hr_calendar.ClockType").objects.filter(company=company),
            [
                Col("nombre", "Tipo", lambda r: r.name, "name"),
                Col("funcion", "Función", lambda r: disp(r, "role"), "role"),
                Col("jornada", "Cuenta como jornada", lambda r: "Sí"
                    if r.counts_as_work else "No", "counts_as_work"),
                Col("activo", "Activo", lambda r: "Sí"
                    if r.is_active else "No", "is_active"),
                Col("defecto", "Por defecto", lambda r: "Sí"
                    if r.is_default else "", "is_default"),
                Col("orden", "Orden", lambda r: r.order, "order",
                    "text-end"),
            ],
            search=("name",), default_order=("order", "name"),
            actions=lambda r: [("Modificar", "bi-pencil-square",
                                "#nui-edit:nui-clocktype-form:%d" % r.pk)],
            note="El periodo no se aplica a este listado."),
        "nominas": _person_fk_def(
            "Nóminas", "hr_calendar.PayslipItem", ("batch",), [
                Col("periodo", "Periodo", lambda r: r.period_label,
                    "period_start"),
                Col("estado", "Estado", lambda r: disp(r, "status"),
                    "status"),
                Col("enviada", "Enviada", lambda r: fmt_datetime(r.sent_at),
                    "sent_at", "text-nowrap"),
                Col("archivo", "Archivo", lambda r: short(r.original_name, 50),
                    "original_name"),
            ], "period_start", default_order=("-period_start",),
            extra_filter=lambda qs, company: qs.filter(
                batch__company=company, person__isnull=False),
            actions=lambda r: (
                [("Ver nómina", "bi-file-earmark-text", reverse(
                    "new_ui:document_file", args=[r.entry_id]))]
                if r.entry_id else []) + _person_actions(r.person),
            note="Periodo: mes de la nómina."),
        "epis": _person_fk_def(
            "EPIs", "document_explorer.EpiDelivery",
            ("epi", "destination_machine"), [
                Col("epi", "EPI", lambda r: r.epi.label if r.epi_id else "",
                    "epi__label"),
                Col("familia", "Familia", lambda r: r.epi.family
                    if r.epi_id else "", "epi__family"),
                Col("fecha", "Entrega", lambda r: fmt_date(r.delivery_date),
                    "delivery_date", "text-nowrap"),
                Col("maquina", "Máquina", lambda r: machine_label(
                    r.destination_machine), "destination_machine__code"),
                # S163 (24/11): de los extintores y botiquines.
                Col("serie", "Nº de serie o matrícula",
                    lambda r: r.serial_number, "serial_number"),
                Col("caducidad", "Caducidad", lambda r: fmt_date(
                    r.expiry_date), "expiry_date", "text-nowrap"),
                Col("revision", "Próxima revisión", lambda r: fmt_date(
                    r.review_date), "review_date", "text-nowrap"),
                Col("retimbrado", "Retimbrado", lambda r: fmt_date(
                    r.retimbrado_date), "retimbrado_date", "text-nowrap"),
                Col("situacion", "Situación", lambda r: (
                    "Retirado el %s" % fmt_date(r.retired_at))
                    if r.retired_at else "", "retired_at"),
            ], "delivery_date", search=("epi__label", "serial_number"),
            default_order=("-delivery_date",),
            actions=_epi_delivery_actions,
            note="Periodo: fecha de entrega."),
        # S163: el catálogo de EPIs (fichas técnicas y lotes en Acciones).
        "catalogo_epis": ListDef(
            "Catálogo de EPIs",
            lambda company: apps.get_model(
                "document_explorer.EpiItemCatalog").objects.filter(
                is_active=True),
            [
                Col("epi", "EPI", lambda r: r.label, "label"),
                Col("familia", "Familia", lambda r: r.family, "family"),
                Col("codigo", "Código", lambda r: r.code, "code"),
                Col("revision", "Revisión periódica", lambda r: "Sí"
                    if r.requires_periodic_review else "",
                    "requires_periodic_review"),
                Col("fichas", "Fichas técnicas",
                    lambda r: len(_epi_sheets(r)), "", "text-end"),
                Col("entregas", "Entregas", lambda r: r.deliveries.count()
                    if hasattr(r, "deliveries") else "", "", "text-end"),
            ],
            search=("label", "code", "family"),
            default_order=("family", "label"),
            actions=lambda r: [
                ("Ficha técnica %d" % (n + 1), "bi-file-earmark-text",
                 reverse("new_ui:document_file", args=[entry_pk]))
                for n, entry_pk in enumerate(_epi_sheets(r))],
            note="El periodo no se aplica a este listado."),
        "requisitos": ListDef(
            "Requisitos",
            lambda company: persons_base().prefetch_related(
                "document_requirements"),
            [
                Col("nombre", "Persona", person_name, "first_surname",
                    entity=True),
                Col("requisitos", "Requisitos de documentación",
                    lambda p: ", ".join(r.name for r in
                                        p.document_requirements.all())
                    or "Sin requisito"),
                Col("categoria", "Categoría", lambda p: p.professional_category,
                    "professional_category"),
            ],
            entity="person", search=("given_name", "first_surname", "dni"),
            default_order=("first_surname", "given_name"),
            actions=_person_actions,
            note="El periodo no se aplica a este listado."),
    }


# ---------------------------------------------------------- documentos
def _doc_lists():
    from django.apps import apps

    def model(path):
        return apps.get_model(path)

    def fk(label, path, related, columns, date_field, date_is_datetime=True,
           search=(), default_order=("-pk",), company_field="", note="",
           actions=None, person=True):
        def queryset(company):
            qs = model(path).objects.select_related(*related)
            if company_field:
                qs = qs.filter(**{company_field: company})
            return qs

        cols = list(columns)
        if person:
            cols.insert(0, Col("persona", "Persona",
                               lambda r: person_name(r.person),
                               "person__first_surname", entity=True))
        return ListDef(
            label, queryset, cols,
            entity="person" if person else None,
            entity_path="person" if person else "",
            entity_of=(lambda r: r.person) if person else (lambda r: None),
            search=search, date_field=date_field,
            date_is_datetime=date_is_datetime, default_order=default_order,
            actions=actions or ((lambda r: _person_actions(r.person))
                                if person else None),
            note=note)

    return {
        "bandeja": fk(
            "Bandeja de entrada", "document_explorer.InboxItem",
            ("person", "document_type", "uploaded_by__user"), [
                Col("archivo", "Archivo", lambda r: short(r.original_name, 60),
                    "original_name"),
                Col("estado", "Estado", lambda r: disp(r, "status"),
                    "status"),
                Col("tipo", "Tipo", lambda r: r.document_type.label
                    if r.document_type_id else "", "document_type__label"),
                Col("motivo", "Motivo", lambda r: short(r.reason), "reason"),
                Col("subido", "Subido por", lambda r: r.uploaded_by.user
                    .get_full_name() if r.uploaded_by_id else "",
                    "uploaded_by__user__first_name"),
                Col("fecha", "Fecha", lambda r: fmt_datetime(r.created_at),
                    "created_at", "text-nowrap"),
            ], "created_at", search=("original_name", "reason"),
            default_order=("-created_at",),
            actions=lambda r: ([("Ver documento", "bi-file-earmark-text",
                                 reverse("new_ui:document_file",
                                         args=[r.entry_id]))]
                               if r.entry_id else [])
            + _person_actions(r.person),
            note="Periodo: fecha de llegada."),
        "circulares": fk(
            "Circulares", "document_explorer.DocumentAcknowledgment",
            ("person", "document_type"), [
                Col("circular", "Circular", lambda r: r.document_type.label
                    if r.document_type_id else "", "document_type__label"),
                Col("entrega", "Entrega", lambda r: fmt_date(r.delivery_date),
                    "delivery_date", "text-nowrap"),
                Col("canal", "Canal", lambda r: r.channel, "channel"),
                Col("whatsapp", "WhatsApp", lambda r: r.whatsapp_status,
                    "whatsapp_status"),
                Col("leida", "Leída", lambda r: fmt_datetime(
                    r.whatsapp_read_at), "whatsapp_read_at", "text-nowrap"),
            ], "delivery_date", date_is_datetime=False,
            search=("document_type__label",),
            default_order=("-delivery_date",),
            note="Periodo: fecha de entrega."),
        # S163: las plantillas de circular (lo que se crea y se edita en
        # Acciones › Circulares), además de las circulares entregadas.
        "plantillas_circular": ListDef(
            "Plantillas de circular",
            lambda company: model("document_explorer.DocumentTypeCatalog")
            .objects.filter(is_active=True, is_notification_template=True),
            [
                Col("nombre", "Circular", lambda r: r.label, "label"),
                Col("codigo", "Código", lambda r: r.code, "code"),
                Col("familia", "Familia", lambda r: model(
                    "document_explorer.DocumentTypeCatalog").family_label(
                    r.family, for_person=True), "family"),
                Col("dirigida", "Dirigida a", lambda r: disp(r, "domain"),
                    "domain"),
                Col("contenido", "Con contenido", lambda r: "Sí"
                    if (r.content_html or "").strip() else "No"),
                Col("firma", "Firma certificada", lambda r: "Sí"
                    if r.requires_signature else "No", "requires_signature"),
            ],
            search=("label", "code"), default_order=("label",),
            actions=lambda r: [
                ("Editar contenido", "bi-pencil-square",
                 reverse("new_ui:circulars_edit", args=[r.pk])),
                ("Generar para una persona", "bi-file-earmark-person",
                 reverse("new_ui:circulars_generate", args=[r.pk])),
                ("Descargar PDF", "bi-filetype-pdf",
                 reverse("new_ui:circulars_export_pdf", args=[r.pk])),
                ("Descargar Word", "bi-filetype-docx",
                 reverse("new_ui:circulars_export_word", args=[r.pk])),
            ],
            note="El periodo no se aplica a este listado."),
        "dosieres": fk(
            "Dosieres", "document_explorer.PersonalDossierTemplate",
            ("created_by__user",), [
                Col("nombre", "Plantilla", lambda r: r.name, "name"),
                Col("ambito", "Ámbito", lambda r: disp(r, "scope"), "scope"),
                Col("tipos", "Tipos de documento",
                    lambda r: r.document_types.count()),
                Col("epis", "EPIs", lambda r: r.epi_items.count() or ""),
                Col("creado", "Creada por", lambda r: r.created_by.user
                    .get_full_name() if r.created_by_id else ""),
                Col("fecha", "Fecha", lambda r: fmt_datetime(r.created_at),
                    "created_at", "text-nowrap"),
            ], "created_at", search=("name",), default_order=("name",),
            company_field="company", person=False,
            # S163 (24/11): pulsar una plantilla la abre en su ventana.
            actions=lambda r: [],
            note="Pulsa una plantilla para ver y marcar lo que lleva. "
                 "Periodo: fecha de creación."),
        # S163: el catálogo de requisitos (de personas y de máquinas).
        "lista_requisitos": ListDef(
            "Requisitos",
            lambda company: model("document_explorer.JobPosition")
            .objects.prefetch_related("required_document_types",
                                      "required_driving_categories"),
            [
                Col("nombre", "Requisito", lambda r: r.name, "name"),
                Col("activo", "Activo", lambda r: "Sí" if r.is_active
                    else "No (no avisa)", "is_active"),
                Col("tipos", "Documentos obligatorios", lambda r: short(
                    ", ".join(t.label for t in
                              r.required_document_types.all()), 120)),
                Col("permiso", "Clases de permiso", lambda r: ", ".join(
                    c.code for c in r.required_driving_categories.all())),
                Col("personas", "Personas", lambda r: r.people.count(),
                    "", "text-end"),
                Col("maquinas", "Máquinas", lambda r: r.machines.count(),
                    "", "text-end"),
                Col("editado", "Editado", lambda r: fmt_datetime(
                    r.updated_at), "updated_at", "text-nowrap"),
            ],
            search=("name",), default_order=("name",),
            actions=lambda r: [],
            extras=[Extra("activo", "Activo", lambda company: [
                ("si", "Activos"), ("no", "Desactivados (no avisan)")],
                lambda qs, v: qs.filter(is_active=v == "si"))],
            # S163 (24/11): pulsar un requisito lo abre para editarlo,
            # como en la antigua.
            row_url=lambda r: reverse("new_ui:requirement_sheet",
                                      args=[r.pk]),
            row_title="Requisito",
            note="Pulsa un requisito para ver y marcar sus documentos "
                 "obligatorios. El periodo no se aplica a este listado."),
        "avisos": fk(
            "Avisos", "document_management.DocumentAlert", (), [
                Col("documento", "Documento", lambda r: r.document_label,
                    "document_label"),
                Col("sujeto", "Persona / máquina", lambda r: r.subject_label,
                    "subject_label"),
                Col("caducidad", "Caducidad", lambda r: fmt_date(
                    r.expiry_date), "expiry_date", "text-nowrap"),
                Col("estado", "Estado", lambda r: disp(r, "status"),
                    "status"),
                Col("enviado", "Avisado", lambda r: fmt_datetime(r.sent_at),
                    "sent_at", "text-nowrap"),
            ], "expiry_date", date_is_datetime=False,
            search=("document_label", "subject_label"),
            default_order=("expiry_date",), company_field="company",
            person=False, note="Periodo: fecha de caducidad."),
        "pedir": fk(
            "Pedir documentos", "document_explorer.WorkerDocumentRequest",
            ("person", "document_type"), [
                Col("documento", "Documento", lambda r: r.document_type.label
                    if r.document_type_id else "", "document_type__label"),
                Col("motivo", "Motivo", lambda r: short(r.reason), "reason"),
                Col("estado", "Estado", lambda r: disp(r, "status"),
                    "status"),
                Col("pedido", "Pedido", lambda r: fmt_datetime(r.created_at),
                    "created_at", "text-nowrap"),
                Col("enviado", "Enviado", lambda r: fmt_datetime(r.sent_at),
                    "sent_at", "text-nowrap"),
                Col("recibido", "Recibido", lambda r: fmt_datetime(
                    r.received_at), "received_at", "text-nowrap"),
            ], "created_at", search=("reason", "document_type__label"),
            default_order=("-created_at",), note="Periodo: fecha de petición."),
        "calendario": fk(
            "Calendario", "hr_calendar.AbsencePeriod",
            ("person", "category"), [
                Col("motivo", "Ausencia", lambda r: r.category.label
                    if r.category_id else "", "category__label"),
                Col("desde", "Desde", lambda r: fmt_date(r.date_start),
                    "date_start", "text-nowrap"),
                Col("hasta", "Hasta", lambda r: fmt_date(r.date_end),
                    "date_end", "text-nowrap"),
                Col("dias", "Días", _days, "", "text-end"),
                Col("nota", "Nota", lambda r: short(r.note), "note"),
            ], "date_start", date_is_datetime=False,
            default_order=("-date_start",), company_field="company",
            note=("Ausencias. Vacaciones y bajas, en Personal › Vacaciones "
                  "y Salud. Periodo: inicio.")),
    }


def _per_person(model_path, person_path, date_lookup, start, end,
                value, extra=None):
    """
    Subquery: one aggregate of a worker's rows of a model in the period.

    ---

    Subconsulta con un dato de las filas de un trabajador en un modelo
    (cuántas, la suma, la última...) dentro del periodo, si lo hay.
    """
    from django.db.models import OuterRef, Subquery

    rows = apps.get_model(model_path).objects.filter(
        **{person_path: OuterRef("pk")})
    if extra:
        rows = rows.filter(**extra)
    if date_lookup and start:
        rows = rows.filter(**{date_lookup + "__gte": start})
    if date_lookup and end:
        rows = rows.filter(**{date_lookup + "__lte": end})
    return Subquery(rows.order_by().values(person_path).annotate(
        v=value).values("v")[:1])


def _count(*args, **kwargs):
    from django.db.models import Count, IntegerField
    from django.db.models.functions import Coalesce

    return Coalesce(_per_person(*args, value=Count("pk"), **kwargs), 0,
                    output_field=IntegerField())


def _annotate_repostajes(qs, start, end):
    from django.db.models import Max, Sum

    path, day = "user__person", "supplied_at__date"
    return qs.annotate(
        nui_rep=_count("fleet.GasoGesSupply", path, day, start, end),
        nui_rep_l=_per_person("fleet.GasoGesSupply", path, day, start, end,
                              Sum("litres")),
        nui_rep_last=_per_person("fleet.GasoGesSupply", path, "", None,
                                 None, Max("supplied_at")))


def _annotate_partes(qs, start, end):
    from django.db.models import Max

    path = "work_order__uploaded_by__person_identity"
    return qs.annotate(
        nui_par=_count("work_order_processor.WorkOrderEntry", path,
                       "work_date", start, end),
        nui_par_last=_per_person("work_order_processor.WorkOrderEntry",
                                 path, "", None, None, Max("work_date")))


def _annotate_epis(qs, start, end):
    from django.db.models import Max

    return qs.annotate(
        nui_epi=_count("document_explorer.EpiDelivery", "person",
                       "delivery_date", start, end),
        nui_epi_all=_count("document_explorer.EpiDelivery", "person", "",
                           None, None),
        nui_epi_last=_per_person("document_explorer.EpiDelivery", "person",
                                 "", None, None, Max("delivery_date")))


def _annotate_bajas(qs, start, end):
    from django.db.models import Exists, Max, Min, OuterRef, Q
    from django.utils import timezone

    today = timezone.localdate()
    leave = apps.get_model("hr_calendar.MedicalLeavePeriod")
    current = leave.objects.filter(
        Q(date_end__isnull=True) | Q(date_end__gte=today),
        person=OuterRef("pk"), date_start__lte=today)
    return qs.annotate(
        nui_baja=Exists(current),
        nui_baja_desde=_per_person(
            "hr_calendar.MedicalLeavePeriod", "person", "", None, None,
            Max("date_start"), extra={"date_start__lte": today}),
        nui_bajas=_count("hr_calendar.MedicalLeavePeriod", "person",
                         "date_start", start, end),
        nui_aus=_count("hr_calendar.AbsencePeriod", "person", "date_start",
                       start, end),
        nui_aus_next=_per_person(
            "hr_calendar.AbsencePeriod", "person", "", None, None,
            Min("date_start"), extra={"date_start__gte": today}))


def _annotate_comunicaciones(qs, start, end):
    from django.db.models import Max

    open_states = ("QUEUED", "SENT")
    return qs.annotate(
        nui_ped=_count("document_explorer.WorkerDocumentRequest", "person",
                       "", None, None, extra={"status__in": open_states}),
        nui_ped_per=_count("document_explorer.WorkerDocumentRequest",
                           "person", "created_at__date", start, end),
        nui_circ=_count("document_explorer.DocumentAcknowledgment",
                        "person", "delivery_date", start, end),
        nui_circ_last=_per_person("document_explorer.DocumentAcknowledgment",
                                  "person", "", None, None,
                                  Max("delivery_date")))


def _yes(value):
    return "Sí" if value else ""


# Tema -> (anotar, [columnas del tema], nota). S163 (23/11).
THEME_COLUMNS = {
    "comunicaciones": (_annotate_comunicaciones, [
        Col("pedidos", "Documentos pedidos sin recibir",
            lambda p: p.nui_ped or "", "nui_ped", "text-end"),
        Col("pedidos_periodo", "Pedidos en el periodo",
            lambda p: p.nui_ped_per or "", "nui_ped_per", "text-end"),
        Col("circulares", "Circulares en el periodo",
            lambda p: p.nui_circ or "", "nui_circ", "text-end"),
        Col("ultima_circular", "Última circular",
            lambda p: fmt_date(p.nui_circ_last), "nui_circ_last"),
    ], "Periodo: pedidos y circulares en esas fechas."),
    "bajas": (_annotate_bajas, [
        Col("de_baja", "De baja ahora", lambda p: _yes(p.nui_baja),
            "nui_baja"),
        Col("baja_desde", "Desde", lambda p: fmt_date(p.nui_baja_desde)
            if p.nui_baja else "", "nui_baja_desde"),
        Col("bajas", "Bajas en el periodo", lambda p: p.nui_bajas or "",
            "nui_bajas", "text-end"),
        Col("ausencias", "Ausencias en el periodo",
            lambda p: p.nui_aus or "", "nui_aus", "text-end"),
        Col("proxima_ausencia", "Próxima ausencia",
            lambda p: fmt_date(p.nui_aus_next), "nui_aus_next"),
    ], "Periodo: bajas y ausencias que empiezan en esas fechas."),
    "partes_trab": (_annotate_partes, [
        Col("partes", "Partes en el periodo", lambda p: p.nui_par or "",
            "nui_par", "text-end"),
        Col("ultimo_parte", "Último parte",
            lambda p: fmt_date(p.nui_par_last), "nui_par_last"),
    ], "Periodo: partes de esas fechas."),
    "repostajes_trab": (_annotate_repostajes, [
        Col("repostajes", "Repostajes en el periodo",
            lambda p: p.nui_rep or "", "nui_rep", "text-end"),
        Col("litros", "Litros en el periodo",
            lambda p: fmt_num(p.nui_rep_l) if p.nui_rep_l else "",
            "nui_rep_l", "text-end"),
        Col("ultimo_repostaje", "Último repostaje",
            lambda p: fmt_datetime(p.nui_rep_last), "nui_rep_last"),
    ], "Periodo: repostajes de esas fechas (como conductor en GasoGes)."),
    "epis_trab": (_annotate_epis, [
        Col("entregas_periodo", "Entregas en el periodo",
            lambda p: p.nui_epi or "", "nui_epi", "text-end"),
        Col("entregas", "Entregas en total",
            lambda p: p.nui_epi_all or "", "nui_epi_all", "text-end"),
        Col("ultima_entrega", "Última entrega",
            lambda p: fmt_date(p.nui_epi_last), "nui_epi_last"),
    ], "Periodo: entregas de esas fechas."),
}


def _annotate_mantenimiento(qs, start, end):
    from django.db.models import Max

    return qs.annotate(
        nui_rev=_count("fleet.MachineServiceRecord", "machine",
                       "service_date", start, end),
        nui_rev_last=_per_person("fleet.MachineServiceRecord", "machine",
                                 "", None, None, Max("service_date")),
        nui_lec_last=_per_person("fleet.MachineMeterReading", "machine",
                                 "", None, None, Max("reading_date")))


def _annotate_taller(qs, start, end):
    from django.db.models import Max

    return qs.annotate(
        nui_par=_count("work_order_processor.WorkOrderEntryLine",
                       "machine_asset", "entry__work_date", start, end),
        nui_ave=_count("chat.BreakdownTicket", "machine",
                       "created_at__date", start, end),
        nui_ave_open=_count("chat.BreakdownTicket", "machine", "", None,
                            None, extra={"status__in": (
                                "OPEN", "IN_PROGRESS", "PAUSED")}),
        nui_lib_last=_per_person("fleet.MachineLogbookEntry", "machine", "",
                                 None, None, Max("entry_date")))


def _annotate_repostajes_maq(qs, start, end):
    from django.db.models import Max, Sum

    path, day = "vehicle__machine", "supplied_at__date"
    return qs.annotate(
        nui_rep=_count("fleet.GasoGesSupply", path, day, start, end),
        nui_rep_l=_per_person("fleet.GasoGesSupply", path, day, start, end,
                              Sum("litres")),
        nui_rep_last=_per_person("fleet.GasoGesSupply", path, "", None,
                                 None, Max("supplied_at")))


def _annotate_seguridad(qs, start, end):
    from django.db.models import Min
    from new_ui.views_safety import safety_q

    rows = apps.get_model("document_explorer.EpiDelivery").objects.filter(
        safety_q(), destination_machine=OuterRef("pk"),
        retired_at__isnull=True)

    def first(field):
        return Subquery(rows.exclude(**{field: None}).order_by().values(
            "destination_machine").annotate(v=Min(field)).values("v")[:1])

    return qs.annotate(
        nui_ext=_count("document_explorer.EpiDelivery",
                       "destination_machine", "", None, None, extra={
                           "epi__label__icontains": "extint",
                           "retired_at__isnull": True}),
        nui_bot=_count("document_explorer.EpiDelivery",
                       "destination_machine", "", None, None, extra={
                           "epi__label__icontains": "botiqu",
                           "retired_at__isnull": True}),
        nui_cad=first("expiry_date"), nui_revi=first("review_date"),
        nui_ret=first("retimbrado_date"))


def _next_safety_date(row, names=("nui_cad", "nui_revi", "nui_ret")):
    """La fecha más cercana de las tres, con aviso si vence en 30 días."""
    from new_ui.views_safety import WARN_DAYS

    dates = [d for d in (getattr(row, n, None) for n in names) if d]
    if not dates:
        return ""
    soonest = min(dates)
    days = (soonest - timezone.localdate()).days
    mark = (" (vencida)" if days < 0 else
            " (en %d días)" % days if days <= WARN_DAYS else "")
    return fmt_date(soonest) + mark


# Centros de gasto: tema -> (anotar, [columnas], nota, de entrada).
MACHINE_THEME_COLUMNS = {
    "documentacion": (None, [], "", ["codigo", "familia", "matricula",
                                     "estado", "itv"]),
    "mantenimiento": (_annotate_mantenimiento, [
        Col("revisiones", "Revisiones en el periodo",
            lambda m: m.nui_rev or "", "nui_rev", "text-end"),
        Col("ultima_revision", "Última revisión",
            lambda m: fmt_date(m.nui_rev_last), "nui_rev_last"),
        Col("ultima_lectura", "Última lectura",
            lambda m: fmt_date(m.nui_lec_last), "nui_lec_last"),
    ], "Periodo: revisiones de esas fechas.",
        ["codigo", "familia", "estado", "horas", "km"]),
    "taller_maq": (_annotate_taller, [
        Col("partes", "Líneas de parte en el periodo",
            lambda m: m.nui_par or "", "nui_par", "text-end"),
        Col("averias", "Averías en el periodo",
            lambda m: m.nui_ave or "", "nui_ave", "text-end"),
        Col("averias_abiertas", "Averías abiertas",
            lambda m: m.nui_ave_open or "", "nui_ave_open", "text-end"),
        Col("ultimo_libro", "Última anotación del libro",
            lambda m: fmt_date(m.nui_lib_last), "nui_lib_last"),
    ], "Periodo: partes y averías de esas fechas.",
        ["codigo", "familia", "estado"]),
    "seguridad": (_annotate_seguridad, [
        Col("extintores", "Extintores", lambda m: m.nui_ext or "",
            "nui_ext", "text-end"),
        Col("botiquines", "Botiquines", lambda m: m.nui_bot or "",
            "nui_bot", "text-end"),
        Col("proxima", "Próxima fecha", _next_safety_date),
    ], "Extintores y botiquines entregados para cada centro de gasto.",
        ["codigo", "familia", "matricula", "estado"]),
    "repostajes_maq": (_annotate_repostajes_maq, [
        Col("repostajes", "Repostajes en el periodo",
            lambda m: m.nui_rep or "", "nui_rep", "text-end"),
        Col("litros", "Litros en el periodo",
            lambda m: fmt_num(m.nui_rep_l) if m.nui_rep_l else "",
            "nui_rep_l", "text-end"),
        Col("ultimo_repostaje", "Último repostaje",
            lambda m: fmt_datetime(m.nui_rep_last), "nui_rep_last"),
    ], "Periodo: repostajes de esas fechas.",
        ["codigo", "familia", "matricula", "estado"]),
}


def _safety_records_def(order=("-delivery_date",)):
    """
    En la ficha de un centro de gasto, Seguridad: sus extintores y
    botiquines (S163, 23/11).
    """
    from new_ui.views_safety import WARN_DAYS, safety_q

    definition = _machine_fk_def(
        "Seguridad", "document_explorer.EpiDelivery", ("epi", "person"),
        "destination_machine", [
            Col("tipo", "Qué", lambda r: r.epi.label, "epi__label"),
            Col("serie", "Nº de serie o matrícula",
                lambda r: r.serial_number, "serial_number"),
            Col("a_quien", "Entregado a", lambda r: person_name(r.person),
                "person__first_surname"),
            Col("entrega", "Entrega", lambda r: fmt_date(r.delivery_date),
                "delivery_date", "text-nowrap"),
            Col("caducidad", "Caducidad", lambda r: fmt_date(r.expiry_date),
                "expiry_date", "text-nowrap"),
            Col("revision", "Próxima revisión",
                lambda r: fmt_date(r.review_date), "review_date",
                "text-nowrap"),
            Col("retimbrado", "Retimbrado",
                lambda r: fmt_date(r.retimbrado_date), "retimbrado_date",
                "text-nowrap"),
            Col("proxima", "Próxima fecha", lambda r: "" if r.retired_at
                else _next_safety_date(
                    r, ("expiry_date", "review_date", "retimbrado_date"))),
            # S163 (24/11): los retirados se quedan, con su fecha y motivo.
            Col("situacion", "Situación", lambda r: (
                "Retirado el %s%s" % (fmt_date(r.retired_at),
                                      ": " + r.retired_note
                                      if r.retired_note else ""))
                if r.retired_at else "En uso", "retired_at"),
            Col("documento", "Documento de entrega", lambda r: "Sí"
                if r.source_entry_id else "", "source_entry"),
        ], "delivery_date", search=("serial_number", "epi__label",
                                    "person__dni", "person__first_surname"),
        default_order=order,
        note="Periodo: fecha de entrega. Los retirados siguen en la lista "
             "(Situación) y no avisan.")
    base = definition.queryset
    definition.queryset = lambda company: base(company).filter(safety_q())
    definition.actions = _epi_delivery_actions

    def soon(qs, value):
        limit = timezone.localdate() + datetime.timedelta(days=WARN_DAYS)
        near = (Q(expiry_date__lte=limit) | Q(review_date__lte=limit)
                | Q(retimbrado_date__lte=limit))
        qs = qs.filter(retired_at__isnull=True)
        return qs.filter(near) if value == "si" else qs.exclude(near)

    definition.extras.append(Extra(
        "vence", "Vence", lambda company: [
            ("si", "En 30 días o ya vencido"), ("no", "Más adelante")],
        apply=soon))
    definition.extras.append(Extra(
        "situacion", "Situación", lambda company: [
            ("uso", "En uso"), ("retirado", "Retirados")],
        apply=lambda qs, v: qs.filter(retired_at__isnull=v == "uso")))
    return definition


def _theme_machine_list(key):
    """
    The machines list of a Centros de gasto theme (S163, 23/11).

    ---

    La lista de centros de gasto de un tema: las columnas de General y
    las del tema.
    """
    annotate, columns, note, first = MACHINE_THEME_COLUMNS[key]
    definition = _machine_general()
    definition.columns = list(definition.columns) + list(columns)
    definition.period_annotate = annotate
    definition.default_cols = first + [c.key for c in columns]
    definition.date_field = ""
    if note:
        definition.note = note
    return definition


def _theme_person_list(key):
    """
    The workers list of a Personal theme: General's columns plus its own.

    ---

    La lista de trabajadores de un tema: las columnas de General y las
    del tema (de entrada: nombre, sección, estado y las del tema).
    """
    annotate, columns, note = THEME_COLUMNS[key]
    definition = _person_general()
    definition.columns = list(definition.columns) + list(columns)
    definition.period_annotate = annotate
    # El periodo es el de sus datos, no la fecha de alta del trabajador.
    definition.date_field = ""
    definition.default_cols = ["nombre", "seccion", "estado"] + [
        c.key for c in columns]
    definition.note = note
    return definition



# --------------------------------------------------------- horas y pagos
def _annotate_pagos(qs, start, end):
    """El periodo del cálculo en cada fila (sin periodo, el periodo de pago en curso)."""
    from django.db.models import DateField, Value

    from new_ui.views_pay import pay_period

    params = {}
    if start:
        params["desde"] = start.isoformat()
    if end:
        params["hasta"] = end.isoformat()
    start, end = pay_period(params)
    return qs.annotate(nui_pay_from=Value(start, DateField()),
                       nui_pay_to=Value(end, DateField()))


def _prepare_pagos(people):
    from new_ui.views_pay import prepare_people

    prepare_people(people)


def _pay(attr, money=False):
    """Valor del cálculo de Horas y pagos para una columna."""
    def value(person):
        result = getattr(person, "nui_pay", None)
        if result is None:
            return ""
        raw = getattr(result, attr)
        if not raw:
            return ""
        text = fmt_num(raw)
        return text + " €" if money else text
    return value


def _pay_source(person):
    result = getattr(person, "nui_pay", None)
    if result is None:
        return "Sin cuenta del panel" if not person.company_user_id else ""
    from hr_calendar.models import PayWorker

    return dict(PayWorker.Source.choices).get(result.source, "")


def _pay_liquidated(person):
    result = getattr(person, "nui_pay", None)
    if result is None or not result.liquidated:
        return ""
    return ", ".join("%s–%s" % (fmt_date(a), fmt_date(b))
                     for a, b, _p in result.liquidated)


def _pay_person_list():
    """
    Personal › Horas y pagos: each worker's paid hours of the period.

    ---

    Personal › Horas y pagos (S163, 23/11): por trabajador, las horas
    que se pagan del periodo (normales y en festivo), lo que va a la
    bolsa por el tope y el importe con sus precios (hr_calendar/pay.py).
    Sin periodo, el periodo de pago en curso (del 21 al 20).
    """
    definition = _person_general()
    definition.columns = list(definition.columns) + [
        Col("origen_horas", "De dónde salen sus horas", _pay_source),
        Col("horas_pagadas", "Horas a pagar", _pay("normal_hours"),
            "", "text-end"),
        Col("horas_festivo", "Horas en festivo", _pay("holiday_hours"),
            "", "text-end"),
        Col("a_la_bolsa", "A la bolsa (tope)", _pay("bag_hours"), "",
            "text-end"),
        Col("importe", "Importe", _pay("total", money=True), "",
            "text-end text-nowrap"),
        Col("liquidado", "Ya liquidado", _pay_liquidated),
    ]
    definition.period_annotate = _annotate_pagos
    definition.prepare = _prepare_pagos
    definition.date_field = ""
    definition.default_cols = ["nombre", "seccion", "origen_horas",
                               "horas_pagadas", "horas_festivo",
                               "a_la_bolsa", "importe", "liquidado"]
    definition.note = ("Periodo: el del filtro; sin periodo, el mes en "
                       "curso hasta hoy. Qué se paga, en Empresa › Horas "
                       "y pagos.")
    return definition


# ------------------------------------------------------------ seguros
def _insurance_supervisors(company):
    from ivr_config.models import CompanyUser

    return [(str(cu.pk), cu.user.get_full_name() or cu.user.username)
            for cu in CompanyUser.objects.filter(
                insurance_access=True).select_related("user")]


def _insurance_def():
    """
    Empresa › Seguros: the insurance renewal reports.

    ---

    Los informes de renovación de seguros (S163, 24/11), con las
    columnas de la antigua; pulsar uno abre su ventana.
    """
    from insurance.models import InsuranceReport
    from new_ui.views_insurance_nui import decorate

    def queryset(company):
        return InsuranceReport.objects.select_related(
            "created_by__user").prefetch_related("ledgers", "exports")

    def prepare(rows):
        for row in rows:
            decorate(row)
        return rows

    return ListDef(
        "Seguros", queryset, [
            Col("numero", "Nº", lambda r: r.pk, "pk", "text-end"),
            Col("titulo", "Informe", lambda r: r.title, "title"),
            Col("fecha", "Fecha del informe", lambda r: fmt_datetime(
                r.created_at), "created_at", "text-nowrap"),
            Col("vencimiento", "Mes de vencimiento",
                lambda r: getattr(r, "due_label", ""), "month_from"),
            Col("supervisor", "Supervisor",
                lambda r: getattr(r, "supervisor_label", ""),
                "created_by__user__first_name"),
            Col("estado", "Estado", lambda r: disp(r, "status")
                + (" (%s %%)" % r.progress_pct if r.is_live
                   and getattr(r, "progress_pct", 0) else ""), "status"),
            Col("seguros", "Seguros", lambda r: r.policy_count,
                "policy_count", "text-end"),
            Col("prima", "Prima anual", lambda r: fmt_num(r.premium_total),
                "premium_total", "text-end"),
            Col("avisos", "Avisos", lambda r: r.alert_count, "alert_count",
                "text-end"),
            Col("libros", "Libros mayores",
                lambda r: getattr(r, "ledgers_label", "")),
            Col("exportado", "Exportado a",
                lambda r: getattr(r, "exported_label", "")),
        ],
        search=("title", "created_by__user__first_name",
                "created_by__user__last_name"),
        date_field="created_at", date_is_datetime=True,
        default_order=("-created_at",), actions=lambda r: [],
        prepare=prepare,
        extras=[Extra("supervisor", "Supervisor", _insurance_supervisors,
                      lambda qs, v: qs.filter(created_by_id=v)
                      if v.isdigit() else qs)],
        row_url=lambda r: reverse("new_ui:insurance_sheet", args=[r.pk]),
        row_title="Informe de seguros",
        note="Periodo: fecha del informe. Pulsa un informe para verlo, "
             "exportarlo, volver a generarlo o borrarlo.")


# ------------------------------------------------------------- firmas
_SIG_STATES = (
    ("pending", "Pendiente de firma"),
    ("done", "Firmado"),
    ("error", "Con error"),
    ("cancelled", "Cancelado"),
)


def _sig_state(r):
    """Situación de un documento firmado, como en la antigua."""
    from document_explorer.models import SignedFormFile, SignedFormJob

    if (r.job.status == SignedFormJob.STATUS_CANCELLED
            and r.status != SignedFormFile.STATUS_DONE):
        return "cancelled", "Cancelado"
    if r.status in (SignedFormFile.STATUS_WAITING,
                    SignedFormFile.STATUS_SIGNING,
                    SignedFormFile.STATUS_PENDING):
        return "pending", r.get_status_display()
    return r.status, r.get_status_display()


def _sig_state_filter(qs, value):
    from django.db.models import Q as _Q

    from document_explorer.models import SignedFormFile, SignedFormJob

    cancelled = _Q(job__status=SignedFormJob.STATUS_CANCELLED) & ~_Q(
        status=SignedFormFile.STATUS_DONE)
    if value == "cancelled":
        return qs.filter(cancelled)
    qs = qs.exclude(cancelled)
    if value == "pending":
        return qs.filter(status__in=(SignedFormFile.STATUS_WAITING,
                                     SignedFormFile.STATUS_SIGNING,
                                     SignedFormFile.STATUS_PENDING))
    return qs.filter(status=value)


def _fiscal_options(company):
    from document_explorer.models import CompanyFiscalProfile

    return [(str(pk), name) for pk, name in
            CompanyFiscalProfile.objects.order_by(
                "legal_name").values_list("pk", "legal_name")]


def _signed_docs_def():
    """
    Empresa › Firmas › Documentos firmados (digitales y normales).

    ---

    Los documentos de clientes firmados por la empresa: cuándo, de qué
    empresa, con qué firma, para qué trabajador, tipo y situación.
    """
    from document_explorer.models import SignedFormFile, SignedFormJob

    def queryset(company):
        return SignedFormFile.objects.select_related(
            "job__signature__company", "job__person").defer(
            "unsigned_encrypted", "signed_encrypted")

    def doc_name(r):
        return r.name + (" · " + short(r.error, 120) if r.error else "")

    def kind(r):
        return r.job.get_kind_display() + (
            " · todas las páginas" if r.job.all_pages else "")

    return ListDef(
        "Documentos firmados", queryset, [
            Col("fecha", "Fecha", lambda r: fmt_datetime(r.job.created_at),
                "job__created_at", "text-nowrap"),
            Col("documento", "Documento", doc_name, "name"),
            Col("empresa", "Empresa",
                lambda r: r.job.signature.company.legal_name,
                "job__signature__company__legal_name"),
            Col("firma", "Firma", lambda r: r.job.signature.label,
                "job__signature__label"),
            Col("trabajador", "Trabajador",
                lambda r: person_name(r.job.person) if r.job.person_id
                else "", "job__person__first_surname"),
            Col("tipo", "Tipo", kind, "job__kind"),
            Col("situacion", "Situación", lambda r: _sig_state(r)[1],
                "status"),
        ],
        search=("name", "job__signature__label",
                "job__signature__company__legal_name",
                "job__person__first_surname", "job__person__given_name"),
        date_field="job__created_at", date_is_datetime=True,
        default_order=("-job__created_at", "pk"), actions=lambda r: [],
        extras=[
            Extra("situacion", "Situación",
                  lambda company: list(_SIG_STATES), _sig_state_filter),
            Extra("tipo", "Tipo",
                  lambda company: list(SignedFormJob.KIND_CHOICES),
                  lambda qs, v: qs.filter(job__kind=v)),
            Extra("empresa", "Empresa", _fiscal_options,
                  lambda qs, v: qs.filter(job__signature__company_id=v)
                  if v.isdigit() else qs),
        ],
        note="Periodo: fecha en que se generó. Marca los firmados y "
             "descárgalos en Acciones.")


# --------------------------------------------------------- correos CAE
_CAE_STATES = (
    ("por_atender", "Por atender"),
    ("atendidos", "Atendidos"),
    ("leyendo", "Leyéndose"),
    ("error", "Error al leer"),
)


def _cae_state(row):
    if row.attended_at:
        return "Atendido"
    if row.status == "ERROR":
        return "Error al leer"
    if row.status == "PENDING":
        return "Leyéndose"
    return "Por atender"


def _cae_state_filter(qs, value):
    if value == "por_atender":
        return qs.filter(attended_at__isnull=True, status="PROCESSED")
    if value == "atendidos":
        return qs.filter(attended_at__isnull=False)
    if value == "leyendo":
        return qs.filter(status="PENDING")
    if value == "error":
        return qs.filter(status="ERROR")
    return qs


def _cae_platforms(company):
    from cae_mail.models import CaeMail

    return [(name, name) for name in CaeMail.objects.exclude(
        platform="").values_list("platform", flat=True).distinct()
        .order_by("platform")]


def _cae_mails_def():
    """
    Empresa › Coordinación › Correos CAE (S156).

    ---

    Los avisos de las plataformas de coordinación (egestiona, Cellnex,
    Nalanda...): cuándo llegaron, de qué plataforma y cliente, a qué
    empresa, cuántos documentos piden y si ya se han atendido. Pulsar
    uno abre en el visor qué pide y qué tenemos.
    """
    from django.db.models import Count

    from cae_mail.models import CaeMail

    def queryset(company):
        return CaeMail.objects.annotate(demand_count=Count("demands"))

    return ListDef(
        "Correos CAE", queryset, [
            Col("recibido", "Recibido", lambda r: fmt_datetime(
                r.received_at or r.forwarded_at), "received_at",
                "text-nowrap"),
            Col("plataforma", "Plataforma", lambda r: r.platform,
                "platform"),
            Col("cliente", "Cliente", lambda r: r.client, "client"),
            Col("empresa", "Empresa", lambda r: r.our_company,
                "our_company"),
            Col("pide", "Pide", lambda r: r.demand_count or "",
                "demand_count", "text-end"),
            Col("resumen", "Resumen", lambda r: short(r.summary, 120),
                "summary"),
            Col("estado", "Estado", _cae_state, "attended_at"),
        ],
        search=("subject", "client", "summary", "our_company",
                "platform"),
        date_field="forwarded_at", date_is_datetime=True,
        default_order=("-received_at", "-forwarded_at", "-pk"),
        actions=lambda r: [],
        extras=[
            Extra("estado", "Estado", lambda company: list(_CAE_STATES),
                  _cae_state_filter),
            Extra("plataforma", "Plataforma", _cae_platforms,
                  lambda qs, v: qs.filter(platform=v) if v else qs),
        ],
        row_url=lambda r: reverse("new_ui:cae_sheet", args=[r.pk]),
        row_title="Correo CAE",
        note="Periodo: fecha en que llegó. Pulsa un aviso para ver qué "
             "pide y qué tenemos; marca varios para atenderlos o "
             "descargar lo que tenemos en Acciones.")


def _signatures_def():
    """
    Empresa › Firmas › Firmas: las firmas guardadas de cada empresa.

    ---

    Pulsar una firma abre su imagen y con qué certificado firma.
    """
    from document_explorer.models import CompanySignature

    def queryset(company):
        return CompanySignature.objects.select_related(
            "company", "created_by__user").defer("image_encrypted")

    def cert(r):
        if r.certificate_cif:
            return "Certificado de " + r.certificate_cif
        if r.certificate_alias:
            return r.certificate_alias
        return "Solo imagen"

    return ListDef(
        "Firmas", queryset, [
            Col("empresa", "Empresa", lambda r: r.company.legal_name,
                "company__legal_name"),
            Col("quien", "Quién firma", lambda r: r.label, "label"),
            Col("certificado", "Certificado digital", cert,
                "certificate_cif"),
            Col("guardada", "Guardada", lambda r: fmt_datetime(
                r.created_at), "created_at", "text-nowrap"),
        ],
        search=("label", "company__legal_name", "certificate_cif"),
        date_field="created_at", date_is_datetime=True,
        default_order=("company__legal_name", "label"),
        actions=lambda r: [],
        extras=[Extra("empresa", "Empresa", _fiscal_options,
                      lambda qs, v: qs.filter(company_id=v)
                      if v.isdigit() else qs)],
        row_url=lambda r: reverse("new_ui:signature_sheet", args=[r.pk]),
        row_title="Firma",
        note="Pulsa una firma para ver su imagen y elegir con qué "
             "certificado digital firma.")


def _agents_def():
    """
    Empresa › Firmas › Agentes: los ordenadores que firman.

    ---

    Los agentes de firma activos: si están conectados, su equipo, el
    último contacto, AutoFirma y cuántos certificados ven.
    """
    from document_explorer import signing_agent_service as agents
    from document_explorer.models import SigningAgent

    def queryset(company):
        return SigningAgent.objects.filter(is_active=True)

    def name(r):
        return r.name + (" · " + short(r.last_error, 120)
                         if r.last_error else "")

    def certs(r):
        return str(len(r.aliases or [])) + (
            "" if r.certificates else " (agente antiguo)")

    return ListDef(
        "Agentes", queryset, [
            Col("conexion", "Conexión", lambda r: "Conectado"
                if agents.is_online(r) else "Desconectado"),
            Col("ordenador", "Ordenador", name, "name"),
            Col("equipo", "Equipo", lambda r: r.host, "host"),
            Col("contacto", "Último contacto", lambda r: fmt_datetime(
                r.last_seen_at) if r.last_seen_at else "nunca",
                "last_seen_at", "text-nowrap"),
            Col("autofirma", "AutoFirma", lambda r: r.autofirma_version
                or "no encontrado", "autofirma_version"),
            Col("certificados", "Certificados", certs),
        ],
        search=("name", "host"), date_field="last_seen_at",
        date_is_datetime=True, default_order=("name",),
        actions=lambda r: [],
        note="Periodo: último contacto.")


def _pay_periods_def():
    """
    Empresa › Horas y pagos › Liquidaciones: the closed periods.

    ---

    Los periodos liquidados (bloqueados): fechas, trabajadores, importe
    y quién lo liquidó.
    """
    from django.db.models import Count, Sum

    from hr_calendar.models import PayPeriod

    def queryset(company):
        return PayPeriod.objects.filter(company=company).annotate(
            nui_workers=Count("lines__company_user", distinct=True),
            nui_amount=Sum("lines__amount")).select_related(
            "closed_by__person_identity", "closed_by__user")

    def closed_by(r):
        cu = r.closed_by
        if cu is None:
            return ""
        person = getattr(cu, "person_identity", None)
        return person_name(person) if person else str(cu)

    return ListDef(
        "Liquidaciones", queryset, [
            Col("desde", "Desde", lambda r: fmt_date(r.date_from),
                "date_from", "text-nowrap"),
            Col("hasta", "Hasta", lambda r: fmt_date(r.date_to), "date_to",
                "text-nowrap"),
            Col("trabajadores", "Trabajadores", lambda r: r.nui_workers,
                "nui_workers", "text-end"),
            Col("importe", "Importe", lambda r: fmt_num(r.nui_amount or 0)
                + " €", "nui_amount", "text-end text-nowrap"),
            Col("por", "Liquidado por", closed_by),
            Col("el", "El", lambda r: fmt_datetime(r.closed_at),
                "closed_at", "text-nowrap"),
        ],
        date_field="date_from", default_order=("-date_from", "-pk"),
        actions=lambda r: [],
        note="Periodo: el inicio de la liquidación. Sus días ya no se "
             "vuelven a calcular; para cambiarlos, deshaz la liquidación.")



def _prepare_pay_partes(rows):
    """
    Festive split and clock-in/out of each parte (ListDef.prepare).

    ---

    De cada parte: si el día es festivo para su trabajador (sábado,
    domingo o festivo de su base: entonces todas sus horas son festivas
    y no hay extra; si no, extra es lo que pasa de 8), y la primera
    entrada y la última salida de su fichaje ese día (redondeadas), como
    en Partes digitales.
    """
    import datetime as _dt
    from decimal import Decimal

    from hr_calendar.clock_report import MAX_SHIFT_HOURS, build_shifts
    from hr_calendar.models import ClockEvent
    from work_order_processor.festive import is_festive, split_hours

    for row in rows:
        day = row.nui_fecha
        if isinstance(day, str):
            day = _dt.date.fromisoformat(day[:10])
            row.nui_fecha = day
        row.nui_festivo = is_festive(day, row.uploaded_by)
        row.nui_extra, row.nui_festivas = split_hours(
            row.nui_horas or Decimal("0"), row.nui_festivo)
        row.nui_in = row.nui_out = None
    dated = [r for r in rows if r.nui_fecha and r.uploaded_by_id]
    if not dated:
        return
    tz = timezone.get_current_timezone()
    margin = _dt.timedelta(hours=MAX_SHIFT_HOURS)
    first = min(r.nui_fecha for r in dated)
    last = max(r.nui_fecha for r in dated)
    start = timezone.make_aware(_dt.datetime.combine(first, _dt.time.min), tz)
    end = timezone.make_aware(_dt.datetime.combine(
        last + _dt.timedelta(days=1), _dt.time.min), tz)
    events = {}
    for event in ClockEvent.objects.current().filter(
            company_user_id__in={r.uploaded_by_id for r in dated},
            pressed_at__gte=start - margin, pressed_at__lt=end + margin,
    ).order_by("company_user_id", "pressed_at", "pk"):
        events.setdefault(event.company_user_id, []).append(event)
    times = {}
    for user_id, user_events in events.items():
        for shift in build_shifts(user_events):
            day_in, day_out = times.get((user_id, shift.day), (None, None))
            if shift.clock_in is not None and (
                    day_in is None
                    or shift.clock_in.pressed_at < day_in.pressed_at):
                day_in = shift.clock_in
            if shift.clock_out is not None and (
                    day_out is None
                    or shift.clock_out.pressed_at > day_out.pressed_at):
                day_out = shift.clock_out
            times[(user_id, shift.day)] = (day_in, day_out)
    for row in dated:
        day_in, day_out = times.get((row.uploaded_by_id, row.nui_fecha),
                                    (None, None))
        row.nui_in = timezone.localtime(
            day_in.rounded_at or day_in.pressed_at) if day_in else None
        row.nui_out = timezone.localtime(
            day_out.rounded_at or day_out.pressed_at) if day_out else None


def _pay_partes_totals(qs):
    """
    TOTAL row of the partes list: hours, extra, festive, blocks, diets.

    ---

    La fila TOTAL de Partes (como en Partes digitales): de todos los
    partes filtrados, horas, extra, festivas (con el festivo de la base
    de cada trabajador), bloques y dietas.
    """
    import datetime as _dt
    from decimal import Decimal

    from work_order_processor.festive import is_festive, split_hours

    hours = extra = festive = Decimal("0")
    blocks = diets = count = 0
    for row in qs:
        count += 1
        day = row.nui_fecha
        if isinstance(day, str):
            day = _dt.date.fromisoformat(day[:10])
        total = row.nui_horas or Decimal("0")
        more, holiday = split_hours(total, is_festive(day, row.uploaded_by))
        hours += total
        extra += more
        festive += holiday
        blocks += row.nui_bloques or 0
        diets += 1 if row.nui_dieta else 0
    return {
        "fecha": "TOTAL (%d parte%s)" % (count, "" if count == 1 else "s"),
        "bloques": str(blocks), "horas": fmt_num(hours),
        "extra": fmt_num(extra), "festivas": fmt_num(festive),
        "dieta": "%d dieta%s" % (diets, "" if diets == 1 else "s"),
    }


def _pay_partes_def():
    """
    Personal › Horas y pagos › Partes: the digital partes to review.

    ---

    Personal › Horas y pagos › Partes (S163, 23/11, Miguel Ángel:
    "Carolina tendrá que utilizar esta parte"): los partes digitales de
    todos, uno por fila, con lo de Partes digitales (fecha, entrada y
    salida del fichaje, bloques, horas, extra, festivas, dieta, revisado
    y origen). Revisar, desmarcar, eliminar y exportar por plantilla, en
    Acciones. Los días de quien no hace partes salen de su fichaje (ya
    visado en Fichaje) en la lista de trabajadores y en su Cálculo.
    """
    from django.db.models import Count, Exists, Min, Sum

    from work_order_processor.models import WorkOrder, WorkOrderEntry

    def queryset(company):
        diet = WorkOrderEntry.objects.filter(work_order=OuterRef("pk"),
                                             has_diet=True)
        return WorkOrder.objects.filter(
            company=company, uploaded_by__isnull=False,
            source__in=[WorkOrder.Source.DIGITAL,
                        WorkOrder.Source.GENERATED],
        ).annotate(
            nui_fecha=Min("entries__work_date"),
            nui_bloques=Count("entries__lines"),
            nui_horas=Sum("entries__lines__delta_hours"),
            nui_dieta=Exists(diet),
        ).select_related("uploaded_by__person_identity", "uploaded_by__user",
                         "uploaded_by__base", "reviewed_by__user")

    def entity_of(row):
        return getattr(row.uploaded_by, "person_identity", None)

    def who(cu):
        if cu is None:
            return ""
        return cu.user.get_full_name() or cu.user.username

    def hhmm(value):
        return value.strftime("%H:%M") if value else ""

    def hours(value):
        return fmt_num(value) if value else ""

    return ListDef(
        "Partes", queryset, [
            Col("persona", "Trabajador", lambda r: person_name(entity_of(r))
                or who(r.uploaded_by), "uploaded_by__person_identity__"
                "first_surname", entity=True),
            Col("fecha", "Fecha", lambda r: fmt_date(r.nui_fecha),
                "nui_fecha", "text-nowrap"),
            Col("entrada", "Entrada (fichaje)", lambda r: hhmm(r.nui_in)),
            Col("salida", "Salida (fichaje)", lambda r: hhmm(r.nui_out)),
            Col("bloques", "Bloques", lambda r: r.nui_bloques or "",
                "nui_bloques", "text-end"),
            Col("horas", "Horas", lambda r: hours(r.nui_horas), "nui_horas",
                "text-end"),
            Col("extra", "Horas extra", lambda r: hours(r.nui_extra), "",
                "text-end"),
            Col("festivas", "Horas festivas", lambda r: hours(
                r.nui_festivas), "", "text-end"),
            Col("dieta", "Dieta", lambda r: "Sí" if r.nui_dieta else "",
                "nui_dieta"),
            Col("revisado", "Revisado", lambda r: "Sí" if r.reviewed
                else "Pendiente", "reviewed"),
            Col("revisado_por", "Revisado por", lambda r: who(r.reviewed_by),
                "reviewed_by__user__first_name"),
            Col("revisado_el", "Revisado el", lambda r: fmt_datetime(
                r.reviewed_at), "reviewed_at", "text-nowrap"),
            Col("origen", "Origen", lambda r: disp(r, "source"), "source"),
        ],
        entity="person", entity_path="uploaded_by__person_identity",
        entity_filter=lambda qs, ids: qs.filter(
            uploaded_by__person_identity__in=ids),
        entity_of=entity_of,
        search=("uploaded_by__person_identity__first_surname",
                "uploaded_by__person_identity__second_surname",
                "uploaded_by__person_identity__given_name"),
        date_field="nui_fecha", default_order=("nui_fecha", "pk"),
        actions=lambda r: [],
        prepare=_prepare_pay_partes,
        row_url=lambda r: reverse("new_ui:parte_sheet", args=[r.pk]),
        totals=_pay_partes_totals,
        default_cols=["persona", "fecha", "entrada", "salida", "bloques",
                      "horas", "extra", "festivas", "dieta", "revisado"],
        extras=[
            Extra("revisado", "Revisión", lambda company: [
                ("no", "Pendientes de revisar"), ("si", "Revisados")],
                apply=lambda qs, v: qs.filter(reviewed=(v == "si"))),
            Extra("dieta", "Dieta", lambda company: [
                ("si", "Con dieta"), ("no", "Sin dieta")],
                apply=lambda qs, v: qs.filter(nui_dieta=(v == "si"))),
            Extra("origen", "Origen", lambda company: [
                (WorkOrder.Source.DIGITAL, "Digital (del operario)"),
                (WorkOrder.Source.GENERATED, "Generado (ausencia)")],
                apply=lambda qs, v: qs.filter(source=v)),
        ],
        note=("Periodo: fecha del parte. Festivo (sábado, domingo o festivo "
              "de su base): todas sus horas son festivas; si no, extra es "
              "lo que pasa de 8. Revisar, eliminar y exportar por plantilla, "
              "en Acciones con los marcados."))


_CACHE = {}


def list_def(section, tab):
    """
    The ListDef of a section's tab, or None.

    ---

    La definición de una pestaña (se construye una vez por proceso).
    """
    if not _CACHE:
        _CACHE["cdg"] = _cdg_lists()
        _CACHE["per"] = _per_lists()
        _CACHE["doc"] = _doc_lists()
        # S163 (23/11): se configuran en Empresa (catalog.MOVED_VIEWS).
        for key in ("lista_horarios", "tipos_fichaje", "catalogo_epis"):
            _CACHE["doc"][key] = _CACHE["per"].pop(key)
        # S163 (24/11): pulsar un horario o un tipo lo abre en su ventana.
        _CACHE["doc"]["lista_horarios"].row_url = lambda r: reverse(
            "new_ui:schedule_sheet", args=[r.pk])
        _CACHE["doc"]["lista_horarios"].row_title = "Horario"
        _CACHE["doc"]["lista_horarios"].actions = lambda r: []
        _CACHE["doc"]["tipos_fichaje"].row_url = lambda r: reverse(
            "new_ui:clock_type_sheet", args=[r.pk])
        _CACHE["doc"]["tipos_fichaje"].row_title = "Tipo de fichaje"
        _CACHE["doc"]["tipos_fichaje"].actions = lambda r: []
        # S163 (23/11): Nóminas, en Empresa, por entregas y con su acceso.
        _CACHE["per"].pop("nominas", None)
        _CACHE["doc"]["nominas"] = _payslips_def()
        # S163 (24/11): Empresa › Vacaciones, dos listados.
        _CACHE["doc"]["vacaciones"] = _vacation_rules_def()
        _CACHE["doc"]["tipos_ausencia"] = _absence_types_def()
        # S163 (23/11): en Fichajes, las correcciones son un filtro (ya
        # no una vista aparte del calendario): corregidos (el original
        # cambiado o anulado) o puestos al corregir.
        from django.db.models import Q as _Q
        _CACHE["per"]["fichajes"].extras.append(Extra(
            "corregidos", "Correcciones",
            lambda company: [("si", "Solo corregidos"),
                             ("no", "Sin corregir")],
            apply=lambda qs, v: (
                qs.filter(_Q(correction__isnull=False)
                          | _Q(replaces__isnull=False))
                if v == "si" else
                qs.filter(correction__isnull=True,
                          replaces__isnull=True))))
        # S163 (23/11): la lista de trabajadores de cada tema de Personal
        # (Comunicaciones, Bajas, Partes, Repostajes, EPIs): las columnas
        # de General más las del tema (THEME_COLUMNS).
        for key in THEME_COLUMNS:
            _CACHE["per"][key] = _theme_person_list(key)
        # S163 (23/11): en la ficha, Comunicaciones: lo que se le ha
        # pedido y las circulares que ha recibido (las mismas listas que
        # tenía Documentos, ya solo de esa persona).
        for key in MACHINE_THEME_COLUMNS:
            _CACHE["cdg"][key] = _theme_machine_list(key)
        _CACHE["cdg"]["seguridad_reg"] = _safety_records_def()
        # Empresa › Documentación › Avisos de seguridad: los de todos los
        # centros de gasto, primero los que antes vencen.
        _CACHE["doc"]["avisos_seguridad"] = _safety_records_def(
            order=("expiry_date", "review_date", "retimbrado_date"))
        # S163 (23/11): pulsar una tarea del taller abre su parte.
        _CACHE["cdg"]["taller"].row_url = lambda r: reverse(
            "new_ui:parte_sheet", args=[r.entry.work_order_id])
        # S163 (23/11): Horas y pagos.
        _CACHE["per"]["pagos_trab"] = _pay_person_list()
        _CACHE["per"]["pagos_partes"] = _pay_partes_def()
        _CACHE["doc"]["liquidaciones"] = _pay_periods_def()
        # S163 (24/11): Firmas, como la pestaña Firmas de la antigua.
        # S163 (24/11): pulsar una circular (plantilla o enviada) la abre.
        _CACHE["doc"]["plantillas_circular"].row_url = lambda r: reverse(
            "new_ui:circulars_sheet", args=[r.pk])
        _CACHE["doc"]["plantillas_circular"].row_title = "Circular"
        _CACHE["doc"]["circulares"].row_url = lambda r: reverse(
            "new_ui:circulars_sent_sheet", args=[r.pk])
        _CACHE["doc"]["circulares"].row_title = "Circular enviada"
        _CACHE["doc"]["dosieres"].row_url = lambda r: reverse(
            "new_ui:dossier_sheet", args=[r.pk])
        _CACHE["doc"]["dosieres"].row_title = "Plantilla de dosier"
        _CACHE["doc"]["seguros"] = _insurance_def()
        _CACHE["doc"]["firmas"] = _signed_docs_def()
        _CACHE["doc"]["firmas_guardadas"] = _signatures_def()
        _CACHE["doc"]["agentes_firma"] = _agents_def()
        # S156: Empresa › Coordinación › Correos CAE.
        _CACHE["doc"]["correos_cae"] = _cae_mails_def()
        _CACHE["per"]["pedidos"] = _CACHE["doc"]["pedir"]
        _CACHE["per"]["circulares_rec"] = _CACHE["doc"]["circulares"]
    return _CACHE.get(section, {}).get(tab)


# --------------------------------------------------------- consulta común
def filtered(definition, company, params, scope_pk=None):
    """
    Queryset of a list with every common filter applied (unsorted).

    ---

    Las filas de un listado con el bloque común aplicado: vista de una
    sola persona/máquina, solo la selección actual, buscar, periodo y
    los filtros de la entidad (estado, empresa, grupo, familia/sección).
    """
    qs = definition.queryset(company)
    path = definition.entity_path or "pk"

    def by_entities(qs, ids):
        if definition.entity_filter:
            return definition.entity_filter(qs, ids)
        return qs.filter(**{path + "__in": ids})

    if scope_pk and definition.entity:
        if definition.scope_filter:
            qs = definition.scope_filter(qs, scope_pk)
        elif definition.entity_filter:
            qs = definition.entity_filter(qs, [scope_pk])
        else:
            qs = qs.filter(**{path: scope_pk})
    selected = [pk for pk in params.get("selected_ids", "").split(",")
                if pk.isdigit()]
    if params.get("only_selected") == "1" and selected:
        return qs.filter(pk__in=selected)
    search = params.get("q", "").strip()
    if search and definition.search:
        query = Q()
        for field in definition.search:
            query |= Q(**{field + "__icontains": search})
        qs = qs.filter(query)
    if definition.date_field:
        start, end = period_range(params)
        suffix = "__date" if definition.date_is_datetime else ""
        if start:
            qs = qs.filter(**{definition.date_field + suffix + "__gte": start})
        if end:
            qs = qs.filter(**{definition.date_field + suffix + "__lte": end})
    if definition.entity and not scope_pk:
        ids = entity_ids(definition.entity, company, params)
        if ids is not None:
            qs = by_entities(qs, ids)
    if definition.period_annotate:
        start, end = period_range(params)
        qs = definition.period_annotate(qs, start, end)
    return qs


def visible_columns(definition, saved_keys):
    keys = [c.key for c in definition.columns]
    if isinstance(saved_keys, list):
        chosen = [k for k in saved_keys if k in keys]
        if chosen:
            entity_cols = [c.key for c in definition.columns if c.entity]
            for key in entity_cols:
                if key not in chosen:
                    chosen.insert(0, key)
            return [c for c in definition.columns if c.key in chosen]
    if definition.default_cols:
        return [c for c in definition.columns
                if c.key in definition.default_cols or c.entity]
    return list(definition.columns)


def sorted_qs(definition, qs, raw_sort):
    """
    Apply the multi-sort of the headers (nulls always last).

    ---

    Orden múltiple por cabecera en la base de datos; sin orden
    elegido, el de la definición.
    """
    valid = {c.key: c.order for c in definition.columns if c.order}
    current = parse_sort(raw_sort, list(valid))
    if not current:
        return qs.order_by(*definition.default_order), current
    order = []
    for key, desc in current:
        expr = F(valid[key])
        order.append(expr.desc(nulls_last=True) if desc
                     else expr.asc(nulls_last=True))
    order.append("-pk")
    return qs.order_by(*order), current


def headers(definition, columns, current):
    """
    Header cells: label, next sort value, arrow, priority.

    ---

    Cabeceras con el "sort" que manda un clic, su flecha y prioridad.
    """
    active = [k for k, _d in current]
    out = []
    for col in columns:
        item = {"key": col.key, "label": col.label, "css": col.css,
                "next": "", "arrow": "", "priority": ""}
        if col.order:
            if col.key in active:
                index = active.index(col.key)
                desc = current[index][1]
                item["arrow"] = "down" if desc else "up"
                item["priority"] = index + 1 if len(current) > 1 else ""
                first = (col.key, (not desc) if index == 0 else desc)
            else:
                first = (col.key, False)
            keys = [first] + [(k, d) for k, d in current if k != col.key]
            item["next"] = ",".join(("-" if d else "") + k
                                    for k, d in keys[:4])
        out.append(item)
    return out


def rows_for(definition, rows, columns):
    """
    Render-ready rows: pk, cells, entity kind/pk/label, actions.

    ---

    Filas listas para pintar (y exportar): celdas, entidad de la fila
    (para el botón derecho y "ver sus listados") y acciones.
    """
    if definition.prepare and rows and not hasattr(rows[0], "nui_current"):
        definition.prepare(rows)
    out = []
    for row in rows:
        # Solo los listados de personas o máquinas llevan a una ficha.
        entity = definition.entity_of(row) if definition.entity else None
        label = ""
        if entity is not None:
            label = (person_name(entity) if definition.entity == "person"
                     else machine_label(entity))
        cells = []
        for col in columns:
            value = col.value(row)
            cells.append({"key": col.key, "value": "" if value is None
                          else value, "css": col.css,
                          "entity": col.entity})
        # S163 (23/11): lo que se nombra en Acciones («Con el DNI de
        # ...»): la persona o máquina si la fila es ella; si no, el primer
        # dato de la fila y de quién es.
        item = label
        if entity is not None and entity is not row:
            first = next((c["value"] for c in cells
                          if not c["entity"] and c["value"] != ""), "")
            item = "%s de %s" % (first, label) if first else label
        out.append({
            "pk": row.pk,
            "cells": cells,
            "entity_kind": definition.entity if entity is not None else "",
            "entity_pk": entity.pk if entity is not None else "",
            "entity_label": label,
            "label": item or (cells[0]["value"] if cells else ""),
            "actions": definition.actions(row),
            "open_title": definition.row_title,
            "open_url": definition.row_url(row) if definition.row_url
            else "",
        })
    return out
