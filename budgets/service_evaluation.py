# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/service_evaluation.py
"""
Evaluation of assistance services uploaded from a folder (H37, S142).

Every uploaded document (photo or PDF of TIREA) is read with the TIREA
extractor; with its data the route base -> pickup -> delivery -> base
is measured, the budget is priced with the active tariff of the insurer
(same engine as the budgets) and the cost is estimated with the average
costs of the company (`AssistanceCostSettings`): operators per hour,
vehicles per km and fuel per km by kind of vehicle. The yield is the
budget minus the cost. Nothing creates an order.

---

Valoración de los servicios de asistencia subidos desde una carpeta
(S142). Miguel Ángel: "con los datos del servicio vamos a calcular el
precio [...] los vamos a ordenar con la columna del presupuesto
estimado según tarifa [...] de mayor a menor y vamos a tratar de poner
el coste [...] una media de gasto [...] por operarios que tengan que
ir, por el número de vehículos que tengan que ir, con una media del
tipo de vehículo y el gasto de gasoil [...] para poder ordenarlos por
rendimiento."

- Lectura: el extractor de TIREA (`tirea_extraction`).
- Trabajo y vehículos: `dispatch_vehicle.job_for`; un vehículo con su
  operario por cada trabajo (como Alia).
- Ruta: base más cercana a la recogida → recogida → entrega → base,
  con la matriz de rutas de Google (`service_eta.Router`), más los
  tiempos de trabajo de la empresa (`AssistanceTimes`).
- Presupuesto: `services.calculate_budget` con la tarifa activa de la
  aseguradora, sin IVA y sin guardar nada.
- Coste: operarios × horas × €/h, vehículos × km × €/km y gasoil
  (km × l/100 km × €/l) según la clase de cada vehículo. Lo que falte
  de las medias se avisa en la fila y no suma.
"""
import datetime
import logging
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from budgets.models import (
    AssistanceCostSettings,
    AssistanceTimes,
    AssistanceVehicleCost,
    Base,
    Budget,
    ServiceEvaluation,
)

logger = logging.getLogger(__name__)

ACCEPTED_TYPES = (
    "image/jpeg", "image/png", "image/webp", "application/pdf",
)
# Extensions accepted from a folder whose files come without a type.
# Extensiones aceptadas de una carpeta cuyos archivos no traen tipo.
EXTENSION_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "pdf": "application/pdf",
}
CENT = Decimal("0.01")
# Notes written by compute_costs (replaced when the averages change).
# Avisos que escribe compute_costs (se reemplazan al cambiar las medias).
COST_NOTE_PREFIXES = ("Falta ", "«")
# Notes that only say what was deduced (shown as information).
# Avisos que solo dicen qué se dedujo (se muestran como información).
INFO_NOTE_PREFIXES = ("Aseguradora deducida", "Tipo de vehículo deducido")

STATE_WITHOUT_ORDER = "without"
STATE_WITH_ORDER = "with"
MAX_SORT_KEYS = 4
# Miguel Ángel: by the estimated budget, from the highest down.
# Por el presupuesto estimado, de mayor a menor.
DEFAULT_ORDER = (("budget", True),)
FILTER_KEYS = (
    "search", "state", "insurer", "date_from", "date_to", "sort",
)


def _money(value):
    """
    Decimal rounded to cents.

    ---

    Decimal redondeado a céntimos.
    """
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _norm(text):
    """
    Lowercase text without accents.

    ---

    Texto en minúsculas y sin tildes.
    """
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(
        c for c in text if not unicodedata.combining(c)
    ).lower()


# ---------------------------------------------------------------------------
# Upload.
# Subida.
# ---------------------------------------------------------------------------

def content_type_of(upload):
    """
    Accepted content type of an uploaded file, or "".

    ---

    Tipo aceptado de un archivo subido (por su tipo o, si no lo trae,
    por su extensión), o "" si no es una foto ni un PDF.
    """
    content_type = (upload.content_type or "").split(";")[0].lower()
    if content_type in ACCEPTED_TYPES:
        return content_type
    extension = upload.name.rsplit(".", 1)[-1].lower() if (
        "." in upload.name
    ) else ""
    return EXTENSION_TYPES.get(extension, "")


