# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0041_albaranes_varios_s149.py
# H24 (S149, sesión invasora): carga de albaranes de varios trabajadores
# desde la lista de fichajes. La carga puede ir sin trabajador; cada
# albarán lleva el suyo (los ya cargados, el de su carga).

import django.db.models.deletion
from django.db import migrations, models


def sheet_person_from_batch(apps, schema_editor):
    AlbaranSheet = apps.get_model("hr_calendar", "AlbaranSheet")
    for sheet in AlbaranSheet.objects.filter(person__isnull=True).select_related("batch"):
        if sheet.batch.person_id:
            AlbaranSheet.objects.filter(pk=sheet.pk).update(person_id=sheet.batch.person_id)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0219_seed_albaran_trabajo_s153"),
        ("hr_calendar", "0040_albaransheet_full_data_s153"),
    ]

    operations = [
        migrations.AlterField(
            model_name="albaranbatch",
            name="person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="albaran_batches",
                to="document_explorer.personidentity",
                verbose_name="Trabajador",
            ),
        ),
        migrations.AddField(
            model_name="albaranbatch",
            name="candidate_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Carga de varios: los trabajadores marcados en la lista (vacío: todos los que fichan por tipos).",
                verbose_name="Entre quiénes repartir",
            ),
        ),
        migrations.AddField(
            model_name="albaransheet",
            name="person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="albaran_sheets",
                to="document_explorer.personidentity",
                verbose_name="Trabajador",
            ),
        ),
        migrations.AlterField(
            model_name="albaransheet",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Por leer"),
                    ("READ", "Leído"),
                    ("UNREADABLE", "Ilegible"),
                    ("ERROR", "Error"),
                    ("NO_PERSON", "Sin trabajador"),
                ],
                default="PENDING",
                max_length=12,
                verbose_name="Estado",
            ),
        ),
        migrations.RunPython(sheet_person_from_batch, migrations.RunPython.noop),
    ]
