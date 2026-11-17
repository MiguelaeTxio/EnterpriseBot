# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/recheck_albaran_vehicle_s149.py
"""
Read «Vehículo en obra» on the albaranes already loaded and recompare.

---

S149 (Miguel Ángel, 17/11: "¿podemos ejecutar un comando para los
albaranes cargados?"). Las casillas «Vehículo en obra» y «Continuación
día ant.» se leen desde el 17/11 (migración 0044); los albaranes
cargados antes no las tienen. Para cada archivo ya leído:
1. Gemini lee solo esas dos casillas de cada albarán del archivo (una
   llamada por archivo) y se guardan (es un dato del albarán, no cambia
   ningún fichaje).
2. Con --apply, se vuelven a cotejar los días a los que cambia algo: el
   día con «Vehículo en obra» y el siguiente de ese trabajador (y el de
   «Continuación día ant.»). No se tocan los días visados ni los que un
   supervisor ha corregido a mano: se listan para que los revise.
Sin --apply lee y guarda las casillas y dice qué días se cotejarían.
Log propio, pantalla y archivo a la vez, con progreso y ETA
(com-standards 0bis/0ter).
"""
import datetime
import json
import time
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.utils import timezone

_PROMPT = """
Eres un lector de partes de producción (albaranes) de una empresa de
grúas. El documento es una foto o un escaneo; puede traer uno o varios
albaranes.

De cada albarán devuelve solo:
- number: el número de albarán impreso (p. ej. 348153).
- vehicle_on_site: true si está marcada la casilla "Vehículo en obra"
  (arriba, junto al número de albarán); false si está vacía.
- continues_previous: true si está marcada la casilla "Continuación día
  ant." (junto a la anterior); false si está vacía.
"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "albaranes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "vehicle_on_site": {"type": "boolean"},
                    "continues_previous": {"type": "boolean"},
                },
                "required": ["number", "vehicle_on_site",
                             "continues_previous"],
            },
        },
    },
    "required": ["albaranes"],
}


def _read_boxes(data, mime):
    from google.genai.types import GenerateContentConfig, HttpOptions, Part

    from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
    from document_explorer.classification_service import (
        _generate_content_with_retry,
    )

    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=data, mime_type=mime), _PROMPT],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=180_000),
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            temperature=0.0,
        ),
    )
    return json.loads(response.text.strip()).get("albaranes") or []


def _name(person):
    """Surnames and name, without the DNI (the log goes through Drive)."""
    return " ".join(filter(None, (person.first_surname,
                                  person.second_surname))) + ", " + (
        person.given_name or "")


def _digits(text):
    return "".join(ch for ch in str(text or "") if ch.isdigit())


class Command(BaseCommand):
    """
    Read the «Vehículo en obra» boxes of old albaranes and recompare.
    ---
    Lee «Vehículo en obra» de los albaranes ya cargados y recoteja.
    """

    help = ("Lee «Vehículo en obra» / «Continuación día ant.» de los "
            "albaranes ya cargados y vuelve a cotejar los días afectados.")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)
        # 17/11: con las peticiones seguidas, Vertex devuelve 429
        # (RESOURCE_EXHAUSTED; la cuota se comparte con la lectura de
        # albaranes en Celery): una pausa entre archivos.
        parser.add_argument("--pause", type=float, default=10.0)

    def _log(self, text):
        line = "[%s] %s" % (timezone.localtime().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._pause = options["pause"]
            self._run(options["apply"])

    def _run(self, apply):
        from hr_calendar.albaran_check import mime_of, staged_bytes
        from hr_calendar.models import AlbaranSheet

        files = defaultdict(list)
        for sheet in AlbaranSheet.objects.filter(
                status=AlbaranSheet.Status.READ, person__isnull=False,
        ).select_related("person").order_by("staged_path", "position"):
            files[sheet.staged_path].append(sheet)
        total = len(files)
        self._log("Albaranes leídos: %d archivos, %d albaranes (%s)" % (
            total, sum(len(v) for v in files.values()),
            "APLICANDO" if apply else "simulación: se leen las casillas, "
            "sin recotejar"))
        start = datetime.datetime.now()
        flagged, failed = [], []
        for index, (path, sheets) in enumerate(files.items(), 1):
            first = sheets[0]
            if index > 1:
                time.sleep(self._pause)
            found = self._read(first, mime_of, staged_bytes)
            if found is None:
                failed.append(first.original_name)
                continue
            by_number = {_digits(i.get("number")): i for i in found}
            for sheet in sheets:
                item = by_number.get(_digits(sheet.number))
                if item is None and len(sheets) == 1 and len(found) == 1:
                    item = found[0]
                if item is None:
                    self._log("  %s: no se encuentra el albarán %s en la "
                              "lectura" % (sheet.original_name, sheet.number))
                    continue
                sheet.vehicle_on_site = bool(item.get("vehicle_on_site"))
                sheet.continues_previous = bool(
                    item.get("continues_previous"))
                sheet.save(update_fields=["vehicle_on_site",
                                          "continues_previous"])
                if sheet.vehicle_on_site or sheet.continues_previous:
                    flagged.append(sheet)
                    self._log("  Albarán %s (%s, %s):%s%s" % (
                        sheet.number, _name(sheet.person), sheet.day,
                        " vehículo en obra" if sheet.vehicle_on_site
                        else "",
                        " continuación día ant."
                        if sheet.continues_previous else ""))
            elapsed = (datetime.datetime.now() - start).total_seconds()
            eta = elapsed / index * (total - index)
            self._log("[%d/%d] %s · quedan ~%d min" % (
                index, total, first.original_name, eta // 60))
        days = set()
        for sheet in flagged:
            days.add((sheet.person_id, sheet.day))
            if sheet.vehicle_on_site:
                days.add((sheet.person_id,
                          sheet.day + datetime.timedelta(days=1)))
        self._log("Casillas marcadas: %d albarán/es; días que cambian: %d; "
                  "sin leer: %d%s" % (len(flagged), len(days), len(failed),
                                      (" (" + ", ".join(failed) + ")")
                                      if failed else ""))
        self._recompare(sorted(days), apply)

    QUOTA_WAIT = 120
    QUOTA_TRIES = 3

    def _read(self, sheet, mime_of, staged_bytes):
        """
        The boxes of a file, waiting out Gemini's quota; None if it fails.
        ---
        Las casillas de un archivo. Si Vertex sigue diciendo 429 después
        de sus reintentos, espera QUOTA_WAIT segundos y vuelve a probar
        (QUOTA_TRIES veces); cualquier otro error, o la cuota agotada al
        final, deja el archivo sin leer (None) y se sigue.
        """
        for attempt in range(1, self.QUOTA_TRIES + 2):
            try:
                data = staged_bytes(sheet)
                return _read_boxes(data, mime_of(data))
            except Exception as exc:  # noqa: BLE001 -- se anota y se sigue
                quota = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
                if quota and attempt <= self.QUOTA_TRIES:
                    self._log("  %s: cuota de Gemini agotada, espero %d s "
                              "(%d/%d)" % (sheet.original_name,
                                           self.QUOTA_WAIT, attempt,
                                           self.QUOTA_TRIES))
                    time.sleep(self.QUOTA_WAIT)
                    continue
                self._log("  ERROR %s: %s" % (sheet.original_name,
                                              str(exc)[:200]))
                return None
        return None

    def _recompare(self, days, apply):
        from hr_calendar.albaran_check import compare_day
        from hr_calendar.models import (
            AlbaranSheet, ClockCorrection, ClockDayReview,
        )

        tz = timezone.get_current_timezone()
        done, skipped = 0, []
        for person_id, day in days:
            sheet = AlbaranSheet.objects.filter(
                person_id=person_id, day=day,
                status=AlbaranSheet.Status.READ,
            ).select_related("batch", "person").order_by(
                "-batch__created_at").first()
            if sheet is None:
                continue  # el día siguiente sin albarán: nada que cotejar
            person = sheet.person
            label = "%s %s" % (_name(person), day.strftime("%d/%m/%Y"))
            company_user = person.company_user
            if company_user is None:
                skipped.append("%s: sin usuario del panel" % label)
                continue
            start = timezone.make_aware(
                datetime.datetime.combine(day, datetime.time.min), tz)
            end = start + datetime.timedelta(days=1)
            if ClockDayReview.objects.filter(company_user=company_user,
                                             day=day).exists():
                skipped.append("%s: ya visado" % label)
                continue
            if ClockCorrection.objects.filter(
                    source=ClockCorrection.Source.MANUAL,
                    event__company_user=company_user,
                    event__pressed_at__gte=start,
                    event__pressed_at__lt=end,
            ).exists():
                skipped.append("%s: corregido a mano por un supervisor"
                               % label)
                continue
            if not apply:
                self._log("  Se cotejaría: %s" % label)
                continue
            check = compare_day(sheet.batch, day, person)
            done += 1
            self._log("  Cotejado %s%s" % (
                label, (": " + check.summary.replace("\n", " / "))
                if check else ""))
        for line in skipped:
            self._log("  SIN TOCAR (revisar a mano) %s" % line)
        self._log("Fin: %d día/s cotejado/s, %d sin tocar." % (
            done, len(skipped)))
