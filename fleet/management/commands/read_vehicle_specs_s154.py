# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/read_vehicle_specs_s154.py
"""
H23 (S154, invasora) -- lee con Gemini las especificaciones técnicas de
los centros de gasto (capacidad de elevación, MMA, tara, medidas, ejes,
año) de su ITV, permiso de circulación, ficha técnica y tabla de carga
vigentes, y rellena solo los campos vacíos (fleet.specs_service).

Sin --apply solo cuenta cuántos centros de gasto faltan por leer y
cuántos tienen documentos (sin llamar a Gemini). Cada centro de gasto
se lee una vez: los ya leídos se saltan salvo con --force.
Escribe en pantalla y en su propio fichero de log a la vez
(com-standards 0bis), con progreso y hora estimada de fin (0ter).

---

H23 (S154) -- reads the vehicles' technical specifications with Gemini.
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from fleet.models import MachineAsset
from fleet.specs_service import read_specs, source_documents


class Command(BaseCommand):
    """
    Reads the technical specifications of the cost centres.

    ---

    Lee las especificaciones técnicas de los centros de gasto.
    """

    help = (
        "Lee con Gemini las especificaciones técnicas de los centros de "
        "gasto (sin --apply solo cuenta)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--force", action="store_true",
                            help="Vuelve a leer también los ya leídos.")
        parser.add_argument("--machine", default="",
                            help="Solo este centro de gasto (p. ej. A36).")
        parser.add_argument("--family", default="",
                            help="Solo esta familia (p. ej. MÓVILES).")
        parser.add_argument(
            "--cranes", action="store_true",
            help="Solo las grúas A y H, sea cual sea su familia.")
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
        # Miguel Ángel (S154): "solo máquinas activas".
        machines = MachineAsset.objects.filter(
            is_active=True).order_by("code")
        if not options["force"]:
            machines = machines.filter(specs_read_at__isnull=True)
        if options["machine"]:
            machines = machines.filter(code__iexact=options["machine"])
        if options["cranes"]:
            machines = machines.filter(code__regex=r"^[AaHh][0-9]")
        if options["family"]:
            machines = machines.filter(family__iexact=options["family"])
        machines = list(machines)
        mode = "APLICAR" if options["apply"] else "SOLO CONTAR"
        self._log("Especificaciones -- %s -- %d centros de gasto por "
                  "leer" % (mode, len(machines)))
        if not options["apply"]:
            with_docs = sum(1 for m in machines if source_documents(m))
            self._log_summary(len(machines), with_docs, 0, 0, 0, [])
            return
        if options["limit"]:
            machines = machines[:options["limit"]]

        total = len(machines)
        start = datetime.now()
        read = without_docs = fields = 0
        failed = []
        for index, machine in enumerate(machines, start=1):
            try:
                result = read_specs(machine)
            except Exception as exc:  # noqa: BLE001 -- se anota y sigue
                failed.append("%s: %s" % (machine.code, exc))
                self._log("%s -> ERROR: %s" % (machine.code, exc))
            else:
                if result["documents"] or result["filled"]:
                    read += 1
                    fields += len(result["filled"])
                    self._log("%s (%s) -> %d documento(s), rellenado: %s" % (
                        machine.code, machine.family or "sin familia",
                        result["documents"],
                        ", ".join(
                            "%s [%s]" % (field, source or "-")
                            for field, source in result["filled"].items()
                        ) or "nada nuevo",
                    ))
                else:
                    without_docs += 1
                    self._log("%s -> sin documentos técnicos" % (
                        machine.code))
            elapsed = (datetime.now() - start).total_seconds()
            remaining = elapsed / index * (total - index)
            end = datetime.now() + timedelta(seconds=remaining)
            self._log(
                "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                "-- leídos %d, sin documentos %d, errores %d" % (
                    index, total, index * 100 // max(total, 1),
                    remaining // 60, remaining % 60,
                    end.strftime("%H:%M:%S"), read, without_docs,
                    len(failed),
                )
            )
        self._log_summary(total, None, read, without_docs, fields, failed)

    def _log_summary(self, total, with_docs, read, without_docs, fields,
                     failed):
        self._log("", stamp=False)
        self._log("RESUMEN", stamp=False)
        self._log("Centros de gasto: %d" % total, stamp=False)
        if with_docs is not None:
            self._log("Con ITV, permiso, ficha técnica o tabla de carga "
                      "vigente: %d" % with_docs, stamp=False)
            return
        self._log("Leídos: %d" % read, stamp=False)
        self._log("Sin documentos técnicos: %d" % without_docs, stamp=False)
        self._log("Campos rellenados: %d" % fields, stamp=False)
        self._log("Errores: %d" % len(failed), stamp=False)
        for line in failed:
            self._log("  %s" % line, stamp=False)
