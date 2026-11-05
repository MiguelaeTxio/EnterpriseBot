# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/apply_person_corrections.py
"""
H24 (S145). Apply reviewed corrections to person files from a JSON file.

---

H24 (S145). Correcciones revisadas a mano de las fichas (y de la
caducidad de algún documento), leídas de un JSON que se escribe en SWAP
en el propio Comando S: los datos de personas nunca van a git.

Formato:
    {"people": [{"id": 8, "fields": {"city": "MÁLAGA", ...}}],
     "entries": [{"id": 52781, "expiry_date": "2030-11-26"}]}

Solo los campos de `PERSON_FIELDS`; las fechas en AAAA-MM-DD. Cada
cambio se registra antes -> después. DRY-RUN POR DEFECTO; `--apply`
escribe. Log propio en `--log-file`.
"""
import datetime
import json

from django.core.management.base import BaseCommand, CommandError

from document_explorer.models import DocumentIndexEntry, PersonIdentity

PERSON_FIELDS = {
    "hire_date": "date", "birth_date": "date", "dni_expiry_date": "date",
    "driving_license_expiry_date": "date", "medical_exam_date": "date",
    "address_street": "text", "city": "text", "province": "text",
    "ss_affiliation_number": "text",
}


def _value(kind, raw):
    """Typed value of a JSON field."""
    if kind == "date":
        return datetime.date.fromisoformat(raw) if raw else None
    return raw or ""


class Command(BaseCommand):
    help = "S145: aplica correcciones revisadas de fichas desde un JSON."

    def add_arguments(self, parser):
        parser.add_argument("--json", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def handle(self, *args, **options):
        log_file = open(options["log_file"], "a", encoding="utf-8")

        def _log(text):
            line = "[%s] %s" % (
                datetime.datetime.now().strftime("%H:%M:%S"), text)
            print(line, flush=True)
            log_file.write(line + "\n")
            log_file.flush()

        apply = options["apply"]
        with open(options["json"], encoding="utf-8") as handle:
            data = json.load(handle)
        _log("Correcciones revisadas de fichas (S145) -- %s" % (
            "APLICANDO" if apply
            else "SIMULACIÓN (sin --apply no se escribe)"))
        changed = unchanged = 0
        people = data.get("people", [])
        for number, item in enumerate(people, 1):
            person = PersonIdentity.objects.filter(pk=item["id"]).first()
            if person is None:
                raise CommandError("No existe la persona id=%s" % item["id"])
            _log("%d/%d %s %s, %s (id=%d)" % (
                number, len(people), person.first_surname,
                person.second_surname, person.given_name, person.pk))
            to_write = []
            for field, raw in item["fields"].items():
                if field not in PERSON_FIELDS:
                    raise CommandError("Campo no permitido: %s" % field)
                new = _value(PERSON_FIELDS[field], raw)
                old = getattr(person, field)
                if old == new:
                    unchanged += 1
                    continue
                _log("    %s: %s -> %s" % (field, old or "(vacío)", new))
                setattr(person, field, new)
                to_write.append(field)
                changed += 1
            if apply and to_write:
                person.save(update_fields=to_write)
        for item in data.get("entries", []):
            entry = DocumentIndexEntry.objects.get(pk=item["id"])
            new = _value("date", item["expiry_date"])
            _log("Documento #%d %s: caducidad %s -> %s" % (
                entry.pk, entry.name, entry.expiry_date, new))
            if entry.expiry_date != new:
                changed += 1
                if apply:
                    entry.expiry_date = new
                    entry.save(update_fields=["expiry_date"])
        log_file.write("\n")
        for text in (
            "RESUMEN",
            "Cambios: %d" % changed,
            "Ya estaban así: %d" % unchanged,
            "Escrito en la BD: %s" % ("sí" if apply else "no"),
        ):
            print(text, flush=True)
            log_file.write(text + "\n")
        log_file.close()
