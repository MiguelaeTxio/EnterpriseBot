# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0003_seed_first_medical_leave_period.py
"""
H31 (S94). Criterio de cierre del Punto 1 de la hoja de ruta: crea al
menos un MedicalLeavePeriod real a partir de un PARTE_BAJA_MEDICA
existente de una persona con baja real en BD -- Alejandro García
Luque, PersonIdentity pk=158 (dni=74852724Y, confirmado en
0062_person_identity_audit_fixes_s74.py), según lo indicado
explícitamente en el anexo H31.

Toma el DocumentIndexEntry más reciente clasificado como
PARTE_BAJA_MEDICA y vinculado a esa PersonIdentity vía
domain_content_type/domain_object_id (mismo mecanismo que
0062_person_identity_audit_fixes_s74.py), con issue_date real
extraído (H30 completó la extracción del dominio PERSONAL al 100% en
S92). date_start = issue_date de ese documento (h28_migration_agent/
extract_personal_dates_bulk.py mapea PARTE_BAJA_MEDICA -> "issue").
date_end queda nulo -- un único documento de baja no declara por sí
solo la fecha de alta médica. contingency_type se fija a COMUN por
defecto -- el documento de origen no distingue tipo de contingencia
de forma estructurada; pendiente de refinar caso por caso si Miguel
Ángel lo pide en una sesión futura.

No falla el despliegue si la persona o el documento no existen en el
momento de aplicar esta migración (estado real de BD puede haber
cambiado entre sesiones) -- se limita a no crear nada, nunca a
romper `migrate --noinput`.
"""
from django.db import migrations


def seed_first_medical_leave_period(apps, schema_editor):
    PersonIdentity = apps.get_model("document_explorer", "PersonIdentity")
    DocumentIndexEntry = apps.get_model("document_explorer", "DocumentIndexEntry")
    ContentType = apps.get_model("contenttypes", "ContentType")
    MedicalLeavePeriod = apps.get_model("hr_calendar", "MedicalLeavePeriod")

    person = PersonIdentity.objects.filter(pk=158, dni="74852724Y").first()
    if person is None:
        return

    person_ct = ContentType.objects.get_for_model(PersonIdentity)

    entry = (
        DocumentIndexEntry.objects.filter(
            document_type__code="PARTE_BAJA_MEDICA",
            domain_content_type=person_ct,
            domain_object_id=person.pk,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        .exclude(issue_date__isnull=True)
        .order_by("-issue_date")
        .first()
    )
    if entry is None:
        return

    if MedicalLeavePeriod.objects.filter(source_document=entry).exists():
        return

    MedicalLeavePeriod.objects.create(
        person=person,
        source_document=entry,
        date_start=entry.issue_date,
        date_end=None,
        contingency_type="COMUN",
    )


def noop_reverse(apps, schema_editor):
    """
    No se revierte -- mismo criterio que
    0062_person_identity_audit_fixes_s74.py: distinguir con certeza
    si el registro fue creado por esta migración o a mano tras su
    aplicación no es posible de forma fiable.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0002_medicalleaveperiod"),
        ("document_explorer", "0069_seed_expediente_disciplinario_s83"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(seed_first_medical_leave_period, noop_reverse),
    ]
