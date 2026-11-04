# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0195_localdownloadjob_previous_folder_s144.py
# H24 (S144): carpeta anterior de la persona en las descargas a local
# (baja, reactivación, cambio de empresa: el agente la vacía y la borra).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0194_localdownloadjob_s144"),
    ]

    operations = [
        migrations.AddField(
            model_name="localdownloadjob",
            name="previous_folder",
            field=models.TextField(blank=True, default="", help_text="Carpeta virtual de la persona antes de moverla; el agente la vacía y la borra en local.", verbose_name="Carpeta anterior"),
        ),
    ]