def queue_upload(company_user, upload, content_type):
    """
    Keep the document and queue its evaluation.

    ---

    Guarda el documento en GCS (carpeta de hojas de servicio), crea su
    valoración "En cola" y la manda al worker. Devuelve la valoración,
    o None si no se pudo guardar el documento.
    """
    from budgets.tasks import evaluate_service_task
    from chat import room_service

    blob = room_service.store_source_document(
        company_user.company, upload.read(), content_type,
    )
    if not blob:
        return None
    evaluation = ServiceEvaluation.objects.create(
        company=company_user.company,
        created_by=company_user,
        file_name=upload.name.rsplit("/", 1)[-1][:255],
        source_document_blob=blob,
        source_document_type=content_type,
    )
    transaction.on_commit(
        lambda: evaluate_service_task.delay(evaluation.pk),
    )
    return evaluation


def requeue(evaluation):
    """
    Evaluate a service again from its stored document.

    ---

    Vuelve a valorar un servicio desde su documento guardado.
    """
    from budgets.tasks import evaluate_service_task

    ServiceEvaluation.objects.filter(pk=evaluation.pk).update(
        status=ServiceEvaluation.STATUS_PENDING, error="",
    )
    transaction.on_commit(
        lambda: evaluate_service_task.delay(evaluation.pk),
    )


# ---------------------------------------------------------------------------
# Evaluation.
# Valoración.
# ---------------------------------------------------------------------------

def restore_data(data):
    """
    Extraction data as the TIREA extractor returns it.

    ---

    Datos leídos tal como los devuelve el extractor de TIREA: las
    fechas, que se guardan como texto, vuelven a ser `datetime`.
    """
    from django.utils.dateparse import parse_datetime

    from budgets.tirea_extraction import DATETIME_FIELDS

    restored = {
        key: value for key, value in (data or {}).items()
        if not key.startswith("_")
    }
    for key in DATETIME_FIELDS:
        if isinstance(restored.get(key), str):
            restored[key] = parse_datetime(restored[key])
    return restored


def _service_moment(data):
    """
    Date and time of the service, or now.

    ---

    Fecha y hora del servicio (la del documento o, si no la trae, la
    de la solicitud; en su defecto, ahora), en hora de Madrid.
    """
    when = data.get("service_datetime") or data.get("request_time")
    if not isinstance(when, datetime.datetime):
        when = timezone.now()
    if timezone.is_naive(when):
        when = timezone.make_aware(when)
    return timezone.localtime(when)


def _is_night(insurer, company, when):
    """
    Whether the moment falls in the night schedule of the insurer.

    ---

    Si el momento cae en el horario nocturno: el de la aseguradora, el
    de la empresa por defecto o el de la ficha de la empresa (mismo
    orden que `service_sheet.is_night`).
    """
    from budgets.services import _resolve_night_schedule

    source = (_resolve_night_schedule(insurer) if insurer else None) or (
        company
    )
    start, end = source.night_start, source.night_end
    if start is None or end is None:
        return False
    if isinstance(start, str):
        start = datetime.time.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.time.fromisoformat(end)
    moment = when.time()
    if start <= end:
        return start <= moment < end
    return moment >= start or moment < end


def _route(company, data, kinds, notes):
    """
    Base, km and hours of the service, base to base.

    ---

    Base más cercana a la recogida (por tiempo de trayecto), km y
    horas del circuito base → recogida → entrega → base, más los
    tiempos de trabajo de la empresa. Devuelve (base, km, horas de
    viaje, horas de trabajo) o cuatro None si no se puede medir.
    """
    from budgets.dispatch_vehicle import ON_SITE_KINDS
    from budgets.service_eta import (
        EtaError,
        Router,
        _join,
        address_point,
        base_point,
    )

    pickup = _join(
        data.get("pickup_location"), data.get("vehicle_locality"),
        data.get("pickup_province"),
    ) if data.get("pickup_location") else ""
    if not pickup:
        notes.append("Sin dirección de recogida: no se mide la ruta.")
        return None, None, None, None
    delivery_place = data.get("delivery_address") or ""
    delivery = _join(
        delivery_place, data.get("delivery_locality"),
        data.get("delivery_province"),
    ) if delivery_place else ""
    bases = [
        (base, base_point(base))
        for base in Base.objects.filter(company=company)
    ]
    bases = [(base, point) for base, point in bases if point is not None]
    if not bases:
        notes.append("No hay bases con ubicación: no se mide la ruta.")
        return None, None, None, None
    router = Router()
    pickup_point = address_point(pickup)
    try:
        matrix = router.matrix(
            [point for _base, point in bases], [pickup_point],
        )
        if not matrix:
            raise EtaError("Google no encuentra la recogida %s." % pickup)
        index = min(matrix, key=lambda key: matrix[key][0])[0]
        base, start = bases[index]
        seconds, meters = matrix[(index, 0)]
        on_site = bool(kinds) and all(k in ON_SITE_KINDS for k in kinds)
        end = pickup_point
        if delivery and not on_site:
            delivery_point = address_point(delivery)
            leg_seconds, leg_meters = router.leg(pickup_point, delivery_point)
            seconds += leg_seconds
            meters += leg_meters
            end = delivery_point
        leg_seconds, leg_meters = router.leg(end, start)
        seconds += leg_seconds
        meters += leg_meters
    except EtaError as exc:
        notes.append("Ruta no calculada: %s" % exc)
        return None, None, None, None
    times = AssistanceTimes.for_company(company)
    if on_site:
        work = times.on_site_minutes
    else:
        first = times.lift_minutes if "lift" in kinds else times.load_minutes
        work = first + (times.unload_minutes if delivery else 0)
    km = (Decimal(meters) / 1000).quantize(Decimal("0.1"))
    travel = (Decimal(seconds) / 3600).quantize(CENT)
    work_hours = (Decimal(work) / 60).quantize(CENT)
    return base, km, travel, work_hours


