# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/import_vacation_forms_s141.py
"""
H24 (S141). Registers as VacationPeriod the vacation forms ("partes de
vacaciones") of 2025 and 2026 found in the bucket.

---

H24 (S141). Da de alta como VacationPeriod los partes de vacaciones de
2025 y 2026 que hay en el cubo (búsqueda "vacaciones" en el índice del
explorador, OCR ya cacheado). Miguel Ángel (S141): "esas partes y ya
esperamos el resto". Fechas leídas del propio parte (FECHA INICIO y
FECHA FINALIZACIÓN), una vez por periodo: los duplicados del cubo
(`_1`) no se repiten.

- `operator` vacío a propósito: son vacaciones ya disfrutadas y no
  deben generar la tarea fantasma del parte (VacationPeriod.save).
- No da de alta un periodo que ya se solapa con otro de la misma
  persona (se anota en el log).
- Por defecto solo muestra lo que haría; con --apply lo guarda.
  `--log-file` obligatorio (pantalla y archivo a la vez).
"""
import datetime
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from document_explorer.models import PersonIdentity
from hr_calendar.models import VacationPeriod
from ivr_config.models import Company

COMPANY_SLUG = "grupo-alvarez"

# (documento del cubo, persona, desde, hasta)
FORMS = [
    (40133, 49, date(2025, 6, 2), date(2025, 6, 15)),
    (40219, 219, date(2025, 7, 21), date(2025, 8, 4)),
    (34076, 151, date(2025, 8, 18), date(2025, 9, 1)),
    (34734, 155, date(2025, 12, 22), date(2026, 1, 4)),
    (40134, 49, date(2025, 12, 22), date(2026, 1, 6)),
    (34077, 151, date(2026, 1, 19), date(2026, 2, 2)),
    (39844, 213, date(2026, 3, 23), date(2026, 3, 29)),
    (34897, 85, date(2026, 5, 4), date(2026, 5, 10)),
    (35736, 159, date(2026, 5, 18), date(2026, 5, 31)),
    (40220, 219, date(2026, 6, 29), date(2026, 7, 13)),
    (42801, 151, date(2026, 7, 9), date(2026, 7, 9)),
    (43886, 178, date(2026, 7, 13), date(2026, 7, 27)),
    (41709, 154, date(2026, 8, 3), date(2026, 8, 17)),
    (42802, 151, date(2026, 8, 10), date(2026, 8, 23)),
    (43100, 85, date(2026, 9, 3), date(2026, 9, 17)),
    (43248, 169, date(2026, 9, 7), date(2026, 9, 21)),
    (43819, 161, date(2026, 9, 10), date(2026, 9, 11)),
]


class Command(BaseCommand):
    """
    Register the 2025-2026 vacation forms as VacationPeriod.

    ---

    Da de alta los partes de vacaciones de 2025-2026 como periodos.
    """

    help = (
        "Da de alta como VacationPeriod los partes de vacaciones de "
        "2025 y 2026 del cubo (H24, S141). Sin --apply solo muestra."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        """
        Print and append one timestamped line to the log, flushed.

        ---

        Escribe una línea con hora en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (
            datetime.datetime.now().strftime("%H:%M:%S"), message,
        )
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._run(options["apply"])

    def _run(self, apply):
        mode = "GUARDANDO" if apply else "SIMULACIÓN (sin --apply)"
        self._log("Inicio: partes de vacaciones 2025-2026 -- %s." % mode)
        company = Company.objects.filter(slug=COMPANY_SLUG).first()
        if company is None:
            self._log("ERROR: no existe la empresa %s." % COMPANY_SLUG)
            raise CommandError("Empresa no encontrada.")
        created = skipped = 0
        for position, (doc_id, person_id, start, end) in enumerate(
                FORMS, start=1):
            person = PersonIdentity.objects.filter(pk=person_id).first()
            label = "%d/%d doc %d" % (position, len(FORMS), doc_id)
            if person is None:
                self._log(
                    "%s: NO EXISTE la persona %d." % (label, person_id),
                )
                skipped += 1
                continue
            name = "%s %s" % (person.first_surname, person.given_name)
            overlap = VacationPeriod.objects.filter(
                person=person, date_start__lte=end, date_end__gte=start,
            ).first()
            if overlap is not None:
                self._log("%s: %s %s-%s YA SOLAPA con el periodo %d "
                          "(%s-%s); no se da de alta." % (
                              label, name, start, end, overlap.pk,
                              overlap.date_start, overlap.date_end))
                skipped += 1
                continue
            if apply:
                with transaction.atomic():
                    period = VacationPeriod.objects.create(
                        person=person, company=company,
                        date_start=start, date_end=end,
                    )
                self._log("%s: %s %s a %s -> periodo %d." % (
                    label, name, start, end, period.pk))
            else:
                self._log("%s: %s %s a %s -> se daría de alta." % (
                    label, name, start, end))
            created += 1
        self._log("Fin. %s: %d; no dados de alta: %d." % (
            "Dados de alta" if apply else "Se darían de alta", created,
            skipped))
