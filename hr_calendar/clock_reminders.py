# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_reminders.py
"""
WhatsApp reminders of forgotten clock presses (H24, S141).

S144: each worker chooses on their clock-in page when to get it, from
15 minutes before to 15 after the scheduled time (5 minutes before by
default).

Miguel Ángel's rule (S141): a quarter of an hour after the start of
the worker's schedule (the season one, already defined in the panel),
if they have not clocked in, a reminder; the same for the clock-out a
quarter of an hour after the end of the schedule. Never when the
worker is on holiday, has an absence (or a sick leave) or the day is
a holiday of their base's labour calendar. Two templates: forgotten
IN and forgotten OUT.

---

Recordatorios por WhatsApp de fichajes olvidados (H24, S141).

S144 (Miguel Ángel): el momento lo elige cada trabajador en su página
de fichaje ("que no sea que lo decide el supervisor"), de 15 minutos
antes a 15 después de la hora del horario, de 5 en 5; quien no elige,
5 minutos antes (ClockSettings.reminder_offset_minutes).

Regla de Miguel Ángel (S141): un cuarto de hora después de la hora de
entrada del horario del trabajador (el de la temporada, ya definido en
el panel), si no ha fichado la entrada, un recordatorio; lo mismo con
la salida un cuarto de hora después de la hora de salida. Nunca si
está de vacaciones, tiene una ausencia (o una baja) o el día es
festivo del calendario laboral de su base. Dos plantillas: olvido de
la entrada y olvido de la salida.

- Horario: `_resolve_operator_schedule` (el mismo que usan los partes
  y el informe de fichajes), y solo si tiene un horario asignado, suyo
  o de su sección (S141: el de por defecto de la empresa no cuenta);
  entrada = la primera hora de entrada, salida = la última hora de
  salida (la comida ya no se ficha, S133).
- Festivos: `_day_rule` del informe de fichajes (S144: festivos de la
  base solo con "Se trabaja en festivos" en el horario; sábados y
  domingos, los guardas y los horarios según el día).
- Un recordatorio por trabajador, día y tipo (`ClockReminder`).
- A quién (S141, desde la pestaña Fichajes, hr_calendar/clock_settings):
  envío activado en la empresa, sección que ficha con la plataforma,
  trabajador obligado a fichar y con los recordatorios activados.
- Dentro de la ventana de 24 horas sale como texto libre; fuera, con
  la plantilla, solo cuando Meta la ha aprobado.
- S144 (Miguel Ángel): con horario abierto, ningún recordatorio. Tras
  una jornada excepcional, tampoco: ni el día en que la salida anterior
  queda a menos de REST_HOURS (hr_calendar/clock_report.py) de la
  primera entrada del horario, ni mientras sigue abierta una jornada
  empezada el día anterior fuera de horario (trabajo nocturno), ni el
  de salida de una jornada que entró fuera de horario.
- S144 (guardas): horario de noche (la salida del último tramo es menor
  que su entrada: sale al día siguiente). El de entrada sale esa noche;
  el de salida, a la mañana siguiente si la jornada sigue abierta, y se
  apunta en el día de la entrada.
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

# S141: un cuarto de hora después; S144: lo elige cada trabajador
# (WorkerClockSetting.reminder_offset_minutes), este es solo el de reserva.
REMINDER_DELAY = datetime.timedelta(minutes=15)
IN_TEMPLATE = "clock_in_reminder"
OUT_TEMPLATE = "clock_out_reminder"
# S141 (Miguel Ángel): las mismas con un botón «Fichar ahora». Se usan
# en cuanto Meta las aprueba; hasta entonces, las de texto plano.
IN_LINK_TEMPLATE = "clock_in_reminder_link"
OUT_LINK_TEMPLATE = "clock_out_reminder_link"
# S144: el aviso que sale antes de la hora del horario ("Recuerde
# fichar"), no el de "no consta que haya fichado". Hasta que Meta la
# apruebe se usa la de siempre.
IN_EARLY_TEMPLATE = "clock_in_prereminder_link"
OUT_EARLY_TEMPLATE = "clock_out_prereminder_link"


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


def due_reminder(schedule_starts, schedule_ends, events, now,
                 offset=REMINDER_DELAY):
    """
    The reminder due now for one user, as (kind, scheduled time), or
    None. `events` are the user's presses of the day, in order.

    ---

    El recordatorio que toca ahora a un usuario, como (tipo, hora del
    horario), o None. `events` son sus pulsaciones del día, en orden.
    `offset` (S144): cuándo, respecto de la hora del horario (negativo,
    antes; un cuarto de hora después hasta S144).
    - Entrada: desde la primera hora de entrada + offset, sin ninguna
      entrada ese día, y antes de la hora de salida.
    - Salida: desde la última hora de salida + offset,
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
    if end <= start:
        # S144: horario de noche, la salida es del día siguiente.
        end_at += datetime.timedelta(days=1)
    kinds = [event.kind for event in events]
    if not set(kinds) & {ClockEvent.Kind.IN, ClockEvent.Kind.CHANGE}:
        if start_at + offset <= now < end_at:
            return ClockReminder.Kind.IN, start
        return None
    # S141: un cambio de tipo deja la jornada abierta, como la entrada.
    if (end > start
            and kinds[-1] in (ClockEvent.Kind.IN, ClockEvent.Kind.CHANGE)
            and now >= end_at + offset
            and not _off_schedule(_opening(events), schedule_starts)):
        return ClockReminder.Kind.OUT, end
    return None


