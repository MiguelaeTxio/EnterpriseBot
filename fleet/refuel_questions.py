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

S137, Miguel Ángel: el cuentakilómetros o el horómetro a veces está
roto y el chófer teclea ceros o cualquier cosa. Las dos plantillas
pasan a una versión 2 con un tercer botón, "Contador averiado": al
pulsarlo el vehículo queda marcado como averiado
(`GasoGesVehicle.meter_broken`), no se vuelve a preguntar por él y sus
repostajes no dan lectura hasta que alguien lo marque como reparado en
Repostajes. Las preguntas ya enviadas con la versión 1 siguen valiendo
(los botones tienen los mismos `id`).

S137, Miguel Ángel: al chófer hay que recordarle qué se anota en ese
vehículo, horas o kilómetros (regla del taller). La pregunta del dato
usa la plantilla v3 (lleva "las horas que marca el horómetro" o "los
kilómetros que marca el cuentakilómetros") en cuanto Meta la aprueba;
mientras, la v2. Al pulsar "No, lo corrijo" se le pide la unidad
concreta y por qué no encajaba (texto libre, ya dentro de la ventana de
24 horas); el número que escribe se comprueba igual, y si tampoco
encaja se le pide otra vez, salvo que repita el mismo (entonces se da
por bueno: lo ha comprobado).

S137, Miguel Ángel: los chóferes reciben el aviso y no saben por qué
está mal ("tiene que quedar claro que el operario sepa por qué"). Cada
pregunta del dato guarda el motivo en una frase para el chófer
(`question_reason`: kilómetros en lugar de horas, horas en lugar de
kilómetros, un número que baja o que sube más de lo posible, con la
lectura con la que se compara) y la plantilla v4 lo lleva en el
mensaje. Se usa en cuanto Meta la aprueba; mientras, la v3 o la v2 (y
el motivo se le dice al pulsar "No, lo corrijo"). Por los brazos (B)
no se pregunta el dato hasta tener la v4 (Miguel Ángel, S137).
Escribir AVERIADO vale como el botón "Contador averiado" (S137).

S137, Miguel Ángel: "cuesta mucho meter un número diferente". Se acepta
el número aunque venga con texto ("Tiene 1625 horas"), y sin haber
pulsado ningún botón; si no encaja se le dice por qué y basta con
contestar SÍ para darlo por bueno (`_value_text`).
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
from fleet.gasoges_rules import (
    MAX_CREDIBLE_HOURS,
    MIN_CREDIBLE_VALUE,
    elapsed_text,
    max_rise,
)
from fleet.gasoges_sync import accept_supply, build_readings
from fleet.models import GasoGesSupply, GasoGesVehicle, RefuelQuestion

logger = logging.getLogger(__name__)

VALUE_TEMPLATE = "refuel_value_check_v2"
VALUE_TEMPLATE_V3 = "refuel_value_check_v3"
VALUE_TEMPLATE_V4 = "refuel_value_check_v4"
UNIT_TEMPLATE = "refuel_unit_check_v2"
VALUE_OK = "refuel_value_ok"
VALUE_FIX = "refuel_value_fix"
UNIT_KM = "refuel_unit_km"
UNIT_HOURS = "refuel_unit_hours"
METER_BROKEN = "refuel_meter_broken"
BUTTONS = (VALUE_OK, VALUE_FIX, UNIT_KM, UNIT_HOURS, METER_BROKEN)

RECENT_HOURS = 48
ANSWER_HOURS = 24
UNIT_RETRY_DAYS = 7
SEND_FROM_HOUR = 8
SEND_UNTIL_HOUR = 21
MAX_PER_RUN = 20
APPROVAL_URL = "https://content.twilio.com/v1/Content/%s/ApprovalRequests"
UNIT_PHRASES = {
    GasoGesVehicle.UNIT_KM: "los kilómetros que marca el cuentakilómetros",
    GasoGesVehicle.UNIT_HOURS: "las horas que marca el horómetro",
}
UNIT_ASK = {
    GasoGesVehicle.UNIT_KM: "los KILÓMETROS que marca ahora el "
                            "cuentakilómetros",
    GasoGesVehicle.UNIT_HOURS: "las HORAS que marca ahora el horómetro",
}
# "AVERIADO", "averiado.", "está averiado": mensaje corto con la palabra.
_BROKEN_RE = re.compile(r"\baveriad[oa]s?\b", re.I)
_BROKEN_MAX_LEN = 60
_ANY_NUMBER_RE = re.compile(r"\d{1,3}(?:\.\d{3})+|\d+")
_TEXT_MAX_LEN = 80
# "Sí", "si, es correcto", "correcto", "eso es lo que marca", "está
# bien" (S137): el chófer confirma escribiendo en vez de pulsar.
_AFFIRMATIVE_RE = re.compile(
    r"^\s*(s[ií]\b|correcto|es correcto|est[aá] bien|(eso )?es lo que "
    r"marca)", re.I)
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


def _variables(question, template_name=""):
    """
    Template variables of a question.

    ---

    Variables de la plantilla: nombre, centro de gasto, fecha y hora
    del repostaje y lo que tecleó; con la v3 y la v4, qué hay que
    anotar en ese vehículo ({{5}}); con la v4, además, por qué no
    parece correcto ({{6}}, S137).
    """
    supply = question.supply
    vehicle = question.vehicle
    variables = {
        "1": question.person.given_name or "trabajador",
        "2": vehicle.machine.code if vehicle.machine else (
            vehicle.plate or vehicle.name),
        "3": timezone.localtime(supply.supplied_at).strftime(
            "%d/%m/%Y %H:%M"),
        "4": _format_value(supply.meter_value),
    }
    if template_name in (VALUE_TEMPLATE_V3, VALUE_TEMPLATE_V4):
        variables["5"] = UNIT_PHRASES.get(
            vehicle.unit, UNIT_PHRASES[GasoGesVehicle.UNIT_KM])
    if template_name == VALUE_TEMPLATE_V4:
        variables["6"] = question.reason
    return variables


def _references(supply):
    """
    Good readings of the same machine and unit to compare a value with.

    ---

    Lecturas buenas del mismo centro de gasto y unidad con las que
    comparar un número. S137: en un vehículo de horas no cuentan las de
    50.000 o más (ningún horómetro llega ahí: son kilómetros que se
    anotaron antes, como en los brazos); si no, las primeras horas de
    verdad que escriba el chófer saldrían "menos de lo que marcaba".
    """
    vehicle = supply.vehicle
    readings = GasoGesSupply.objects.filter(
        vehicle__machine_id=vehicle.machine_id, vehicle__unit=vehicle.unit,
        status=GasoGesSupply.STATUS_READING,
    ).exclude(pk=supply.pk)
    if vehicle.unit == GasoGesVehicle.UNIT_HOURS:
        readings = readings.filter(meter_value__lt=MAX_CREDIBLE_HOURS)
    return readings


def _previous_reading(supply):
    """
    (date, value) of the last good reading before this supply, or None.

    ---

    Fecha y valor de la última lectura buena del mismo centro de gasto
    y unidad anterior a este repostaje, o None.
    """
    return _references(supply).filter(
        supplied_at__lt=supply.supplied_at,
    ).order_by("-supplied_at").values_list(
        "supplied_at", "meter_value").first()


def _next_reading(supply):
    """
    (date, value) of the first good reading after this supply, or None.

    ---

    Fecha y valor de la primera lectura buena del mismo centro de gasto
    y unidad posterior a este repostaje, o None.
    """
    return _references(supply).filter(
        supplied_at__gt=supply.supplied_at,
    ).order_by("supplied_at").values_list(
        "supplied_at", "meter_value").first()


def _day(when):
    """
    "dd/mm" of a datetime, in local time.

    ---

    Día y mes de una fecha, en hora local.
    """
    return timezone.localtime(when).strftime("%d/%m")


def value_problem(supply, value):
    """
    Why a value does not fit the vehicle's readings ("" if it fits).

    ---

    Por qué un número no encaja con las lecturas del vehículo, en una
    frase que entienda el chófer ("" si encaja). S137, Miguel Ángel: el
    operario tiene que saber por qué se le pregunta: si ha puesto
    kilómetros en lugar de horas, horas en lugar de kilómetros, un
    número que baja o uno que sube más de lo posible. Siempre con la
    lectura de referencia (fecha y valor) para que la compare.
    """
    if value is None:
        return ""
    hours = supply.vehicle.unit == GasoGesVehicle.UNIT_HOURS
    word = "horas" if hours else "km"
    meter = "el horómetro" if hours else "el cuentakilómetros"
    if not value:
        return "es 0 o está vacío"
    if value < MIN_CREDIBLE_VALUE:
        return "%s es demasiado poco para %s de este vehículo" % (
            _format_value(value), meter)
    if hours and value >= MAX_CREDIBLE_HOURS:
        return ("%s horas es más de lo que marca ningún horómetro: "
                "parecen kilómetros, y este vehículo va por horas"
                % _format_value(value))
    previous = _previous_reading(supply)
    if previous is not None:
        when, last = previous
        if value < last:
            if not hours and value * 5 < last:
                return ("parecen horas, y este vehículo va por "
                        "kilómetros: el %s marcaba %s km"
                        % (_day(when), _format_value(last)))
            return ("es menos de lo que marcaba el %s (%s %s), y %s no "
                    "puede bajar" % (_day(when), _format_value(last), word,
                                     meter))
        # S154, Miguel Ángel: no más horas de las que han pasado; un
        # camión o una grúa, no más de 100 km por hora.
        family = supply.vehicle.machine.family if (
            supply.vehicle.machine_id) else ""
        if value - last > max_rise(supply.vehicle.unit, when,
                                   supply.supplied_at, family):
            elapsed = elapsed_text(when, supply.supplied_at)
            if hours:
                return ("son %s horas más que el %s (%s) y solo han "
                        "pasado %s" % (_format_value(value - last),
                                       _day(when), _format_value(last),
                                       elapsed))
            return ("son %s km más que el %s (%s) en %s, y no da tiempo "
                    "a recorrerlos"
                    % (_format_value(value - last), _day(when),
                       _format_value(last), elapsed))
    following = _next_reading(supply)
    if following is not None and value > following[1]:
        return ("es más de lo que marcó después, el %s (%s %s)"
                % (_day(following[0]), _format_value(following[1]), word))
    return ""


def question_reason(supply):
    """
    Why a doubtful supply is asked about, for the driver (never empty).

    ---

    Por qué se le pregunta al chófer por un repostaje dudoso, en una
    frase (nunca vacía): la de `value_problem` o, si no hay lectura con
    la que compararlo, que no encaja con el resto.
    """
    return (value_problem(supply, supply.meter_value)
            or "no encaja con el resto de lecturas del vehículo")


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
        vehicle__ask_driver=True, vehicle__meter_broken=False,
        user__ask_driver=True, user__person__isnull=False,
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
            # S163 (23/11, Miguel Ángel: "si estás metiendo bien, no hay
            # que enviar ningún mensaje"): solo se pregunta si se le
            # puede decir al chófer por qué no encaja con las lecturas
            # buenas; sin motivo concreto, no se le molesta.
            if not value_problem(supply, supply.meter_value):
                continue
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
                "sin_movil": 0, "esperan": 0, "brazos": 0}
    hour = timezone.localtime().hour
    if not SEND_FROM_HOUR <= hour < SEND_UNTIL_HOUR:
        log("Preguntas de repostajes: fuera de horario (8:00-21:00).")
        return counters
    sender = os.environ.get("TWILIO_WHATSAPP_SENDER", "")
    # S137: la v4 del dato (dice por qué no encaja y si son horas o km)
    # en cuanto esté aprobada; si no, la v3 (solo horas o km); si no, v2.
    value_template = next((
        template for template in (
            _template(company, VALUE_TEMPLATE_V4),
            _template(company, VALUE_TEMPLATE_V3),
            _template(company, VALUE_TEMPLATE))
        if template and template_approved(template.content_sid)), None)
    unit_template = _template(company, UNIT_TEMPLATE)
    if unit_template and not template_approved(unit_template.content_sid):
        unit_template = None
    templates = {
        RefuelQuestion.KIND_VALUE: value_template,
        RefuelQuestion.KIND_UNIT: unit_template,
    }
    approved = {kind: t is not None for kind, t in templates.items()}
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
        # S137, Miguel Ángel: a los brazos (B) se les pregunta el dato
        # cuando esté aprobada la v4, que dice por qué no encaja. Solo a
        # los de horas: los B de asistencia van por km y se les pregunta
        # como a cualquiera.
        if (kind == RefuelQuestion.KIND_VALUE
                and templates[kind].name != VALUE_TEMPLATE_V4
                and supply.vehicle.unit == GasoGesVehicle.UNIT_HOURS
                and supply.vehicle.machine.code.upper().startswith("B")):
            counters["brazos"] += 1
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
            person=person, phone=phone,
            reason=(question_reason(supply)[:255]
                    if kind == RefuelQuestion.KIND_VALUE else ""))
        try:
            message = send_notification(
                client, sender, company, phone,
                templates[kind].content_sid, _variables(
                    question, templates[kind].name))
        except Exception as exc:  # Twilio: se apunta y se sigue.
            log("ERROR enviando pregunta a %s: %s" % (phone, exc))
            continue
        question.message_sid = getattr(message, "sid", "") or ""
        question.save()
        busy.add(person.pk)
        counters["enviadas"] += 1
    log("Preguntas de repostajes: %(enviadas)d enviadas, %(esperan)d "
        "esperan a que el chófer conteste otra, %(sin_movil)d sin móvil, "
        "%(brazos)d de brazos esperan a la v4, %(caducadas)d caducadas."
        % counters)
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


