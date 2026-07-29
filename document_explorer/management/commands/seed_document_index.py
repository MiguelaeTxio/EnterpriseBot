# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/seed_document_index.py
"""
Django management command: seed_document_index.

Full sweep of the indexed buckets into DocumentIndexEntry. Idempotent
and re-runnable: a second pass over an unchanged bucket updates
metadata and creates nothing.

This is the EXPENSIVE path, on purpose. Google's own documentation
warns that listing an entire hierarchical-namespace bucket has to walk
every folder and subfolder. Use it to seed, to repair, or after a bulk
change -- not as the routine refresh, which is what
`refresh_document_folder` is for.

What it deliberately does NOT do:

- It never resurrects a logically deleted row. If an entry already
  carries `deleted_at`, it stays in its owner's trash.
- It never deletes anything, in the bucket or in the table.
- It never touches the marks prefix, which holds the local-existence
  manifests written by the Windows agent, not documents.

---

Comando de gestión Django: seed_document_index.

Barrido completo de los cubos indexados hacia DocumentIndexEntry.
Idempotente y reejecutable: una segunda pasada sobre un cubo sin
cambios actualiza metadatos y no crea nada.

Éste es el camino CARO, y a propósito. La documentación de Google
advierte de que listar un cubo entero con Namespace Jerárquico obliga a
recorrer todas las carpetas y subcarpetas. Se usa para sembrar, para
reparar o tras un cambio masivo -- no como refresco rutinario, para lo
que está `refresh_document_folder`.

Lo que deliberadamente NO hace:

- Nunca resucita una fila borrada de forma lógica. Si ya tiene
  `deleted_at`, se queda en la papelera de su dueño.
- Nunca borra nada, ni en el cubo ni en la tabla.
- Nunca toca el prefijo de marcas, donde viven los manifiestos de
  existencia local del agente de Windows, que no son documentos.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from document_explorer import index_writer
from document_explorer.buckets import INDEXED_BUCKETS, MARKS_PREFIX
from document_explorer.gcs_index_service import (
    has_hierarchical_namespace,
    iter_all_folders,
)
from spare_parts.gcs_service import get_storage_client


class Command(BaseCommand):
    help = (
        "Siembra el índice documental con el contenido real de los "
        "cubos de Google Cloud Storage. Idempotente: se puede "
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
        Sweep one bucket and report on it.

        ---

        Barre un cubo e informa del resultado.
        """
        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %s ===" % bucket_name,
        ))

        file_rows = []
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

            row = index_writer.file_row(blob)
            file_rows.append(row)
            folder_paths.update(
                index_writer.ancestors_of(row["parent_path"])
            )

            if blob.size is not None:
                with_size += 1
            if blob.crc32c:
                with_crc += 1
            if blob.md5_hash:
                with_md5 += 1
            if blob.generation is not None:
                with_generation += 1

        derived = set(folder_paths)
        hns = has_hierarchical_namespace(client, bucket_name)
        if hns:
            for path, _updated in iter_all_folders(bucket_name):
                folder_paths.add(path)

        total = len(file_rows)
        self.stdout.write(
            "  %d archivo(s), %d carpeta(s), %d marca(s) ignorada(s)."
            % (total, len(folder_paths), skipped_marks)
        )
        self._report_folders(hns, derived, folder_paths)
        self._report_metadata(
            total, with_size, with_crc, with_md5, with_generation,
        )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "  Dry-run: no se ha escrito nada en la base de datos."
            ))
            return

        sizes = index_writer.accumulate_folder_sizes(
            file_rows, folder_paths,
        )
        rows = [
            index_writer.folder_row(path, sizes.get(path, 0))
            for path in sorted(folder_paths)
        ] + file_rows

        with transaction.atomic():
            created, updated = index_writer.persist_rows(
                bucket_name, rows,
            )
            index_writer.recount_children(bucket_name)
            linked, model_name = index_writer.link_domain_objects(
                bucket_name,
            )

        if model_name:
            self.stdout.write(
                "  Vinculados %d objeto(s) con %s."
                % (linked, model_name)
            )
        self.stdout.write(self.style.SUCCESS(
            "  %d fila(s) nueva(s), %d actualizada(s)."
            % (created, updated)
        ))

    def _report_folders(self, hns, derived, folder_paths):
        """
        Explain where the folders came from.

        Empty folders only exist in hierarchical-namespace buckets. In
        a flat bucket a folder is just the prefix of an existing
        object, so none is missing -- reporting otherwise would be
        alarming and wrong.

        ---

        Explica de dónde salen las carpetas.

        Las carpetas vacías solo existen en cubos con Namespace
        Jerárquico. En un cubo plano una carpeta es solo el prefijo de
        un objeto existente, así que no falta ninguna -- informar de lo
        contrario sería alarmante y falso.
        """
        if hns:
            self.stdout.write(
                "  Namespace Jerárquico: sí. %d carpeta(s) deducidas "
                "de rutas de archivo y %d halladas vía Storage "
                "Control; estas últimas están VACÍAS y el listado de "
                "objetos no las devuelve nunca."
                % (len(derived), len(folder_paths) - len(derived))
            )
        else:
            self.stdout.write(
                "  Namespace Jerárquico: no. Las %d carpeta(s) salen "
                "de las rutas de archivo y no falta ninguna: en un "
                "cubo plano una carpeta vacía no puede existir."
                % len(derived)
            )

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