def overnight_out_due(company_user, company, day, events, now,
                      offset=REMINDER_DELAY):
    """
    The OUT reminder of last night's shift, as (kind, time), or None.
    ---
    S144 (guardas): el recordatorio de salida de la jornada de noche de
    ayer, como (tipo, hora del horario), o None. Toca si el horario de
    ayer acaba hoy (salida del último tramo menor que su entrada), ya
    ha llegado su hora (salida + offset) y sigue abierta una
    jornada que entró ayer dentro de horario. `events` son las
    pulsaciones desde 24 h antes del día hasta ahora, en orden.
    """
    from hr_calendar.clock_report import MAX_SHIFT_HOURS
    from hr_calendar.clock_report import schedule_ends
    from hr_calendar.clock_report import schedule_starts
    from panel.views_operator import _resolve_operator_schedule

    yesterday = day - datetime.timedelta(days=1)
    schedule = _resolve_operator_schedule(company_user, company, yesterday)
    if schedule is None or schedule.is_open:
        return None
    starts, ends = schedule_starts(schedule), schedule_ends(schedule)
    if not starts or not ends or ends[-1] > starts[-1]:
        return None
    end_at = timezone.make_aware(
        datetime.datetime.combine(day, ends[-1]),
        timezone.get_current_timezone())
    if now < end_at + offset:
        return None
    opening = _opening(events)
    if opening is None or opening.kind == ClockEvent.Kind.OUT:
        return None
    opened = opening.pressed_at
    if (timezone.localtime(opened).date() != yesterday
            or now - opened > datetime.timedelta(hours=MAX_SHIFT_HOURS)
            or _off_schedule(opening, starts)):
        return None
    return ClockReminder.Kind.OUT, ends[-1]


def _opening(events):
    """
    The press that opened the last open shift of `events`, or None.
    ---
    La pulsación que abrió la última jornada abierta: la última entrada
    (los cambios de tipo de después no la cierran).
    """
    for event in reversed(events):
        if event.kind == ClockEvent.Kind.OUT:
            return None
        if event.kind == ClockEvent.Kind.IN:
            return event
    return events[-1] if events else None


def _off_schedule(event, starts):
    """
    True if the press is more than MAX_COMPARE_MINUTES away from every
    start time: a shift begun out of schedule (S144).
    ---
    True si la pulsación está a más de MAX_COMPARE_MINUTES de todas las
    horas de entrada: una jornada empezada fuera de horario, que no
    lleva recordatorios (S144).
    """
    from hr_calendar.clock_report import MAX_COMPARE_MINUTES

    if event is None or not starts:
        return False
    real = timezone.localtime(event.pressed_at)
    minutes = real.hour * 60 + real.minute
    return min(
        abs(t.hour * 60 + t.minute - minutes) for t in starts
    ) > MAX_COMPARE_MINUTES