def _mark_meter_broken(question, answer):
    """
    Mark the question's vehicle meter as broken; return the reply.

    ---

    Marca como averiado el contador del vehículo de la pregunta (botón
    "Contador averiado" o la palabra AVERIADO escrita) y devuelve la
    respuesta para el chófer.
    """
    vehicle = question.vehicle
    vehicle.meter_broken = True
    vehicle.meter_broken_since = question.supply.supplied_at
    vehicle.save(update_fields=[
        "meter_broken", "meter_broken_since", "updated_at"])
    question.status = RefuelQuestion.STATUS_METER_BROKEN
    question.answer = answer[:255]
    question.answered_at = timezone.now()
    question.save(update_fields=["status", "answer", "answered_at"])
    build_readings(lambda _line: None, vehicle=vehicle)
    return ("Gracias, queda anotado que el contador está averiado. No "
            "te volveremos a preguntar por este vehículo hasta que se "
            "repare.")


def _extract_number(text):
    """
    The only number written in a short message, or None.

    ---

    El único número de un mensaje corto ("1625", "1.625", "Tiene 1625
    horas", "1625horas"), o None si no hay ninguno o hay varios (S137:
    los chóferes no escriben solo el número).
    """
    if not text or len(text) > _TEXT_MAX_LEN:
        return None
    exact = _parse_number(text)
    if exact is not None:
        return exact
    numbers = _ANY_NUMBER_RE.findall(text)
    if len(numbers) != 1:
        return None
    return int(re.sub(r"[.\s]", "", numbers[0]))


