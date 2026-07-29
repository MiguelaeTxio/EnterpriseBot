# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/refresh_document_folder.py
"""
Django management command: refresh_document_folder.

Refreshes ONE folder of the index: its direct files and its direct
subfolders. This is the routine path, and the efficient one.

Google's documentation is explicit about why: listing an entire
hierarchical-namespace bucket has to walk every folder and subfolder,
while listing within a specific prefix using a delimiter is the
efficient operation. The full sweep (`seed_document_index`) took 45
seconds over 37.700 objects in production; this one only ever reads a
single folder.

Empty subfolders are covered here too, without the Storage Control
API: `include_folders_as_prefixes` makes the object listing return
Folders among its prefixes, which is exactly the gap that made empty
folders invisible to the index.

WHAT IT DOES NOT DO, AND WHY

If a row exists in the index whose object is no longer in the bucket,
this command REPORTS it and changes nothing. It does not delete. Under
the design of H29 that situation should be impossible -- the panel is
the only thing that removes objects, and it updates the row itself --
so its appearance means either a deletion that bypassed the panel or a
bug. Silently erasing the evidence would destroy exactly the
information needed to tell those two apart.

---

Comando de gestión Django: refresh_document_folder.

Refresca UNA carpeta del índice: sus archivos directos y sus
subcarpetas directas. Éste es el camino rutinario, y el eficiente.

La documentación de Google explica por qué: listar un cubo entero con
Namespace Jerárquico obliga a recorrer todas las carpetas y
subcarpetas, mientras que listar dentro de un prefijo concreto con
delimitador es la operación eficiente. El barrido completo
(`seed_document_index`) tardó 45 segundos sobre 37.700 objetos en
producción; éste lee una sola carpeta.

Las subcarpetas vacías también quedan cubiertas aquí, y sin la API de
Storage Control: `include_folders_as_prefixes` hace que el listado de
objetos devuelva las Folders entre sus prefijos, que es justamente el
hueco por el que las carpetas vacías eran invisibles para el índice.

LO QUE NO HACE, Y POR QUÉ

Si existe una fila cuyo objeto ya no está en el cubo, este comando lo
INFORMA y no cambia nada. No borra. Con el diseño de H29 esa situación
debería ser imposible -- el panel es lo único que retira objetos, y él
mismo actualiza la fila --, así que si aparece significa o un borrado
que se saltó el panel o un error. Borrar la evidencia en silencio
destruiría justo la información que permite distinguir una cosa de la
otra.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from document_explorer import index_writer
from document_explorer.buckets import INDEXED_BUCKETS, MARKS_PREFIX
from document_explorer.gcs_index_service import list_folder_children
from document_explorer.models import DocumentIndexEntry, path_digest
from spare_parts.gcs_service import get_storage_client


class Command(BaseCommand):
    help = (
        "Refresca una sola carpeta del índice documental: sus "
        "archivos y subcarpetas directos. Camino rutinario y "
        "eficiente, frente al barrido completo de seed_document_index."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            required=True,
            help="Cubo indexado al que pertenece la carpeta.",
        )
        parser.add_argument(
            "--path",
            default="",
            help=(
                "Ruta de la carpeta dentro del cubo, sin barra final. "
                "Vacío para la raíz del cubo."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Informa de lo que haría sin escribir nada.",
        )

    def handle(self, *args, **options):
        bucket_name = options["bucket"]
        if bucket_name not in INDEXED_BUCKETS:
            raise CommandError(
                "Cubo no indexado: %s" % bucket_name
            )

        folder_path = options["path"].strip().strip("/")
        if folder_path and (
            (folder_path + "/").startswith(MARKS_PREFIX)
        ):
            raise CommandError(
                "El prefijo de marcas no se indexa: guarda los "
                "manifiestos de existencia local del agente, que no "
                "son documentos."
            )

        client = get_storage_client()
        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %s/%s ===" % (bucket_name, folder_path or "(raíz)")
        ))

        blobs, subfolders = list_folder_children(
            client, bucket_name, folder_path,
        )
        blobs = [
            b for b in blobs if not b.name.startswith(MARKS_PREFIX)
        ]
        subfolders = [
            p for p in subfolders
            if not (p + "/").startswith(MARKS_PREFIX)
        ]

        self.stdout.write(
            "  %d archivo(s) y %d subcarpeta(s) directas."
            % (len(blobs), len(subfolders))
        )

        self._report_vanished(bucket_name, folder_path, blobs)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(
                "  Dry-run: no se ha escrito nada en la base de datos."
            ))
            return

        file_rows = [index_writer.file_row(b) for b in blobs]
        rows = [
            index_writer.folder_row(path) for path in subfolders
        ] + file_rows

        # La propia carpeta refrescada también debe existir como fila,
        # salvo que sea la raíz del cubo, que no es una carpeta.
        if folder_path:
            rows.append(index_writer.folder_row(folder_path))

        scope = {path_digest(row["blob_name"]) for row in rows}

        with transaction.atomic():
            created, updated = index_writer.persist_rows(
                bucket_name, rows, scope_hashes=scope,
            )
            touched = index_writer.recount_children(
                bucket_name,
                folder_paths=subfolders + (
                    [folder_path] if folder_path else []
                ),
            )
            linked, model_name = index_writer.link_domain_objects(
                bucket_name,
            )

        if model_name:
            self.stdout.write(
                "  Vinculados %d objeto(s) con %s."
                % (linked, model_name)
            )
        self.stdout.write(self.style.SUCCESS(
            "  %d fila(s) nueva(s), %d actualizada(s), %d contador(es) "
            "de carpeta recalculado(s)."
            % (created, updated, touched)
        ))

    def _report_vanished(self, bucket_name, folder_path, blobs):
        """
        Report indexed files that are no longer in the bucket.

        ---

        Informa de archivos indexados que ya no están en el cubo.
        """
        live = {b.name for b in blobs}
        indexed = DocumentIndexEntry.objects.filter(
            bucket=bucket_name,
            parent_path_hash=path_digest(folder_path),
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        ).values_list("blob_name", flat=True)

        vanished = sorted(set(indexed) - live)
        if not vanished:
            return

        self.stdout.write(self.style.WARNING(
            "  ATENCIÓN: %d archivo(s) indexado(s) ya no están en el "
            "cubo. No se toca ninguna fila: con el diseño de H29 esto "
            "no debería poder ocurrir, así que es un borrado que se "
            "saltó el panel o un error, y en ambos casos hace falta "
            "decisión humana." % len(vanished)
        ))
        for name in vanished[:20]:
            self.stdout.write("    - %s" % name)
        if len(vanished) > 20:
            self.stdout.write(
                "    ... y %d más." % (len(vanished) - 20)
            )
