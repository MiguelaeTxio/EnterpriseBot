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
        skipped_marks = 0
        with_size = with_crc = with_md5 = with_generation = 0

        for blob in client.list_blobs(bucket_name):
            if blob.name.startswith(MARKS_PREFIX):
                skipped_marks += 1
                continue
            if blob.name.endswith("/"):
                folder_paths.add(blob.name.rstrip("/"))
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
            "  %d archivo(s), %d carpeta(s) derivada(s), %d marca(s) "
            "ignorada(s)." % (total, len(folder_paths), skipped_marks)
        )
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
            created, updated = self._write_folders(
                bucket_name, folder_paths, sizes,
            )
            f_created, f_updated = self._write_files(bucket_name, files)
            self._link_domain_objects(bucket_name)

        self.stdout.write(self.style.SUCCESS(
            "  Carpetas: %d nueva(s), %d actualizada(s). "
            "Archivos: %d nuevo(s), %d actualizado(s)."
            % (created, updated, f_created, f_updated)
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

    def _write_folders(self, bucket_name, folder_paths, sizes):
        """
        Upsert one row per folder.

        ---

        Inserta o actualiza una fila por carpeta.
        """
        created = updated = 0
        for path in sorted(folder_paths):
            parent_path, name = split_path(path)
            defaults = {
                "entry_kind": DocumentIndexEntry.KIND_FOLDER,
                "blob_name": path,
                "parent_path": parent_path,
                "parent_path_hash": path_digest(parent_path),
                "name": name,
                "total_size_bytes": sizes.get(path, 0),
            }
            if self._upsert(bucket_name, path, defaults):
                created += 1
            else:
                updated += 1
        self._recount_children(bucket_name)
        return created, updated

    def _write_files(self, bucket_name, files):
        """
        Upsert one row per object.

        ---

        Inserta o actualiza una fila por objeto.
        """
        created = updated = 0
        for blob_name, info in files.items():
            defaults = dict(info)
            defaults["entry_kind"] = DocumentIndexEntry.KIND_FILE
            defaults["blob_name"] = blob_name
            defaults["parent_path_hash"] = path_digest(
                info["parent_path"],
            )
            if self._upsert(bucket_name, blob_name, defaults):
                created += 1
            else:
                updated += 1
        return created, updated

    def _upsert(self, bucket_name, blob_name, defaults):
        """
        Create or update a live row. Returns True when created.

        A row already sitting in someone's trash is left untouched:
        the bucket does not get to overrule a deletion made from the
        panel.

        ---

        Crea o actualiza una fila viva. Devuelve True si la ha creado.

        Una fila que ya está en la papelera de alguien se deja intacta:
        el cubo no puede revocar un borrado hecho desde el panel.
        """
        digest = path_digest(blob_name)
        entry = DocumentIndexEntry.objects.filter(
            bucket=bucket_name,
            blob_name_hash=digest,
            purged_at__isnull=True,
        ).first()

        if entry is None:
            DocumentIndexEntry.objects.create(
                bucket=bucket_name,
                blob_name_hash=digest,
                **defaults
            )
            return True

        if entry.deleted_at is not None:
            return False

        for field, value in defaults.items():
            setattr(entry, field, value)
        entry.save()
        return False

    def _recount_children(self, bucket_name):
        """
        Refresh the precomputed direct-child counter of each folder.

        ---

        Refresca el contador precalculado de hijos directos de cada
        carpeta.
        """
        folders = DocumentIndexEntry.objects.filter(
            bucket=bucket_name,
            entry_kind=DocumentIndexEntry.KIND_FOLDER,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        for folder in folders:
            folder.child_count = DocumentIndexEntry.objects.filter(
                bucket=bucket_name,
                parent_path_hash=path_digest(folder.blob_name),
                deleted_at__isnull=True,
                purged_at__isnull=True,
            ).count()
            folder.save(update_fields=["child_count"])

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
        linked = 0
        for entry in entries:
            object_id = by_blob_name.get(entry.blob_name)
            if object_id is None:
                continue
            entry.domain_content_type = content_type
            entry.domain_object_id = object_id
            entry.save(update_fields=[
                "domain_content_type", "domain_object_id",
            ])
            linked += 1

        self.stdout.write(
            "  Vinculados %d objeto(s) con %s."
            % (linked, model.__name__)
        )
