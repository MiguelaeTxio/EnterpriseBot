# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/link_gasoges_vehicles.py
"""
H30 (S135). Links the GasoGes vehicles with the cost centres.

---

H30 (S135). Enlaza los vehículos de GasoGes (programa del surtidor) con
los centros de gasto (`fleet.MachineAsset.gasoges_vehicle_id`), punto 3
de la hoja de ruta S135:
- Por `MATRICULA` contra `plate`, normalizadas (sin espacios ni
  guiones, mayúsculas).
- Si el vehículo de GasoGes no tiene matrícula, por `NOMBRE` contra
  `code`, con la misma normalización.

No enlaza nada dudoso: si una matrícula coincide con varios centros de
gasto, si un centro de gasto ya tiene otro ID, o si dos vehículos de
GasoGes caen en el mismo centro de gasto, lo deja sin enlazar y lo
anota. Al final, lista de los vehículos sin enlazar con el motivo (va
al log en SWAP, nunca a git). Idempotente. Sin `--apply` solo informa.
"""
from datetime import datetime
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from fleet.gasoges_client import GasoGesClient
from fleet.gasoges_client import GasoGesError
from fleet.models import MachineAsset

HEARTBEAT_EVERY = 25


def normalize(value):
    """
    Uppercase without spaces or hyphens.

    ---

    Mayúsculas, sin espacios ni guiones.
    """
    if value is None:
        return ""
    return str(value).replace(" ", "").replace("-", "").strip().upper()


class Command(BaseCommand):
    """
    Link GasoGes vehicles with cost centres by plate (or name → code).

    ---

    Enlaza vehículos de GasoGes con centros de gasto por matrícula (o
    nombre contra código si no hay matrícula).
    """

    help = (
        "Enlaza los vehículos de GasoGes con los centros de gasto "
        "(H30, S135). Sin --apply solo informa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

    def _write(self, line):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def _log(self, message):
        """
        Log line with the clock time in front.

        ---

        Línea de log con la hora delante.
        """
        self._write(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _log_plain(self, message):
        """
        Log line without time (summary).

        ---

        Línea de log sin hora (resumen).
        """
        self._write(message)

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._run(options["apply"])

    def _heartbeat(self, done, total, start, counters):
        """
        Progress line with ETA and estimated end time.

        ---

        Línea de progreso con ETA y hora de fin estimada.
        """
        elapsed = (datetime.now() - start).total_seconds()
        eta = (elapsed / done) * (total - done) if done else 0
        end = (datetime.now() + timedelta(seconds=eta)).strftime("%H:%M:%S")
        self._log(
            "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) -- %s"
            % (done, total, done * 100 // total, eta // 60, eta % 60, end,
               counters)
        )

    def _run(self, apply):
        mode = "APLICAR" if apply else "SOLO INFORME (sin --apply)"
        self._log("Inicio: enlace de vehículos de GasoGes -- %s." % mode)
        try:
            vehicles = GasoGesClient().vehicles()
        except GasoGesError as exc:
            self._log("ERROR: %s" % exc)
            raise CommandError(str(exc))
        total = len(vehicles)
        self._log("Vehículos en GasoGes: %d." % total)

        assets = list(MachineAsset.objects.all())
        by_plate = {}
        by_code = {}
        for asset in assets:
            if normalize(asset.plate):
                by_plate.setdefault(normalize(asset.plate), []).append(asset)
            by_code.setdefault(normalize(asset.code), []).append(asset)
        holder_of = {
            asset.gasoges_vehicle_id: asset for asset in assets
            if asset.gasoges_vehicle_id is not None
        }

        claimed = {}
        linked = already = 0
        unlinked = []
        start = datetime.now()
        with transaction.atomic():
            for position, vehicle in enumerate(vehicles, start=1):
                vid = vehicle["vehicle_id"]
                plate = normalize(vehicle["plate"])
                name = normalize(vehicle["name"])
                if plate:
                    candidates = by_plate.get(plate, [])
                    how = "matrícula"
                else:
                    candidates = by_code.get(name, [])
                    how = "nombre"
                reason = None
                asset = None
                if not candidates:
                    reason = "sin coincidencia por %s" % how
                    if plate and by_code.get(name):
                        reason += (
                            " (por NOMBRE coincidiría con %s)"
                            % by_code[name][0].code
                        )
                elif len(candidates) > 1:
                    reason = "%s en varios centros de gasto: %s" % (
                        how, ", ".join(a.code for a in candidates))
                else:
                    asset = candidates[0]
                    other = holder_of.get(vid)
                    if asset.gasoges_vehicle_id == vid:
                        already += 1
                        claimed[asset.pk] = vid
                        asset = None
                    elif asset.gasoges_vehicle_id is not None:
                        reason = "%s ya tiene otro ID de GasoGes (%s)" % (
                            asset.code, asset.gasoges_vehicle_id)
                    elif other is not None:
                        reason = "ID ya puesto en %s" % other.code
                    elif asset.pk in claimed:
                        reason = (
                            "%s ya enlazado en esta ejecución con el "
                            "ID %s" % (asset.code, claimed[asset.pk])
                        )
                if reason:
                    unlinked.append((vehicle, reason))
                elif asset is not None:
                    linked += 1
                    claimed[asset.pk] = vid
                    self._log(
                        "%d/%d ID %s (%s / %s) -> %s por %s%s."
                        % (position, total, vid, vehicle["plate"],
                           vehicle["name"], asset.code, how,
                           "" if asset.is_active else " [INACTIVO]")
                    )
                    if apply:
                        asset.gasoges_vehicle_id = vid
                        asset.save(update_fields=[
                            "gasoges_vehicle_id", "updated_at"])
                if position % HEARTBEAT_EVERY == 0 or position == total:
                    self._heartbeat(
                        position, total, start,
                        "enlazados=%d, ya_estaban=%d, sin_enlazar=%d"
                        % (linked, already, len(unlinked)),
                    )

        self._log_plain("")
        self._log_plain("VEHÍCULOS DE GASOGES SIN ENLAZAR (%d):" % len(
            unlinked))
        for vehicle, reason in unlinked:
            self._log_plain(
                "- ID %s | matrícula '%s' | nombre '%s' | %s"
                % (vehicle["vehicle_id"], vehicle["plate"] or "",
                   vehicle["name"] or "", reason)
            )
        self._log_plain("")
        self._log_plain("RESUMEN (%s):" % mode)
        self._log_plain("- Vehículos en GasoGes: %d" % total)
        self._log_plain("- Enlazados %s: %d" % (
            "ahora" if apply else "por enlazar", linked))
        self._log_plain("- Ya enlazados de antes: %d" % already)
        self._log_plain("- Sin enlazar: %d" % len(unlinked))
        self._log_plain(
            "- Centros de gasto con ID de GasoGes en BD: %d"
            % MachineAsset.objects.filter(
                gasoges_vehicle_id__isnull=False).count()
        )
        self._log_plain("Fin.")
