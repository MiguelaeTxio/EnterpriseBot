# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/seed_person_identities.py
"""
Django management command: seed_person_identities.

Seeds `PersonIdentity` (H29, S040) -- the DNI -> real DOC. PERSONAL
folder index the future quarantine consumer needs to relocate
personal-domain files with certainty instead of guessing from a name
that (per Hallazgo 5 of the H28 annex) can appear written eight
different ways.

Two-stage, on purpose, to avoid a real Gemini call on every single
file in DOC. PERSONAL (~21.500 files, real cost):

1. Cheap pre-filter: `DocumentIndexEntry.name` containing "DNI"
   (case-insensitive) -- a real, structural pattern already confirmed
   against the actual corpus (Hallazgo 2 of the H28 annex lists `DNI`
   as one of the closed personal vocabulary types, and the sample
   Miguel Ángel uploaded in S040 had it in the filename every time).
2. Real classification (`classification_service.classify_entry`,
   domain=PERSONAL) only on that shortlist -- confirms the type really
   is `DNI` (never trusts the filename alone) and extracts
   `dni_hint`/name hints from the actual document content.

A person's own folder is assumed to be the DNI file's own
`parent_path` -- verified against the real corpus (H29 3.31): every
sampled person's documents, including their DNI, sit directly in that
person's own folder, never nested deeper.

Read/write to `PersonIdentity` only -- never touches
`DocumentIndexEntry.name`/`parent_path` (no renaming, no relocation
here; that is `apply_classification()`'s job, over quarantine files,
once this index exists to resolve against).

---

Comando de gestión Django: seed_person_identities.

Siembra `PersonIdentity` (H29, S040) -- el índice DNI -> carpeta real
de DOC. PERSONAL que necesita el futuro consumidor de cuarentena para
reubicar archivos de dominio personal con certeza, en vez de adivinar
por un nombre que (según el Hallazgo 5 del anexo H28) puede aparecer
escrito de ocho formas distintas.

Dos fases, a propósito, para no lanzar una llamada real a Gemini sobre
cada archivo de DOC. PERSONAL (~21.500 archivos, coste real):

1. Filtro barato: `DocumentIndexEntry.name` que contenga "DNI" (sin
   distinguir mayúsculas) -- un patrón real, estructural, ya
   confirmado contra el corpus real (el Hallazgo 2 del anexo H28 lista
   `DNI` como uno de los tipos cerrados del vocabulario de personal, y
   la muestra que subió Miguel Ángel en S040 lo llevaba en el nombre
   de archivo siempre).
2. Clasificación real (`classification_service.classify_entry`,
   domain=PERSONAL) solo sobre esa preselección -- confirma que el
   tipo es de verdad `DNI` (nunca se fía solo del nombre de archivo) y
   extrae `dni_hint`/pistas de nombre del propio contenido.

Se asume que la carpeta propia de una persona es el `parent_path` del
propio archivo de DNI -- verificado contra el corpus real (anexo H29,
3.31): los documentos de cada persona de la muestra, incluido su DNI,
viven directamente en su propia carpeta, nunca anidados más adentro.

Solo lee/escribe `PersonIdentity` -- nunca toca
`DocumentIndexEntry.name`/`parent_path` (aquí no se renombra ni se
reubica nada; eso es trabajo de `apply_classification()`, sobre
archivos de cuarentena, una vez que este índice exista para resolver
contra él.
"""
import re

from django.core.management.base import BaseCommand

from document_explorer import classification_service
from document_explorer.buckets import PRIMARY_BUCKET
from document_explorer.models import DocumentIndexEntry, PersonIdentity

_DNI_NORMALIZE_RE = re.compile(r"[^A-Z0-9]")


def _normalize_dni(raw_dni: str) -> str:
    return _DNI_NORMALIZE_RE.sub("", raw_dni.upper())


