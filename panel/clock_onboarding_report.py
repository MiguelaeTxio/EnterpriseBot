# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/clock_onboarding_report.py
"""
Who got the clock-in onboarding and does not clock in (S149).

---

S149 (Miguel Ángel, 20/11): "informes que sean muy claros, con
exportación [...] usuarios que tienen el alta enviada, que la han
recibido, que la han leído y que no están fichando. Desde cuándo
recibieron el alta y el número de días que llevan sin fichar desde que
la recibieron. Si se les ha reenviado el alta, el número de días que
llevan sin fichar desde que se les reenvió [...] para tener un mapa
claro de quiénes son las personas que no están fichando porque no
quieren".

Una fila por trabajador activo con alguna circular de alta enviada por
WhatsApp (ALTA_FICHAJE o ALTA_FICHAJE_PANEL):
- envíos: el primero, el último y cuántos;
- recibida: el estado de WhatsApp (Twilio: entregada, leída en
  WhatsApp, fallida...) del mejor de sus envíos; los anteriores a S149
  lo traen del comando backfill_circular_status_s149;
- abierta: cuándo pulsó «Leer» en la circular (whatsapp_read_at);
- entró en el panel (último acceso) y sus fichajes (primero, último);
- días sin fichar desde el primer envío y desde el último reenvío, si
  no ha fichado desde entonces;
- situación: un solo estado que resume lo anterior (ESTADOS).
"""
import datetime

from django.utils import timezone

ONBOARDING_CODES = ("ALTA_FICHAJE", "ALTA_FICHAJE_PANEL")

# Situación, del "peor" al "mejor" (orden del resumen y del filtro).
NOT_REACHED = "no_llega"
SENT = "enviada"
RECEIVED = "recibida"
OPENED = "abierta"
ENTERED = "entro"
STOPPED = "dejo"
CLOCKS = "ficha"
STATES = (
    (NOT_REACHED, "No le llega el WhatsApp", "danger"),
    (SENT, "Enviada, sin confirmar que la recibió", "secondary"),
    (RECEIVED, "Recibida, no la ha abierto", "warning"),
    (OPENED, "La abrió, no ha entrado ni fichado", "warning"),
    (ENTERED, "Entró en el panel, no ha fichado", "danger"),
    (STOPPED, "Fichó, pero lleva días sin fichar", "info"),
    (CLOCKS, "Ficha", "success"),
)
STATE_LABELS = {key: label for key, label, _badge in STATES}
STATE_BADGES = {key: badge for key, _label, badge in STATES}
# Sin fichar desde hace más de esto (días), quien ya fichó "dejó".
STOPPED_DAYS = 3

WHATSAPP_LABELS = {
    "": "Sin dato", "accepted": "Enviada", "queued": "Enviada",
    "sending": "Enviada", "sent": "Enviada", "delivered": "Entregada",
    "read": "Leída en WhatsApp", "failed": "Fallida",
    "undelivered": "No entregada",
}


def _sent_at(ack):
    """When a send went out (its record; the date if it is older)."""
    if ack.created_at:
        return ack.created_at
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.datetime.combine(
        ack.delivery_date, datetime.time.min), tz)


