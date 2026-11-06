# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/cancel_clock_events.py
"""
Management command: cancel_clock_events.

Cancels the given presses as supervisor corrections, with their reason
(nothing is deleted: they stay in the corrections history). Dry run by
default; --apply writes.

---

Comando de gestión: cancel_clock_events (H24, S143).

Anula las pulsaciones indicadas (--ids) como corrección firmada por el
supervisor --by-user-id y con el motivo --reason; quedan en el historial
de correcciones, no se borra nada. Solo pulsaciones vigentes (sin
corrección) de la persona --person, para no tocar la de otro por un id
mal escrito. Sin --apply solo lista lo que haría.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from hr_calendar.clock_corrections import ClockCorrectionError, correct_event
from hr_calendar.models import ClockCorrection, ClockEvent
from ivr_config.models import CompanyUser


class Command(BaseCommand):
    help = "Anula pulsaciones (corrección del supervisor, con motivo)."

    def add_arguments(self, parser):
        parser.add_argument("--person", type=int, required=True)
        parser.add_argument("--ids", required=True,
                            help="Ids de pulsación separados por comas.")
        parser.add_argument("--reason", required=True)
        parser.add_argument("--by-user-id", type=int, required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", default="")

    def handle(self, *args, **options):
        log = open(options["log_file"], "a", encoding="utf-8") \
            if options["log_file"] else None

        def say(text):
            self.stdout.write(text)
            self.stdout.flush()
            if log:
                log.write(text + "\n")
                log.flush()

        try:
            ids = [int(x) for x in options["ids"].split(",") if x.strip()]
        except ValueError:
            raise CommandError("--ids: números separados por comas.")
        by = CompanyUser.objects.filter(pk=options["by_user_id"]).first()
        if by is None:
            raise CommandError("No existe el CompanyUser %s."
                               % options["by_user_id"])
        apply = options["apply"]
        say("# cancel_clock_events %s: persona #%d, pulsaciones %s" % (
            "APLICANDO" if apply else "SIMULACIÓN", options["person"],
            ",".join(map(str, ids))))
        done = 0
        for pk in ids:
            event = ClockEvent.objects.filter(
                pk=pk, person_id=options["person"],
                correction__isnull=True,
            ).first()
            if event is None:
                say("#%d: no es una pulsación vigente de esa persona, no se "
                    "toca" % pk)
                continue
            say("#%d: %s %s -> anular" % (
                pk, event.kind,
                timezone.localtime(event.pressed_at).strftime(
                    "%d/%m/%Y %H:%M:%S")))
            if not apply:
                continue
            signer = CompanyUser.objects.filter(
                user_id=by.user_id, company_id=event.company_id,
            ).first() or by
            try:
                correct_event(pk, signer, ClockCorrection.Action.CANCEL,
                              options["reason"],
                              user_agent="cancel_clock_events")
                done += 1
            except ClockCorrectionError as exc:
                say("#%d: NO se ha anulado: %s" % (pk, exc))
        say("# Resultado: %d anuladas%s" % (
            done, "" if apply else " (simulación: nada escrito)"))
        if log:
            log.close()
