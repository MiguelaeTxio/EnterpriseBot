# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0171_worker_submission_duplicates_restore_s125.py
# H30 (S125): segunda parte de la limpieza de la carrera de la prueba
# real. Los dos anversos se archivaron a la vez con el MISMO nombre, así
# que sus dos filas del índice apuntan al mismo objeto de GCS, y la
# sustitución automática dejó obsoleto al primero (el bueno).
# - La fila del repetido que comparte objeto con la buena se retira del
#   índice como registro de auditoría (deleted_at + purged_at), SIN tocar
#   GCS: purgarla desde la papelera habría borrado el objeto compartido.
# - La buena vuelve a ser vigente si solo la dejó obsoleta el repetido.

from django.db import migrations
from django.utils import timezone


def restore_kept_entries(apps, schema_editor):
    Submission = apps.get_model(
        "document_explorer", "WorkerDocumentSubmission",
    )
    Entry = apps.get_model("document_explorer", "DocumentIndexEntry")
    Log = apps.get_model("document_management", "DocumentSubstitutionLog")
    now = timezone.now()
    for duplicate in Submission.objects.filter(
        status="DUPLICATE", entry__isnull=False,
    ).exclude(content_sha256=""):
        first = Submission.objects.filter(
            person_id=duplicate.person_id,
            content_sha256=duplicate.content_sha256,
            status="ACCEPTED",
            pk__lt=duplicate.pk,
        ).order_by("pk").first()
        if first is None or first.entry_id is None:
            continue
        dup_entry = Entry.objects.get(pk=duplicate.entry_id)
        keep = Entry.objects.get(pk=first.entry_id)
        if (dup_entry.bucket == keep.bucket
                and dup_entry.blob_name == keep.blob_name
                and dup_entry.purged_at is None):
            dup_entry.deleted_at = now
            dup_entry.purged_at = now
            dup_entry.save(update_fields=["deleted_at", "purged_at"])
            print("0171: fila %s retirada del índice (comparte objeto con "
                  "%s; GCS intacto)." % (dup_entry.pk, keep.pk))
        wrongly_superseded = Log.objects.filter(
            superseding_object_id=dup_entry.pk,
            superseded_object_id=keep.pk,
        ).exists()
        if keep.is_obsolete and wrongly_superseded:
            keep.is_obsolete = False
            keep.save(update_fields=["is_obsolete"])
            print("0171: archivo %s vuelve a estar vigente." % keep.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('document_explorer', '0170_worker_submission_duplicates_cleanup_s125'),
    ]

    operations = [
        migrations.RunPython(
            restore_kept_entries, migrations.RunPython.noop,
        ),
    ]
