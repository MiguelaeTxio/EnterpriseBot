# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/assign_media_types.py
"""
H30 (S67). Asigna IMAGEN/VIDEO/AUDIO (migracion 0050) por extension de
archivo real, a los archivos sin tipo de DOC. PERSONAL/PERSONAL/ --
nunca por contenido/OCR, la extension real de GCS ya es dato fiable
al 100% para esta decision (una foto de WhatsApp no necesita OCR para
saber que es una imagen).

Reutiliza sin modificar la misma cadena de resolucion de persona ya
validada en run_fase_a_sweep.py: _resolve_person_by_folder ->
_resolve_person_by_name -> _resolve_person_by_sliding_window. Mismo
desacoplo tipo/dominio de S54: si ningun resolutor encuentra la
persona, el tipo se guarda igual (con --apply), el dominio queda
pendiente para revision manual/Fase B.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.management.commands.run_fase_a_sweep import (
    _build_person_name_index, _resolve_person_by_folder,
    _resolve_person_by_name, _resolve_person_by_sliding_window,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity

SCOPE_ROOT = "DOC. PERSONAL/PERSONAL/"

EXT_TO_CODE = {
    "jpg": "IMAGEN", "jpeg": "IMAGEN", "png": "IMAGEN",
    "gif": "IMAGEN", "bmp": "IMAGEN", "webp": "IMAGEN",
    "mp4": "VIDEO", "mov": "VIDEO", "avi": "VIDEO",
    "mkv": "VIDEO", "3gp": "VIDEO", "wmv": "VIDEO",
    "mp3": "AUDIO", "wav": "AUDIO", "m4a": "AUDIO",
    "ogg": "AUDIO", "opus": "AUDIO", "amr": "AUDIO",
}


class Command(BaseCommand):
    help = (
        "H30 (S67) -- asigna IMAGEN/VIDEO/AUDIO por extension real a "
        "los archivos sin tipo de DOC. PERSONAL/PERSONAL/. Dry-run "
        "por defecto, usar --apply para escribir de verdad."
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
            t.code: t
            for t in DocumentTypeCatalog.objects.filter(
                code__in=("IMAGEN", "VIDEO", "AUDIO"), is_active=True,
            )
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
            "no_es_media": 0,
        }

        for entry in qs:
            ext = entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""
            code = EXT_TO_CODE.get(ext)
            if not code:
                stats["no_es_media"] += 1
                continue

            obj = _resolve_person_by_folder(entry)
            if not obj:
                obj = _resolve_person_by_name(entry, person_name_index)
            if not obj:
                obj = _resolve_person_by_sliding_window(
                    entry, person_name_index,
                )

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
