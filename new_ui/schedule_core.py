# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/schedule_core.py
"""
Which workday schedule applies to a worker, and where it comes from.

---

S163: copia de panel/views_operator.py (resolve_person_schedule,
bulk_schedule_cache y sus ayudantes) para la nueva interfaz: el horario
que le toca a cada trabajador y de dónde le viene (propio, de su
usuario, de la sección, por defecto de la empresa, jornada intensiva),
con la misma caché por petición para muchas personas a la vez.
"""
import contextlib
import contextvars

from django.db.models import Case, When

# S141: de dónde sale el horario de un trabajador (pestaña Horarios).
ORIGIN_INTENSIVE = "intensive"
ORIGIN_OWN = "own"
ORIGIN_USER = "user"
ORIGIN_SECTION = "section"
ORIGIN_DEFAULT = "default"
ORIGIN_NONE = "none"


# ------------------------------------------------------------------
# S153: caché por petición para resolver el horario de muchas personas
# a la vez (Personal, Horarios). Incidente real: Personal tardaba 14-25 s
# (logs/slow_requests.log del 18/11: ~260 consultas de WorkerClockSetting,
# ~210 de PersonSectionAssignment, ~170 de PersonIdentity por usuario,
# ~220 de WorkdaySchedule, una o varias por persona). bulk_schedule_cache()
# las trae todas de golpe y los helpers de abajo leen de ella mientras
# está activa; fuera de ella todo funciona igual que antes.
# ------------------------------------------------------------------

_SCHEDULE_CACHE = contextvars.ContextVar("schedule_cache", default=None)


@contextlib.contextmanager
def bulk_schedule_cache(people, company):
    """
    Preloads in bulk what resolve_person_schedule needs for `people`.
    ---
    Precarga en pocas consultas todo lo que resolve_person_schedule
    necesita para estas personas: horario propio, sección vigente,
    ficha de cada usuario, sección con horario de su contacto de la
    centralita y los horarios por defecto e intensivo de la empresa.
    """
    from django.db.models import Prefetch

    from document_explorer.models import PersonIdentity
    from hr_calendar.clock_settings import current_sections
    from hr_calendar.models import WorkerClockSetting
    from ivr_config.models import Contact as _Contact_C
    from ivr_config.models import Section as _Section_C
    from ivr_config.models import WorkdaySchedule as _WDS_C

    people = list(people)
    user_ids = [p.company_user_id for p in people if p.company_user_id]
    persons_of_users = {
        p.company_user_id: p for p in PersonIdentity.objects.filter(
            company_user_id__in=user_ids)
    }
    person_ids = {p.pk for p in people} | {
        p.pk for p in persons_of_users.values()}
    own = {pk: None for pk in person_ids}
    for setting in WorkerClockSetting.objects.filter(
            person_id__in=person_ids).select_related("workday_schedule"):
        own[setting.person_id] = setting.workday_schedule
    contact_section = {uid: (None, None) for uid in user_ids}
    sections_qs = _Section_C.objects.filter(
        is_active=True, workday_schedule__isnull=False,
    ).select_related("workday_schedule").order_by("name")
    for contact in _Contact_C.objects.filter(
            company_user_id__in=user_ids).order_by(
            "company__name", "name").prefetch_related(
            Prefetch("sections", queryset=sections_qs,
                     to_attr="schedule_sections")):
        if contact_section.get(contact.company_user_id, (None,))[0]:
            continue
        if contact.schedule_sections:
            sec = contact.schedule_sections[0]
            contact_section[contact.company_user_id] = (
                sec.workday_schedule, sec)
    intensive = _WDS_C.objects.filter(
        company=company, is_intensive=True, varies_by_day=False,
    ).exclude(season=_WDS_C.Season.WINTER).order_by(
        Case(When(season=_WDS_C.Season.SUMMER, then=0), default=1),
        "label",
    ).first()
    cache = {
        "person_of_user": persons_of_users,
        "own": own,
        "section": current_sections(person_ids),
        "contact_section": contact_section,
        "default": _WDS_C.objects.filter(
            company=company, is_default=True).first(),
        "intensive": intensive,
        "company_id": company.pk if company else None,
    }
    token = _SCHEDULE_CACHE.set(cache)
    try:
        yield cache
    finally:
        _SCHEDULE_CACHE.reset(token)


