# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0015_machineasset_document_requirement_jobposition_s119.py
"""
H30 (S119). Vuelve a añadir MachineAsset.document_requirement -- esta
vez apuntando a document_explorer.JobPosition (el catálogo ÚNICO de
"Requisitos de documentación" que ya usa Personal, creado en
document_explorer 0100/S109), no al modelo separado
MachineDocumentRequirement recién revertido (0014/0146).

Miguel Ángel, verbatim: "los requisitos documentales no son ni para
personas ni para máquinas [...] la gestión de requisitos documentales
es global [...] cogemos de todos los documentos, cogemos los que
queremos y fabricamos un requisito documental [...] ese requisito se
asigna a una máquina, a una dependencia o a una persona." Sin ninguna
restricción de dominio en el propio requisito -- si alguien asigna por
error un requisito pensado para personas a una máquina, el aviso de
documento faltante lo delata solo, y se corrige reasignando desde la
ficha, nunca con una validación que lo impida.

Campo nullable, sin valor que rellenar en las filas existentes.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0014_undo_machine_document_requirement_s119"),
        ("document_explorer", "0146_undo_machine_document_requirement_s119"),
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
                to="document_explorer.jobposition",
                verbose_name="Requisito de documentación",
            ),
        ),
    ]
