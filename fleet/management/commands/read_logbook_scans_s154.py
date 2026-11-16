# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/read_logbook_scans_s154.py
"""
H23 (S154, invasora) -- lee con Gemini los libros historiales escaneados
de las grúas A y H (fleet.logbook_service) y guarda sus filas y los
datos de la grúa en la ficha.

Sin --apply solo cuenta qué escaneos faltan por leer (sin llamar a
Gemini). Cada escaneo se lee una sola vez: los ya leídos sin error se
saltan salvo con --force; los que dieron error se reintentan
(directriz 4.17: nunca reprocesar a ciegas).
Escribe en pantalla y en su propio fichero de log a la vez
(com-standards 0bis), con progreso y hora estimada de fin (0ter).

---

H23 (S154) -- reads the scanned crane logbooks with Gemini.
"""
import time
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from fleet.logbook_service import read_scan, scan_documents, store_scan
from fleet.models import MachineAsset, MachineLogbookSource


class Command(BaseCommand):
    """
    Reads the scanned logbooks of the A/H cranes.

    ---

    Lee los libros historiales escaneados de las grúas A y H.
    """

    help = (
        "Lee con Gemini los libros historiales escaneados de las grúas "
        "A y H (sin --apply solo cuenta)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--force", action="store_true",
                            help="Vuelve a leer también los ya leídos.")
        parser.add_argument("--machine", default="",
                            help="Solo esta máquina (p. ej. A36).")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--log-file", required=True)

    def _log(self, text, stamp=True):
        line = (
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
            if stamp else text
        )
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options)
        finally:
            self._log_handle.close()

    def _run(self, options):
        machine = None
        if options["machine"]:
            machine = MachineAsset.objects.filter(
                code=options["machine"].strip().upper(),
            ).first()
            if machine is None:
                self._log("No existe la máquina %s." % options["machine"])
                return
        pending = scan_documents(machine)
        read_ids = set(
            MachineLogbookSource.objects.filter(
                kind=MachineLogbookSource.KIND_SCAN, error="",
            ).values_list("document_id", flat=True)
        )
        total_found = len(pending)
        already_read = len(
            [entry for entry, _found in pending if entry.pk in read_ids]
        )
        if not options["force"]:
            pending = [
                (entry, found) for entry, found in pending
                if entry.pk not in read_ids
            ]
        if options["limit"]:
            pending = pending[:options["limit"]]
        machines = sorted({found.code for _entry, found in pending})
        self._log(
            "Escaneos LIBRO_HISTORIAL de grúas A/H: %d; ya leídos: %d; "
            "a leer ahora: %d (%d máquinas: %s)" % (
                total_found, already_read, len(pending), len(machines),
                ", ".join(machines),
            )
        )
        if not options["apply"]:
            self._log("Sin --apply: no se lee nada.")
            return
        start = datetime.now()
        counters = {"leidos": 0, "filas": 0, "errores": 0, "campos": 0}
        total = len(pending)
        for index, (entry, found) in enumerate(pending, start=1):
            try:
                parsed = read_scan(entry, found)
                result = store_scan(entry, found, parsed)
                counters["leidos"] += 1
                counters["filas"] += result["rows"]
                counters["campos"] += len(result["filled"])
                self._log(
                    "%s · %s (id %d): %d filas%s" % (
                        found.code, entry.name, entry.pk, result["rows"],
                        "; ficha: " + ", ".join(result["filled"])
                        if result["filled"] else "",
                    )
                )
            except Exception as exc:  # noqa: BLE001 -- se anota y sigue
                counters["errores"] += 1
                store_scan(entry, found, error=str(exc)[:2000])
                self._log(
                    "%s · %s (id %d): ERROR %s" % (
                        found.code, entry.name, entry.pk, exc,
                    )
                )
            elapsed = (datetime.now() - start).total_seconds()
            eta_seconds = elapsed / index * (total - index)
            end_at = datetime.now() + timedelta(seconds=eta_seconds)
            self._log(
                "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                "-- filas=%d, errores=%d" % (
                    index, total, index * 100 // total,
                    int(eta_seconds // 60), int(eta_seconds % 60),
                    end_at.strftime("%H:%M:%S"),
                    counters["filas"], counters["errores"],
                )
            )
            time.sleep(0.5)
        self._log("RESUMEN", stamp=False)
        self._log(
            "Escaneos leídos: %d · filas guardadas: %d · campos de ficha "
            "rellenados: %d · errores: %d" % (
                counters["leidos"], counters["filas"], counters["campos"],
                counters["errores"],
            ),
            stamp=False,
        )
