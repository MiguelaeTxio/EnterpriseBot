# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/apply_lost_driver_answers_s137.py
"""
H30 (S137). Stores two values that drivers wrote on 27/10 and that the
bot did not pick up.

---

H30 (S137). Guarda dos datos que los chóferes escribieron el 27/10 y
que el robot no recogió (todavía no entendía un número con texto ni
una respuesta sin pulsar botón; arreglado en refuel_questions):
- Z40 (pregunta 2): "Tiene 1625horas" -- 1.625 horas (anterior 1.350
  el 05/08, encaja).
- A58 (pregunta 12): escribió 26708 y luego "Eso es lo que marca".
Miguel Ángel: "1" (apuntar los dos). Cada repostaje queda como
corregido por el chófer, con su lectura, y la pregunta como corregida.
Sin `--apply` solo informa. Idempotente: una pregunta ya corregida no
se toca.
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from fleet.gasoges_sync import accept_supply
from fleet.models import RefuelQuestion

# (pregunta, valor, lo que escribió el chófer)
ANSWERS = (
    (2, 1625, "Tiene 1625horas"),
    (12, 26708, "26708 / Eso es lo que marca"),
)


class Command(BaseCommand):
    """
    Store the two lost driver answers.

    ---

    Guarda las dos respuestas perdidas de los chóferes.
    """

    help = (
        "Guarda los datos que escribieron los chóferes de Z40 y A58 el "
        "27/10 y no se recogieron (H30, S137). Sin --apply solo informa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def handle(self, *args, **options):
        apply = options["apply"]
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._log("Inicio: respuestas perdidas de los chóferes -- %s."
                      % ("APLICAR" if apply else "SOLO INFORME"))
            done = 0
            for position, (pk, value, text) in enumerate(ANSWERS, start=1):
                question = RefuelQuestion.objects.filter(pk=pk).select_related(
                    "supply", "vehicle__machine").first()
                prefix = "%d/%d pregunta %d" % (position, len(ANSWERS), pk)
                if question is None or (
                        question.status == RefuelQuestion.STATUS_CORRECTED):
                    self._log("%s: SALTADA, no existe o ya está corregida."
                              % prefix)
                    continue
                self._log("%s: %s, tecleó %s -> %s (estaba: %s)." % (
                    prefix, question.vehicle.machine.code,
                    question.supply.meter_value, value,
                    question.get_status_display()))
                if not apply:
                    continue
                question.status = RefuelQuestion.STATUS_CORRECTED
                question.answer = text
                question.answered_at = question.answered_at or timezone.now()
                question.save(update_fields=[
                    "status", "answer", "answered_at"])
                accept_supply(question.supply, "corregido por el chófer",
                              value)
                done += 1
                self._log("%s: guardado." % prefix)
            self._log("Resumen: %d guardadas." % done)
            self._log("Fin.")