# ---------------------------------------------------------------------------
# Inference from the names, until the documents bring the data (S142).
# Deducción por los nombres, hasta que los documentos traigan el dato.
# ---------------------------------------------------------------------------

# Words of an insurer name that do not tell which insurer it is.
# Palabras del nombre de una aseguradora que no dicen cuál es.
GENERIC_INSURER_WORDS = {
    "asistencia", "assistance", "seguros", "seguro", "compania", "cia",
    "sa", "sl", "slu", "s", "a", "l", "de", "y", "del", "la", "el",
}


def _brand_words(name):
    """
    Words of an insurer name that tell which insurer it is, in order.

    ---

    Palabras de un nombre de aseguradora que dicen cuál es, en orden.
    """
    from budgets.views_services import _plain

    return [w for w in _plain(name).split() if w not in GENERIC_INSURER_WORDS]


def infer_insurer(company, data):
    """
    Insurer card inferred from the read name, or None.

    ---

    Ficha de aseguradora deducida del nombre leído cuando el alta de
    TIREA no la reconoce (Miguel Ángel, S142: "inferirlo del nombre
    hasta el martes"). Entre las fichas de la empresa del grupo del CIF
    del documento (todas, si no hay CIF del grupo), las que comparten
    alguna palabra de marca con el nombre leído; si son varias, la que
    empieza por la primera palabra leída ("RACC ASISTENCIA" -> "RACC -
    Zurich", no "Zurich - RACC"). None si no queda una sola.
    """
    from budgets.models import Insurer
    from budgets.views_services import _plain, own_company_for_tax_id

    read = _brand_words(data.get("insurer_name"))
    if not read:
        return None
    insurers = list(Insurer.objects.filter(company=company, is_active=True))
    profile = own_company_for_tax_id(data.get("company_tax_id"))
    if profile is not None:
        own = [_plain(profile.legal_name)] + [
            _plain(alias) for alias in profile.name_aliases.splitlines()
            if alias.strip()
        ]
        mine = [
            insurer for insurer in insurers
            if _brand_words(insurer.service_company_name)
            and any(
                all(w in name.split() for w in _brand_words(
                    insurer.service_company_name,
                ))
                for name in own
            )
        ]
        insurers = mine or insurers
    candidates = [
        insurer for insurer in insurers
        if set(read) & set(_brand_words(insurer.insurer_company_name))
    ]
    if len(candidates) > 1:
        candidates = [
            insurer for insurer in candidates
            if _brand_words(insurer.insurer_company_name)[:1] == read[:1]
        ]
    return candidates[0] if len(candidates) == 1 else None


def _kg_range(name):
    """
    (from, to) kilograms of a tariff vehicle type, or None.

    ---

    Tramo de kilos de un tipo de vehículo de la tarifa ("3.500 Kg. -
    5.000 Kg.", "> 20.000 Kg.", "Camiones hasta 8.000 KG"), o None si
    el nombre no lleva kilos.
    """
    import re

    text = _norm(name)
    if "kg" not in text:
        return None
    numbers = [
        int(n.replace(".", ""))
        for n in re.findall(r"\d{1,3}(?:\.\d{3})+|\d{4,}", text)
    ]
    if not numbers:
        return None
    if ">" in text or "mas de" in text:
        return numbers[0], float("inf")
    if len(numbers) == 1:
        return 0, numbers[0]
    return numbers[0], numbers[1]


