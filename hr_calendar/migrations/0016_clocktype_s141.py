# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0016_clocktype_s141.py
# H24 (S141): tipos de fichaje (como Sesame), cambio de tipo con la
# jornada abierta, secciones que fichan por tipos y los cinco tipos de
# partida de cada empresa.

import django.db.models.deletion
from django.db import migrations, models

KIND_CHOICES = [
    ("IN", "Entrada"),
    ("OUT", "Salida"),
    ("CHG", "Cambio de tipo"),
]

# (nombre, icono, cuenta como jornada, por defecto)
INITIAL_TYPES = [
    ("Fichaje normal", "bi-box-arrow-in-right", True, True),
    ("Desplazamiento", "bi-truck", False, False),
    ("Presencia", "bi-people", False, False),
    ("Trabajo efectivo", "bi-star", True, False),
    ("Varios", "bi-arrow-bar-right", True, False),
]


def seed_types(apps, schema_editor):
    """
    The five initial clock types of every company.
    ---
    Los cinco tipos de fichaje de partida de cada empresa.
    """
    company_model = apps.get_model("ivr_config", "Company")
    clock_type_model = apps.get_model("hr_calendar", "ClockType")
    for company in company_model.objects.all():
        for order, (name, icon, counts, default) in enumerate(
                INITIAL_TYPES, start=1):
            clock_type_model.objects.get_or_create(
                company=company, name=name,
                defaults={
                    "icon": icon, "counts_as_work": counts,
                    "is_default": default, "order": order,
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0015_clock_settings_s141"),
        ("ivr_config", "0051_role_admin_supervisor_s141"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClockType",
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
                    "name",
                    models.CharField(max_length=60, verbose_name="Nombre"),
                ),
                (
                    "icon",
                    models.CharField(
                        default="bi-box-arrow-in-right",
                        help_text="Nombre de un icono de Bootstrap Icons "
                                  "(bi-...).",
                        max_length=40,
                        verbose_name="Icono",
                    ),
                ),
                (
                    "counts_as_work",
                    models.BooleanField(
                        default=True, verbose_name="Cuenta como jornada",
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        default=False, verbose_name="Tipo por defecto",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Activo"),
                ),
                (
                    "order",
                    models.PositiveSmallIntegerField(
                        default=0, verbose_name="Orden",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Último cambio",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clock_types",
                        to="ivr_config.company",
                        verbose_name="Empresa",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="ivr_config.companyuser",
                        verbose_name="Cambiado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tipo de fichaje",
                "verbose_name_plural": "Tipos de fichaje",
                "ordering": ["order", "name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("company", "name"),
                        name="clocktype_unique_company_name",
                    ),
                ],
            },
        ),
        migrations.AlterField(
            model_name="clockevent",
            name="kind",
            field=models.CharField(
                choices=KIND_CHOICES, max_length=3, verbose_name="Tipo",
            ),
        ),
        migrations.AddField(
            model_name="clockevent",
            name="clock_type",
            field=models.ForeignKey(
                blank=True,
                help_text="S141: tipo del tramo que abre una entrada o un "
                          "cambio de tipo (secciones que fichan por "
                          "tipos). Vacío en las salidas y en quien ficha "
                          "con el botón único.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="clock_events",
                to="hr_calendar.clocktype",
                verbose_name="Tipo de fichaje",
            ),
        ),
        migrations.AlterField(
            model_name="clockcorrection",
            name="old_kind",
            field=models.CharField(
                choices=KIND_CHOICES, max_length=3,
                verbose_name="Tipo anterior",
            ),
        ),
        migrations.AlterField(
            model_name="clockcorrection",
            name="new_kind",
            field=models.CharField(
                blank=True, choices=KIND_CHOICES, max_length=3,
                verbose_name="Tipo nuevo",
            ),
        ),
        migrations.AddField(
            model_name="clockcorrection",
            name="old_clock_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="hr_calendar.clocktype",
                verbose_name="Tipo de fichaje anterior",
            ),
        ),
        migrations.AddField(
            model_name="clockcorrection",
            name="new_clock_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="hr_calendar.clocktype",
                verbose_name="Tipo de fichaje nuevo",
            ),
        ),
        migrations.AddField(
            model_name="sectionclocksetting",
            name="uses_types",
            field=models.BooleanField(
                default=False, verbose_name="Ficha por tipos",
            ),
        ),
        migrations.RunPython(seed_types, migrations.RunPython.noop),
    ]
