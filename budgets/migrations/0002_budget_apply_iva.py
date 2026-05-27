# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0002_budget_apply_iva.py
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Adds apply_iva boolean field to Budget model.
    Defaults to False — existing budgets are not affected.
    ---
    Añade el campo booleano apply_iva al modelo Budget.
    Por defecto False — los presupuestos existentes no se ven afectados.
    """

    dependencies = [
        ("budgets", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="budget",
            name="apply_iva",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Indica si se debe aplicar el IVA vigente sobre el importe base "
                    "del presupuesto. El porcentaje de IVA se define como constante "
                    "IVA_PERCENT en budgets/services.py."
                ),
                verbose_name="Aplicar IVA",
            ),
        ),
    ]
