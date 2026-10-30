# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_reminders.py
"""
WhatsApp reminders of forgotten clock presses (H24, S141).

Miguel Ángel's rule (S141): a quarter of an hour after the start of
the worker's schedule (the season one, already defined in the panel),
if they have not clocked in, a reminder; the same for the clock-out a
quarter of an hour after the end of the schedule. Never when the
worker is on holiday, has an absence (or a sick leave) or the day is
a holiday of their base's labour calendar. Two templates: forgotten
IN and forgotten OUT.

---

Recordatorios por WhatsApp de fichajes olvidados (H24, S141).

Regla de Miguel Ángel (S141): un cuarto de hora después de la hora de
entrada del horario del trabajador (el de la temporada, ya definido en
el panel), si no ha fichado la entrada, un recordatorio; lo mismo con
la salida un cuarto de hora después de la hora de salida. Nunca si
está de vacaciones, tiene una ausencia (o una baja) o el día es
festivo del calendario laboral de su base. Dos plantillas: olvido de
la entrada y olvido de la salida.

- Horario: `_resolve_operator_schedule` (el mismo que usan los partes
  y el informe de fichajes), y solo si tiene un horario asignado, suyo
  o de su sección (S141: el de por defecto de la empresa no cuenta); entrada = la primera hora de entrada,
  salida = la última hora de salida (la comida ya no se ficha, S133).
- Festivos: `_day_rule` del informe de fichajes (sábados, domingos y
  festivos de la base; los guardas nocturnos, todos los días).
- Un recordatorio por trabajador, día y tipo (`ClockReminder`).
- A quién (S141, desde la pestaña Fichajes, hr_calendar/clock_settings):
  envío activado en la empresa, sección que ficha con la plataforma,
  trabajador obligado a fichar y con los recordatorios activados.
- Dentro de la ventana de 24 horas sale como texto libre; fuera, con
  la plantilla, solo cuando Meta la ha aprobado.
"""
import datetime
import logging
import os

from django.db.models import Q
from django.utils import timezone

from hr_calendar.models import AbsencePeriod
from hr_calendar.models import ClockEvent
from hr_calendar.models import ClockReminder
from hr_calendar.models import MedicalLeavePeriod
from hr_calendar.models import VacationPeriod

logger = logging.getLogger(__name__)

REMINDER_DELAY = datetime.timedelta(minutes=15)
IN_TEMPLATE = "clock_in_reminder"
OUT_TEMPLATE = "clock_out_reminder"
# S141 (Miguel Ángel): las mismas con un botón «Fichar ahora». Se usan
# en cuanto Meta las aprueba; hasta entonces, las de texto plano.
IN_LINK_TEMPLATE = "clock_in_reminder_link"
OUT_LINK_TEMPLATE = "clock_out_reminder_link"


def _away(company_user, person, day):
    """
    True if the worker is on holiday, absent or on sick leave that day.

    ---

    True si ese día el trabajador está de vacaciones, ausente o de
    baja.
    """
    on_holiday = Q(operator=company_user)
    if person is not None:
        on_holiday |= Q(person=person)
    if VacationPeriod.objects.filter(
        on_holiday, date_start__lte=day, date_end__gte=day,
    ).exists():
        return True
    if person is None:
        return False
    if AbsencePeriod.objects.filter(
        person=person, date_start__lte=day, date_end__gte=day,
    ).exists():
        return True
    return MedicalLeavePeriod.objects.filter(
        Q(date_end__isnull=True) | Q(date_end__gte=day),
        person=person, date_start__lte=day,
    ).exists()


def _phone(company_user, person):
    """
    The worker's WhatsApp number (E.164), or None.

    ---

    El móvil de WhatsApp del trabajador (E.164): el de su ficha de
    Personal y, si no tiene, el de su cuenta del panel.
    """
    from document_explorer.person_phone_service import mobile_of
    from document_explorer.person_phone_service import whatsapp_address

    if person is not None:
        phone = mobile_of(person)
        if phone:
            return phone
    return whatsapp_address(company_user.phone)


