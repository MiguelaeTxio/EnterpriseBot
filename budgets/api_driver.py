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
import datetime
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
from budgets.assistance_traffic import (
    OPEN_ORDER_STATUSES, driver_is_out, route_units, unit_at,
)
from budgets import service_sheet as sheet
from budgets.service_chain import chain_on_start
from budgets.service_route import purge_night
from budgets.service_geocode import maps_url
from budgets.models import (
    DriverDeviceToken,
    DriverPosition,
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
        # S138: "Cómo llegar" buttons (Google Maps, by coordinates when
        # the order has them).
        # Botones "Cómo llegar" (Google Maps, por coordenadas si las hay).
        "pickup_maps_url": maps_url(work_order, "pickup"),
        "destination_maps_url": maps_url(work_order, "destination"),
        "client_name": work_order.client_name,
        "client_phone": work_order.client_phone,
        "vehicle": " ".join(part for part in (
            work_order.vehicle_brand, work_order.vehicle_model,
        ) if part),
        "vehicle_plate": " / ".join(part for part in (
            work_order.vehicle_plate, work_order.second_vehicle_plate,
        ) if part),
        "breakdown": work_order.breakdown_description,
        "machine": unit.machine,
        "helpers": unit.helper_names,
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
        # Not sent yet by the office, closed in base or cancelled: the
        # driver does not see it.
        # Aún sin enviar por la oficina, cerrado en base o anulado: el
        # conductor no lo ve.
        status__in=(
            WorkOrderAssistanceUnit.STATUS_PENDING,
            WorkOrderAssistanceUnit.STATUS_CLOSED_BASE,
            WorkOrderAssistanceUnit.STATUS_CANCELLED,
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
            # S133: whether the app sends the phone position (map).
            # Si la app envía la posición del móvil (mapa de tráfico).
            "tracking": driver_is_out(company_user),
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
    operator = unit.operator
    # H37 (S133): Pepe's service sheet. "started" is the gate: without
    # the km at departure the app only shows the header.
    # Hoja de servicio de Pepe. "started" es la puerta: sin los km de
    # salida la app solo enseña la cabecera.
    payload.update({
        "operator": _display_name(operator) if operator else "",
        "started": unit.km_start is not None,
        "km_start": _number(unit.km_start),
        "departed_at": (
            timezone.localtime(unit.started_at).strftime("%H:%M")
            if unit.started_at and unit.km_start is not None else ""
        ),
        "arrived": unit.arrived_at is not None,
        "vehicle_pma": _number(work_order.vehicle_pma),
        "vehicle_tare": _number(work_order.vehicle_tare),
        "vehicle_length": _number(work_order.vehicle_length),
        "vehicle_height": _number(work_order.vehicle_height),
        "vehicle_load": work_order.vehicle_load,
        "pickup_location": work_order.pickup_location,
        "work_hours": _number(unit.work_hours),
        "driver_notes": unit.driver_notes,
        "repair_on_site": work_order.repair_on_site,
        "photo_counts": sheet.photo_counts(unit),
        "required_photos": sheet.required_photo_kinds(unit),
        "missing": sheet.missing_for_signature(unit),
        "bases": [
            {"id": base.pk, "name": base.name}
            for base in sheet.bases_of(work_order.company)
        ],
        "default_base": (
            unit.arrival_base_id or unit.departure_base_id
            or getattr(operator, "base_id", None) or work_order.base_id
        ),
    })
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


def _missing_km(unit, phase1_km, phase2_km):
    """
    Error text if the driver did not write the km of the albarán, or "".

    ---

    Texto de error si el chófer no ha anotado los km, o "". Sin
    pernocta, un dato (recogida, destino y vuelta a base); con pernocta,
    dos (recogida y vuelta a base; ida a destino y vuelta a base).
    """
    if phase1_km is None:
        return (
            "Faltan los km de la recogida con la vuelta a base."
            if unit.is_overnight else
            "Faltan los km del servicio, con la vuelta a base."
        )
    if unit.is_overnight and phase2_km is None:
        return "Faltan los km de la ida al destino con la vuelta a base."
    return ""


def _device_time(millis, now):
    """
    A phone time in milliseconds if sane (not in the future), else now.

    ---

    Hora del móvil en milisegundos si es razonable (no futura); si no,
    la de ahora.
    """
    if isinstance(millis, (int, float)) and not isinstance(millis, bool):
        try:
            taken = datetime.datetime.fromtimestamp(
                millis / 1000, tz=datetime.timezone.utc,
            )
        except (OverflowError, OSError, ValueError):
            return now
        if taken <= now:
            return taken
    return now


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
            work_hours = _decimal(data, "work_hours", "Horas de trabajo")
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
            # S138 (Miguel Ángel): the km are the driver's and always
            # needed: what he writes, including the return to base he
            # has not driven yet, is what is billed.
            # Los km son del chófer y siempre obligatorios: lo que anota,
            # con la vuelta a base que aún no ha hecho, es lo que se cobra.
            missing_km = _missing_km(unit, phase1_km, phase2_km)
            if missing_km:
                return _error(missing_km, 400)
            # S133: the service sheet is filled before the signature.
            # La hoja de servicio se rellena antes de la firma.
            try:
                sheet.apply_order_fields(unit, data)
            except sheet.SheetError as exc:
                return _error(str(exc), 400)
            missing = sheet.missing_for_signature(unit)
            if missing:
                # What was filled is kept; only the signature waits.
                # Lo rellenado se guarda; solo la firma espera.
                return _error(
                    "Falta en la hoja de servicio: %s." % ", ".join(missing),
                    400,
                )
            previous = unit.status
            now = timezone.now()
            if "phase1_km" in data:
                unit.phase1_km = phase1_km
            if "phase2_km" in data:
                unit.phase2_km = phase2_km if unit.is_overnight else None
            unit.rescue_hours = rescue_hours
            unit.wait_hours = wait_hours
            unit.work_hours = work_hours
            if "driver_notes" in data:
                unit.driver_notes = str(data.get("driver_notes") or "").strip()
            unit.synced_at = now
            # S138: when it was really signed (also without coverage).
            # Cuándo se firmó de verdad (también sin cobertura).
            signed_at = _device_time(data.get("signed_at"), now)
            if signature_data:
                unit.status = Unit.STATUS_COMPLETED
                unit.completed_at = signed_at
                unit.unsigned_reason = ""
                detail = "Albarán firmado en la app."
            else:
                unit.status = Unit.STATUS_CLOSED_UNSIGNED
                unit.closed_at = signed_at
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
            if unit.is_overnight:
                # S138: the night in base is not work: its positions go.
                # La noche en base no es trabajo: sus posiciones se borran.
                unit_pk = unit.pk
                transaction.on_commit(lambda: purge_night(unit_pk))
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
        # S133: Pepe's sheet: base, time of arrival and litres too.
        # Hoja de Pepe: también base y hora de llegada y litros.
        arrival_base = sheet.bases_of(company_user.company).filter(
            pk=data.get("base") or 0,
        ).first()
        if arrival_base is None:
            return _error("Indica la base a la que llegas.", 400)
        arrived_at = sheet.client_time(data.get("arrived_at"))
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
            # S140: arriving in base before signing is not possible (the
            # app used to send the time the albarán was opened).
            # No se llega a base antes de firmar (la app mandaba la hora
            # a la que se abrió el albarán).
            work_end = unit.completed_at or unit.closed_at
            if arrived_at and work_end and arrived_at < work_end:
                return _error(
                    "La hora de llegada a base (%s) es anterior a la firma "
                    "(%s). Corrígela." % (
                        timezone.localtime(arrived_at).strftime("%H:%M"),
                        timezone.localtime(work_end).strftime("%H:%M"),
                    ),
                    400,
                )
            if unit.km_start is not None and km_end < unit.km_start:
                return _error(
                    "Los km de llegada (%s) no pueden ser menos que los de "
                    "salida (%s)." % (km_end, unit.km_start),
                    400,
                )
            previous = unit.status
            unit.base_km_end = km_end
            unit.arrival_base = arrival_base
            unit.base_arrived_at = arrived_at
            if (unit.phase1_km is None and unit.km_start is not None
                    and not unit.is_overnight):
                unit.phase1_km = km_end - unit.km_start
            unit.refueled = refueled
            unit.refuel_liters = liters if refueled else None
            unit.base_closed_at = timezone.now()
            unit.base_closed_by = company_user
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


@method_decorator(csrf_exempt, name="dispatch")
class DriverAlbaranStartView(View):
    """
    Open the service sheet with the km at departure.

    ---

    Abre la hoja de servicio con los km y la hora de salida de base (la
    puerta de la hoja: Miguel Ángel, S133). El sistema apunta la base de
    salida y si es nocturno. Se puede repetir para corregirlos.
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
            try:
                previous = sheet.start(
                    unit, company_user, data.get("km_start"), data.get("at"),
                )
            except sheet.SheetError as exc:
                return _error(str(exc), 400)
            # S138: coming back from another albarán, that one ends here
            # (chained on the road) and is closed in base.
            # Si volvía de otro albarán, ese acaba aquí (encadenado en
            # ruta) y se cierra en base.
            chained = chain_on_start(unit, company_user)
            if previous != unit.status:
                WorkOrderAssistanceUnitEvent.status_change(
                    unit, previous, unit.status, by=company_user,
                    detail=(
                        "Sale con %s km desde donde estaba, al terminar %s "
                        "(encadenado en ruta)." % (
                            unit.km_start, chained.albaran_number,
                        )
                        if chained else
                        "Sale de base con %s km." % unit.km_start
                    ),
                )
        unit = _unit_of_driver(company_user, pk) or unit
        return JsonResponse({"albaran": _detail_payload(unit)})


@method_decorator(csrf_exempt, name="dispatch")
class DriverAlbaranArriveView(View):
    """
    Mark the arrival at the service.

    ---

    Marca la llegada al servicio (hora de entrada, solo oficina).
    """

    def post(self, request, pk):
        """
        Save the time.

        ---

        Guarda la hora.
        """
        company_user, _token = _token_user(request)
        if company_user is None:
            return _error("Sesión no válida.", 401)
        data = _json_body(request)
        unit = _unit_of_driver(company_user, pk)
        if unit is None:
            return _error("Este albarán ya no está asignado a ti.", 404)
        try:
            sheet.arrive(unit, data.get("at"))
        except sheet.SheetError as exc:
            return _error(str(exc), 400)
        return JsonResponse({"albaran": _detail_payload(unit)})


@method_decorator(csrf_exempt, name="dispatch")
class DriverAlbaranPhotoView(View):
    """
    Upload a photo of the service sheet.

    ---

    Sube una foto de la hoja (antes de cargar, cargado o descargado),
    en JSON con la imagen en base64. Repetir el envío con el mismo id
    del móvil no la duplica.
    """

    def post(self, request, pk):
        """
        Store the photo.

        ---

        Guarda la foto.
        """
        company_user, _token = _token_user(request)
        if company_user is None:
            return _error("Sesión no válida.", 401)
        data = _json_body(request)
        unit = _unit_of_driver(company_user, pk)
        if unit is None:
            return _error("Este albarán ya no está asignado a ti.", 404)
        try:
            sheet.save_photo(
                unit, company_user, data.get("kind"), data.get("uid"),
                data.get("image"), data.get("taken_at"),
            )
        except sheet.SheetError as exc:
            return _error(str(exc), 400)
        unit = _unit_of_driver(company_user, pk) or unit
        return JsonResponse({"albaran": _detail_payload(unit)})


def _coordinate(data, key, label, limit):
    """
    Coordinate of the request, checked against its range.

    ---

    Coordenada de la petición, dentro de su rango (±90 la latitud,
    ±180 la longitud), o ValueError.
    """
    try:
        value = Decimal(str(data.get(key))).quantize(Decimal("0.000001"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Falta la %s." % label)
    if not value.is_finite() or abs(value) > limit:
        raise ValueError("La %s no es válida." % label)
    return value


MAX_POSITION_BATCH = 500


def _position_row(company_user, data, now):
    """
    Unsaved DriverPosition of one position sent by the app.

    ---

    La posición (sin guardar) de un punto que manda la app, o
    ValueError. Hora del móvil si es razonable (no futura); si no, la
    de ahora.
    """
    latitude = _coordinate(data, "latitude", "latitud", 90)
    longitude = _coordinate(data, "longitude", "longitud", 180)
    recorded_at = _device_time(data.get("recorded_at"), now)
    accuracy = data.get("accuracy")
    return DriverPosition(
        company_user=company_user,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=(
            int(accuracy)
            if isinstance(accuracy, (int, float))
            and not isinstance(accuracy, bool) and 0 <= accuracy < 100000
            else None
        ),
        recorded_at=recorded_at,
    )


@method_decorator(csrf_exempt, name="dispatch")
class DriverPositionView(View):
    """
    Position of the driver's phone.

    ---

    Posición del móvil del conductor para el mapa de tráfico (H37,
    S133). Solo se guarda mientras el conductor tiene un albarán en
    curso (enviado, en servicio o regresando): fuera de servicio no se
    le sigue. La respuesta dice a la app si debe seguir enviando
    (`tracking`); con `false` la app deja de enviar.
    """

    def post(self, request):
        """
        Store the position(s) if the driver is on a service.

        ---

        Guarda la posición si el conductor está en un servicio. S138:
        también un lote ({"positions": [...]}), las que el móvil guardó
        sin cobertura, para que la ruta del albarán no tenga huecos.
        Cada posición queda ligada al albarán que llevaba a la hora en
        que se tomó (assistance_traffic.unit_at: rutas encadenadas en
        base o en ruta); la que no es de ninguno no se guarda.
        """
        company_user, _token = _token_user(request)
        if company_user is None:
            return _error("Sesión no válida.", 401)
        tracking = driver_is_out(company_user)
        data = _json_body(request)
        batch = data.get("positions")
        if batch is None and not tracking:
            return JsonResponse({"tracking": False})
        items = batch[:MAX_POSITION_BATCH] if isinstance(batch, list) else [
            data,
        ]
        now = timezone.now()
        rows = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                rows.append(_position_row(company_user, item, now))
            except ValueError as exc:
                if batch is None:
                    return _error(str(exc), 400)
        if rows:
            units = route_units(
                company_user, min(row.recorded_at for row in rows),
            )
            for row in rows:
                row.unit = unit_at(units, row.recorded_at)
            rows = [row for row in rows if row.unit is not None]
            DriverPosition.objects.bulk_create(rows)
        return JsonResponse({"tracking": tracking, "saved": len(rows)})


# ---------------------------------------------------------------------------
# Android App Links of the drivers' app.
# App Links de la app de chóferes.
# ---------------------------------------------------------------------------

# H37 (S138): SHA-256 of the fixed signing certificate of EBotDeliveryNotes
# (the build workflow prints it as the "Huella APK" annotation).
# Huella del certificado fijo de firma de la app (anotación "Huella APK"
# del workflow de compilación).
DRIVER_APP_PACKAGE = "com.miguelaetxio.ebotdeliverynotes"
DRIVER_APP_CERT_SHA256 = (
    "8D:47:D7:C6:2B:3B:AC:F0:5B:FA:3D:7D:9C:80:D5:AB:"
    "05:7E:0D:32:41:CE:96:32:DF:F2:5D:0E:FF:12:A7:3C"
)


def asset_links(request):
    """
    /.well-known/assetlinks.json for the drivers' app.

    ---

    assetlinks.json para que Android abra en la app de chóferes el
    enlace del aviso de WhatsApp del albarán (Miguel Ángel, S138: con un
    servicio, el móvil debe mandar su posición al panel, y la manda en
    cuanto se abre la app).
    """
    return JsonResponse([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": DRIVER_APP_PACKAGE,
            "sha256_cert_fingerprints": [DRIVER_APP_CERT_SHA256],
        },
    }], safe=False)
