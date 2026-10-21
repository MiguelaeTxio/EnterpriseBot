# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/api_driver.py
"""
H37 (S133). API of the driver app (EBotDeliveryNotes).

---

H37 (S133). API de la app del conductor (EBotDeliveryNotes, app
nativa Android, anexo V37 sección 4.1). JSON sobre HTTPS, sin sesión
ni CSRF: la app manda `Authorization: Token <token>` en cada petición.

- `POST /api/driver/login/`: usuario y contraseña del panel; devuelve
  un token por dispositivo (`DriverDeviceToken`, solo se guarda su
  SHA-256).
- `POST /api/driver/logout/`: revoca el token del dispositivo.
- `GET /api/driver/albaranes/`: albaranes de las órdenes abiertas
  asignados al conductor (primer o segundo tramo) que la oficina ya le
  ha enviado (los pendientes de enviar no salen).

Pueden entrar los conductores de la sección Asistencia
(`assistance_resources.assistance_drivers`) y, para las pruebas, los
administradores y supervisores de asistencia.
"""
import hashlib
import json
import logging
import secrets

from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from budgets.assistance_resources import assistance_drivers
from budgets.assistance_traffic import OPEN_ORDER_STATUSES
from budgets.models import DriverDeviceToken, WorkOrderAssistanceUnit
from ivr_config.models import CompanyUser

logger = logging.getLogger(__name__)

STAFF_ROLES = (CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ASSIST_SUPERVISOR)


def _hash(key):
    """
    SHA-256 of a token.

    ---

    SHA-256 de un token.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _error(message, status):
    """
    JSON error response.

    ---

    Respuesta de error en JSON, con el mensaje que enseña la app.
    """
    return JsonResponse({"error": message}, status=status)


def _can_use_app(company_user):
    """
    Whether a panel user may use the driver app.

    ---

    Si un usuario del panel puede usar la app del conductor.
    """
    if not company_user.is_active:
        return False
    if company_user.role in STAFF_ROLES:
        return True
    return assistance_drivers(company_user.company).filter(
        pk=company_user.pk,
    ).exists()


def _display_name(company_user):
    """
    Full name of a panel user, or his username.

    ---

    Nombre completo del usuario, o su usuario.
    """
    user = company_user.user
    return user.get_full_name() or user.username


def _token_user(request):
    """
    Panel user of the `Authorization: Token` header, or None.

    ---

    Usuario del panel del token de la cabecera, o None si falta, no
    existe, está revocado o el usuario ya no puede usar la app. Anota
    el último uso.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, key = header.partition(" ")
    if scheme.lower() != "token" or not key.strip():
        return None, None
    token = DriverDeviceToken.objects.select_related(
        "company_user__user", "company_user__company",
    ).filter(key_hash=_hash(key.strip()), revoked_at__isnull=True).first()
    if token is None or not _can_use_app(token.company_user):
        return None, None
    DriverDeviceToken.objects.filter(pk=token.pk).update(
        last_used_at=timezone.now(),
    )
    return token.company_user, token


def _json_body(request):
    """
    JSON body of the request as a dict ({} if it is not valid JSON).

    ---

    Cuerpo JSON de la petición como diccionario.
    """
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@method_decorator(csrf_exempt, name="dispatch")
class DriverLoginView(View):
    """
    Sign in with the panel username and password.

    ---

    Entrada con el usuario y la contraseña del panel. Devuelve el token
    del dispositivo y el nombre del conductor.
    """

    def post(self, request):
        """
        Check the credentials and create the device token.

        ---

        Comprueba las credenciales y crea el token del dispositivo.
        """
        data = _json_body(request)
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        device = str(data.get("device", "")).strip()[:120]
        if not username or not password:
            return _error("Escribe tu usuario y tu contraseña.", 400)
        user = authenticate(request, username=username, password=password)
        company_user = (
            CompanyUser.objects.select_related("company").filter(
                user=user,
            ).first()
            if user is not None
            else None
        )
        if company_user is None:
            logger.warning(
                "# [DRIVER API] Acceso rechazado para %r.", username,
            )
            return _error("Usuario o contraseña incorrectos.", 401)
        if not _can_use_app(company_user):
            return _error(
                "Tu usuario no está dado de alta como conductor de "
                "asistencia.",
                403,
            )
        key = secrets.token_urlsafe(32)
        DriverDeviceToken.objects.create(
            company_user=company_user,
            key_hash=_hash(key),
            device_name=device,
        )
        logger.info(
            "# [DRIVER API] Acceso de %s desde %r.", username, device,
        )
        return JsonResponse({
            "token": key,
            "user": {
                "username": user.username,
                "name": _display_name(company_user),
            },
        })


@method_decorator(csrf_exempt, name="dispatch")
class DriverLogoutView(View):
    """
    Revoke the token of this device.

    ---

    Revoca el token de este dispositivo.
    """

    def post(self, request):
        """
        Revoke the token.

        ---

        Revoca el token.
        """
        company_user, token = _token_user(request)
        if token is None:
            return _error("Sesión no válida.", 401)
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
        return JsonResponse({"ok": True})


def _unit_payload(unit):
    """
    JSON of one albarán for the app.

    ---

    JSON de un albarán para la app.
    """
    work_order = unit.work_order
    return {
        "id": unit.pk,
        "number": unit.albaran_number,
        "status": unit.status,
        "status_label": unit.get_status_display(),
        "service_date": work_order.service_date.isoformat(),
        "insurer": work_order.insurer.name,
        "expediente": work_order.expediente,
        "pickup": (
            "Base" if work_order.base_pickup
            else work_order.pickup_location
        ),
        "destination": work_order.destination,
        "client_name": work_order.client_name,
        "client_phone": work_order.client_phone,
        "vehicle": " ".join(part for part in (
            work_order.vehicle_brand, work_order.vehicle_model,
        ) if part),
        "vehicle_plate": work_order.vehicle_plate,
        "breakdown": work_order.breakdown_description,
        "machine": unit.machine,
        "albaran_url": settings.PLATFORM_BASE_URL + reverse(
            "budgets:work_order_albaran", args=[unit.pk],
        ),
    }


class DriverAlbaranesView(View):
    """
    Albaranes assigned to the driver.

    ---

    Albaranes de las órdenes abiertas asignados al conductor, del más
    próximo al más lejano.
    """

    def get(self, request):
        """
        Return the list.

        ---

        Devuelve la lista.
        """
        company_user, _token = _token_user(request)
        if company_user is None:
            return _error("Sesión no válida.", 401)
        units = WorkOrderAssistanceUnit.objects.filter(
            Q(operator=company_user) | Q(operator_2=company_user),
            work_order__company=company_user.company,
            work_order__status__in=OPEN_ORDER_STATUSES,
        ).exclude(
            # Not sent yet by the office: the driver does not see it.
            # Aún sin enviar por la oficina: el conductor no lo ve.
            status=WorkOrderAssistanceUnit.STATUS_PENDING,
        ).select_related("work_order__insurer").order_by(
            "work_order__service_date", "work_order__work_order_number",
            "unit_number",
        )
        return JsonResponse({
            "driver": _display_name(company_user),
            "albaranes": [_unit_payload(unit) for unit in units],
        })
