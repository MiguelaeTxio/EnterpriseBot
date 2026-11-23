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
                 scope_filter=None, prepare=None, extras=()):
        self.label = label
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
            ],
            entity="person", search=("given_name", "first_surname", "dni"),
            default_order=("first_surname", "given_name"),
            actions=_person_actions, prepare=_prepare_schedules,
            extras=[
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
            ], "delivery_date", search=("epi__label",),
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
                Col("creado", "Creada por", lambda r: r.created_by.user
                    .get_full_name() if r.created_by_id else ""),
                Col("fecha", "Fecha", lambda r: fmt_datetime(r.created_at),
                    "created_at", "text-nowrap"),
            ], "created_at", search=("name",), default_order=("name",),
            company_field="company", person=False,
            # S163: «Modificar» la carga en el editor de Acciones.
            actions=lambda r: [("Modificar", "bi-pencil-square",
                                "#nui-dossier-edit-%d" % r.pk)],
            note="Periodo: fecha de creación."),
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
            actions=lambda r: [("Modificar", "bi-pencil-square",
                                "#nui-edit:nui-requirement-form:%d" % r.pk)],
            note="El periodo no se aplica a este listado."),
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
        "firmas": fk(
            "Firmas", "document_explorer.SignedFormJob",
            ("person", "signature"), [
                Col("tipo", "Tipo", lambda r: disp(r, "kind"), "kind"),
                Col("firma", "Firma de empresa", lambda r: r.signature.label
                    if r.signature_id else "", "signature__label"),
                Col("estado", "Estado", lambda r: disp(r, "status"),
                    "status"),
                Col("creada", "Pedida", lambda r: fmt_datetime(r.created_at),
                    "created_at", "text-nowrap"),
                Col("terminada", "Terminada", lambda r: fmt_datetime(
                    r.finished_at), "finished_at", "text-nowrap"),
            ], "created_at", default_order=("-created_at",),
            note="Periodo: fecha de la firma."),
        "seguros": fk(
            "Seguros", "insurance.InsuranceReport", ("created_by__user",), [
                Col("titulo", "Informe", lambda r: r.title, "title"),
                Col("desde", "Desde", lambda r: fmt_date(r.month_from),
                    "month_from", "text-nowrap"),
                Col("hasta", "Hasta", lambda r: fmt_date(r.month_to),
                    "month_to", "text-nowrap"),
                Col("estado", "Estado", lambda r: disp(r, "status"),
                    "status"),
                Col("polizas", "Pólizas", lambda r: r.policy_count,
                    "policy_count", "text-end"),
                Col("prima", "Prima total", lambda r: fmt_num(
                    r.premium_total), "premium_total", "text-end"),
                Col("alertas", "Avisos", lambda r: r.alert_count,
                    "alert_count", "text-end"),
                Col("creado", "Creado", lambda r: fmt_datetime(r.created_at),
                    "created_at", "text-nowrap"),
            ], "created_at", search=("title",), default_order=("-created_at",),
            person=False, note="Periodo: fecha del informe."),
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
        for key in ("lista_horarios", "tipos_fichaje", "catalogo_epis",
                    "nominas"):
            _CACHE["doc"][key] = _CACHE["per"].pop(key)
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
        # (Comunicaciones, Bajas, Partes, Repostajes, EPIs), de momento
        # con las columnas de General; las propias de cada tema, después.
        for key in ("comunicaciones", "bajas", "partes_trab",
                    "repostajes_trab", "epis_trab"):
            _CACHE["per"][key] = _person_general()
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
        })
    return out
