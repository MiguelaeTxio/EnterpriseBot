# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0015_clock_settings_s141.py
# H24 (S141): ajustes de fichaje desde el panel -- permiso general de
# recordatorios (empresa), secciones que fichan con la plataforma y, por
# trabajador, si ficha y si recibe recordatorios.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0192_recheck_id_photos_s136"),
        ("hr_calendar", "0014_clockcorrection_s141"),
        ("ivr_config", "0050_role_crane_operator_s137"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClockSettings",
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
                    "reminders_enabled",
                    models.BooleanField(
                        default=False,
                        verbose_name="Enviar recordatorios de fichaje",
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
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clock_settings",
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
                "verbose_name": "Ajustes de fichaje",
                "verbose_name_plural": "Ajustes de fichaje",
            },
        ),
        migrations.CreateModel(
            name="SectionClockSetting",
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
                    "clocks",
                    models.BooleanField(
                        default=True,
                        verbose_name="Ficha con la plataforma",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Último cambio",
                    ),
                ),
                (
                    "section",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clock_setting",
                        to="ivr_config.section",
                        verbose_name="Sección",
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
                "verbose_name": "Fichaje de una sección",
                "verbose_name_plural": "Fichaje de las secciones",
            },
        ),
        migrations.CreateModel(
            name="WorkerClockSetting",
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
                    "clocks",
                    models.BooleanField(
                        default=True, verbose_name="Obligado a fichar",
                    ),
                ),
                (
                    "reminders",
                    models.BooleanField(
                        default=False, verbose_name="Recibe recordatorios",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Último cambio",
                    ),
                ),
                (
                    "person",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clock_setting",
                        to="document_explorer.personidentity",
                        verbose_name="Trabajador",
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
                "verbose_name": "Fichaje de un trabajador",
                "verbose_name_plural": "Fichaje de los trabajadores",
            },
        ),
    ]
