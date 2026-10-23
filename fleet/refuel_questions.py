# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/refuel_questions.py
"""
H30 (S135). WhatsApp questions to the driver about a GasoGes supply:
choose, send and process the answer.

---

H30 (S135). Preguntas por WhatsApp al chófer sobre un repostaje de
GasoGes. Miguel Ángel: cuando una lectura no sea correcta, "por
WhatsApp, usando el robot [...] pregunte. Los datos que has
introducido son los correctos. Si no son los correctos, por favor,
responde [...] con los kilómetros correctos o las horas correctas".
Decidido con él en S135: dos plantillas con botones
(`refuel_value_check`, `refuel_unit_check`, ver
whatsapp/management/commands/create_refuel_check_whatsapp_templates.py).

Qué se pregunta (`send_pending_questions`, desde la tarea horaria):
- Unidad: vehículos con centro de gasto y sin saber si apuntan km u
  horas, con un repostaje de las últimas 48 horas. Una vez por
  vehículo (se repite solo si en 7 días nadie contestó).
- Dato: repostajes dudosos de las últimas 48 horas de vehículos con
  unidad conocida, una vez por repostaje.
Nunca por los vehículos marcados "no preguntar" (los que lleva siempre
la misma persona, S135). Solo a quien repostó, si tiene ficha y
móvil; una pregunta abierta por chófer a la vez (así la respuesta no
se confunde); de 8:00 a 21:00; y solo cuando Meta ha aprobado la
plantilla (se consulta a Twilio).

Respuestas (`handle_whatsapp_reply`, desde el webhook, antes que el
chatbot): los botones, y el número que escribe el chófer tras pulsar
"No, lo corrijo".
"""
import logging
import os
import re
from datetime import timedelta

import requests
from django.utils import timezone

from document_explorer.person_phone_service import (
    mobile_of,
    resolve_person_by_phone,
)
from fleet.gasoges_sync import accept_supply, build_readings
from fleet.models import GasoGesSupply, GasoGesVehicle, RefuelQuestion

logger = logging.getLogger(__name__)

VALUE_TEMPLATE = "refuel_value_check"
UNIT_TEMPLATE = "refuel_unit_check"
VALUE_OK = "refuel_value_ok"
VALUE_FIX = "refuel_value_fix"
UNIT_KM = "refuel_unit_km"
UNIT_HOURS = "refuel_unit_hours"
BUTTONS = (VALUE_OK, VALUE_FIX, UNIT_KM, UNIT_HOURS)

RECENT_HOURS = 48
ANSWER_HOURS = 24
UNIT_RETRY_DAYS = 7
SEND_FROM_HOUR = 8
SEND_UNTIL_HOUR = 21
MAX_PER_RUN = 20
APPROVAL_URL = "https://content.twilio.com/v1/Content/%s/ApprovalRequests"
_NUMBER_RE = re.compile(r"^\s*(\d{1,3}(?:[.\s]\d{3})+|\d+)\s*$")
OPEN_STATUSES = (RefuelQuestion.STATUS_SENT,
                 RefuelQuestion.STATUS_AWAITING_VALUE)


def _template(company, name):
    """
    The registered template, or None.

    ---

    La plantilla registrada en BD, o None.
    """
    from whatsapp.models import WhatsAppTemplate

    return WhatsAppTemplate.objects.filter(
        company=company, name=name).first()


def template_approved(content_sid):
    """
    True if Meta approved the template (asked to Twilio each time).

    ---

    True si Meta ha aprobado la plantilla. Se pregunta a Twilio
    (`whatsapp.status` de ApprovalRequests, verificado en línea en
    S135): mientras no esté aprobada, no se envía nada.
    """
    try:
        response = requests.get(
            APPROVAL_URL % content_sid,
            auth=(os.environ["TWILIO_API_KEY_SID"],
                  os.environ["TWILIO_API_KEY_SECRET"]),
            timeout=20,
        )
        status = response.json().get("whatsapp", {}).get("status")
    except (KeyError, ValueError, requests.RequestException) as exc:
        logger.warning("# [REPOSTAJES] Sin estado de %s: %s",
                       content_sid, exc)
        return False
    return status == "approved"


def _format_value(value):
    """
    "33.333" style thousands, as written in Spain.

    ---

    Con punto de miles, como se escribe en España.
    """
    return "{:,}".format(value).replace(",", ".") if value else "0"