def _cache_for(company=None):
    cache = _SCHEDULE_CACHE.get()
    if cache is None:
        return None
    if company is not None and cache["company_id"] != company.pk:
        return None
    return cache


def _person_of_user(cu):
    """
    The PersonIdentity of a CompanyUser, or None.
    ---
    La ficha de Personal de un usuario del panel, o None.
    """
    from django.core.exceptions import ObjectDoesNotExist

    cache = _cache_for()
    if cache is not None and cu is not None:
        if cu.pk in cache["person_of_user"]:
            return cache["person_of_user"][cu.pk]
    try:
        return cu.person_identity
    except (ObjectDoesNotExist, AttributeError):
        return None


def _person_schedule(person):
    """
    The worker's own WorkdaySchedule (S141), or None.
    ---
    El horario propio del trabajador (S141, pestaña Horarios), o None.
    """
    from hr_calendar.models import WorkerClockSetting

    if person is None:
        return None
    cache = _cache_for()
    if cache is not None and person.pk in cache["own"]:
        return cache["own"][person.pk]
    setting = WorkerClockSetting.objects.filter(
        person=person,
    ).select_related("workday_schedule").first()
    return setting.workday_schedule if setting else None


def _person_section(person):
    """
    The worker's Personal section in force today, or None.
    ---
    La sección de Personal vigente hoy del trabajador, o None.
    """
    from hr_calendar.clock_settings import current_sections

    if person is None:
        return None
    cache = _cache_for()
    if cache is not None and person.pk in cache["section"]:
        return cache["section"][person.pk]
    return current_sections([person.pk]).get(person.pk)


def resolve_person_schedule(person, company):
    """
    (schedule, (origin, section)) of a worker, with or without a panel user.
    ---
    El horario de un trabajador y de dónde le viene (S141), tenga o no
    usuario del panel: con usuario, el de _resolve_base_schedule_with_origin;
    sin él, el suyo propio, el de su sección de Personal o el de por
    defecto de la empresa.
    """
    from ivr_config.models import WorkdaySchedule as _WDS_P

    if person.company_user_id:
        return _resolve_base_schedule_with_origin(
            person.company_user, company,
        )
    own = _person_schedule(person)
    if own is not None:
        return own, (ORIGIN_OWN, None)
    section = _person_section(person)
    if section is not None and section.workday_schedule_id:
        return section.workday_schedule, (ORIGIN_SECTION, section)
    cache = _cache_for(company)
    if cache is not None:
        default = cache["default"]
    else:
        default = _WDS_P.objects.filter(
            company=company, is_default=True).first()
    return default, ((ORIGIN_DEFAULT if default else ORIGIN_NONE), None)


