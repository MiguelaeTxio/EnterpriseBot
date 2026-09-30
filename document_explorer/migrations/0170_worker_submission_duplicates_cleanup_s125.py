# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0170_worker_submission_duplicates_cleanup_s125.py
# H30 (S125): limpieza de lo que dejó la carrera de la prueba real (dos
# anversos idénticos procesados a la vez y archivados los dos). Toda
# entrega ACEPTADA con la misma huella SHA-256 que otra anterior aceptada
# de la misma persona pasa a DUPLICATE, y su archivo queda obsoleto con
# registro de sustitución hacia el primero. Nada se borra.

from django.db import migrations


def mark_duplicates(apps, schema_editor):
    Submission = apps.get_model(
        "document_explorer", "WorkerDocumentSubmission",
    )
    Entry = apps.get_model("document_explorer", "DocumentIndexEntry")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Log = apps.get_model("document_management", "DocumentSubstitutionLog")
    entry_ct = ContentType.objects.filter(
        app_label="document_explorer", model="documentindexentry",
    ).first()
    first_by_key = {}
    for submission in Submission.objects.filter(
        status="ACCEPTED",
    ).exclude(content_sha256="").order_by("pk"):
        key = (submission.person_id, submission.content_sha256)
        first = first_by_key.get(key)
        if first is None:
            first_by_key[key] = submission
            continue
        submission.status = "DUPLICATE"
        submission.reason = (
            "Repetido: mismo archivo que el adjunto %s (limpieza 0170)."
            % first.pk
        )
        submission.save(update_fields=["status", "reason"])
        entry = Entry.objects.filter(pk=submission.entry_id).first()
        keep = Entry.objects.filter(pk=first.entry_id).first()
        if entry is None or keep is None or entry.is_obsolete:
            continue
        entry.is_obsolete = True
        entry.save(update_fields=["is_obsolete"])
        person = submission.person
        company = person.company if person is not None else None
        if entry_ct is not None and company is not None:
            Log.objects.create(
                company=company,
                superseding_content_type=entry_ct,
                superseding_object_id=keep.pk,
                superseding_label=keep.name,
                superseded_content_type=entry_ct,
                superseded_object_id=entry.pk,
                superseded_label=entry.name,
                subject_label="%s %s, %s" % (
                    person.first_surname, person.second_surname,
                    person.given_name,
                ),
                document_type=(
                    entry.document_type.code if entry.document_type_id
                    else ""
                ),
                reasoning=(
                    "Mismo archivo recibido dos veces por WhatsApp (S125, "
                    "limpieza 0170)."
                ),
            )
        print("0170: adjunto %s repetido de %s -- archivo %s obsoleto."
              % (submission.pk, first.pk, entry.pk))


class Migration(migrations.Migration):

    dependencies = [
        ('document_explorer', '0169_worker_submission_duplicate_s125'),
        ('document_management', '0005_documentalertsettings'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(mark_duplicates, migrations.RunPython.noop),
    ]
