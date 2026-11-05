# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/clocks_from_alta.py
"""
Management command: clocks_from_alta.

The workers who received the clock-in onboarding on --alta-day (and had
never clocked before it) clock from --from: sets
WorkerClockSetting.clocks_from and cancels, as supervisor corrections
with their reason, the presses they made before that day. Dry run by
default; --apply writes.

---

Comando de gestión: clocks_from_alta (H24, S143).

Miguel Ángel envió el alta en el fichaje el 05/11 para que empezaran a
fichar el 06/11, pero nadie tenía puesto "Ficha desde" y Carlos Núñez
fichó ese mismo día. Este comando, a quienes recibieron la circular
"Alta en el fichaje" el día --alta-day y no habían fichado nunca antes
de ese día:
1. Les pone "Ficha desde" --from (antes ni avisos ni fichajes).
2. Anula, como corrección del supervisor --by-user-id y con su motivo,
   las pulsaciones que hayan hecho antes de --from (quedan en el
   historial de correcciones; no se borra nada).
Sin --apply solo lista lo que haría.
"""
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from document_explorer.models import DocumentAcknowledgment
from hr_calendar.clock_corrections import ClockCorrectionError, correct_event
from hr_calendar.models import ClockCorrection, ClockEvent
from hr_calendar.models import WorkerClockSetting
from ivr_config.models import CompanyUser
from panel.personal_access import ONBOARDING_CIRCULAR

REASON = ("Alta en el fichaje enviada el %s para fichar desde el %s: "
          "pulsación anterior a su primer día de fichaje.")


class Command(BaseCommand):
    help = ("Fichan desde --from quienes recibieron el alta el "
            "--alta-day; anula sus pulsaciones anteriores.")

    def add_arguments(self, parser):
        parser.add_argument("--alta-day", required=True)
        parser.add_argument("--from", dest="from_day", required=True)
        parser.add_argument("--by-user-id", type=int, required=True,
                            help="CompanyUser que firma las correcciones.")
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
            alta_day = datetime.date.fromisoformat(options["alta_day"])
            from_day = datetime.date.fromisoformat(options["from_day"])
        except ValueError as exc:
            raise CommandError("Fecha no válida: %s" % exc)
        by = CompanyUser.objects.filter(pk=options["by_user_id"]).first()
        if by is None:
            raise CommandError("No existe el CompanyUser %s."
                               % options["by_user_id"])
        apply = options["apply"]
        say("# clocks_from_alta %s: alta del %s, fichan desde el %s, "
            "firma CompanyUser %s" % (
                "APLICANDO" if apply else "SIMULACIÓN", alta_day,
                from_day, by.pk))
        tz = timezone.get_current_timezone()
        alta_start = timezone.make_aware(
            datetime.datetime.combine(alta_day, datetime.time.min), tz)
        from_start = timezone.make_aware(
            datetime.datetime.combine(from_day, datetime.time.min), tz)
        acks = DocumentAcknowledgment.objects.filter(
            document_type__code=ONBOARDING_CIRCULAR,
            delivery_date=alta_day,
        ).select_related("person").order_by("person_id")
        people = {a.person_id: a.person for a in acks}
        say("# Personas con el alta del %s: %d" % (alta_day, len(people)))
        done = skipped = cancelled = 0
        for pk, person in people.items():
            label = "#%d %s %s" % (pk, person.given_name,
                                   person.first_surname)
            if ClockEvent.objects.filter(
                person_id=pk, pressed_at__lt=alta_start,
            ).exists():
                say("%s: ya fichaba antes del alta, no se toca" % label)
                skipped += 1
                continue
            presses = list(ClockEvent.objects.filter(
                person_id=pk, pressed_at__gte=alta_start,
                pressed_at__lt=from_start,
                correction__isnull=True,
            ).order_by("pressed_at"))
            say("%s: ficha desde el %s; pulsaciones a anular: %s" % (
                label, from_day.strftime("%d/%m/%Y"),
                ", ".join("%s %s" % (
                    e.kind,
                    timezone.localtime(e.pressed_at).strftime("%H:%M:%S"))
                    for e in presses) or "ninguna"))
            if not apply:
                continue
            setting, _created = WorkerClockSetting.objects.get_or_create(
                person_id=pk,
            )
            setting.clocks = True
            setting.clocks_from = from_day
            setting.updated_by = by
            setting.save()
            for event in presses:
                # Quien firma, en la empresa de la pulsación si tiene
                # cuenta en ella.
                signer = CompanyUser.objects.filter(
                    user_id=by.user_id, company_id=event.company_id,
                ).first() or by
                try:
                    correct_event(
                        event.pk, signer, ClockCorrection.Action.CANCEL,
                        REASON % (alta_day.strftime("%d/%m/%Y"),
                                  from_day.strftime("%d/%m/%Y")),
                        user_agent="clocks_from_alta",
                    )
                    cancelled += 1
                except ClockCorrectionError as exc:
                    say("%s: NO se ha anulado la pulsación %d: %s"
                        % (label, event.pk, exc))
            done += 1
        say("# Resultado: %d con «Ficha desde», %d sin tocar, %d "
            "pulsaciones anuladas%s" % (
                done, skipped, cancelled,
                "" if apply else " (simulación: nada escrito)"))
        if log:
            log.close()