def infer_vehicle_type(insurer, data, job):
    """
    Tariff vehicle type inferred from the service, or (None, "").

    ---

    Tipo de vehículo de la tarifa deducido cuando el documento no trae
    uno reconocible (S142, hasta que lo traiga): reparación in situ ->
    furgón taller / coche piloto; semirremolque o tractora -> cabezas
    tractoras; autobús -> autocares; con peso, el tramo de kilos que le
    toca; sin peso, turismo si la tarifa lo tiene y, si no, el tramo
    más bajo (estimado a la baja). Devuelve (tipo, motivo).
    """
    from budgets.dispatch_vehicle import ON_SITE_KINDS, _weight_kg

    types = list(insurer.vehicle_types.filter(is_active=True))
    if not types:
        return None, ""

    def named(*words):
        for vehicle_type in types:
            if any(word in _norm(vehicle_type.name) for word in words):
                return vehicle_type
        return None

    kinds = job.get("trabajos") or []
    text = _norm(" ".join(str(data.get(field) or "") for field in (
        "vehicle_brand", "vehicle_model", "vehicle_subtype_label",
        "breakdown_description", "insurer_comments",
    )))
    if kinds and all(kind in ON_SITE_KINDS for kind in kinds):
        found = named("taller", "piloto")
        if found:
            return found, "reparación in situ"
    if "semitrailer" in kinds or "tractora" in text:
        found = named("tractora")
        if found:
            return found, "tractora"
    if any(word in text for word in ("autobus", "autocar")):
        found = named("autocar", "autobus")
        if found:
            return found, "autobús"
    ranges = [
        (vehicle_type, _kg_range(vehicle_type.name)) for vehicle_type in types
    ]
    ranges = [(vt, r) for vt, r in ranges if r is not None]
    weight = _weight_kg(data)
    if weight is not None:
        for vehicle_type, (low, high) in ranges:
            if low <= weight <= high:
                return vehicle_type, "%d kg" % weight
    if not job.get("pesado"):
        found = named("turismo")
        if found:
            return found, "vehículo ligero"
    if ranges:
        lowest = min(ranges, key=lambda item: item[1][0])[0]
        return lowest, "sin peso: tramo más bajo"
    return None, ""


def _budget_amount(evaluation, when, notes):
    """
    Estimated budget by the active tariff, without IVA, or None.

    ---

    Presupuesto estimado con la tarifa activa de la aseguradora, sin
    IVA y sin guardar nada (mismo motor que los presupuestos y la
    simulación de factura), o None si faltan datos o tarifa.
    """
    from budgets.services import calculate_budget

    if evaluation.insurer is None:
        notes.append("Aseguradora no reconocida: sin presupuesto.")
        return None
    if evaluation.vehicle_type is None:
        notes.append(
            "Tipo de vehículo no reconocido en la tarifa: sin presupuesto.",
        )
        return None
    if evaluation.km is None:
        return None
    budget = Budget(
        company=evaluation.company,
        insurer=evaluation.insurer,
        vehicle_type=evaluation.vehicle_type,
        base=evaluation.base,
        service_date=when.date(),
        service_time=when.time().replace(microsecond=0),
        km_phase1=evaluation.km,
        is_night=_is_night(evaluation.insurer, evaluation.company, when),
        route_calculation_mode=Budget.ROUTE_MODE_MANUAL,
        apply_iva=False,
    )
    try:
        calculate_budget(budget)
    except Exception as exc:  # noqa: BLE001 -- se avisa en la fila
        logger.warning("# [VALORACION] Presupuesto no calculado: %s", exc)
        notes.append("Presupuesto no calculado: %s" % exc)
        return None
    if not budget.total_amount:
        # S142: a tariff without prices for this vehicle type gives 0 €,
        # which is not a budget (it made the yield negative).
        # Una tarifa sin precios para este tipo da 0 €, que no es un
        # presupuesto (dejaba el rendimiento en negativo).
        notes.append(
            "La tarifa de %s no tiene precios para «%s»: sin "
            "presupuesto." % (
                evaluation.insurer.name, evaluation.vehicle_type.name,
            ),
        )
        return None
    return _money(budget.total_amount)


def _vehicle_classes(company):
    """
    Cost class of every machine type of the company.

    ---

    Clase de coste (`AssistanceVehicleCost`) de cada tipo de máquina.
    """
    classes = {}
    for vehicle in AssistanceVehicleCost.objects.filter(company=company):
        for type_name in vehicle.type_names():
            classes.setdefault(_norm(type_name), vehicle)
    return classes


