# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0202_databasebackup_s146.py
# H24 (S146): copias de seguridad de la base de datos (volcado del
# servidor, bajado a OneDrive por el agente H28).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0201_excedencia_expires_s145"),
    ]

    operations = [
        migrations.CreateModel(
            name="DatabaseBackup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file_name", models.CharField(max_length=100, unique=True, verbose_name="Archivo")),
                ("blob_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Objeto en GCS")),
                ("status", models.CharField(choices=[("running", "Volcando"), ("ready", "Lista para bajar"), ("downloaded", "En OneDrive"), ("failed", "Fallida")], default="running", max_length=20, verbose_name="Estado")),
                ("started_at", models.DateTimeField(verbose_name="Empezada")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="Terminada")),
                ("size_bytes", models.BigIntegerField(default=0, verbose_name="Tamaño comprimido")),
                ("uncompressed_bytes", models.BigIntegerField(default=0, verbose_name="Tamaño sin comprimir")),
                ("sha256", models.CharField(blank=True, default="", max_length=64, verbose_name="SHA-256")),
                ("row_counts", models.JSONField(blank=True, default=dict, verbose_name="Filas de control")),
                ("error", models.TextField(blank=True, default="", verbose_name="Error")),
                ("downloaded_at", models.DateTimeField(blank=True, null=True, verbose_name="Bajada a OneDrive")),
                ("host", models.CharField(blank=True, default="", max_length=255, verbose_name="Equipo")),
                ("local_path", models.TextField(blank=True, default="", verbose_name="Ruta en OneDrive")),
                ("removed_from_bucket_at", models.DateTimeField(blank=True, null=True, verbose_name="Quitada del cubo")),
                ("removed_from_local_at", models.DateTimeField(blank=True, null=True, verbose_name="Quitada de OneDrive")),
            ],
            options={
                "verbose_name": "Copia de seguridad de la base de datos",
                "verbose_name_plural": "Copias de seguridad de la base de datos",
                "ordering": ["-started_at"],
            },
        ),
    ]
