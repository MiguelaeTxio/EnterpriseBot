# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/gasoges_sync.py
"""
H30 (S135). Sync of GasoGes into the database: users, vehicles,
supplies, units and readings.

---

H30 (S135). Sincronización de GasoGes con la BD, punto 4 de la hoja de
ruta S135 (con la ampliación de Miguel Ángel en la misma sesión):
1. Usuarios: cruzados por nombre con su ficha (para el WhatsApp).
2. Vehículos: uno por registro de GasoGes, enlazado con su centro de
   gasto por matrícula o código (varios registros por máquina).
3. Suministros: pedidos día a día (la API corta a 1.000 por petición)
   y guardados una sola vez.
4. Unidad de cada vehículo (km u horas), deducida si es clara; si no,
   queda sin saber y la confirmará el chófer.
5. Lecturas: solo de los suministros que pasan la comprobación; los
   dudosos quedan marcados, sin lectura.

Todas las funciones reciben `log` (una función que escribe una línea).
"""
from datetime import datetime
from datetime import time
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation

from django.db import transaction
from django.utils import timezone

from document_explorer.models import PersonIdentity
from fleet.gasoges_client import GasoGesClient
from fleet.gasoges_client import GasoGesError
from fleet.gasoges_rules import check_reading
from fleet.gasoges_rules import deduce_unit
from fleet.gasoges_rules import name_matches
from fleet.gasoges_rules import normalize
from fleet.gasoges_rules import typical_value
from fleet.models import GasoGesSupply
from fleet.models import GasoGesUser
from fleet.models import GasoGesVehicle
from fleet.models import MachineAsset
from fleet.models import MachineMeterReading

API_PAGE_LIMIT = 1000
UNIT_WINDOW_SUPPLIES = 40


def _person_name(person):
    """
    Full name of a worker.

    ---

    Nombre completo de una ficha.
    """
    return " ".join(part for part in (
        person.given_name, person.first_surname, person.second_surname,
    ) if part)


def sync_users(client, log):
    """
    Store GasoGes users and match the unmatched ones with a worker.

    Active workers first; if none matches, any worker. Only a single
    match is taken. Returns a counters dict.

    ---

    Guarda los usuarios de GasoGes y cruza con una ficha los que aún no
    la tienen: primero entre los trabajadores activos y, si ninguno
    casa, entre todos. Solo se acepta un único resultado.
    """
    people = [(p, _person_name(p), p.is_active_employee)
              for p in PersonIdentity.objects.all()]
    counters = {"usuarios": 0, "cruzados_ahora": 0, "sin_ficha": 0,
                "varios": 0}
    for row in client.users():
        counters["usuarios"] += 1
        user, _created = GasoGesUser.objects.get_or_create(
            gasoges_id=row["user_id"])
        user.name = (row["name"] or "").strip()
        if user.person_id is None:
            hits = [p for p, full, _a in people
                    if name_matches(user.name, full)]
            active = [p for p in hits if p.is_active_employee]
            chosen = active if active else hits
            if len(chosen) == 1:
                user.person = chosen[0]
                user.match_note = "cruzado por nombre%s" % (
                    "" if chosen[0].is_active_employee else " (inactivo)")
                counters["cruzados_ahora"] += 1
            elif chosen:
                user.match_note = "varias fichas: " + ", ".join(
                    _person_name(p) for p in chosen[:4])
                counters["varios"] += 1
            else:
                user.match_note = "sin ficha"
                counters["sin_ficha"] += 1
        user.save()
    log("Usuarios: %(usuarios)d; cruzados ahora %(cruzados_ahora)d, "
        "sin ficha %(sin_ficha)d, varias fichas %(varios)d." % counters)
    return counters


def _machine_candidates(plate, raw_name, by_plate, by_code):
    """
    Cost centres matching a GasoGes vehicle, and how.

    ---

    Centros de gasto que casan con un vehículo de GasoGes y por qué vía
    (Miguel Ángel, S135, opción A.1): matrícula; código en MATRICULA;
    código en NOMBRE; código en una palabra del NOMBRE.
    """
    name = normalize(raw_name)
    if plate and by_plate.get(plate):
        return by_plate[plate], "matrícula"
    if plate and by_code.get(plate):
        return by_code[plate], "código en MATRICULA"
    if name and by_code.get(name):
        return by_code[name], "código en NOMBRE"
    found = {}
    for word in str(raw_name or "").split():
        for asset in by_code.get(normalize(word), []):
            found[asset.pk] = asset
    if found:
        return list(found.values()), "código dentro del NOMBRE"
    return [], ""


