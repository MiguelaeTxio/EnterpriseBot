# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0048_machine_model_manual_counters_s154.py
"""
S154 (invasora, 28/11) -- modelos de máquina con sus manuales, y las
páginas de los manuales que enseñan dónde están los contadores (para la
ficha QR, revisadas antes de publicarse).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0047_meterreading_source_real_s154"),
        ("ivr_config", "0065_transfer_announced_by_system_s155"),
        ("document_explorer", "0235_caedocumentreading_s156"),
    ]

    operations = [
        migrations.CreateModel(
            name="MachineModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Marca y modelo")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creado el")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="machine_models", to="ivr_config.company", verbose_name="Empresa")),
                ("machines", models.ManyToManyField(blank=True, related_name="machine_models", to="fleet.machineasset", verbose_name="Centros de gasto")),
                ("manuals", models.ManyToManyField(blank=True, related_name="machine_models", to="document_explorer.documentindexentry", verbose_name="Manuales")),
            ],
            options={
                "verbose_name": "Modelo de máquina",
                "verbose_name_plural": "Modelos de máquina",
                "ordering": ["name"],
                "unique_together": {("company", "name")},
            },
        ),
        migrations.CreateModel(
            name="ManualCounterImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("KM", "Cuentakilómetros"), ("MOTOR", "Horas de motor"), ("GRUA", "Horas de grúa"), ("DISPLAY", "Botones del display")], max_length=10, verbose_name="Qué enseña")),
                ("caption", models.CharField(blank=True, default="", max_length=300, verbose_name="Explicación")),
                ("page", models.PositiveIntegerField(default=0, verbose_name="Página")),
                ("is_photo", models.BooleanField(default=False, verbose_name="Es una foto")),
                ("bucket", models.CharField(max_length=100, verbose_name="Cubo")),
                ("blob_name", models.CharField(max_length=500, verbose_name="Objeto")),
                ("status", models.CharField(choices=[("PENDIENTE", "Pendiente de revisar"), ("PUBLICADA", "Publicada en el QR"), ("QUITADA", "Quitada")], default="PENDIENTE", max_length=10, verbose_name="Estado")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, verbose_name="Revisada el")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creada el")),
                ("machine_model", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="counter_images", to="fleet.machinemodel", verbose_name="Modelo")),
                ("manual", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="document_explorer.documentindexentry", verbose_name="Manual")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="ivr_config.companyuser", verbose_name="Revisada por")),
            ],
            options={
                "verbose_name": "Contador en el manual",
                "verbose_name_plural": "Contadores en los manuales",
                "ordering": ["kind", "-is_photo", "id"],
            },
        ),
    ]
