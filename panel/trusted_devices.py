# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/trusted_devices.py
"""
Trusted devices of the panel users (H24, S129): the only place that
reads, issues or revokes the `eb_trusted_device` cookie. Used by the
login (quick access without password), the profile and the clock-in
(hr_calendar/clockin.py), which identifies the worker with this cookie
even when the panel session has expired.

A user may trust several devices (phone and PC): each one is a
TrustedDevice row whose token travels in the signed cookie. Before S129
there was one token per user, so trusting a second device silently
broke the first one.

---

Dispositivos de confianza de los usuarios del panel (H24, S129): el
único sitio que lee, emite o revoca la cookie `eb_trusted_device`. La
usan el login (acceso rápido sin contraseña), el perfil y el fichaje
(hr_calendar/clockin.py), que identifica al trabajador con esta cookie
aunque la sesión del panel haya caducado.

Un usuario puede confiar en varios dispositivos (móvil y PC): cada uno
es una fila TrustedDevice cuyo token viaja en la cookie firmada. Antes
de S129 había un token por usuario, así que confiar en un segundo
dispositivo rompía en silencio el primero.
"""
import logging
import uuid

from django.core import signing

from ivr_config.models import TrustedDevice

logger = logging.getLogger(__name__)

COOKIE_NAME = "eb_trusted_device"
COOKIE_MAX_AGE = 365 * 24 * 3600


def current_device(request):
    """
    The valid TrustedDevice of the request's cookie, or None (no
    cookie, bad signature, revoked device, inactive user).
    ---
    El TrustedDevice válido de la cookie de la petición, o None (sin
    cookie, firma mala, dispositivo revocado, usuario inactivo).
    """
    raw = request.COOKIES.get(COOKIE_NAME, "")
    if not raw:
        return None
    try:
        payload = signing.loads(raw, max_age=COOKIE_MAX_AGE)
        token = uuid.UUID(str(payload.get("tok")))
    except (signing.BadSignature, AttributeError, TypeError, ValueError):
        return None
    device = TrustedDevice.objects.select_related(
        "company_user__user", "company_user__company",
    ).filter(token=token).first()
    if device is None:
        return None
    company_user = device.company_user
    if (
        company_user.user_id != payload.get("uid")
        or not company_user.is_active
        or not company_user.user.is_active
    ):
        return None
    return device


def device_owner(request):
    """
    The CompanyUser that owns the request's valid trusted device.
    ---
    El CompanyUser dueño del dispositivo de confianza válido de la
    petición.
    """
    device = current_device(request)
    return device.company_user if device is not None else None


def trust(request, response, company_user):
    """
    Marks the request's device as trusted for company_user: a new
    TrustedDevice and its cookie on the response. The other devices of
    the user stay valid; a previous device of the same user in this
    browser is replaced.
    ---
    Marca el dispositivo de la petición como de confianza para
    company_user: un TrustedDevice nuevo y su cookie en la respuesta.
    Los demás dispositivos del usuario siguen valiendo; si este
    navegador ya era un dispositivo del mismo usuario, se sustituye.
    """
    previous = current_device(request)
    if previous is not None and previous.company_user_id == company_user.pk:
        previous.delete()
    device = TrustedDevice.objects.create(
        company_user=company_user,
        token=uuid.uuid4(),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:200],
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=signing.dumps(
            {"uid": company_user.user_id, "tok": str(device.token)},
        ),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="Lax",
    )
    logger.info(
        "# [TRUSTED DEVICE] Dispositivo #%d de confianza para usuario "
        "pk=%s.", device.pk, company_user.user_id,
    )
    return device


def forget(request, response):
    """
    Revokes the request's trusted device (only this one) and deletes
    the cookie.
    ---
    Revoca el dispositivo de confianza de la petición (solo este) y
    borra la cookie.
    """
    device = current_device(request)
    if device is not None:
        logger.info(
            "# [TRUSTED DEVICE] Dispositivo #%d revocado (usuario pk=%s).",
            device.pk, device.company_user.user_id,
        )
        device.delete()
    response.delete_cookie(COOKIE_NAME)
