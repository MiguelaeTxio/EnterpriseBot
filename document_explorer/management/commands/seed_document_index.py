# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/seed_document_index.py
"""
Django management command: seed_document_index.

Populates DocumentIndexEntry from the real contents of the indexed
buckets. Idempotent and re-runnable by design: a second run over an
unchanged bucket updates metadata in place and creates nothing.

What it deliberately does NOT do:

- It never resurrects a logically deleted row. If an entry already
  carries `deleted_at`, it stays in its owner's trash: the seeding is
  a mirror of the bucket, not an authority over the panel's own
  decisions.
- It never deletes anything, in the bucket or in the table.
- It never touches the marks prefix, which holds the local-existence
  manifests written by the Windows agent, not documents.

It also answers an open empirical question instead of assuming it:
nobody has confirmed which metadata Google Cloud Storage actually
returns when LISTING objects, as opposed to reading each one. The
command counts how many blobs arrived with size, crc32c, md5 and
generation populated, and reports it. That report decides whether the
index can be kept fresh by listing alone.

---

Comando de gestión Django: seed_document_index.

Puebla DocumentIndexEntry a partir del contenido real de los cubos
indexados. Idempotente y reejecutable por diseño: una segunda pasada
sobre un cubo que no ha cambiado actualiza metadatos y no crea nada.

Lo que deliberadamente NO hace:

- Nunca resucita una fila borrada de forma lógica. Si una entrada ya
  tiene `deleted_at`, se queda en la papelera de su dueño: el sembrado
  es un espejo del cubo, no una autoridad sobre las decisiones tomadas
  desde el panel.
- Nunca borra nada, ni en el cubo ni en la tabla.
- Nunca toca el prefijo de marcas, que guarda los manifiestos de
  existencia local que escribe el agente de Windows, no documentos.

Además responde a una pregunta empírica abierta en vez de darla por
supuesta: nadie ha confirmado qué metadatos devuelve realmente Google
Cloud Storage al LISTAR objetos, frente a leer cada uno. El comando
cuenta cuántos blobs llegaron con tamaño, crc32c, md5 y generación
rellenos, y lo informa. Ese informe decide si el índice se puede
mantener al día solo con listados.
"""
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from document_explorer.buckets import (
    DOMAIN_MODEL_BY_BUCKET,
    INDEXED_BUCKETS,
    MARKS_PREFIX,
)
from document_explorer.models import DocumentIndexEntry, path_digest
from spare_parts.gcs_service import get_storage_client


def split_path(blob_name):
    """
    Split a blob name into (parent_path, name).

    ---

    Parte un nombre de blob en (carpeta_contenedora, nombre).
    """
    if "/" not in blob_name:
        return "", blob_name
    parent, _, name = blob_name.rpartition("/")
    return parent, name


def ancestors_of(parent_path):
    """
    Yield every ancestor folder path of a blob, root first.

    ---

    Devuelve todas las carpetas antecesoras de un blob, de la raíz
    hacia dentro.
    """
    if not parent_path:
        return []
    parts = parent_path.split("/")
    return ["/".join(parts[:i + 1]) for i in range(len(parts))]


