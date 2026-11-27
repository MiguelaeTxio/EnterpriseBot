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
import datetime
import hashlib
import json
import logging
import re
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

from hr_calendar.clock_settings import active_types
from hr_calendar.clock_settings import default_type
from hr_calendar.clock_settings import meal_check
from hr_calendar.clock_settings import press_notes
from hr_calendar.clock_settings import uses_types
from hr_calendar.models import ClockEvent
from hr_calendar.models import ClockType

logger = logging.getLogger(__name__)

MAX_BODY = 4096
_SW_PATH = Path(__file__).resolve().parent / "static_src" / "clockin_sw.js"
_PAGE_PATH = (Path(__file__).resolve().parent / "templates" / "hr_calendar"
              / "clockin.html")
# S143 (Miguel Ángel): "que la propia aplicación les diga cuándo
# recargarla, porque haya un cambio en la misma". Versión de la app =
# huella de la página y del service worker: cambia sola con cada cambio
# desplegado. La página guardada en el móvil lleva la suya y la compara
# con la que da /fichaje/estado/; si no coinciden, avisa de recargar.
APP_VERSION = hashlib.md5(
    _PAGE_PATH.read_bytes() + _SW_PATH.read_bytes(),
).hexdigest()[:12]
# S143 (Miguel Ángel): "Vamos a eliminar el fichaje manual". Un olvido
# lo corrige el supervisor (ClockCorrection).
# S147 (Miguel Ángel): "Los PC los denegamos nosotros directamente
# diciendo que solo se permite fichar desde dispositivos móviles" (un
# ordenador no tiene GPS: salía "Sevilla" a 50 km de precisión).
MOBILE_AGENT = re.compile(r"Android|iPhone|iPad|iPod|Mobile", re.I)
NO_PC = "Solo se permite fichar desde dispositivos móviles."
# S147 (Miguel Ángel): "como ADIDAS": sin permiso de ubicación (o en un
# navegador sin ubicación) no se ficha. La página lo explica y ni lo
# envía; aquí se rechaza por si llega igual. Tiempo agotado o posición
# no disponible sí se admiten (el móvil tiene GPS y lo ha intentado).
# S147 (Miguel Ángel): "vigilar las dobles pulsaciones y los fichajes
# en tiempos breves para no duplicar fichajes" (hubo entrada, salida y
# entrada en 7 segundos). Entre dos fichajes del mismo trabajador tiene
# que haber al menos este margen; si no, el segundo no se admite.
MIN_GAP = datetime.timedelta(minutes=2)
TOO_SOON = (
    "Ya fichaste {kind} a las {time}. Para no duplicar fichajes tiene "
    "que pasar al menos 2 minutos entre un fichaje y el siguiente."
)
GPS_REQUIRED = ("permiso denegado", "este navegador no da ubicación")
GPS_BLOCKED = (
    "No se puede fichar sin dar permiso de ubicación a esta página. "
    "Dale permiso y vuelve a fichar; después de fichar puedes quitarlo. "
    "Si no lo consigues, contacta con los administradores del sistema."
)

