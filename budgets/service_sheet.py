# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/service_sheet.py
"""
H37 (S133). Service sheet of the driver (Pepe's model).

---

H37 (S133). Hoja de servicio del conductor, según el modelo que pasó
Pepe ("HOJA DE SERVICIO - Registro de asistencia y remolque"):

- 01 Datos generales: nº de albarán, día, máquina y operario los pone
  el sistema. Km salida es obligatorio y es la PUERTA: hasta meterlo,
  el conductor no ve la hoja (Miguel Ángel, S133: "si no mete la
  información inicial no le da acceso a la hoja de servicio"; en el
  modelo venía como opcional, pendiente de confirmar con Pepe). La hora
  de salida de base (`started_at`) también la pone el conductor en la
  puerta (Miguel Ángel, S133: en el modelo venía en rojo por error,
  "lo debe rellenar el chófer"). La base de salida y el nocturno los
  apunta el sistema: solo los ve la oficina.
- 02 Cliente y vehículo: obligatorios cliente, PMA y avería; el resto
  se puede dejar vacío.
- 03 Servicio y tiempos: obligatorios recogida, destino y firma (o el
  motivo por el que no firma, regla del dossier); al cerrar en base,
  base, km y hora de llegada y litros de gasoil. La hora de entrada al
  servicio la marca el conductor al llegar (solo oficina).
- 04 Fotos: antes de cargar, cargado en altura y descargado. Sin ellas
  no aparece la firma (reunión con Pepe, S133), salvo reparación en el
  sitio, donde no se carga nada.

S140 (Miguel Ángel, tras la prueba de campo del 28/10), cada paso es
obligatorio y sin él no aparece el siguiente:
1. Salida: km y hora (hasta entonces el chófer no ve ningún dato).
2. Llegada: cuentakilómetros al llegar, con los km del GPS desde la
   salida como orientación.
3. Fotos, todas: las de remolque o, en reparación en el sitio, antes y
   después de la reparación.
4. Km: en remolque, el cuentakilómetros en la entrega; siempre, los km
   de vuelta a base como distancia (con la de Google desde donde está
   como orientación). Los km del servicio salen de ahí.
5. Firma, que envía el albarán.
6. Cierre en base (km de llegada y repostaje) o en ruta.
Con pernocta siguen los dos tramos de km que anota el chófer (S138).
"""
import base64
import binascii
import datetime
import uuid
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from budgets.models import (
    Base,
    WorkOrderAssistanceUnit,
    WorkOrderAssistanceUnitPhoto as Photo,
)

Unit = WorkOrderAssistanceUnit

PHOTO_BUCKET = "cgs_grupo_alvarez"
PHOTO_PREFIX = "asistencia/albaranes"
MAX_PHOTO_BYTES = 6 * 1024 * 1024
# A time sent by the phone is trusted within these limits (offline
# actions arrive later); otherwise the server time is used.
# Una hora enviada por el móvil vale dentro de estos límites (lo hecho
# sin cobertura llega después); si no, se usa la del servidor.
MAX_PAST = datetime.timedelta(hours=72)
MAX_FUTURE = datetime.timedelta(minutes=10)

# Fields of the order the driver fills in the sheet: argument ->
# (field, label, required for the signature).
# Campos de la orden que el conductor rellena en la hoja: argumento ->
# (campo, etiqueta, obligatorio para la firma).
ORDER_FIELDS = {
    "client_name": ("client_name", "Cliente", True),
    "expediente": ("expediente", "Expediente", False),
    "vehicle_plate": ("vehicle_plate", "Matrícula", False),
    "vehicle_pma": ("vehicle_pma", "PMA", True),
    "vehicle_tare": ("vehicle_tare", "Tara", False),
    "vehicle_length": ("vehicle_length", "Largo", False),
    "vehicle_height": ("vehicle_height", "Alto", False),
    "vehicle_load": ("vehicle_load", "Vehículo / carga", False),
    "breakdown": ("breakdown_description", "Avería", True),
    "pickup": ("pickup_location", "Recogida", True),
    "destination": ("destination", "Destino", True),
}
DECIMAL_ORDER_FIELDS = (
    "vehicle_pma", "vehicle_tare", "vehicle_length", "vehicle_height",
)


class SheetError(Exception):
    """
    Message for the driver when a step of the sheet is not valid.

    ---

    Mensaje para el conductor cuando un paso de la hoja no vale.
    """