def _crew_types(kinds):
    """
    Machine type of the vehicle of each job (the first that fits).

    ---

    Tipo de máquina del vehículo de cada trabajo: el primero de los
    que lo hacen (`dispatch_vehicle`), uno por trabajo.
    """
    from budgets.dispatch_vehicle import JOB_TYPES, TOW_TYPES

    return [
        (TOW_TYPES.get(kind) or JOB_TYPES[kind])[0] for kind in kinds
    ]


def _split_hours(evaluation):
    """
    (travel hours, work hours) of an evaluation, or (None, None).

    ---

    (horas de viaje, horas de trabajo) guardadas al valorar; las
    valoraciones anteriores a S142 (tarde) no las tienen: (None, None).
    """
    data = evaluation.data or {}
    travel, work = data.get("_travel_hours"), data.get("_work_hours")
    if travel is None or work is None:
        return None, None
    return Decimal(str(travel)), Decimal(str(work))


def crew_hours_for(vehicle, km, travel, work, hours):
    """
    Hours of one crew: work plus the longer of the two travel times.

    ---

    Horas de un equipo: el trabajo más el viaje, el que sea mayor de
    los dos: el de Google o el de los km a la velocidad máxima de su
    clase (Miguel Ángel, S142: una grúa de gran tonelaje va como mucho a
    75 km/h, "como mínimo va a tardar"), más los tiempos muertos de la
    clase ("siempre hay tiempos muertos"). Sin el desglose (valoraciones
    antiguas), las horas totales más los tiempos muertos.
    """
    dead = (
        vehicle.dead_time_hours
        if vehicle is not None and vehicle.dead_time_hours else Decimal("0")
    )
    if travel is None:
        return hours + dead
    if vehicle is not None and vehicle.max_speed_kmh:
        travel = max(travel, km / Decimal(vehicle.max_speed_kmh))
    return travel + work + dead


def compute_costs(evaluation, settings=None, classes=None):
    """
    Estimated cost and yield of an evaluated service (no save).

    ---

    Coste estimado y rendimiento de un servicio valorado, con las
    medias vigentes (sin guardar). Se recalcula sin volver a leer el
    documento ni a medir la ruta cuando cambian las medias. Devuelve
    la lista de avisos de las medias que faltan.
    """
    settings = settings or AssistanceCostSettings.for_company(
        evaluation.company,
    )
    classes = classes if classes is not None else _vehicle_classes(
        evaluation.company,
    )
    notes = []
    crew_types = (evaluation.data or {}).get("_crew_types") or []
    if evaluation.km is None or evaluation.hours is None or not crew_types:
        evaluation.operators_cost = None
        evaluation.vehicles_cost = None
        evaluation.fuel_cost = None
        evaluation.total_cost = None
        evaluation.margin = None
        return notes
    km, hours = evaluation.km, evaluation.hours
    travel, work = _split_hours(evaluation)
    operator_hours = Decimal("0")
    vehicles = Decimal("0")
    fuel = Decimal("0")
    vehicles_known = fuel_known = True
    for type_name in crew_types:
        vehicle = classes.get(_norm(type_name))
        crew_hours = crew_hours_for(vehicle, km, travel, work, hours)
        operator_hours += crew_hours
        if vehicle is None:
            notes.append("«%s» no está en ninguna clase de vehículo." % (
                type_name,
            ))
            vehicles_known = fuel_known = False
            continue
        if vehicle.cost_per_km is None:
            vehicles_known = False
            notes.append("Falta el coste por km de %s." % vehicle.name)
        else:
            vehicles += km * vehicle.cost_per_km
        if settings.fuel_price_per_liter is None:
            fuel_known = False
        elif vehicle.fuel_liters_per_hour:
            # Hour-metered (mobile cranes): litres per hour of the crew.
            # Por horas (grúas móviles): litros por hora del equipo.
            fuel += (
                crew_hours * vehicle.fuel_liters_per_hour
                * settings.fuel_price_per_liter
            )
        else:
            fuel += (
                km * vehicle.fuel_liters_per_100km / 100
                * settings.fuel_price_per_liter
            )
    if settings.fuel_price_per_liter is None:
        notes.append("Falta el precio del gasoil.")
    operators = None
    if settings.operator_cost_per_hour is None:
        notes.append("Falta el coste por hora de operario.")
    else:
        operators = _money(operator_hours * settings.operator_cost_per_hour)
    evaluation.operators_cost = operators
    evaluation.vehicles_cost = _money(vehicles) if vehicles_known else None
    evaluation.fuel_cost = _money(fuel) if fuel_known else None
    parts = [
        part for part in (
            evaluation.operators_cost, evaluation.vehicles_cost,
            evaluation.fuel_cost,
        ) if part is not None
    ]
    evaluation.total_cost = _money(sum(parts)) if parts else None
    evaluation.margin = (
        _money(evaluation.budget_amount - evaluation.total_cost)
        if evaluation.budget_amount is not None
        and evaluation.total_cost is not None else None
    )
    return notes


