# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0010_base_insurerbase_refactor.py
# Manual migration — FK and index already dropped manually in MySQL.
# Uses SeparateDatabaseAndState to skip the AlterUniqueTogether at DB level
# since the unique_together constraint no longer exists in the database.
# Migracion manual — FK e indice ya eliminados manualmente en MySQL.
# Usa SeparateDatabaseAndState para saltar AlterUniqueTogether a nivel BD
# ya que el unique_together ya no existe en la base de datos.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0009_budget_base_fk"),
        ("ivr_config", "0030_company_labor_calendar_company_operation_bases"),
    ]

    operations = [

        # Step 1 — Tell Django the old unique_together is gone (already removed from DB).
        # Paso 1 — Informar a Django que el unique_together anterior ya no existe en BD.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterUniqueTogether(
                    name="base",
                    unique_together=set(),
                ),
            ],
        ),

        # Step 2 — Remove insurer ForeignKey from Base (already removed from DB).
        # Paso 2 — Eliminar FK insurer de Base (ya eliminada de BD manualmente).
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(
                    model_name="base",
                    name="insurer",
                ),
            ],
        ),

        # Step 3 — Add company ForeignKey to Base (nullable for existing rows).
        # Paso 3 — Añadir FK company a Base (nullable para filas existentes).
        migrations.AddField(
            model_name="base",
            name="company",
            field=models.ForeignKey(
                blank=True,
                help_text="Empresa a la que pertenece esta base.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bases",
                to="ivr_config.company",
                verbose_name="Empresa",
            ),
        ),

        # Step 4 — Set the new unique_together (company, name).
        # Paso 4 — Establecer el nuevo unique_together (company, name).
        migrations.AlterUniqueTogether(
            name="base",
            unique_together={("company", "name")},
        ),

        # Step 5 — Update Meta options on Base.
        # Paso 5 — Actualizar opciones Meta de Base.
        migrations.AlterModelOptions(
            name="base",
            options={
                "ordering": ["company__name", "name"],
                "verbose_name": "Base",
                "verbose_name_plural": "Bases",
            },
        ),

        # Step 6 — Update is_active help_text on Base.
        # Paso 6 — Actualizar help_text de is_active en Base.
        migrations.AlterField(
            model_name="base",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Indica si esta base esta disponible globalmente. "
                    "Cuando es False, no puede usarse en ningun presupuesto "
                    "independientemente de su configuracion por aseguradora."
                ),
                verbose_name="Activa globalmente",
            ),
        ),

        # Step 7 — Create InsurerBase model.
        # Paso 7 — Crear modelo InsurerBase.
        migrations.CreateModel(
            name="InsurerBase",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Indica si esta base esta activa para esta aseguradora. "
                            "Una base puede estar activa para una aseguradora e inactiva "
                            "para otra. El flag global Base.is_active tiene precedencia: "
                            "si es False, la base no aparece en el wizard aunque este "
                            "flag sea True."
                        ),
                        verbose_name="Activa para esta aseguradora",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Fecha de creacion",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Fecha de modificacion",
                    ),
                ),
                (
                    "base",
                    models.ForeignKey(
                        help_text="Base fisica asignada a esta aseguradora.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurer_bases",
                        to="budgets.base",
                        verbose_name="Base",
                    ),
                ),
                (
                    "insurer",
                    models.ForeignKey(
                        help_text="Aseguradora a la que se asigna esta base.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurer_bases",
                        to="budgets.insurer",
                        verbose_name="Aseguradora",
                    ),
                ),
            ],
            options={
                "verbose_name": "Base de aseguradora",
                "verbose_name_plural": "Bases de aseguradora",
                "ordering": ["insurer__name", "base__name"],
                "unique_together": {("insurer", "base")},
            },
        ),
    ]
