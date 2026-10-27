# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/notify_wrong_confirmations.py
"""
H30 (S137). Tells the drivers who answered "Yes, it is correct" to a
value that is wrong (kilometres in an hours vehicle) why it is wrong,
and undoes their confirmation.

---

H30 (S137). Miguel Ángel: unos pocos chóferes contestaron "Sí, es
correcto" a un dato que no lo es: en un brazo (va por horas) anotaron
kilómetros. A esos, sin plantilla nueva (contestaron hoy: la ventana de
24 horas está abierta), se les escribe en texto libre que el valor
sigue siendo incorrecto, que en ese vehículo van horas y no kilómetros,
que es por la revisión, que tienen que anotarlo en horas y que seguirán
recibiendo mensajes mientras no lo hagan.

Además se deshace su confirmación: el "Sí, es correcto" había metido
esos kilómetros como horas buenas en la serie del vehículo (y de ahí al
aviso de revisión). El repostaje vuelve a calcularse y queda dudoso; la
pregunta queda como contestada, con la nota de que se le explicó.

Lista cerrada de preguntas (consulta de solo lectura de S137, run
40506698267): B43, B34, B47 y B44. La Z113 no entra (25.924 tras
23.279 del 22/07 sale a unas 27 horas al día: más probable que esté mal
la lectura anterior). Si la ventana de un chófer ya está cerrada, no se
le envía nada y se dice en el log. Sin `--apply` solo informa.
"""
import os
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from fleet.gasoges_sync import build_readings
from fleet.models import GasoGesSupply, RefuelQuestion
from fleet.refuel_questions import _format_value, value_problem

QUESTION_IDS = (3, 6, 8, 9)
EXPLAINED = " (se le explicó que van horas, S137)"
MESSAGE = (
    "Hola {name}. Sobre el repostaje de {code} del {when}: contestó que "
    "{value} es correcto, pero no lo es. Ese número son kilómetros, y en "
    "{code} hay que anotar las HORAS que marca el horómetro, no los "
    "kilómetros. Es por la revisión: el cambio de aceite y filtros del "
    "motor toca por horas (cada 800 o 1.200 horas, según el aceite), y "
    "con los kilómetros no podemos saber cuándo le toca. El valor sigue "
    "siendo incorrecto, y mientras se anoten kilómetros seguirá "
    "recibiendo estos mensajes. En el próximo repostaje anote las horas, "
    "por favor. Gracias."
)


class Command(BaseCommand):
    """
    Explain to the drivers why their confirmed value is wrong.

    ---

    Explica a los chóferes por qué el dato que confirmaron está mal.
    """

    help = (
        "Escribe a los chóferes que confirmaron kilómetros en un vehículo "
        "de horas y deshace su confirmación (H30, S137). Sin --apply "
        "solo informa."
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
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._run(options["apply"])

    def _run(self, apply):
        from whatsapp.services import _build_twilio_client
        from whatsapp.window_service import to_e164, window_open

        mode = "APLICAR" if apply else "SOLO INFORME (sin --apply)"
        self._log("Inicio: aviso a quien confirmó km en un vehículo de "
                  "horas -- %s." % mode)
        sender = os.environ.get("TWILIO_WHATSAPP_SENDER", "")
        sender = sender if sender.startswith("whatsapp:") else (
            "whatsapp:%s" % sender)
        client = _build_twilio_client() if apply else None
        sent = closed = skipped = 0
        total = len(QUESTION_IDS)
        questions = {q.pk: q for q in RefuelQuestion.objects.filter(
            pk__in=QUESTION_IDS).select_related(
            "supply", "vehicle", "vehicle__machine", "person")}
        for position, pk in enumerate(QUESTION_IDS, start=1):
            question = questions.get(pk)
            prefix = "%d/%d pregunta %d" % (position, total, pk)
            if question is None or (
                    question.status != RefuelQuestion.STATUS_CONFIRMED):
                skipped += 1
                self._log("%s: SALTADA, no existe o no está como "
                          "\"Sí, es correcto\"." % prefix)
                continue
            supply = question.supply
            code = question.vehicle.machine.code
            text = MESSAGE.format(
                name=question.person.given_name or "trabajador", code=code,
                when=timezone.localtime(supply.supplied_at).strftime(
                    "%d/%m/%Y %H:%M"),
                value=_format_value(supply.meter_value))
            self._log("%s: %s, %s, tecleó %s -- %s" % (
                prefix, code, question.person.given_name,
                _format_value(supply.meter_value),
                value_problem(supply, supply.meter_value) or "sin motivo"))
            if not window_open(None, question.phone):
                closed += 1
                self._log("%s: ventana de 24 h CERRADA, no se le envía."
                          % prefix)
                continue
            if not apply:
                sent += 1
                continue
            message = client.messages.create(
                from_=sender, to="whatsapp:%s" % to_e164(question.phone),
                body=text)
            sent += 1
            self._log("%s: enviado (%s)." % (prefix, message.sid))
            self._undo(supply, question)
            status = GasoGesSupply.objects.get(
                pk=supply.pk).get_status_display()
            self._log("%s: confirmación deshecha, repostaje ahora %s."
                      % (prefix, status))
        self._log("Resumen: %d %s, %d con la ventana cerrada, %d "
                  "saltadas." % (sent, "enviados" if apply
                                 else "por enviar", closed, skipped))
        self._log("Fin.")

    def _undo(self, supply, question):
        """
        Undo the driver's confirmation and recheck the vehicle.

        ---

        Deshace la confirmación del chófer: el repostaje deja de ser
        lectura forzada y se rehace la serie del vehículo, con lo que
        queda dudoso. La pregunta guarda que se le explicó.
        """
        if supply.reading_id:
            supply.reading.delete()
        supply.reading = None
        supply.status = GasoGesSupply.STATUS_PENDING
        supply.status_note = ""
        supply.save(update_fields=["reading", "status", "status_note"])
        question.answer = (question.answer + EXPLAINED)[:255]
        question.save(update_fields=["answer"])
        build_readings(lambda _line: None, vehicle=supply.vehicle)
