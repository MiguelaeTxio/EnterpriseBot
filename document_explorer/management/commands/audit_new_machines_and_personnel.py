# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/audit_new_machines_and_personnel.py
"""
Django management command: audit_new_machines_and_personnel.

Real gap Miguel Ángel identified (S043): the automatic-creation of
`MachineAsset`/`PersonIdentity` (`resolve_or_create_machine_asset()`/
`resolve_or_create_person_identity()`) only started existing in S042.
Everything classified BEFORE that -- the original bulk pass over
`DOC. MAQUINAS`/`DOC. PERSONAL` that seeded the whole index in the
first place -- never got a row created for machines/people that
didn't already exist in `fleet.MachineAsset`/`document_explorer.
PersonIdentity` at the time. Those files are correctly filed and
correctly named; the machine/person they belong to simply has no
database row. Miguel Ángel, verbatim: "esas máquinas no están en la
base de datos y no van a aparecer porque no se va a meter la
documentación, ya está metida."

Pure Python/SQL, deliberately -- **zero Gemini calls, zero GCS
contact.** Miguel Ángel, verbatim: "para esto no hacen falta llamadas
a Gemini, esto lo hacemos directamente en Python." Everything this
command needs is already in the index (`DocumentIndexEntry`) and in
`fleet.MachineAsset`/`document_explorer.PersonIdentity` -- this is
Phase 1 of a two-phase plan: find the real gaps first, cheaply;
deciding how to fill them (a second command, or Miguel Ángel uploading
the handful of real files for manual extraction to avoid a Gemini
call on "30 o 40 archivos") is deliberately out of scope here.

Machine side: reuses the EXACT SAME folder-name-to-code pattern
already trusted in production (`_FOLDER_MACHINE_CODE_RE`/
`_FOLDER_PLATE_RE`, `classification_service.resolve_machine_asset`) --
never a new, possibly-inconsistent heuristic. Every `FOLDER` row's own
`name` is tested; a distinct candidate code with no matching
`MachineAsset.code`/`plate` is exactly the same code a real document
arriving in that folder today would fail to resolve.

Personal side: a folder counts as a real, populated person folder when
it has at least one real FILE directly inside (never just more
subfolders, e.g. category folders like "OPERARIOS"/"BAJAS") -- found
with ONE grouped query over `parent_path`, never one query per
candidate folder. Subtracting `PersonIdentity.folder_path` (already
registered) leaves exactly the folders with real content and no
identity -- deliberately looser than `seed_person_identities`
(doesn't require a "DNI"-named file, doesn't confirm anything with
Gemini): this command's whole point is to be cheap and complete, not
to resolve every case with confidence -- that is the second phase.

---

Comando de gestión Django: audit_new_machines_and_personnel.

Hueco real identificado por Miguel Ángel (S043): el alta automática de
`MachineAsset`/`PersonIdentity` (`resolve_or_create_machine_asset()`/
`resolve_or_create_person_identity()`) solo existe desde S042. Todo lo
clasificado ANTES -- el barrido inicial sobre `DOC. MAQUINAS`/`DOC.
PERSONAL` que sembró el índice por primera vez -- nunca creó fila para
máquinas/personas que no existieran ya en `fleet.MachineAsset`/
`document_explorer.PersonIdentity` en aquel momento. Esos archivos
están bien archivados y bien nombrados; a la máquina o persona a la
que pertenecen simplemente le falta la fila de base de datos. Miguel
Ángel, verbatim: "esas máquinas no están en la base de datos y no van
a aparecer porque no se va a meter la documentación, ya está metida."

Python/SQL puro, a propósito -- **cero llamadas a Gemini, cero
contacto con GCS.** Miguel Ángel, verbatim: "para esto no hacen falta
llamadas a Gemini, esto lo hacemos directamente en Python." Todo lo
que necesita este comando ya está en el índice (`DocumentIndexEntry`)
y en `fleet.MachineAsset`/`document_explorer.PersonIdentity` -- esto
es la Fase 1 de un plan de dos fases: encontrar primero los huecos
reales, barato; decidir cómo rellenarlos (otro comando, o que Miguel
Ángel suba los pocos archivos reales para extracción manual y evitar
una llamada a Gemini sobre "30 o 40 archivos") queda fuera de alcance
aquí a propósito.

Lado máquina: reutiliza el MISMO patrón de nombre de carpeta a código
ya confiado en producción (`_FOLDER_MACHINE_CODE_RE`/
`_FOLDER_PLATE_RE`, `classification_service.resolve_machine_asset`) --
nunca una heurística nueva y potencialmente distinta. Se prueba el
`name` propio de cada fila `FOLDER`; un código candidato distinto sin
ningún `MachineAsset.code`/`plate` que lo iguale es exactamente el
mismo código que un documento real que llegara hoy a esa carpeta
fallaría en resolver.

Lado personal: una carpeta cuenta como carpeta de persona real y con
contenido cuando tiene al menos un ARCHIVO real directamente dentro
(nunca solo más subcarpetas, p. ej. carpetas de categoría como
"OPERARIOS"/"BAJAS") -- encontrado con UNA consulta agrupada sobre
`parent_path`, nunca una consulta por carpeta candidata. Restando
`PersonIdentity.folder_path` (ya registradas) queda exactamente el
conjunto de carpetas con contenido real y sin identidad -- a propósito
más laxo que `seed_person_identities` (no exige un archivo nombrado
"DNI", no confirma nada con Gemini): el objetivo entero de este
comando es ser barato y completo, no resolver cada caso con certeza --
eso es la segunda fase.
"""
import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.buckets import PRIMARY_BUCKET
from document_explorer.models import DocumentIndexEntry, PersonIdentity
from fleet.models import MachineAsset

