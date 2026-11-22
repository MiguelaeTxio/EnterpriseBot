# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_refuels.py
"""
Pump refuels (GasoGes) actions, new interface.

---

Acciones de los repostajes del surtidor (GasoGes) en la nueva interfaz
(S163), copiado de panel/views_refuels.py: sobre los vehículos de los
repostajes marcados, fijar si apuntan km u horas, si se pregunta al
chófer por WhatsApp y si el contador está averiado; en Personal,
además, si se pregunta a los chóferes de los marcados.
"""
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from fleet.gasoges_sync import build_readings, redo_vehicle
from fleet.models import GasoGesSupply, GasoGesUser, GasoGesVehicle
from new_ui.mixins import SuperuserRequiredMixin


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _supplies(request):
    ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
    return GasoGesSupply.objects.filter(pk__in=ids)


def _vehicle_ids(request):
    return set(_supplies(request).values_list("vehicle_id", flat=True))


class RefuelUnitView(SuperuserRequiredMixin, View):
    """
    POST `unit` (KM | HOURS): set the unit of the marked vehicles.

    ---

    POST: fija a mano si los vehículos de los repostajes marcados
    apuntan km u horas (la deducción automática ya no la cambia) y
    rehace su serie de lecturas entera.
    """

    def post(self, request):
        unit = request.POST.get("unit")
        if unit not in (GasoGesVehicle.UNIT_KM, GasoGesVehicle.UNIT_HOURS):
            return _error("Elige kilómetros u horas.")
        vehicles = GasoGesVehicle.objects.filter(
            pk__in=_vehicle_ids(request), machine__isnull=False)
        switched = list(vehicles.select_related("machine"))
        changed = vehicles.update(
            unit=unit, unit_source=GasoGesVehicle.UNIT_SOURCE_MANUAL)
        if not changed:
            return _error("Ninguno de los vehículos de los marcados tiene "
                          "centro de gasto.")
        for vehicle in switched:
            vehicle.unit = unit
            redo_vehicle(vehicle, lambda _line: None)
        counters = build_readings(lambda _line: None)
        return _ok("%d vehículo(s) en %s. Series rehechas: %d lecturas y "
                   "%d dudosas." % (
                       changed, "kilómetros" if unit == GasoGesVehicle.UNIT_KM
                       else "horas", counters["lecturas"],
                       counters["dudosos"]))


class RefuelAskView(SuperuserRequiredMixin, View):
    """
    POST `ask` (1 | 0), `who` (vehicle | driver): WhatsApp questions.

    ---

    POST: si se pregunta o no por WhatsApp a los vehículos (o a los
    chóferes) de los repostajes marcados. Se pregunta si el chófer y el
    vehículo lo tienen marcado; sus lecturas siguen entrando igual.
    """

    def post(self, request):
        ask = request.POST.get("ask") == "1"
        if request.POST.get("who") == "driver":
            ids = set(_supplies(request).exclude(user__isnull=True)
                      .values_list("user_id", flat=True))
            changed = GasoGesUser.objects.filter(pk__in=ids).update(
                ask_driver=ask)
            what = "chófer(es)"
        else:
            changed = GasoGesVehicle.objects.filter(
                pk__in=_vehicle_ids(request)).update(ask_driver=ask)
            what = "vehículo(s)"
        if not changed:
            return _error("Marca antes algún repostaje.")
        return _ok("%d %s: %s." % (
            changed, what,
            "se le preguntará" if ask else "no se le preguntará"))


class RefuelMeterView(SuperuserRequiredMixin, View):
    """
    POST `broken` (1 | 0): meter of the marked vehicles broken/repaired.

    ---

    POST: marca el contador de los vehículos de los repostajes marcados
    como averiado (no se pregunta y sus repostajes dejan de dar lectura)
    o reparado (vuelven a contar desde que se averió).
    """

    def post(self, request):
        broken = request.POST.get("broken") == "1"
        vehicles = list(GasoGesVehicle.objects.filter(
            pk__in=_vehicle_ids(request)))
        if not vehicles:
            return _error("Marca antes algún repostaje.")
        for vehicle in vehicles:
            vehicle.meter_broken = broken
            vehicle.meter_broken_since = timezone.now() if broken else None
            vehicle.save(update_fields=[
                "meter_broken", "meter_broken_since", "updated_at"])
            build_readings(lambda _line: None, vehicle=vehicle)
        return _ok("%d vehículo(s): contador %s." % (
            len(vehicles), "averiado" if broken else "reparado"))