def sync_vehicles(client, log):
    """
    Store GasoGes vehicles and link the unlinked ones with a machine.

    A vehicle already linked is never relinked (a manual link stays).

    ---

    Guarda los vehículos de GasoGes y enlaza con su centro de gasto los
    que aún no lo tienen. Uno ya enlazado no se toca. Lo dudoso (varios
    centros de gasto) queda sin enlazar, con el motivo.
    """
    by_plate = {}
    by_code = {}
    for asset in MachineAsset.objects.all():
        if normalize(asset.plate):
            by_plate.setdefault(normalize(asset.plate), []).append(asset)
        by_code.setdefault(normalize(asset.code), []).append(asset)
    counters = {"vehiculos": 0, "enlazados_ahora": 0, "sin_enlace": 0}
    for row in client.vehicles():
        counters["vehiculos"] += 1
        vehicle, _created = GasoGesVehicle.objects.get_or_create(
            gasoges_id=row["vehicle_id"])
        vehicle.plate = (row["plate"] or "").strip()
        vehicle.name = (row["name"] or "").strip()
        vehicle.last_km = row["last_km"]
        if vehicle.machine_id is None:
            candidates, how = _machine_candidates(
                normalize(vehicle.plate), vehicle.name, by_plate, by_code)
            if len(candidates) == 1:
                vehicle.machine = candidates[0]
                vehicle.link_method = how
                counters["enlazados_ahora"] += 1
            else:
                vehicle.link_method = (
                    "varios centros de gasto: " + ", ".join(
                        a.code for a in candidates)
                    if candidates else "sin coincidencia")[:40]
                counters["sin_enlace"] += 1
        vehicle.save()
    log("Vehículos: %(vehiculos)d; enlazados ahora %(enlazados_ahora)d, "
        "sin centro de gasto %(sin_enlace)d." % counters)
    return counters


