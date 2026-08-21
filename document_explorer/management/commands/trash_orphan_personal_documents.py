# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/trash_orphan_personal_documents.py
"""
H30 (S62) -- manda a papelera documentos de dominio PERSONAL cuyo
`document_type` ya esta resuelto pero cuyo `domain_object_id` sigue
pendiente TRAS agotar los tres resolutores de
`resolve_domain_pending_types` (folder / nombre / ventana deslizante).

Decision explicita de Miguel Angel (S62), verbatim: "nosotros
tendremos los 70 que estan en el Excel de trabajadores [...] desde la
plataforma no podemos acceder a un nombre que no este dentro de esos
70 [...] documento que no haga referencia a una persona que este en
activo, ese documento se queda ya huerfano [...] documentos vinculados
a trabajadores que no esten dentro de esos 70 van directamente a la
papelera."

Principio 4.12 respetado: usa `trash_dossier_entry()` (deleted_at/
deleted_by, escritura de indice pura) -- `blob_name` en GCS nunca se
toca, el archivo real sigue accesible via Microsoft 365 o el propio
explorador de archivos del panel (solo deja de aparecer vinculado
desde la interfaz de documentacion por persona).

Alcance: solo los tipos de dominio PERSONAL ya agotados por
`resolve_domain_pending_types` (nunca PAGO_CORRIENTE, que es dominio
COMPANY desde S58 -- ver `resolve_company_worksite_domain.py`, un
problema distinto). No vuelve a intentar resolver -- eso ya lo hizo
`resolve_domain_pending_types` en el mismo Comando S previo de esta
sesion; este comando solo actua sobre lo que quedo sin resolver de
verdad.

DRY-RUN POR DEFECTO. Con --apply manda a papelera de verdad.
"""
from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.models import DocumentIndexEntry

# Tipos de dominio PERSONAL ya agotados por resolve_domain_pending_types
# (S58/S62) -- PAGO_CORRIENTE queda fuera a proposito, es dominio
# COMPANY desde S58.
DEFAULT_TYPES = [
    "INVESTIGACION_ACCIDENTE",
    "ENTREGA_INFORMACION",
    "BAJA_PERSONAL",
    "AUTORIZACION_USO_MAQUINARIA",
    "PARTE_BAJA_MEDICA",
]


class Command(BaseCommand):
    help = (
        "H30 (S62) -- manda a papelera documentos PERSONAL con tipo "
        "OK pero sin persona de los 70 activos vinculada, tras agotar "
        "resolve_domain_pending_types. Dry-run por defecto, --apply "
        "para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )
        parser.add_argument(
            "--types", nargs="+", default=DEFAULT_TYPES,
            help=(
                "Codigos de DocumentTypeCatalog a procesar (por "
                "defecto, los cinco tipos PERSONAL ya agotados)."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        types = options["types"]

        totals = {"candidatos": 0, "a_papelera": 0, "fallos": 0}

        for code in types:
            entries = list(
                DocumentIndexEntry.objects.filter(
                    bucket="cgs_grupo_alvarez",
                    entry_kind=DocumentIndexEntry.KIND_FILE,
                    document_type__code=code,
                    domain_object_id__isnull=True,
                    deleted_at__isnull=True,
                    purged_at__isnull=True,
                ).only("id", "name", "parent_path")
            )
            self.stdout.write(
                "--- %s: %d candidatos a papelera (huerfanos) ---"
                % (code, len(entries))
            )
            totals["candidatos"] += len(entries)

            for entry in entries:
                if apply_changes:
                    ok = trash_dossier_entry(entry)
                    if ok:
                        totals["a_papelera"] += 1
                    else:
                        totals["fallos"] += 1
                        self.stdout.write(
                            "FALLO: %s / %s"
                            % (entry.parent_path, entry.name)
                        )
                else:
                    self.stdout.write(
                        "  IRIA A PAPELERA: %s / %s"
                        % (entry.parent_path, entry.name)
                    )

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in totals.items():
            self.stdout.write("    %s: %d" % (key, value))
