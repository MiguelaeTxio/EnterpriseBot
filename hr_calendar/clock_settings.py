# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_settings.py
"""
Clock-in settings managed from the panel (H24, S141).

Miguel Ángel (S141): everything is set from the Fichajes tab -- the
permission to send the reminders, which sections clock in with the
platform (Plataformas clocks with Prologic and is taken out or put
back as the bosses say) and, per worker, whether they must clock
(a section head, for instance, may not) and whether they get the
reminders.

---

Ajustes de fichaje desde el panel (H24, S141).

Miguel Ángel (S141): todo se configura desde la pestaña Fichajes: el
permiso para enviar los recordatorios, qué secciones fichan con la
plataforma (Plataformas ficha con Prologic y se quita o se pone según
digan los jefes) y, por trabajador, si está obligado a fichar (un jefe
de sección, por ejemplo, puede no estarlo) y si recibe los
recordatorios.

Un trabajador recibe un recordatorio solo si: el envío está activado
en la empresa, su sección ficha con la plataforma, él está obligado a
fichar y tiene los recordatorios activados.
"""
from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from hr_calendar.models import ClockSettings
from hr_calendar.models import ClockType
from hr_calendar.models import PersonSectionAssignment
from hr_calendar.models import SectionClockSetting
from hr_calendar.models import WorkerClockSetting


@dataclass
class WorkerClockState:
    """
    Clock-in state of one worker, as shown in the Fichajes list.
    ---
    Estado de fichaje de un trabajador, tal como sale en Fichajes.
    """

    section: object = None
    section_clocks: bool = True
    worker_clocks: bool = True
    reminders: bool = False
    # S141: su sección ficha por tipos (Grúas, Asistencia). S148: o él,
    # con su tipo de fichaje propio (clock_mode).
    uses_types: bool = False
    # S148: "" como su sección, "normal" o "types".
    clock_mode: str = ""
    # S143: los avisos que ha elegido (claves de WorkerClockSetting;
    # None: los de por defecto).
    in_reminders: list = None
    out_reminders: list = None
    # S143: desde qué día ficha (None: desde ya) y el día que se mira.
    clocks_from: object = None
    day: object = None

    @property
    def starts_later(self):
        """
        True if the worker only starts clocking after `day`.
        ---
        True si todavía no ha llegado su primer día de fichaje.
        """
        day = self.day or timezone.localdate()
        return self.clocks_from is not None and day < self.clocks_from

    @property
    def must_clock(self):
        return (self.section_clocks and self.worker_clocks
                and not self.starts_later)

    @property
    def section_name(self):
        return self.section.name if self.section is not None else ""


def reminders_enabled(company):
    """
    True if the company has the reminders switched on.
    ---
    True si la empresa tiene activado el envío de recordatorios.
    """
    return ClockSettings.objects.filter(
        company=company, reminders_enabled=True,
    ).exists()


def set_reminders_enabled(company, enabled, by):
    """
    Switch the company's reminders on or off.
    ---
    Activa o desactiva el envío de recordatorios de la empresa.
    """
    settings, _created = ClockSettings.objects.get_or_create(
        company=company,
    )
    settings.reminders_enabled = bool(enabled)
    settings.updated_by = by
    settings.save()
    return settings


def set_worker_reminders(person, in_keys, out_keys):
    """
    The worker's own choice of reminders, with checkboxes.
    ---
    Los avisos que elige el propio trabajador en su página de fichaje
    (S143): los de entrada y los de salida, cada uno solo si todavía no
    ha fichado. Una lista vacía es "ninguno". ValueError si alguna clave
    no es de las permitidas.
    """
    allowed_in = dict(WorkerClockSetting.IN_REMINDER_CHOICES)
    allowed_out = dict(WorkerClockSetting.OUT_REMINDER_CHOICES)
    in_keys = [str(key) for key in in_keys]
    out_keys = [str(key) for key in out_keys]
    bad = [k for k in in_keys if k not in allowed_in] + [
        k for k in out_keys if k not in allowed_out]
    if bad:
        raise ValueError("Valor no permitido: %s." % ", ".join(bad))
    setting, _created = WorkerClockSetting.objects.get_or_create(
        person=person,
    )
    # In the order of the choices, without repeats.
    # En el orden de las opciones, sin repetir.
    setting.in_reminders = ",".join(
        k for k in allowed_in if k in in_keys)
    setting.out_reminders = ",".join(
        k for k in allowed_out if k in out_keys)
    setting.save(update_fields=["in_reminders", "out_reminders",
                                "updated_at"])
    return setting


