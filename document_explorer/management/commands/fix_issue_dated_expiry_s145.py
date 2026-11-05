# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fix_issue_dated_expiry_s145.py
"""
H24 (S145). Documents of types that do not expire, with an expiry date.

---

H24 (S145). Documentos de tipos que no caducan (alta, baja, certificados:
`DocumentTypeCatalog.expires` desmarcado) con fecha de caducidad. Salían
en rojo en la ficha sin poder quitarlo (el alta de Berenguer Gómez:
"no sé tampoco concretamente a qué se refiere, porque las fechas están
bien"). La fecha que tenían como caducidad es la del documento.

- Con fecha del documento ya puesta: se quita la caducidad sin más.
- Sin ella: pasa a fecha del documento la del nombre de archivo
  (_AAAAMMDD, la que se ve en la ficha); si el nombre no trae fecha, la
  caducidad si no es futura. Una caducidad futura sin fecha en el
  nombre se queda sin fecha y se dice.

DRY-RUN POR DEFECTO; `--apply` escribe. Log propio en `--log-file`.
"""
import datetime
import re

from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry

_NAME_DATE = re.compile(r"_(\d{4})(\d{2})(\d{2})(?:_\d+)?\.[A-Za-z0-9]+$")


def _name_date(name):
    """Date of the canonical name (_YYYYMMDD) or None."""
    match = _NAME_DATE.search(name or "")
    if not match:
        return None
    try:
        return datetime.date(*map(int, match.groups()))
    except ValueError:
        return None


class Command(BaseCommand):
    help = "S145: quita la caducidad de los tipos que no caducan."

    def add_arguments(self, parser):
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
        today = datetime.date.today()
        _log("Caducidad en tipos que no caducan (S145) -- %s" % (
            "APLICANDO" if apply
            else "SIMULACIÓN (sin --apply no se escribe)"))
        entries = list(DocumentIndexEntry.objects.filter(
            deleted_at__isnull=True,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__expires=False,
            expiry_date__isnull=False,
        ).select_related("document_type").order_by(
            "document_type__code", "pk"))
        total = len(entries)
        cleared = dated = undated = 0
        for number, entry in enumerate(entries, 1):
            prefix = "%d/%d #%d %s" % (
                number, total, entry.pk, entry.document_type.code)
            new_issue = entry.issue_date
            if new_issue is None:
                new_issue = _name_date(entry.name) or (
                    entry.expiry_date if entry.expiry_date <= today
                    else None)
            if entry.issue_date is not None:
                cleared += 1
                what = "fecha del documento %s se queda" % (
                    entry.issue_date)
            elif new_issue is not None:
                dated += 1
                what = "fecha del documento -> %s" % new_issue
            else:
                undated += 1
                what = "SIN FECHA (caducidad futura y nombre sin fecha)"
            _log("%s %s | caducidad %s quitada | %s" % (
                prefix, entry.name, entry.expiry_date, what))
            if apply:
                entry.issue_date = new_issue
                entry.expiry_date = None
                entry.save(update_fields=["issue_date", "expiry_date"])
        log_file.write("\n")
        for text in (
            "RESUMEN",
            "Documentos: %d" % total,
            "Solo se quita la caducidad: %d" % cleared,
            "Con fecha del documento nueva: %d" % dated,
            "Quedan sin fecha: %d" % undated,
            "Escrito en la BD: %s" % ("sí" if apply else "no"),
        ):
            print(text, flush=True)
            log_file.write(text + "\n")
        log_file.close()
