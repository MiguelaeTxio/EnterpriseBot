# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/reorganize_root_tree_s127.py
"""
H30 (S127). Root tree reorganisation of the primary bucket.

---

H30 (S127). Reorganización del árbol raíz del cubo principal (Miguel
Ángel: "hicimos esto para tener un orden y que no fuese una selva").

Árbol final (aprobado por Miguel Ángel en S127):

    DOC. EMPRESA/
    DOC. MAQUINAS/
        ACCESORIOS DE ELEVACION/CERTIFICADOS|REVISIONES/<tipo>/
        MANUALES DE USO/
    DOC. PERSONAL/
    NO CONFORMES/
        CLASIFICACION/        (H28)
        WHATSAPP/             (entregas por WhatsApp)
        BANDEJA DE ENTRADA/   (Bandeja de entrada)
    _CUARENTENA/

Movimiento VIRTUAL (regla 4.12 de move_service): solo cambian
`parent_path`/`name` en el índice; `blob_name` y Google Cloud Storage no
se tocan. Usa las mismas primitivas que el panel (`merge_folders`,
`move_entries`). Los archivos de la papelera bajo una carpeta origen
se llevan también a su sitio nuevo (solo `parent_path`: los contadores
de carpeta no cuentan la papelera), para que al restaurarlos vuelvan al
árbol nuevo y no a una carpeta que ya no existe. Una carpeta origen sin
ningún archivo solo se borra del índice.

Sin --apply no escribe nada: informe de lo que haría. Idempotente: una
segunda ejecución no encuentra nada que mover.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.buckets import (
    INBOX_NO_CONFORMES_PREFIX, LIFTING_CERTIFICATES_FOLDER,
    LIFTING_REVIEWS_FOLDER, MANUAL_USO_FOLDER, NO_CONFORMES_PREFIX,
    NO_CONFORMES_ROOT, PRIMARY_BUCKET, WHATSAPP_NO_CONFORMES_PREFIX,
)
from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import (
    DocumentIndexEntry, WorkerDocumentSubmission, path_digest,
)
from document_explorer.move_service import merge_folders, move_entries

BUCKET = PRIMARY_BUCKET

# Carpetas raíz antiguas -> destino nuevo (subárbol completo).
FOLDER_MERGES = (
    ("_CERTIFICADOS_ACCESORIOS_ELEVACION", LIFTING_CERTIFICATES_FOLDER),
    ("_REVISIONES_ACCESORIOS_ELEVACION", LIFTING_REVIEWS_FOLDER),
    ("MANUALES DE USO", MANUAL_USO_FOLDER),
    ("MANUALES USO", MANUAL_USO_FOLDER),
    ("NO CONFORMES BANDEJA DE ENTRADA",
     INBOX_NO_CONFORMES_PREFIX.rstrip("/")),
)


def _tree_q(field, folder):
    return Q(**{field: folder}) | Q(**{"%s__startswith" % field: folder + "/"})


def _files_under(folder):
    """
    Every FILE row under `folder`, by state.

    ---

    Archivos bajo `folder` (vivos y en la papelera), para el informe y
    para no dejar huérfanos de la papelera.
    """
    rows = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        purged_at__isnull=True,
    ).filter(_tree_q("parent_path", folder))
    return (
        rows.filter(deleted_at__isnull=True).count(),
        rows.filter(deleted_at__isnull=False).count(),
    )


def _folder_rows(folder):
    return DocumentIndexEntry.objects.filter(
        bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FOLDER,
        purged_at__isnull=True,
    ).filter(_tree_q("blob_name", folder))


def _move_trashed(source, destination):
    """
    Re-home the trashed files under `source` (index only).

    ---

    Lleva los archivos de la papelera de `source` a la misma ruta
    relativa bajo `destination`, solo cambiando `parent_path` (y su
    hash). Crea la cadena de carpetas para que una restauración caiga
    en una carpeta que existe.
    """
    rows = list(DocumentIndexEntry.objects.filter(
        bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=False, purged_at__isnull=True,
    ).filter(_tree_q("parent_path", source)))
    targets = set()
    for entry in rows:
        relative = entry.parent_path[len(source):].lstrip("/")
        entry.parent_path = (
            "%s/%s" % (destination, relative) if relative else destination
        )
        entry.parent_path_hash = path_digest(entry.parent_path)
        targets.add(entry.parent_path)
    for target in targets:
        ensure_folder_chain(BUCKET, target)
    DocumentIndexEntry.objects.bulk_update(
        rows, ["parent_path", "parent_path_hash"], batch_size=500,
    )
    return len(rows)


class Command(BaseCommand):
    help = (
        "S127: reorganiza el árbol raíz del cubo principal (movimiento "
        "virtual). Sin --apply solo informa."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Ejecuta de verdad. Sin él, solo informe.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        self.stdout.write(
            "# [S127] Reorganización del árbol raíz -- %s"
            % ("APLICANDO" if apply else "MODO PRUEBA (sin --apply)")
        )
        problems = 0

        # 1) Carpetas raíz antiguas.
        for number, (source, destination) in enumerate(FOLDER_MERGES, 1):
            folders = _folder_rows(source).count()
            live, trashed = _files_under(source)
            if not folders and not live and not trashed:
                self.stdout.write(
                    "%d. %s: no existe -- nada que hacer." % (number, source)
                )
                continue
            self.stdout.write(
                "%d. %s -> %s: %d archivo(s) vivos, %d en la papelera, "
                "%d fila(s) de carpeta." % (
                    number, source, destination, live, trashed, folders,
                )
            )
            if not apply:
                continue
            if trashed:
                # merge_folders solo mueve los vivos y borra las filas de
                # carpeta: los de la papelera se llevan antes, a mano.
                moved_trash = _move_trashed(source, destination)
                self.stdout.write(
                    "   [OK] %d archivo(s) de la papelera llevados a %s."
                    % (moved_trash, destination)
                )
            if live:
                results, removed = merge_folders(BUCKET, source, destination)
                renamed = sum(
                    1 for row in results
                    if row["original_name"] != row["final_name"]
                )
                self.stdout.write(
                    "   [OK] %d movido(s) (%d renombrado(s) por colisión), "
                    "%d fila(s) de carpeta retiradas."
                    % (len(results), renamed, removed)
                )
            else:
                removed, _ = _folder_rows(source).delete()
                self.stdout.write(
                    "   [OK] Carpeta vacía retirada del índice (%d fila(s))."
                    % removed
                )

        # 2) Archivos sueltos en NO CONFORMES/ -> su subcarpeta.
        loose = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            parent_path=NO_CONFORMES_ROOT,
        ))
        whatsapp_pks = set(
            WorkerDocumentSubmission.objects.filter(
                entry_id__in=[entry.pk for entry in loose],
            ).values_list("entry_id", flat=True)
        )
        whatsapp = [entry for entry in loose if entry.pk in whatsapp_pks]
        classification = [
            entry for entry in loose if entry.pk not in whatsapp_pks
        ]
        trashed_loose = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=False, purged_at__isnull=True,
            parent_path=NO_CONFORMES_ROOT,
        ).count()
        number = len(FOLDER_MERGES) + 1
        self.stdout.write(
            "%d. %s/ sueltos: %d de WhatsApp -> %s, %d de clasificación "
            "-> %s (%d en la papelera, se quedan donde están)." % (
                number, NO_CONFORMES_ROOT, len(whatsapp),
                WHATSAPP_NO_CONFORMES_PREFIX.rstrip("/"),
                len(classification), NO_CONFORMES_PREFIX.rstrip("/"),
                trashed_loose,
            )
        )
        for entry in whatsapp + classification:
            self.stdout.write(
                "   - pk=%s %s" % (entry.pk, entry.name)
            )
        if apply:
            for group, destination in (
                (whatsapp, WHATSAPP_NO_CONFORMES_PREFIX.rstrip("/")),
                (classification, NO_CONFORMES_PREFIX.rstrip("/")),
            ):
                if group:
                    moved = move_entries(group, destination)
                    self.stdout.write(
                        "   [OK] %d movido(s) a %s." % (len(moved), destination)
                    )

        self.stdout.write(
            "# [S127] Fin. %s"
            % ("Paradas: %d." % problems if problems else "Sin paradas.")
        )
