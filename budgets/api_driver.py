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
import base64
import binascii
import hashlib
import json
import logging
import secrets
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from budgets.assistance_resources import assistance_drivers
from budgets.assistance_traffic import OPEN_ORDER_STATUSES
from budgets.models import (
    DriverDeviceToken,
    WorkOrderAssistanceSignature,
    WorkOrderAssistanceUnit,
    WorkOrderAssistanceUnitEvent,
)
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


def _driver_units(company_user):
    """
    Albaranes of the open orders assigned to the driver and sent.

    ---

    Albaranes de las órdenes abiertas asignados al conductor (primer o
    segundo tramo) que la oficina ya le ha enviado.
    """
    return WorkOrderAssistanceUnit.objects.filter(
        Q(operator=company_user) | Q(operator_2=company_user),
        work_order__company=company_user.company,
        work_order__status__in=OPEN_ORDER_STATUSES,
    ).exclude(
        # Not sent yet by the office, or already closed in base: the
        # driver does not see it.
        # Aún sin enviar por la oficina, o ya cerrado en base: el
        # conductor no lo ve.
        status__in=(
            WorkOrderAssistanceUnit.STATUS_PENDING,
            WorkOrderAssistanceUnit.STATUS_CLOSED_BASE,
        ),
    ).select_related("work_order__insurer")


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
        units = _driver_units(company_user).order_by(
            "work_order__service_date", "work_order__work_order_number",
            "unit_number",
        )
        return JsonResponse({
            "driver": _display_name(company_user),
            "albaranes": [_unit_payload(unit) for unit in units],
        })


# ---------------------------------------------------------------------------
# H37 (S133). Driver sheet: detail of one albarán and its delivery.
# Hoja del conductor: detalle de un albarán y su entrega firmada.
# ---------------------------------------------------------------------------

Unit = WorkOrderAssistanceUnit
# States in which the driver can still fill and send the albarán.
# Estados en los que el conductor aún puede rellenar y enviar.
EDITABLE_STATUSES = (
    Unit.STATUS_NOTIFY_SENDING,
    Unit.STATUS_NOTIFIED,
    Unit.STATUS_NOTIFY_FAILED,
    Unit.STATUS_DOWNLOADED,
    Unit.STATUS_IN_PROGRESS,
)
OPENED_FROM = (
    Unit.STATUS_NOTIFY_SENDING,
    Unit.STATUS_NOTIFIED,
    Unit.STATUS_NOTIFY_FAILED,
)
# States from which the driver closes in base (signed, or closed
# without signature).
# Estados desde los que el conductor cierra en base.
CLOSABLE_IN_BASE = (
    Unit.STATUS_COMPLETED,
    Unit.STATUS_CLOSED_UNSIGNED,
    Unit.STATUS_SIGNED_RECEIVED,
)
SIGNATURE_PREFIX = "data:image/png;base64,"
MAX_SIGNATURE_CHARS = 2_000_000


def _number(value):
    """
    String of a decimal for the app, or "".

    ---

    Cadena de un decimal para la app, o "" si está vacío.
    """
    return "" if value is None else format(value, "f")


def _detail_payload(unit):
    """
    Full JSON of one albarán for the driver sheet.

    ---

    JSON completo de un albarán para la hoja del conductor: lo que
    necesita para el servicio, sin importes ni notas internas (dossier
    de Pepe, hoja del conductor).
    """
    work_order = unit.work_order
    signature = getattr(unit, "signature", None)
    payload = _unit_payload(unit)
    payload.update({
        "client_address": work_order.client_address,
        "vehicle_color": work_order.vehicle_color,
        "pickup_province": work_order.pickup_province,
        "delivery_address": work_order.delivery_address,
        "delivery_locality": work_order.delivery_locality,
        "insurer_comments": work_order.insurer_comments,
        "is_overnight": unit.is_overnight,
        "phase1_km": _number(unit.phase1_km),
        "phase2_km": _number(unit.phase2_km),
        "rescue_hours": _number(unit.rescue_hours),
        "wait_hours": _number(unit.wait_hours),
        "signer_name": signature.signer_name if signature else "",
        "signed": signature is not None,
        "unsigned_reason": unit.unsigned_reason,
        "editable": unit.status in EDITABLE_STATUSES,
        "can_close_base": unit.status in CLOSABLE_IN_BASE,
    })
    return payload


