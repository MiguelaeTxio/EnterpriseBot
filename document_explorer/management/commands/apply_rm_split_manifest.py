# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/apply_rm_split_manifest.py
"""
H30 (S59). Segunda mitad de la particion de dosieres RM -- lee el/los
manifiesto(s) JSONL generados por `split_rm_dossier_vm.py` en la VM
(un blob nuevo por linea de pagina resuelta, ya subido a GCS de
verdad) y hace la parte que SI necesita Django/el ORM real:

1. `index_writer.refresh_folder()` sobre cada carpeta destino tocada
   -- crea la fila `DocumentIndexEntry` nueva con `blob_name_hash`/
   `parent_path_hash` calculados correctamente, cadena de carpetas
   antecesoras asegurada, `total_size_bytes` propagado. Nunca
   reimplementado a mano por SQL (ver docstring de
   `split_rm_dossier_vm.py` para el porque).
2. Asigna `document_type`=RECONOCIMIENTO_MEDICO y, si la pagina
   resolvio por DNI, `domain_content_type`/`domain_object_id` a la
   `PersonIdentity` correspondiente.
3. Cuando TODAS las paginas de un dosier se procesaron con exito
   (`todas_paginas_ok` true en el manifiesto), manda el dosier
   original a papelera (`trash_dossier_entry()`, 4.12).

DRY-RUN POR DEFECTO. Con --apply escribe de verdad.
"""
import json

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.index_writer import refresh_folder
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)

BUCKET = "cgs_grupo_alvarez"


class Command(BaseCommand):
    help = (
        "H30 (S59) -- aplica el/los manifiesto(s) de "
        "split_rm_dossier_vm.py: indexa blobs nuevos, asigna tipo/"
        "dominio, manda a papelera el dosier original cuando "
        "corresponde. Dry-run por defecto, usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--files", nargs="+", required=True,
            help="Ruta(s) a los archivos rm_split_manifest_shard*.jsonl "
                 "subidos desde la VM.",
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        rm_type = DocumentTypeCatalog.objects.get(
            code="RECONOCIMIENTO_MEDICO",
        )
        person_ct = ContentType.objects.get_for_model(PersonIdentity)

        stats = {
            "dosieres_procesados": 0, "paginas_indexadas": 0,
            "paginas_error": 0, "dosieres_a_papelera": 0,
            "dosieres_sin_papelera": 0,
        }
        target_folders = set()
        registros = []

        for path in options["files"]:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    registros.append(json.loads(line))

        for registro in registros:
            if registro.get("status") == "ERROR":
                self.stdout.write(
                    "ERROR EN VM (dossier id=%s): %s"
                    % (registro.get("dossier_entry_id"),
                       registro.get("error"))
                )
                continue

            stats["dosieres_procesados"] += 1
            for pagina in registro["paginas"]:
                if pagina["status"] != "OK":
                    stats["paginas_error"] += 1
                    continue
                target_folders.add(
                    (pagina["target_folder"], pagina["filename"],
                     pagina.get("person_id"))
                )

        self.stdout.write(
            "--- %d dosieres en el manifiesto, %d paginas OK a indexar ---"
            % (stats["dosieres_procesados"], len(target_folders))
        )

        if apply_changes:
            folders_to_refresh = {f for f, _n, _p in target_folders}
            for folder in folders_to_refresh:
                refresh_folder(BUCKET, folder)

            for folder, filename, person_id in target_folders:
                entry = DocumentIndexEntry.objects.filter(
                    bucket=BUCKET, parent_path=folder, name=filename,
                ).first()
                if entry is None:
                    self.stdout.write(
                        "AVISO: no se encontro tras refresh_folder: "
                        "%s/%s" % (folder, filename)
                    )
                    continue
                entry.document_type = rm_type
                update_fields = ["document_type"]
                if person_id:
                    entry.domain_content_type = person_ct
                    entry.domain_object_id = person_id
                    update_fields += [
                        "domain_content_type", "domain_object_id",
                    ]
                entry.save(update_fields=update_fields)
                stats["paginas_indexadas"] += 1
                self.stdout.write("INDEXADO: %s/%s" % (folder, filename))

        for registro in registros:
            if registro.get("status") == "ERROR":
                continue
            if not registro.get("todas_paginas_ok"):
                stats["dosieres_sin_papelera"] += 1
                self.stdout.write(
                    "NO SE MANDA A PAPELERA (paginas sin resolver): "
                    "[%s] %s"
                    % (registro["dossier_parent_path"],
                       registro["dossier_name"])
                )
                continue
            stats["dosieres_a_papelera"] += 1
            if apply_changes:
                entry = DocumentIndexEntry.objects.get(
                    pk=registro["dossier_entry_id"],
                )
                if trash_dossier_entry(entry):
                    self.stdout.write(
                        "PAPELERA: %s" % registro["dossier_name"]
                    )

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