NO_MANUAL = (
    "El fichaje manual ya no existe. Si se te olvidó fichar, díselo a tu "
    "responsable para que lo corrija."
)

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
    # S133: what an OUT did to the parte, for the worker ("" = nothing).
    # Lo que una salida hizo con el parte, para el trabajador.
    parte_notice: str = ""
    parte_ok: bool = True


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
    S130: with `auto` the server decides IN/OUT (single button). S143:
    no more manual presses from the phone (sent_by=MANUAL is refused).
    ---
    Guarda una pulsación con los datos que envía el móvil. Si llega
    otra vez el mismo `id`, devuelve la ya guardada (created=False) en
    vez de crear un segundo registro. Lanza ClockInError si la
    pulsación no es válida. S130: con `auto` decide el servidor si es
    entrada o salida (botón único). S143: el móvil ya no puede enviar
    fichajes manuales (sent_by=MANUAL se rechaza; uno guardado sin
    cobertura antes del cambio sale en el móvil como no válido).
    """
    client_id = str(payload.get("id") or "").strip()
    if not client_id or len(client_id) > 40:
        raise ClockInError("La pulsación no trae un identificador válido.")
    existing = ClockEvent.objects.filter(client_id=client_id).first()
    if existing is not None:
        if existing.company_user_id != company_user.pk:
            raise ClockInError("Esa pulsación pertenece a otro usuario.")
        return PressResult(existing, False)
    if not MOBILE_AGENT.search(user_agent or ""):
        raise ClockInError(NO_PC)

    pressed_at = parse_datetime(str(payload.get("pressed_at") or ""))
    if pressed_at is None or not timezone.is_aware(pressed_at):
        raise ClockInError("La pulsación no trae una hora válida.")
    if (_coordinate(payload.get("lat"), 90) is None
            and str(payload.get("gps_error") or "") in GPS_REQUIRED):
        raise ClockInError(GPS_BLOCKED)
    # S143: antes de su primer día de fichaje no se ficha.
    starts = _clocks_from(company_user)
    if starts is not None and timezone.localtime(pressed_at).date() < starts:
        raise ClockInError(starts_text(starts))
    sent_by = str(payload.get("sent_by") or "").upper()
    # S141: CORRECTION es solo de las correcciones del supervisor;
    # nunca la envía el móvil.
    if (sent_by not in ClockEvent.SentBy.values
            or sent_by == ClockEvent.SentBy.CORRECTION):
        sent_by = ClockEvent.SentBy.ONLINE
    if sent_by == ClockEvent.SentBy.MANUAL:
        raise ClockInError(NO_MANUAL)
    kind = str(payload.get("kind") or "").upper()
    # S130: botón único. Con `auto` (pulsado con cobertura y nada
    # pendiente en el móvil) el tipo lo decide aquí el servidor; sin
    # cobertura lo decidió el móvil y se respeta tal cual llega.
    auto = bool(payload.get("auto"))
    if not auto and kind not in ClockEvent.Kind.values:
        raise ClockInError("Falta indicar si es entrada o salida.")
    # S141: tipos de fichaje (secciones que fichan por tipos, como en
    # Sesame). Quien ficha con el botón único nunca lleva tipo.
    by_types = uses_types(company_user)
    clock_type = _clock_type_of(company_user, payload) if by_types else None
    if not auto and kind == ClockEvent.Kind.CHANGE and clock_type is None:
        raise ClockInError("Un cambio de tipo tiene que indicar el tipo.")
    latitude = _coordinate(payload.get("lat"), 90)
    longitude = _coordinate(payload.get("lon"), 180)
    accuracy = _accuracy(payload.get("accuracy"))
    if latitude is None or longitude is None:
        latitude = longitude = accuracy = None
    forgotten = None
    try:
        with transaction.atomic():
            # S147: una pulsación a la vez por trabajador (dos envíos
            # casi simultáneos no pasan los dos el control de abajo).
            type(company_user).objects.select_for_update().filter(
                pk=company_user.pk).first()
            # S149 (27/11, Alejandro García y Antonio Fontalba): la
            # página y el segundo plano envían la misma pulsación en el
            # mismo segundo; el segundo esperaba aquí al primero y luego
            # el control de 2 minutos lo rechazaba ("Ya fichaste...") por
            # su propia pulsación, y el móvil decía que no se había
            # fichado. Es la misma: se devuelve la ya guardada.
            existing = ClockEvent.objects.filter(client_id=client_id).first()
            if existing is not None:
                if existing.company_user_id != company_user.pk:
                    raise ClockInError(
                        "Esa pulsación pertenece a otro usuario.")
                return PressResult(existing, False)
            _reject_too_soon(company_user, pressed_at, clock_type)
            if auto:
                kind, forgotten = _decide_kind(company_user, pressed_at)
                # S141: con la jornada abierta, elegir un tipo es cambiar
                # de tipo; la salida llega sin tipo.
                if kind == ClockEvent.Kind.OUT and clock_type is not None:
                    kind = ClockEvent.Kind.CHANGE
            if kind == ClockEvent.Kind.OUT:
                clock_type = None
            elif by_types and clock_type is None:
                clock_type = default_type(company_user.company)
            event = _build_event(
                company_user, payload, client_id, kind, pressed_at,
                latitude, longitude, accuracy, sent_by, user_agent,
            )
            event.clock_type = clock_type
            # S144: desplazamiento con su vehículo (kilómetros al cerrar
            # el tramo, hr_calendar/clock_extras.py).
            event.own_vehicle = bool(
                payload.get("own_vehicle") and clock_type is not None
                and clock_type.role == ClockType.ROLE_TRAVEL
            )
            # S143: "No he parado para comer" (fichaje por tipos). S149:
            # también el botón único con la casilla (Plataformas).
            event.no_meal_break = bool(
                payload.get("no_meal_break")
                and (by_types or meal_check(company_user)))
            # S149 (Plataformas): comentario en la entrada y la salida.
            if not by_types and press_notes(company_user):
                event.worker_note = str(
                    payload.get("worker_note") or "").strip()[:255]
            # S149: salida fichada tarde con la hora real que indica.
            if kind == ClockEvent.Kind.OUT:
                _set_claim(event, company_user, payload)
            event.save()
    except IntegrityError:
        # Two sends of the same press at once (page and background).
        # Dos envíos de la misma pulsación a la vez (página y segundo
        # plano): gana el primero.
        existing = ClockEvent.objects.filter(client_id=client_id).first()
        if existing is None:
            raise
        return PressResult(existing, False)
    result = _after_save(event, company_user)
    if forgotten is not None:
        # S143: la entrada de hoy deja la jornada olvidada "sin salida".
        # S147: si su parte ya fichó esa salida, el aviso es el suyo.
        if not result.parte_notice.startswith("No fichaste la salida"):
            result.parte_notice = " ".join(filter(None, (
                forgotten_text(forgotten), result.parte_notice)))
        result.parte_ok = False
    return result


def _set_claim(event, company_user, payload):
    """
    The real exit time the worker says, when he clocks out late.
    ---
    S149 (Miguel Ángel): "se le olvida picar la salida [...] que pueda
    poner un mensaje diciendo hora real de salida". Se guarda junto a la
    salida (que queda a la hora en que se pulsó) para que el supervisor
    la aplique. Una hora que no cabe (no es anterior a la pulsación o no
    es posterior al fichaje anterior) no se guarda como hora, pero el
    mensaje sí, con lo que escribió.
    """
    raw = str(payload.get("claimed_at") or "").strip()
    note = str(payload.get("claim_note") or "").strip()
    if not raw and not note:
        return
    claimed = parse_datetime(raw) if raw else None
    if claimed is not None and timezone.is_naive(claimed):
        claimed = timezone.make_aware(claimed)
    previous = ClockEvent.objects.current().filter(
        company_user=company_user, pressed_at__lt=event.pressed_at,
    ).order_by("-pressed_at").values_list("pressed_at", flat=True).first()
    if claimed is not None and (
            claimed >= event.pressed_at
            or (previous is not None and claimed <= previous)):
        note = "(hora indicada no válida: %s) %s" % (
            timezone.localtime(claimed).strftime("%d/%m %H:%M"), note)
        claimed = None
    if claimed is None and raw and not note.startswith("(hora"):
        note = "(hora indicada ilegible: %s) %s" % (raw[:20], note)
    event.claimed_at = claimed
    event.claim_note = note.strip()[:255]


def _reject_too_soon(company_user, pressed_at, clock_type=None):
    """
    Refuse a press too close to another one of the same worker.
    ---
    Rechaza la pulsación si el trabajador tiene otra vigente a menos de
    MIN_GAP (antes o después: con pulsaciones guardadas sin cobertura
    pueden llegar desordenadas). Las correcciones del supervisor no
    cuentan. Elegir otro tipo justo después (entra con el de siempre y
    al momento elige el suyo) sí se admite: es cambiar de tipo, no
    repetir el fichaje.
    """
    near = ClockEvent.objects.current().filter(
        company_user=company_user,
        pressed_at__gt=pressed_at - MIN_GAP,
        pressed_at__lt=pressed_at + MIN_GAP,
    ).exclude(sent_by=ClockEvent.SentBy.CORRECTION).order_by(
        "-pressed_at").first()
    if near is not None and not (
            clock_type is not None and near.clock_type_id != clock_type.pk):
        raise ClockInError(TOO_SOON.format(
            kind={"IN": "la entrada", "OUT": "la salida"}.get(
                near.kind, "un cambio de tipo"),
            time=timezone.localtime(near.pressed_at).strftime("%H:%M:%S"),
        ))


def _clocks_from(company_user):
    """
    The first day the worker clocks (None: from now).
    ---
    El primer día en que ficha el trabajador (S143; None: desde ya).
    """
    from hr_calendar.models import WorkerClockSetting

    person = _person_of(company_user)
    if person is None:
        return None
    return WorkerClockSetting.objects.filter(person=person).values_list(
        "clocks_from", flat=True).first()


def starts_text(day):
    """
    "Empiezas a fichar el viernes 06/11." for the worker.
    ---
    El aviso al trabajador de cuándo empieza a fichar (S143).
    """
    days = ("lunes", "martes", "miércoles", "jueves", "viernes",
            "sábado", "domingo")
    return "Empiezas a fichar el %s %s. Hasta entonces no hace falta " \
        "fichar." % (days[day.weekday()], day.strftime("%d/%m"))


def forgotten_text(opening):
    """
    The notice of a forgotten clock-out, for the worker.
    ---
    El aviso al trabajador de una salida que no fichó (S143): "No
    fichaste la salida del miércoles 04/11 (entrada 07:55). Tu
    responsable la corregirá."
    """
    days = ("lunes", "martes", "miércoles", "jueves", "viernes",
            "sábado", "domingo")
    opened = timezone.localtime(opening.pressed_at)
    return (
        "No fichaste la salida del %s %s (entrada %s). Tu responsable la "
        "corregirá." % (days[opened.weekday()], opened.strftime("%d/%m"),
                        opened.strftime("%H:%M"))
    )


def _clock_type_of(company_user, payload):
    """
    The active ClockType of the user's company named in the payload
    (`clock_type`, its id), or None when it does not come. Raises
    ClockInError when it is not one of them.
    ---
    El tipo de fichaje activo de la empresa del usuario que indica la
    pulsación (`clock_type`, su id), o None si no viene. Lanza
    ClockInError si no es uno de ellos.
    """
    value = payload.get("clock_type")
    if value in (None, ""):
        return None
    try:
        pk = int(value)
    except (TypeError, ValueError):
        raise ClockInError("El tipo de fichaje no es válido.")
    clock_type = ClockType.objects.filter(
        pk=pk, company=company_user.company, is_active=True,
    ).first()
    if clock_type is None:
        raise ClockInError(
            "Ese tipo de fichaje ya no está disponible. Vuelve a abrir la "
            "página de fichaje."
        )
    return clock_type


def _decide_kind(company_user, pressed_at):
    """
    (IN or OUT, forgotten opening) for an `auto` press
    (clock_report.next_kind against the user's last press before it).
    The user's row is locked so two presses at once do not both read
    the same last press.
    ---
    (ENTRADA o SALIDA, entrada olvidada) para una pulsación `auto`
    (clock_report.next_kind con la última pulsación del usuario anterior
    a ella). Se bloquea la fila del usuario para que dos pulsaciones a
    la vez no lean la misma última pulsación. S143: si es ENTRADA porque
    la jornada abierta se da por olvidada, su entrada; si no, None.
    """
    from ivr_config.models import CompanyUser
    from hr_calendar.clock_report import next_kind
    from hr_calendar.clock_report import open_shift_opening

    CompanyUser.objects.select_for_update().filter(
        pk=company_user.pk,
    ).first()
    last = (
        ClockEvent.objects.current().filter(
            company_user=company_user, pressed_at__lte=pressed_at,
        ).order_by("-pressed_at", "-pk").first()
    )
    kind = next_kind(last, pressed_at, company_user)
    if kind == ClockEvent.Kind.IN and last is not None and last.kind in (
            ClockEvent.Kind.IN, ClockEvent.Kind.CHANGE):
        # Una entrada con la jornada abierta: la anterior queda sin
        # salida (por el olvido de S143 o por las 24 horas).
        return kind, open_shift_opening(company_user, last)
    return kind, None


def _build_event(company_user, payload, client_id, kind, pressed_at,
                 latitude, longitude, accuracy, sent_by, user_agent):
    """
    The unsaved ClockEvent of one press.
    ---
    El ClockEvent, sin guardar, de una pulsación.
    """
    gps_error = str(payload.get("gps_error") or "")[:120]
    if sent_by == ClockEvent.SentBy.MANUAL:
        gps_error = "Fichaje manual"
    return ClockEvent(
        company=company_user.company,
        company_user=company_user,
        person=_person_of(company_user),
        kind=kind,
        client_id=client_id,
        pressed_at=pressed_at,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy,
        gps_error=gps_error,
        sent_by=sent_by,
        user_agent=(user_agent or "")[:200],
    )


def _after_save(event, company_user):
    """
    Log line, municipality and clock-out effects on the work order of a
    press just stored.
    ---
    Línea de log, municipio y efectos de la salida sobre el parte de una
    pulsación recién guardada.
    """
    client_id = event.client_id
    logger.info(
        "# [FICHAJE] %s usuario=#%d tipo=%s pulsado=%s retraso_s=%s "
        "envio=%s gps=%s",
        client_id, company_user.pk, event.kind,
        event.pressed_at.isoformat(), event.delay_seconds, event.sent_by,
        "si" if event.latitude is not None else (event.gps_error or "no"),
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
    # S144: si la pulsación cierra un tramo con vehículo propio, sus
    # kilómetros (nunca impide guardar el fichaje).
    try:
        from hr_calendar.clock_extras import on_press
        on_press(event)
    except Exception:
        logger.exception(
            "# [FICHAJE-KM] Error con el fichaje %s.", client_id,
        )
    outcome = None
    # S147: también la entrada normal (la vuelta de la comida fichada).
    if event.kind in (ClockEvent.Kind.OUT, ClockEvent.Kind.IN):
        # H24 (S129): la salida ajusta el parte de ese día si ya estaba
        # hecho y lo cierra si cuadra (hr_calendar/clock_parts.py). S130:
        # una entrada manual apuntada después de la salida vuelve a
        # mirar ese parte (clock_parts.on_clock_press). Un fallo aquí
        # nunca impide guardar el fichaje.
        try:
            from hr_calendar.clock_parts import on_clock_press
            outcome = on_clock_press(event)
        except Exception:
            logger.exception(
                "# [FICHAJE-PARTE] Error ajustando el parte al fichaje %s.",
                client_id,
            )
    if outcome is None:
        return PressResult(event, True)
    return PressResult(event, True, outcome.notice, outcome.ok)


def _event_json(event):
    return {
        "id": event.client_id,
        "kind": event.kind,
        "kind_label": event.get_kind_display(),
        "pressed_at": event.pressed_at.isoformat(),
        "received_at": event.received_at.isoformat(),
        "delay_seconds": event.delay_seconds,
        "manual": event.sent_by == ClockEvent.SentBy.MANUAL,
        # S141: tipo de fichaje del tramo que abre (o None).
        "clock_type": event.clock_type_id,
        "clock_type_name": (event.clock_type.name
                            + (" con mi vehículo" if event.own_vehicle
                               else "")
                            if event.clock_type_id else ""),
    }


def _type_json(clock_type):
    return {
        "id": clock_type.pk,
        "name": clock_type.name,
        "icon": clock_type.icon,
        "is_default": clock_type.is_default,
        "role": clock_type.role,
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
    data["parte_notice"] = result.parte_notice
    data["parte_ok"] = result.parte_ok
    return JsonResponse(data)


@csrf_exempt
@require_POST
def attempt(request):
    """
    POST (JSON): a press the page did not save, with why. 200 also when
    it was already stored (the phone retries until it gets a 200).
    ---
    POST (JSON): un intento de fichar que la página no guardó, con el
    motivo (S149, Antonio Fontalba: "no lo dejó"). 200 también si ya
    estaba guardado: el móvil lo reintenta hasta recibir un 200.
    """
    from hr_calendar.models import ClockAttempt

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
    client_id = str(payload.get("id") or "")[:64]
    attempted_at = parse_datetime(str(payload.get("attempted_at") or ""))
    reason = str(payload.get("reason") or "")
    if (not client_id or attempted_at is None
            or reason not in ClockAttempt.Reason.values):
        return JsonResponse({"error": "Datos no válidos."}, status=400)
    if timezone.is_naive(attempted_at):
        attempted_at = timezone.make_aware(attempted_at)
    ClockAttempt.objects.get_or_create(
        client_id=client_id,
        defaults={
            "company_user": company_user,
            "attempted_at": attempted_at,
            "reason": reason,
            "kind": str(payload.get("kind") or "")[:4],
            "message": str(payload.get("message") or "")[:500],
            "screen": str(payload.get("screen") or "")[:500],
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
        },
    )
    return JsonResponse({"ok": True})


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
    from hr_calendar.clock_report import MAX_SHIFT_HOURS, next_kind
    from hr_calendar.clock_report import forgotten_after
    from hr_calendar.clock_report import open_shift_opening

    now = timezone.now()
    last = (
        ClockEvent.objects.current().filter(
            company_user=company_user, pressed_at__lte=now,
        ).select_related("clock_type").order_by("-pressed_at", "-pk").first()
    )
    # S143: desde cuándo la jornada abierta se da por olvidada (para que
    # el móvil decida igual sin cobertura) y, si ya lo está, el aviso.
    # La página lo enseña en cuanto llega `forgotten_after`.
    opening = open_shift_opening(company_user, last)
    since = forgotten_after(company_user, opening)
    if opening is not None:
        # Sin horario, la regla de siempre: pasadas MAX_SHIFT_HOURS.
        limit = last.pressed_at + datetime.timedelta(hours=MAX_SHIFT_HOURS)
        since = min(since, limit) if since is not None else limit
    kind_now = next_kind(last, now, company_user)
    starts = _clocks_from(company_user)
    if starts is not None and timezone.localdate() >= starts:
        starts = None
    forgotten = forgotten_text(opening) if since is not None else ""
    # S141: quien ficha por tipos ve la lista de tipos activos.
    by_types = uses_types(company_user)
    types = active_types(company_user.company) if by_types else []
    # S130: lo que registrará el botón único ahora mismo, y el límite
    # de turno abierto para que el móvil decida igual sin cobertura.
    return JsonResponse({
        # S143: qué avisos recibe (los marca aquí) y la versión de la
        # app, para avisar de recargar si la del móvil es vieja.
        **_reminder_json(company_user),
        "app_version": APP_VERSION,
        "name": _worker_name(company_user),
        "company": company_user.company.name,
        "last": _event_json(last) if last is not None else None,
        "next_kind": kind_now,
        "forgotten_after": since.isoformat() if since else None,
        "forgotten": forgotten,
        "max_shift_hours": MAX_SHIFT_HOURS,
        # S143: antes de su primer día de fichaje, el aviso y sin botón.
        "starts_on": starts.isoformat() if starts else None,
        "starts_text": starts_text(starts) if starts else "",
        "uses_types": by_types,
        # S149: botón único con "No he parado para comer".
        "meal_check": by_types or meal_check(company_user),
        # S149 (Plataformas): comentario al fichar.
        "press_notes": not by_types and press_notes(company_user),
        "clock_types": [_type_json(t) for t in types],
        # H11 (S162): albaranes de grúa del trabajador.
        "crane_albaranes": _crane_albaranes_json(company_user),
    })


def _crane_albaranes_json(company_user):
    """
    Whether the worker sees "My albaranes" and how many are pending.
    ---
    H11 (S162): si el trabajador ve "Mis albaranes" en el fichaje (los
    gruistas y quien ya tenga alguno) y cuántos tiene sin firmar.
    """
    from crane_albaranes.models import CraneAlbaran
    from ivr_config.models import CompanyUser

    person = _person_of(company_user)
    if person is None:
        return {"show": False, "pending": 0}
    mine = CraneAlbaran.objects.filter(person=person).exclude(
        status=CraneAlbaran.Status.CANCELLED)
    pending = mine.filter(signed_at__isnull=True).count()
    show = (company_user.role == CompanyUser.ROLE_CRANE_OPERATOR
            or pending > 0 or mine.exists())
    return {"show": show, "pending": pending}


def _reminder_json(company_user):
    """
    Whether the worker gets reminders and which ones, with the choices.
    ---
    S143: si recibe avisos, cuáles ha marcado (o los de por defecto) y
    las opciones, para las casillas de la página.
    """
    from hr_calendar.models import WorkerClockSetting

    person = _person_of(company_user)
    setting = (WorkerClockSetting.objects.filter(person=person).first()
               if person is not None else None)
    choices = WorkerClockSetting

    def options(pairs):
        return [{"value": value, "label": label} for value, label in pairs]

    # S143: horario propio para los avisos, solo con horario abierto.
    from panel.views_operator import _resolve_base_schedule

    schedule = _resolve_base_schedule(company_user, company_user.company)
    shifts = setting.own_shifts() if setting else []
    return {
        "own_allowed": bool(schedule is not None and schedule.is_open),
        "own_shifts": [[a.strftime("%H:%M"), b.strftime("%H:%M")]
                       for a, b in shifts],
        "own_days": setting.own_days() if setting else [0, 1, 2, 3, 4],
        "own_until": (setting.own_schedule_until.isoformat()
                      if setting and setting.own_schedule_until else ""),
        "own_max": choices.MAX_OWN_SHIFTS,
        "reminders": bool(setting and setting.reminders),
        "in_reminders": (setting.in_reminder_keys() if setting
                         else list(choices.DEFAULT_IN_REMINDERS)),
        "out_reminders": (setting.out_reminder_keys() if setting
                          else list(choices.DEFAULT_OUT_REMINDERS)),
        "in_choices": options(choices.IN_REMINDER_CHOICES),
        "out_choices": options(choices.OUT_REMINDER_CHOICES),
    }


@csrf_exempt
@require_POST
def reminder_choices_view(request):
    """
    POST (JSON {"in": [...], "out": [...]}): this worker's reminders.
    ---
    POST (JSON {"in": [...], "out": [...]}): los avisos que marca este
    trabajador (S143, Miguel Ángel: "que puedan configurar sus avisos a
    la entrada y a la salida [...] con un casillero"). 401 sin
    dispositivo de confianza.
    """
    from hr_calendar.clock_settings import set_worker_reminders

    company_user = trusted_device_user(request)
    if company_user is None:
        return _untrusted_response(request)
    person = _person_of(company_user)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        in_keys, out_keys = payload.get("in"), payload.get("out")
        if (person is None or not isinstance(in_keys, list)
                or not isinstance(out_keys, list)):
            raise ValueError("datos")
        set_worker_reminders(person, in_keys, out_keys)
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
        return JsonResponse({"error": "No se ha podido guardar."},
                            status=400)
    return JsonResponse(_reminder_json(company_user))


@csrf_exempt
@require_POST
def own_schedule_view(request):
    """
    POST (JSON {"shifts": [[in, out]...], "days": [...], "until": ""}).
    ---
    POST: el horario propio para los avisos (S143, Miguel Ángel: con
    horario abierto "que puedan configurarse el horario temporal que
    vayan a tener"). Solo con horario abierto; 401 sin dispositivo de
    confianza.
    """
    from hr_calendar.clock_settings import set_worker_own_schedule

    company_user = trusted_device_user(request)
    if company_user is None:
        return _untrusted_response(request)
    person = _person_of(company_user)
    if person is None or not _reminder_json(company_user)["own_allowed"]:
        return JsonResponse(
            {"error": "Tu horario no es abierto: los avisos van con él."},
            status=400)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        shifts, days = payload.get("shifts"), payload.get("days")
        if not isinstance(shifts, list) or not isinstance(days, list):
            raise ValueError("No se ha podido guardar.")
        set_worker_own_schedule(person, shifts, days,
                                payload.get("until") or "")
    except (ValueError, TypeError, AttributeError,
            UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc) or "No se ha podido "
                             "guardar."}, status=400)
    return JsonResponse(_reminder_json(company_user))


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
    return render(request, "hr_calendar/clockin.html",
                  {"app_version": APP_VERSION})


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
        # H37 (S138): explicit id, the same Chrome already derives from
        # start_url (installed phones keep the app), so the Sala de
        # Asistencia (/sala/) can be installed beside it.
        # Identificador explícito, el mismo que Chrome ya saca de
        # start_url (los móviles instalados conservan la app), para que
        # la Sala de Asistencia se pueda instalar junto a ella.
        "id": "/fichaje/",
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