def _unit_of_driver(company_user, pk):
    """
    Albarán of the driver, or None.

    ---

    Albarán del conductor, o None si no es suyo o no está enviado.
    """
    return _driver_units(company_user).select_related(
        "signature",
    ).filter(pk=pk).first()


class DriverAlbaranDetailView(View):
    """
    Detail of one albarán (opening it marks it as opened).

    ---

    Detalle de un albarán. Abrirlo lo marca como "Descargado", igual
    que la página web del albarán cuando la abre su conductor.
    """

    def get(self, request, pk):
        """
        Return the albarán.

        ---

        Devuelve el albarán.
        """
        company_user, _token = _token_user(request)
        if company_user is None:
            return _error("Sesión no válida.", 401)
        unit = _unit_of_driver(company_user, pk)
        if unit is None:
            return _error("Este albarán ya no está asignado a ti.", 404)
        if unit.status in OPENED_FROM:
            previous = unit.status
            unit.status = Unit.STATUS_DOWNLOADED
            unit.downloaded_at = timezone.now()
            unit.save(update_fields=["status", "downloaded_at"])
            WorkOrderAssistanceUnitEvent.status_change(
                unit, previous, unit.status, by=company_user,
                detail="El chófer abre el albarán en la app.",
            )
        return JsonResponse({"albaran": _detail_payload(unit)})


