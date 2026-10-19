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
(panel/trusted_devices.py): {"uid": user pk, "tok": UUID}, valid while
its TrustedDevice row exists (several per user: phone and PC). The cookie is
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
`eb_trusted_device` (panel/trusted_devices.py): {"uid": pk del usuario,
"tok": UUID}, válida mientras exista su fila TrustedDevice (varias por
usuario: móvil y PC). La cookie es SameSite=Lax, así que un
POST desde otra web nunca la lleva -- por eso el endpoint de recepción
puede ir sin CSRF: una pulsación guardada sin cobertura se envía más
tarde, quizá sin un token CSRF válido.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from hr_calendar.models import ClockEvent

logger = logging.getLogger(__name__)

MAX_BODY = 4096
_SW_PATH = Path(__file__).resolve().parent / "static_src" / "clockin_sw.js"

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
    The active CompanyUser that owns the request's trusted device, or
    None. The panel session is not needed (panel/trusted_devices.py).
    ---
    El CompanyUser activo dueño del dispositivo de confianza de la
    petición, o None. No hace falta sesión del panel
    (panel/trusted_devices.py).
    """
    from panel.trusted_devices import device_owner

    return device_owner(request)


def _untrusted_response(request):
    """
    401 for a browser that is not a trusted device. When the user has
    an open panel session on it, the page offers to trust it right away
    (/panel/trust-device/?next=/fichaje/) instead of a new login.
    ---
    401 para un navegador que no es dispositivo de confianza. Si tiene
    la sesión del panel abierta, la página ofrece marcarlo en el acto
    (/panel/trust-device/?next=/fichaje/) en vez de volver a entrar.
    """
    logged_in = (
        request.user.is_authenticated
        and getattr(request.user, "company_user", None) is not None
    )
    return JsonResponse({
        "error": NO_TRUSTED_DEVICE,
        "code": "no_trusted_device",
        "logged_in": bool(logged_in),
    }, status=401)


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
    if event.latitude is not None:
        # H24 (S129): municipio de las coordenadas (clock_geocode). Un
        # fallo aquí nunca impide guardar el fichaje; lo que quede sin
        # consultar se rellena al abrirlo en la pestaña Fichajes.
        try:
            from hr_calendar.clock_geocode import fill_municipality
            fill_municipality(event)
        except Exception:
            logger.exception(
                "# [FICHAJE-MUNICIPIO] Error con el fichaje %s.", client_id,
            )
    if event.kind == ClockEvent.Kind.OUT:
        # H24 (S129): la salida ajusta el parte de ese día si ya estaba
        # hecho y lo cierra si cuadra (hr_calendar/clock_parts.py). Un
        # fallo aquí nunca impide guardar el fichaje.
        try:
            from hr_calendar.clock_parts import on_clock_out
            on_clock_out(event)
        except Exception:
            logger.exception(
                "# [FICHAJE-PARTE] Error ajustando el parte al fichaje %s.",
                client_id,
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
        return _untrusted_response(request)
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
        return _untrusted_response(request)
    last = (
        ClockEvent.objects.filter(company_user=company_user)
        .order_by("-pressed_at").first()
    )
    return JsonResponse({
        "name": _worker_name(company_user),
        "company": company_user.company.name,
        "last": _event_json(last) if last is not None else None,
    })


@never_cache
@require_GET
def page(request):
    """
    GET: the clock-in page, the same for everyone (the service worker
    keeps it for offline use); it asks /fichaje/estado/ who is pressing.
    ---
    GET: la página de fichaje, igual para todos (el service worker la
    guarda para usarla sin cobertura); pregunta a /fichaje/estado/ quién
    ficha.
    """
    return render(request, "hr_calendar/clockin.html")


@never_cache
@require_GET
def service_worker(request):
    """
    GET: the service worker, served inside /fichaje/ so its scope is
    exactly that path.
    ---
    GET: el service worker, servido dentro de /fichaje/ para que su
    ámbito sea exactamente esa ruta.
    """
    response = HttpResponse(
        _SW_PATH.read_text(encoding="utf-8"),
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/fichaje/"
    return response


@never_cache
@require_GET
def manifest(request):
    """
    GET: web app manifest, so the page can go on the home screen.
    ---
    GET: manifiesto, para poner la página en la pantalla de inicio como
    una app.
    """
    data = {
        "name": "Fichaje — Grupo Álvarez",
        "short_name": "Fichaje",
        "start_url": "/fichaje/",
        "scope": "/fichaje/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0d6efd",
        "orientation": "portrait",
        "icons": [
            {"src": "/static/panel/img/albaran_icon_192.png",
             "sizes": "192x192", "type": "image/png"},
            {"src": "/static/panel/img/albaran_icon_512.png",
             "sizes": "512x512", "type": "image/png"},
        ],
    }
    return HttpResponse(
        json.dumps(data, ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )


_RETIRED_TEST_SW = """
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (event) {
    event.waitUntil(caches.keys().then(function (keys) {
        return Promise.all(keys.filter(function (k) {
            return k.indexOf("fichaje-prueba-") === 0;
        }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.registration.unregister(); }));
});
"""


@never_cache
def retired_test_page(request):
    """
    GET /fichaje-prueba/: the S129 test is over; sends to /fichaje/.
    ---
    GET /fichaje-prueba/: la prueba de S129 ha terminado; lleva a
    /fichaje/.
    """
    return redirect("/fichaje/")


@never_cache
def retired_test_sw(request):
    """
    GET /fichaje-prueba/sw.js: a service worker that deletes the test
    copy and unregisters itself on the phones that installed the test.
    ---
    GET /fichaje-prueba/sw.js: un service worker que borra la copia de
    la prueba y se da de baja solo en los móviles que la instalaron.
    """
    return HttpResponse(
        _RETIRED_TEST_SW,
        content_type="application/javascript; charset=utf-8",
    )
