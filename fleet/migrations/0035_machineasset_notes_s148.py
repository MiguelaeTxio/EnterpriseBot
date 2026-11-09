# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0035_machineasset_notes_s148.py
"""
S148. `MachineAsset.notes`: observaciones libres del centro de gasto
(Miguel Ángel: "parecido a los antiguos campos Memo"). Texto vacío por
defecto en las filas que ya hay.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0034_machinegrouptemplate_s148"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineasset",
            name="notes",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Avisos y notas libres sobre el centro de gasto.",
                verbose_name="Observaciones",
            ),
        ),
    ]