def _person(company_user):
    """
    The worker's Personal record, or None.

    ---

    La ficha de Personal del usuario, o None si no tiene.
    """
    from document_explorer.models import PersonIdentity

    try:
        return company_user.person_identity
    except PersonIdentity.DoesNotExist:
        return None


def due_reminder(schedule_starts, schedule_ends, events, now):
    """
    The reminder due now for one user, as (kind, scheduled time), or
    None. `events` are the user's presses of the day, in order.

    ---

    El recordatorio que toca ahora a un usuario, como (tipo, hora del
    horario), o None. `events` son sus pulsaciones del día, en orden.
    - Entrada: pasado un cuarto de hora de la primera hora de entrada,
      sin ninguna entrada ese día, y antes de la hora de salida.
    - Salida: pasado un cuarto de hora de la última hora de salida,
      con la jornada abierta (la última pulsación del día es una
      entrada). Un horario que cruza la medianoche no lleva aviso de
      salida: ese día no sabe cuál es su salida.
    """
    if not schedule_starts or not schedule_ends:
        return None
    start, end = min(schedule_starts), max(schedule_ends)
    day = now.date()
    tz = timezone.get_current_timezone()
    start_at = timezone.make_aware(datetime.datetime.combine(day, start), tz)
    end_at = timezone.make_aware(datetime.datetime.combine(day, end), tz)
    kinds = [event.kind for event in events]
    if not set(kinds) & {ClockEvent.Kind.IN, ClockEvent.Kind.CHANGE}:
        if start_at + REMINDER_DELAY <= now < end_at:
            return ClockReminder.Kind.IN, start
        return None
    # S141: un cambio de tipo deja la jornada abierta, como la entrada.
    if (end > start
            and kinds[-1] in (ClockEvent.Kind.IN, ClockEvent.Kind.CHANGE)
            and now >= end_at + REMINDER_DELAY):
        return ClockReminder.Kind.OUT, end
    return None


def _templates(company):
    """
    {kind: (WhatsAppTemplate or None, approved by Meta)}.

    ---

    {tipo: (plantilla o None, aprobada por Meta)}.
    """
    from fleet.refuel_questions import template_approved
    from whatsapp.models import WhatsAppTemplate

    result = {}
    for kind, names in (
            (ClockReminder.Kind.IN, (IN_LINK_TEMPLATE, IN_TEMPLATE)),
            (ClockReminder.Kind.OUT, (OUT_LINK_TEMPLATE, OUT_TEMPLATE))):
        # La del botón si ya está aprobada; si no, la de texto plano.
        result[kind] = (None, False)
        for name in names:
            template = WhatsAppTemplate.objects.filter(
                company=company, name=name,
            ).first()
            if template is None:
                continue
            # Sin ninguna aprobada se queda la de texto plano (la
            # última), que dentro de la ventana sale como texto libre.
            approved = template_approved(template.content_sid)
            result[kind] = (template, approved)
            if approved:
                break
    return result


