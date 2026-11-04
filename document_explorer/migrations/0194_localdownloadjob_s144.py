# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0194_localdownloadjob_s144.py
# H24 (S144): descarga a la carpeta local de OneDrive de los documentos
# de un trabajador recién dado de alta (la hace el agente H28).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0193_circular_alta_fichaje_s141"),
        ("ivr_config", "0047_trusteddevice_s129"),
    ]

    operations = [
        migrations.CreateModel(
            name="LocalDownloadJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creada")),
                ("files", models.JSONField(default=list, verbose_name="Archivos")),
                ("status", models.CharField(choices=[("pending", "Pendiente"), ("in_progress", "Descargando"), ("done", "Terminada")], default="pending", max_length=20, verbose_name="Estado")),
                ("downloaded_count", models.PositiveIntegerField(default=0, verbose_name="Descargados")),
                ("last_error", models.TextField(blank=True, default="", verbose_name="Último error")),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True, verbose_name="Último intento")),
                ("host", models.CharField(blank=True, default="", max_length=255, verbose_name="Equipo")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="Terminada")),
                ("person", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="local_download_jobs", to="document_explorer.personidentity", verbose_name="Trabajador")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="local_download_jobs", to="ivr_config.companyuser", verbose_name="Pedida por")),
            ],
            options={
                "verbose_name": "Descarga a la carpeta local",
                "verbose_name_plural": "Descargas a la carpeta local",
                "ordering": ["created_at"],
            },
        ),
    ]