def exceptional_day(company_user, company, day, starts, events, now):
    """
    True if no reminder goes today after an exceptional shift (S144).
    ---
    True si hoy no va ningún recordatorio por una jornada excepcional
    (S144). `events` son las pulsaciones desde 24 h antes del día hasta
    ahora, en orden.
    - La salida anterior a la primera entrada del horario de hoy queda a
      menos de REST_HOURS de ella (clock_report.short_rest).
    - O sigue abierta una jornada empezada ayer fuera del horario de
      ayer (un trabajo nocturno que todavía no ha terminado).
    """
    from hr_calendar.clock_report import MAX_SHIFT_HOURS
    from hr_calendar.clock_report import build_shifts
    from hr_calendar.clock_report import schedule_starts
    from hr_calendar.clock_report import short_rest
    from panel.views_operator import _resolve_operator_schedule

    if not starts:
        return False
    tz = timezone.get_current_timezone()
    start_at = timezone.make_aware(
        datetime.datetime.combine(day, min(starts)), tz)
    outs = [e.pressed_at for e in events
            if e.kind == ClockEvent.Kind.OUT and e.pressed_at < start_at]
    if short_rest(day, starts, max(outs) if outs else None):
        return True
    shifts = build_shifts(events)
    last = shifts[-1] if shifts else None
    if (last is None or last.clock_in is None
            or last.clock_out is not None):
        return False
    opened = last.clock_in.pressed_at
    if timezone.localtime(opened).date() >= day or (
            now - opened > datetime.timedelta(hours=MAX_SHIFT_HOURS)):
        return False
    yesterday = day - datetime.timedelta(days=1)
    schedule = _resolve_operator_schedule(company_user, company, yesterday)
    return _off_schedule(last.clock_in, schedule_starts(schedule))


