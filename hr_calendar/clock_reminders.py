# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_reminders.py
"""
WhatsApp reminders of forgotten clock presses (H24, S141).

S143: each worker ticks on their clock-in page which reminders they
want: IN 5 minutes before, on time and 3 minutes after; OUT on time, 3
minutes, half an hour, one hour and every hour after. Each one only
goes while the press is still missing.

Miguel Ángel's rule (S141): a quarter of an hour after the start of
the worker's schedule (the season one, already defined in the panel),
if they have not clocked in, a reminder; the same for the clock-out a
quarter of an hour after the end of the schedule. Never when the
worker is on holiday, has an absence (or a sick leave) or the day is
a holiday of their base's labour calendar. Two templates: forgotten
IN and forgotten OUT.

---

Recordatorios por WhatsApp de fichajes olvidados (H24, S141).

S143 (Miguel Ángel, sustituye al momento único de S144): cada
trabajador marca en su página de fichaje qué avisos quiere
(WorkerClockSetting.in_reminders y out_reminders):
- Entrada: 5 minutos antes, a la hora en punto y 3 minutos después.
- Salida: a la hora en punto, 3 minutos, media hora y una hora después,
  y cada hora ("muchas veces tienen que echar horas extras [...] y así
  pueden recibir mensajes recordatorios cada hora para marcar").
- "Cada aviso se enviará si no ha fichado ya": en cuanto ficha, dejan de
  salir. Cada aviso es una fila de ClockReminder (`slot`, minutos
  respecto de la hora del horario); si la tarea va con retraso y tocan
  varios a la vez, sale solo el último.
- "Cada hora" sigue mientras la jornada esté abierta, hasta medianoche
  (el día siguiente ya no cuenta las pulsaciones del anterior) y nunca
  más allá de MAX_SHIFT_HOURS desde la entrada.
- Quien no ha elegido: entrada 5 minutos antes y salida a la hora.
- La tarea corre cada minuto (enterprise_core/settings.py), para que los
  avisos de 3 minutos salgan a su hora.

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

# S143: "cada hora" son los avisos a 60, 120, 180... minutos de la hora
# de salida, como mucho los de un turno (clock_report.MAX_SHIFT_HOURS).
HOURLY_LIMIT_HOURS = 24
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


def reminder_minutes(keys):
    """
    Minutes from the scheduled time of the chosen reminders, sorted.
    ---
    Minutos respecto de la hora del horario de los avisos elegidos
    (claves de WorkerClockSetting), ordenados. "Cada hora" son 60, 120,
    180... hasta HOURLY_LIMIT_HOURS.
    """
    from hr_calendar.models import WorkerClockSetting

    minutes = set()
    for key in keys or ():
        if key == WorkerClockSetting.HOURLY:
            minutes.update(range(60, HOURLY_LIMIT_HOURS * 60 + 1, 60))
        else:
            try:
                minutes.add(int(key))
            except ValueError:
                continue
    return sorted(minutes)


def _latest(anchor, minutes, now):
    """
    The last of `minutes` already reached at `now`, or None.
    ---
    El último de los avisos (`minutes` desde `anchor`) al que ya ha
    llegado `now`, o None: si la tarea va con retraso y tocan varios a
    la vez, sale solo el último.
    """
    reached = [m for m in minutes
               if anchor + datetime.timedelta(minutes=m) <= now]
    return max(reached) if reached else None


def due_reminder(schedule_starts, schedule_ends, events, now,
                 in_minutes, out_minutes):
    """
    The reminder due now for one user, as (kind, scheduled time, slot
    minutes), or None. `events` are the user's presses of the day.

    ---

    El aviso que toca ahora a un usuario, como (tipo, hora del horario,
    minutos del aviso), o None. `events` son sus pulsaciones del día, en
    orden. `in_minutes` y `out_minutes` (S143): los avisos que ha
    elegido, en minutos respecto de la hora (negativo, antes).
    - Entrada: el último aviso de entrada ya alcanzado, sin ninguna
      entrada ese día, y antes de la hora de salida.
    - Salida: el último aviso de salida ya alcanzado, con la jornada
      abierta (la última pulsación del día es una entrada o un cambio
      de tipo) desde hace menos de MAX_SHIFT_HOURS. Un horario que
      cruza la medianoche no lleva aviso de salida ese día
      (overnight_out_due).
    """
    from hr_calendar.clock_report import MAX_SHIFT_HOURS

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
        if now >= end_at:
            return None
        slot = _latest(start_at, in_minutes, now)
        return None if slot is None else (ClockReminder.Kind.IN, start, slot)
    # S141: un cambio de tipo deja la jornada abierta, como la entrada.
    if end <= start or kinds[-1] not in (ClockEvent.Kind.IN,
                                         ClockEvent.Kind.CHANGE):
        return None
    opening = _opening(events)
    if _off_schedule(opening, schedule_starts) or (
            opening is not None and now - opening.pressed_at
            > datetime.timedelta(hours=MAX_SHIFT_HOURS)):
        return None
    slot = _latest(end_at, out_minutes, now)
    return None if slot is None else (ClockReminder.Kind.OUT, end, slot)


def own_shifts_due(shifts, events, now, in_minutes, out_minutes):
    """
    The reminder due now for an own schedule with several shifts, as
    (kind, scheduled time, slot minutes, slot key), or None.

    ---

    S143 (Miguel Ángel): el aviso que toca ahora con el horario propio
    de quien tiene horario abierto, que puede tener varios tramos
    (entrada y salida, pausa de comida o cena, entrada y salida). Como
    (tipo, hora, minutos del aviso, clave del aviso) o None. Cada tramo
    manda desde la mitad de la pausa anterior hasta la mitad de la
    siguiente:
    - Entrada: sin entrada ni cambio de tipo en ese tiempo, con la
      jornada cerrada (sin pulsaciones o la última es una salida) y
      antes de la salida del tramo.
    - Salida: con la jornada abierta (la última pulsación es una entrada
      o un cambio de tipo) desde hace menos de MAX_SHIFT_HOURS.
    La clave del aviso es la de siempre en el primer tramo y "2:0",
    "3:-5"... en los siguientes (uno por tramo y aviso).
    """
    from hr_calendar.clock_report import MAX_SHIFT_HOURS

    if not shifts:
        return None
    tz = timezone.get_current_timezone()
    day = now.date()

    def at(t):
        return timezone.make_aware(datetime.datetime.combine(day, t), tz)

    bounds = [at(datetime.time.min)]
    for (_s, prev_end), (next_start, _e) in zip(shifts, shifts[1:]):
        bounds.append(at(prev_end) + (at(next_start) - at(prev_end)) / 2)
    bounds.append(at(datetime.time.min) + datetime.timedelta(days=1))
    open_kinds = (ClockEvent.Kind.IN, ClockEvent.Kind.CHANGE)
    last = events[-1] if events else None
    for index, (start, end) in enumerate(shifts):
        if not bounds[index] <= now < bounds[index + 1]:
            continue
        inside = [e for e in events
                  if bounds[index] <= e.pressed_at <= now]
        due = None
        if last is None or last.kind == ClockEvent.Kind.OUT:
            if (not any(e.kind in open_kinds for e in inside)
                    and now < at(end)):
                slot = _latest(at(start), in_minutes, now)
                if slot is not None:
                    due = (ClockReminder.Kind.IN, start, slot)
        else:
            opening = _opening(events)
            if opening is None or now - opening.pressed_at <= (
                    datetime.timedelta(hours=MAX_SHIFT_HOURS)):
                slot = _latest(at(end), out_minutes, now)
                if slot is not None:
                    due = (ClockReminder.Kind.OUT, end, slot)
        if due is None:
            return None
        key = str(due[2]) if index == 0 else "%d:%d" % (index + 1, due[2])
        return due + (key,)
    return None


def overnight_out_due(company_user, company, day, events, now,
                      out_minutes):
    """
    The OUT reminder of last night's shift, as (kind, time, slot), or
    None.
    ---
    S144 (guardas): el aviso de salida de la jornada de noche de ayer,
    como (tipo, hora del horario, minutos del aviso), o None. Toca si el
    horario de ayer acaba hoy (salida del último tramo menor que su
    entrada), ya ha llegado alguno de sus avisos de salida (S143) y
    sigue abierta una jornada que entró ayer dentro de horario.
    `events` son las pulsaciones desde 24 h antes del día hasta ahora,
    en orden.
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
    slot = _latest(end_at, out_minutes, now)
    if slot is None:
        return None
    opening = _opening(events)
    if opening is None or opening.kind == ClockEvent.Kind.OUT:
        return None
    opened = opening.pressed_at
    if (timezone.localtime(opened).date() != yesterday
            or now - opened > datetime.timedelta(hours=MAX_SHIFT_HOURS)
            or _off_schedule(opening, starts)):
        return None
    return ClockReminder.Kind.OUT, ends[-1], slot


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
    from hr_calendar.clock_settings import reminders_enabled
    from hr_calendar.models import WorkerClockSetting
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
    # S143: uno por usuario, día, tipo y aviso.
    already = set(ClockReminder.objects.filter(
        company=company,
        day__in=[day, day - datetime.timedelta(days=1)],
    ).values_list("company_user_id", "day", "kind", "slot"))
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
    # S143: los avisos que ha marcado cada uno (o los de por defecto) y
    # el horario propio de hoy de quien tiene horario abierto.
    chosen, own_shifts = {}, {}
    for setting in WorkerClockSetting.objects.filter(
        person__in=people,
    ).exclude(own_schedule="").select_related("person"):
        own_shifts[setting.person.company_user_id] = (
            setting.own_shifts_on(day))
    for p in people:
        state = states[p.pk]
        chosen[p.company_user_id] = (
            reminder_minutes(
                WorkerClockSetting.DEFAULT_IN_REMINDERS
                if state.in_reminders is None else state.in_reminders),
            reminder_minutes(
                WorkerClockSetting.DEFAULT_OUT_REMINDERS
                if state.out_reminders is None else state.out_reminders),
        )
    for company_user in users:
        in_minutes, out_minutes = chosen[company_user.pk]
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
        window = [e for e in window_by_user.get(company_user.pk, [])
                  if e.pressed_at <= now]
        due, reminder_day = None, day
        # S144 (Miguel Ángel): "en los horarios abiertos no tenemos
        # ningún recordatorio". S143: salvo con el horario propio que se
        # haya puesto el trabajador para los avisos.
        if schedule is not None and schedule.is_open:
            shifts = own_shifts.get(company_user.pk, [])
            if not shifts:
                counters["abierto"] += 1
                continue
            due = own_shifts_due(
                shifts, events_by_user.get(company_user.pk, []), now,
                in_minutes, out_minutes,
            )
            if due is None:
                continue
        elif schedule is not None:
            if exceptional_day(
                    company_user, company, day, schedule_starts(schedule),
                    window, now):
                counters["excepcional"] += 1
                continue
            due = due_reminder(
                schedule_starts(schedule), schedule_ends(schedule),
                events_by_user.get(company_user.pk, []), now,
                in_minutes, out_minutes,
            )
            if due is not None:
                due = due + (str(due[2]),)
        if due is None:
            # S144: la salida del turno de noche de ayer (también si hoy
            # no trabaja).
            due = overnight_out_due(company_user, company, day, window, now,
                                    out_minutes)
            if due is not None:
                due = due + (str(due[2]),)
            reminder_day = day - datetime.timedelta(days=1)
        if due is None:
            if schedule is None:
                counters["sin_horario"] += 1
            continue
        kind, scheduled_time, slot, slot_key = due
        if (company_user.pk, reminder_day, kind, slot_key) in already:
            continue
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
            scheduled_time=scheduled_time, phone=phone, slot=slot_key,
            message_sid=getattr(message, "sid", "") or "",
            sent_as_text=getattr(message, "sent_as_text", False),
        )
        counters["enviados"] += 1
        log("Recordatorio de %s enviado a %s (horario %s, aviso %+d min)."
            % (ClockReminder.Kind(kind).label.lower(),
               company_user.user.username, variables["3"], slot))
    log("Recordatorios de fichaje: %(enviados)d enviados, %(festivo)d "
        "con el día festivo, %(sin_horario)d sin horario, %(abierto)d con "
        "horario abierto, %(excepcional)d tras una jornada excepcional, "
        "%(fuera)d de "
        "vacaciones/ausencia/baja, %(sin_movil)d sin móvil, "
        "%(sin_plantilla)d sin plantilla aprobada, %(errores)d errores."
        % counters)
    return counters
