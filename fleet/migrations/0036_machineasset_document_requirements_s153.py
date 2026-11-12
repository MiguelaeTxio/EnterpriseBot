# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0036_machineasset_document_requirements_s153.py
# S153: varios requisitos de documentación por centro de gasto. El FK
# `MachineAsset.document_requirement` (uno solo) pasa a la relación
# `MachineAsset.document_requirements` (varios); cada máquina conserva
# el requisito que tenía.

from django.db import migrations, models


def copy_requirements(apps, schema_editor):
    """
    Copy each machine's single requirement into the new relation.
    ---
    Copia el requisito de cada máquina a la relación nueva.
    """
    machine_model = apps.get_model("fleet", "MachineAsset")
    through = machine_model.document_requirements.through
    through.objects.bulk_create([
        through(machineasset_id=pk, jobposition_id=requirement_id)
        for pk, requirement_id in machine_model.objects.filter(
            document_requirement__isnull=False,
        ).values_list("pk", "document_requirement_id")
    ])


def restore_requirement(apps, schema_editor):
    """
    Back to one requirement per machine (the lowest pk).
    ---
    Vuelta a un requisito por máquina (el de pk más bajo).
    """
    machine_model = apps.get_model("fleet", "MachineAsset")
    through = machine_model.document_requirements.through
    first = {}
    for machine_id, requirement_id in through.objects.order_by(
        "jobposition_id",
    ).values_list("machineasset_id", "jobposition_id"):
        first.setdefault(machine_id, requirement_id)
    for machine_id, requirement_id in first.items():
        machine_model.objects.filter(pk=machine_id).update(
            document_requirement_id=requirement_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0035_machineasset_notes_s148"),
        (
            "document_explorer",
            "0215_personidentity_document_requirements_s153",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="machineasset",
            name="document_requirement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="+",
                to="document_explorer.jobposition",
                verbose_name="Requisito de documentación",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="document_requirements",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "S119 -- mismo catálogo único que el de una persona "
                    "(Requisitos de documentación): sin requisito "
                    "asignado, esta máquina no avisa de ningún documento "
                    "faltante ni caducado. S153: varios por máquina "
                    "(antes uno solo); lo obligatorio es la unión de los "
                    "requisitos activos."
                ),
                related_name="machines",
                to="document_explorer.jobposition",
                verbose_name="Requisitos de documentación",
            ),
        ),
        migrations.RunPython(copy_requirements, restore_requirement),
        migrations.RemoveField(
            model_name="machineasset",
            name="document_requirement",
        ),
    ]
