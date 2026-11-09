# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0212_personidentity_notes_s148.py
# S148: `PersonIdentity.notes`, observaciones libres de la persona
# (Miguel Ángel: "parecido a los antiguos campos Memo"). Texto vacío por
# defecto en las filas que ya hay.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0211_localdownloadjob_machine_s148"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="notes",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Avisos y notas libres sobre la persona.",
                verbose_name="Observaciones",
            ),
        ),
    ]
