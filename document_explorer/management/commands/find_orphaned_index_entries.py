# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/find_orphaned_index_entries.py
"""
Django management command: find_orphaned_index_entries.

Reverse of seed_document_index: seed_document_index brings GCS objects
INTO the index (creates what is missing, refreshes what changed) but
never removes a row whose object disappeared from the bucket. This
command finds exactly that -- live DocumentIndexEntry FILE rows
(deleted_at and purged_at both null) whose blob no longer exists in
GCS, meaning the object was deleted directly in the bucket, bypassing
the explorer's own two-tier deletion.

Report-only, always. Marking a row `purged_at` is a decision with
audit consequences (H29 design: purged_at is the tier only an
administrator can trigger, and it keeps the row as a historical
record) -- this command never writes to the database, by design, not
even behind a --confirm-style flag: Miguel Angel decides case by case
what to do with what it finds.

Scope: FILE entries only. A FOLDER row is not a real GCS object in a
flat-namespace sense (it is derived from file paths); deciding whether
an empty folder still "exists" is a separate, fuzzier question left
out of this first pass on purpose.

Uso:
    python -m dotenv run python manage.py find_orphaned_index_entries
    python -m dotenv run python manage.py find_orphaned_index_entries --bucket cgs_grupo_alvarez

---

Comando de gestión Django: find_orphaned_index_entries.

Inverso de seed_document_index: éste trae objetos de GCS HACIA el
índice (crea lo que falta, refresca lo que cambió) pero nunca retira
una fila cuyo objeto desapareció del cubo. Este comando encuentra
justo eso -- filas vivas de DocumentIndexEntry de tipo FILE
(deleted_at y purged_at nulos) cuyo blob ya no existe en GCS, es
decir, el objeto se borró directamente en el cubo, sin pasar por el
borrado de dos niveles del propio explorador.

Solo informa, siempre. Marcar una fila como purged_at es una decisión
con consecuencias de auditoría (diseño de H29: purged_at es el nivel
que solo puede disparar un administrador, y conserva la fila como
registro histórico) -- este comando nunca escribe en la base de datos,
por diseño, ni siquiera detrás de un flag al estilo --confirm: Miguel
Ángel decide caso por caso qué hacer con lo que encuentre.

Alcance: solo entradas FILE. Una fila FOLDER no es un objeto real de
GCS en sentido de espacio de nombres plano (se deriva de rutas de
archivo); decidir si una carpeta vacía "sigue existiendo" es una
pregunta aparte y más difusa que se deja fuera de esta primera pasada
a propósito.
"""
from django.core.management.base import BaseCommand, CommandError

from document_explorer.buckets import INDEXED_BUCKETS
from document_explorer.models import DocumentIndexEntry
from spare_parts.gcs_service import get_storage_client


class Command(BaseCommand):
    help = (
        "Lista filas vivas del indice documental cuyo blob ya no "
        "existe en el cubo -- borrado directo en GCS por fuera del "
        "explorador. Solo informa, nunca escribe en la base de datos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            action="append",
            dest="buckets",
            help=(
                "Cubo concreto a auditar. Se puede repetir. Por "
                "defecto, los cinco cubos indexados."
            ),
        )

    def handle(self, *args, **options):
        selected = options.get("buckets") or list(INDEXED_BUCKETS)
        unknown = [b for b in selected if b not in INDEXED_BUCKETS]
        if unknown:
            raise CommandError(
                "Cubos no indexados: %s" % ", ".join(unknown)
            )

        client = get_storage_client()
        total_orphans = 0
        for bucket_name in selected:
            total_orphans += self._audit_bucket(client, bucket_name)

        if total_orphans:
            self.stdout.write(self.style.WARNING(
                "\n%d fila(s) huerfana(s) en total, en todos los "
                "cubos auditados. No se ha escrito nada en la base de "
                "datos -- decide caso por caso qué hacer con cada una."
                % total_orphans
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nNinguna fila huerfana en los cubos auditados."
            ))

    def _audit_bucket(self, client, bucket_name):
        """
        Audit one bucket and report on it. Returns the orphan count.

        ---

        Audita un cubo e informa del resultado. Devuelve el número de
        huérfanas.
        """
        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %s ===" % bucket_name,
        ))

        real_blob_names = {
            blob.name for blob in client.list_blobs(bucket_name)
            if not blob.name.endswith("/")
        }

        live_entries = list(
            DocumentIndexEntry.objects.filter(
                bucket=bucket_name,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True,
                purged_at__isnull=True,
            ).only("id", "blob_name")
        )

        orphans = [
            entry for entry in live_entries
            if entry.blob_name not in real_blob_names
        ]

        self.stdout.write(
            "  %d fila(s) FILE vivas en el indice, %d objeto(s) "
            "reales en el cubo, %d huerfana(s)."
            % (len(live_entries), len(real_blob_names), len(orphans))
        )
        for entry in orphans:
            self.stdout.write("  id=%d  %s" % (entry.id, entry.blob_name))

        if not orphans:
            self.stdout.write("  (ninguna huérfana)")

        return len(orphans)
