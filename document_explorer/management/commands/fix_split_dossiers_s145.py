# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fix_split_dossiers_s145.py
"""
H24 (S145). Archivos ya separados antes del tipo "Dossier".

---

H24 (S145). Lo que se separó con "Separar" antes de existir el tipo
"Dossier" (el de Berenguer Gómez): el original se quedó con su tipo
viejo (DNI) marcado como no vigente, y en el Historial del DNI
aparecía como un DNI posterior al vigente. Miguel Ángel: "está mal
tipado. Tendríamos que tener un tipo para dossier".

- Original separado (nota "Separado:") que no es Dossier: pasa a
  Dossier con el cambio de tipo completo del panel y vuelve a verse.
- Lo sacado de un dossier con caducidad anterior a 1950: siglo mal
  leído (la tarjeta CAP de Berenguer quedó en 1927 por 2027); se le
  suman 100 años.

DRY-RUN POR DEFECTO; `--apply` escribe. Log propio en `--log-file`.
"""
import datetime

from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from document_explorer.subject_upload_service import change_document_type


class Command(BaseCommand):
    help = "S145: originales separados a Dossier y siglos mal leídos."

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
        _log("Separados antes del tipo Dossier (S145) -- %s" % (
            "APLICANDO" if apply
            else "SIMULACIÓN (sin --apply no se escribe)"))
        dossier = DocumentTypeCatalog.objects.get(code="DOSSIER")
        live = DocumentIndexEntry.objects.filter(
            deleted_at__isnull=True,
            entry_kind=DocumentIndexEntry.KIND_FILE,
        ).select_related("document_type")
        originals = list(live.filter(
            curator_note__contains="Separado:").exclude(
                document_type=dossier))
        for entry in originals:
            _log("A DOSSIER: #%d %s (era %s)" % (
                entry.pk, entry.name,
                entry.document_type.code if entry.document_type_id
                else "sin tipo"))
            if apply:
                change_document_type(entry, dossier)
                entry.is_obsolete = False
                entry.save(update_fields=["is_obsolete"])
        century = list(live.filter(
            curator_note__contains="Sacado del dossier",
            expiry_date__lt=datetime.date(1950, 1, 1)))
        for entry in century:
            fixed = entry.expiry_date.replace(
                year=entry.expiry_date.year + 100)
            _log("SIGLO: #%d %s caducidad %s -> %s" % (
                entry.pk, entry.name, entry.expiry_date, fixed))
            if apply:
                entry.expiry_date = fixed
                entry.save(update_fields=["expiry_date"])
        log_file.write("\n")
        for text in (
            "RESUMEN",
            "A Dossier: %d" % len(originals),
            "Siglo corregido: %d" % len(century),
            "Escrito en la BD: %s" % ("sí" if apply else "no"),
        ):
            print(text, flush=True)
            log_file.write(text + "\n")
        log_file.close()