def _templates(company, early=False):
    """
    {kind: (WhatsAppTemplate or None, approved by Meta)}.

    ---

    {tipo: (plantilla o None, aprobada por Meta)}. Con `early` (el aviso
    sale antes de la hora del horario, S144), primero la de "Recuerde
    fichar"; sin ella aprobada, las de siempre.
    """
    from fleet.refuel_questions import template_approved
    from whatsapp.models import WhatsAppTemplate

    result = {}
    for kind, names in (
            (ClockReminder.Kind.IN, (IN_LINK_TEMPLATE, IN_TEMPLATE)),
            (ClockReminder.Kind.OUT, (OUT_LINK_TEMPLATE, OUT_TEMPLATE))):
        if early:
            names = ((IN_EARLY_TEMPLATE if kind == ClockReminder.Kind.IN
                      else OUT_EARLY_TEMPLATE),) + names
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
    from hr_calendar.clock_settings import reminder_offset
    from hr_calendar.clock_settings import reminders_enabled
    from hr_calendar.clock_settings import worker_states
    from panel.views_operator import _resolve_base_schedule
    from panel.views_operator import _resolve_operator_schedule
    from panel.views_operator import has_assigned_schedule
    from whatsapp.services import _build_twilio_client
    from whatsapp.window_service import send_notification
    from whatsapp.window_service import window_open

    now = timezone.localtime(now or timezone.now())
    day = now.date()
    counters = {"enviados": 0, "festivo": 0, "fuera": 0, "sin_horario": 0,
                "abierto": 0, "excepcional": 0, "sin_movil": 0,
                "sin_plantilla": 0, "errores": 0}
    # S141: el permiso de envío se da en la pestaña Fichajes.
    if not reminders_enabled(company):
        log("Recordatorios de fichaje: desactivados en Fichajes.")
        return counters
    # S144 (Miguel Ángel): cuándo sale lo elige cada trabajador en su
    # página de fichaje; sin elección, el de la empresa (5 min antes).
    default_offset = reminder_offset(company)
    sender = os.environ.get("TWILIO_WHATSAPP_SENDER", "")
    if not sender:
        log("Recordatorios de fichaje: sin TWILIO_WHATSAPP_SENDER.")
        return counters
    # Se pregunta a Twilio por la aprobación solo cuando toca enviar
    # (S144: un juego para los avisos de antes de la hora y otro para
    # los de a la hora o después).
    templates = {}
    # S144: también los de ayer (el de salida del turno de noche se
    # apunta en el día de la entrada).
    already = set(ClockReminder.objects.filter(
        company=company,
        day__in=[day, day - datetime.timedelta(days=1)],
    ).values_list("company_user_id", "day", "kind"))
    tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(
        datetime.datetime.combine(day, datetime.time.min), tz)
    events_by_user, window_by_user = {}, {}
    # S144: desde 24 h antes, para ver la jornada de ayer (excepcional).
    for event in ClockEvent.objects.current().filter(
        company=company,
        pressed_at__gte=day_start - datetime.timedelta(days=1),
        pressed_at__lt=day_start + datetime.timedelta(days=1),
    ).order_by("pressed_at"):
        window_by_user.setdefault(event.company_user_id, []).append(event)
        if event.pressed_at >= day_start:
            events_by_user.setdefault(
                event.company_user_id, []).append(event)
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
    chosen = {p.company_user_id: states[p.pk].reminder_offset
              for p in people}
    for company_user in users:
        own = chosen.get(company_user.pk)
        offset = datetime.timedelta(
            minutes=default_offset if own is None else own)
        # S144: el festivo depende del horario ("Se trabaja en festivos").
        if not _day_rule(
                company_user,
                _resolve_base_schedule(company_user, company))(day):
            counters["festivo"] += 1
            continue
        # S141: el horario de hoy (puede ser distinto según el día).
        # S141 (Miguel Ángel): solo a quien tiene un horario asignado
        # (el suyo o el de su sección); el de por defecto no cuenta.
        if not has_assigned_schedule(company_user):
            counters["sin_horario"] += 1
            continue
        schedule = _resolve_operator_schedule(company_user, company, day)
        # S144 (Miguel Ángel): "en los horarios abiertos no tenemos
        # ningún recordatorio".
        if schedule is not None and schedule.is_open:
            counters["abierto"] += 1
            continue
        window = [e for e in window_by_user.get(company_user.pk, [])
                  if e.pressed_at <= now]
        due, reminder_day = None, day
        if schedule is not None:
            if exceptional_day(
                    company_user, company, day, schedule_starts(schedule),
                    window, now):
                counters["excepcional"] += 1
                continue
            due = due_reminder(
                schedule_starts(schedule), schedule_ends(schedule),
                events_by_user.get(company_user.pk, []), now, offset,
            )
        if due is None:
            # S144: la salida del turno de noche de ayer (también si hoy
            # no trabaja).
            due = overnight_out_due(company_user, company, day, window, now,
                                    offset)
            reminder_day = day - datetime.timedelta(days=1)
        if due is None:
            if schedule is None:
                counters["sin_horario"] += 1
            continue
        if (company_user.pk, reminder_day, due[0]) in already:
            continue
        kind, scheduled_time = due
        person = _person(company_user)
        if _away(company_user, person, reminder_day):
            counters["fuera"] += 1
            continue
        phone = _phone(company_user, person)
        if not phone:
            counters["sin_movil"] += 1
            log("Sin móvil: %s." % company_user.user.username)
            continue
        # S144: antes de la hora del horario, "Recuerde fichar".
        early = now < timezone.make_aware(
            datetime.datetime.combine(day, scheduled_time), tz)
        if early not in templates:
            templates[early] = _templates(company, early)
        template, approved = templates[early][kind]
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
            "2": reminder_day.strftime("%d/%m"),
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
            company=company, company_user=company_user, day=reminder_day,
            kind=kind,
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
        "con el día festivo, %(sin_horario)d sin horario, %(abierto)d con "
        "horario abierto, %(excepcional)d tras una jornada excepcional, "
        "%(fuera)d de "
        "vacaciones/ausencia/baja, %(sin_movil)d sin móvil, "
        "%(sin_plantilla)d sin plantilla aprobada, %(errores)d errores."
        % counters)
    return counters
