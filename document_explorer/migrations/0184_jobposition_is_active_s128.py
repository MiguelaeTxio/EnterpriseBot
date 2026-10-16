# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0184_jobposition_is_active_s128.py
"""
H30 (S128), hoja de ruta punto 1. Activar/desactivar requisitos de
documentación: un requisito desactivado no genera avisos. Todos los
existentes quedan activos (default=True), como hasta ahora.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0183_merge_subrogation_s127"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobposition",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "H30 (S128). Un requisito desactivado no genera "
                    "avisos (ni de falta ni de caducidad, ni en el panel "
                    "ni por WhatsApp), pero sigue asignado a quien lo "
                    "tenga. Se activa y desactiva desde el gestor de "
                    "Requisitos."
                ),
                verbose_name="Activo",
            ),
        ),
    ]
