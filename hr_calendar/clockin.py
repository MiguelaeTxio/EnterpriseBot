# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clockin.py
"""
Clock-in reception (H24, S129, roadmap point 3).

Miguel Ángel's decisions (annex V24, 7.4bis): presses come from the
worker's trusted device ("Los fichajes serán a través del dispositivo
de confianza"), without a bank-vault level of protection; a press made
without coverage is accepted later with the trusted-device key even if
the panel session has expired ("Claro, no?"); each press is stored
once by the id the phone gives it.

The trusted-device key is the signed HttpOnly cookie `eb_trusted_device`
(panel.views_auth.TrustDeviceView): {"uid": user pk, "tok": UUID}, valid
while it matches CompanyUser.trusted_device_token. The cookie is
SameSite=Lax, so a POST from another site never carries it -- that is
why the receive endpoint can be CSRF-exempt: a press queued offline is
sent later, possibly without a valid CSRF token.

---

Recepción de fichajes (H24, S129, punto 3 de la hoja de ruta).

Decisiones de Miguel Ángel (anexo V24, 7.4bis): las pulsaciones llegan
desde el dispositivo de confianza del trabajador ("Los fichajes serán a
través del dispositivo de confianza"), sin una protección de caja de
caudales; una pulsación hecha sin cobertura se acepta después con la
llave del dispositivo de confianza aunque la sesión del panel haya
caducado ("Claro, no?"); cada pulsación se guarda una sola vez por el
identificador que le da el móvil.

La llave del dispositivo de confianza es la cookie firmada HttpOnly
`eb_trusted_device` (panel.views_auth.TrustDeviceView): {"uid": pk del
usuario, "tok": UUID}, válida mientras coincida con
CompanyUser.trusted_device_token. La cookie es SameSite=Lax, así que un
POST desde otra web nunca la lleva -- por eso el endpoint de recepción
puede ir sin CSRF: una pulsación guardada sin cobertura se envía más
tarde, quizá sin un token CSRF válido.
"""
import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from hr_calendar.models import ClockEvent
from ivr_config.models import CompanyUser

logger = logging.getLogger(__name__)

TRUSTED_COOKIE = "eb_trusted_device"
TRUSTED_COOKIE_MAX_AGE = 365 * 24 * 3600
MAX_BODY = 4096

NO_TRUSTED_DEVICE = (
    "Este móvil no es tu dispositivo de confianza. Entra en el panel "
    "con tu usuario y contraseña y, cuando te pregunte, márcalo como "
    "dispositivo de confianza."
)


class ClockInError(ValueError):
    """
    A press that cannot be stored; the message is shown to the worker.
    ---
    Una pulsación que no se puede guardar; el mensaje se muestra al
    trabajador.
    """


@dataclass
class PressResult:
    """
    Outcome of storing one press.
    ---
    Resultado de guardar una pulsación.
    """

    event: ClockEvent
    created: bool


def trusted_device_user(request):
    """
    Returns the active CompanyUser that owns the trusted-device cookie
    of the request, or None. The panel session is not needed.
    ---
    Devuelve el CompanyUser activo dueño de la cookie de dispositivo de
    confianza de la petición, o None. No hace falta sesión del panel.
    """
    raw = request.COOKIES.get(TRUSTED_COOKIE, "")
    if not raw:
        return None
    try:
        payload = signing.loads(raw, max_age=TRUSTED_COOKIE_MAX_AGE)
    except signing.BadSignature:
        return None
    if not isinstance(payload, dict):
        return None
    company_user = (
        CompanyUser.objects.select_related("company", "user")
        .filter(user_id=payload.get("uid"), is_active=True)
        .first()
    )
    if (
        company_user is None
        or not company_user.user.is_active
        or company_user.trusted_device_token is None
        or str(company_user.trusted_device_token) != payload.get("tok")
    ):
        return None
    return company_user


def _coordinate(value, limit):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value)).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError):
        return None
    if abs(number) > limit:
        return None
    return number


