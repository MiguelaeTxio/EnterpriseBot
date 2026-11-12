# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0215_personidentity_document_requirements_s153.py
# S153: varios requisitos de documentación por persona. El FK
# `PersonIdentity.job_position` (uno solo) pasa a la relación
# `PersonIdentity.document_requirements` (varios); cada persona conserva
# el requisito que tenía.

from django.db import migrations, models


def copy_requirements(apps, schema_editor):
    """
    Copy each person's single requirement into the new relation.
    ---
    Copia el requisito de cada persona a la relación nueva.
    """
    person_model = apps.get_model("document_explorer", "PersonIdentity")
    through = person_model.document_requirements.through
    through.objects.bulk_create([
        through(personidentity_id=pk, jobposition_id=requirement_id)
        for pk, requirement_id in person_model.objects.filter(
            job_position__isnull=False,
        ).values_list("pk", "job_position_id")
    ])


def restore_requirement(apps, schema_editor):
    """
    Back to one requirement per person (the lowest pk).
    ---
    Vuelta a un requisito por persona (el de pk más bajo).
    """
    person_model = apps.get_model("document_explorer", "PersonIdentity")
    through = person_model.document_requirements.through
    first = {}
    for person_id, requirement_id in through.objects.order_by(
        "jobposition_id",
    ).values_list("personidentity_id", "jobposition_id"):
        first.setdefault(person_id, requirement_id)
    for person_id, requirement_id in first.items():
        person_model.objects.filter(pk=person_id).update(
            job_position_id=requirement_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "document_explorer",
            "0214_documenttypecatalog_requirement_category_s153",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="personidentity",
            name="job_position",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="+",
                to="document_explorer.jobposition",
                verbose_name="Requisitos de documentación",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="document_requirements",
            field=models.ManyToManyField(
                blank=True,
                related_name="people",
                to="document_explorer.jobposition",
                verbose_name="Requisitos de documentación",
            ),
        ),
        migrations.RunPython(copy_requirements, restore_requirement),
        migrations.RemoveField(
            model_name="personidentity",
            name="job_position",
        ),
    ]
