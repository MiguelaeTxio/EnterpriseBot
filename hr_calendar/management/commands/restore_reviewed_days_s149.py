# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/restore_reviewed_days_s149.py
"""
Put back the visados days the AI corrected by mistake.

---

S149 (Miguel Ángel, 17/11): "lo que había visado Juan se tiene que
quedar como lo había visado Juan [...] hemos machacado sus visados y
tenemos que revertir la situación a como estaba. Hay que indicar que
por un error en el sistema". Al cargar los albaranes, la IA corrigió
días que un supervisor ya había visado (casilla de visado o alguna
corrección a mano, que también cuenta como visto).

Para cada día así:
1. Se busca la primera corrección de la IA posterior al visado.
2. Se reconstruyen los fichajes vigentes justo antes de ella.
3. Se deja el día con esos fichajes (mismo tipo, hora y tipo de
   fichaje), con origen «Restaurado por error del sistema», en nombre
   de quien lo visó y con el motivo explicándolo.
4. El resultado de la IA de ese día («Comparado por IA») se marca como
   error del sistema.
Si después de la IA el supervisor ya volvió a corregir el día a mano,
no se toca: se lista para que lo revise él.
Sin --apply solo dice lo que haría. Log propio (com-standards 0bis).
"""
import datetime
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

REASON = ("Restaurado tal como lo dejó el supervisor: por un error del "
          "sistema, la carga de albaranes (IA) corrigió este día ya "
          "visado.")
NOTE = ("Error del sistema: la IA corrigió este día ya visado; se ha "
        "restaurado tal como lo dejó el supervisor.")


def _name(person):
    if person is None:
        return "(sin persona)"
    return " ".join(filter(None, (person.first_surname,
                                  person.second_surname))) + ", " + (
        person.given_name or "")


def _hm(when):
    return timezone.localtime(when).strftime("%H:%M")


