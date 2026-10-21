# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0036_assistancecrew_driverposition_s133.py
"""
H37 (S133). Assistance crews (driver + machine) and driver positions.

---

H37 (S133). Equipos de asistencia (conductor + máquina) y posiciones
de los conductores. Los albaranes ya asignados con conductor y máquina
de la flota forman su equipo, para que el panel no los deje sueltos.
"""
import django.db.models.deletion
from django.db import migrations, models

# Albaranes whose driver and machine are together right now.
# Albaranes cuyo conductor y máquina van juntos ahora mismo.
ACTIVE_STATUSES = (
    "PENDING",
    "NOTIFY_SENDING",
    "NOTIFY_FAILED",
    "NOTIFIED",
    "DOWNLOADED",
    "IN_PROGRESS",
    "COMPLETED",
    "CLOSED_UNSIGNED",
    "SIGNED_RECEIVED",
)


def crews_from_units(apps, schema_editor):
    """
    One crew per driver and machine of the albaranes in progress.

    ---

    Un equipo por cada conductor y máquina de los albaranes en curso,
    del más reciente al más antiguo; si el conductor o la máquina ya
    tienen equipo, el albarán más antiguo no forma otro.
    """
    unit_model = apps.get_model("budgets", "WorkOrderAssistanceUnit")
    crew_model = apps.get_model("budgets", "AssistanceCrew")
    units = unit_model.objects.filter(
        status__in=ACTIVE_STATUSES,
        operator__isnull=False,
        machine_asset__isnull=False,
        work_order__status__in=("PENDING", "IN_PROGRESS"),
    ).select_related("work_order").order_by("-updated_at")
    drivers = set()
    machines = set()
    for unit in units:
        if unit.operator_id in drivers or unit.machine_asset_id in machines:
            continue
        crew_model.objects.create(
            company_id=unit.work_order.company_id,
            driver_id=unit.operator_id,
            machine_id=unit.machine_asset_id,
        )
        drivers.add(unit.operator_id)
        machines.add(unit.machine_asset_id)


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0035_unit_closed_base_s133"),
        ("fleet", "0019_service_crane_hours_s131"),
        ("ivr_config", "0049_companyuser_role_assist_supervisor_s132"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistanceCrew",
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
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Formado",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistance_crews",
                        to="ivr_config.company",
                        verbose_name="Empresa",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="ivr_config.companyuser",
                        verbose_name="Formado por",
                    ),
                ),
                (
                    "driver",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistance_crew",
                        to="ivr_config.companyuser",
                        verbose_name="Conductor",
                    ),
                ),
                (
                    "machine",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistance_crew",
                        to="fleet.machineasset",
                        verbose_name="Máquina",
                    ),
                ),
            ],
            options={
                "verbose_name": "Equipo de asistencia",
                "verbose_name_plural": "Equipos de asistencia",
                "ordering": ["machine__code"],
            },
        ),
        migrations.CreateModel(
            name="DriverPosition",
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
                    "latitude",
                    models.DecimalField(
                        decimal_places=6, max_digits=9,
                        verbose_name="Latitud",
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        decimal_places=6, max_digits=9,
                        verbose_name="Longitud",
                    ),
                ),
                (
                    "accuracy_m",
                    models.PositiveIntegerField(
                        blank=True, null=True,
                        verbose_name="Precisión (m)",
                    ),
                ),
                (
                    "recorded_at",
                    models.DateTimeField(
                        help_text="Hora del móvil al tomar la posición.",
                        verbose_name="Tomada",
                    ),
                ),
                (
                    "received_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Recibida",
                    ),
                ),
                (
                    "company_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="driver_positions",
                        to="ivr_config.companyuser",
                        verbose_name="Conductor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Posición del conductor",
                "verbose_name_plural": "Posiciones de los conductores",
                "ordering": ["-recorded_at"],
                "indexes": [
                    models.Index(
                        fields=["company_user", "-recorded_at"],
                        name="drvpos_user_recorded_idx",
                    ),
                ],
            },
        ),
        migrations.RunPython(crews_from_units, migrations.RunPython.noop),
    ]