def _km_in_hours_reply(question, answer):
    """
    Reply for a "yes, correct" to kilometres in an hours vehicle.

    ---

    S137, Miguel Ángel: a quien dice que es correcto un número que
    parecen kilómetros en un vehículo de horas no se le da por bueno:
    se le explica que van horas por la revisión, que el valor sigue mal
    y qué tiene que escribir. Devuelve la respuesta, o "" si no es el
    caso (y entonces el "sí" vale).
    """
    supply = question.supply
    if supply.vehicle.unit != GasoGesVehicle.UNIT_HOURS or (
            "parecen kilómetros" not in value_problem(
                supply, supply.meter_value)):
        return ""
    question.status = RefuelQuestion.STATUS_AWAITING_VALUE
    question.answer = answer[:255]
    question.answered_at = timezone.now()
    question.save(update_fields=["status", "answer", "answered_at"])
    code = supply.vehicle.machine.code if supply.vehicle.machine else (
        "este vehículo")
    return ("%s no es correcto: son kilómetros, y en %s hay que anotar "
            "las HORAS que marca el horómetro. Es por la revisión: el "
            "cambio de aceite y filtros toca por horas (cada 800 o 1.200), "
            "y con los kilómetros no sabemos cuándo le toca. Escribe "
            "ahora las horas que marca el horómetro, por ejemplo 1625. Si "
            "el horómetro está averiado, escribe AVERIADO."
            % (_format_value(supply.meter_value), code))