def build_rows(company):
    """
    The report rows of the company, worst situation first.
    ---
    Las filas del informe de la empresa (dicts), primero la peor
    situación y, dentro, quien más días lleva sin fichar.
    """
    from document_explorer.models import DocumentAcknowledgment
    from document_explorer.person_phone_service import mobile_of
    from hr_calendar.clock_settings import current_sections
    from hr_calendar.models import ClockEvent, WorkerClockSetting

    acks = {}
    for ack in DocumentAcknowledgment.objects.filter(
        person__company=company, person__is_active_employee=True,
        document_type__code__in=ONBOARDING_CODES,
        channel=DocumentAcknowledgment.CHANNEL_WHATSAPP,
    ).select_related("person__company_user__user").order_by(
            "created_at", "pk"):
        acks.setdefault(ack.person_id, []).append(ack)
    if not acks:
        return []
    people = {sends[0].person_id: sends[0].person for sends in acks.values()}
    sections = current_sections(list(people))
    clocks = dict(WorkerClockSetting.objects.filter(
        person_id__in=list(people)).values_list("person_id", "clocks"))
    user_ids = [p.company_user_id for p in people.values()
                if p.company_user_id]
    first_press, last_press = {}, {}
    for user_id, pressed in ClockEvent.objects.current().filter(
        company_user_id__in=user_ids,
    ).order_by("pressed_at").values_list("company_user_id", "pressed_at"):
        first_press.setdefault(user_id, pressed)
        last_press[user_id] = pressed
    today = timezone.localdate()
    rows = []
    for person_id, sends in acks.items():
        person = people[person_id]
        first, last = sends[0], sends[-1]
        first_at, last_at = _sent_at(first), _sent_at(last)
        account = person.company_user
        user = account.user if account else None
        last_login = user.last_login if user else None
        last_clock = last_press.get(person.company_user_id)
        opened = min((a.whatsapp_read_at for a in sends
                      if a.whatsapp_read_at), default=None)
        # Recibida si le llegó cualquiera de los envíos; "no le llega"
        # solo si fallaron y ninguno le llegó.
        reached = [a.whatsapp_status for a in sends
                   if a.whatsapp_status in ("delivered", "read")]
        status = ("read" if "read" in reached else reached[0] if reached
                  else last.whatsapp_status or next(
                      (a.whatsapp_status for a in reversed(sends)
                       if a.whatsapp_status), ""))
        clocked_since_first = bool(last_clock and last_clock >= first_at)
        clocked_since_last = bool(last_clock and last_clock >= last_at)
        days_since_first = (None if clocked_since_first else
                            (today - timezone.localtime(first_at).date())
                            .days)
        days_since_resend = (
            None if len(sends) < 2 or clocked_since_last else
            (today - timezone.localtime(last_at).date()).days)
        days_since_clock = ((today - timezone.localtime(last_clock).date())
                            .days if last_clock else None)
        entered = bool(last_login and last_login >= first_at)
        if clocked_since_first:
            state = (STOPPED if days_since_clock is not None
                     and days_since_clock > STOPPED_DAYS else CLOCKS)
        elif entered:
            state = ENTERED
        elif opened:
            state = OPENED
        elif status in ("failed", "undelivered"):
            state = NOT_REACHED
        elif status in ("delivered", "read"):
            state = RECEIVED
        else:
            state = SENT
        section = sections.get(person_id)
        rows.append({
            "key": str(person_id),
            "person": person,
            "label": "%s, %s" % (" ".join(filter(None, (
                person.first_surname, person.second_surname))),
                person.given_name),
            "dni": person.dni,
            "section": section.name if section else "",
            "phone": mobile_of(person) or "",
            "username": user.username if user else "",
            "clocks": clocks.get(person_id),
            "sends": len(sends),
            "first_sent": timezone.localtime(first_at),
            "last_sent": timezone.localtime(last_at) if len(sends) > 1
            else None,
            "whatsapp": WHATSAPP_LABELS.get(status, status),  # el mejor
            "whatsapp_status": status,
            "whatsapp_at": (timezone.localtime(last.whatsapp_status_at)
                            if last.whatsapp_status_at else None),
            "opened": timezone.localtime(opened) if opened else None,
            "last_login": (timezone.localtime(last_login)
                           if last_login else None),
            "first_clock": (timezone.localtime(
                first_press[person.company_user_id])
                if person.company_user_id in first_press else None),
            "last_clock": (timezone.localtime(last_clock)
                           if last_clock else None),
            "days_since_first": days_since_first,
            "days_since_resend": days_since_resend,
            "days_since_clock": days_since_clock,
            "state": state,
            "state_label": STATE_LABELS[state],
            "state_badge": STATE_BADGES[state],
        })
    order = {key: i for i, (key, _l, _b) in enumerate(STATES)}
    rows.sort(key=lambda r: (
        order[r["state"]],
        -(r["days_since_resend"] if r["days_since_resend"] is not None
          else r["days_since_first"] if r["days_since_first"] is not None
          else r["days_since_clock"] or 0),
        r["label"]))
    return rows


def not_clocking(row):
    """Whether the row is someone who is not clocking in."""
    return row["state"] != CLOCKS
