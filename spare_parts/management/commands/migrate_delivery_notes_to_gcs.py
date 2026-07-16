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

Requiere --confirm -- se niega a ejecutar si no se pasa. --dry-run
muestra qué se migraría sin tocar BD ni GCS.

Uso:
    python -m dotenv run python manage.py migrate_delivery_notes_to_gcs \\
        --confirm

---

Django management command: migrate_delivery_notes_to_gcs.

One-time command (S022): for every DeliveryNote with drive_file_id
already set (uploaded to Drive before the migration) and
gcs_blob_name still empty, downloads the original file from Drive and
re-uploads it to Google Cloud Storage
(spare_parts.gcs_service.DELIVERY_NOTES_BUCKET). drive_file_id/
drive_web_link are NOT touched -- kept as legacy, explicit decision by
Miguel Ángel in S022 (traceability of what started on Drive).

Requires --confirm -- refuses to run otherwise. --dry-run shows what
would be migrated without touching BD or GCS.

Usage:
    python -m dotenv run python manage.py migrate_delivery_notes_to_gcs \\
        --confirm
"""
import io
import os
import tempfile

from django.core.management.base import BaseCommand, CommandError
from googleapiclient.http import MediaIoBaseDownload

from spare_parts.gcs_service import DELIVERY_NOTES_BUCKET, upload_file
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
        "todavía vacío. Requiere --confirm."
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
            help="Muestra qué se migraría, sin tocar BD ni GCS.",
        )

    def handle(self, *args, **options) -> None:
        """
        Punto de entrada. Itera cada DeliveryNote pendiente de migrar
        y ejecuta Drive -> local -> GCS -> BD para cada uno.
        ---
        Entry point. Iterates every DeliveryNote pending migration and
        runs Drive -> local -> GCS -> BD for each one.
        """
        dry_run = options["dry_run"]

        if not dry_run and not options["confirm"]:
            raise CommandError(
                "# Operación de migración de datos reales -- vuelve a "
                "ejecutar con --confirm para proceder, o con --dry-run "
                "para ver qué se migraría sin tocar nada."
            )

        pending = DeliveryNote.objects.exclude(
            drive_file_id="",
        ).filter(gcs_blob_name="")
        count = pending.count()
        self.stdout.write(
            f"# {count} albarán(es) con drive_file_id y sin migrar a GCS."
        )

        if count == 0:
            self.stdout.write("# Nada que migrar.")
            return

        try:
            drive_service = get_drive_service()
        except GDriveNotConfigured as exc:
            raise CommandError(f"# Drive no configurado: {exc}")

        migrated, failed = 0, 0
        for note in pending:
            if dry_run:
                self.stdout.write(
                    f"# [dry-run] Se migraría albarán #{note.pk} "
                    f"(drive_file_id={note.drive_file_id})."
                )
                continue

            try:
                # -- Metadata (nombre real del archivo en Drive) -----
                metadata = drive_service.files().get(
                    fileId=note.drive_file_id, fields="name",
                ).execute()
                original_name = metadata.get("name", f"{note.pk}.bin")
                extension = os.path.splitext(original_name)[1].lower()

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

                # -- Subida a GCS, misma convención de nombre que -----
                # upload_delivery_note_file() (spare_parts/gcs_service.py):
                # 'AAAA-MM/identificador_nombre'.
                year_month = note.created_at.strftime("%Y-%m")
                identifier = note.delivery_number or note.pk
                blob_name = f"{year_month}/{identifier}_{original_name}"
                upload_file(DELIVERY_NOTES_BUCKET, blob_name, tmp_path)
                os.remove(tmp_path)

                note.gcs_blob_name = blob_name
                note.save(update_fields=["gcs_blob_name"])

                migrated += 1
                self.stdout.write(
                    f"# Albarán #{note.pk} migrado a GCS (blob={blob_name})."
                )
            except Exception as exc:
                failed += 1
                self.stderr.write(
                    f"# Fallo migrando albarán #{note.pk} "
                    f"(drive_file_id={note.drive_file_id}): {exc}"
                )

        self.stdout.write(
            f"# Migración terminada: {migrated} migrado(s), "
            f"{failed} fallido(s) de {count} total."
        )