class Command(BaseCommand):
    help = (
        "Siembra PersonIdentity clasificando de verdad los candidatos a "
        "DNI ya existentes dentro de DOC. PERSONAL (filtro barato por "
        "nombre + confirmación real con Gemini)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--root",
            default="DOC. PERSONAL",
            help="Carpeta raíz dentro del cubo donde buscar candidatos.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Tope de candidatos a clasificar en esta pasada (opcional).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo lista los candidatos encontrados, sin llamar a Gemini.",
        )

    def handle(self, *args, **options):
        root = options["root"].strip("/")
        candidates = (
            DocumentIndexEntry.objects.filter(
                bucket=PRIMARY_BUCKET,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True,
                purged_at__isnull=True,
                blob_name__startswith=root + "/",
                name__icontains="DNI",
            )
            .order_by("blob_name")
        )
        if options["limit"]:
            candidates = candidates[: options["limit"]]
        candidates = list(candidates)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d candidato(s) a DNI bajo %s ===" % (len(candidates), root)
        ))
        if options["dry_run"]:
            for entry in candidates:
                self.stdout.write("  " + entry.blob_name)
            self.stdout.write(self.style.WARNING(
                "Dry-run: no se ha llamado a Gemini ni escrito nada."
            ))
            return

        created_count = 0
        updated_count = 0
        rejected_count = 0
        for entry in candidates:
            result = classification_service.classify_entry(entry, "PERSONAL")
            if "error" in result:
                self.stdout.write(self.style.WARNING(
                    "  Fallo clasificando %s: %s"
                    % (entry.blob_name, result["error"])
                ))
                rejected_count += 1
                continue

            if result.get("document_type_code") != "DNI":
                self.stdout.write(
                    "  Descartado (no es DNI de verdad, es %s): %s"
                    % (result.get("document_type_code", "?"), entry.blob_name)
                )
                rejected_count += 1
                continue

            dni_raw = (result.get("dni_hint") or "").strip()
            first_surname = (result.get("first_surname_hint") or "").strip()
            given_name = (result.get("given_name_hint") or "").strip()
            if not dni_raw or not first_surname or not given_name:
                self.stdout.write(self.style.WARNING(
                    "  Descartado (DNI confirmado pero faltan datos para "
                    "identificar a la persona): %s" % entry.blob_name
                ))
                rejected_count += 1
                continue

            # Hallazgo real S040 (documento "ADOLFO DNI.pdf",
            # perfectamente legible, confirmado por Miguel Ángel con 5
            # documentos más de la misma persona): Gemini puede leer
            # mal un dígito incluso en un documento claro. La letra de
            # control real del DNI lo detecta gratis, sin abrir nada.
            if not classification_service.is_valid_spanish_dni(dni_raw):
                self.stdout.write(self.style.WARNING(
                    "  Descartado (DNI leído no pasa la letra de "
                    "control -- probable lectura errónea de Gemini, "
                    "%s): %s" % (dni_raw, entry.blob_name)
                ))
                rejected_count += 1
                continue

            dni = _normalize_dni(dni_raw)
            second_surname = (result.get("second_surname_hint") or "").strip()

            # Fallo real detectado en la primera prueba controlada
            # (S040): un mismo DNI puede aparecer varias veces (el
            # actual y viejos escaneos guardados en una subcarpeta
            # "OBSOLETO"/"OBSOLETOS"), y update_or_create sobrescribía
            # la carpeta cada vez que encontraba otro -- si el último
            # procesado era el obsoleto, la identidad terminaba
            # apuntando a la carpeta equivocada. Regla: una carpeta
            # obsoleta nunca sobrescribe una carpeta ya buena; entre
            # dos candidatas igual de buenas (o igual de obsoletas), se
            # conserva la primera encontrada.
            existing = PersonIdentity.objects.filter(dni=dni).first()
            new_is_obsolete = "obsoleto" in entry.parent_path.lower()
            if existing is None:
                should_update_folder = True
            elif "obsoleto" in existing.folder_path.lower() and not new_is_obsolete:
                should_update_folder = True  # mejora: de obsoleta a buena
            else:
                should_update_folder = False  # conserva lo que ya había

            defaults = {
                "first_surname": first_surname,
                "second_surname": second_surname,
                "given_name": given_name,
            }
            if should_update_folder:
                defaults["folder_path"] = entry.parent_path
                defaults["source_entry"] = entry

            _, created = PersonIdentity.objects.update_or_create(
                dni=dni, defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
            self.stdout.write(self.style.SUCCESS(
                "  %s -- %s %s %s -- %s%s"
                % (
                    dni, first_surname, second_surname, given_name,
                    entry.parent_path if should_update_folder
                    else "(carpeta conservada: %s)" % (
                        existing.folder_path if existing else "?"
                    ),
                    "" if should_update_folder else " -- descartada por obsoleta",
                )
            ))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n%d identidad(es) nueva(s), %d actualizada(s), %d "
            "descartada(s)." % (created_count, updated_count, rejected_count)
        ))