def evaluate(evaluation_pk):
    """
    Read, measure, price and cost one uploaded service.

    ---

    Lee el documento, mide la ruta, calcula el presupuesto y el coste
    de un servicio subido, y lo deja "Valorado" (o "Error" con el
    motivo). Lo llama el worker (`budgets.tasks`).
    """
    from budgets.dispatch_vehicle import JOB_LABELS, job_for
    from budgets.tirea_extraction import extract_tirea_albaran
    from budgets.views_services import _initial_from_extraction
    from chat.room_service import ATTACHMENT_BUCKET
    from spare_parts.gcs_service import download_bytes

    evaluation = ServiceEvaluation.objects.select_related("company").filter(
        pk=evaluation_pk,
    ).first()
    if evaluation is None:
        return
    ServiceEvaluation.objects.filter(pk=evaluation.pk).update(
        status=ServiceEvaluation.STATUS_PROCESSING,
    )
    company = evaluation.company
    logger.info("# [VALORACION] Valorando %s (%s).", evaluation.pk,
                evaluation.file_name)
    try:
        content = download_bytes(
            ATTACHMENT_BUCKET, evaluation.source_document_blob,
        )
        data = extract_tirea_albaran(
            content, evaluation.source_document_type,
        )
        notes = []
        initial = _initial_from_extraction(company, data)
        evaluation.insurer_id = initial.get("insurer")
        evaluation.vehicle_type_id = initial.get("vehicle_type")
        job = job_for(data) or {"trabajos": ["tow_light"], "pesado": False}
        kinds = job["trabajos"]
        if evaluation.insurer_id is None:
            insurer = infer_insurer(company, data)
            if insurer is not None:
                evaluation.insurer = insurer
                notes.append("Aseguradora deducida del nombre: %s." % (
                    insurer.name,
                ))
        if evaluation.insurer_id and evaluation.vehicle_type_id is None:
            vehicle_type, reason = infer_vehicle_type(
                evaluation.insurer, data, job,
            )
            if vehicle_type is not None:
                evaluation.vehicle_type = vehicle_type
                notes.append("Tipo de vehículo deducido (%s): %s." % (
                    reason, vehicle_type.name.rstrip("."),
                ))
        crew_types = _crew_types(kinds)
        evaluation.crews = len(crew_types)
        evaluation.job_label = "; ".join(
            JOB_LABELS[kind] for kind in kinds
        )[:255]
        base, km, travel, work_hours = _route(company, data, kinds, notes)
        evaluation.base = base
        evaluation.km = km
        evaluation.hours = (
            travel + work_hours if travel is not None else None
        )
        when = _service_moment(data)
        evaluation.budget_amount = _budget_amount(evaluation, when, notes)
        evaluation.data = dict(
            data, _crew_types=crew_types,
            _travel_hours=travel, _work_hours=work_hours,
        )
        notes += compute_costs(evaluation)
        evaluation.notes = "\n".join(notes)
        evaluation.status = ServiceEvaluation.STATUS_DONE
        evaluation.error = ""
    except Exception as exc:  # noqa: BLE001 -- se ve en la fila
        logger.exception("# [VALORACION] Error valorando %s.", evaluation.pk)
        evaluation.status = ServiceEvaluation.STATUS_ERROR
        evaluation.error = str(exc)[:1000]
    evaluation.processed_at = timezone.now()
    evaluation.save()
    logger.info("# [VALORACION] %s: %s.", evaluation.pk, evaluation.status)


