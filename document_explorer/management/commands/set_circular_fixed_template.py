# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/set_circular_fixed_template.py
"""
H30 (S124). Registers a fixed PDF as the current template of a circular.

---

H30 (S124). Da de alta un PDF fijo (sin variables, p. ej. el Plan
Nacional de calor del Ministerio de Sanidad) como plantilla vigente
(`current_template`) de una circular: lo sube al cubo, crea su entrada
en el índice con el tipo de la circular y apunta la circular a ella.
Origen: la plantilla del Plan de calor era la copia ya firmada por
Docuten de un trabajador (#40356, 2025); Miguel Ángel aportó el PDF
limpio de 2026, versionado en `document_explorer/fixed_templates/`
(documento público, sin datos de personas).

Idempotente: si el blob ya está en el índice, lo reutiliza. La
plantilla anterior no se borra ni se toca (sigue siendo el documento
del trabajador que es).

DRY-RUN POR DEFECTO. `--apply` escribe. `--log-file` obligatorio.
"""
import os
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, path_digest,
)
from spare_parts.gcs_service import upload_bytes

BUCKET = "cgs_grupo_alvarez"


class Command(BaseCommand):
    """
    Register a fixed PDF as a circular's current template.

    ---

    Da de alta un PDF fijo como plantilla vigente de una circular.
    """

    help = (
        "Sube un PDF fijo y lo deja como plantilla vigente de una "
        "circular (H30, S124). Dry-run por defecto; --apply escribe."
    )

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True)
        parser.add_argument("--file", required=True)
        parser.add_argument("--folder", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        """
        Print and append one timestamped line to the log, flushed.

        ---

        Escribe una línea con hora en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(options)

    def _run(self, options):
        """
        Upload, index and point the circular to the new template.

        ---

        Sube, indexa y apunta la circular a la plantilla nueva.
        """
        apply_changes = options["apply"]
        document_type = DocumentTypeCatalog.objects.filter(
            code=options["code"],
        ).first()
        if document_type is None:
            self._log("ERROR: no existe el tipo %s." % options["code"])
            raise CommandError("Tipo no encontrado.")
        path = options["file"]
        if not os.path.isfile(path):
            self._log("ERROR: no existe el archivo %s." % path)
            raise CommandError("Archivo no encontrado.")
        with open(path, "rb") as source:
            data = source.read()
        folder = options["folder"].strip("/")
        name = os.path.basename(path)
        blob_name = "%s/%s" % (folder, name)
        self._log("Modo: %s" % ("APPLY" if apply_changes else "DRY-RUN"))
        self._log("Circular: %s -- plantilla actual: %s" % (
            document_type.code,
            document_type.current_template_id or "ninguna",
        ))
        self._log("Archivo: %s (%d bytes) -> %s" % (
            path, len(data), blob_name,
        ))
        entry = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, blob_name_hash=path_digest(blob_name),
            deleted_at__isnull=True,
        ).first()
        if entry is not None:
            self._log("Ya indexado: #%d (no se vuelve a subir)." % entry.pk)
        if not apply_changes:
            self._log("DRY-RUN: no se escribe nada.")
            return
        if entry is None:
            upload_bytes(
                BUCKET, blob_name, data, content_type="application/pdf",
            )
            self._log("Subido a GCS: %s" % blob_name)
            ensure_folder_chain(BUCKET, folder)
            entry = DocumentIndexEntry.objects.create(
                bucket=BUCKET,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                blob_name=blob_name,
                blob_name_hash=path_digest(blob_name),
                parent_path=folder,
                parent_path_hash=path_digest(folder),
                name=name,
                size_bytes=len(data),
                content_type="application/pdf",
                document_type=document_type,
            )
            self._log("Indexado: #%d" % entry.pk)
        document_type.current_template = entry
        document_type.save(update_fields=["current_template"])
        self._log("Plantilla vigente de %s: #%d" % (
            document_type.code, entry.pk,
        ))
