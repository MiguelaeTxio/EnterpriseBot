# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0044_machine_qr_sheet_s154.py
"""
H23 (S154, invasora) -- ficha QR de cada centro de gasto: observaciones
y fotos y vídeos que ve el trabajador al leer su código QR.

Nota de despliegue: la primera vez no se aplicó (el panel no arrancaba
por una importación que faltaba en panel/urls.py y el despliegue solo
lanza migrate cuando el push trae una migración); este comentario la
vuelve a traer para que deploy.yml ejecute migrate.
"""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0043_machineasset_capacity_tm_s154"),
        ("ivr_config", "0056_workdayscheduleday_holiday_s144"),
    ]

    operations = [
        migrations.CreateModel(
            name="MachineQrSheet",
            fields=[
                ("id", models.BigAutoField(auto_created=True,
                                           primary_key=True,
                                           serialize=False,
                                           verbose_name="ID")),
                ("token", models.UUIDField(
                    default=uuid.uuid4, editable=False, unique=True,
                    verbose_name="Identificador del QR")),
                ("observations", models.TextField(
                    blank=True, default="", verbose_name="Observaciones")),
                ("updated_at", models.DateTimeField(
                    auto_now=True, verbose_name="Modificada el")),
                ("machine", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="qr_sheet", to="fleet.machineasset",
                    verbose_name="Centro de gasto")),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ivr_config.companyuser",
                    verbose_name="Modificada por")),
            ],
            options={
                "verbose_name": "Ficha QR",
                "verbose_name_plural": "Fichas QR",
            },
        ),
        migrations.CreateModel(
            name="MachineQrMedia",
            fields=[
                ("id", models.BigAutoField(auto_created=True,
                                           primary_key=True,
                                           serialize=False,
                                           verbose_name="ID")),
                ("kind", models.CharField(
                    choices=[("PHOTO", "Foto"), ("VIDEO", "Vídeo")],
                    max_length=10, verbose_name="Tipo")),
                ("caption", models.CharField(
                    blank=True, default="", max_length=300,
                    verbose_name="Descripción")),
                ("bucket", models.CharField(max_length=100,
                                            verbose_name="Cubo")),
                ("blob_name", models.CharField(max_length=500,
                                               verbose_name="Objeto")),
                ("content_type", models.CharField(
                    max_length=100, verbose_name="Tipo de contenido")),
                ("size", models.PositiveBigIntegerField(
                    default=0, verbose_name="Tamaño (bytes)")),
                ("position", models.PositiveIntegerField(
                    default=0, verbose_name="Orden")),
                ("created_at", models.DateTimeField(
                    auto_now_add=True, verbose_name="Subida el")),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ivr_config.companyuser",
                    verbose_name="Subida por")),
                ("sheet", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="media", to="fleet.machineqrsheet",
                    verbose_name="Ficha QR")),
            ],
            options={
                "verbose_name": "Foto o vídeo de ficha QR",
                "verbose_name_plural": "Fotos y vídeos de fichas QR",
                "ordering": ["position", "id"],
            },
        ),
    ]
