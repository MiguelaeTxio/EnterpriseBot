# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/management/commands/migrate_delivery_notes_to_gcs.py
"""
Django management command: migrate_delivery_notes_to_gcs.

Comando de un solo uso (S022): para cada DeliveryNote con
drive_file_id ya asignado (subido a Drive antes de la migración) y
gcs_blob_name todavía vacío, descarga el archivo original de Drive y
lo vuelve a subir a Google Cloud Storage
(spare_parts.gcs_service.DELIVERY_NOTES_BUCKET). drive_file_id/
drive_web_link NO se tocan -- quedan como legado, decisión explícita
de Miguel Ángel en S022 (trazabilidad de lo que empezó en Drive).

BUG CORREGIDO EN S022 (misma sesión, tras la primera ejecución real):
el nombre que Drive ya tenía guardado para cada archivo (metadata
"name") YA incluía el número de albarán como prefijo -- así lo puso
en su día upload_delivery_note_file() (Drive). La primera versión de
este comando volvía a anteponer ese mismo identificador, generando
nombres duplicados y anidados de forma no intencionada cuando el
número de albarán contenía '/' (ej.
"2026-07/BA/2606366_BA/2606366_albaran-camara_....jpg"). Corregido:
ya no se antepone el identificador (el nombre de Drive es la única
fuente), y se sanea cualquier '/' embebido vía
gcs_service.sanitize_path_component(). Ver --repair más abajo para
recomponer los registros ya migrados con el nombre incorrecto.

Requiere --confirm -- se niega a ejecutar si no se pasa. --dry-run
muestra qué se migraría/repararía sin tocar BD ni GCS. --repair
procesa también los que YA tienen gcs_blob_name, comparando contra el
nombre correcto derivado ahora mismo -- si difiere, borra el blob
viejo (mal nombrado) y sube uno nuevo con el nombre correcto.

Uso:
    python -m dotenv run python manage.py migrate_delivery_notes_to_gcs \\
        --confirm
    python -m dotenv run python manage.py migrate_delivery_notes_to_gcs \\
        --repair --confirm

---

Django management command: migrate_delivery_notes_to_gcs.

One-time command (S022): for every DeliveryNote with drive_file_id
already set (uploaded to Drive before the migration) and
gcs_blob_name still empty, downloads the original file from Drive and
re-uploads it to Google Cloud Storage
(spare_parts.gcs_service.DELIVERY_NOTES_BUCKET). drive_file_id/
drive_web_link are NOT touched -- kept as legacy, explicit decision by
Miguel Ángel in S022 (traceability of what started on Drive).

BUG FIXED IN S022 (same session, after the first real run): the name
Drive already had stored for each file (the "name" metadata) ALREADY
included the delivery number as a prefix -- that's how
upload_delivery_note_file() (Drive) named it originally. The first
version of this command prepended that same identifier again,
producing duplicated, unintentionally nested names whenever the
delivery number contained '/' (e.g.
"2026-07/BA/2606366_BA/2606366_albaran-camara_....jpg"). Fixed: the
identifier is no longer prepended (Drive's name is the only source),
and any embedded '/' is sanitized via
gcs_service.sanitize_path_component(). See --repair below to fix
records already migrated with the wrong name.

Requires --confirm -- refuses to run otherwise. --dry-run shows what
would be migrated/repaired without touching BD or GCS. --repair also
processes notes that already have a gcs_blob_name, comparing against
the correct name derived right now -- if it differs, deletes the old
(wrongly named) blob and uploads a new one with the correct name.

Usage:
    python -m dotenv run python manage.py migrate_delivery_notes_to_gcs \\
        --confirm
    python -m dotenv run python manage.py migrate_delivery_notes_to_gcs \\
        --repair --confirm
"""
import io
import os
import tempfile

from django.core.management.base import BaseCommand, CommandError
from googleapiclient.http import MediaIoBaseDownload

from spare_parts.gcs_service import (
    DELIVERY_NOTES_BUCKET,
    sanitize_path_component,
    delete_file,
    upload_file,
)
from spare_parts.gdrive_service import GDriveNotConfigured, get_drive_service
from spare_parts.models import DeliveryNote