def recompute_company(company):
    """
    Recompute the cost of every evaluated service of a company.

    ---

    Recalcula el coste y el rendimiento de todos los servicios
    valorados de la empresa con las medias vigentes (al guardarlas).
    """
    settings = AssistanceCostSettings.for_company(company)
    classes = _vehicle_classes(company)
    fields = [
        "operators_cost", "vehicles_cost", "fuel_cost", "total_cost",
        "margin", "notes", "budget_amount",
    ]
    for evaluation in ServiceEvaluation.objects.filter(
        company=company, status=ServiceEvaluation.STATUS_DONE,
    ).select_related("insurer", "vehicle_type"):
        kept = [
            line for line in evaluation.notes.splitlines()
            if not line.startswith(COST_NOTE_PREFIXES)
        ]
        if evaluation.budget_amount == 0:
            # Valued before S142 (tarde): a 0 € budget is a tariff
            # without prices for the type, not a budget.
            # Valorado antes del cambio: 0 € es una tarifa sin precios
            # para el tipo, no un presupuesto.
            evaluation.budget_amount = None
            kept.append(
                "La tarifa de %s no tiene precios para «%s»: sin "
                "presupuesto." % (
                    evaluation.insurer.name if evaluation.insurer else "?",
                    evaluation.vehicle_type.name
                    if evaluation.vehicle_type else "?",
                ),
            )
        notes = compute_costs(evaluation, settings, classes)
        evaluation.notes = "\n".join(kept + notes)
        evaluation.save(update_fields=fields)


# ---------------------------------------------------------------------------
# List (directive 4.24).
# Listado (directriz 4.24).
# ---------------------------------------------------------------------------

def _num(value):
    """
    Float of a decimal, or None.

    ---

    Float de un decimal, o None.
    """
    return float(value) if value is not None else None


SORTABLE = {
    "budget": lambda row: _num(row.evaluation.budget_amount),
    "cost": lambda row: _num(row.evaluation.total_cost),
    "margin": lambda row: _num(row.evaluation.margin),
    "km": lambda row: _num(row.evaluation.km),
    "hours": lambda row: _num(row.evaluation.hours),
    "date": lambda row: row.service_at.timestamp() if row.service_at
    else None,
    "insurer": lambda row: _norm(row.insurer) or None,
    "file": lambda row: _norm(row.evaluation.file_name) or None,
    "uploaded": lambda row: row.evaluation.created_at.timestamp(),
}


class EvaluationRow:
    """
    One row of the list: an uploaded service.

    ---

    Una fila del listado: un servicio subido, con lo que pinta la
    tabla resuelto aquí (plantillas tontas).
    """

    def __init__(self, evaluation):
        from budgets.service_eta import _join

        self.evaluation = evaluation
        self.key = "e%d" % evaluation.pk
        data = restore_data(evaluation.data)
        when = data.get("service_datetime") or data.get("request_time")
        self.service_at = (
            timezone.localtime(when) if isinstance(when, datetime.datetime)
            and timezone.is_aware(when) else when
        )
        self.insurer = (
            evaluation.insurer.name if evaluation.insurer
            else data.get("insurer_name") or ""
        )
        self.expediente = data.get("expediente") or ""
        self.plate = data.get("vehicle_plate") or ""
        self.vehicle = (
            evaluation.vehicle_type.name if evaluation.vehicle_type
            else data.get("vehicle_type_label") or ""
        )
        self.pickup = _join(
            data.get("pickup_location"), data.get("vehicle_locality"),
        )
        self.delivery = _join(
            data.get("delivery_address"), data.get("delivery_locality"),
        )
        self.label = " · ".join(
            part for part in (
                self.expediente or evaluation.file_name, self.insurer,
                self.plate,
            ) if part
        )
        lines = [line for line in evaluation.notes.splitlines() if line]
        # S142: what was deduced is information, not a warning; the
        # warning triangle is only for what is missing.
        # Lo deducido es información, no aviso: el triángulo naranja
        # queda solo para lo que falta.
        self.infos = [
            line for line in lines if line.startswith(INFO_NOTE_PREFIXES)
        ]
        self.notes = [
            line for line in lines
            if not line.startswith(INFO_NOTE_PREFIXES)
        ]
        self.is_done = evaluation.status == ServiceEvaluation.STATUS_DONE
        self.is_error = evaluation.status == ServiceEvaluation.STATUS_ERROR
        self.is_waiting = not (self.is_done or self.is_error)
        self.margin_negative = (
            evaluation.margin is not None and evaluation.margin < 0
        )
        self.can_create_order = (
            self.is_done and evaluation.work_order_id is None
        )
        self.phrase = _norm(" ".join(str(part) for part in (
            evaluation.file_name, self.insurer, self.expediente, self.plate,
            self.vehicle, self.pickup, self.delivery, evaluation.job_label,
            data.get("vehicle_brand"), data.get("vehicle_model"),
            data.get("breakdown_description"), data.get("client_name"),
            evaluation.base.name if evaluation.base else "",
        ) if part))


