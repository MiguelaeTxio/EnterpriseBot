# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0210_localdownloadjob_machine_s148.py
# H31 (S148): las descargas a la carpeta local de OneDrive también son
# de máquinas (DOC. MAQUINAS): `machine` nuevo y `person` opcional. Los
# trabajos que ya hay son todos de personas y no cambian. Además,
# `obsolete_files`: lo sustituido pasa a OBSOLETOS dentro de la carpeta.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0209_grupos_sin_repetidos_s147"),
        ("fleet", "0034_machinegrouptemplate_s148"),
    ]

    operations = [
        migrations.AddField(
            model_name="localdownloadjob",
            name="obsolete_files",
            field=models.JSONField(
                blank=True, default=list, verbose_name="Pasan a obsoletos",
            ),
        ),
        migrations.AlterField(
            model_name="localdownloadjob",
            name="person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="local_download_jobs",
                to="document_explorer.personidentity",
                verbose_name="Trabajador",
            ),
        ),
        migrations.AddField(
            model_name="localdownloadjob",
            name="machine",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="local_download_jobs",
                to="fleet.machineasset",
                verbose_name="Máquina",
            ),
        ),
    ]
