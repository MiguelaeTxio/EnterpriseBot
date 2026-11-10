# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/find_empty_folders.py
"""
H30 (S72) -- deriva de un incidente real reportado por Miguel Ángel:
carpetas que en el explorador muestran "Sin resultados" porque TODO su
contenido ya está en papelera (`deleted_at`), pero la propia fila
FOLDER que las representa nunca se marcó, así que sigue apareciendo en
la navegación como si tuviera algo dentro. Limitación ya documentada
como pendiente en H29 S039 ("una carpeta vaciada... queda como fila
huérfana en el índice -- candidata a una futura herramienta de
'carpetas vacías'").

Alcance: TODO el cubo indexado, no solo `DOC. PERSONAL/ENTREGA EPIS`
-- instrucción explícita de Miguel Ángel en S72, verbatim: "no
solamente ya de los EPIs, sino de todo el cubo. Personal, dos
máquinas, todas las carpetas vacías deben quedar eliminadas [...] no
es solamente problema de la parte de Epis ni de entrega de Epis, sino
está en todo el cubo. Está en dos máquinas, está en dos personal, está
en todos lados." Por defecto recorre TODOS los cubos indexados con
filas FOLDER; `--bucket` acota a uno solo si hace falta.

Mecanismo (4.12 respetado -- escritura de índice pura, `blob_name`
nunca se toca en GCS): recorre las carpetas de más profunda a menos
profunda (bottom-up, por número de segmentos de `blob_name`),
calculando en cada nivel el número de hijos VIVOS reales (`deleted_at`/
`purged_at` nulos) -- NUNCA el `child_count` precalculado de la
propia fila, que está desactualizado porque `SendToTrashView` no lo
decrementa al enviar un hijo a papelera (mismo problema de fondo ya
corregido para los contadores en `recalculate_folder_counters.py`,
pero ese comando corrige el número, no decide si la carpeta debe
desaparecer de la navegación). Una carpeta con cero hijos vivos se
manda a papelera con `trash_dossier_entry()` (mismo mecanismo ya
probado en `trash_orphan_personal_documents.py`), lo que la excluye
del conteo de SU PROPIO padre en la misma pasada -- así una cadena de
carpetas que se ha ido vaciando de abajo a arriba (p. ej. varios años
de `ENTREGA EPIS` sin nada vivo dentro) se detecta entera de una sola
vez, sin relanzar el comando varias veces.

Mismo patrón de agrupación que `recalculate_folder_counters.py`
(parent_path exacto, una sola consulta por cubo -- nunca un COUNT por
carpeta), no `parent_path_hash`, por consistencia con ese comando
hermano.

DRY-RUN POR DEFECTO -- criterio de la plataforma para cualquier
`--apply` (ver `SESSION_VARIABLES.md`). Con `--apply` manda a papelera
de verdad. Tras aplicar, ejecutar `recalculate_folder_counters.py` por
cubo para dejar `child_count`/`total_size_bytes` de las carpetas
supervivientes consistentes con la nueva realidad -- responsabilidad
de ESE comando, no de este, para no mezclar "quién desaparece" con
"qué número le queda a quien se queda".

Uso:
    python -m dotenv run python manage.py find_empty_folders
    python -m dotenv run python manage.py find_empty_folders --bucket cgs_grupo_alvarez
    python -m dotenv run python manage.py find_empty_folders --apply
"""
from django.core.management.base import BaseCommand
from document_explorer.classification_service import trash_dossier_entry
from document_explorer.empty_folder_service import find_empty_folders
from document_explorer.models import DocumentIndexEntry


class Command(BaseCommand):
    help = (
        "H30 (S72) -- detecta y manda a papelera carpetas cuyo "
        "contenido está íntegramente en papelera/purgado, en todo el "
        "cubo indexado (o uno solo con --bucket). Dry-run por "
        "defecto, --apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )
        parser.add_argument(
            "--bucket", default=None,
            help=(
                "Restringe a un cubo concreto (p. ej. "
                "cgs_grupo_alvarez). Por defecto, todos los cubos con "
                "filas FOLDER vivas."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        bucket_filter = options["bucket"]

        if apply_changes:
            self.stdout.write(self.style.WARNING(
                "--apply activo: se escribirá de verdad."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "Dry-run (por defecto): no se escribirá nada. Usa "
                "--apply para mandar a papelera de verdad."
            ))

        buckets = (
            [bucket_filter] if bucket_filter else
            list(
                DocumentIndexEntry.objects.filter(
                    entry_kind=DocumentIndexEntry.KIND_FOLDER,
                    deleted_at__isnull=True,
                    purged_at__isnull=True,
                ).values_list("bucket", flat=True).distinct()
            )
        )

        grand_total = {"vacias": 0, "a_papelera": 0, "fallos": 0}

        for bucket in buckets:
            self.stdout.write(
                self.style.MIGRATE_HEADING("=== CUBO: %s ===" % bucket)
            )
            totals = self._process_bucket(bucket, apply_changes)
            for key in grand_total:
                grand_total[key] += totals[key]

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== TOTAL GENERAL (%s) ===" % (
                "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
            )
        ))
        for key, value in grand_total.items():
            self.stdout.write("    %s: %d" % (key, value))

    def _process_bucket(self, bucket, apply_changes):
        totals = {"vacias": 0, "a_papelera": 0, "fallos": 0}
        # S149: la detección vive en empty_folder_service (la comparte
        # el botón "Limpiar carpetas vacías" del explorador).
        for folder in find_empty_folders(bucket):
            totals["vacias"] += 1
            self.stdout.write(
                "  %s: %s" % (
                    "A PAPELERA" if apply_changes else "IRÍA A PAPELERA",
                    folder.blob_name,
                )
            )
            if not apply_changes:
                totals["a_papelera"] += 1
            elif trash_dossier_entry(folder):
                totals["a_papelera"] += 1
            else:
                totals["fallos"] += 1
                self.stdout.write("  FALLO: %s" % folder.blob_name)
        return totals
