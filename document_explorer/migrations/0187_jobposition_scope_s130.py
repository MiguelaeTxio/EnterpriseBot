# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0187_jobposition_scope_s130.py
# S130: ámbito Personal/Maquinaria de los requisitos de documentación.
# Los existentes quedan como Personal (en producción solo hay "dni",
# asignado a nadie y con tipos de dominio PERSONAL).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0186_personalexporttemplate_s129"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobposition",
            name="scope",
            field=models.CharField(
                choices=[("PERSONAL", "Personal"), ("MACHINE", "Maquinaria")],
                default="PERSONAL",
                help_text=(
                    "S130. Personal o Maquinaria: en qué listados y fichas "
                    "se ofrece para asignar."
                ),
                max_length=10,
                verbose_name="Ámbito",
            ),
        ),
    ]