def set_worker_own_schedule(person, shifts, days, until):
    """
    The worker's own schedule for the reminders (open schedules).
    ---
    El horario propio para los avisos que se pone el trabajador con
    horario abierto (S143): `shifts` como [["07:00", "13:00"], ...] (las
    pausas de comida o cena quedan entre tramos), `days` los días de la
    semana (0 lunes ... 6 domingo) y `until` "AAAA-MM-DD" o vacío. Sin
    tramos se quita. ValueError si algo no vale: cada salida después de
    su entrada y cada tramo después del anterior, en el mismo día.
    """
    import datetime

    if len(shifts) > WorkerClockSetting.MAX_OWN_SHIFTS:
        raise ValueError("Como mucho %d tramos."
                         % WorkerClockSetting.MAX_OWN_SHIFTS)
    parsed, previous_end = [], None
    for shift in shifts:
        try:
            start, end = shift
            start_t = datetime.datetime.strptime(str(start), "%H:%M").time()
            end_t = datetime.datetime.strptime(str(end), "%H:%M").time()
        except (TypeError, ValueError):
            raise ValueError("Pon la hora de entrada y la de salida de "
                             "cada tramo.") from None
        if end_t <= start_t:
            raise ValueError("La salida va después de la entrada.")
        if previous_end is not None and start_t < previous_end:
            raise ValueError("Cada tramo va después del anterior.")
        previous_end = end_t
        parsed.append("%s-%s" % (start_t.strftime("%H:%M"),
                                 end_t.strftime("%H:%M")))
    try:
        day_numbers = sorted({int(d) for d in days})
    except (TypeError, ValueError):
        day_numbers = [-1]
    if any(d < 0 or d > 6 for d in day_numbers):
        raise ValueError("Día de la semana no válido.")
    if parsed and not day_numbers:
        raise ValueError("Marca algún día.")
    try:
        until_date = (datetime.date.fromisoformat(str(until)) if until
                      else None)
    except ValueError:
        raise ValueError("La fecha de fin no es válida.") from None
    setting, _created = WorkerClockSetting.objects.get_or_create(
        person=person,
    )
    setting.own_schedule = ",".join(parsed)
    setting.own_schedule_days = ",".join(str(d) for d in day_numbers)
    setting.own_schedule_until = until_date
    setting.save(update_fields=["own_schedule", "own_schedule_days",
                                "own_schedule_until", "updated_at"])
    return setting


def current_sections(person_ids, day=None):
    """
    {person id: Section in force on `day` (today by default) or None}.
    ---
    {id de persona: sección vigente ese día (hoy por defecto) o None}:
    la asignación con la fecha más reciente que no sea posterior.
    """
    day = day or timezone.localdate()
    result = {pk: None for pk in person_ids}
    for assignment in PersonSectionAssignment.objects.filter(
        person_id__in=list(person_ids), valid_from__lte=day,
    ).select_related("section").order_by("person_id", "valid_from"):
        result[assignment.person_id] = assignment.section
    _fill_from_ivr_contacts(result)
    return result