def send_clock_reminders(company, now=None, log=logger.info):
    """
    Send the reminders due now. Returns a counters dict.

    ---

    Envía los recordatorios que tocan ahora, con las condiciones del
    docstring del módulo. Devuelve los contadores.
    """
    from document_explorer.models import PersonIdentity
    from hr_calendar.clock_report import _day_rule
    from hr_calendar.clock_report import schedule_ends
    from hr_calendar.clock_report import schedule_starts
    from hr_calendar.clock_settings import reminders_enabled
    from hr_calendar.clock_settings import worker_states
    from panel.views_operator import _resolve_operator_schedule
    from panel.views_operator import has_assigned_schedule
    from whatsapp.services import _build_twilio_client
    from whatsapp.window_service import send_notification
    from whatsapp.window_service import window_open

    now = timezone.localtime(now or timezone.now())
    day = now.date()
    counters = {"enviados": 0, "festivo": 0, "fuera": 0, "sin_horario": 0,
                "sin_movil": 0, "sin_plantilla": 0, "errores": 0}
    # S141: el permiso de envío se da en la pestaña Fichajes.
    if not reminders_enabled(company):
        log("Recordatorios de fichaje: desactivados en Fichajes.")
        return counters
    sender = os.environ.get("TWILIO_WHATSAPP_SENDER", "")
    if not sender:
        log("Recordatorios de fichaje: sin TWILIO_WHATSAPP_SENDER.")
        return counters
    # Se pregunta a Twilio por la aprobación solo cuando toca enviar.
    templates = None
    already = set(ClockReminder.objects.filter(
        company=company, day=day,
    ).values_list("company_user_id", "kind"))
    tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(
        datetime.datetime.combine(day, datetime.time.min), tz)
    events_by_user = {}
    for event in ClockEvent.objects.current().filter(
        company=company, pressed_at__gte=day_start,
        pressed_at__lt=day_start + datetime.timedelta(days=1),
    ).order_by("pressed_at"):
        events_by_user.setdefault(event.company_user_id, []).append(event)
    client = None
    # S141: solo los trabajadores con los recordatorios activados, que
    # están obligados a fichar y cuya sección ficha con la plataforma.
    people = list(PersonIdentity.objects.filter(
        clock_setting__reminders=True,
        company_user__company=company,
        company_user__is_active=True,
    ).select_related("company_user__base", "company_user__user"))
    states = worker_states(people, day)
    users = [
        p.company_user for p in people if states[p.pk].must_clock
    ]
    for company_user in users:
        if not _day_rule(company_user)(day):
            counters["festivo"] += 1
            continue
        # S141: el horario de hoy (puede ser distinto según el día).
        # S141 (Miguel Ángel): solo a quien tiene un horario asignado
        # (el suyo o el de su sección); el de por defecto no cuenta.
        if not has_assigned_schedule(company_user):
            counters["sin_horario"] += 1
            continue
        schedule = _resolve_operator_schedule(company_user, company, day)
        if schedule is None:
            counters["sin_horario"] += 1
            continue
        due = due_reminder(
            schedule_starts(schedule), schedule_ends(schedule),
            events_by_user.get(company_user.pk, []), now,
        )
        if due is None or (company_user.pk, due[0]) in already:
            continue
        kind, scheduled_time = due
        person = _person(company_user)
        if _away(company_user, person, day):
            counters["fuera"] += 1
            continue
        phone = _phone(company_user, person)
        if not phone:
            counters["sin_movil"] += 1
            log("Sin móvil: %s." % company_user.user.username)
            continue
        if templates is None:
            templates = _templates(company)
        template, approved = templates[kind]
        # Sin plantilla aprobada solo se puede escribir dentro de la
        # ventana de 24 horas (texto libre con el texto de la
        # plantilla).
        if template is None or not (
                approved or window_open(company, phone)):
            counters["sin_plantilla"] += 1
            continue
        # S141: como en el aviso de la sala («Miguel Angel», no
        # «MIGUEL ANGEL»).
        name = ((person.given_name if person is not None else "")
                or company_user.user.first_name or "trabajador")
        name = name.strip().title()
        variables = {
            "1": name,
            "2": day.strftime("%d/%m"),
            "3": scheduled_time.strftime("%H:%M"),
        }
        if client is None:
            client = _build_twilio_client()
        try:
            message = send_notification(
                client, sender, company, phone, template.content_sid,
                variables,
            )
        except Exception as exc:  # Twilio: se apunta y se sigue.
            counters["errores"] += 1
            log("ERROR enviando recordatorio a %s: %s"
                % (company_user.user.username, exc))
            continue
        ClockReminder.objects.create(
            company=company, company_user=company_user, day=day, kind=kind,
            scheduled_time=scheduled_time, phone=phone,
            message_sid=getattr(message, "sid", "") or "",
            sent_as_text=getattr(message, "sent_as_text", False),
        )
        counters["enviados"] += 1
        log("Recordatorio de %s enviado a %s (horario %s)." % (
            ClockReminder.Kind(kind).label.lower(),
            company_user.user.username, variables["3"],
        ))
    log("Recordatorios de fichaje: %(enviados)d enviados, %(festivo)d "
        "con el día festivo, %(sin_horario)d sin horario, %(fuera)d de "
        "vacaciones/ausencia/baja, %(sin_movil)d sin móvil, "
        "%(sin_plantilla)d sin plantilla aprobada, %(errores)d errores."
        % counters)
    return counters
