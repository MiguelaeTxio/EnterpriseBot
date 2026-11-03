# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0019_clocktype_effective_default_s144.py
# H24 (S144). Fuera el "Fichaje normal": crea confusión (lo ve Juan
# Francisco en Huelva, con Sesame). "Trabajo efectivo" pasa a ser el tipo
# por defecto (el que se usa cuando una entrada llega sin tipo) y queda
# en primer lugar de la lista; el "Fichaje normal" se borra si ningún
# fichaje ni corrección lo usa (en producción, ninguno a 03/11/2026) y,
# si alguno lo usara, solo se desactiva. Si una empresa no tuviera
# "Trabajo efectivo", el "Fichaje normal" se renombra a ese nombre.
# Solo datos: el esquema no cambia.

from django.db import migrations

NORMAL = "Fichaje normal"
EFFECTIVE = "Trabajo efectivo"


def effective_as_default(apps, schema_editor):
    """
    Make "Trabajo efectivo" the default clock type of every company.
    ---
    "Trabajo efectivo" pasa a ser el tipo por defecto de cada empresa.
    """
    clock_type_model = apps.get_model("hr_calendar", "ClockType")
    event_model = apps.get_model("hr_calendar", "ClockEvent")
    correction_model = apps.get_model("hr_calendar", "ClockCorrection")
    for normal in clock_type_model.objects.filter(name__iexact=NORMAL):
        effective = clock_type_model.objects.filter(
            company_id=normal.company_id, name__iexact=EFFECTIVE,
        ).first()
        if effective is None:
            normal.name = EFFECTIVE
            normal.icon = "bi-star"
            normal.counts_as_work = True
            normal.is_default = True
            normal.is_active = True
            normal.save()
            continue
        effective.is_default = True
        effective.is_active = True
        effective.counts_as_work = True
        effective.order = min(effective.order, normal.order)
        effective.save()
        used = (
            event_model.objects.filter(clock_type_id=normal.pk).exists()
            or correction_model.objects.filter(
                old_clock_type_id=normal.pk).exists()
            or correction_model.objects.filter(
                new_clock_type_id=normal.pk).exists()
        )
        if used:
            normal.is_default = False
            normal.is_active = False
            normal.save()
        else:
            normal.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0018_clockcorrection_add_s144"),
    ]

    operations = [
        migrations.RunPython(
            effective_as_default, migrations.RunPython.noop,
        ),
    ]
