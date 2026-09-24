# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/retype_person_types_on_machines.py
"""
H30 (S117) -- punto 4 de la hoja de ruta ("cajones de sastre"):
documentos asignados a una MÁQUINA con un tipo documental de PERSONA.

Medido con datos reales (consulta de solo lectura S117): 12 documentos
-- 10 BAJA_PERSONAL en "DOC. MAQUINAS/PLATAFORMAS (Z)/BAJAS/..."
(plataformas vendidas: IEDMT, revisiones, certificados de aislamiento),
tipados así por la regla de carpeta "/BAJAS/" (corregida en origen en
heuristic_type_service.folder_based_type), 1 ALTA y 1
RECONOCIMIENTO_MEDICO que por su nombre no lo son.

Para cada uno se vuelve a aplicar la heurística de MÁQUINAS a su nombre
(ya sin la regla de carpeta de persona): si da un tipo de máquina, se
le pone; si no, queda SIN TIPO (conservando su máquina) para la Fase 3
(OCR) -- nunca se mantiene un tipo de persona falso ni se inventa otro.

DRY-RUN por defecto; --apply escribe. Nunca toca GCS (4.12). Log propio
(com-standards 0bis/0ter).
"""
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.heuristic_type_service import (
    folder_based_type, resolve_document_type_heuristic,
)
from document_explorer.management.commands.calibrate_fase_a_keywords import (
    _strip_accents,
)
from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from fleet.models import MachineAsset


class Command(BaseCommand):
    help = (
        "H30 (S117) -- retipa documentos de maquina con tipo de persona. "
        "Dry-run por defecto, --apply para escribir."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"])
        finally:
            self._log_handle.close()

    def _run(self, apply_changes):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        catalog = {t.code: t for t in DocumentTypeCatalog.objects.filter(is_active=True)}
        entries = list(
            DocumentIndexEntry.objects.filter(
                entry_kind=DocumentIndexEntry.KIND_FILE,
                domain_content_type=machine_ct,
                document_type__domain="PERSONAL",
                deleted_at__isnull=True, purged_at__isnull=True,
            ).select_related("document_type")
        )
        self._log(
            "MODO: %s -- %d documentos de maquina con tipo de persona"
            % ("APLICAR (escribe)" if apply_changes else "DRY-RUN (no escribe nada)", len(entries))
        )
        retyped = untyped = 0
        for index, entry in enumerate(entries, start=1):
            name_upper = _strip_accents(entry.name).upper()
            code = folder_based_type(entry, "MACHINE")
            if not code:
                code, dossier_pair = resolve_document_type_heuristic(
                    entry, "MACHINE", name_upper,
                )
                if dossier_pair:
                    code = None
            new_type = catalog.get(code) if code else None
            if new_type and new_type.domain not in ("MACHINE", "BOTH"):
                new_type = None
            self._log(
                "[%d/%d] %s -> %s  [%s] %s"
                % (index, len(entries), entry.document_type.code,
                   new_type.code if new_type else "SIN TIPO (Fase 3 OCR)",
                   entry.parent_path, entry.name)
            )
            if new_type:
                retyped += 1
            else:
                untyped += 1
            if apply_changes:
                entry.document_type = new_type
                entry.save(update_fields=["document_type"])
        self._log("=== RESUMEN (%s) ===" % ("APLICADO" if apply_changes else "DRY-RUN, nada escrito"))
        self._log("    retipados a un tipo de maquina: %d" % retyped)
        self._log("    sin tipo (conservan su maquina, Fase 3 OCR): %d" % untyped)
