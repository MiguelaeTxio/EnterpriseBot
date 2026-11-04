# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0196_personidentity_nickname_s144.py
# H24 (S144): mote del trabajador (se rellena desde el Excel de
# trabajadores con un Comando S; entra en la búsqueda).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0195_localdownloadjob_previous_folder_s144"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="nickname",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="Mote"),
        ),
    ]