def _value_text(question, body):
    """
    Process a written answer to a value question; return the reply.

    ---

    Procesa lo que escribe el chófer a una pregunta del dato (haya
    pulsado "No, lo corrijo" o no). S137, Miguel Ángel: "cuesta mucho
    meter un número diferente". Ahora:
    - Un número, aunque venga con texto: si encaja, queda anotado; si
      no, se le dice por qué y que si es lo que marca conteste SÍ (o
      lo repita).
    - "Sí", "es correcto", "eso es lo que marca": si antes escribió un
      número que no encajaba, se da por bueno ese número (lo ha
      comprobado); si no había escrito ninguno, vale como el botón
      "Sí, es correcto".
    - Otra cosa: se le explica qué escribir, con un ejemplo.
    """
    supply = question.supply
    unit_ask = UNIT_ASK.get(supply.vehicle.unit,
                            "el número que marca el vehículo")
    meter = ("el horómetro" if supply.vehicle.unit ==
             GasoGesVehicle.UNIT_HOURS else "el cuentakilómetros")
    value = _extract_number(body)
    previous = _extract_number(question.answer)
    if value is None and _AFFIRMATIVE_RE.search(body) and previous is None:
        km_reply = _km_in_hours_reply(question, body.strip())
        if km_reply:
            return km_reply
    if value is None and _AFFIRMATIVE_RE.search(body):
        question.answered_at = timezone.now()
        if previous is not None:
            question.status = RefuelQuestion.STATUS_CORRECTED
            question.answer = ("%s (confirmado: %s)" % (
                _format_value(previous), body.strip()))[:255]
            question.save(update_fields=["status", "answer", "answered_at"])
            accept_supply(supply, "corregido por el chófer", previous)
            return "Gracias, queda anotado %s." % _format_value(previous)
        question.status = RefuelQuestion.STATUS_CONFIRMED
        question.answer = body.strip()[:255]
        question.save(update_fields=["status", "answer", "answered_at"])
        accept_supply(supply, "confirmado por el chófer")
        return "Gracias, queda anotado como correcto."
    if value is None:
        return ("No lo he entendido. Escribe solo %s, por ejemplo 1625. "
                "Si es correcto %s, contesta SÍ. Si %s está averiado, "
                "escribe AVERIADO." % (
                    unit_ask, "el número que escribiste (%s)" % (
                        _format_value(previous)) if previous is not None
                    else "lo que anotaste", meter))
    problem = value_problem(supply, value)
    if problem and previous != value:
        # Se guarda lo que escribió: si lo repite o dice que sí, se da
        # por bueno.
        question.status = RefuelQuestion.STATUS_AWAITING_VALUE
        question.answer = body.strip()[:255]
        question.save(update_fields=["status", "answer"])
        return ("%s no parece correcto: %s. Si es lo que marca %s, "
                "contesta SÍ. Si no, escribe el número bueno."
                % (_format_value(value), problem, meter))
    question.status = RefuelQuestion.STATUS_CORRECTED
    question.answer = body.strip()[:255]
    question.answered_at = timezone.now()
    question.save(update_fields=["status", "answer", "answered_at"])
    accept_supply(supply, "corregido por el chófer", value)
    return "Gracias, queda anotado %s." % _format_value(value)


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
        # S137, Miguel Ángel: si el horómetro o el cuentakilómetros está
        # mal, el chófer lo indica escribiendo AVERIADO (el aviso de
        # notify_wrong_confirmations se lo dice), para no recibir más
        # mensajes por ese vehículo. Vale para su última pregunta de las
        # últimas 48 horas, contestada o no.
        if body and len(body) <= _BROKEN_MAX_LEN and _BROKEN_RE.search(
                body):
            person = resolve_person_by_phone(company, phone)
            recent = person and RefuelQuestion.objects.filter(
                person=person, sent_at__gte=timezone.now() - timedelta(
                    hours=RECENT_HOURS),
            ).select_related("supply", "vehicle").order_by(
                "-sent_at").first()
            if recent:
                return _mark_meter_broken(recent, body.strip())
        if not body:
            return None
        person = resolve_person_by_phone(company, phone)
        if not person:
            return None
        awaiting = RefuelQuestion.objects.filter(
            person=person, status=RefuelQuestion.STATUS_AWAITING_VALUE,
        ).select_related("supply__vehicle").order_by("-sent_at").first()
        if awaiting:
            return _value_text(awaiting, body)
        # S137, Miguel Ángel: muchos no pulsan el botón y escriben
        # directamente ("Tiene 1625 horas", "Eso es lo que marca"). Con
        # una pregunta del dato abierta, un número o un "sí, es correcto"
        # escrito vale como respuesta; lo demás sigue al chatbot.
        open_question = RefuelQuestion.objects.filter(
            person=person, status=RefuelQuestion.STATUS_SENT,
            kind=RefuelQuestion.KIND_VALUE,
            sent_at__gte=timezone.now() - timedelta(hours=ANSWER_HOURS),
        ).select_related("supply__vehicle").order_by("-sent_at").first()
        if open_question and (_extract_number(body) is not None
                              or _AFFIRMATIVE_RE.search(body)):
            return _value_text(open_question, body)
        return None

    person = resolve_person_by_phone(company, phone)
    questions = RefuelQuestion.objects.filter(
        person=person, status=RefuelQuestion.STATUS_SENT)
    # "Contador averiado" está en las dos plantillas: vale para la
    # pregunta abierta del chófer, sea cual sea (solo hay una a la vez).
    # ---
    # "Broken meter" is in both templates: any open question.
    if button_payload != METER_BROKEN:
        questions = questions.filter(kind=(
            RefuelQuestion.KIND_UNIT if button_payload in (
                UNIT_KM, UNIT_HOURS) else RefuelQuestion.KIND_VALUE))
    question = person and questions.select_related(
        "supply__vehicle").order_by("-sent_at").first()
    if not question:
        return ("Gracias. Esa pregunta ya estaba contestada o ha "
                "caducado; no hace falta hacer nada más.")
    question.answered_at = timezone.now()
    if button_payload == VALUE_OK:
        km_reply = _km_in_hours_reply(question, "Sí, es correcto")
        if km_reply:
            return km_reply
        question.status = RefuelQuestion.STATUS_CONFIRMED
        question.answer = "Sí, es correcto"
        question.save(update_fields=["status", "answer", "answered_at"])
        accept_supply(question.supply, "confirmado por el chófer")
        return "Gracias, queda anotado como correcto."
    if button_payload == VALUE_FIX:
        question.status = RefuelQuestion.STATUS_AWAITING_VALUE
        question.answer = "No, lo corrijo"
        question.save(update_fields=["status", "answer", "answered_at"])
        supply = question.supply
        unit_ask = UNIT_ASK.get(supply.vehicle.unit,
                                "el número que marca el vehículo")
        problem = value_problem(supply, supply.meter_value)
        return ("De acuerdo. Escribe solo %s del %s, por ejemplo 125400.%s"
                % (unit_ask,
                   supply.vehicle.machine.code if supply.vehicle.machine
                   else "vehículo",
                   " Lo que anotaste (%s) no parece correcto: %s." % (
                       _format_value(supply.meter_value), problem)
                   if problem else ""))
    if button_payload == METER_BROKEN:
        return _mark_meter_broken(question, "Contador averiado")
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
