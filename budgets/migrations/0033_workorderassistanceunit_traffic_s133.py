# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0033_workorderassistanceunit_traffic_s133.py
"""
H37 (S133). Traffic panel: unassigned albaranes, fleet machine and
audit trail.

---

H37 (S133). Panel de tráfico: el chófer de la unidad pasa a poder
estar vacío (albarán creado sin asignar), máquina de la flota
asignada (`machine_asset`) y registro de auditoría de cada cambio de
estado y asignación (`WorkOrderAssistanceUnitEvent`).
"""
import django.db.models.deletion
from django.db import migrations, models


def link_machine_assets(apps, schema_editor):
    """
    Link the units created before S133 to their fleet machine.

    ---

    Enlaza las unidades creadas antes de S133 con su máquina de la
    flota cuando el texto de `machine` es su etiqueta ("X11 9237LGN")
    o su código, para que el panel de tráfico las vea ocupadas.
    """
    unit_model = apps.get_model("budgets", "WorkOrderAssistanceUnit")
    machine_model = apps.get_model("fleet", "MachineAsset")
    units = unit_model.objects.filter(
        machine_asset__isnull=True,
    ).exclude(machine="").select_related("work_order")
    for unit in units:
        text = unit.machine.strip().lower()
        for machine in machine_model.objects.filter(
            company_id=unit.work_order.company_id,
            family__iexact="ASISTENCIA",
        ):
            label = " ".join(
                part for part in (machine.code, machine.plate) if part
            ).lower()
            if text in (label, (machine.code or "").lower()):
                unit.machine_asset_id = machine.pk
                unit.save(update_fields=["machine_asset"])
                break


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0032_workorderassistanceunit_notify_sending_s132"),
        ("fleet", "0019_service_crane_hours_s131"),
        ("ivr_config", "0049_companyuser_role_assist_supervisor_s132"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workorderassistanceunit",
            name="operator",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Chófer asignado al primer tramo del servicio. Vacío "
                    "mientras el albarán está sin asignar."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assistance_units_primary",
                to="ivr_config.companyuser",
                verbose_name="Chófer",
            ),
        ),
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="machine_asset",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Máquina de la familia ASISTENCIA asignada al primer "
                    "tramo desde el panel de tráfico."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assistance_units",
                to="fleet.machineasset",
                verbose_name="Máquina de la flota",
            ),
        ),
        migrations.CreateModel(
            name="WorkOrderAssistanceUnitEvent",
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
                    "kind",
                    models.CharField(
                        choices=[
                            ("CREATED", "Albarán creado"),
                            ("STATUS", "Cambio de estado"),
                            ("ASSIGN", "Asignación"),
                            ("UNASSIGN", "Asignación retirada"),
                        ],
                        max_length=10,
                        verbose_name="Tipo",
                    ),
                ),
                (
                    "from_status",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=20,
                        verbose_name="Estado anterior",
                    ),
                ),
                (
                    "to_status",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=20,
                        verbose_name="Estado nuevo",
                    ),
                ),
                (
                    "detail",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Qué se asignó o retiró, o el motivo del "
                            "cambio."
                        ),
                        max_length=255,
                        verbose_name="Detalle",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Fecha y hora",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        help_text=(
                            "Usuario del panel. Vacío: lo hizo el "
                            "sistema."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assistance_unit_events",
                        to="ivr_config.companyuser",
                        verbose_name="Usuario",
                    ),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="budgets.workorderassistanceunit",
                        verbose_name="Unidad",
                    ),
                ),
            ],
            options={
                "verbose_name": "Evento de albarán (asistencia)",
                "verbose_name_plural": "Eventos de albarán (asistencia)",
                "ordering": ["unit", "created_at", "pk"],
            },
        ),
        migrations.RunPython(
            link_machine_assets, migrations.RunPython.noop,
        ),
    ]
