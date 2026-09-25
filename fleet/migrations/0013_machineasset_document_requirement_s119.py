# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0013_machineasset_document_requirement_s119.py
"""
H30 (S119). Añade MachineAsset.document_requirement -- FK opcional a
document_explorer.MachineDocumentRequirement (misma mecánica que
PersonIdentity.job_position, document_explorer 0100/S109). Ver
docstring completo en fleet/models.py.

Sin ninguna excepción por máquina ni por documento: para exigirle otro
conjunto de tipos a una máquina, se reasigna a otro requisito, nunca
una excepción dentro del mismo (Miguel Ángel, S119, aclarando el
diseño: "no es la máquina [...] cambia de requisito de documentación a
un requisito de documentación diferente").

Campo nullable, sin valor que rellenar en las filas existentes --
ninguna máquina queda con requisito asignado hasta que Miguel Ángel lo
haga desde el panel.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0012_fix_default_machine_photo_s118"),
        ("document_explorer", "0145_machine_document_requirement_s119"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineasset",
            name="document_requirement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="machines",
                to="document_explorer.machinedocumentrequirement",
                verbose_name="Requisito de documentación",
            ),
        ),
    ]
