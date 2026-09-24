# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/run_fase2_assign_machines.py
"""
H30 (S117) -- FASE 2 DE MÁQUINAS: documentos de DOC. MAQUINAS que YA
tienen tipo documental pero ninguna máquina asignada (384 al empezar).

Causa real, vista con datos (consulta de solo lectura S117, agrupada
por carpeta): resolve_machine_asset() solo reconocía palabras que
EMPIEZAN como un código de flota (A-29, Z131), así que no resolvía
- carpetas nombradas por matrícula ("VEHICULOS DE EMPRESA/DOCUMENT
  3968HWN (PEUGEOT 208 NUÑEZ)", "DOCUMENT 0230 KWB ...") -- los turismos
  llevan la matrícula como código en Centros de gasto;
- códigos entre paréntesis ("(X-01)");
- carpetas genéricas (GESTORIA VEHICULOS, OBSOLETO de una familia,
  PROPUESTA SEGURO...) donde la máquina solo aparece en el nombre del
  archivo.
classification_service ya cubre los tres casos (_machine_from_text,
resolve_machine_asset_with_filename). Este comando los aplica.

NUNCA crea máquinas: las que no encuentra se listan con su carpeta
para decidir con Miguel Ángel/Yolanda. Deja FUERA las eslingas
(ESLINGAS ...): accesorios de elevación, punto 9 de la hoja de ruta de
H30, pendiente de diseño con Miguel Ángel.

H30 (S118), punto 7 de la hoja de ruta: --untyped aplica la misma
resolución por ruta y nombre a los documentos SIN TIPO y sin máquina
(solo PDF e imágenes, los candidatos a OCR) -- paso gratuito previo al
OCR, para que el OCR se lance solo sobre documentos de máquinas ACTIVAS
y nunca sobre los de máquinas de baja. El resumen separa activas e
inactivas.

DRY-RUN por defecto; --apply escribe domain_content_type/
domain_object_id. Nunca toca GCS (4.12). Log propio con heartbeat y
ETA (com-standards 0bis/0ter).
"""
import time
from collections import Counter
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import (
    resolve_machine_asset_with_filename,
)
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset

BUCKET = "cgs_grupo_alvarez"
ROOT = "DOC. MAQUINAS/"
OUT_OF_SCOPE_PREFIXES = ("DOC. MAQUINAS/ESLINGAS",)
OCR_CANDIDATE_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")
# S118 -- permisos de transporte que cubren VARIOS vehículos a la vez
# ("p14 g02 g03.pdf"): asignarlos al primer código sería falso.
UNTYPED_OUT_OF_SCOPE_PREFIXES = ("DOC. MAQUINAS/PERMISOS ESPECIALES",)


class Command(BaseCommand):
    help = (
        "H30 (S117) -- Fase 2 de MAQUINAS: asigna maquina a documentos "
        "con tipo y sin maquina. Dry-run por defecto, --apply para escribir."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--untyped", action="store_true",
            help="Documentos SIN tipo (PDF e imagenes) en vez de con tipo.",
        )
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, com-standards 0bis).",
        )

    def _log(self, message):
        self._log_plain("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"], options["untyped"])
        finally:
            self._log_handle.close()

    def _run(self, apply_changes, untyped=False):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        qs = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__isnull=untyped, domain_object_id__isnull=True,
            parent_path__startswith=ROOT,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).select_related("document_type")
        entries = [
            e for e in qs
            if not e.parent_path.upper().startswith(OUT_OF_SCOPE_PREFIXES)
            and (
                not untyped
                or (
                    e.name.lower().endswith(OCR_CANDIDATE_EXTENSIONS)
                    and not e.parent_path.upper().startswith(
                        UNTYPED_OUT_OF_SCOPE_PREFIXES,
                    )
                )
            )
        ]
        excluded = qs.count() - len(entries)
        total = len(entries)
        self._log(
            "MODO: %s -- %d documentos %s y sin maquina en DOC. "
            "MAQUINAS (%d fuera: eslingas, punto 9 de la hoja de ruta%s)"
            % (
                "APLICAR (escribe)" if apply_changes
                else "DRY-RUN (no escribe nada, no crea maquinas)",
                total,
                "SIN TIPO (PDF e imagenes)" if untyped else "con tipo",
                excluded,
                ", extensiones no OCR y PERMISOS ESPECIALES"
                if untyped else "",
            )
        )

        assigned = 0
        assigned_active = 0
        by_machine = Counter()
        unresolved_by_folder = Counter()
        unresolved_examples = {}
        start_time = datetime.now()
        last_beat = time.monotonic()

        for index, entry in enumerate(entries, start=1):
            asset = resolve_machine_asset_with_filename(entry)
            type_code = (
                entry.document_type.code if entry.document_type_id
                else "SIN TIPO"
            )
            if asset:
                assigned += 1
                if asset.is_active:
                    assigned_active += 1
                by_machine[(asset.code, asset.is_active)] += 1
                self._log(
                    "ASIGNADO -> %s (%s)  [%s] %s (%s)"
                    % (asset.code,
                       "activa" if asset.is_active else "INACTIVA",
                       entry.parent_path, entry.name, type_code)
                )
                if apply_changes:
                    entry.domain_content_type = machine_ct
                    entry.domain_object_id = asset.pk
                    entry.save(update_fields=[
                        "domain_content_type", "domain_object_id",
                    ])
            else:
                unresolved_by_folder[entry.parent_path] += 1
                unresolved_examples.setdefault(entry.parent_path, []).append(
                    "%s (%s)" % (entry.name, type_code)
                )

            if index % 25 == 0 or time.monotonic() - last_beat >= 30 or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                hora_fin = (
                    datetime.now() + timedelta(seconds=eta_seg)
                ).strftime("%H:%M:%S")
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                    "-- asignados=%d (activas=%d), sin_maquina=%d" % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                        assigned, assigned_active, index - assigned,
                    )
                )

        self._log_plain("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log_plain("    documentos revisados: %d" % total)
        self._log_plain("    asignados a su maquina: %d" % assigned)
        self._log_plain("      - a maquina ACTIVA: %d" % assigned_active)
        self._log_plain("      - a maquina INACTIVA: %d" % (
            assigned - assigned_active,
        ))
        self._log_plain("    sin maquina reconocible: %d" % (total - assigned))
        self._log_plain("    fuera de alcance (eslingas, punto 9%s): %d" % (
            "; extensiones no OCR y PERMISOS ESPECIALES" if untyped else "",
            excluded,
        ))
        self._log_plain("--- Asignados por maquina ---")
        for (code, is_active), count in sorted(by_machine.items()):
            self._log_plain("    %s%s: %d" % (
                code, "" if is_active else " (INACTIVA)", count,
            ))
        self._log_plain("--- SIN MAQUINA, por carpeta (TODOS, con sus archivos) ---")
        for folder, count in unresolved_by_folder.most_common():
            self._log_plain("  %4d | %s" % (count, folder))
            for example in unresolved_examples[folder]:
                self._log_plain("         - %s" % example)