class Command(BaseCommand):
    """
    Restore the visados days the AI corrected.
    ---
    Deja como estaban los días visados que corrigió la IA.
    """

    help = ("Deja tal y como estaban los días visados que la IA corrigió "
            "al cargar albaranes (error del sistema).")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        line = "[%s] %s" % (timezone.localtime().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._run(options["apply"])

    def _run(self, apply):
        from hr_calendar.models import ClockCorrection

        ai_by_day = defaultdict(list)
        for corr in ClockCorrection.objects.filter(
                source=ClockCorrection.Source.AI,
        ).select_related("event", "replacement"):
            event = corr.event or corr.replacement
            when = corr.old_pressed_at or corr.new_pressed_at
            if event is None or when is None:
                continue
            day = timezone.localtime(when).date()
            ai_by_day[(event.company_user_id, day)].append(corr)
        self._log("Días con correcciones de la IA: %d (%s)" % (
            len(ai_by_day), "APLICANDO" if apply else
            "simulación, sin cambios"))
        restored, kept = 0, []
        for (user_id, day), corrections in sorted(
                ai_by_day.items(), key=lambda item: (item[0][1], item[0][0])):
            result = self._day(user_id, day, corrections, apply)
            if result is None:
                continue
            if result.startswith("SIN TOCAR"):
                kept.append(result)
            else:
                restored += 1
                self._log("  " + result)
        for line in kept:
            self._log("  " + line)
        self._log("Fin: %d día/s %s, %d sin tocar." % (
            restored, "restaurado/s" if apply else "a restaurar",
            len(kept)))

    def _day(self, user_id, day, corrections, apply):
        """One day: None if it was not visado before the AI."""
        from django.db.models import Q

        from hr_calendar.clock_corrections import (
            ClockCorrectionError, edit_presses,
        )
        from hr_calendar.models import (
            ClockCorrection, ClockDayAiCheck, ClockDayReview, ClockEvent,
        )

        tz = timezone.get_current_timezone()
        start = timezone.make_aware(
            datetime.datetime.combine(day, datetime.time.min), tz)
        end = start + datetime.timedelta(days=1)
        in_day = (Q(event__company_user_id=user_id,
                    event__pressed_at__gte=start, event__pressed_at__lt=end)
                  | Q(event__isnull=True, replacement__company_user_id=user_id,
                      replacement__pressed_at__gte=start,
                      replacement__pressed_at__lt=end))
        manual = list(ClockCorrection.objects.filter(
            in_day, source=ClockCorrection.Source.MANUAL,
        ).select_related("corrected_by").order_by("corrected_at"))
        review = ClockDayReview.objects.filter(
            company_user_id=user_id, day=day,
        ).select_related("reviewed_by").first()
        # Cuándo quedó visto el día por primera vez, y por quién.
        seen = []
        if review is not None:
            seen.append((review.reviewed_at, review.reviewed_by))
        if manual:
            seen.append((manual[0].corrected_at, manual[0].corrected_by))
        if not seen:
            return None
        seen_at, supervisor = min(seen, key=lambda item: item[0])
        after = sorted((c for c in corrections if c.corrected_at > seen_at),
                       key=lambda c: c.corrected_at)
        if not after:
            return None  # la IA corrigió antes de visar: lo vio y lo visó
        moment = after[0].corrected_at
        events = list(ClockEvent.objects.filter(
            company_user_id=user_id, pressed_at__gte=start,
            pressed_at__lt=end,
        ).select_related("person", "company_user").order_by("pressed_at"))
        if not events:
            return None
        person = events[0].person
        label = "%s %s (visado por %s)" % (
            _name(person), day.strftime("%d/%m/%Y"),
            getattr(getattr(supervisor, "user", None), "get_full_name",
                    lambda: "")() or "un supervisor")
        redone = [m for m in manual if m.corrected_at > moment]
        if redone:
            return ("SIN TOCAR (revisar a mano) %s: después de la IA ya lo "
                    "volvió a corregir a mano" % label)
        if supervisor is None:
            return ("SIN TOCAR (revisar a mano) %s: no consta quién lo visó"
                    % label)
        fixed_before = dict(ClockCorrection.objects.filter(
            event__in=events, corrected_at__lt=moment,
        ).values_list("event_id", "corrected_at"))
        # Lo que puso la IA (o cualquiera) desde ese momento no estaba:
        # la pulsación nueva se crea un instante antes de su corrección.
        new_since = set(ClockCorrection.objects.filter(
            replacement__in=events, corrected_at__gte=moment,
        ).values_list("replacement_id", flat=True))
        before = [e for e in events if e.received_at < moment
                  and e.pk not in fixed_before and e.pk not in new_since]
        current = [e for e in events if not hasattr_correction(e)]

        def key(e):
            return (e.kind, e.pressed_at.replace(second=0, microsecond=0),
                    e.clock_type_id if e.kind != ClockEvent.Kind.OUT
                    else None)

        wanted = [key(e) for e in before]
        rows, missing = [], list(wanted)
        for event in current:
            k = key(event)
            if k in missing:
                missing.remove(k)
                rows.append({"id": event.pk, "kind": k[0], "at": k[1],
                             "type": k[2]})
            else:
                rows.append({"id": event.pk, "delete": True})
        for kind, at, type_id in missing:
            rows.append({"id": None, "kind": kind, "at": at,
                         "type": type_id})
        changes = [r for r in rows if r.get("delete") or not r.get("id")]
        if not changes:
            return None  # ya está como estaba
        text = "%s: quedaba %s; vuelve a %s" % (
            label,
            ", ".join("%s %s" % (e.kind, _hm(e.pressed_at))
                      for e in current) or "nada",
            ", ".join("%s %s" % (k[0], _hm(k[1])) for k in wanted)
            or "nada")
        if not apply:
            return text
        try:
            with transaction.atomic():
                edit_presses(
                    events[0].company_user, person, supervisor, REASON,
                    rows, source=ClockCorrection.Source.SYSTEM)
                ClockDayAiCheck.objects.filter(
                    company_user_id=user_id, day=day,
                ).update(corrected=False, summary=NOTE)
        except ClockCorrectionError as exc:
            return "SIN TOCAR (revisar a mano) %s: %s" % (label, exc)
        return text


def hasattr_correction(event):
    """Whether the press was corrected (it is not current)."""
    from django.core.exceptions import ObjectDoesNotExist

    try:
        return event.correction is not None
    except ObjectDoesNotExist:
        return False