def _decimal(data, key, label):
    """
    Non-negative decimal of the body, None if empty.

    ---

    Decimal no negativo del cuerpo, None si viene vacío. Lanza
    ValueError con el mensaje para el conductor si no es válido.
    """
    raw = str(data.get(key, "") or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise ValueError("%s: no es un número válido." % label)
    if value < 0 or value != value:
        raise ValueError("%s: no puede ser negativo." % label)
    return value


@method_decorator(csrf_exempt, name="dispatch")
class DriverAlbaranSubmitView(View):
    """
    Send the filled albarán: signed by the client, or closed without
    signature with a reason.

    ---

    Envía el albarán relleno: firmado por el cliente (pasa a
    Completado) o cerrado sin firma con su motivo (pasa a Cerrado sin
    firma). Regla del dossier: no se cierra sin firma o motivo de no
    firma. Guarda hora y usuario del cambio.
    """

    def post(self, request, pk):
        """
        Validate and save.

        ---

        Valida y guarda.
        """
        company_user, _token = _token_user(request)
        if company_user is None:
            return _error("Sesión no válida.", 401)
        data = _json_body(request)
        try:
            phase1_km = _decimal(data, "phase1_km", "Km")
            phase2_km = _decimal(data, "phase2_km", "Km del 2º tramo")
            rescue_hours = _decimal(
                data, "rescue_hours", "Horas de rescate",
            )
            wait_hours = _decimal(data, "wait_hours", "Horas de espera")
        except ValueError as exc:
            return _error(str(exc), 400)
        signature_data = str(data.get("signature_data", "") or "").strip()
        signer_name = str(data.get("signer_name", "") or "").strip()[:120]
        unsigned_reason = str(data.get("unsigned_reason", "") or "").strip()
        signed_offline = bool(data.get("signed_offline", False))
        if signature_data:
            if (not signature_data.startswith(SIGNATURE_PREFIX)
                    or len(signature_data) > MAX_SIGNATURE_CHARS):
                return _error("La firma no es válida.", 400)
            try:
                base64.b64decode(
                    signature_data[len(SIGNATURE_PREFIX):], validate=True,
                )
            except (binascii.Error, ValueError):
                return _error("La firma no es válida.", 400)
        elif not unsigned_reason:
            return _error(
                "Falta la firma del cliente o el motivo por el que no "
                "firma.",
                400,
            )

        with transaction.atomic():
            unit = _driver_units(company_user).select_for_update().filter(
                pk=pk,
            ).first()
            if unit is None:
                return _error("Este albarán ya no está asignado a ti.", 404)
            if unit.status not in EDITABLE_STATUSES:
                return _error(
                    "Este albarán ya está %s."
                    % unit.get_status_display().lower(),
                    409,
                )
            previous = unit.status
            now = timezone.now()
            unit.phase1_km = phase1_km
            unit.phase2_km = phase2_km if unit.is_overnight else None
            unit.rescue_hours = rescue_hours
            unit.wait_hours = wait_hours
            unit.synced_at = now
            if signature_data:
                unit.status = Unit.STATUS_COMPLETED
                unit.completed_at = now
                unit.unsigned_reason = ""
                detail = "Albarán firmado en la app."
            else:
                unit.status = Unit.STATUS_CLOSED_UNSIGNED
                unit.closed_at = now
                unit.unsigned_reason = unsigned_reason
                detail = "Cerrado sin firma: %s" % unsigned_reason
            unit.save()
            if signature_data:
                WorkOrderAssistanceSignature.objects.update_or_create(
                    unit=unit,
                    defaults={
                        "signature_data": signature_data,
                        "signer_name": signer_name,
                        "signed_offline": signed_offline,
                    },
                )
            WorkOrderAssistanceUnitEvent.status_change(
                unit, previous, unit.status, by=company_user,
                detail=detail,
            )
        logger.info(
            "# [DRIVER API] Albarán %s enviado por %s (%s).",
            unit.albaran_number, company_user.user.username, unit.status,
        )
        unit = _unit_of_driver(company_user, pk) or unit
        return JsonResponse({"albaran": _detail_payload(unit)})


@method_decorator(csrf_exempt, name="dispatch")
class DriverAlbaranCloseBaseView(View):
    """
    Close the albarán in base: final km and refuelling.

    ---

    Cierre en base (fase 4 del dossier): el conductor, ya en base, mete
    los km finales y si repostó y cuántos litros. El albarán pasa a
    "Cerrado en base" y conductor y máquina quedan libres en el panel de
    tráfico. Reglas del dossier: no se cierra en base sin km finales ni
    sin indicar si repostó.
    """

    def post(self, request, pk):
        """
        Validate and close.

        ---

        Valida y cierra.
        """
        company_user, _token = _token_user(request)
        if company_user is None:
            return _error("Sesión no válida.", 401)
        data = _json_body(request)
        try:
            km_end = _decimal(data, "km_end", "Km finales")
            liters = _decimal(data, "liters", "Litros")
        except ValueError as exc:
            return _error(str(exc), 400)
        refueled = data.get("refueled")
        if km_end is None:
            return _error("Faltan los km finales.", 400)
        if not isinstance(refueled, bool):
            return _error("Indica si has repostado.", 400)
        if refueled and not liters:
            return _error("Indica cuántos litros has repostado.", 400)

        with transaction.atomic():
            unit = _driver_units(company_user).select_for_update().filter(
                pk=pk,
            ).first()
            if unit is None:
                return _error("Este albarán ya no está asignado a ti.", 404)
            if unit.status not in CLOSABLE_IN_BASE:
                return _error(
                    "Este albarán no se puede cerrar en base: está %s."
                    % unit.get_status_display().lower(),
                    409,
                )
            previous = unit.status
            unit.base_km_end = km_end
            unit.refueled = refueled
            unit.refuel_liters = liters if refueled else None
            unit.base_closed_at = timezone.now()
            unit.status = Unit.STATUS_CLOSED_BASE
            unit.save()
            WorkOrderAssistanceUnitEvent.status_change(
                unit, previous, unit.status, by=company_user,
                detail=(
                    "Cerrado en base: %s km, %s." % (
                        km_end,
                        "repostó %s l" % liters if refueled
                        else "sin repostar",
                    )
                ),
            )
        logger.info(
            "# [DRIVER API] Albarán %s cerrado en base por %s.",
            unit.albaran_number, company_user.user.username,
        )
        return JsonResponse({"ok": True, "number": unit.albaran_number})
