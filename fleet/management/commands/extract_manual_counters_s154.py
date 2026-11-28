# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/extract_manual_counters_s154.py
"""
S154 (invasora, 28/11) -- busca en los manuales de un modelo de máquina
dónde están los contadores (cuentakilómetros, horómetros de motor y de
grúa, botones del display) y guarda esas páginas como imágenes
pendientes de revisar para la ficha QR (fleet.manual_counters_service).

--model es la Marca / Modelo exacta de las máquinas (p. ej. «LUNA AT
35/32»): crea el modelo con ellas y sus manuales sin repetir, y busca.
Sin --apply solo dice qué máquinas y manuales entran, sin llamar a
Gemini. --manual <id> fija el manual del modelo y descarta en la BD
las demás copias (no borra nada del cubo). --reset borra antes las
pendientes de revisar del modelo. Escribe en pantalla y en su propio
fichero de log a la vez (com-standards 0bis), con progreso y hora estimada de fin (0ter).

---

S154 -- finds where the counters are in a machine model's manuals.
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from fleet.models import MachineAsset


class Command(BaseCommand):
    """
    Finds the counters in a machine model's manuals.

    ---

    Busca los contadores en los manuales de un modelo de máquina.
    """

    help = ("Busca en los manuales de un modelo dónde están los "
            "contadores (sin --apply solo cuenta).")

    def add_arguments(self, parser):
        parser.add_argument("--model", required=True,
                            help="Marca / Modelo exacta (p. ej. "
                                 "«LUNA AT 35/32»).")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--manual", type=int, default=0,
            help="Id del manual que se queda como el del modelo (las "
                 "demás copias se descartan en la BD, sin borrar nada).")
        parser.add_argument(
            "--reset", action="store_true",
            help="Borra antes las imágenes del modelo pendientes de "
                 "revisar (las publicadas se quedan).")
        parser.add_argument("--log-file", required=True)

    def _log(self, text, stamp=True):
        line = ("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
                if stamp else text)
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
        from fleet import manual_counters_service as service

        name = options["model"].strip()
        machines = list(MachineAsset.objects.filter(
            brand_model__iexact=name).order_by("code"))
        if not machines:
            raise CommandError("Ninguna máquina con Marca / Modelo «%s»."
                               % name)
        manuals = service.machine_manuals(machines)
        self._log("Modelo «%s»: %s máquinas (%s), %s manuales sin repetir."
                  % (name, len(machines),
                     ", ".join(m.code for m in machines), len(manuals)))
        for entry in manuals:
            self._log("   id %s: %s (%.1f MB)" % (
                entry.pk, entry.name, (entry.size_bytes or 0) / 1048576),
                stamp=False)
        if not options["apply"]:
            self._log("Sin --apply: no se llama a Gemini.")
            return
        company = machines[0].company
        model = service.build_model(company, name)
        if options["manual"]:
            chosen = next((e for e in manuals
                           if e.pk == options["manual"]), None)
            if chosen is None and (model.manual_id != options["manual"]):
                raise CommandError("El manual %s no es de este modelo."
                                   % options["manual"])
            if chosen is not None:
                discarded = service.set_model_manual(model, chosen)
                self._log("Manual del modelo: %s. Copias descartadas en "
                          "la BD (siguen en el cubo): %s."
                          % (chosen.name, discarded))
        if model.manual is None:
            raise CommandError("Elige el manual del modelo con --manual "
                               "<id> (ver la lista de arriba).")
        if options["reset"]:
            self._log("Pendientes de revisar borradas: %s."
                      % service.clear_pending(model))
        start = datetime.now()
        total = 1
        done = [0]

        def log(text):
            if text.startswith("[") and "/" in text.split("]")[0]:
                if done[0]:
                    elapsed = (datetime.now() - start).total_seconds()
                    eta = elapsed / done[0] * (total - done[0])
                    text += " -- ETA %dm%02ds (fin aprox. %s)" % (
                        eta // 60, eta % 60,
                        (datetime.now() + timedelta(seconds=eta))
                        .strftime("%H:%M:%S"))
                done[0] += 1
            self._log(text)

        saved = service.extract_for_model(model, log)
        self._log_plain_summary(model, saved)

    def _log_plain_summary(self, model, saved):
        from fleet.models import ManualCounterImage

        self._log("", stamp=False)
        self._log("RESUMEN", stamp=False)
        self._log("Modelo: %s (id %s)" % (model.name, model.pk),
                  stamp=False)
        self._log("Imágenes nuevas pendientes de revisar: %s" % saved,
                  stamp=False)
        for kind, label in ManualCounterImage.KIND_CHOICES:
            count = model.counter_images.filter(kind=kind).exclude(
                status=ManualCounterImage.STATUS_REJECTED).count()
            self._log("   %s: %s" % (label, count), stamp=False)
