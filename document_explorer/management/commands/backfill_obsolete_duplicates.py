# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/backfill_obsolete_duplicates.py
"""
H30 (S48). La Fase A/B0/B1 escribió `document_type`/`domain_object`
para 11.000+ archivos que nunca pasaron por
`subject_upload_service.upload_subject_document()` (la única vía que
aplica `evaluate_substitution()` y marca `is_obsolete`). Resultado
real, verificado con datos: 1.172 grupos (mismo tipo + mismo sujeto)
con más de un documento "vigente" a la vez -- 8.750 documentos de más
que deberían estar marcados como obsoletos. Miguel Ángel, S48: "si es
necesario una migración, añadir un campo... se hace la migración, se
añade el campo y se muestran los documentos vigentes" -- el campo
(`is_obsolete`) ya existe (misma sesión); lo que faltaba era
RELLENARLO para los documentos que nunca pasaron por la sustitución
real.

Criterio, por grupo (mismo `document_type` + mismo sujeto):
- Si algún documento del grupo tiene `expiry_date`/`issue_date` ->
  mismo criterio real de `vigencia_service.is_current()` (el que ya
  usa la ficha para vigentes/obsoletos).
- Si NINGUNO tiene fecha -> el de `id` más alto (el indexado más
  reciente) queda vigente, el resto se marca obsoleto -- desempate
  explícito, nunca al azar.

DRY-RUN POR DEFECTO. Sin `--apply`, solo informa.

H35 (S107): excluye por completo los `document_type.is_cumulative=True`
(FORMACION, ENTREGA_INFORMACION, EPIS...) -- agrupar solo por
tipo+sujeto marcaria como obsoletos cursos/entregas reales y
distintos entre si que son legitimamente vigentes a la vez. Ver
docstring de `DocumentTypeCatalog.is_cumulative` en models.py.
"""
from django.core.management.base import BaseCommand
from django.db.models import Count

from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog
from document_management.vigencia_service import DocumentSnapshot, is_current

BUCKET = "cgs_grupo_alvarez"


class Command(BaseCommand):
    help = (
        "H30 (S48) -- marca is_obsolete en duplicados reales "
        "(mismo tipo+sujeto, nunca pasaron por la sustitucion real). "
        "Dry-run por defecto, --apply para escribir. Excluye tipos "
        "is_cumulative=True (S107)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        non_cumulative_ids = set(
            DocumentTypeCatalog.objects.filter(
                is_cumulative=False,
            ).values_list("id", flat=True)
        )

        groups = (
            DocumentIndexEntry.objects.filter(
                bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True, purged_at__isnull=True,
                document_type__isnull=False, domain_object_id__isnull=False,
                document_type_id__in=non_cumulative_ids,
                is_obsolete=False,
            )
            .values("document_type_id", "domain_content_type_id", "domain_object_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )

        stats = {"grupos": 0, "marcados_obsoletos": 0}

        for group in groups:
            stats["grupos"] += 1
            entries = list(
                DocumentIndexEntry.objects.filter(
                    bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
                    deleted_at__isnull=True, purged_at__isnull=True,
                    document_type_id=group["document_type_id"],
                    domain_content_type_id=group["domain_content_type_id"],
                    domain_object_id=group["domain_object_id"],
                    is_obsolete=False,
                ).order_by("id"),
            )

            has_any_date = any(
                e.expiry_date or e.issue_date for e in entries
            )

            if has_any_date:
                snapshots = {
                    e.pk: DocumentSnapshot(
                        identifier=e.pk, expiry_date=e.expiry_date,
                        issue_date=e.issue_date,
                    )
                    for e in entries
                }
                for entry in entries:
                    candidate = snapshots[entry.pk]
                    siblings = [
                        s for pk, s in snapshots.items() if pk != entry.pk
                    ]
                    if not is_current(candidate, siblings):
                        stats["marcados_obsoletos"] += 1
                        if apply_changes:
                            entry.is_obsolete = True
                            entry.save(update_fields=["is_obsolete"])
            else:
                # Sin ninguna fecha -- el id mas alto (mas reciente
                # indexado) queda vigente, el resto obsoleto.
                for entry in entries[:-1]:
                    stats["marcados_obsoletos"] += 1
                    if apply_changes:
                        entry.is_obsolete = True
                        entry.save(update_fields=["is_obsolete"])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
