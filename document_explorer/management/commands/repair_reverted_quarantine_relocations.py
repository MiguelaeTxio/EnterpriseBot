# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/repair_reverted_quarantine_relocations.py
"""
Django management command: repair_reverted_quarantine_relocations.

H29, S041 -- reparación puntual del daño real causado por el bug de
`persist_rows()` corregido en el commit `e27fd6a` (ver directriz 4.12
del documento maestro): antes de ese fix, `refresh_quarantine_index_
task` (cada hora) reescribía en silencio `parent_path`/`name` de
cualquier archivo de cuarentena que ya hubiera sido reubicado de
verdad por `consume_quarantine_task`, devolviéndolo a `_CUARENTENA/`
sin que nadie lo supiera. Con el bug ya corregido esto no puede volver
a pasar, pero deja detrás un backlog real: archivos que HOY siguen en
cuarentena pero que YA tenían una decisión correcta (reubicar o
enviar a papelera por ser dossier) tomada y registrada en su propio
historial (`DataOperationLogEntry`), simplemente deshecha después.

Miguel Ángel, al decidir cómo seguir: "Reparar" -- en vez de esperar
a que la Always-on Task los vuelva a procesar uno a uno (otra llamada
real a Gemini por archivo, con coste y tiempo reales), este comando
reaplica directamente la ÚLTIMA decisión real ya tomada para cada
archivo, sin volver a llamar a Gemini.

Por cada archivo que hoy sigue en cuarentena:
1. Busca en su propio `DataOperationLogEntry` el último
   `ACTION_RELOCATED` o `ACTION_TRASHED` (por orden de `id`, el más
   reciente).
2. Si es `ACTION_RELOCATED`: reaplica el mismo `name`/`parent_path`
   que quedaron registrados entonces, vía `move_service.move_entry()`
   (mismo mecanismo de siempre, con su propia protección de
   colisiones -- puede que el destino ya no esté libre con ese nombre
   exacto si algo cambió mientras tanto).
2. Si es `ACTION_TRASHED`: reaplica el envío a la papelera del
   administrador vía `classification_service.trash_dossier_entry()`.
3. Si no hay ningún `ACTION_RELOCATED`/`ACTION_TRASHED` en su
   historial (nunca se llegó a resolver antes, o solo hay
   `ACTION_NOT_CLASSIFIED`), se deja intacto -- la Always-on Task ya
   lo recogerá en su próxima pasada normal, con Gemini, como
   cualquier archivo nuevo.

Nunca toca GCS (directriz 4.12) -- pura escritura de índice, igual
que todo lo demás en este módulo.

Por defecto ESCRIBE de verdad (mismo criterio que `seed_person_
identities`/`seed_document_index`) -- usar `--dry-run` para ver el
informe sin escribir nada.

Uso:
    python -m dotenv run python manage.py \
        repair_reverted_quarantine_relocations --bucket cgs_grupo_alvarez
    python -m dotenv run python manage.py \
        repair_reverted_quarantine_relocations --bucket cgs_grupo_alvarez \
        --dry-run

---

Comando de gestión Django: repair_reverted_quarantine_relocations.

H29, S041 -- reparación puntual del daño real causado por el bug de
`persist_rows()` corregido en el commit `e27fd6a` (ver directriz 4.12
del documento maestro): antes de ese fix, `refresh_quarantine_index_
task` (cada hora) reescribía en silencio `parent_path`/`name` de
cualquier archivo de cuarentena que ya hubiera sido reubicado de
verdad por `consume_quarantine_task`, devolviéndolo a `_CUARENTENA/`
sin que nadie lo supiera. Con el bug ya corregido esto no puede volver
a pasar, pero deja detrás un backlog real: archivos que HOY siguen en
cuarentena pero que YA tenían una decisión correcta (reubicar o
enviar a papelera por ser dossier) tomada y registrada en su propio
historial (`DataOperationLogEntry`), simplemente deshecha después.

Miguel Ángel, al decidir cómo seguir: "Reparar" -- en vez de esperar
a que la Always-on Task los vuelva a procesar uno a uno (otra llamada
real a Gemini por archivo, con coste y tiempo reales), este comando
reaplica directamente la ÚLTIMA decisión real ya tomada para cada
archivo, sin volver a llamar a Gemini.

Nunca toca GCS (directriz 4.12) -- pura escritura de índice, igual
que todo lo demás en este módulo.

Por defecto ESCRIBE de verdad (mismo criterio que `seed_person_
identities`/`seed_document_index`) -- usar `--dry-run` para ver el
informe sin escribir nada.
"""
from django.core.management.base import BaseCommand

from document_explorer.buckets import QUARANTINE_PREFIX
from document_explorer.classification_service import trash_dossier_entry
from document_explorer.models import DataOperationLogEntry, DocumentIndexEntry
from document_explorer.move_service import move_entry


class Command(BaseCommand):
    help = (
        "Reaplica, sin volver a llamar a Gemini, la última decisión "
        "real (reubicar o enviar a papelera) ya registrada en el "
        "historial de cada archivo que hoy sigue en cuarentena pese a "
        "haber sido resuelto antes -- reparación del daño causado por "
        "el bug de persist_rows() (commit e27fd6a, directriz 4.12)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            required=True,
            help="Cubo indexado a reparar (obligatorio).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo informa qué se repararía, sin escribir nada.",
        )

    def handle(self, *args, **options):
        bucket = options["bucket"]
        dry_run = options["dry_run"]

        pending = list(
            DocumentIndexEntry.objects.filter(
                bucket=bucket,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True,
                purged_at__isnull=True,
                parent_path__startswith=QUARANTINE_PREFIX,
            ).order_by("indexed_at")
        )
        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d pendiente(s) en cuarentena a revisar (bucket=%s) "
            "===" % (len(pending), bucket)
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "Dry-run: no se escribirá nada."
            ))

        relocated = 0
        trashed = 0
        skipped = 0

        for entry in pending:
            last = (
                DataOperationLogEntry.objects.filter(
                    index_entry_id=entry.pk,
                    action__in=(
                        DataOperationLogEntry.ACTION_RELOCATED,
                        DataOperationLogEntry.ACTION_TRASHED,
                    ),
                )
                .order_by("-id")
                .first()
            )
            if last is None:
                skipped += 1
                continue

            if last.action == DataOperationLogEntry.ACTION_RELOCATED:
                self.stdout.write(
                    "[REUBICAR] %s/%s -> %s/%s" % (
                        entry.parent_path, entry.name,
                        last.parent_path, last.name,
                    )
                )
                if not dry_run:
                    entry.name = last.name
                    move_entry(entry, last.parent_path)
                relocated += 1
            else:
                self.stdout.write(
                    "[PAPELERA] %s/%s (dossier ya identificado antes)"
                    % (entry.parent_path, entry.name)
                )
                if not dry_run:
                    trash_dossier_entry(entry)
                trashed += 1

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== RESUMEN ==="))
        self.stdout.write("Reubicados: %d" % relocated)
        self.stdout.write("Enviados a papelera (dossier): %d" % trashed)
        self.stdout.write(
            "Sin ACTION_RELOCATED/ACTION_TRASHED previo (se dejan "
            "para la Always-on Task normal): %d" % skipped
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "Dry-run: nada de lo anterior se ha escrito de verdad."
            ))
