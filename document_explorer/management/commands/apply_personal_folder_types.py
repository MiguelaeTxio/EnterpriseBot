# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/apply_personal_folder_types.py
"""
H30 (S67). Aplica document_type/domain_content_type/domain_object_id
via resolve_document_type_heuristic(), acotado EXCLUSIVAMENTE a
DOC. PERSONAL/PERSONAL/ -- nunca toca DOC. MAQUINAS, a diferencia de
run_fase_a_sweep.py (que recorre los dos dominios en el mismo paso).

Origen real: tras assign_media_types.py (S67), quedaron 39 archivos
detectados como "TIPO REAL, NO ES MEDIA" (SEG_SOCIAL,
CERTIFICADO_BANCARIO, BAJA_PERSONAL -- mayoria via el fix real del
bug /BAJAS/) sin escribir -- ese comando solo detecta, nunca escribe
tipos no-media. Este comando cierra ese hueco, con el mismo alcance
exacto que Miguel Angel pidio explicitamente esta sesion ("vamos a
centrarnos en la carpeta de personal, unica y exclusivamente").

Reutiliza sin modificar la cadena de resolucion de persona ya
validada (folder -> name -> sliding_window) y el manejo de dosier
(_dossier_types_already_filed / trash_dossier_entry) de
run_fase_a_sweep.py.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.heuristic_type_service import (
    resolve_document_type_heuristic,
)
from document_explorer.management.commands.calibrate_fase_a_keywords import (
    _strip_accents,
)
from document_explorer.management.commands.run_fase_a_sweep import (
    _build_person_name_index, _dossier_types_already_filed,
    _resolve_person_by_folder, _resolve_person_by_name,
    _resolve_person_by_sliding_window,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity

SCOPE_ROOT = "DOC. PERSONAL/PERSONAL/"


class Command(BaseCommand):
    help = (
        "H30 (S67) -- aplica tipo real (no media) resuelto por "
        "heuristica, acotado a DOC. PERSONAL/PERSONAL/. Dry-run por "
        "defecto, --apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        type_catalog = {
            t.code: t for t in DocumentTypeCatalog.objects.filter(is_active=True)
        }
        person_name_index = _build_person_name_index()

        qs = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez", entry_kind="FILE",
            document_type__isnull=True, deleted_at__isnull=True,
            purged_at__isnull=True,
            parent_path__startswith=SCOPE_ROOT,
        ).only("id", "name", "parent_path")

        stats = {
            "asignados": 0, "tipo_ok_dominio_pendiente": 0,
            "dosier_eliminado": 0, "dosier_sin_dividir_pendiente": 0,
            "sin_tipo_real": 0,
        }

        for entry in qs:
            name_upper = _strip_accents(entry.name).upper()
            code, dossier_pair = resolve_document_type_heuristic(
                entry, "PERSONAL", name_upper,
            )

            if dossier_pair:
                obj = _resolve_person_by_folder(entry)
                if not obj:
                    obj = _resolve_person_by_name(entry, person_name_index)
                if not obj:
                    obj = _resolve_person_by_sliding_window(
                        entry, person_name_index,
                    )
                if _dossier_types_already_filed(obj, person_ct, dossier_pair):
                    stats["dosier_eliminado"] += 1
                    self.stdout.write(
                        "DOSIER ELIMINADO (ya dividido en %s) [%s] %s"
                        % (sorted(dossier_pair), entry.parent_path, entry.name)
                    )
                    if apply_changes:
                        trash_dossier_entry(entry)
                else:
                    stats["dosier_sin_dividir_pendiente"] += 1
                    self.stdout.write(
                        "DOSIER SIN DIVIDIR, NO SE ELIMINA [%s] %s -> %s"
                        % (entry.parent_path, entry.name, sorted(dossier_pair))
                    )
                continue

            if not code:
                stats["sin_tipo_real"] += 1
                continue

            obj = _resolve_person_by_folder(entry)
            if not obj:
                obj = _resolve_person_by_name(entry, person_name_index)
            if not obj:
                obj = _resolve_person_by_sliding_window(entry, person_name_index)

            if not obj:
                stats["tipo_ok_dominio_pendiente"] += 1
                self.stdout.write(
                    "TIPO OK, DOMINIO PENDIENTE [%s] %s -> %s"
                    % (entry.parent_path, entry.name, code)
                )
                if apply_changes:
                    entry.document_type = type_catalog[code]
                    entry.save(update_fields=["document_type"])
                continue

            stats["asignados"] += 1
            self.stdout.write(
                "ASIGNADO persona=%s [%s] %s -> %s"
                % (obj.pk, entry.parent_path, entry.name, code)
            )
            if apply_changes:
                entry.document_type = type_catalog[code]
                entry.domain_content_type = person_ct
                entry.domain_object_id = obj.pk
                entry.save(update_fields=[
                    "document_type", "domain_content_type",
                    "domain_object_id",
                ])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
