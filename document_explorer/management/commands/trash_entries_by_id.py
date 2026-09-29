# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/trash_entries_by_id.py
"""
H30 (S123). Send specific documents to the trash by id.

---

H30 (S123). Manda a la papelera documentos concretos por id. Origen:
el acceso directo de Windows `MARMOL_SERRANO_ALVARO_MOD_145_20210101.lnk`
(id 39772), clasificado como Modelo 145 sin ser un documento; Miguel
Ángel: "borramos desde consola".

Mismo mecanismo que el resto de comandos `trash_*` (principio 4.12):
`trash_dossier_entry()`, escritura de índice pura (`deleted_at`/
`deleted_by`); el `blob_name` en GCS nunca se toca y el documento es
recuperable desde la papelera. Solo actúa sobre archivos vivos.

DRY-RUN POR DEFECTO. `--apply` manda a la papelera. `--log-file`
obligatorio: log propio en pantalla y en archivo a la vez.
"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.models import DocumentIndexEntry


class Command(BaseCommand):
    """
    Trash documents by id.

    ---

    Manda a la papelera documentos por id.
    """

    help = (
        "Manda a la papelera los documentos indicados por id (H30, "
        "S123). Dry-run por defecto; --apply escribe."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids", required=True, help="Ids separados por comas.",
        )
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        try:
            ids = [
                int(value) for value in options["ids"].split(",")
                if value.strip()
            ]
        except ValueError as exc:
            raise CommandError("Id no válido: %s" % exc)
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(ids, options["apply"])

    def _run(self, ids, apply):
        mode = "APPLY" if apply else "DRY-RUN"
        entries = list(DocumentIndexEntry.objects.filter(
            pk__in=ids, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).select_related("document_type").order_by("id"))
        self._log(
            "Inicio (%s): %d id(s) pedidos, %d archivo(s) vivos."
            % (mode, len(ids), len(entries))
        )
        found = {entry.pk for entry in entries}
        for missing in sorted(set(ids) - found):
            self._log("  id=%d -- no existe o ya está en la papelera." % missing)
        trashed = 0
        for entry in entries:
            label = "%s (%s)" % (
                entry.name,
                entry.document_type.code if entry.document_type_id else "sin tipo",
            )
            if apply:
                if trash_dossier_entry(entry):
                    trashed += 1
                    self._log("  id=%d %s -- a la papelera." % (entry.pk, label))
                else:
                    self._log(
                        "  id=%d %s -- ERROR: sin usuario de papelera."
                        % (entry.pk, label)
                    )
            else:
                self._log("  id=%d %s -- iría a la papelera." % (entry.pk, label))
        self._log("Fin (%s): %d a la papelera." % (mode, trashed))