class Command(BaseCommand):
    help = (
        "Siembra el índice documental a partir del contenido real de "
        "los cubos de Google Cloud Storage. Idempotente: se puede "
        "reejecutar sin efectos secundarios."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            action="append",
            dest="buckets",
            help=(
                "Cubo concreto a sembrar. Se puede repetir. Por "
                "defecto, todos los cubos indexados."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Recorre los cubos y emite el informe sin escribir "
                "nada en la base de datos."
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
        for bucket_name in selected:
            self._seed_bucket(client, bucket_name, options["dry_run"])

    def _seed_bucket(self, client, bucket_name, dry_run):
        """
        Seed a single bucket and report on it.

        ---

        Siembra un único cubo e informa del resultado.
        """
        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %s ===" % bucket_name,
        ))

        files = {}
        folder_paths = set()
        real_folder_objects = 0
        skipped_marks = 0
        with_size = with_crc = with_md5 = with_generation = 0

        for blob in client.list_blobs(bucket_name):
            if blob.name.startswith(MARKS_PREFIX):
                skipped_marks += 1
                continue
            if blob.name.endswith("/"):
                folder_paths.add(blob.name.rstrip("/"))
                real_folder_objects += 1
                continue

            parent_path, name = split_path(blob.name)
            files[blob.name] = {
                "parent_path": parent_path,
                "name": name,
                "size_bytes": blob.size,
                "content_type": blob.content_type or "",
                "crc32c": blob.crc32c or "",
                "md5_hash": blob.md5_hash or "",
                "generation": blob.generation,
                "gcs_updated_at": blob.updated,
            }
            folder_paths.update(ancestors_of(parent_path))

            if blob.size is not None:
                with_size += 1
            if blob.crc32c:
                with_crc += 1
            if blob.md5_hash:
                with_md5 += 1
            if blob.generation is not None:
                with_generation += 1

        total = len(files)
        self.stdout.write(
            "  %d archivo(s), %d carpeta(s), %d marca(s) ignorada(s)."
            % (total, len(folder_paths), skipped_marks)
        )
        self.stdout.write(
            "  De esas carpetas, %d llegaron como objeto real del cubo "
            "y %d se dedujeron de las rutas de archivo."
            % (real_folder_objects, len(folder_paths) - real_folder_objects)
        )
        if not real_folder_objects and folder_paths:
            self.stdout.write(self.style.WARNING(
                "  Aviso: el listado no devuelve objetos-carpeta, asi "
                "que una carpeta VACIA es invisible para el indice. "
                "Relevante para la limpieza de la Fase 2 de H28, que "
                "existe justamente para eliminar carpetas vacias."
            ))
        self._report_metadata(
            total, with_size, with_crc, with_md5, with_generation,
        )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "  Dry-run: no se ha escrito nada en la base de datos."
            ))
            return

        sizes = self._folder_sizes(files, folder_paths)
        with transaction.atomic():
            created, updated = self._persist(
                bucket_name, files, folder_paths, sizes,
            )
            self._recount_children(bucket_name)
            self._link_domain_objects(bucket_name)

        self.stdout.write(self.style.SUCCESS(
            "  %d fila(s) nueva(s), %d actualizada(s)."
            % (created, updated)
        ))

    def _report_metadata(self, total, size, crc, md5, generation):
        """
        Report which metadata the listing actually returned.

        ---

        Informa de qué metadatos ha devuelto realmente el listado.
        """
        if not total:
            return
        self.stdout.write(
            "  Metadatos presentes en el listado -- tamaño: %d/%d, "
            "crc32c: %d/%d, md5: %d/%d, generación: %d/%d."
            % (size, total, crc, total, md5, total, generation, total)
        )
        if md5 < total:
            self.stdout.write(
                "  Nota: %d objeto(s) sin MD5. Es lo esperado en "
                "objetos compuestos o subidos por multipart de la API "
                "XML; para esos, CRC32C es el hash de referencia."
                % (total - md5)
            )

    def _folder_sizes(self, files, folder_paths):
        """
        Accumulate each file's size into every ancestor folder.

        Done in memory in a single pass: asking the database for a
        recursive sum per folder would be exactly the kind of nested
        query the index exists to avoid.

        ---

        Acumula el tamaño de cada archivo en todas sus carpetas
        antecesoras.

        Se hace en memoria en una sola pasada: pedir a la base de datos
        una suma recursiva por carpeta sería justo el tipo de consulta
        anidada que el índice existe para evitar.
        """
        sizes = {path: 0 for path in folder_paths}
        for info in files.values():
            size = info["size_bytes"] or 0
            for ancestor in ancestors_of(info["parent_path"]):
                if ancestor in sizes:
                    sizes[ancestor] += size
        return sizes

    def _row_defaults(self):
        """
        Uniform field set, required by bulk_update.

        ---

        Conjunto uniforme de campos, que bulk_update exige.
        """
        return {
            "entry_kind": DocumentIndexEntry.KIND_FILE,
            "blob_name": "",
            "parent_path": "",
            "parent_path_hash": "",
            "name": "",
            "size_bytes": None,
            "content_type": "",
            "crc32c": "",
            "md5_hash": "",
            "generation": None,
            "gcs_updated_at": None,
            "total_size_bytes": 0,
        }

    def _build_rows(self, files, folder_paths, sizes):
        """
        Build one normalised row per folder and per file.

        ---

        Construye una fila normalizada por cada carpeta y cada
        archivo.
        """
        rows = []
        for path in sorted(folder_paths):
            parent_path, name = split_path(path)
            row = self._row_defaults()
            row.update({
                "entry_kind": DocumentIndexEntry.KIND_FOLDER,
                "blob_name": path,
                "parent_path": parent_path,
                "parent_path_hash": path_digest(parent_path),
                "name": name,
                "total_size_bytes": sizes.get(path, 0),
            })
            rows.append(row)

        for blob_name, info in files.items():
            row = self._row_defaults()
            row.update(info)
            row.update({
                "entry_kind": DocumentIndexEntry.KIND_FILE,
                "blob_name": blob_name,
                "parent_path_hash": path_digest(info["parent_path"]),
            })
            rows.append(row)
        return rows

    def _persist(self, bucket_name, files, folder_paths, sizes):
        """
        Write every row in batches instead of one query per row.

        The whole bucket is read in a single query, partitioned in
        memory, and written with bulk_create/bulk_update. A row
        already sitting in someone\'s trash is skipped: the bucket
        does not get to overrule a deletion made from the panel.

        ---

        Escribe todas las filas por lotes en vez de una consulta por
        fila.

        El cubo entero se lee en una sola consulta, se reparte en
        memoria y se escribe con bulk_create/bulk_update. Una fila que
        ya está en la papelera de alguien se omite: el cubo no puede
        revocar un borrado hecho desde el panel.
        """
        existing = {
            digest: (pk, deleted_at)
            for digest, pk, deleted_at in (
                DocumentIndexEntry.objects
                .filter(bucket=bucket_name, purged_at__isnull=True)
                .values_list("blob_name_hash", "id", "deleted_at")
            )
        }

        fields = sorted(self._row_defaults().keys())
        to_create = []
        to_update = []

        for row in self._build_rows(files, folder_paths, sizes):
            digest = path_digest(row["blob_name"])
            found = existing.get(digest)
            if found is None:
                to_create.append(DocumentIndexEntry(
                    bucket=bucket_name,
                    blob_name_hash=digest,
                    **row
                ))
            elif found[1] is None:
                to_update.append(DocumentIndexEntry(
                    id=found[0],
                    bucket=bucket_name,
                    blob_name_hash=digest,
                    **row
                ))

        DocumentIndexEntry.objects.bulk_create(
            to_create, batch_size=1000,
        )
        if to_update:
            DocumentIndexEntry.objects.bulk_update(
                to_update, fields, batch_size=1000,
            )
        return len(to_create), len(to_update)

    def _recount_children(self, bucket_name):
        """
        Refresh every folder counter with two queries, not one per
        folder.

        ---

        Refresca el contador de todas las carpetas con dos consultas,
        no una por carpeta.
        """
        counts = dict(
            DocumentIndexEntry.objects
            .filter(
                bucket=bucket_name,
                deleted_at__isnull=True,
                purged_at__isnull=True,
            )
            .values_list("parent_path_hash")
            .annotate(total=Count("id"))
        )
        folders = list(
            DocumentIndexEntry.objects.filter(
                bucket=bucket_name,
                entry_kind=DocumentIndexEntry.KIND_FOLDER,
                deleted_at__isnull=True,
                purged_at__isnull=True,
            )
        )
        for folder in folders:
            folder.child_count = counts.get(
                path_digest(folder.blob_name), 0,
            )
        if folders:
            DocumentIndexEntry.objects.bulk_update(
                folders, ["child_count"], batch_size=1000,
            )

    def _link_domain_objects(self, bucket_name):
        """
        Point each entry at its business model row, when there is one.

        ---

        Apunta cada entrada a su fila de modelo de negocio, cuando la
        hay.
        """
        mapping = DOMAIN_MODEL_BY_BUCKET.get(bucket_name)
        if mapping is None:
            return

        app_label, model_name, field = mapping
        model = apps.get_model(app_label, model_name)
        content_type = ContentType.objects.get_for_model(model)

        by_blob_name = dict(
            model.objects
            .exclude(**{field: ""})
            .values_list(field, "id")
        )
        if not by_blob_name:
            return

        entries = DocumentIndexEntry.objects.filter(
            bucket=bucket_name,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            domain_object_id__isnull=True,
        )
        pending = []
        for entry in entries:
            object_id = by_blob_name.get(entry.blob_name)
            if object_id is None:
                continue
            entry.domain_content_type = content_type
            entry.domain_object_id = object_id
            pending.append(entry)

        if pending:
            DocumentIndexEntry.objects.bulk_update(
                pending,
                ["domain_content_type", "domain_object_id"],
                batch_size=1000,
            )
        linked = len(pending)

        self.stdout.write(
            "  Vinculados %d objeto(s) con %s."
            % (linked, model.__name__)
        )
