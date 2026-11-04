# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0197_localdownloadjob_folder_s144.py
# H24 (S144): carpeta local de la persona en la descarga (la
# organización del OneDrive: OPERARIOS, TALLER... no la del cubo).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0196_personidentity_nickname_s144"),
    ]

    operations = [
        migrations.AddField(
            model_name="localdownloadjob",
            name="folder",
            field=models.TextField(blank=True, default="", help_text="Carpeta de la persona en el árbol local (OneDrive), con vuestra organización: OPERARIOS, TALLER...", verbose_name="Carpeta en local"),
        ),
    ]
