# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/generate_logbooks_s154.py
"""
H23 (S154, invasora) -- genera de una vez el libro historial de todas
las grúas A y H y lo guarda como su documento LIBRO_HISTORIAL, igual
que el botón «Generar libro historial» de la ficha
(fleet.logbook_service.generate_logbook): un libro ya generado ese día
para la grúa va a la papelera.

Miguel Ángel: "todos los libros generados por la plataforma están
hechos a mano [...] dándole al botón genera el libro historial.
Necesito un comando de gestión que los genere todos."

Sin --apply solo lista las grúas que se generarían.
Escribe en pantalla y en su propio fichero de log a la vez
(com-standards 0bis), con progreso y hora estimada de fin (0ter).

---

H23 (S154) -- generates the logbook of every A/H crane at once.
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from fleet.logbook_service import generate_logbook
from fleet.models import MachineAsset


class Command(BaseCommand):
    """
    Generates and stores the logbook of every A/H crane.

    ---

    Genera y guarda el libro historial de todas las grúas A y H.
    """

    help = (
        "Genera el libro historial de todas las grúas A y H y lo guarda "
        "como su documento (sin --apply solo lista)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--machine", default="",
                            help="Solo esta grúa (p. ej. A36).")
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
        cranes = MachineAsset.objects.filter(
            code__regex=r"^[AaHh][0-9]", is_active=True,
        ).order_by("code")
        if options["machine"]:
            cranes = cranes.filter(code__iexact=options["machine"])
        cranes = [machine for machine in cranes if machine.is_logbook_crane]
        total = len(cranes)
        mode = "APLICAR" if options["apply"] else "SOLO LISTAR"
        self._log("Libros historiales -- %s -- %d grúas" % (mode, total))
        if not options["apply"]:
            for machine in cranes:
                self._log("  %s %s" % (machine.code, machine.brand_model))
            self._log_plain_summary(total, 0, [])
            return

        start = datetime.now()
        done, failed = 0, []
        for index, machine in enumerate(cranes, start=1):
            try:
                entry = generate_logbook(machine)
            except Exception as exc:  # noqa: BLE001 -- se anota y sigue
                failed.append("%s: %s" % (machine.code, exc))
                self._log("%s -> ERROR: %s" % (machine.code, exc))
            else:
                done += 1
                self._log("%s -> libro generado (documento %s)" % (
                    machine.code, entry.pk))
            elapsed = (datetime.now() - start).total_seconds()
            remaining = elapsed / index * (total - index)
            end = datetime.now() + timedelta(seconds=remaining)
            self._log(
                "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                "-- generados %d, errores %d" % (
                    index, total, index * 100 // total,
                    remaining // 60, remaining % 60,
                    end.strftime("%H:%M:%S"), done, len(failed),
                )
            )
        self._log_plain_summary(total, done, failed)

    def _log_plain_summary(self, total, done, failed):
        self._log("", stamp=False)
        self._log("RESUMEN", stamp=False)
        self._log("Grúas: %d" % total, stamp=False)
        self._log("Libros generados: %d" % done, stamp=False)
        self._log("Errores: %d" % len(failed), stamp=False)
        for line in failed:
            self._log("  %s" % line, stamp=False)
