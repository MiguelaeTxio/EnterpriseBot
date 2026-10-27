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
5. Lecturas: solo de los suministros que forman la serie real del
   contador de cada centro de gasto (S137, `best_series`); los dudosos
   quedan marcados, sin lectura.

Todas las funciones reciben `log` (una función que escribe una línea).
"""
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation

from django.db import transaction
from django.utils import timezone

from document_explorer.models import PersonIdentity
from fleet.gasoges_client import GasoGesClient
from fleet.gasoges_client import GasoGesError
from fleet.gasoges_rules import best_series
from fleet.gasoges_rules import convention_unit
from fleet.gasoges_rules import deduce_unit
from fleet.gasoges_rules import name_matches
from fleet.gasoges_rules import normalize
from fleet.gasoges_rules import series_reason
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


def apply_convention(log, dry_run=False):
    """
    Set the unit of every linked vehicle the workshop rule covers.

    ---

    Pone la unidad que fija la regla del taller (S137: P, turismos y
    furgonetas, km; A y B, horas) a los vehículos enlazados a un centro
    de gasto, por encima de lo deducido o puesto a mano. Si la unidad
    cambia, rehace sus lecturas (`redo_vehicle`): lo que no encaje con
    la regla queda dudoso y se pregunta al repostador. Devuelve los
    vehículos que cambiaron.
    """
    changed = []
    vehicles = GasoGesVehicle.objects.filter(
        machine__isnull=False).select_related("machine")
    for vehicle in vehicles:
        unit = convention_unit(vehicle.machine.code, vehicle.machine.family)
        if unit is None:
            continue
        if (vehicle.unit == unit and vehicle.unit_source
                == GasoGesVehicle.UNIT_SOURCE_CONVENTION):
            continue
        before = vehicle.get_unit_display()
        unit_changed = vehicle.unit != unit
        changed.append(vehicle)
        log("%s %s (GasoGes %s): %s -> %s%s." % (
            vehicle.machine.code, vehicle.plate or vehicle.name,
            vehicle.gasoges_id, before,
            dict(GasoGesVehicle.UNIT_CHOICES)[unit],
            "" if unit_changed else " (solo pasa a regla del taller)"))
        if dry_run:
            continue
        vehicle.unit = unit
        vehicle.unit_source = GasoGesVehicle.UNIT_SOURCE_CONVENTION
        vehicle.save(update_fields=["unit", "unit_source", "updated_at"])
        if unit_changed:
            redo_vehicle(vehicle, log)
    log("Regla del taller: %d vehículos cambiados%s." % (
        len(changed), " (DRY-RUN, sin guardar)" if dry_run else ""))
    return changed


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
            points, vehicle.machine.code)
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


DRIVER_NOTES = ("confirmado por el chófer", "corregido por el chófer")
SERIES_NOTE = "encaja con el resto de lecturas del vehículo"


def _field_of(unit):
    """
    Reading field of a vehicle unit ("km" or "hours").

    ---

    Campo de la lectura según la unidad del vehículo.
    """
    return "km" if unit == GasoGesVehicle.UNIT_KM else "hours"


def meter_broken_at(vehicle, when):
    """
    True if the vehicle's meter was marked broken at that moment.

    ---

    True si el contador del vehículo estaba averiado en ese momento
    (S137): marcado como averiado y el repostaje es de esa fecha o
    posterior (sin fecha, todos).
    """
    if not vehicle.meter_broken:
        return False
    since = vehicle.meter_broken_since
    return since is None or when >= since


def _mark_broken(supply):
    """
    Leave a supply without reading because its meter is broken.

    ---

    Deja un repostaje sin lectura porque su contador está averiado.
    """
    if (supply.status == GasoGesSupply.STATUS_BROKEN_METER
            and supply.reading_id is None):
        return
    with transaction.atomic():
        if supply.reading_id is not None:
            supply.reading.delete()
        supply.reading = None
        supply.status = GasoGesSupply.STATUS_BROKEN_METER
        supply.status_note = "contador averiado"
        supply.save(update_fields=["status", "status_note", "reading"])


def recheck_series(machine, unit):
    """
    Recompute which supplies of a machine form its meter series.

    ---

    Rehace, para un centro de gasto y una unidad (km u horas), qué
    repostajes forman la serie real de su contador (S137,
    `best_series`): esos tienen lectura y el resto quedan dudosos, con
    el motivo. Junta los repostajes de todos sus vehículos de GasoGes
    con esa unidad (A56 reposta con dos). Los confirmados o corregidos
    por el chófer conservan su lectura siempre, pero cuentan como uno
    más al elegir la serie: un "sí, es correcto" a un dato malo no
    vuelve dudosas las lecturas buenas. Solo se tocan las lecturas que
    cambian. Devuelve (lecturas, dudosos) tras rehacerla.
    """
    field = _field_of(unit)
    supplies = []
    for supply in GasoGesSupply.objects.filter(
        vehicle__machine=machine, vehicle__unit=unit,
    ).select_related("reading", "vehicle").order_by("supplied_at", "id"):
        # S137: con el contador averiado no hay lectura ni cuenta para la
        # serie.
        if meter_broken_at(supply.vehicle, supply.supplied_at):
            _mark_broken(supply)
        else:
            supplies.append(supply)
    points = [(s.supplied_at, s.meter_value) for s in supplies]
    forced = {i for i, s in enumerate(supplies)
              if s.status_note.startswith(DRIVER_NOTES)}
    chain = best_series(points, unit)
    readings = doubtful = 0
    for index, supply in enumerate(supplies):
        if index in forced:
            readings += 1
            continue
        if index in chain:
            readings += 1
            reading = supply.reading
            if (supply.status == GasoGesSupply.STATUS_READING
                    and reading is not None
                    and getattr(reading, field) == supply.meter_value):
                continue
            with transaction.atomic():
                if reading is not None:
                    reading.delete()
                supply.reading = MachineMeterReading.objects.create(
                    machine=machine,
                    reading_date=timezone.localtime(
                        supply.supplied_at).date(),
                    source=MachineMeterReading.SOURCE_GASOGES,
                    **{field: supply.meter_value},
                )
                supply.status = GasoGesSupply.STATUS_READING
                supply.status_note = SERIES_NOTE
                supply.save(update_fields=[
                    "status", "status_note", "reading"])
            continue
        doubtful += 1
        note = series_reason(points, index, chain, unit)[:255]
        if (supply.status == GasoGesSupply.STATUS_ANOMALY
                and supply.reading_id is None
                and supply.status_note == note):
            continue
        with transaction.atomic():
            if supply.reading is not None:
                supply.reading.delete()
            supply.reading = None
            supply.status = GasoGesSupply.STATUS_ANOMALY
            supply.status_note = note
            supply.save(update_fields=["status", "status_note", "reading"])
    return readings, doubtful


def build_readings(log, heartbeat=None, vehicle=None, recheck_all=False):
    """
    Resolve pending supplies and recheck the affected meter series.

    ---

    Mira los repostajes pendientes, sin centro de gasto, sin unidad o
    con el contador averiado (pueden haberse resuelto) y rehace la serie
    del contador de cada centro de gasto afectado (`recheck_series`): un
    repostaje nuevo puede hacer dudoso uno anterior o al revés. Con
    `recheck_all`, todas las series (S137, para rehacerlas con la regla
    nueva sin borrar lo confirmado por los chóferes).
    """
    pending = GasoGesSupply.objects.filter(status__in=[
        GasoGesSupply.STATUS_PENDING, GasoGesSupply.STATUS_NO_MACHINE,
        GasoGesSupply.STATUS_NO_UNIT, GasoGesSupply.STATUS_BROKEN_METER,
    ]).select_related("vehicle", "vehicle__machine")
    if vehicle is not None:
        pending = pending.filter(vehicle=vehicle)
    counters = {"lecturas": 0, "dudosos": 0, "sin_centro": 0,
                "sin_unidad": 0, "averiados": 0, "series": 0}
    groups = set()
    for supply in pending.iterator():
        current = supply.vehicle
        if meter_broken_at(current, supply.supplied_at):
            _mark_broken(supply)
            counters["averiados"] += 1
            continue
        if current.machine_id is None:
            status = GasoGesSupply.STATUS_NO_MACHINE
            counters["sin_centro"] += 1
        elif current.unit == GasoGesVehicle.UNIT_UNKNOWN:
            status = GasoGesSupply.STATUS_NO_UNIT
            counters["sin_unidad"] += 1
        else:
            groups.add((current.machine_id, current.unit))
            continue
        if supply.status != status or supply.status_note:
            supply.status = status
            supply.status_note = ""
            supply.save(update_fields=["status", "status_note"])
    known = GasoGesVehicle.objects.filter(machine__isnull=False).exclude(
        unit=GasoGesVehicle.UNIT_UNKNOWN)
    if recheck_all:
        groups.update(known.values_list("machine_id", "unit"))
    elif vehicle is not None and vehicle.machine_id and (
            vehicle.unit != GasoGesVehicle.UNIT_UNKNOWN):
        groups.add((vehicle.machine_id, vehicle.unit))
    machines = MachineAsset.objects.in_bulk({m for m, _u in groups})
    total = len(groups)
    for done, (machine_id, unit) in enumerate(sorted(groups), start=1):
        readings, doubtful = recheck_series(machines[machine_id], unit)
        counters["lecturas"] += readings
        counters["dudosos"] += doubtful
        counters["series"] += 1
        if heartbeat:
            heartbeat(done, total, counters)
    log("Lecturas: %(series)d series de contador rehechas, con "
        "%(lecturas)d lecturas y %(dudosos)d dudosas; %(sin_centro)d "
        "sin centro de gasto, %(sin_unidad)d sin unidad, %(averiados)d "
        "con el contador averiado." % counters)
    return counters


def accept_supply(supply, note, value=None):
    """
    Turn a supply into a reading because the driver said so.

    ---

    Convierte un repostaje en lectura porque lo ha dicho el chófer
    (S135, pregunta por WhatsApp): confirmó que el dato es correcto o
    escribió el valor correcto (`value`). El valor tecleado original
    queda en el motivo. Sin centro de gasto o sin unidad no hay lectura
    posible y devuelve False.
    """
    vehicle = supply.vehicle
    if vehicle.machine_id is None or (
            vehicle.unit == GasoGesVehicle.UNIT_UNKNOWN):
        return False
    field = "km" if vehicle.unit == GasoGesVehicle.UNIT_KM else "hours"
    if value is not None and value != supply.meter_value:
        note = "%s (tecleó %s)" % (note, supply.meter_value)
        supply.meter_value = value
    with transaction.atomic():
        if supply.reading_id:
            supply.reading.delete()
        supply.reading = MachineMeterReading.objects.create(
            machine=vehicle.machine,
            reading_date=timezone.localtime(supply.supplied_at).date(),
            source=MachineMeterReading.SOURCE_GASOGES,
            **{field: supply.meter_value},
        )
        supply.status = GasoGesSupply.STATUS_READING
        supply.status_note = note[:255]
        supply.save(update_fields=[
            "meter_value", "reading", "status", "status_note"])
    return True


def redo_vehicle(vehicle, log):
    """
    Redo the GasoGes readings of one vehicle with its current unit.

    ---

    Rehace las lecturas del surtidor de un vehículo con la unidad que
    tiene ahora (S135: Z134 estaba deducida en km y es de horas). No
    toca los repostajes que confirmó o corrigió el chófer.
    """
    supplies = vehicle.supplies.exclude(
        status_note__startswith="confirmado por el chófer").exclude(
        status_note__startswith="corregido por el chófer")
    with transaction.atomic():
        deleted, _detail = MachineMeterReading.objects.filter(
            gasoges_supply__in=supplies).delete()
        supplies.update(status=GasoGesSupply.STATUS_PENDING,
                        status_note="", reading=None)
    counters = build_readings(lambda _line: None, vehicle=vehicle)
    log("%s (GasoGes %s): %d lecturas borradas; serie rehecha con %d "
        "lecturas y %d dudosas." % (
            vehicle.machine.code if vehicle.machine else "-",
            vehicle.gasoges_id, deleted, counters["lecturas"],
            counters["dudosos"]))
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


def run_sync(start, end, log, heartbeat=None, rebuild=False,
             recheck=False):
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
    summary["regla"] = len(apply_convention(log))
    summary["unidades"] = deduce_units(log)
    summary["lecturas"] = build_readings(log, recheck_all=recheck)
    return summary
