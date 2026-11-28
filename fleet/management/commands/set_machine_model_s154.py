# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/set_machine_model_s154.py
"""
S154 (invasora, 28/11) -- crea (o completa) un modelo a mano: nombre,
centros de gasto y manual. Para lo que no sale de la Marca / Modelo,
p. ej. la plataforma que lleva encima una furgoneta (Miguel Ángel: un
camión con grúa o plataforma apunta a dos modelos, el del vehículo y el
del equipo). El manual elegido queda como el del modelo y las demás
copias de manual de uso de esas máquinas se descartan en la BD, sin
borrar nada (fleet.manual_counters_service.set_model_manual).

Sin --apply solo dice lo que haría. Escribe en pantalla y en su propio
fichero de log a la vez (com-standards 0bis).

---

S154 -- creates or completes a machine model by hand.
"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from fleet.models import MachineAsset


class Command(BaseCommand):
    """
    Creates or completes a machine model by hand.

    ---

    Crea o completa un modelo de máquina a mano.
    """

    help = "Crea o completa un modelo a mano (sin --apply solo lista)."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--machines", required=True,
                            help="Códigos separados por comas.")
        parser.add_argument("--manual", type=int, default=0)
        parser.add_argument("--discard", default="",
                            help="Ids de las copias que se descartan.")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def _fail(self, text):
        self._log("ERROR: " + text)
        raise CommandError(text)

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options)
        finally:
            self._log_handle.close()

    def _run(self, options):
        from fleet import manual_counters_service as service

        codes = [c.strip() for c in options["machines"].split(",")
                 if c.strip()]
        machines = list(MachineAsset.objects.filter(code__in=codes))
        missing = set(codes) - {m.code for m in machines}
        if missing:
            self._fail("No existen: %s" % ", ".join(sorted(missing)))
        manuals = service.machine_manuals(machines)
        chosen = next((e for e in manuals
                       if e.pk == options["manual"]), None)
        if options["manual"] and chosen is None:
            self._fail("El manual %s no es un manual de uso de esas "
                       "máquinas." % options["manual"])
        discard = {int(x) for x in options["discard"].split(",")
                   if x.strip()}
        unknown = discard - {e.pk for e in manuals}
        if unknown:
            self._fail("No son manuales de uso de esas máquinas: %s"
                       % ", ".join(str(x) for x in sorted(unknown)))
        self._log("Modelo «%s»: %s" % (options["name"], ", ".join(codes)))
        for entry in manuals:
            self._log("   %s id %s: %s" % (
                "SE QUEDA" if chosen and entry.pk == chosen.pk
                else "descarta" if entry.pk in discard else "se deja ",
                entry.pk, entry.name))
        if not options["apply"]:
            self._log("Sin --apply: no se ha cambiado nada.")
            return
        model = service.build_model(machines[0].company, options["name"],
                                    machines)
        if chosen is not None:
            discarded = service.set_model_manual(model, chosen,
                                                 only=discard)
            self._log("Manual fijado; copias descartadas en la BD: %s."
                      % discarded)
        self._log("Hecho (modelo id %s)." % model.pk)