def _accuracy(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return min(round(number), 2_000_000_000)


def _person_of(company_user):
    try:
        return company_user.person_identity
    except ObjectDoesNotExist:
        return None


def record_press(company_user, payload, user_agent=""):
    """
    Stores one press from the payload sent by the phone. The same
    `id` sent again returns the stored press (created=False) instead
    of a second record. Raises ClockInError when the press is invalid.
    ---
    Guarda una pulsación con los datos que envía el móvil. Si llega
    otra vez el mismo `id`, devuelve la ya guardada (created=False) en
    vez de crear un segundo registro. Lanza ClockInError si la
    pulsación no es válida.
    """
    client_id = str(payload.get("id") or "").strip()
    if not client_id or len(client_id) > 40:
        raise ClockInError("La pulsación no trae un identificador válido.")
    existing = ClockEvent.objects.filter(client_id=client_id).first()
    if existing is not None:
        if existing.company_user_id != company_user.pk:
            raise ClockInError("Esa pulsación pertenece a otro usuario.")
        return PressResult(existing, False)

    kind = str(payload.get("kind") or "").upper()
    if kind not in ClockEvent.Kind.values:
        raise ClockInError("Falta indicar si es entrada o salida.")
    pressed_at = parse_datetime(str(payload.get("pressed_at") or ""))
    if pressed_at is None or not timezone.is_aware(pressed_at):
        raise ClockInError("La pulsación no trae una hora válida.")
    sent_by = str(payload.get("sent_by") or "").upper()
    if sent_by not in ClockEvent.SentBy.values:
        sent_by = ClockEvent.SentBy.ONLINE

    latitude = _coordinate(payload.get("lat"), 90)
    longitude = _coordinate(payload.get("lon"), 180)
    accuracy = _accuracy(payload.get("accuracy"))
    if latitude is None or longitude is None:
        latitude = longitude = accuracy = None
    event = ClockEvent(
        company=company_user.company,
        company_user=company_user,
        person=_person_of(company_user),
        kind=kind,
        client_id=client_id,
        pressed_at=pressed_at,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy,
        gps_error=str(payload.get("gps_error") or "")[:120],
        sent_by=sent_by,
        user_agent=(user_agent or "")[:200],
    )
    try:
        with transaction.atomic():
            event.save()
    except IntegrityError:
        # Two sends of the same press at once (page and background).
        # Dos envíos de la misma pulsación a la vez (página y segundo
        # plano): gana el primero.
        existing = ClockEvent.objects.filter(client_id=client_id).first()
        if existing is None:
            raise
        return PressResult(existing, False)
    logger.info(
        "# [FICHAJE] %s usuario=#%d tipo=%s pulsado=%s retraso_s=%s "
        "envio=%s gps=%s",
        client_id, company_user.pk, kind, pressed_at.isoformat(),
        event.delay_seconds, sent_by,
        "si" if latitude is not None else (event.gps_error or "no"),
    )
    return PressResult(event, True)


def _event_json(event):
    return {
        "id": event.client_id,
        "kind": event.kind,
        "kind_label": event.get_kind_display(),
        "pressed_at": event.pressed_at.isoformat(),
        "received_at": event.received_at.isoformat(),
        "delay_seconds": event.delay_seconds,
    }


def _worker_name(company_user):
    person = _person_of(company_user)
    if person is not None:
        return f"{person.given_name} {person.first_surname}".strip()
    return company_user.user.get_full_name() or company_user.user.username


@csrf_exempt
@require_POST
def receive(request):
    """
    POST (JSON): one press from the trusted device. 200 with the stored
    press (also when it was already stored); 401 without a valid
    trusted-device key; 400 when the press is invalid. The phone keeps
    a press pending until it gets a 200.
    ---
    POST (JSON): una pulsación desde el dispositivo de confianza. 200
    con la pulsación guardada (también si ya lo estaba); 401 sin llave
    de dispositivo de confianza válida; 400 si la pulsación no es
    válida. El móvil la mantiene pendiente hasta recibir un 200.
    """
    company_user = trusted_device_user(request)
    if company_user is None:
        return JsonResponse(
            {"error": NO_TRUSTED_DEVICE, "code": "no_trusted_device"},
            status=401,
        )
    if len(request.body) > MAX_BODY:
        return JsonResponse({"error": "Petición demasiado grande."},
                            status=400)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Datos no válidos."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Datos no válidos."}, status=400)
    try:
        result = record_press(
            company_user, payload,
            request.META.get("HTTP_USER_AGENT", ""),
        )
    except ClockInError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    data = _event_json(result.event)
    data["duplicate"] = not result.created
    return JsonResponse(data)


@never_cache
@require_GET
def status(request):
    """
    GET (JSON): whose trusted device this is and the last press, so the
    clock-in page can greet the worker and suggest IN or OUT. 401
    without a valid trusted-device key.
    ---
    GET (JSON): de quién es este dispositivo de confianza y su última
    pulsación, para que la página de fichaje salude al trabajador y
    proponga entrada o salida. 401 sin llave de dispositivo de
    confianza válida.
    """
    company_user = trusted_device_user(request)
    if company_user is None:
        return JsonResponse(
            {"error": NO_TRUSTED_DEVICE, "code": "no_trusted_device"},
            status=401,
        )
    last = (
        ClockEvent.objects.filter(company_user=company_user)
        .order_by("-pressed_at").first()
    )
    return JsonResponse({
        "name": _worker_name(company_user),
        "company": company_user.company.name,
        "last": _event_json(last) if last is not None else None,
    })