def _variables(question):
    """
    Template variables of a question.

    ---

    Variables de la plantilla: nombre, centro de gasto, fecha y hora
    del repostaje y lo que tecleó.
    """
    supply = question.supply
    vehicle = question.vehicle
    return {
        "1": question.person.given_name or "trabajador",
        "2": vehicle.machine.code if vehicle.machine else (
            vehicle.plate or vehicle.name),
        "3": timezone.localtime(supply.supplied_at).strftime(
            "%d/%m/%Y %H:%M"),
        "4": _format_value(supply.meter_value),
    }


def _expire_old():
    """
    Close the questions nobody answered in time.

    ---

    Cierra las preguntas sin respuesta pasadas 24 horas.
    """
    limit = timezone.now() - timedelta(hours=ANSWER_HOURS)
    return RefuelQuestion.objects.filter(
        status__in=OPEN_STATUSES, sent_at__lt=limit,
    ).update(status=RefuelQuestion.STATUS_EXPIRED)


def _candidates():
    """
    (kind, supply) pairs worth asking, newest first.

    ---

    Parejas (tipo, repostaje) que merece la pena preguntar, de la más
    reciente a la más antigua.
    """
    since = timezone.now() - timedelta(hours=RECENT_HOURS)
    recent = GasoGesSupply.objects.filter(
        supplied_at__gte=since, vehicle__machine__isnull=False,
        vehicle__ask_driver=True, user__person__isnull=False,
    ).select_related("vehicle", "user__person").order_by("-supplied_at")
    asked_supplies = set(RefuelQuestion.objects.filter(
        supply__in=recent).values_list("supply_id", flat=True))
    unit_limit = timezone.now() - timedelta(days=UNIT_RETRY_DAYS)
    asked_units = set(RefuelQuestion.objects.filter(
        kind=RefuelQuestion.KIND_UNIT,
    ).exclude(
        status=RefuelQuestion.STATUS_EXPIRED, sent_at__lt=unit_limit,
    ).values_list("vehicle_id", flat=True))
    pairs = []
    for supply in recent:
        if supply.pk in asked_supplies:
            continue
        unit_unknown = supply.vehicle.unit == GasoGesVehicle.UNIT_UNKNOWN
        if unit_unknown and supply.meter_value and (
                supply.vehicle_id not in asked_units):
            pairs.append((RefuelQuestion.KIND_UNIT, supply))
            asked_units.add(supply.vehicle_id)
        elif not unit_unknown and (
                supply.status == GasoGesSupply.STATUS_ANOMALY):
            pairs.append((RefuelQuestion.KIND_VALUE, supply))
    # Primero las de unidad: una respuesta desbloquea todas las lecturas
    # de ese vehículo (S135).
    # ---
    # Unit questions first: one answer unlocks a whole vehicle.
    pairs.sort(key=lambda pair: pair[0] != RefuelQuestion.KIND_UNIT)
    return pairs


def send_pending_questions(company, log=logger.info):
    """
    Send the pending questions. Returns a counters dict.

    ---

    Envía las preguntas pendientes, con todas las condiciones del
    docstring del módulo. Devuelve los contadores.
    """
    from whatsapp.services import _build_twilio_client
    from whatsapp.window_service import send_notification

    counters = {"enviadas": 0, "caducadas": _expire_old(),
                "sin_movil": 0, "esperan": 0}
    hour = timezone.localtime().hour
    if not SEND_FROM_HOUR <= hour < SEND_UNTIL_HOUR:
        log("Preguntas de repostajes: fuera de horario (8:00-21:00).")
        return counters
    sender = os.environ.get("TWILIO_WHATSAPP_SENDER", "")
    templates = {
        RefuelQuestion.KIND_VALUE: _template(company, VALUE_TEMPLATE),
        RefuelQuestion.KIND_UNIT: _template(company, UNIT_TEMPLATE),
    }
    approved = {
        kind: bool(t and template_approved(t.content_sid))
        for kind, t in templates.items()}
    if not sender or not any(approved.values()):
        log("Preguntas de repostajes: plantillas sin aprobar todavía "
            "(o sin TWILIO_WHATSAPP_SENDER); no se envía nada.")
        return counters
    busy = set(RefuelQuestion.objects.filter(
        status__in=OPEN_STATUSES).values_list("person_id", flat=True))
    client = _build_twilio_client()
    for kind, supply in _candidates():
        if counters["enviadas"] >= MAX_PER_RUN:
            break
        if not approved[kind]:
            continue
        person = supply.user.person
        phone = mobile_of(person)
        if not phone:
            counters["sin_movil"] += 1
            continue
        if person.pk in busy:
            counters["esperan"] += 1
            continue
        question = RefuelQuestion(
            kind=kind, supply=supply, vehicle=supply.vehicle,
            person=person, phone=phone)
        try:
            message = send_notification(
                client, sender, company, phone,
                templates[kind].content_sid, _variables(question))
        except Exception as exc:  # Twilio: se apunta y se sigue.
            log("ERROR enviando pregunta a %s: %s" % (phone, exc))
            continue
        question.message_sid = getattr(message, "sid", "") or ""
        question.save()
        busy.add(person.pk)
        counters["enviadas"] += 1
    log("Preguntas de repostajes: %(enviadas)d enviadas, %(esperan)d "
        "esperan a que el chófer conteste otra, %(sin_movil)d sin móvil, "
        "%(caducadas)d caducadas." % counters)
    return counters


