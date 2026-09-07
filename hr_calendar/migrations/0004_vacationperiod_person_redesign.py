# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0004_vacationperiod_person_redesign.py
"""
H31 (S94). Rediseño real de VacationPeriod tras incidente reportado
por Miguel Ángel con evidencia de captura de pantalla: el modelo
original (H24) enlazaba solo con CompanyUser (cuenta de panel),
confundiendo "es trabajador de la empresa" con "tiene acceso de login
al panel". Ver docstring completo de VacationPeriod en models.py para
el detalle.

Esta migración, en un único archivo (esquema + datos + endurecimiento
final), porque el volumen real de filas en producción es trivial (2
filas reales confirmadas por Comando S en S94):

1. Añade `person` (FK PersonIdentity) nullable -- todavía no se puede
   exigir NOT NULL sin datos que rellenarlo primero.
2. Relaja `operator` a nullable (antes obligatorio, CASCADE) y cambia
   su on_delete a SET_NULL, con related_name nuevo
   (vacation_periods_as_operator) para no chocar con el related_name
   de person (vacation_periods, ahora el principal).
3. Datos reales, S94:
   - Borra el pk=4 (operator alvarez_admin, 16-31/07/2026) -- fila de
     prueba, confirmada explícitamente por Miguel Ángel como
     eliminable ("ese periodo vacacional que ahora mismo se puede
     eliminar porque fue una prueba que hice").
   - Para el resto de filas (pk=3, Antonio Fontalba, y cualquier otra
     que exista en el momento real del despliegue), reenlaza `person`
     desde `operator` vía el puente PersonIdentity.company_user (S74).
   - Salvaguarda: si alguna fila no resuelve PersonIdentity (caso no
     esperado con los datos reales confirmados en S94, pero posible si
     el estado real cambió entre sesiones), se borra esa fila en vez
     de dejar la migración a medias -- se registra con print() para
     que quede en la salida real del despliegue, nunca en silencio.
4. Endurece `person` a NOT NULL, ya con todas las filas resueltas.
"""
import django.db.models.deletion
from django.db import migrations, models


def backfill_person_and_drop_test_row(apps, schema_editor):
    VacationPeriod = apps.get_model("hr_calendar", "VacationPeriod")
    PersonIdentity = apps.get_model("document_explorer", "PersonIdentity")

    # Fila de prueba real, confirmada por Miguel Ángel en S94.
    VacationPeriod.objects.filter(pk=4).delete()

    for period in VacationPeriod.objects.filter(person__isnull=True):
        person = None
        if period.operator_id is not None:
            person = PersonIdentity.objects.filter(
                company_user_id=period.operator_id,
            ).first()
        if person is None:
            print(
                f"# [0004_vacationperiod_person_redesign] AVISO: "
                f"VacationPeriod pk={period.pk} (operator_id="
                f"{period.operator_id!r}) no resolvió ninguna "
                f"PersonIdentity real -- fila borrada para no dejar "
                f"la migración a medias. Revisar manualmente si hacía "
                f"falta conservarla."
            )
            period.delete()
            continue
        period.person_id = person.pk
        period.save(update_fields=["person"])


def noop_reverse(apps, schema_editor):
    """
    No se revierte -- mismo criterio que otras migraciones de datos
    reales del proyecto (0062_person_identity_audit_fixes_s74.py):
    reconstruir qué filas se borraron o qué operator tenían antes no
    es posible con certeza.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0003_seed_first_medical_leave_period"),
        ("document_explorer", "0069_seed_expediente_disciplinario_s83"),
    ]

    operations = [
        migrations.AddField(
            model_name="vacationperiod",
            name="person",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="vacation_periods",
                to="document_explorer.personidentity",
                verbose_name="Persona",
            ),
        ),
        migrations.AlterField(
            model_name="vacationperiod",
            name="operator",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="vacation_periods_as_operator",
                to="ivr_config.companyuser",
                verbose_name="Cuenta de panel vinculada",
            ),
        ),
        migrations.RunPython(
            backfill_person_and_drop_test_row, noop_reverse,
        ),
        migrations.AlterField(
            model_name="vacationperiod",
            name="person",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="vacation_periods",
                to="document_explorer.personidentity",
                verbose_name="Persona",
            ),
        ),
    ]
