# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0049_model_single_manual_discarded_s154.py
"""
S154 (invasora, 28/11) -- un manual por modelo (FK en vez de M2M) y las
copias descartadas, marcadas en la BD sin borrar nada del cubo ni de
Microsoft 365. La M2M solo tenía la prueba de la A29.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0048_machine_model_manual_counters_s154"),
        ("ivr_config", "0065_transfer_announced_by_system_s155"),
        ("document_explorer", "0235_caedocumentreading_s156"),
    ]

    operations = [
        migrations.RemoveField(model_name="machinemodel", name="manuals"),
        migrations.AddField(
            model_name="machinemodel",
            name="manual",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="document_explorer.documentindexentry", verbose_name="Manual"),
        ),
        migrations.CreateModel(
            name="DiscardedManual",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("discarded_at", models.DateTimeField(auto_now_add=True, verbose_name="Descartado el")),
                ("entry", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="manual_discard", to="document_explorer.documentindexentry", verbose_name="Manual descartado")),
                ("machine_model", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="discarded_manuals", to="fleet.machinemodel", verbose_name="Modelo")),
                ("kept_manual", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="document_explorer.documentindexentry", verbose_name="Manual que se queda")),
                ("discarded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="ivr_config.companyuser", verbose_name="Descartado por")),
            ],
            options={
                "verbose_name": "Manual descartado",
                "verbose_name_plural": "Manuales descartados",
            },
        ),
    ]