def _decimal(value):
    """
    Decimal from an API number, or None.

    ---

    Decimal a partir de un número de la API, o None.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _supply_key(row):
    """
    Unique key of one supply (the API gives no supply id).

    ---

    Clave única de un suministro (la API no da ID de suministro).
    """
    when = row["datetime"]
    stamp = (when.strftime("%Y%m%d%H%M%S")
             if isinstance(when, datetime) else str(when))
    return "%s|%s|%s|%s|%s" % (
        row["vehicle_id"], stamp, row["km"], row["litres"],
        row["pump_serial"])[:120]


def sync_supplies(client, start, end, log, heartbeat=None):
    """
    Store the supplies between two dates, one API call per day.

    ---

    Guarda los suministros entre dos fechas, una petición por día (la
    API corta a 1.000 por petición: S135). Un día que devuelva 1.000 se
    avisa en el log, porque puede faltar algo. No duplica nada.
    """
    users = {u.gasoges_id: u for u in GasoGesUser.objects.all()}
    vehicles = {v.gasoges_id: v for v in GasoGesVehicle.objects.all()}
    counters = {"dias": 0, "leidos": 0, "nuevos": 0, "dias_al_tope": 0,
                "dias_con_error": 0}
    total_days = (end - start).days + 1
    day = start
    while day <= end:
        counters["dias"] += 1
        try:
            rows = client.supplies(day, day)
        except GasoGesError as exc:
            # S135: el 04/01/2026 GasoGes no devolvió una lista y paró
            # la carga entera. Un día raro se apunta y se sigue; un
            # error de credenciales (401) sí para todo.
            # ---
            # One odd day is logged and skipped; a 401 stops everything.
            if "401" in str(exc):
                raise
            counters["dias_con_error"] += 1
            log("AVISO: %s sin leer -- %s" % (day, exc))
            rows = []
        counters["leidos"] += len(rows)
        if len(rows) >= API_PAGE_LIMIT:
            counters["dias_al_tope"] += 1
            log("AVISO: %s devolvió %d suministros (el tope de la API); "
                "puede faltar alguno." % (day, len(rows)))
        for row in rows:
            if not isinstance(row["datetime"], datetime):
                log("AVISO: suministro sin fecha válida, se salta: %s"
                    % row["datetime"])
                continue
            vehicle = vehicles.get(row["vehicle_id"])
            if vehicle is None:
                vehicle, _c = GasoGesVehicle.objects.get_or_create(
                    gasoges_id=row["vehicle_id"])
                vehicles[vehicle.gasoges_id] = vehicle
            _supply, created = GasoGesSupply.objects.get_or_create(
                dedupe_key=_supply_key(row),
                defaults={
                    "vehicle": vehicle,
                    "user": users.get(row["user_id"]),
                    "gasoges_user_id": row["user_id"],
                    "supplied_at": timezone.make_aware(row["datetime"]),
                    "meter_value": row["km"],
                    "litres": _decimal(row["litres"]),
                    "price": _decimal(row["price"]),
                    "pump_serial": row["pump_serial"],
                    "tank_id": row["tank_id"],
                    "fuel_id": row["fuel_id"],
                },
            )
            counters["nuevos"] += int(created)
        if heartbeat:
            heartbeat(counters["dias"], total_days, counters)
        day += timedelta(days=1)
    log("Suministros: %(dias)d días, %(leidos)d leídos, %(nuevos)d "
        "nuevos, %(dias_al_tope)d días al tope de la API, "
        "%(dias_con_error)d días sin leer." % counters)
    return counters


def deduce_units(log):
    """
    Deduce the unit of linked vehicles still without a confirmed one.

    ---

    Deduce la unidad de los vehículos enlazados que no la tienen
    confirmada (sin saber o deducida antes); nunca toca la confirmada
    por el chófer ni la puesta a mano.
    """
    counters = {"km": 0, "horas": 0, "sin_saber": 0}
    vehicles = GasoGesVehicle.objects.filter(
        machine__isnull=False,
        unit_source__in=["", GasoGesVehicle.UNIT_SOURCE_DEDUCED],
    ).select_related("machine")
    for vehicle in vehicles:
        # Los últimos suministros del vehículo, no los de los últimos
        # días desde hoy: en la carga inicial pueden ser antiguos.
        # ---
        # The vehicle's latest supplies, whatever their age.
        points = list(vehicle.supplies.order_by(
            "-supplied_at").values_list(
            "supplied_at", "meter_value")[:UNIT_WINDOW_SUPPLIES])
        unit, reason = deduce_unit(
            vehicle.machine.has_odometer, vehicle.machine.has_engine_hours,
            points)
        vehicle.unit = unit
        vehicle.unit_source = (GasoGesVehicle.UNIT_SOURCE_DEDUCED
                               if unit != GasoGesVehicle.UNIT_UNKNOWN
                               else "")
        vehicle.save(update_fields=["unit", "unit_source", "updated_at"])
        key = {"KM": "km", "HOURS": "horas"}.get(unit, "sin_saber")
        counters[key] += 1
        if unit == GasoGesVehicle.UNIT_UNKNOWN and points:
            log("Unidad sin saber: %s (GasoGes %s) -- %s." % (
                vehicle.machine.code, vehicle.gasoges_id, reason))
    log("Unidades deducidas: km %(km)d, horas %(horas)d, sin saber "
        "%(sin_saber)d." % counters)
    return counters


def _previous_reading(machine, field, day):
    """
    Last reading of a machine with that field, on or before a day.

    ---

    Última lectura de la máquina con ese dato, ese día o antes.
    """
    return MachineMeterReading.objects.filter(
        machine=machine, reading_date__lte=day,
        **{"%s__isnull" % field: False},
    ).order_by("-reading_date", "-id").first()


def build_readings(log, heartbeat=None):
    """
    Turn credible supplies into meter readings, in time order.

    ---

    Convierte en lecturas los suministros creíbles, por orden de fecha.
    Vuelve a mirar los que estaban pendientes, sin centro de gasto o
    sin unidad (pueden haberse resuelto); los dudosos no se tocan.
    """
    pending = GasoGesSupply.objects.filter(status__in=[
        GasoGesSupply.STATUS_PENDING, GasoGesSupply.STATUS_NO_MACHINE,
        GasoGesSupply.STATUS_NO_UNIT,
    ]).select_related("vehicle", "vehicle__machine").order_by(
        "supplied_at", "id")
    total = pending.count()
    counters = {"lecturas": 0, "dudosos": 0, "sin_centro": 0,
                "sin_unidad": 0}
    typicals = {}
    for done, supply in enumerate(pending.iterator(), start=1):
        vehicle = supply.vehicle
        if vehicle.machine_id is None:
            supply.status = GasoGesSupply.STATUS_NO_MACHINE
            supply.status_note = ""
            counters["sin_centro"] += 1
        elif vehicle.unit == GasoGesVehicle.UNIT_UNKNOWN:
            supply.status = GasoGesSupply.STATUS_NO_UNIT
            supply.status_note = ""
            counters["sin_unidad"] += 1
        else:
            field = "km" if vehicle.unit == GasoGesVehicle.UNIT_KM else (
                "hours")
            local = timezone.localtime(supply.supplied_at)
            previous = _previous_reading(vehicle.machine, field,
                                         local.date())
            previous_value = getattr(previous, field) if previous else None
            previous_when = (timezone.make_aware(datetime.combine(
                previous.reading_date, time(12)))
                if previous else None)
            if vehicle.pk not in typicals:
                typicals[vehicle.pk] = typical_value(
                    vehicle.supplies.order_by("-supplied_at").values_list(
                        "meter_value", flat=True)[:UNIT_WINDOW_SUPPLIES])
            ok, reason = check_reading(
                supply.meter_value, vehicle.unit, previous_value,
                previous_when, supply.supplied_at,
                typicals[vehicle.pk])
            if ok:
                with transaction.atomic():
                    supply.reading = MachineMeterReading.objects.create(
                        machine=vehicle.machine,
                        reading_date=local.date(),
                        source=MachineMeterReading.SOURCE_GASOGES,
                        **{field: supply.meter_value},
                    )
                supply.status = GasoGesSupply.STATUS_READING
                counters["lecturas"] += 1
            else:
                supply.status = GasoGesSupply.STATUS_ANOMALY
                counters["dudosos"] += 1
            supply.status_note = reason[:255]
        supply.save(update_fields=["status", "status_note", "reading"])
        if heartbeat:
            heartbeat(done, total, counters)
    log("Lecturas: %(lecturas)d creadas, %(dudosos)d dudosas, "
        "%(sin_centro)d sin centro de gasto, %(sin_unidad)d sin "
        "unidad." % counters)
    return counters


def reset_readings(log):
    """
    Delete the readings that came from GasoGes and redo them.

    ---

    Borra las lecturas que vinieron del surtidor (nunca las puestas a
    mano), deja todos los suministros pendientes y vuelve a deducir
    las unidades que no confirmó nadie, para rehacer las lecturas con
    las reglas vigentes (S135: A44 y Z01 tras la primera carga).
    """
    with transaction.atomic():
        deleted, _detail = MachineMeterReading.objects.filter(
            source=MachineMeterReading.SOURCE_GASOGES).delete()
        GasoGesSupply.objects.update(
            status=GasoGesSupply.STATUS_PENDING, status_note="",
            reading=None)
    log("Rehacer: %d lecturas del surtidor borradas; todos los "
        "suministros vuelven a pendiente." % deleted)
    return deleted


def run_sync(start, end, log, heartbeat=None, rebuild=False):
    """
    Full sync: users, vehicles, supplies, units and readings.

    ---

    Sincronización completa, en este orden: usuarios, vehículos,
    suministros, unidades y lecturas.
    """
    client = GasoGesClient()
    summary = {}
    summary["usuarios"] = sync_users(client, log)
    summary["vehiculos"] = sync_vehicles(client, log)
    summary["suministros"] = sync_supplies(
        client, start, end, log, heartbeat)
    if rebuild:
        summary["rehacer"] = reset_readings(log)
    summary["unidades"] = deduce_units(log)
    summary["lecturas"] = build_readings(log)
    return summary