def _parse_number(text):
    """
    The number a driver writes ("100.004", "17500"), or None.

    ---

    El número que escribe el chófer ("100.004", "17 500", "17500"), o
    None si no es solo un número.
    """
    match = _NUMBER_RE.match(text or "")
    if not match:
        return None
    return int(re.sub(r"[.\s]", "", match.group(1)))


def handle_whatsapp_reply(company, phone, button_payload, body):
    """
    Process a driver's answer; return the reply text, or None.

    None means "not an answer to a refuel question": the message goes
    on to the normal flow.

    ---

    Procesa la respuesta del chófer y devuelve el texto a contestarle,
    o None si el mensaje no es una respuesta a una pregunta de
    repostaje (sigue el camino normal del webhook).
    """
    if button_payload not in BUTTONS:
        awaiting = None
        if body:
            person = resolve_person_by_phone(company, phone)
            awaiting = person and RefuelQuestion.objects.filter(
                person=person, status=RefuelQuestion.STATUS_AWAITING_VALUE,
            ).select_related("supply__vehicle").order_by("-sent_at").first()
        if not awaiting:
            return None
        value = _parse_number(body)
        if value is None:
            return ("No lo he entendido. Escribe solo el número correcto, "
                    "por ejemplo 125400.")
        awaiting.status = RefuelQuestion.STATUS_CORRECTED
        awaiting.answer = body[:255]
        awaiting.answered_at = timezone.now()
        awaiting.save(update_fields=["status", "answer", "answered_at"])
        accept_supply(awaiting.supply, "corregido por el chófer", value)
        return "Gracias, queda anotado %s." % _format_value(value)

    person = resolve_person_by_phone(company, phone)
    kind = (RefuelQuestion.KIND_UNIT if button_payload in (
        UNIT_KM, UNIT_HOURS) else RefuelQuestion.KIND_VALUE)
    question = person and RefuelQuestion.objects.filter(
        person=person, kind=kind, status=RefuelQuestion.STATUS_SENT,
    ).select_related("supply__vehicle").order_by("-sent_at").first()
    if not question:
        return ("Gracias. Esa pregunta ya estaba contestada o ha "
                "caducado; no hace falta hacer nada más.")
    question.answered_at = timezone.now()
    if button_payload == VALUE_OK:
        question.status = RefuelQuestion.STATUS_CONFIRMED
        question.answer = "Sí, es correcto"
        question.save(update_fields=["status", "answer", "answered_at"])
        accept_supply(question.supply, "confirmado por el chófer")
        return "Gracias, queda anotado como correcto."
    if button_payload == VALUE_FIX:
        question.status = RefuelQuestion.STATUS_AWAITING_VALUE
        question.answer = "No, lo corrijo"
        question.save(update_fields=["status", "answer", "answered_at"])
        return ("De acuerdo. Escribe solo el número correcto que marca "
                "el vehículo (kilómetros u horas), por ejemplo 125400.")
    unit = (GasoGesVehicle.UNIT_KM if button_payload == UNIT_KM
            else GasoGesVehicle.UNIT_HOURS)
    vehicle = question.vehicle
    vehicle.unit = unit
    vehicle.unit_source = GasoGesVehicle.UNIT_SOURCE_DRIVER
    vehicle.save(update_fields=["unit", "unit_source", "updated_at"])
    question.status = RefuelQuestion.STATUS_UNIT_SET
    question.answer = "Kilómetros" if unit == GasoGesVehicle.UNIT_KM else (
        "Horas")
    question.save(update_fields=["status", "answer", "answered_at"])
    build_readings(lambda _line: None, vehicle=vehicle)
    return "Gracias, queda anotado: %s." % question.answer.lower()