# Mismos patrones exactos que classification_service.py -- nunca
# reinventados aquí. Si algún día cambian allí, deben cambiar aquí
# también (mismo criterio de "una sola fuente de verdad" que ya aplica
# a otras constantes compartidas del proyecto).
_FOLDER_MACHINE_CODE_RE = re.compile(r"^([A-Z]+-?\d+)")
_FOLDER_PLATE_RE = re.compile(r"(\d{4})[\s-]?([A-Z]{3})\b")


def _extract_machine_code(folder_name: str) -> str | None:
    """
    Same word-by-word / fallback-to-plate logic as
    `classification_service.resolve_machine_asset()`/
    `resolve_or_create_machine_asset()`, applied to a single folder's
    own `name` (one path segment) instead of scanning a whole
    `parent_path` -- collecting a match from every `FOLDER` row's own
    name already covers every segment of every real path in the tree,
    since each segment IS some folder's own name.

    ---

    Misma lógica palabra a palabra / respaldo a matrícula que
    `classification_service.resolve_machine_asset()`/
    `resolve_or_create_machine_asset()`, aplicada al `name` propio de
    una carpeta (un solo segmento de ruta) en vez de recorrer un
    `parent_path` completo -- recoger una coincidencia del `name`
    propio de cada fila `FOLDER` ya cubre cada segmento de cada ruta
    real del árbol, porque cada segmento ES el `name` propio de alguna
    carpeta.
    """
    upper = folder_name.strip().upper()
    for word in upper.split():
        match = _FOLDER_MACHINE_CODE_RE.match(word)
        if match:
            return match.group(1).replace("-", "")
    match = _FOLDER_PLATE_RE.search(upper)
    if match:
        return match.group(1) + match.group(2)
    return None


class Command(BaseCommand):
    help = (
        "Auditoría de solo lectura (sin Gemini, sin GCS): compara las "
        "carpetas ya indexadas de DOC. MAQUINAS/DOC. PERSONAL contra "
        "MachineAsset/PersonIdentity y lista qué máquinas y qué "
        "personas tienen documentación real archivada pero ninguna "
        "fila de base de datos -- caso real: alta automática solo "
        "existe desde S042, todo lo clasificado antes se quedó sin "
        "fila."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--root-machines", default="DOC. MAQUINAS",
            help="Carpeta raíz para el lado máquina.",
        )
        parser.add_argument(
            "--root-personal", default="DOC. PERSONAL",
            help="Carpeta raíz para el lado personal.",
        )
        parser.add_argument(
            "--skip-machines", action="store_true",
            help="Omite la auditoría de máquinas.",
        )
        parser.add_argument(
            "--skip-personal", action="store_true",
            help="Omite la auditoría de personal.",
        )
        parser.add_argument(
            "--show-paths", type=int, default=3,
            help=(
                "Cuántas rutas de ejemplo mostrar por código candidato "
                "de máquina (0 para ninguna)."
            ),
        )

    def handle(self, *args, **options):
        if not options["skip_machines"]:
            self._audit_machines(
                options["root_machines"], options["show_paths"],
            )
        if not options["skip_personal"]:
            self._audit_personal(options["root_personal"])

    def _audit_machines(self, root, show_paths):
        root = root.strip("/")
        folders = DocumentIndexEntry.objects.filter(
            bucket=PRIMARY_BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FOLDER,
            deleted_at__isnull=True, purged_at__isnull=True,
            blob_name__startswith=root + "/",
        ).only("blob_name", "name")

        candidates = defaultdict(list)
        for folder in folders.iterator():
            code = _extract_machine_code(folder.name)
            if code:
                candidates[code].append(folder.blob_name)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== MÁQUINAS -- %d código(s) candidato(s) distinto(s) "
            "bajo %s ===" % (len(candidates), root)
        ))

        missing = []
        for code in sorted(candidates):
            exists = MachineAsset.objects.filter(
                Q(code__iexact=code) | Q(plate__iexact=code),
            ).exists()
            if not exists:
                missing.append(code)

        for code in missing:
            paths = candidates[code]
            self.stdout.write(
                "  %s -- %d carpeta(s) real(es)" % (code, len(paths))
            )
            if show_paths:
                for path in paths[:show_paths]:
                    self.stdout.write("      %s" % path)
                if len(paths) > show_paths:
                    self.stdout.write(
                        "      ... y %d más"
                        % (len(paths) - show_paths)
                    )

        self.stdout.write(self.style.WARNING(
            "\n%d código(s) de máquina SIN MachineAsset real (de %d "
            "candidato(s) encontrado(s))." % (len(missing), len(candidates))
        ))

    def _audit_personal(self, root):
        root = root.strip("/")
        registered_paths = set(
            PersonIdentity.objects.values_list("folder_path", flat=True)
        )
        # Carpetas con al menos un archivo real directamente dentro --
        # una sola consulta agrupada, nunca una por carpeta candidata.
        parents_with_files = set(
            DocumentIndexEntry.objects.filter(
                bucket=PRIMARY_BUCKET,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True, purged_at__isnull=True,
                parent_path__startswith=root + "/",
            ).values_list("parent_path", flat=True).distinct()
        )
        missing = sorted(parents_with_files - registered_paths)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== PERSONAL -- carpetas con contenido bajo %s SIN "
            "PersonIdentity registrada ===" % root
        ))
        for path in missing:
            self.stdout.write("  %s" % path)

        self.stdout.write(self.style.WARNING(
            "\n%d carpeta(s) con contenido real y sin identidad "
            "registrada (de %d carpeta(s) con contenido en total)."
            % (len(missing), len(parents_with_files))
        ))