def _resolve_base_schedule_with_origin(cu, company):
    """
    Resolves the effective WorkdaySchedule for a CompanyUser following
    the Gate 4 priority chain:
      0. If cu.is_intensive_override=True, returns the company's intensive
         WorkdaySchedule (is_intensive=True) when one exists. Falls through
         to the normal chain if no intensive schedule is configured.
      1. S141: the worker's own schedule (WorkerClockSetting of their
         PersonIdentity), then CompanyUser.workday_schedule.
      2. First active Section of the operator's Contact that has a
         workday_schedule assigned; S141: then the schedule of their
         Personal section in force today.
      3. Company-level default WorkdaySchedule (is_default=True).
      4. None — no schedule available.
    Returns (WorkdaySchedule or None, (origin, Section or None)); S141:
    the origin says which gate gave it (pestaña Horarios).
    ---
    Resuelve el WorkdaySchedule efectivo para un CompanyUser siguiendo
    la cadena de prioridad de Gate 4:
      0. Si cu.is_intensive_override=True, devuelve el WorkdaySchedule
         intensivo de la empresa (is_intensive=True) si existe. Si no
         existe horario intensivo configurado, continua con la cadena normal.
      1. CompanyUser.workday_schedule (asignacion individual).
      2. Primera Section activa del Contact del operario que tenga
         workday_schedule asignado.
      3. WorkdaySchedule por defecto de empresa (is_default=True).
      4. None — no hay horario disponible.
    Devuelve la instancia WorkdaySchedule resuelta o None.
    """
    from ivr_config.models import WorkdaySchedule as _WDS_R
    from ivr_config.models import Contact as _Contact_R

    # S141: horario propio del trabajador (su ficha de Personal, pestaña
    # Horarios). Manda sobre todo lo demás, salvo que el trabajador haya
    # marcado la jornada intensiva (verano) y su horario sea de invierno:
    # entonces le toca el intensivo. Un horario de "todo el año" no cambia
    # con la jornada intensiva.
    _own = _person_schedule(_person_of_user(cu))
    _override = getattr(cu, "is_intensive_override", False)
    if _own is not None and not (
            _override and _own.season == _WDS_R.Season.WINTER):
        return _own, (ORIGIN_OWN, None)

    if _override:
        # S141 (incidente real): antes valía el primer horario con
        # is_intensive por orden alfabético, y un horario personal "según
        # el día" cuyo lunes es de un solo tramo (is_intensive=True) se
        # colaba como "la jornada intensiva" de todos los que la tienen
        # marcada. Ahora solo un horario intensivo de verdad: igual toda
        # la semana y de verano (si no hay, uno de "todo el año").
        _cache = _cache_for(company)
        if _cache is not None:
            _intensive = _cache["intensive"]
        else:
            _intensive = _WDS_R.objects.filter(
                company=company, is_intensive=True, varies_by_day=False,
            ).exclude(season=_WDS_R.Season.WINTER).order_by(
                Case(When(season=_WDS_R.Season.SUMMER, then=0), default=1),
                "label",
            ).first()
        if _intensive is not None:
            return _intensive, (ORIGIN_INTENSIVE, None)

    if _own is not None:
        return _own, (ORIGIN_OWN, None)

    # Gate 1 — individual schedule assignment.
    # Only apply if the assigned schedule is coherent with
    # is_intensive_override:
    #   - override=True  + intensive schedule  -> Gate 0 already
    #     returned; reaching here means no intensive schedule
    #     exists, so Gate 1 applies normally.
    #   - override=False + intensive schedule  -> incoherent;
    #     skip Gate 1 and fall through to Gate 2/3.
    #   - override=False + non-intensive schedule -> coherent;
    #     Gate 1 applies normally.
    # ---
    # Gate 1 — asignacion individual de horario.
    # Solo aplica si el horario asignado es coherente con
    # is_intensive_override:
    #   - override=True  + horario intensivo  -> Gate 0 ya retorno;
    #     llegar aqui significa que no existe horario intensivo,
    #     Gate 1 aplica normalmente.
    #   - override=False + horario intensivo  -> incoherente;
    #     se ignora Gate 1 y se continua a Gate 2/3.
    #   - override=False + horario no intensivo -> coherente;
    #     Gate 1 aplica normalmente.
    if cu.workday_schedule_id:
        _cu_sched = cu.workday_schedule
        _override_active = getattr(cu, "is_intensive_override", False)
        _sched_is_intensive = getattr(_cu_sched, "is_intensive", False)
        _gate1_coherent = not (not _override_active and _sched_is_intensive)
        if _gate1_coherent:
            return _cu_sched, (ORIGIN_USER, None)

    _cache = _cache_for(company)
    if _cache is not None and cu.pk in _cache["contact_section"]:
        section_schedule, _section_of = _cache["contact_section"][cu.pk]
        if section_schedule is not None:
            return section_schedule, (ORIGIN_SECTION, _section_of)
        contact = None
    else:
        contact = (
            _Contact_R.objects.filter(company_user=cu)
            .prefetch_related("sections__workday_schedule")
            .first()
        )
    if contact is not None:
        section_schedule = next(
            (
                (sec.workday_schedule, sec)
                for sec in contact.sections.filter(
                    is_active=True, workday_schedule__isnull=False
                )
                .select_related("workday_schedule")
                .order_by("name")
            ),
            (None, None),
        )
        section_schedule, _section_of = section_schedule
        if section_schedule is not None:
            return section_schedule, (ORIGIN_SECTION, _section_of)

    # S141: el de su sección de Personal (la vigente hoy).
    _section = _person_section(_person_of_user(cu))
    if _section is not None and _section.workday_schedule_id:
        return _section.workday_schedule, (ORIGIN_SECTION, _section)

    _cache = _cache_for(company)
    if _cache is not None:
        default = _cache["default"]
    else:
        default = _WDS_R.objects.filter(
            company=company, is_default=True).first()
    return default, ((ORIGIN_DEFAULT if default else ORIGIN_NONE), None)