def _fill_from_ivr_contacts(result):
    """
    Fill the workers without a Personal section with their IVR one.
    ---
    S141 (Miguel Ángel: "en taller mecánico había una pila de gente"):
    casi nadie tiene todavía asignación de sección de Personal; la
    sección de verdad es la de la centralita (los contactos de cada
    sección, SectionContact). A quien no tiene asignación de Personal se
    le da la sección activa de su contacto (el de su usuario del panel),
    la de prioridad más alta si está en varias. La asignación de Personal
    manda siempre que exista.
    """
    from document_explorer.models import PersonIdentity
    from ivr_config.models import SectionContact

    missing = [pk for pk, section in result.items() if section is None]
    if not missing:
        return
    person_of_user = dict(PersonIdentity.objects.filter(
        pk__in=missing, company_user__isnull=False,
    ).values_list("company_user_id", "pk"))
    if not person_of_user:
        return
    links = SectionContact.objects.filter(
        contact__company_user_id__in=list(person_of_user),
        section__is_active=True,
    ).select_related("section", "contact").order_by(
        "priority", "section__name",
    )
    for link in links:
        person_id = person_of_user.get(link.contact.company_user_id)
        if person_id is not None and result.get(person_id) is None:
            result[person_id] = link.section


def section_clocks_map(section_ids):
    """
    {section id: clocks with the platform} (no row = True).
    ---
    {id de sección: ficha con la plataforma} (sin fila = sí).
    """
    result = {pk: True for pk in section_ids}
    for setting in SectionClockSetting.objects.filter(
        section_id__in=list(section_ids),
    ):
        result[setting.section_id] = setting.clocks
    return result


def section_types_map(section_ids):
    """
    {section id: clocks by types} (no row = False).
    ---
    {id de sección: ficha por tipos} (sin fila = no).
    """
    result = {pk: False for pk in section_ids}
    for setting in SectionClockSetting.objects.filter(
        section_id__in=list(section_ids),
    ):
        result[setting.section_id] = setting.uses_types
    return result


def uses_types(company_user, day=None):
    """
    True if the user's section (today) clocks by types.
    ---
    True si la sección vigente del usuario ficha por tipos. Sin ficha de
    Personal o sin sección, no. S148: el tipo de fichaje propio del
    trabajador (WorkerClockSetting.clock_mode) manda sobre su sección.
    """
    try:
        person = company_user.person_identity
    except ObjectDoesNotExist:
        return False
    mode = WorkerClockSetting.objects.filter(
        person=person).values_list("clock_mode", flat=True).first()
    if mode == WorkerClockSetting.CLOCK_MODE_TYPES:
        return True
    if mode == WorkerClockSetting.CLOCK_MODE_NORMAL:
        return False
    section = current_sections([person.pk], day).get(person.pk)
    if section is None:
        return False
    return section_types_map([section.pk])[section.pk]


def active_types(company):
    """
    The company's active clock types, in order.
    ---
    Los tipos de fichaje activos de la empresa, en orden.
    """
    return list(ClockType.objects.filter(company=company, is_active=True))


def default_type(company):
    """
    The default clock type ("Trabajo efectivo" since S144), or None.
    ---
    El tipo por defecto ("Trabajo efectivo" desde S144), o None.
    """
    return ClockType.objects.filter(
        company=company, is_default=True, is_active=True,
    ).first()


def set_section_types(section, value, by):
    """
    Put a section in or out of clocking by types.
    ---
    Pone o quita una sección del fichaje por tipos.
    """
    setting, _created = SectionClockSetting.objects.get_or_create(
        section=section,
    )
    setting.uses_types = bool(value)
    setting.updated_by = by
    setting.save()
    return setting


