# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_ingestion/management/commands/purge_orphaned_gcs_blobs.py
"""
Django management command: purge_orphaned_gcs_blobs.

Limpieza de blobs HUÉRFANOS en MACHINE_DOCUMENTS_BUCKET /
PERSONNEL_DOCUMENTS_BUCKET -- blobs que ya no tiene ningún
MachineDocument.gcs_blob_name / PersonalDocument.gcs_blob_name
apuntando a ellos. Origen (S026): un comando de reset escrito sin
comprobar antes si ya existía uno (document_ingestion.
reset_documentation, que sí borra GCS correctamente) solo limpió las
filas de BD y el archivo local de staging, dejando huérfanos los
blobs ya subidos a GCS de las 84 filas de MachineDocument borradas --
fallo real, corregido en la misma sesión.

Lista TODOS los blobs de cada bucket, calcula el conjunto de
gcs_blob_name todavía referenciados en BD, y borra (con --confirm) los
que no estén en ese conjunto. Dry-run por defecto -- solo lista lo que
borraría. Recorre las DOS carpetas de máquina (código real +
SIN_ASIGNAR) y de personal, sin acotar por empresa -- los nombres de
bucket ya son específicos de Grupo Álvarez
(enterprisebot-alvarez-machine-documents/-personnel-documents), pero
el filtro por gcs_blob_name referenciado en BD es la salvaguarda real,
no el nombre del bucket.

Uso:
    python -m dotenv run python manage.py purge_orphaned_gcs_blobs
    python -m dotenv run python manage.py purge_orphaned_gcs_blobs --confirm

---

Comando de gestión Django: purge_orphaned_gcs_blobs.

Borra blobs de GCS que ya no tienen ningún documento en BD apuntando
a ellos. Dry-run por defecto; --confirm obligatorio para borrar de
verdad.
"""
from django.core.management.base import BaseCommand

from machine_documents.models import MachineDocument
from personal_documents.models import PersonalDocument
from spare_parts.gcs_service import (
    MACHINE_DOCUMENTS_BUCKET,
    PERSONNEL_DOCUMENTS_BUCKET,
    get_storage_client,
)


class Command(BaseCommand):
    help = (
        "Borra blobs de GCS (MACHINE_DOCUMENTS_BUCKET/"
        "PERSONNEL_DOCUMENTS_BUCKET) que ya no tienen ningún "
        "documento en BD apuntando a ellos. Dry-run por defecto; "
        "--confirm para borrar de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm", action="store_true",
            help="Borra de verdad. Sin este flag, solo lista lo que "
                 "se borraría (dry-run).",
        )

    def _purge_bucket(self, client, bucket_name, referenced_blob_names, confirm):
        bucket = client.bucket(bucket_name)
        blobs = list(client.list_blobs(bucket))
        orphaned = [
            blob for blob in blobs if blob.name not in referenced_blob_names
        ]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"=== {bucket_name} -- {len(blobs)} blob(s) totales, "
            f"{len(orphaned)} huérfano(s) ===",
        ))
        for blob in orphaned:
            self.stdout.write(f"  {blob.name}")
            if confirm:
                blob.delete()

        if not orphaned:
            self.stdout.write("  (ninguno huérfano)")
        elif not confirm:
            self.stdout.write(self.style.WARNING(
                f"  Dry-run -- no se ha borrado nada. Repite con "
                f"--confirm para borrar de verdad.",
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"  {len(orphaned)} blob(s) borrado(s) de {bucket_name}.",
            ))

    def handle(self, *args, **options):
        confirm = options["confirm"]
        client = get_storage_client()

        machine_referenced = set(
            MachineDocument.objects
            .exclude(gcs_blob_name="")
            .values_list("gcs_blob_name", flat=True)
        )
        self._purge_bucket(
            client, MACHINE_DOCUMENTS_BUCKET, machine_referenced, confirm,
        )

        personal_referenced = set(
            PersonalDocument.objects
            .exclude(gcs_blob_name="")
            .values_list("gcs_blob_name", flat=True)
        )
        self._purge_bucket(
            client, PERSONNEL_DOCUMENTS_BUCKET, personal_referenced, confirm,
        )
