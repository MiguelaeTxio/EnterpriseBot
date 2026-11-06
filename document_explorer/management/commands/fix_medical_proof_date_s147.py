# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fix_medical_proof_date_s147.py
"""
H24 (S147). Restore the date of the SAS medical proof 36621.

---

H24 (S147). El retipado de retype_medical_proofs_s147 dejó el
justificante 36621 (Muñoz Cara) con la fecha de su indexación en el
nombre (20260729): no tenía issue_date y el nombre canónico tomó la de
reserva, perdiendo el 20260820 que le puso Miguel Ángel en S127
(fix_review_names_s127). Se le pone esa fecha como issue_date y se
vuelve a sacar su nombre canónico (apply_personal_canonical_rename,
solo nombre virtual: 4.12). El texto del SAS lee "20/05/26"; se respeta
la fecha que decidió Miguel Ángel en S127.

DRY-RUN POR DEFECTO; `--apply` escribe. Log propio en `--log-file`,
pantalla y archivo a la vez.
"""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from document_explorer.classification_service import (
    apply_personal_canonical_rename,
)
from document_explorer.models import DocumentIndexEntry

PK = 36621
DATE = datetime.date(2026, 8, 20)
CODE = "JUSTIFICANTE_ASISTENCIA_MEDICA"


class Command(BaseCommand):
    help = "S147: fecha del justificante 36621 y su nombre canónico."

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
        _log("Fecha del justificante %d (S147) -- %s" % (
            PK, "APLICANDO" if apply
            else "SIMULACIÓN (sin --apply no se escribe)"))
        entry = DocumentIndexEntry.objects.select_related(
            "document_type").filter(pk=PK, deleted_at__isnull=True).first()
        code = entry.document_type.code if entry and entry.document_type_id \
            else ""
        if entry is None or code != CODE or entry.issue_date:
            _log("SALTADO: no existe, no es %s o ya tiene fecha (%s)" % (
                CODE, entry.issue_date if entry else "-"))
            log_file.close()
            return
        _log("Antes: %s, sin fecha" % entry.name)
        if apply:
            with transaction.atomic():
                entry.issue_date = DATE
                entry.save(update_fields=["issue_date"])
                result = apply_personal_canonical_rename(
                    entry, apply_changes=True)
            _log("HECHO: fecha %s, ahora %s" % (
                DATE.strftime("%d/%m/%Y"),
                result.get("new_name") or entry.name))
        else:
            _log("Se pondría la fecha %s y su nombre canónico." % (
                DATE.strftime("%d/%m/%Y")))
        log_file.close()
