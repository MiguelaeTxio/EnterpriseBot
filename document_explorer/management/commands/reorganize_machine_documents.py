# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/reorganize_machine_documents.py
"""
H30 (S119), roadmap item 3 -- ACTIVAS/INACTIVAS folders and canonical
names for machine documents.
---
H30 (S119), punto 3 de la hoja de ruta -- carpetas ACTIVAS/INACTIVAS y
renombrado canónico de los documentos de MÁQUINAS. Decisiones de Miguel
Ángel en S119:

- 1a: `DOC. MAQUINAS/ACTIVAS/{FAMILIA}/{CÓDIGO}/` y
  `DOC. MAQUINAS/INACTIVAS/{CÓDIGO}/` (análogo de Personal S99). Todos
  los documentos vivos de cada máquina aterrizan directamente en su
  carpeta (`machine_folder_service`), sea cual sea su ruta histórica.
  Las inactivas solo se mueven, no se renombran.
- 2a: nombre `{CÓDIGO}_{TIPO}_{AAAAMMDD}[_N]` con caducidad, si no
  emisión, si no la fecha ficticia 2021-01-01 solo en el nombre
  (`classification_service.apply_machine_canonical_rename`).

Solo virtual: `parent_path`/`name` en BD, nunca `blob_name` ni GCS. En
dry-run nunca se llama a `move_entries()` (siempre escribe); el
renombrado se simula en la carpeta destino con un dict de nombres
reservados, así los ordinales del dry-run son los del --apply.

DRY-RUN por defecto; --apply escribe. Log propio (pantalla y archivo a
la vez, com-standards 0bis) con heartbeat y ETA.
"""
import datetime
import time
from collections import Counter

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import (
    apply_machine_canonical_rename,
)
from document_explorer.machine_folder_service import (
    machine_entries_to_move,
    machine_folder_for,
    outside_intake_q,
)
from document_explorer.models import DocumentIndexEntry
from document_explorer.move_service import move_entries
from fleet.models import MachineAsset

BUCKET = "cgs_grupo_alvarez"
# Convención de Miguel Ángel (Personal S98): festivo nacional, ningún
# documento real se emite ni vence ese día; solo va en el nombre.
FICTITIOUS_DATE = datetime.date(2021, 1, 1)


class Command(BaseCommand):
    help = (
        "H30 (S119) -- punto 3: carpetas ACTIVAS/INACTIVAS y "
        "renombrado canónico de máquinas. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, 0bis).",
        )

    def _log(self, message):
        self._log_plain(
            "[%s] %s" % (
                datetime.datetime.now().strftime("%H:%M:%S"), message,
            ),
        )

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"])
        finally:
            self._log_handle.close()

    def _run(self, apply_changes):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        machines = list(MachineAsset.objects.order_by("code"))
        total = len(machines)
        self._log(
            "PUNTO 3 -- MODO: %s -- %d maquinas (%d activas)" % (
                "APLICAR (escribe)" if apply_changes
                else "DRY-RUN (no escribe nada)",
                total, sum(1 for m in machines if m.is_active),
            )
        )
        stats = Counter()
        pending = []
        examples = []
        start_time = datetime.datetime.now()
        last_beat = time.monotonic()
        for index, asset in enumerate(machines, start=1):
            self._process_machine(
                asset, machine_ct, apply_changes, stats, pending, examples,
            )
            if index % 25 == 0 or time.monotonic() - last_beat >= 30 \
                    or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.datetime.now() - start_time
                           ).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. "
                    "%s) -- movidos=%d, renombrados=%d, sin_renombrar=%d"
                    % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60),
                        (datetime.datetime.now()
                         + datetime.timedelta(seconds=eta_seg)
                         ).strftime("%H:%M:%S"),
                        stats["movidos"], stats["renombrados"],
                        len(pending),
                    )
                )
        self._summary(apply_changes, stats, pending, examples)

    def _process_machine(self, asset, machine_ct, apply_changes, stats,
                         pending, examples):
        """
        Move one machine's documents and, if active, rename them.
        ---
        Mueve los documentos de una máquina a su carpeta y, si está
        activa, los renombra en la carpeta destino.
        """
        target, to_move = machine_entries_to_move(asset)
        if to_move:
            stats["maquinas_con_movimientos"] += 1
            stats["movidos"] += len(to_move)
            if apply_changes:
                move_entries(to_move, target)
        if not asset.is_active:
            return
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            domain_content_type=machine_ct, domain_object_id=asset.pk,
        ).filter(outside_intake_q()).select_related(
            "document_type",
        ).order_by("id"))
        folder = machine_folder_for(asset)
        reserved = {}
        for entry in entries:
            # En dry-run el documento sigue en su carpeta vieja: se
            # simula (sin guardar) que ya está en la de su máquina.
            entry.parent_path = folder
            reserved[(entry.bucket, folder, entry.name)] = entry.pk
        for entry in entries:
            result = apply_machine_canonical_rename(
                entry, asset, fictitious_date=FICTITIOUS_DATE,
                apply_changes=apply_changes, reserved_names=reserved,
            )
            if result["reason"]:
                pending.append("id=%d %s | %s | %s" % (
                    entry.id, asset.code, entry.name, result["reason"],
                ))
                continue
            if result["renamed"]:
                stats["renombrados"] += 1
                if len(examples) < 40:
                    examples.append("id=%d %s | %s -> %s" % (
                        entry.id, asset.code, entry.name, result["new_name"],
                    ))
            else:
                stats["ya_canonicos"] += 1

    def _summary(self, apply_changes, stats, pending, examples):
        self._log_plain("=== RESUMEN PUNTO 3 (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key in ("maquinas_con_movimientos", "movidos", "renombrados",
                    "ya_canonicos"):
            self._log_plain("    %s: %d" % (key, stats[key]))
        self._log_plain("    sin_renombrar: %d" % len(pending))
        self._log_plain("--- EJEMPLOS DE RENOMBRADO (hasta 40) ---")
        for line in examples:
            self._log_plain("      %s" % line)
        self._log_plain("--- SIN RENOMBRAR, POR ID ---")
        for line in pending:
            self._log_plain("      %s" % line)