class Command(BaseCommand):
    """
    Migra los albaranes ya subidos a Drive hacia GCS (Drive -> local
    temporal -> GCS), uno por uno, sin tocar drive_file_id/
    drive_web_link.
    ---
    Migrates delivery notes already uploaded to Drive over to GCS
    (Drive -> local temp -> GCS), one at a time, without touching
    drive_file_id/drive_web_link.
    """

    help = (
        "Descarga de Drive y vuelve a subir a Google Cloud Storage cada "
        "DeliveryNote con drive_file_id ya asignado y gcs_blob_name "
        "todavía vacío (o, con --repair, recompone también los que ya "
        "tienen gcs_blob_name mal nombrado). Requiere --confirm."
    )

    def add_arguments(self, parser) -> None:
        """
        Define los argumentos de línea de comandos.
        ---
        Defines the command-line arguments.
        """
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Obligatorio -- confirma la operación.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Muestra qué se migraría/repararía, sin tocar BD ni GCS.",
        )
        parser.add_argument(
            "--repair",
            action="store_true",
            default=False,
            help=(
                "Procesa también los albaranes que YA tienen "
                "gcs_blob_name, recomponiéndolos si el nombre correcto "
                "derivado ahora difiere del guardado (borra el blob "
                "viejo mal nombrado)."
            ),
        )

    def _derive_blob_name(self, original_name: str, year_month: str) -> str:
        """
        Deriva el nombre de blob correcto: 'AAAA-MM/<nombre de Drive
        saneado>'. El nombre de Drive ya incluye el identificador del
        albarán (puesto por upload_delivery_note_file histórico) --
        nunca se vuelve a anteponer aquí (ver docstring del módulo).
        ---
        Derives the correct blob name: 'AAAA-MM/<sanitized Drive
        name>'. Drive's name already includes the delivery
        identifier (set by the historical upload_delivery_note_file)
        -- never prepended again here (see module docstring).
        """
        return f"{year_month}/{sanitize_path_component(original_name)}"

    def handle(self, *args, **options) -> None:
        """
        Punto de entrada. Itera cada DeliveryNote pendiente (o, con
        --repair, también las ya migradas) y ejecuta
        Drive -> local -> GCS -> BD para cada una que lo necesite.
        ---
        Entry point. Iterates every pending DeliveryNote (or, with
        --repair, also already-migrated ones) and runs
        Drive -> local -> GCS -> BD for each one that needs it.
        """
        dry_run = options["dry_run"]
        repair = options["repair"]

        if not dry_run and not options["confirm"]:
            raise CommandError(
                "# Operación de migración de datos reales -- vuelve a "
                "ejecutar con --confirm para proceder, o con --dry-run "
                "para ver qué se migraría/repararía sin tocar nada."
            )

        candidates = DeliveryNote.objects.exclude(drive_file_id="")
        if not repair:
            candidates = candidates.filter(gcs_blob_name="")
        count = candidates.count()
        self.stdout.write(
            f"# {count} albarán(es) candidato(s) "
            f"({'modo reparación' if repair else 'solo pendientes'})."
        )

        if count == 0:
            self.stdout.write("# Nada que hacer.")
            return

        try:
            drive_service = get_drive_service()
        except GDriveNotConfigured as exc:
            raise CommandError(f"# Drive no configurado: {exc}")

        migrated, repaired, skipped, failed = 0, 0, 0, 0
        for note in candidates:
            try:
                # -- Metadata (nombre real del archivo en Drive) -----
                metadata = drive_service.files().get(
                    fileId=note.drive_file_id, fields="name",
                ).execute()
                original_name = metadata.get("name", f"{note.pk}.bin")
                extension = os.path.splitext(original_name)[1].lower()
                year_month = note.created_at.strftime("%Y-%m")
                correct_blob_name = self._derive_blob_name(
                    original_name, year_month,
                )

                needs_repair = (
                    repair
                    and note.gcs_blob_name
                    and note.gcs_blob_name != correct_blob_name
                )
                needs_migration = not note.gcs_blob_name

                if not needs_migration and not needs_repair:
                    skipped += 1
                    continue

                if dry_run:
                    action = "repararía" if needs_repair else "migraría"
                    self.stdout.write(
                        f"# [dry-run] Se {action} albarán #{note.pk} "
                        f"-> blob={correct_blob_name}"
                        + (
                            f" (blob viejo={note.gcs_blob_name})"
                            if needs_repair else ""
                        )
                    )
                    continue

                # -- Descarga a un archivo temporal local ------------
                request = drive_service.files().get_media(
                    fileId=note.drive_file_id,
                )
                buffer = io.BytesIO()
                downloader = MediaIoBaseDownload(buffer, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

                with tempfile.NamedTemporaryFile(
                    suffix=extension, delete=False,
                ) as tmp:
                    tmp.write(buffer.getvalue())
                    tmp_path = tmp.name

                old_blob_name = note.gcs_blob_name
                upload_file(DELIVERY_NOTES_BUCKET, correct_blob_name, tmp_path)
                os.remove(tmp_path)

                if needs_repair and old_blob_name:
                    delete_file(DELIVERY_NOTES_BUCKET, old_blob_name)

                note.gcs_blob_name = correct_blob_name
                note.save(update_fields=["gcs_blob_name"])

                if needs_repair:
                    repaired += 1
                    self.stdout.write(
                        f"# Albarán #{note.pk} reparado en GCS "
                        f"(blob viejo={old_blob_name} -> "
                        f"blob nuevo={correct_blob_name})."
                    )
                else:
                    migrated += 1
                    self.stdout.write(
                        f"# Albarán #{note.pk} migrado a GCS "
                        f"(blob={correct_blob_name})."
                    )
            except Exception as exc:
                failed += 1
                self.stderr.write(
                    f"# Fallo procesando albarán #{note.pk} "
                    f"(drive_file_id={note.drive_file_id}): {exc}"
                )

        self.stdout.write(
            f"# Terminado: {migrated} migrado(s), {repaired} "
            f"reparado(s), {skipped} ya correcto(s), {failed} "
            f"fallido(s) de {count} candidato(s)."
        )