def parse_sort(raw):
    """
    [(key, descending), ...] of a sort value, at most MAX_SORT_KEYS.

    ---

    [(clave, descendente), ...] de un valor de orden, como mucho
    MAX_SORT_KEYS (directriz 4.24).
    """
    keys = []
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in SORTABLE and key not in [k for k, _d in keys]:
            keys.append((key, token.startswith("-")))
    return keys[:MAX_SORT_KEYS]


def sort_controls(raw):
    """
    Sort value of each header click, arrows and priorities.

    ---

    Para cada columna ordenable, el valor de "sort" de un clic en su
    cabecera, su flecha y su prioridad (mismo criterio que la pestaña
    Albaranes, `assistance_albaranes.sort_controls`).
    """
    keys = parse_sort(raw)
    active = [key for key, _desc in keys]
    cols = {}
    for key in SORTABLE:
        if key in active:
            idx = active.index(key)
            desc = keys[idx][1]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(keys) > 1 else ""
            new = [(key, (not desc) if idx == 0 else desc)] + [
                (k, d) for k, d in keys if k != key
            ]
        else:
            arrow, priority = "", ""
            # Amounts start from the highest; the rest, A to Z.
            # Los importes empiezan por el mayor; lo demás, de la A a la Z.
            first_desc = key in ("budget", "cost", "margin", "km", "hours",
                                 "date", "uploaded")
            new = [(key, first_desc)] + keys
        cols[key] = {
            "next": ",".join(
                ("-" if d else "") + k for k, d in new[:MAX_SORT_KEYS]
            ),
            "arrow": arrow,
            "priority": priority,
        }
    return {
        "sort_cols": cols,
        "sort_active": bool(keys),
        "current_sort": ",".join(("-" if d else "") + k for k, d in keys),
    }


def _sort_rows(rows, keys):
    """
    Stable sort by several keys; empty values always at the end.

    ---

    Orden estable por varias claves, la primera la más importante; los
    valores vacíos (sin presupuesto, sin coste...) siempre al final.
    Sin orden elegido: presupuesto estimado de mayor a menor.
    """
    for key, desc in reversed(list(keys or DEFAULT_ORDER)):
        getter = SORTABLE[key]
        present = [row for row in rows if getter(row) is not None]
        missing = [row for row in rows if getter(row) is None]
        present.sort(key=getter, reverse=desc)
        rows = present + missing
    return rows


def _date(raw):
    """
    Date of a filter (YYYY-MM-DD), or None.

    ---

    Fecha de un filtro (AAAA-MM-DD), o None.
    """
    try:
        return datetime.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def build_rows(company, params, only_keys=None):
    """
    Rows of the list with the filters and the order applied.

    ---

    Filas del listado con los filtros y el orden aplicados. `state`:
    "" con y sin orden, "without", "with", "none" ninguno (semántica
    literal de casilla). Con `only_keys` (mostrar solo la selección)
    se ignoran estado, aseguradora y fechas.
    """
    evaluations = ServiceEvaluation.objects.filter(
        company=company,
    ).select_related("insurer", "vehicle_type", "base")
    rows = [EvaluationRow(evaluation) for evaluation in evaluations]
    if only_keys is not None:
        rows = [row for row in rows if row.key in only_keys]
    else:
        state = params.get("state", "")
        if state == "none":
            return []
        if state == STATE_WITHOUT_ORDER:
            rows = [r for r in rows if r.evaluation.work_order_id is None]
        elif state == STATE_WITH_ORDER:
            rows = [r for r in rows if r.evaluation.work_order_id]
        insurer = (params.get("insurer") or "").strip()
        if insurer.isdigit():
            rows = [
                r for r in rows if r.evaluation.insurer_id == int(insurer)
            ]
        date_from = _date(params.get("date_from"))
        date_to = _date(params.get("date_to"))
        if date_from or date_to:
            rows = [
                r for r in rows if r.service_at
                and (not date_from or r.service_at.date() >= date_from)
                and (not date_to or r.service_at.date() <= date_to)
            ]
    words = _norm(params.get("search") or "").split()
    if words:
        rows = [r for r in rows if all(w in r.phrase for w in words)]
    return _sort_rows(rows, parse_sort(params.get("sort")))
