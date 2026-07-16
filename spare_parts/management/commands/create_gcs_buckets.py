# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/management/commands/create_gcs_buckets.py
"""
Django management command: create_gcs_buckets.

Comando de un solo uso (S022): crea los 4 buckets de la migración a
Google Cloud Storage (ver spare_parts/gcs_service.py), si no existen
ya -- idempotente, seguro de volver a ejecutar. Requiere que la
Service Account de GCP_CREDENTIALS_PATH tenga el rol roles/storage.admin
sobre el proyecto (ver docstring de gcs_service.py, sección
"Configuración manual requerida").

Uso:
    python -m dotenv run python manage.py create_gcs_buckets

---

Django management command: create_gcs_buckets.

One-time command (S022): creates the 4 buckets for the migration to
Google Cloud Storage (see spare_parts/gcs_service.py), if they don't
exist yet -- idempotent, safe to re-run. Requires the Service Account
in GCP_CREDENTIALS_PATH to have the roles/storage.admin role on the
project (see gcs_service.py docstring, "Configuración manual
requerida" section).

Usage:
    python -m dotenv run python manage.py create_gcs_buckets
"""
from django.core.management.base import BaseCommand

from spare_parts.gcs_service import (
    ALL_BUCKETS,
    GCSNotConfigured,
    get_storage_client,
    ensure_bucket,
)


class Command(BaseCommand):
    """
    Crea (si no existen) los 4 buckets de GCS de la plataforma.
    ---
    Creates (if they don't exist) the platform's 4 GCS buckets.
    """

    help = (
        "Crea los 4 buckets de Google Cloud Storage de EnterpriseBot "
        "(fotos de tarea, albaranes, documentación de centros de "
        "gasto, documentación de personal), si no existen ya. "
        "Idempotente."
    )

    def handle(self, *args, **options) -> None:
        """
        Punto de entrada. Itera ALL_BUCKETS y llama a ensure_bucket()
        para cada uno.
        ---
        Entry point. Iterates ALL_BUCKETS and calls ensure_bucket()
        for each.
        """
        try:
            client = get_storage_client()
        except GCSNotConfigured as exc:
            self.stderr.write(f"# {exc}")
            return

        for bucket_name in ALL_BUCKETS:
            bucket = client.bucket(bucket_name)
            already_existed = bucket.exists()
            ensure_bucket(client, bucket_name)
            if already_existed:
                self.stdout.write(
                    f"# Bucket '{bucket_name}' ya existía -- sin cambios."
                )
            else:
                self.stdout.write(
                    f"# Bucket '{bucket_name}' creado (location=EU, "
                    f"acceso uniforme, privado)."
                )

        self.stdout.write("# Los 4 buckets están listos.")
