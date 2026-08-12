# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/reconcile_machine_folders.py
"""
H30 (S49). Reconciliacion real de carpetas de maquina bajo
DOC. MAQUINAS contra fleet.MachineAsset -- responde a la incidencia
real de Miguel Angel en S49: "hay maquinaria que esta presente en el
directorio, pero no tiene reflejo en nuestra base de datos", detectada
con un caso real (el coche que conduce, matricula 7245GBM, YA estaba
en MachineAsset porque un documento suyo se habia clasificado antes --
pero cualquier carpeta cuyos archivos NUNCA hayan pasado por
clasificacion no dispara la creacion automatica, porque
resolve_or_create_machine_asset() solo se llama como efecto colateral
de clasificar un archivo).

Reutiliza EXACTAMENTE la misma logica de deteccion ya probada en
produccion (`_FOLDER_MACHINE_CODE_RE`/`_FOLDER_PLATE_RE`/
`resolve_machine_asset`/`resolve_or_create_machine_asset` de
`classification_service.py`) -- nunca reescribe el patron de codigo de
flota ni de matricula.

DRY-RUN POR DEFECTO. Sin `--apply`, solo informa que carpetas quedarian
sin resolver o se crearia una MachineAsset nueva -- no escribe nada.
Con `--apply`, llama a `resolve_or_create_machine_asset()` de verdad
(mismo mecanismo, mismos valores por defecto de empresa/seccion GRA,
pendientes de confirmar caso a caso, igual que ya ocurre en Fase A).
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from document_explorer.classification_service import (
    _FOLDER_MACHINE_CODE_RE, _FOLDER_PLATE_RE, resolve_machine_asset,
    resolve_or_create_machine_asset,
)
from document_explorer.models import DocumentIndexEntry

BUCKET = "cgs_grupo_alvarez"
MACHINE_ROOT = "DOC. MAQUINAS"


class Command(BaseCommand):
    help = (
        "H30 (S49) -- reconciliacion de carpetas de maquina bajo "
        "DOC. MAQUINAS contra fleet.MachineAsset. Dry-run por "
        "defecto, usar --apply para crear de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Crea MachineAsset de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        files = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).filter(parent_path=MACHINE_ROOT) | DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).filter(parent_path__startswith=MACHINE_ROOT + "/")

        # Un representante real por carpeta -- nunca hace falta mas de
        # un archivo para resolver/crear, y evita repetir la creacion
        # varias veces para la misma carpeta.
        representative_by_folder = {}
        for entry in files.only("id", "parent_path"):
            representative_by_folder.setdefault(entry.parent_path, entry)

        stats = {
            "ya_resuelta": 0, "candidata_creacion": 0,
            "sin_forma_de_codigo": 0,
        }
        created = []

        for folder, entry in sorted(representative_by_folder.items()):
            existing = resolve_machine_asset(entry)
            if existing:
                stats["ya_resuelta"] += 1
                continue

            # Solo para informar en dry-run, sin duplicar la logica
            # real de creacion -- misma forma exacta que usa
            # resolve_or_create_machine_asset() internamente.
            has_code_shape = any(
                _FOLDER_MACHINE_CODE_RE.match(word)
                for segment in folder.split("/")
                for word in segment.strip().split()
            )
            has_plate_shape = any(
                _FOLDER_PLATE_RE.search(segment.strip().upper())
                for segment in folder.split("/")
            )

            if not has_code_shape and not has_plate_shape:
                stats["sin_forma_de_codigo"] += 1
                continue

            stats["candidata_creacion"] += 1
            if apply_changes:
                result = {}
                asset = resolve_or_create_machine_asset(entry, result)
                if asset:
                    created.append((folder, asset.code, asset.pk))
                    self.stdout.write(
                        "CREADA  [%s] -> MachineAsset %s (pk=%d)"
                        % (folder, asset.code, asset.pk)
                    )
            else:
                self.stdout.write(
                    "CANDIDATA A CREAR  [%s]" % folder
                )

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self.stdout.write(
            "    carpetas de maquina totales: %d"
            % len(representative_by_folder)
        )
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
        if apply_changes:
            self.stdout.write("    creadas de verdad: %d" % len(created))
