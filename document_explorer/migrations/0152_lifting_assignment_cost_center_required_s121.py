# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0152_lifting_assignment_cost_center_required_s121.py
"""
H30 (S121). La entrega de un accesorio de elevación anota siempre a qué
centro de gasto y a quién se entrega (Miguel Ángel, S121): el centro de
gasto pasa a ser obligatorio (PROTECT: un CdG con entregas no se borra).

Sin filas afectadas: 0 entregas en producción (consulta real S121,
previa a esta migración).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "document_explorer",
            "0151_lifting_accessory_certificates_as_domain_links_s121",
        ),
        ("fleet", "0016_sync_state_s120"),
    ]

    operations = [
        migrations.AlterField(
            model_name="liftingaccessoryassignment",
            name="machine",
            field=models.ForeignKey(
                help_text=(
                    "Centro de gasto al que se entrega (máquina, EMPRESA_* "
                    "o PERSONAL). Obligatorio (S121)."
                ),
                on_delete=django.db.models.deletion.PROTECT,
                related_name="lifting_accessory_assignments",
                to="fleet.machineasset",
                verbose_name="Centro de gasto",
            ),
        ),
    ]