def worker_states(people, day=None):
    """
    {person id: WorkerClockState} for a list of PersonIdentity.
    ---
    {id de persona: WorkerClockState} para una lista de personas, con
    unas pocas consultas en total.
    """
    ids = [p.pk for p in people]
    sections = current_sections(ids, day)
    section_ids = {s.pk for s in sections.values() if s is not None}
    clocks = section_clocks_map(section_ids)
    by_types = section_types_map(section_ids)
    settings = {
        s.person_id: s
        for s in WorkerClockSetting.objects.filter(person_id__in=ids)
    }
    states = {}
    for pk in ids:
        section = sections.get(pk)
        setting = settings.get(pk)
        mode = setting.clock_mode if setting else ""
        section_types = (by_types.get(section.pk, False)
                         if section is not None else False)
        states[pk] = WorkerClockState(
            section=section,
            section_clocks=(clocks.get(section.pk, True)
                            if section is not None else True),
            worker_clocks=setting.clocks if setting else True,
            reminders=setting.reminders if setting else False,
            uses_types=(
                True if mode == WorkerClockSetting.CLOCK_MODE_TYPES
                else False if mode == WorkerClockSetting.CLOCK_MODE_NORMAL
                else section_types),
            clock_mode=mode,
            in_reminders=setting.in_reminder_keys() if setting else None,
            out_reminders=(setting.out_reminder_keys()
                           if setting else None),
            clocks_from=setting.clocks_from if setting else None,
            day=day,
        )
    return states


def set_worker_flag(person_ids, field, value, by):
    """
    Set `clocks` or `reminders` for several workers. Returns how many.
    ---
    Pone `clocks` o `reminders` a varios trabajadores. Devuelve cuántos.
    """
    if field not in ("clocks", "reminders"):
        raise ValueError(field)
    count = 0
    for pk in person_ids:
        setting, _created = WorkerClockSetting.objects.get_or_create(
            person_id=pk,
        )
        setattr(setting, field, bool(value))
        setting.updated_by = by
        setting.save()
        count += 1
    return count


def set_worker_clock_mode(person_ids, mode, by):
    """
    Own clock mode of several workers ("" back to their section's).
    ---
    Tipo de fichaje propio de varios trabajadores (S148): "normal",
    "types" o "" (vuelven al de su sección). Devuelve cuántos.
    """
    if mode not in dict(WorkerClockSetting.CLOCK_MODE_CHOICES):
        raise ValueError(mode)
    count = 0
    for pk in person_ids:
        setting, _created = WorkerClockSetting.objects.get_or_create(
            person_id=pk,
        )
        setting.clock_mode = mode
        setting.updated_by = by
        setting.save()
        count += 1
    return count


def set_worker_clocks_from(person_ids, day, by):
    """
    The marked workers clock from `day` (None: from now). Returns how
    many.
    ---
    Los marcados fichan desde `day` (S143; None: desde ya) y quedan
    obligados a fichar. Devuelve cuántos.
    """
    count = 0
    for pk in person_ids:
        setting, _created = WorkerClockSetting.objects.get_or_create(
            person_id=pk,
        )
        setting.clocks = True
        setting.clocks_from = day
        setting.updated_by = by
        setting.save()
        count += 1
    return count


def set_worker_schedule(people, schedule, by):
    """
    Set (or clear) the own WorkdaySchedule of several workers.
    ---
    Pone (o quita, con None) el horario propio de varios trabajadores
    (S141, pestaña Horarios). Al quitarlo se quita también el que
    pudiera tener su usuario del panel de antes de S141, para que les
    toque el de su sección o el de por defecto. Devuelve cuántos.
    """
    from ivr_config.models import CompanyUser

    count = 0
    for person in people:
        setting, _created = WorkerClockSetting.objects.get_or_create(
            person=person,
        )
        setting.workday_schedule = schedule
        setting.updated_by = by
        setting.save()
        count += 1
    if schedule is None:
        CompanyUser.objects.filter(
            pk__in=[p.company_user_id for p in people if p.company_user_id],
        ).update(workday_schedule=None)
    return count


def set_section_clocks(section, clocks, by):
    """
    Put a section in or out of clocking with the platform.
    ---
    Pone o quita una sección del fichaje con la plataforma.
    """
    setting, _created = SectionClockSetting.objects.get_or_create(
        section=section,
    )
    setting.clocks = bool(clocks)
    setting.updated_by = by
    setting.save()
    return setting
