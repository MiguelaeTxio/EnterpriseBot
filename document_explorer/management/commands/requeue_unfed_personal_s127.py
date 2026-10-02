# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/requeue_unfed_personal_s127.py
"""
H30 (S127). Unfed files of DOC. PERSONAL back to the H28 quarantine.

---

H30 (S127). Pasada pedida por Miguel Ángel: "sacar a la luz documentos
faltantes que se encuentran en las carpetas personales pero no han
nutrido la BBDD" (su propio contrato de 2025 estaba en la carpeta
antigua OPERARIOS/MUÑOZ CARA, MIGUEL ANGEL (GR) con un nombre que no lo
relacionaba y el aviso lo daba por inexistente).

Universo: archivos vivos de DOC. PERSONAL sin dueño o sin tipo (449 el
02/10/2026). Cada uno se reencola en la cuarentena del H28 con el mismo
movimiento virtual del botón "Reencolar" (blob_name intacto, 4.12) y una
nota de supervisor con su carpeta de origen, que es la pista de la
persona cuando el documento no lleva su nombre. El H28 los clasifica
con las reglas de S127 (nombre único, DNI con error de lectura,
pasajeros, dominio por el documento, dominio EMPRESA) y los archiva.

Sin --apply solo informa (reparto por carpeta). Idempotente: lo ya
reencolado está en _CUARENTENA y no vuelve a entrar.
"""
from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.buckets import PRIMARY_BUCKET, QUARANTINE_PREFIX
from document_explorer.models import DocumentIndexEntry
from document_explorer.move_service import move_entries

ROOT = "DOC. PERSONAL"
NOTE = (
    "Carpeta de origen: %s. Si el documento no trae nombre, es de la "
    "persona de esa carpeta (cuando la carpeta lleva nombre de persona)."
)


class Command(BaseCommand):
    help = (
        "S127: reencola en la cuarentena del H28 los archivos de DOC. "
        "PERSONAL sin dueño o sin tipo. Sin --apply solo informa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        apply = options["apply"]
        entries = list(DocumentIndexEntry.objects.filter(
            bucket=PRIMARY_BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).filter(
            Q(parent_path=ROOT) | Q(parent_path__startswith=ROOT + "/"),
        ).filter(
            Q(domain_object_id__isnull=True)
            | Q(document_type__isnull=True),
        ).order_by("parent_path", "name"))
        self.stdout.write(
            "# [S127] Reencolar DOC. PERSONAL sin dueño o sin tipo -- %s: "
            "%d archivo(s)." % (
                "APLICANDO" if apply else "MODO PRUEBA (sin --apply)",
                len(entries),
            )
        )
        by_folder = Counter(entry.parent_path for entry in entries)
        for folder, count in sorted(
            by_folder.items(), key=lambda item: (-item[1], item[0]),
        ):
            self.stdout.write("   %4d  %s" % (count, folder))
        if not apply:
            return
        groups = {}
        for entry in entries:
            note = NOTE % entry.parent_path
            if note not in (entry.curator_note or ""):
                entry.curator_note = (
                    "%s\n%s" % (entry.curator_note, note)
                    if entry.curator_note else note
                )
                entry.save(update_fields=["curator_note"])
            destination = QUARANTINE_PREFIX + entry.parent_path
            groups.setdefault(destination, []).append(entry)
        moved = 0
        for destination, group in groups.items():
            moved += len(move_entries(group, destination))
        self.stdout.write(
            "# [S127] Fin. %d archivo(s) reencolado(s) en la cuarentena; "
            "el H28 los irá clasificando en sus pasadas." % moved
        )