def client_time(raw):
    """
    Datetime of an epoch in milliseconds sent by the phone, or now.

    ---

    Hora de un instante en milisegundos enviado por el móvil, o la del
    servidor si no viene o no es creíble.
    """
    now = timezone.now()
    try:
        value = datetime.datetime.fromtimestamp(
            int(raw) / 1000, tz=datetime.timezone.utc,
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return now
    if now - MAX_PAST <= value <= now + MAX_FUTURE:
        return min(value, now)
    return now


def decimal_or_none(raw, label):
    """
    Non-negative decimal written with point or comma, None if empty.

    ---

    Decimal no negativo (punto o coma), None si viene vacío.
    """
    text = str(raw if raw is not None else "").strip().replace(",", ".")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise SheetError("%s: no es un número válido." % label)
    if value != value or value < 0:
        raise SheetError("%s: no puede ser negativo." % label)
    return value


def is_night(unit, when):
    """
    Whether a moment falls in the night schedule of the service.

    ---

    Si un momento cae en el horario nocturno del servicio: el de la
    aseguradora, el de la empresa por defecto o, en su defecto, el de
    la ficha de la empresa (mismo orden que el motor de presupuestos).
    """
    from budgets.services import _resolve_night_schedule

    work_order = unit.work_order
    schedule = (
        _resolve_night_schedule(work_order.insurer)
        if work_order.insurer_id else None
    )
    source = schedule or work_order.company
    start, end = source.night_start, source.night_end
    if start is None or end is None:
        return None
    if isinstance(start, str):
        start = datetime.time.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.time.fromisoformat(end)
    moment = timezone.localtime(when).time()
    if start <= end:
        return start <= moment < end
    return moment >= start or moment < end


def start(unit, by, km_raw, at_raw):
    """
    Open the sheet: km at departure, departure time, base and night.

    ---

    Abre la hoja: km y hora de salida de base, que pone el conductor
    (obligatorios), y, por el sistema, base de salida y nocturno. Pasa
    el albarán a "En curso". Se puede repetir para corregirlos.
    Devuelve el estado anterior para el registro.
    """
    km = decimal_or_none(km_raw, "Km salida")
    if km is None:
        raise SheetError("Faltan los km de salida.")
    if at_raw in (None, ""):
        raise SheetError("Falta la hora de salida de base.")
    when = client_time(at_raw)
    previous = unit.status
    unit.km_start = km
    unit.started_at = when
    base = getattr(by, "base", None) or unit.work_order.base
    if unit.departure_base_id is None and base is not None:
        unit.departure_base = base
    unit.is_night = is_night(unit, unit.started_at)
    unit.status = Unit.STATUS_IN_PROGRESS
    unit.save()
    return previous


def arrive(unit, at_raw, km_raw):
    """
    Mark the arrival at the service with the odometer.

    ---

    Marca la llegada al servicio con el cuentakilómetros, obligatorio
    (S140). La hora vale la primera; los km se pueden corregir.
    """
    if unit.km_start is None:
        raise SheetError("Primero los km de salida.")
    km = decimal_or_none(km_raw, "Km al llegar")
    if km is None:
        raise SheetError("Faltan los km del cuentakilómetros al llegar.")
    if km < unit.km_start:
        raise SheetError(
            "Los km al llegar (%s) no pueden ser menos que los de salida "
            "(%s)." % (km, unit.km_start)
        )
    unit.km_arrival = km
    if unit.arrived_at is None:
        unit.arrived_at = client_time(at_raw)
    unit.save(update_fields=["km_arrival", "arrived_at", "updated_at"])


def needs_delivery_km(unit):
    """
    Whether the odometer at delivery is asked (tow without overnight).

    ---

    Si se pide el cuentakilómetros en la entrega: remolque sin pernocta
    (en reparación en el sitio, la entrega es el mismo sitio).
    """
    return not unit.work_order.repair_on_site and not unit.is_overnight


def service_km(unit, km_delivery=None, km_return=None):
    """
    Km of the service worked out from the driver's data, or None.

    ---

    Km del servicio a partir de lo que anota el chófer (S140): del
    cuentakilómetros de salida al de la entrega (en reparación en el
    sitio, al de la llegada) más los km de vuelta a base.
    """
    km_delivery = km_delivery if km_delivery is not None else unit.km_delivery
    km_return = km_return if km_return is not None else unit.km_return
    end = km_delivery if needs_delivery_km(unit) else unit.km_arrival
    if unit.km_start is None or end is None or km_return is None:
        return None
    return end - unit.km_start + km_return


def gps_km(unit):
    """
    Km driven since departure according to the phone positions.

    ---

    Km recorridos desde la salida según las posiciones del móvil (hasta
    la llegada si ya llegó): orientación para el cuentakilómetros.
    """
    from budgets.service_route import _points, distance_m

    if unit.started_at is None:
        return None
    points = [
        p for p in _points(unit)
        if p[2] >= unit.started_at
        and (unit.arrived_at is None or p[2] <= unit.arrived_at)
    ]
    meters = sum(
        distance_m(points[k][:2], points[k + 1][:2])
        for k in range(len(points) - 1)
    )
    return (Decimal(meters) / 1000).quantize(Decimal("0.1"))


def required_photo_kinds(unit):
    """
    Photo kinds required before the signature.

    ---

    Fotos obligatorias antes de la firma: las tres de remolque o, en
    reparación en el sitio, antes y después de la reparación (S140).
    """
    if unit.work_order.repair_on_site:
        return list(Photo.REPAIR_KINDS)
    return list(Photo.TOW_KINDS)


def photo_counts(unit):
    """
    Number of photos of each kind.

    ---

    Número de fotos de cada tipo.
    """
    counts = {kind: 0 for kind, _label in Photo.KIND_CHOICES}
    for photo in unit.photos.all():
        counts[photo.kind] = counts.get(photo.kind, 0) + 1
    return counts


def save_photo(unit, by, kind, client_uid, image_b64, taken_at_raw):
    """
    Store a photo of the sheet in GCS (idempotent by the phone id).

    ---

    Guarda una foto de la hoja en GCS. Si ya llegó (mismo id del
    móvil), no la duplica. S140: las fotos van después de la llegada.
    """
    from spare_parts.gcs_service import upload_bytes

    if unit.km_start is None:
        raise SheetError("Primero los km de salida.")
    if unit.km_arrival is None:
        raise SheetError("Primero la llegada, con los km.")
    if kind not in dict(Photo.KIND_CHOICES):
        raise SheetError("Tipo de foto no válido.")
    client_uid = str(client_uid or "").strip()[:64] or uuid.uuid4().hex
    existing = unit.photos.filter(client_uid=client_uid).first()
    if existing is not None:
        return existing
    try:
        data = base64.b64decode(str(image_b64 or ""), validate=True)
    except (binascii.Error, ValueError):
        raise SheetError("La foto no es válida.")
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise SheetError("La foto no es válida o es demasiado grande.")
    taken_at = client_time(taken_at_raw)
    blob_name = "%s/%s/%s/%s_%s.jpg" % (
        PHOTO_PREFIX, unit.work_order.work_order_number,
        unit.albaran_number, kind.lower(), client_uid,
    )
    upload_bytes(PHOTO_BUCKET, blob_name, data, content_type="image/jpeg")
    return Photo.objects.create(
        unit=unit, kind=kind, blob_name=blob_name, client_uid=client_uid,
        taken_at=taken_at, uploaded_by=by,
    )


def apply_order_fields(unit, data):
    """
    Save the order fields the driver filled (only those sent).

    ---

    Guarda en la orden los campos que el conductor ha rellenado (solo
    los que vienen en el envío).
    """
    work_order = unit.work_order
    changed = []
    for arg, (field, label, _required) in ORDER_FIELDS.items():
        if arg not in data:
            continue
        if field in DECIMAL_ORDER_FIELDS:
            value = decimal_or_none(data.get(arg), label)
        else:
            max_length = work_order._meta.get_field(field).max_length
            value = str(data.get(arg) or "").strip()[:max_length]
        if getattr(work_order, field) != value:
            setattr(work_order, field, value)
            changed.append(field)
    if changed:
        work_order.save(update_fields=changed + ["updated_at"])


def missing_for_signature(unit):
    """
    What is still missing before the client can sign.

    ---

    Lo que falta para que el cliente pueda firmar: km de salida, km al
    llegar, los obligatorios de la hoja y las fotos.
    """
    work_order = unit.work_order
    missing = []
    if unit.km_start is None:
        missing.append("Km salida")
    if unit.km_arrival is None:
        missing.append("Km al llegar")
    for _arg, (field, label, required) in ORDER_FIELDS.items():
        if required and getattr(work_order, field) in (None, ""):
            missing.append(label)
    counts = photo_counts(unit)
    labels = dict(Photo.KIND_CHOICES)
    for kind in required_photo_kinds(unit):
        if not counts.get(kind):
            missing.append("Fotos: %s" % labels[kind].lower())
    return missing


def bases_of(company):
    """
    Active bases of the company, for the arrival base.

    ---

    Bases activas de la empresa, para elegir la base de llegada.
    """
    return Base.objects.filter(company=company, is_active=True)
