# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0023_meal_type_s144.py
# H24 (S144): el tipo "Desplazamiento" pasa a ser el de desplazamiento
# (vehículo propio, kilómetros) y se crea "Pausa para comer" (no cuenta
# como jornada; comida o cena según la hora, dietas) en cada empresa
# que ficha por tipos. Si ya existe un tipo con ese nombre, se le pone
# la función y no se crea otro.

from django.db import migrations

MEAL_NAME = "Pausa para comer"


def forwards(apps, schema_editor):
    ClockType = apps.get_model("hr_calendar", "ClockType")
    ClockType.objects.filter(name__iexact="Desplazamiento").update(
        role="travel",
    )
    for company_id in ClockType.objects.values_list(
            "company_id", flat=True).distinct():
        existing = ClockType.objects.filter(
            company_id=company_id, name__iexact=MEAL_NAME,
        ).first()
        if existing is not None:
            existing.role = "meal"
            existing.counts_as_work = False
            existing.save(update_fields=["role", "counts_as_work"])
            continue
        last = ClockType.objects.filter(company_id=company_id).order_by(
            "-order").first()
        ClockType.objects.create(
            company_id=company_id, name=MEAL_NAME, icon="bi-cup-hot",
            counts_as_work=False, role="meal",
            order=(last.order + 1) if last else 1,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0022_clock_extras_s144"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
