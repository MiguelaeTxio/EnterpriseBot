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

from django.utils import timezone

from hr_calendar.models import ClockSettings
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

    @property
    def must_clock(self):
        return self.section_clocks and self.worker_clocks

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
    return result


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


def worker_states(people, day=None):
    """
    {person id: WorkerClockState} for a list of PersonIdentity.
    ---
    {id de persona: WorkerClockState} para una lista de personas, con
    unas pocas consultas en total.
    """
    ids = [p.pk for p in people]
    sections = current_sections(ids, day)
    clocks = section_clocks_map(
        {s.pk for s in sections.values() if s is not None},
    )
    settings = {
        s.person_id: s
        for s in WorkerClockSetting.objects.filter(person_id__in=ids)
    }
    states = {}
    for pk in ids:
        section = sections.get(pk)
        setting = settings.get(pk)
        states[pk] = WorkerClockState(
            section=section,
            section_clocks=(clocks.get(section.pk, True)
                            if section is not None else True),
            worker_clocks=setting.clocks if setting else True,
            reminders=setting.reminders if setting else False,
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
